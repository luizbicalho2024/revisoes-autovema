from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dateutil.relativedelta import relativedelta
from pymongo import UpdateOne
from pymongo.database import Database


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_revision_rules(db: Database) -> list[dict[str, Any]]:
    doc = db.settings.find_one({"_id": "revision_rules"}) or {}
    rules = doc.get("rules") or []
    normalized = []
    for n in range(1, 6):
        current = next((r for r in rules if int(r.get("revision_number", 0)) == n), {})
        normalized.append(
            {
                "revision_number": n,
                "months_after_sale": current.get("months_after_sale"),
                "km": current.get("km"),
            }
        )
    return normalized


def get_loyalty_bonuses(db: Database) -> dict[int, float]:
    doc = db.settings.find_one({"_id": "loyalty"}) or {}
    raw = doc.get("bonuses") or {"3": 1.0, "4": 2.0, "5": 3.0}
    result: dict[int, float] = {}
    for key, value in raw.items():
        try:
            result[int(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def calculate_due_date(sale_date: datetime | None, months_after_sale: Any) -> datetime | None:
    if not sale_date or months_after_sale in (None, ""):
        return None
    try:
        months = int(months_after_sale)
    except (TypeError, ValueError):
        return None
    return sale_date + relativedelta(months=months)


def recalculate_revision_plan(db: Database, user_email: str) -> dict[str, int]:
    rules = get_revision_rules(db)
    now = utcnow()
    ops: list[UpdateOne] = []
    journey_count = 0

    for journey in db.journeys.find({"status": "ativa"}):
        journey_count += 1
        sale_date = journey.get("sale_date")
        for rule in rules:
            n = int(rule["revision_number"])
            due_date = calculate_due_date(sale_date, rule.get("months_after_sale"))
            default_status = "pendente" if due_date else "nao_parametrizada"
            ops.append(
                UpdateOne(
                    {"vehicle_id": journey["vehicle_id"], "revision_number": n},
                    {
                        "$set": {
                            "customer_id": journey.get("customer_id"),
                            "journey_id": journey.get("_id"),
                            "company_code": journey.get("company_code"),
                            "company_name": journey.get("company_name"),
                            "due_date": due_date,
                            "due_km": rule.get("km"),
                            "updated_at": now,
                            "updated_by": user_email,
                        },
                        "$setOnInsert": {
                            "status": default_status,
                            "performed_at": None,
                            "performed_km": None,
                            "notes": None,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
            )

    if ops:
        db.revisions.bulk_write(ops, ordered=False)
    refresh_loyalty_for_all(db)
    return {"journeys": journey_count, "revision_records": len(ops)}


def loyalty_level_from_revisions(revisions: list[dict[str, Any]], bonuses: dict[int, float]) -> tuple[int, float, bool, str | None]:
    by_number = {int(r.get("revision_number", 0)): r for r in revisions}
    if any((r.get("status") == "externa_perdida") for r in revisions):
        return 0, 0.0, True, "Foi registrada revisão fora da concessionária/evasão."

    consecutive = 0
    for n in range(1, 6):
        rev = by_number.get(n)
        if rev and rev.get("status") == "realizada":
            consecutive = n
        else:
            break

    if consecutive >= 5:
        return 5, float(bonuses.get(5, 3.0)), False, None
    if consecutive >= 4:
        return 4, float(bonuses.get(4, 2.0)), False, None
    if consecutive >= 3:
        return 3, float(bonuses.get(3, 1.0)), False, None
    return consecutive, 0.0, False, None


def refresh_loyalty_for_vehicle(db: Database, vehicle_id: str) -> None:
    journey = db.journeys.find_one({"vehicle_id": vehicle_id})
    if not journey:
        return
    revisions = list(db.revisions.find({"vehicle_id": vehicle_id}).sort("revision_number", 1))
    level, bonus, cancelled, reason = loyalty_level_from_revisions(revisions, get_loyalty_bonuses(db))
    db.journeys.update_one(
        {"_id": journey["_id"]},
        {
            "$set": {
                "current_revision": level,
                "loyalty_bonus_pct": bonus,
                "loyalty_cancelled": cancelled,
                "loyalty_cancel_reason": reason,
                "updated_at": utcnow(),
            }
        },
    )


def refresh_loyalty_for_all(db: Database) -> None:
    for vehicle_id in db.journeys.distinct("vehicle_id"):
        refresh_loyalty_for_vehicle(db, vehicle_id)
