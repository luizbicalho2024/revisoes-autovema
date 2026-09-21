from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st


APP_NAME = "Dealer Hub | Revisões Autovema"
APP_SHORT_NAME = "Dealer Hub"
BRAND_PRIMARY = "#B5121B"
BRAND_DARK = "#17202A"
BRAND_MUTED = "#6B7280"

ROLES = {
    "superadmin": "Superadministrador",
    "admin": "Administrador",
    "gestor": "Gestor",
    "operador": "Operador",
    "consulta": "Consulta",
}

ROLE_PERMISSIONS = {
    "superadmin": {"*"},
    "admin": {
        "dashboard.view",
        "customers.view",
        "vehicles.view",
        "journey.view",
        "journey.edit",
        "loyalty.view",
        "import.execute",
        "reports.export",
        "users.manage",
        "settings.manage",
        "audit.view",
    },
    "gestor": {
        "dashboard.view",
        "customers.view",
        "vehicles.view",
        "journey.view",
        "journey.edit",
        "loyalty.view",
        "reports.export",
    },
    "operador": {
        "dashboard.view",
        "customers.view",
        "vehicles.view",
        "journey.view",
        "journey.edit",
        "loyalty.view",
    },
    "consulta": {
        "dashboard.view",
        "customers.view",
        "vehicles.view",
        "journey.view",
        "loyalty.view",
    },
}

REVISION_STATUSES = {
    "nao_parametrizada": "Não parametrizada",
    "pendente": "Pendente",
    "agendada": "Agendada",
    "realizada": "Realizada na concessionária",
    "externa_perdida": "Realizada fora / evasão",
    "cancelada": "Cancelada",
    "nao_aplicavel": "Não aplicável",
}

DEFAULT_LOYALTY_BONUSES = {3: 1.0, 4: 2.0, 5: 3.0}


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    mongo_database: str
    bootstrap_name: str
    bootstrap_email: str
    bootstrap_password: str
    timezone: str
    session_timeout_hours: int


def _secret(section: str, key: str, default: Any = None) -> Any:
    try:
        value = st.secrets[section][key]
        return value if value is not None else default
    except Exception:
        return default


def get_settings() -> Settings:
    mongo_uri = str(_secret("mongo", "uri", "")).strip()
    database = str(_secret("mongo", "database", "dealer_hub")).strip() or "dealer_hub"
    return Settings(
        mongo_uri=mongo_uri,
        mongo_database=database,
        bootstrap_name=str(_secret("auth", "bootstrap_name", "Administrador Dealer Hub")).strip(),
        bootstrap_email=str(_secret("auth", "bootstrap_email", "")).strip().lower(),
        bootstrap_password=str(_secret("auth", "bootstrap_password", "")),
        timezone=str(_secret("app", "timezone", "America/Porto_Velho")).strip(),
        session_timeout_hours=int(_secret("app", "session_timeout_hours", 8) or 8),
    )
