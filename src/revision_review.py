"""Conferência humana de sinais do ROF080, preservada entre reimportações."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .journey import refresh_loyalty_for_vehicle
from .maintenance import reconcile_vehicle_service_history
from .repositories import audit


def review_event(db: Any, user: dict[str, Any], event_id: str,
                 action: str, revision_number: int | None = None) -> None:
    if action not in {"confirmada", "descartada"}:
        raise ValueError("Ação de revisão inválida.")
    event = db.revision_events.find_one({"_id": event_id})
    if not event:
        raise ValueError("Evidência não encontrada.")
    from .security import get_user_scope
    scope = get_user_scope(user)
    if scope and event.get("company_code") not in scope:
        raise PermissionError("Usuário fora do escopo da concessionária.")
    vid = event.get("vehicle_id")
    if action == "confirmada":
        if not vid or not event.get("closed_at") or event.get("post_sale") is not True:
            raise ValueError("A OS deve estar encerrada, vinculada ao veículo e posterior à venda.")
        if event.get("owner_match") is False:
            raise ValueError("Divergência de proprietário: valide o cadastro antes da confirmação.")
        if not isinstance(revision_number, int) or not 1 <= revision_number <= 18:
            raise ValueError("Informe uma etapa entre a 1ª e a 18ª revisão.")
    now = datetime.now(timezone.utc)
    db.revision_events.update_one({"_id": event_id}, {"$set": {
        "review_override": action, "manual_revision_number": revision_number if action == "confirmada" else None,
        "reviewed_by": user.get("email"), "reviewed_at": now,
    }})
    if action == "confirmada" and vid and revision_number <= 5:
        existing = db.revisions.find_one({"vehicle_id": vid, "revision_number": revision_number},
                                         {"status": 1})
        if not existing or existing.get("status") not in {
            "realizada", "externa_perdida", "cancelada", "nao_aplicavel"
        }:
            journey = db.journeys.find_one({"vehicle_id": vid})
            if journey:
                db.revisions.update_one(
                    {"vehicle_id": vid, "revision_number": revision_number},
                    {"$set": {
                        "status": "realizada", "performed_at": event.get("service_date"),
                        "performed_km": event.get("os_km"), "source": "rof080_revisado",
                        "service_order_id": event.get("service_order_id"),
                        "notes": "Validação humana registrada na importação ROF080.",
                        "customer_id": journey.get("customer_id"), "journey_id": journey.get("_id"),
                        "company_code": journey.get("company_code"),
                        "company_name": journey.get("company_name"),
                        "updated_at": now, "updated_by": user.get("email"),
                    }, "$setOnInsert": {"created_at": now}}, upsert=not bool(existing))
                refresh_loyalty_for_vehicle(db, vid)
                reconcile_vehicle_service_history(db, vid, user_email=user.get("email") or "system")
    audit(db, user, "revision_evidence_review", "revision_events", event_id,
          {"action": action, "revision_number": revision_number})
