"""Métricas auditáveis de revisões ROF080, com escopo de concessionária."""
from __future__ import annotations

from typing import Any


def _scope(user: dict[str, Any]) -> dict[str, Any]:
    # O mesmo conceito de escopo das jornadas: código de empresa autorizado.
    from .repositories import scoped_filter
    return scoped_filter(user)


def get_revision_metrics(db: Any, user: dict[str, Any]) -> dict[str, Any]:
    scope = _scope(user)
    base_query = dict(scope)
    confirmed = {"$and": [base_query, {"$or": [
        {"classification": "confirmada", "review_override": {"$ne": "descartada"}},
        {"review_override": "confirmada"},
    ]}]}
    checked = {"$and": [base_query, {"classification": "verificar"},
                       {"review_override": {"$nin": ["confirmada", "descartada"]}}]}
    total = db.revision_events.count_documents(base_query)
    validated = db.revision_events.count_documents(confirmed)
    pending = db.revision_events.count_documents(checked)
    linked = db.revision_events.count_documents({**base_query, "vehicle_id": {"$ne": None}})
    ordinal = list(db.revision_events.aggregate([
        {"$match": confirmed},
        {"$project": {"vehicle_id": 1, "revision_stage": {
            "$ifNull": ["$manual_revision_number", "$revision_number"]}}},
        {"$match": {"revision_stage": {"$ne": None}}},
        {"$group": {"_id": "$revision_stage", "orders": {"$sum": 1},
                    "vehicles": {"$addToSet": "$vehicle_id"}}},
        {"$project": {"_id": 1, "orders": 1, "vehicles": {"$size": "$vehicles"}}},
        {"$sort": {"_id": 1}},
    ]))
    monthly = list(db.revision_events.aggregate([
        {"$match": confirmed},
        {"$match": {"service_date": {"$type": "date"}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$service_date"}},
                    "total": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]))
    by_confidence = list(db.revision_events.aggregate([
        {"$match": base_query},
        {"$group": {"_id": "$confidence", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]))
    return {"total": total, "confirmed": validated, "pending": pending,
            "linked": linked, "by_revision": ordinal, "monthly": monthly,
            "by_confidence": by_confidence}
