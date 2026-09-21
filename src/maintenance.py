from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database


DEFAULT_SERVICE_RECONCILIATION = {
    "km_tolerance": 1500,
    "days_tolerance": 45,
    "require_owner_match": True,
}

MAINTENANCE_LABELS = {
    "em_dia": "Em dia",
    "conciliar": "OS conciliada — confirmar revisão",
    "atrasada": "Manutenção atrasada",
    "sem_parametros": "Sem regra de revisão",
    "sem_historico": "Sem histórico de OS",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_service_reconciliation_settings(db: Database) -> dict[str, Any]:
    doc = db.settings.find_one({"_id": "service_reconciliation"}) or {}
    raw = doc.get("rules") or {}

    try:
        km_tolerance = int(
            raw.get("km_tolerance", DEFAULT_SERVICE_RECONCILIATION["km_tolerance"])
        )
    except (TypeError, ValueError):
        km_tolerance = DEFAULT_SERVICE_RECONCILIATION["km_tolerance"]

    try:
        days_tolerance = int(
            raw.get(
                "days_tolerance",
                DEFAULT_SERVICE_RECONCILIATION["days_tolerance"],
            )
        )
    except (TypeError, ValueError):
        days_tolerance = DEFAULT_SERVICE_RECONCILIATION["days_tolerance"]

    return {
        "km_tolerance": max(0, min(km_tolerance, 10000)),
        "days_tolerance": max(0, min(days_tolerance, 365)),
        "require_owner_match": bool(
            raw.get(
                "require_owner_match",
                DEFAULT_SERVICE_RECONCILIATION["require_owner_match"],
            )
        ),
    }


def evaluate_match(
    revision: dict[str, Any],
    order: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    due_km = revision.get("due_km")
    due_date = revision.get("due_date")
    service_km = order.get("os_km")
    service_date = order.get("service_date")

    checks = 0
    passed = 0
    km_delta = None
    days_delta = None

    if due_km not in (None, "") and service_km not in (None, ""):
        checks += 1
        km_delta = abs(int(service_km) - int(due_km))
        if km_delta <= int(settings["km_tolerance"]):
            passed += 1

    if due_date and service_date:
        checks += 1
        days_delta = abs((service_date.date() - due_date.date()).days)
        if days_delta <= int(settings["days_tolerance"]):
            passed += 1

    if checks == 0 or passed == 0:
        return None

    if checks >= 2 and passed == checks:
        confidence = "alta"
        rank = 0
    else:
        confidence = "media"
        rank = 1

    km_score = (
        km_delta / max(int(settings["km_tolerance"]), 1)
        if km_delta is not None
        else 1.0
    )
    date_score = (
        days_delta / max(int(settings["days_tolerance"]), 1)
        if days_delta is not None
        else 1.0
    )

    return {
        "confidence": confidence,
        "rank": rank,
        "score": float(km_score + date_score),
        "km_delta": km_delta,
        "days_delta": days_delta,
        "matched_checks": passed,
        "configured_checks": checks,
    }


def _eligible_order(order: dict[str, Any], settings: dict[str, Any]) -> bool:
    if not order.get("vehicle_id"):
        return False
    if order.get("post_sale") is not True:
        return False
    if settings.get("require_owner_match") and order.get("owner_match") is False:
        return False
    return bool(order.get("service_date"))


def reconcile_vehicle_service_history(
    db: Database,
    vehicle_id: str,
    user_email: str = "system",
) -> dict[str, Any]:
    journey = db.journeys.find_one({"vehicle_id": vehicle_id})
    if not journey:
        return {
            "vehicle_id": vehicle_id,
            "status": "sem_historico",
            "candidates": 0,
        }

    settings = get_service_reconciliation_settings(db)
    revisions = list(
        db.revisions.find({"vehicle_id": vehicle_id}).sort("revision_number", 1)
    )
    orders = list(
        db.service_orders.find({"vehicle_id": vehicle_id}).sort("service_date", 1)
    )
    eligible = [order for order in orders if _eligible_order(order, settings)]

    # Limpa apenas sugestões automáticas. Uma revisão confirmada pelo usuário continua intacta.
    for revision in revisions:
        db.revisions.update_one(
            {"_id": revision["_id"]},
            {
                "$unset": {
                    "candidate_service_order_id": "",
                    "candidate_confidence": "",
                    "candidate_km_delta": "",
                    "candidate_days_delta": "",
                    "candidate_score": "",
                }
            },
        )

    candidate_pairs: list[tuple[int, float, int, str, str, dict[str, Any]]] = []

    for revision in revisions:
        if revision.get("status") == "realizada":
            continue

        rejected = set(revision.get("rejected_service_order_ids") or [])
        for order in eligible:
            if order["_id"] in rejected:
                continue

            evaluated = evaluate_match(revision, order, settings)
            if not evaluated:
                continue

            candidate_pairs.append(
                (
                    int(evaluated["rank"]),
                    float(evaluated["score"]),
                    int(revision.get("revision_number") or 0),
                    str(revision["_id"]),
                    str(order["_id"]),
                    evaluated,
                )
            )

    candidate_pairs.sort(key=lambda item: (item[0], item[1], item[2]))

    used_revisions: set[str] = set()
    used_orders: set[str] = set()
    assignments: dict[str, tuple[str, dict[str, Any]]] = {}

    for _, _, _, revision_id, order_id, evaluated in candidate_pairs:
        if revision_id in used_revisions or order_id in used_orders:
            continue
        used_revisions.add(revision_id)
        used_orders.add(order_id)
        assignments[revision_id] = (order_id, evaluated)

    for revision_id, (order_id, evaluated) in assignments.items():
        db.revisions.update_one(
            {"_id": revision_id},
            {
                "$set": {
                    "candidate_service_order_id": order_id,
                    "candidate_confidence": evaluated["confidence"],
                    "candidate_km_delta": evaluated["km_delta"],
                    "candidate_days_delta": evaluated["days_delta"],
                    "candidate_score": evaluated["score"],
                    "updated_at": utcnow(),
                    "updated_by": user_email,
                }
            },
        )

    latest_order = max(
        eligible,
        key=lambda order: order.get("service_date")
        or datetime.min.replace(tzinfo=timezone.utc),
        default=None,
    )
    latest_km = latest_order.get("os_km") if latest_order else None
    latest_date = latest_order.get("service_date") if latest_order else None

    refreshed = list(
        db.revisions.find({"vehicle_id": vehicle_id}).sort("revision_number", 1)
    )

    has_parameter = any(
        revision.get("due_date") or revision.get("due_km") not in (None, "")
        for revision in refreshed
    )

    maintenance_status = "em_dia"
    maintenance_reason = "Nenhuma revisão vencida identificada."
    next_revision_number = None
    next_due_date = None
    next_due_km = None

    if not refreshed or not has_parameter:
        maintenance_status = "sem_parametros"
        maintenance_reason = (
            "Configure os prazos e/ou quilometragens das revisões para classificar a manutenção."
        )
    else:
        now = utcnow()
        unfinished = [r for r in refreshed if r.get("status") != "realizada"]

        if not eligible and unfinished:
            maintenance_status = "sem_historico"
            maintenance_reason = "Nenhuma ordem de serviço foi conciliada para este veículo."

        for revision in refreshed:
            if revision.get("status") == "realizada":
                continue

            next_revision_number = int(revision.get("revision_number") or 0)
            next_due_date = revision.get("due_date")
            next_due_km = revision.get("due_km")

            due_by_date = bool(
                revision.get("due_date") and revision["due_date"] <= now
            )
            due_by_km = bool(
                revision.get("due_km") not in (None, "")
                and latest_km not in (None, "")
                and int(latest_km) >= int(revision["due_km"])
            )
            due = due_by_date or due_by_km

            if due and revision.get("candidate_service_order_id"):
                maintenance_status = "conciliar"
                maintenance_reason = (
                    f"A {next_revision_number}ª revisão está vencida pelo plano, "
                    "mas existe uma OS compatível aguardando confirmação."
                )
            elif due:
                maintenance_status = "atrasada"
                maintenance_reason = (
                    f"A {next_revision_number}ª revisão atingiu o prazo/quilometragem "
                    "e não possui revisão realizada nem OS compatível."
                )
            else:
                maintenance_status = "em_dia"
                maintenance_reason = (
                    f"A próxima etapa é a {next_revision_number}ª revisão e ainda "
                    "não atingiu o prazo/quilometragem configurados."
                )
            break

        if not unfinished:
            maintenance_status = "em_dia"
            maintenance_reason = "Todas as revisões previstas no plano estão realizadas."

    db.journeys.update_one(
        {"_id": journey["_id"]},
        {
            "$set": {
                "maintenance_status": maintenance_status,
                "maintenance_status_reason": maintenance_reason,
                "latest_service_at": latest_date,
                "latest_service_km": latest_km,
                "service_order_count": len(eligible),
                "next_revision_number": next_revision_number,
                "next_due_date": next_due_date,
                "next_due_km": next_due_km,
                "service_reconciled_at": utcnow(),
                "updated_at": utcnow(),
            }
        },
    )

    return {
        "vehicle_id": vehicle_id,
        "status": maintenance_status,
        "candidates": len(assignments),
        "service_orders": len(orders),
    }


def reconcile_all_service_history(
    db: Database,
    user_email: str = "system",
) -> dict[str, int]:
    vehicle_ids = db.journeys.distinct("vehicle_id")
    total = 0
    candidates = 0

    for vehicle_id in vehicle_ids:
        result = reconcile_vehicle_service_history(
            db,
            vehicle_id,
            user_email=user_email,
        )
        total += 1
        candidates += int(result.get("candidates", 0))

    return {
        "vehicles": total,
        "candidates": candidates,
    }
