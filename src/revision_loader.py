"""Consulta consolidada das cinco revisões para as páginas operacionais.

Fonte das confirmações: plano da jornada e eventos ROF080 verificados;
nenhum cálculo nesta consulta persiste bonificações ou reclassifica OS.
"""
from __future__ import annotations

from typing import Any

from .revision_audit import summarize_journeys
from .security import get_user_scope


def _blocks(values: list[str], size: int = 400):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def load_five(db: Any, user: dict[str, Any], active_only: bool = True) -> dict[str, Any]:
    """Devolve a estrutura ``rows/by_stage/...`` exigida pelas cinco telas.

    Escopo vazio mantém a semântica existente do sistema: consulta global.
    Escopo preenchido restringe a consulta às empresas autorizadas.
    """
    query: dict[str, Any] = {}
    if user.get("role") != "superadmin":
        companies = get_user_scope(user)
        if companies:
            query["company_code"] = {"$in": companies}
    if active_only:
        query["status"] = {"$ne": "cancelada"}

    journeys = list(db.journeys.find(query, {
        "vehicle_id": 1, "customer_id": 1, "company_name": 1,
        "company_code": 1, "status": 1, "sale_date": 1,
    }))
    vehicle_ids = list({str(j["vehicle_id"]) for j in journeys if j.get("vehicle_id")})
    customer_ids = list({str(j["customer_id"]) for j in journeys if j.get("customer_id")})
    vehicles: dict[str, dict[str, Any]] = {}
    customers: dict[str, dict[str, Any]] = {}
    revisions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for ids in _blocks(vehicle_ids):
        query_ids = {"$in": ids}
        for item in db.vehicles.find({"_id": query_ids}, {"plate": 1, "chassis": 1, "model": 1}):
            vehicles[str(item["_id"])] = item
        revisions.extend(db.revisions.find({"vehicle_id": query_ids}))
        events.extend(db.revision_events.find({"vehicle_id": query_ids}))
    for ids in _blocks(customer_ids):
        for item in db.customers.find({"_id": {"$in": ids}}, {"name": 1}):
            customers[str(item["_id"])] = item

    return summarize_journeys(journeys, vehicles, customers, revisions, events)
