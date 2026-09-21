from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from pymongo.database import Database

from .security import get_user_scope


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def scoped_filter(user: dict[str, Any], field: str = "company_code") -> dict[str, Any]:
    scope = get_user_scope(user)
    if not scope:
        return {}
    return {field: {"$in": scope}}


def array_scoped_filter(user: dict[str, Any], field: str = "company_codes") -> dict[str, Any]:
    scope = get_user_scope(user)
    if not scope:
        return {}
    return {field: {"$in": scope}}


def combine_filters(*filters: dict[str, Any] | None) -> dict[str, Any]:
    valid = [f for f in filters if f]
    if not valid:
        return {}
    if len(valid) == 1:
        return valid[0]
    return {"$and": valid}


def text_search_filter(term: str, fields: Iterable[str]) -> dict[str, Any]:
    term = (term or "").strip()
    if not term:
        return {}
    escaped = re.escape(term)
    return {"$or": [{field: {"$regex": escaped, "$options": "i"}} for field in fields]}


def audit(
    db: Database,
    user: dict[str, Any] | None,
    action: str,
    entity: str,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.audit_logs.insert_one(
        {
            "created_at": utcnow(),
            "user_email": (user or {}).get("email", "system"),
            "user_name": (user or {}).get("name", "Sistema"),
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "details": details or {},
        }
    )
