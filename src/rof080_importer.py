"""Importação ROF080 em leitura sequencial, idempotente e sem dados brutos no Git."""
from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Callable
from zipfile import ZipFile
import re

from lxml import etree
from pymongo import UpdateOne
from pymongo.database import Database

from .importer import clean_chassis, clean_code, clean_date, clean_digits, clean_float, clean_int, clean_plate, clean_text
from .journey import refresh_loyalty_for_vehicle
from .maintenance import get_service_reconciliation_settings, reconcile_vehicle_service_history
from .repositories import audit
from .revision_taxonomy import catalog_from_database, parse_evidence, normalize

EXPECTED = {"ORDEM SERV.", "OS OBSERVACAO", "SERVICOS", "DATA ABERT.", "CHASSI", "DATA ENCER."}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _read_rows(file_bytes: bytes):
    """Leitor OOXML incremental: não carrega os 290 MB do XML em memória.

    ROF080 fornecido pela operação não possui <dimension>; leitores Excel
    tradicionais podem demorar muito antes de apresentar a prévia.
    """
    with ZipFile(BytesIO(file_bytes)) as archive:
        # A exportação analisada traz uma única aba de dados. Se houver outras,
        # identifica o cabeçalho pelo conteúdo da linha, não pelo nome da aba.
        names = [n for n in archive.namelist()
                 if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
        if not names:
            raise ValueError("Arquivo XLSX sem planilha de serviços.")
        strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as fh:
                for _, si in etree.iterparse(fh, events=("end",), tag="{*}si"):
                    strings.append("".join(si.itertext()))
                    si.clear()
                    while si.getprevious() is not None:
                        del si.getparent()[0]
        found = False
        for sheet_name in names:
            with archive.open(sheet_name) as fh:
                columns: dict[str, int] | None = None
                for _, element in etree.iterparse(fh, events=("end",), tag="{*}row"):
                    values: dict[int, Any] = {}
                    for cell in element:
                        if not cell.tag.endswith("}c"):
                            continue
                        addr = cell.get("r") or ""
                        col = re.match(r"[A-Z]+", addr)
                        if not col:
                            continue
                        idx = 0
                        for letter in col.group():
                            idx = idx * 26 + ord(letter) - 64
                        idx -= 1
                        t = cell.get("t")
                        if t == "inlineStr":
                            inline = cell.find("{*}is")
                            value = "".join(inline.itertext()) if inline is not None else None
                        else:
                            v = cell.find("{*}v")
                            raw = v.text if v is not None else None
                            if t == "s" and raw is not None:
                                value = strings[int(raw)]
                            elif t in ("n", None) and raw:
                                try:
                                    value = float(raw) if "." in raw or "E" in raw.upper() else int(raw)
                                except ValueError:
                                    value = raw
                            else:
                                value = raw
                        if value is not None:
                            values[idx] = value
                    if columns is None:
                        header = {i: normalize(v) for i, v in values.items()}
                        if EXPECTED.issubset(set(header.values())):
                            columns = {name: idx for idx, name in header.items() if name}
                            found = True
                    else:
                        yield {key: values.get(idx) for key, idx in columns.items()}
                    element.clear()
                    while element.getprevious() is not None:
                        del element.getparent()[0]
            if found:
                break
        if not found:
            raise ValueError("Estrutura ROF080 não reconhecida; verifique a planilha Serviços Oficina.")


def preview_rof080(file_bytes: bytes, max_rows: int = 8) -> list[dict[str, Any]]:
    wanted = ["ORDEM SERV.", "SERVICOS", "DATA ENCER.", "KM", "PLACA", "CHASSI"]
    result = []
    for row in _read_rows(file_bytes):
        if row.get("ORDEM SERV."):
            result.append({k: str(row.get(k) or "")[:110] for k in wanted})
        if len(result) >= max_rows:
            break
    return result


def _aggregate(file_bytes: bytes, catalog: dict[str, str], progress: Callable[[int], None] | None):
    orders: dict[str, dict[str, Any]] = {}
    counters: Counter[str] = Counter()
    for row in _read_rows(file_bytes):
        counters["rows_received"] += 1
        os_number = clean_code(row.get("ORDEM SERV."))
        chassis = clean_chassis(row.get("CHASSI"))
        dealer = clean_digits(row.get("CNPJ CONCESSIONARIA")) or clean_code(row.get("DEALER NUMBER"))
        if not os_number or not chassis or not dealer:
            counters["rows_skipped"] += 1
            continue
        key = f"os:ROF080:{dealer}:{os_number}"
        item = orders.get(key)
        if item is None:
            item = {
                "_id": key, "source": "rof080", "company_dealer": dealer,
                "company_name": clean_text(row.get("NOME CONCESSIONARIA")),
                "os_code": os_number, "os_number": os_number, "chassis": chassis,
                "plate": clean_plate(row.get("PLACA")),
                "model": clean_text(row.get("MODELO DESCRICAO")),
                "owner_document": clean_digits(row.get("CNPJ/CPF DO CLIENTE")),
                "owner_name": clean_text(row.get("NOME DO CLIENTE")),
                "os_km": clean_int(row.get("KM")),
                "created_at_source": clean_date(row.get("DATA ABERT.")),
                "closed_at": clean_date(row.get("DATA ENCER.")),
                "report_sale_at": clean_date(row.get("DATA VENDA")),
                "service_amount": 0.0, "product_amount": 0.0,
                "total_amount": 0.0, "source_rows": 0,
                "services": [], "evidences": [],
            }
            orders[key] = item
        elif item["chassis"] != chassis:
            # Uma OS de concessionária com chassi conflitante requer tratamento manual.
            item["conflicting_chassis"] = True
        item["source_rows"] += 1
        opened = clean_date(row.get("DATA ABERT."))
        closed = clean_date(row.get("DATA ENCER."))
        if opened and (not item["created_at_source"] or opened < item["created_at_source"]):
            item["created_at_source"] = opened
        if closed and (not item["closed_at"] or closed > item["closed_at"]):
            item["closed_at"] = closed
        km = clean_int(row.get("KM"))
        if km is not None:
            item["os_km"] = km
        product = clean_float(row.get("TOTAL PECAS")) or 0.0
        service = clean_float(row.get("TOTAL SERVICOS")) or 0.0
        item["product_amount"] += product
        item["service_amount"] += service
        item["total_amount"] += product + service
        service_label = clean_text(row.get("SERVICOS"))
        if service_label and service_label not in item["services"] and len(item["services"]) < 24:
            item["services"].append(service_label[:140])
        evidence = parse_evidence(
            row.get("SERVICOS"), row.get("DESCRICAO"),
            row.get("OS OBSERVACAO"), item.get("model"), catalog,
        )
        if evidence and evidence not in item["evidences"] and len(item["evidences"]) < 12:
            item["evidences"].append(evidence)
        if progress and counters["rows_received"] % 5000 == 0:
            progress(counters["rows_received"])
    counters["unique_orders"] = len(orders)
    return orders, counters


def _choose_evidence(order: dict[str, Any]) -> dict[str, Any] | None:
    evidences = order.get("evidences") or []
    if not evidences:
        return None
    ranking = {"servico": 0, "sem_numero": 1, "observacao": 2,
               "observacao_sem_numero": 3, "ambiguo": 4}
    best_rank = min(ranking.get(e.get("confidence"), 4) for e in evidences)
    best = [e for e in evidences if ranking.get(e.get("confidence"), 4) == best_rank]
    nums = {e.get("revision_number") for e in best if e.get("revision_number")}
    if len(nums) > 1 or order.get("conflicting_chassis"):
        return {"revision_number": None, "confidence": "ambiguo", "evidence_source": "divergencia",
                "evidence_text": "A OS contém evidências ou chassis conflitantes"}
    return best[0]


def _related(db: Database, batch: list[dict[str, Any]], settings: dict[str, Any]):
    chassis = list({order["chassis"] for order in batch})
    vehicles = {v["chassis"]: v for v in db.vehicles.find(
        {"chassis": {"$in": chassis}}, {"_id": 1, "chassis": 1, "customer_id": 1}
    )}
    ids = [v["_id"] for v in vehicles.values()]
    journeys = {j["vehicle_id"]: j for j in db.journeys.find(
        {"vehicle_id": {"$in": ids}},
        {"_id": 1, "vehicle_id": 1, "customer_id": 1, "company_code": 1,
         "company_name": 1, "sale_date": 1, "status": 1}
    )}
    customer_ids = [j["customer_id"] for j in journeys.values() if j.get("customer_id")]
    customers = {c["_id"]: c for c in db.customers.find(
        {"_id": {"$in": customer_ids}}, {"_id": 1, "document": 1}
    )}
    for order in batch:
        v = vehicles.get(order["chassis"])
        j = journeys.get(v["_id"]) if v else None
        c = customers.get(j.get("customer_id")) if j else None
        owner = order.get("owner_document")
        target = clean_digits(c.get("document")) if c else None
        owner_match = owner == target if owner and target else None
        service_date = order.get("closed_at") or order.get("created_at_source")
        sale_date = j.get("sale_date") if j else None
        if isinstance(sale_date, datetime):
            sale_date = sale_date.replace(tzinfo=timezone.utc) if sale_date.tzinfo is None else sale_date
        post_sale = (service_date.date() >= sale_date.date()) if service_date and sale_date else None
        eligible = bool(
            v and j and post_sale is True and order.get("closed_at")
            and not order.get("conflicting_chassis")
            and (owner_match is True or (not settings.get("require_owner_match", True)
                                         and owner_match is not False))
        )
        if not v: link = "unmatched_vehicle"
        elif not j: link = "no_journey"
        elif post_sale is False: link = "pre_sale"
        elif owner_match is False: link = "owner_mismatch"
        elif not order.get("closed_at"): link = "open_order"
        else: link = "matched"
        yield order, v, j, c, owner_match, post_sale, eligible, link, service_date


def _write_batch(db: Database, batch: list[dict[str, Any]], job_id: str,
                 user: dict[str, Any], settings: dict[str, Any],
                 counters: Counter[str], affected: set[str], completed: set[str]):
    now = utcnow()
    ops: list[UpdateOne] = []
    events: list[UpdateOne] = []
    for order, vehicle, journey, customer, owner_match, post_sale, eligible, link, service_date in _related(db, batch, settings):
        vid = vehicle["_id"] if vehicle else None
        if vid: affected.add(vid)
        if eligible: counters["linked_closed_orders"] += 1
        else: counters["unlinked_or_ineligible_orders"] += 1
        evidence = _choose_evidence(order)
        stored = {k: value for k, value in order.items() if k not in {"evidences", "report_sale_at"}}
        stored.update({
            "vehicle_id": vid, "journey_id": journey["_id"] if journey else None,
            "customer_id": journey.get("customer_id") if journey else None,
            "company_code": journey.get("company_code") if journey else None,
            "owner_match": owner_match, "post_sale": post_sale,
            "link_status": link, "eligible_reconciliation": eligible,
            "service_date": service_date, "source_revision": evidence,
            "updated_at": now, "updated_by": user.get("email"), "last_import_job_id": job_id,
            "service_amount": round(order["service_amount"], 2),
            "product_amount": round(order["product_amount"], 2),
            "total_amount": round(order["total_amount"], 2),
        })
        ops.append(UpdateOne({"_id": order["_id"]}, {
            "$set": stored,
            "$setOnInsert": {"created_at": now, "created_by": user.get("email")},
        }, upsert=True))
        if not evidence:
            continue
        counters["orders_with_revision_signal"] += 1
        n = evidence.get("revision_number")
        confirmed = bool(eligible and n and evidence.get("confidence") == "servico")
        if confirmed: counters["confirmed_revisions"] += 1
        elif evidence.get("confidence") in {"observacao", "observacao_sem_numero"}:
            counters["observation_signals"] += 1
        elif evidence.get("confidence") == "sem_numero": counters["unclassified_revisions"] += 1
        else: counters["revision_review_required"] += 1
        event = {
            "_id": f"revision:ROF080:{order['_id']}", "source": "rof080",
            "service_order_id": order["_id"], "os_number": order["os_number"],
            "company_dealer": order["company_dealer"], "company_name": order["company_name"],
            "company_code": journey.get("company_code") if journey else None,
            "vehicle_id": vid, "customer_id": journey.get("customer_id") if journey else None,
            "chassis": order["chassis"], "plate": order["plate"], "model": order["model"],
            "revision_number": n, "classification": "confirmada" if confirmed else "verificar",
            "confidence": evidence["confidence"], "evidence_source": evidence["evidence_source"],
            "evidence_text": evidence["evidence_text"],
            "reference_km": evidence.get("reference_km"),
            "service_date": service_date, "closed_at": order.get("closed_at"),
            "os_km": order["os_km"], "link_status": link,
            "owner_match": owner_match, "post_sale": post_sale,
            "updated_at": now, "last_import_job_id": job_id,
        }
        events.append(UpdateOne({"_id": event["_id"]}, {
            "$set": event, "$setOnInsert": {"created_at": now},
        }, upsert=True))
        if not confirmed or not journey or not vid or not 1 <= int(n) <= 5:
            continue
        existing = db.revisions.find_one({"vehicle_id": vid, "revision_number": int(n)},
                                         {"status": 1, "source": 1, "performed_at": 1})
        # A importação não altera decisões manuais, evasões nem confirmações anteriores.
        if existing and existing.get("status") in {"externa_perdida", "cancelada", "nao_aplicavel"}:
            continue
        if existing and existing.get("status") == "realizada":
            continue
        db.revisions.update_one(
            {"vehicle_id": vid, "revision_number": int(n)},
            {"$set": {
                "status": "realizada", "source": "rof080_confirmado",
                "service_order_id": order["_id"], "performed_at": service_date,
                "performed_km": order["os_km"],
                "notes": "Revisão comprovada por serviço em OS ROF080 encerrada.",
                "customer_id": journey.get("customer_id"), "journey_id": journey["_id"],
                "company_code": journey.get("company_code"), "company_name": journey.get("company_name"),
                "updated_at": now, "updated_by": "import:rof080",
            }, "$setOnInsert": {"created_at": now}}, upsert=not bool(existing))
        completed.add(vid)
    if ops: db.service_orders.bulk_write(ops, ordered=False)
    if events: db.revision_events.bulk_write(events, ordered=False)


def import_rof080(db: Database, file_bytes: bytes, filename: str,
                  user: dict[str, Any], progress: Callable[[int], None] | None = None) -> dict[str, Any]:
    digest = hashlib.sha256(file_bytes).hexdigest()
    previous = db.import_jobs.find_one({"import_type": "rof080", "file_sha256": digest, "status": "success"})
    if previous:
        return {**(previous.get("summary") or {}), "already_imported": True}
    started = utcnow()
    job_id = f"import:rof080:{digest[:20]}:{int(started.timestamp())}"
    db.import_jobs.insert_one({
        "_id": job_id, "import_type": "rof080", "file_sha256": digest,
        "filename": filename, "started_at": started, "status": "processing",
        "user_email": user.get("email"),
    })
    counters: Counter[str] = Counter()
    try:
        catalog = catalog_from_database(db)
        orders, counters = _aggregate(file_bytes, catalog, progress)
        if not orders:
            raise ValueError("Nenhuma OS válida foi encontrada no relatório.")
        settings = get_service_reconciliation_settings(db)
        affected: set[str] = set()
        completed: set[str] = set()
        values = list(orders.values())
        for idx in range(0, len(values), 400):
            _write_batch(db, values[idx:idx + 400], job_id, user, settings,
                         counters, affected, completed)
        del orders, values
        # A jornada e as métricas anteriores permanecem consistentes após a importação.
        for vid in affected:
            reconcile_vehicle_service_history(db, vid, user_email="import:rof080")
        for vid in completed:
            refresh_loyalty_for_vehicle(db, vid)
        counters["vehicles_reconciled"] = len(affected)
        counters["vehicles_with_new_confirmations"] = len(completed)
        summary = dict(counters)
        db.import_jobs.update_one({"_id": job_id}, {"$set": {
            "status": "success", "finished_at": utcnow(), "summary": summary,
        }})
        audit(db, user, "import_success", "ROF080", job_id, {"filename": filename, **summary})
        return summary
    except Exception as exc:
        db.import_jobs.update_one({"_id": job_id}, {"$set": {
            "status": "failed", "finished_at": utcnow(), "error": str(exc)[:500],
            "summary": dict(counters),
        }})
        audit(db, user, "import_failed", "ROF080", job_id,
              {"filename": filename, "error": str(exc)[:300]})
        raise
