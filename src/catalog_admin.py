"""CRUD auditável do catálogo SIGMEC, inclusive códigos padrão desativados."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .repositories import audit
from .revision_taxonomy import DEFAULT_CATALOG, normalize, possible_revision_numbers
from .security import can

CODE_PATTERN = re.compile(r"[A-Z0-9]{3,24}\Z")


def _authorize(user: dict[str, Any]) -> None:
    if not can(user, "settings.manage"):
        raise PermissionError("Sem permissão para modificar o catálogo SIGMEC.")


def validated_code(code: str) -> str:
    value = str(code or "").strip().upper()
    if not CODE_PATTERN.fullmatch(value):
        raise ValueError("O código deve ter de 3 a 24 caracteres alfanuméricos.")
    if value == "0010A14":
        raise ValueError("O código 0010A14 representa entrega e não pode ser cadastrado como revisão.")
    return value


def validated_description(description: str) -> str:
    value = " ".join(str(description or "").strip().split())
    if not 8 <= len(value) <= 200:
        raise ValueError("Informe descrição com 8 a 200 caracteres.")
    if "REVISAO" not in normalize(value):
        raise ValueError("A descrição deve identificar explicitamente uma revisão.")
    if not possible_revision_numbers(value):
        raise ValueError("Indique a etapa ordinal, como 1ª REVISÃO FLEX ou 2ª REVISÃO DIESEL.")
    return value


def catalog_rows(db: Any) -> list[dict[str, Any]]:
    base = {code: {"code": code, "description": desc, "default": True, "active": True}
            for code, desc in DEFAULT_CATALOG}
    for item in db.revision_catalog.find({}, {"_id": 1, "description": 1, "disabled": 1}):
        code = str(item["_id"]).strip().upper()
        default = code in base
        base[code] = {
            "code": code,
            "description": str(item.get("description") or (base.get(code) or {}).get("description") or ""),
            "default": default,
            "active": not bool(item.get("disabled")),
        }
    return sorted(base.values(), key=lambda row: row["code"])


def save_code(db: Any, user: dict[str, Any], code: str, description: str) -> None:
    _authorize(user)
    code = validated_code(code)
    description = validated_description(description)
    now = datetime.now(timezone.utc)
    db.revision_catalog.update_one({"_id": code}, {"$set": {
        "description": description, "disabled": False,
        "updated_at": now, "updated_by": user.get("email"),
    }}, upsert=True)
    audit(db, user, "revision_catalog_saved", "revision_catalog", code,
          {"description": description, "active": True})


def disable_code(db: Any, user: dict[str, Any], code: str) -> None:
    _authorize(user)
    code = validated_code(code)
    present = {row["code"]: row for row in catalog_rows(db)}
    if code not in present or not present[code]["active"]:
        raise ValueError("Código inexistente ou já desativado.")
    db.revision_catalog.update_one({"_id": code}, {"$set": {
        "description": present[code]["description"], "disabled": True,
        "updated_at": datetime.now(timezone.utc), "updated_by": user.get("email"),
    }}, upsert=True)
    audit(db, user, "revision_catalog_disabled", "revision_catalog", code)
