"""Importação SIGMEC .001 com conciliação estrita por OS ROF080.

Não atribui chassi a partir de placa ou modelo e não modifica bonificações.
OS não localizada continua em sigmec_orders para auditoria posterior.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from pymongo import UpdateOne

from .repositories import audit
from .revision_taxonomy import catalog_from_database, fuel_for_model, possible_revision_numbers
from .sigmec_parser import catalog_candidates, normalize_os, parse_sigmec


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _chunks(items: list[Any], size: int = 220):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _os_variants(number: str) -> set[str]:
    clean = normalize_os(number)
    if not clean:
        return set()
    return {clean, clean.zfill(7), clean.zfill(8), clean.zfill(9), clean.zfill(10)}


def _find_rof080(db: Any, group: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    variants: set[str] = set()
    for row in group:
        variants.update(_os_variants(row["os_number"]))
    found: dict[str, list[dict[str, Any]]] = {}
    if not variants:
        return found
    projection = {
        "_id": 1, "source": 1, "os_number": 1, "company_dealer": 1,
        "chassis": 1, "plate": 1, "model": 1, "vehicle_id": 1,
        "customer_id": 1, "journey_id": 1, "company_code": 1,
        "service_date": 1, "closed_at": 1, "post_sale": 1,
        "owner_match": 1, "eligible_reconciliation": 1,
        "link_status": 1, "os_km": 1, "company_name": 1,
    }
    for doc in db.service_orders.find(
        {"source": "rof080", "os_number": {"$in": sorted(variants)}}, projection
    ):
        key = normalize_os(doc.get("os_number"))
        if key:
            found.setdefault(key, []).append(doc)
    return found


def _pick_order(sigmec: dict[str, Any], matched: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if not matched:
        return None, "sem_rof080"
    if len(matched) == 1:
        doc = matched[0]
        dealer = str(doc.get("company_dealer") or "").strip()
        # CNPJ (14 dígitos) e código interno (7 dígitos) não são diretamente comparáveis.
        if len(dealer) == 7 and dealer != sigmec["dealer_code"]:
            return None, "concessionaria_divergente"
        return doc, "os_localizada"
    exact = [doc for doc in matched if str(doc.get("company_dealer") or "").strip() == sigmec["dealer_code"]]
    return (exact[0], "os_localizada") if len(exact) == 1 else (None, "os_ambiguas")


def _stage_for_code(code: str, catalog: dict[str, str], model: str | None) -> int | None:
    description = catalog.get(code)
    if not description:
        return None
    fuel = fuel_for_model(model)
    desc_upper = description.upper()
    if fuel == "diesel" and "FLEX" in desc_upper and "DIESEL" not in desc_upper:
        return None
    if fuel == "flex" and "DIESEL" in desc_upper and "FLEX" not in desc_upper:
        return None
    numbers = possible_revision_numbers(description, model)
    return numbers[0] if len(numbers) == 1 and numbers[0] in {1, 2, 3, 4, 5} else None


def _audit_evidence(db: Any, order: dict[str, Any], sigmec: dict[str, Any],
                    intervention: dict[str, str], catalog: dict[str, str],
                    now: datetime, counters: Counter[str]) -> tuple[UpdateOne | None, str]:
    code = intervention["code"]
    model = str(order.get("model") or "")
    if order.get("vehicle_id"):
        vehicle = db.vehicles.find_one({"_id": order["vehicle_id"]}, {"fuel": 1, "model": 1}) or {}
        model = " ".join(str(x or "") for x in (model, vehicle.get("fuel"), vehicle.get("model")))
    stage = _stage_for_code(code, catalog, model)
    if not stage:
        return None, "etapa_ambigua" if code in catalog else "nao_catalogado"

    event_id = f"revision:ROF080:{order['_id']}"
    old = db.revision_events.find_one({"_id": event_id},
        {"review_override": 1, "classification": 1, "revision_number": 1, "manual_revision_number": 1})
    if old and old.get("review_override") == "descartada":
        return None, "descartada_manualmente"
    if old and old.get("revision_number") is not None:
        try:
            previous = int(old["revision_number"])
        except (ValueError, TypeError):
            previous = None
        if previous is not None and previous != stage:
            return None, "divergencia_etapa"
    if old and old.get("review_override") == "confirmada":
        return None, "confirmacao_manual_preservada"

    can_confirm = bool(
        order.get("eligible_reconciliation") is True
        and order.get("closed_at")
        and order.get("post_sale") is True
        and order.get("link_status") == "matched"
        and order.get("vehicle_id")
        and order.get("owner_match") is not False
    )
    # A evidência SIGMEC não se sobrepõe a uma confirmação anterior legítima.
    if old and old.get("classification") == "confirmada":
        return None, "confirmacao_existente_preservada"

    status = "confirmada" if can_confirm else "verificar"
    event = {
        "source": "rof080", "service_order_id": order["_id"],
        "os_number": order.get("os_number"),
        "company_dealer": order.get("company_dealer"),
        "company_name": order.get("company_name"),
        "company_code": order.get("company_code"),
        "vehicle_id": order.get("vehicle_id"),
        "customer_id": order.get("customer_id"),
        "chassis": order.get("chassis"), "plate": order.get("plate"),
        "model": order.get("model"),
        "revision_number": stage,
        "classification": status,
        "confidence": "servico", "evidence_source": "codigo",
        "evidence_text": f"Código SIGMEC {code} - {intervention.get('label') or catalog.get(code, '')}"[:140],
        "sigmec_code": code, "sigmec_dealer_code": sigmec["dealer_code"],
        "service_date": order.get("service_date"), "closed_at": order.get("closed_at"),
        "os_km": order.get("os_km"), "link_status": order.get("link_status"),
        "owner_match": order.get("owner_match"), "post_sale": order.get("post_sale"),
        "updated_at": now,
    }
    counters["events_qualified"] += 1
    if can_confirm:
        counters["events_eligible_for_confirming"] += 1
    return UpdateOne({"_id": event_id}, {"$set": event, "$setOnInsert": {"created_at": now}}, upsert=True), (
        "confirmada" if can_confirm else "etapa_identificada_pendente"
    )


def preview_sigmec(data: bytes, filename: str, catalog: dict[str, str]) -> dict[str, Any]:
    rows, summary = parse_sigmec(data, filename)
    return {**summary, **catalog_candidates(rows, catalog),
            "example_codes": sorted({p["code"] for row in rows for p in row["interventions"]})[:30]}


def import_sigmec(db: Any, data: bytes, filename: str, user: dict[str, Any],
                  progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    rows, parsed = parse_sigmec(data, filename)
    digest = hashlib.sha256(data).hexdigest()
    previous = db.import_jobs.find_one({"import_type": "sigmec001", "file_sha256": digest,
                                        "status": "success"})
    if previous:
        return {"already_imported": True, **(previous.get("summary") or {})}
    catalog = catalog_from_database(db)
    job_id = f"sigmec001:{digest}"
    now = _now()
    db.import_jobs.update_one({"_id": job_id}, {"$set": {
        "import_type": "sigmec001", "filename": filename,
        "file_sha256": digest, "status": "processing", "started_at": now,
    }}, upsert=True)
    counters: Counter[str] = Counter()
    candidates = catalog_candidates(rows, catalog)
    try:
        for chunk in _chunks(rows):
            lookup = _find_rof080(db, chunk)
            updates_orders = []
            updates_events = []
            for sig in chunk:
                counters["orders_processed"] += 1
                order, link = _pick_order(sig, lookup.get(sig["os_normalized"], []))
                counters[link] += 1
                conclusions = []
                revision_interventions = [
                    item for item in sig["interventions"]
                    if item["code"] in catalog and item["code"] != "0010A14"
                ]
                counters["delivery_services_excluded"] += sum(
                    item["code"] == "0010A14" for item in sig["interventions"]
                )
                stages_found = {
                    _stage_for_code(item["code"], catalog, str(order.get("model") or ""))
                    for item in revision_interventions
                } if order else set()
                conflicting_stages = len({n for n in stages_found if n is not None}) > 1
                for intervention in revision_interventions:
                    code = intervention["code"]
                    counters["catalog_revision_items"] += 1
                    if conflicting_stages:
                        status = "multiplas_etapas_mesma_os"
                    elif order:
                        update, status = _audit_evidence(db, order, sig, intervention, catalog, now, counters)
                        if update:
                            updates_events.append((str(order["_id"]), update))
                    else:
                        status = "sem_os_conciliada"
                    counters[status] += 1
                    conclusions.append({"code": code, "status": status})
                # Não armazenar dados pessoais que aparecem nas linhas #C.
                public_doc = {
                    "source": "sigmec001", "dealer_code": sig["dealer_code"],
                    "os_number": sig["os_number"], "os_normalized": sig["os_normalized"],
                    "report_date_hint": sig["report_date_hint"],
                    "interventions": sig["interventions"],
                    "rof080_order_id": order["_id"] if order else None,
                    "link_status": link, "revision_results": conclusions,
                    "updated_at": now,
                }
                key = f"sigmec:{sig['dealer_code']}:{sig['os_normalized']}"
                updates_orders.append(UpdateOne({"_id": key}, {"$set": public_doc,
                    "$addToSet": {"source_files": filename, "source_hashes": digest},
                    "$setOnInsert": {"created_at": now}}, upsert=True))
            if updates_orders:
                db.sigmec_orders.bulk_write(updates_orders, ordered=False)
            if updates_events:
                # Uma OS pode ter mais de um código de revisão e um único
                # evento ROF080; não sobrescrever silenciosamente estágios.
                dedup_events = {}
                for order_key, update in updates_events:
                    dedup_events[order_key] = update
                db.revision_events.bulk_write(list(dedup_events.values()), ordered=False)
            if progress:
                progress(counters["orders_processed"], len(rows))
        summary = {**parsed, **candidates, **dict(counters)}
        db.import_jobs.update_one({"_id": job_id}, {"$set": {
            "status": "success", "summary": summary, "finished_at": _now(),
        }})
        audit(db, user, "sigmec001_imported", "import_jobs", job_id,
              {"orders": summary["orders_processed"],
               "revision_codes": summary.get("catalog_revision_items", 0),
               "events_qualified": summary.get("events_qualified", 0)})
        return summary
    except Exception as exc:
        db.import_jobs.update_one({"_id": job_id}, {"$set": {
            "status": "failed", "finished_at": _now(),
            "error_type": type(exc).__name__,
        }})
        raise
