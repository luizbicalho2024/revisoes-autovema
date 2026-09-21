from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import (
    AutoReconnect,
    NotPrimaryError,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from .config import DEFAULT_LOYALTY_BONUSES, get_settings
from .security import hash_password, normalize_email


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@st.cache_resource(show_spinner=False)
def get_client() -> MongoClient:
    settings = get_settings()
    if not settings.mongo_uri:
        raise RuntimeError(
            "MongoDB não configurado. Adicione [mongo].uri nos Secrets do Streamlit Cloud."
        )

    client = MongoClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=20000,
        retryWrites=True,
        retryReads=True,
        tz_aware=True,
        appname="dealer-hub-revisoes-autovema",
    )
    client.admin.command("ping")
    return client


def get_db() -> Database:
    settings = get_settings()
    return get_client()[settings.mongo_database]


def ensure_indexes(db: Database) -> None:
    db.users.create_index(
        [("email", ASCENDING)],
        unique=True,
        name="uq_users_email",
    )
    db.users.create_index(
        [("active", ASCENDING), ("role", ASCENDING)],
        name="ix_users_active_role",
    )

    db.customers.create_index(
        [("document", ASCENDING)],
        unique=True,
        name="uq_customer_document",
        partialFilterExpression={"document": {"$type": "string"}},
    )
    db.customers.create_index(
        [("name", ASCENDING)],
        name="ix_customer_name",
    )
    db.customers.create_index(
        [("company_codes", ASCENDING)],
        name="ix_customer_company",
    )
    db.customers.create_index(
        [("last_purchase_at", DESCENDING)],
        name="ix_customer_last_purchase",
    )

    db.vehicles.create_index(
        [("chassis", ASCENDING)],
        unique=True,
        name="uq_vehicle_chassis",
        partialFilterExpression={"chassis": {"$type": "string"}},
    )
    db.vehicles.create_index(
        [("plate", ASCENDING)],
        name="ix_vehicle_plate",
    )
    db.vehicles.create_index(
        [("customer_id", ASCENDING)],
        name="ix_vehicle_customer",
    )
    db.vehicles.create_index(
        [("company_codes", ASCENDING)],
        name="ix_vehicle_company",
    )

    db.sales.create_index(
        [("company_code", ASCENDING), ("invoice_code", ASCENDING)],
        unique=True,
        name="uq_sale_company_invoice",
    )
    db.sales.create_index(
        [("customer_id", ASCENDING), ("sale_date", DESCENDING)],
        name="ix_sale_customer_date",
    )
    db.sales.create_index(
        [("vehicle_id", ASCENDING), ("sale_date", DESCENDING)],
        name="ix_sale_vehicle_date",
    )
    db.sales.create_index(
        [("sale_date", DESCENDING)],
        name="ix_sale_date",
    )

    db.journeys.create_index(
        [("vehicle_id", ASCENDING)],
        unique=True,
        name="uq_journey_vehicle",
    )
    db.journeys.create_index(
        [("company_code", ASCENDING), ("status", ASCENDING)],
        name="ix_journey_company_status",
    )
    db.journeys.create_index(
        [("maintenance_status", ASCENDING)],
        name="ix_journey_maintenance",
    )

    db.revisions.create_index(
        [("vehicle_id", ASCENDING), ("revision_number", ASCENDING)],
        unique=True,
        name="uq_revision_vehicle_number",
    )
    db.revisions.create_index(
        [
            ("company_code", ASCENDING),
            ("status", ASCENDING),
            ("due_date", ASCENDING),
        ],
        name="ix_revision_status_due",
    )
    db.revisions.create_index(
        [("candidate_service_order_id", ASCENDING)],
        name="ix_revision_candidate_os",
    )

    db.service_orders.create_index(
        [("chassis", ASCENDING), ("service_date", DESCENDING)],
        name="ix_service_chassis_date",
    )
    db.service_orders.create_index(
        [("vehicle_id", ASCENDING), ("service_date", DESCENDING)],
        name="ix_service_vehicle_date",
    )
    db.service_orders.create_index(
        [("customer_id", ASCENDING), ("service_date", DESCENDING)],
        name="ix_service_customer_date",
    )
    db.service_orders.create_index(
        [("company_name", ASCENDING), ("service_date", DESCENDING)],
        name="ix_service_company_date",
    )
    db.service_orders.create_index(
        [("link_status", ASCENDING)],
        name="ix_service_link_status",
    )
    db.service_orders.create_index(
        [("os_number", ASCENDING)],
        name="ix_service_os_number",
    )

    db.import_jobs.create_index(
        [("started_at", DESCENDING)],
        name="ix_import_started",
    )
    db.import_jobs.create_index(
        [("file_sha256", ASCENDING)],
        name="ix_import_hash",
    )
    db.import_jobs.create_index(
        [("import_type", ASCENDING), ("started_at", DESCENDING)],
        name="ix_import_type_started",
    )

    db.audit_logs.create_index(
        [("created_at", DESCENDING)],
        name="ix_audit_created",
    )
    db.audit_logs.create_index(
        [("user_email", ASCENDING), ("created_at", DESCENDING)],
        name="ix_audit_user",
    )


def ensure_default_settings(db: Database) -> None:
    now = utcnow()

    db.settings.update_one(
        {"_id": "loyalty"},
        {
            "$setOnInsert": {
                "enabled": True,
                "program_name": "Recompra Garantida Fidelidade",
                "bonuses": {
                    str(key): value
                    for key, value in DEFAULT_LOYALTY_BONUSES.items()
                },
                "updated_at": now,
            }
        },
        upsert=True,
    )

    db.settings.update_one(
        {"_id": "revision_rules"},
        {
            "$setOnInsert": {
                "rules": [
                    {
                        "revision_number": number,
                        "months_after_sale": None,
                        "km": None,
                    }
                    for number in range(1, 6)
                ],
                "updated_at": now,
            }
        },
        upsert=True,
    )

    db.settings.update_one(
        {"_id": "service_reconciliation"},
        {
            "$setOnInsert": {
                "rules": {
                    "km_tolerance": 1500,
                    "days_tolerance": 45,
                    "require_owner_match": True,
                },
                "updated_at": now,
            }
        },
        upsert=True,
    )


def ensure_bootstrap_admin(db: Database) -> tuple[bool, str]:
    settings = get_settings()

    if db.users.count_documents({}) > 0:
        return True, "Usuários já configurados."

    email = normalize_email(settings.bootstrap_email)
    password = settings.bootstrap_password

    if not email or not password:
        return False, (
            "Nenhum usuário existe. Configure auth.bootstrap_email e "
            "auth.bootstrap_password nos Secrets para criar o primeiro administrador."
        )

    now = utcnow()

    db.users.insert_one(
        {
            "_id": f"user:{email}",
            "name": (
                settings.bootstrap_name
                or "Administrador Dealer Hub"
            ),
            "email": email,
            "password_hash": hash_password(password),
            "role": "superadmin",
            "company_codes": [],
            "active": True,
            "must_change_password": True,
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }
    )
    return True, "Superadministrador inicial criado."

TRANSIENT_MONGO_CODES = {
    6, 7, 89, 91, 189, 9001, 10107, 11600, 11602, 13435, 13436,
}


def is_transient_mongo_error(exc: BaseException) -> bool:
    if isinstance(exc, (NotPrimaryError, AutoReconnect, ServerSelectionTimeoutError)):
        return True

    if isinstance(exc, OperationFailure):
        if exc.code in TRANSIENT_MONGO_CODES:
            return True
        for label in ("RetryableWriteError", "RetryableReadError", "NoWritesPerformed"):
            try:
                if exc.has_error_label(label):
                    return True
            except Exception:
                pass
    return False


def _bootstrap_database_once() -> tuple[Database, str]:
    db = get_db()
    ensure_indexes(db)
    ensure_default_settings(db)
    ok, message = ensure_bootstrap_admin(db)
    if not ok:
        raise RuntimeError(message)
    return db, message


@st.cache_resource(show_spinner=False)
def bootstrap_database() -> tuple[Database, str]:
    delays = (0.0, 0.75, 1.5, 3.0, 5.0)
    last_error: BaseException | None = None

    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        try:
            return _bootstrap_database_once()
        except Exception as exc:
            last_error = exc
            if not is_transient_mongo_error(exc):
                raise
            if attempt >= len(delays):
                raise
            try:
                get_client().admin.command("ping")
            except Exception:
                pass

    if last_error is not None:
        raise last_error
    raise RuntimeError("Falha inesperada ao inicializar o MongoDB.")


def clear_database_caches() -> None:
    try:
        bootstrap_database.clear()
    except Exception:
        pass
    try:
        get_client.clear()
    except Exception:
        pass
