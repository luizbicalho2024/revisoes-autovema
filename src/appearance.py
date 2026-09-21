from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database


DEFAULT_APPEARANCE = {
    "system_name": "Dealer Hub",
    "system_subtitle": "Revisões Autovema",
    "primary_color": "#B5121B",
    "secondary_color": "#17202A",
    "accent_color": "#F59E0B",
    "background_color": "#F6F8FB",
    "surface_color": "#FFFFFF",
    "text_color": "#17202A",
    "muted_color": "#667085",
    "border_color": "#E4E7EC",
    "sidebar_color": "#101828",
    "sidebar_text_color": "#F8FAFC",
    "border_radius": 14,
    "sidebar_width": 304,
    "show_scope": True,
}

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_LOGO_BYTES = 1_500_000
ALLOWED_LOGO_MIMES = {"image/png", "image/jpeg", "image/webp"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean_hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text.upper() if HEX_RE.fullmatch(text) else fallback


def _clean_text(value: Any, fallback: str, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    return (text or fallback)[:limit]


def detect_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_appearance(values: dict[str, Any] | None) -> dict[str, Any]:
    values = values or {}
    result = dict(DEFAULT_APPEARANCE)

    result["system_name"] = _clean_text(
        values.get("system_name"), DEFAULT_APPEARANCE["system_name"], 60
    )
    result["system_subtitle"] = _clean_text(
        values.get("system_subtitle"), DEFAULT_APPEARANCE["system_subtitle"], 90
    )

    for key in (
        "primary_color",
        "secondary_color",
        "accent_color",
        "background_color",
        "surface_color",
        "text_color",
        "muted_color",
        "border_color",
        "sidebar_color",
        "sidebar_text_color",
    ):
        result[key] = _clean_hex(values.get(key), DEFAULT_APPEARANCE[key])

    try:
        result["border_radius"] = max(
            6, min(int(values.get("border_radius", DEFAULT_APPEARANCE["border_radius"])), 28)
        )
    except (TypeError, ValueError):
        result["border_radius"] = DEFAULT_APPEARANCE["border_radius"]

    try:
        result["sidebar_width"] = max(
            260, min(int(values.get("sidebar_width", DEFAULT_APPEARANCE["sidebar_width"])), 380)
        )
    except (TypeError, ValueError):
        result["sidebar_width"] = DEFAULT_APPEARANCE["sidebar_width"]

    result["show_scope"] = bool(
        values.get("show_scope", DEFAULT_APPEARANCE["show_scope"])
    )
    return result


def get_appearance_settings(db: Database) -> dict[str, Any]:
    doc = db.settings.find_one({"_id": "appearance"}) or {}
    return {
        **normalize_appearance(doc.get("theme")),
        "logo_b64": doc.get("logo_b64"),
        "logo_mime": doc.get("logo_mime"),
        "logo_name": doc.get("logo_name"),
        "logo_sha256": doc.get("logo_sha256"),
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }


def logo_data_uri(appearance: dict[str, Any] | None) -> str | None:
    appearance = appearance or {}
    mime = appearance.get("logo_mime")
    payload = appearance.get("logo_b64")
    if mime not in ALLOWED_LOGO_MIMES or not payload:
        return None
    return f"data:{mime};base64,{payload}"


def save_appearance_settings(
    db: Database,
    values: dict[str, Any],
    user_email: str,
    *,
    logo_bytes: bytes | None = None,
    logo_name: str | None = None,
    remove_logo: bool = False,
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "theme": normalize_appearance(values),
        "updated_at": _utcnow(),
        "updated_by": user_email,
    }
    operation: dict[str, Any] = {"$set": update}

    if remove_logo:
        operation["$unset"] = {
            "logo_b64": "",
            "logo_mime": "",
            "logo_name": "",
            "logo_sha256": "",
        }
    elif logo_bytes is not None:
        if len(logo_bytes) > MAX_LOGO_BYTES:
            raise ValueError("O logotipo deve ter no máximo 1,5 MB.")

        mime = detect_image_mime(logo_bytes)
        if mime not in ALLOWED_LOGO_MIMES:
            raise ValueError(
                "Arquivo inválido. Use uma imagem PNG, JPG/JPEG ou WEBP válida."
            )

        update.update(
            {
                "logo_b64": base64.b64encode(logo_bytes).decode("ascii"),
                "logo_mime": mime,
                "logo_name": _clean_text(logo_name, "logo", 120),
                "logo_sha256": hashlib.sha256(logo_bytes).hexdigest(),
            }
        )

    db.settings.update_one({"_id": "appearance"}, operation, upsert=True)
    return get_appearance_settings(db)


def reset_appearance_settings(db: Database, user_email: str) -> None:
    db.settings.update_one(
        {"_id": "appearance"},
        {
            "$set": {
                "theme": dict(DEFAULT_APPEARANCE),
                "updated_at": _utcnow(),
                "updated_by": user_email,
            },
            "$unset": {
                "logo_b64": "",
                "logo_mime": "",
                "logo_name": "",
                "logo_sha256": "",
            },
        },
        upsert=True,
    )
