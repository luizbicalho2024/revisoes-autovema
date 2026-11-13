"""Reprocessa OS SIGMEC persistidas após alterações no catálogo.

Não lê novamente arquivos .001, não altera bônus nem aprova conflitos entre
etapas. Decisões de revisão manual nunca são desfeitas.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from itertools import islice
from typing import Any, Callable

from pymongo import UpdateOne

from .repositories import audit
from .revision_bi import stage_from_code
from .revision_taxonomy import catalog_from_database, possible_revision_numbers
from .security import can
from .sigmec_importer import _audit_evidence, _find_rof080, _pick_order


def _batches(items: Any, length: int = 180):
    iterator = iter(items)
    while True:
        part = list(islice(iterator, length))
        if not part:
            return
        yield part


def classify_interventions(interventions: list[dict[str, Any]], catalog: dict[str, str],
                           model: str) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """Uma OS só gera uma etapa quando todos os códigos relevantes concordam."""
    candidates = []
    for item in interventions or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        if code == "0010A14" or code not in catalog:
            continue
        if not any(n in (1, 2, 3, 4, 5) for n in possible_revision_numbers(catalog[code], model)):
            continue
        candidates.append({"code": code, "label": str(item.get("label") or "")})
    if not candidates:
        return [], None
    stages = {stage_from_code(x["code"], catalog, model) for x in candidates}
    if None in stages or len(stages) != 1:
        return [{"code": x["code"], "status": "etapa_ambigua"} for x in candidates], None
    candidate = min(candidates, key=lambda item: item["code"])
    return [{"code": x["code"], "status": "etapa_identificada_pendente"} for x in candidates], candidate


def _invalidate_automatic(db: Any, old_order_id: Any, valid_codes: set[str],
                          candidate_stage: int | None, now: datetime) -> bool:
    """Neutraliza prova antiga SIGMEC quando o catálogo mudou ou código saiu."""
    if not old_order_id:
        return False
    key = f"revision:ROF080:{old_order_id}"
    previous = db.revision_events.find_one({"_id": key}, {
        "sigmec_code": 1, "revision_number": 1, "review_override": 1,
    })
    if not previous or not previous.get("sigmec_code"):
        return False
    if previous.get("review_override") in ("confirmada", "descartada"):
        return False
    original_stage = previous.get("revision_number")
    unchanged = (str(previous["sigmec_code"]).upper() in valid_codes
                 and original_stage == candidate_stage)
    if unchanged:
        return False
    db.revision_events.update_one({"_id": key}, {"$set": {
        "classification": "verificar", "revision_number": None,
        "confidence": "catalogo_revisado", "sigmec_code": None,
        "evidence_source": "codigo",
        "evidence_text": "Classificação SIGMEC alterada; conferir OS novamente.",
        "updated_at": now,
    }})
    return True


def sync_existing_orders(db: Any, user: dict[str, Any],
                         progress: Callable[[int, int], None] | None = None) -> dict[str, int]:
    if not can(user, "settings.manage"):
        raise PermissionError("Somente administradores podem sincronizar OS SIGMEC.")
    catalog = catalog_from_database(db)
    total = db.sigmec_orders.count_documents({})
    counts: Counter[str] = Counter()
    now = datetime.now(timezone.utc)
    cursor = db.sigmec_orders.find({}, {
        "_id": 1, "dealer_code": 1, "os_number": 1, "os_normalized": 1,
        "interventions": 1, "rof080_order_id": 1,
    }).sort("_id", 1)
    for chunk in _batches(cursor):
        lookup = _find_rof080(db, chunk)
        order_updates = []
        for sig in chunk:
            counts["os_processadas"] += 1
            old_order = sig.get("rof080_order_id")
            order, link = _pick_order(sig, lookup.get(str(sig.get("os_normalized") or ""), []))
            model = str((order or {}).get("model") or "")
            if order and order.get("vehicle_id"):
                vehicle = db.vehicles.find_one({"_id": order["vehicle_id"]}, {"fuel": 1, "model": 1}) or {}
                model = " ".join(str(x or "") for x in (model, vehicle.get("fuel"), vehicle.get("model")))
            conclusions, candidate = classify_interventions(sig.get("interventions") or [], catalog, model)
            chosen_stage = stage_from_code(candidate["code"], catalog, model) if candidate else None
            allowed_codes = {x["code"] for x in conclusions} if candidate else set()
            new_order = order["_id"] if order else None
            if _invalidate_automatic(db, old_order,
                                     allowed_codes if old_order == new_order else set(),
                                     chosen_stage if old_order == new_order else None, now):
                counts["eventos_anteriores_pendentes"] += 1
            if order:
                counts["os_vinculadas"] += 1
            else:
                counts["os_sem_rof080"] += 1

            if candidate and order:
                key = f"revision:ROF080:{new_order}"
                prev = db.revision_events.find_one({"_id": key}, {
                    "review_override": 1, "sigmec_code": 1,
                    "revision_number": 1, "classification": 1, "confidence": 1,
                })
                if prev is None:
                    update, status = _audit_evidence(db, order, sig, candidate, catalog, now, counts)
                    if update is not None:
                        db.revision_events.bulk_write([update], ordered=False)
                        counts["eventos_novos"] += 1
                elif prev.get("review_override") in ("confirmada", "descartada"):
                    status = "decisao_manual_preservada"
                elif prev.get("confidence") == "catalogo_revisado" or (
                    prev.get("revision_number") is None and not prev.get("sigmec_code")
                ):
                    status = "revisao_manual_necessaria"
                else:
                    status = "evento_existente_preservado"
                conclusions = [{"code": x["code"], "status": status} for x in conclusions]
            elif candidate and not order:
                conclusions = [{"code": x["code"], "status": "sem_os_conciliada"} for x in conclusions]
            elif conclusions:
                counts["os_etapa_ambigua"] += 1

            order_updates.append(UpdateOne({"_id": sig["_id"]}, {"$set": {
                "rof080_order_id": new_order, "link_status": link,
                "revision_results": conclusions, "catalog_sync_at": now,
                "updated_at": now,
            }}))
        if order_updates:
            db.sigmec_orders.bulk_write(order_updates, ordered=False)
        if progress:
            progress(counts["os_processadas"], total)
    if progress:
        progress(counts["os_processadas"], total)
    summary = {name: int(value) for name, value in counts.items()}
    summary.setdefault("os_processadas", 0)
    summary.setdefault("eventos_novos", 0)
    summary.setdefault("eventos_anteriores_pendentes", 0)
    audit(db, user, "sigmec_catalog_resynchronized", "sigmec_orders", "all", summary)
    return summary
