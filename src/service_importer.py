from __future__ import annotations

import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from pymongo import UpdateOne
from pymongo.database import Database

from .importer import (
    clean_chassis,
    clean_code,
    clean_date,
    clean_digits,
    clean_float,
    clean_int,
    clean_plate,
    clean_text,
    file_sha256,
    mongo_safe,
)
from .maintenance import (
    get_service_reconciliation_settings,
    reconcile_vehicle_service_history,
)
from .repositories import audit


REQUIRED_SERVICE_COLUMNS = {
    "K_OS_Codigo",
    "OS_Numero",
    "Empresa_Nome",
    "DocIdentificador",
    "Veiculo_Chassi",
    "OS_KM",
    "Data_Criacao",
    "Fechado",
}


@dataclass
class ServiceImportResult:
    rows_received: int = 0
    rows_valid: int = 0
    rows_skipped: int = 0
    unique_orders: int = 0
    orders_upserted: int = 0
    orders_updated: int = 0
    matched_orders: int = 0
    unmatched_orders: int = 0
    post_sale_orders: int = 0
    owner_mismatches: int = 0
    vehicles_reconciled: int = 0
    revision_candidates: int = 0
    errors: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_received": self.rows_received,
            "rows_valid": self.rows_valid,
            "rows_skipped": self.rows_skipped,
            "unique_orders": self.unique_orders,
            "orders_upserted": self.orders_upserted,
            "orders_updated": self.orders_updated,
            "matched_orders": self.matched_orders,
            "unmatched_orders": self.unmatched_orders,
            "post_sale_orders": self.post_sale_orders,
            "owner_mismatches": self.owner_mismatches,
            "vehicles_reconciled": self.vehicles_reconciled,
            "revision_candidates": self.revision_candidates,
            "errors": self.errors or [],
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def read_service_orders(file_bytes: bytes) -> pd.DataFrame:
    workbook = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    sheet_name = "Dados" if "Dados" in workbook.sheet_names else workbook.sheet_names[0]
    df = pd.read_excel(
        workbook,
        sheet_name=sheet_name,
        dtype=object,
    )
    df.columns = [str(column).strip() for column in df.columns]
    return df


def validate_service_dataframe(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_SERVICE_COLUMNS - set(df.columns))
    if missing:
        errors.append("Colunas obrigatórias ausentes: " + ", ".join(missing))
    if df.empty:
        errors.append("A planilha não possui registros.")
    return errors


def _company_key(value: Any) -> str:
    text = clean_text(value) or "SEM_EMPRESA"
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_") or "SEM_EMPRESA"


def _order_id(company_name: Any, os_code: Any) -> str | None:
    code = clean_code(os_code)
    if not code:
        return None
    return f"os:{_company_key(company_name)}:{code}"


def _max_date(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if not current:
        return candidate
    if not candidate:
        return current
    return max(current, candidate)


def _min_date(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if not current:
        return candidate
    if not candidate:
        return current
    return min(current, candidate)


def _aggregate_orders(
    df: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[str]]:
    grouped: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for idx, series in df.iterrows():
        row = {
            str(key): mongo_safe(value)
            for key, value in series.to_dict().items()
        }

        order_id = _order_id(
            row.get("Empresa_Nome"),
            row.get("K_OS_Codigo"),
        )
        chassis = clean_chassis(row.get("Veiculo_Chassi"))

        if not order_id or not chassis:
            errors.append(
                f"Linha {idx + 2}: OS ou chassi inválido; registro ignorado."
            )
            continue

        if order_id not in grouped:
            grouped[order_id] = {
                "_id": order_id,
                "source_rows": 0,
                "row_numbers": [],
                "company_name": clean_text(row.get("Empresa_Nome")),
                "os_code": clean_code(row.get("K_OS_Codigo")),
                "os_number": clean_code(row.get("OS_Numero")),
                "type_code": clean_code(row.get("TipoOS_Codigo")),
                "type_short": clean_text(row.get("TipoOS_Sigla")),
                "type_description": clean_text(row.get("TipoOS_Descricao")),
                "classification": clean_text(row.get("TipoOS_Classificacao")),
                "consultants": set(),
                "productives": set(),
                "owner_name": clean_text(row.get("Proprietario_Veiculo")),
                "owner_document": clean_digits(row.get("DocIdentificador")),
                "owner_phone": clean_text(row.get("Telefone")),
                "owner_source_code": clean_code(row.get("Proprietario_Codigo")),
                "vehicle_source_code": clean_code(row.get("Veiculo_Codigo")),
                "plate": clean_plate(row.get("Veiculo_Placa")),
                "chassis": chassis,
                "model": clean_text(row.get("ModeloVeiculo_Descricao")),
                "os_km": clean_int(row.get("OS_KM")),
                "service_amount": 0.0,
                "product_amount": 0.0,
                "discount_amount": 0.0,
                "total_amount": 0.0,
                "purchase_request_amount": 0.0,
                "created_at_source": None,
                "released_at": None,
                "promised_at": None,
                "stopped_at": None,
                "closed_at": None,
                "prism_number": clean_text(row.get("OS_NroPrisma")),
                "scheduler_name": clean_text(row.get("K_AgendadorNome")),
            }

        item = grouped[order_id]
        item["source_rows"] += 1
        item["row_numbers"].append(idx + 2)

        consultant = clean_text(row.get("Consultor_Nome"))
        productive = clean_text(row.get("Produtivo_Nome"))
        if consultant:
            item["consultants"].add(consultant)
        if productive:
            item["productives"].add(productive)

        item["service_amount"] += clean_float(row.get("Servico")) or 0.0
        item["product_amount"] += clean_float(row.get("Produto")) or 0.0
        item["discount_amount"] += clean_float(row.get("Desconto")) or 0.0
        item["total_amount"] += clean_float(row.get("Total")) or 0.0
        item["purchase_request_amount"] += (
            clean_float(row.get("RequisicaoCompra_Valor")) or 0.0
        )

        item["created_at_source"] = _min_date(
            item["created_at_source"],
            clean_date(row.get("Data_Criacao")),
        )
        item["released_at"] = _max_date(
            item["released_at"],
            clean_date(row.get("Data_Liberacao")),
        )
        item["promised_at"] = _max_date(
            item["promised_at"],
            clean_date(row.get("OS_DataPrometida")),
        )
        item["stopped_at"] = _max_date(
            item["stopped_at"],
            clean_date(row.get("Parado")),
        )
        item["closed_at"] = _max_date(
            item["closed_at"],
            clean_date(row.get("Fechado")),
        )

    result = []
    for item in grouped.values():
        item["consultants"] = sorted(item["consultants"])
        item["productives"] = sorted(item["productives"])

        # Data_Liberacao representa melhor a saída do veículo. Em sua ausência,
        # utiliza o fechamento e, por último, a criação.
        item["service_date"] = (
            item["released_at"]
            or item["closed_at"]
            or item["created_at_source"]
        )

        for key in (
            "service_amount",
            "product_amount",
            "discount_amount",
            "total_amount",
            "purchase_request_amount",
        ):
            item[key] = round(float(item[key]), 2)

        result.append(item)

    result.sort(
        key=lambda item: item.get("service_date")
        or datetime.min.replace(tzinfo=timezone.utc)
    )
    return result, errors


def preview_service_orders(
    file_bytes: bytes,
    max_rows: int = 12,
) -> tuple[pd.DataFrame, list[str]]:
    df = read_service_orders(file_bytes)
    errors = validate_service_dataframe(df)
    if errors:
        return pd.DataFrame(), errors

    wanted = [
        "K_OS_Codigo",
        "OS_Numero",
        "Empresa_Nome",
        "Proprietario_Veiculo",
        "DocIdentificador",
        "Veiculo_Placa",
        "Veiculo_Chassi",
        "ModeloVeiculo_Descricao",
        "OS_KM",
        "TipoOS_Descricao",
        "Servico",
        "Produto",
        "Total",
        "Data_Criacao",
        "Data_Liberacao",
        "Fechado",
    ]
    columns = [column for column in wanted if column in df.columns]
    return df[columns].head(max_rows), []


def import_service_orders(
    db: Database,
    file_bytes: bytes,
    filename: str,
    user: dict[str, Any],
) -> ServiceImportResult:
    started_at = utcnow()
    digest = file_sha256(file_bytes)
    job_id = f"import:service:{digest[:16]}:{int(started_at.timestamp())}"
    result = ServiceImportResult(errors=[])

    db.import_jobs.insert_one(
        {
            "_id": job_id,
            "import_type": "service_orders",
            "filename": filename,
            "file_sha256": digest,
            "status": "processing",
            "started_at": started_at,
            "finished_at": None,
            "user_email": user.get("email"),
            "summary": {},
        }
    )

    try:
        df = read_service_orders(file_bytes)
        result.rows_received = len(df)

        validation_errors = validate_service_dataframe(df)
        if validation_errors:
            raise ValueError(" | ".join(validation_errors))

        orders, row_errors = _aggregate_orders(df)
        result.errors = row_errors[:100]
        result.rows_valid = result.rows_received - len(row_errors)
        result.rows_skipped = len(row_errors)
        result.unique_orders = len(orders)

        chassis_values = sorted(
            {order["chassis"] for order in orders if order.get("chassis")}
        )
        vehicles = list(
            db.vehicles.find(
                {"chassis": {"$in": chassis_values}},
                {
                    "_id": 1,
                    "chassis": 1,
                    "customer_id": 1,
                    "last_sale_at": 1,
                },
            )
        )
        vehicle_by_chassis = {
            vehicle.get("chassis"): vehicle
            for vehicle in vehicles
            if vehicle.get("chassis")
        }

        vehicle_ids = [vehicle["_id"] for vehicle in vehicles]
        journeys = list(
            db.journeys.find(
                {"vehicle_id": {"$in": vehicle_ids}},
                {
                    "_id": 1,
                    "vehicle_id": 1,
                    "customer_id": 1,
                    "sale_date": 1,
                },
            )
        )
        journey_by_vehicle = {
            journey["vehicle_id"]: journey for journey in journeys
        }

        customer_ids = {
            journey.get("customer_id")
            for journey in journeys
            if journey.get("customer_id")
        }
        customers = list(
            db.customers.find(
                {"_id": {"$in": list(customer_ids)}},
                {"_id": 1, "document": 1, "name": 1},
            )
        )
        customer_by_id = {
            customer["_id"]: customer for customer in customers
        }

        settings = get_service_reconciliation_settings(db)
        now = utcnow()
        operations: list[UpdateOne] = []
        affected_vehicle_ids: set[str] = set()

        for order in orders:
            vehicle = vehicle_by_chassis.get(order["chassis"])
            journey = (
                journey_by_vehicle.get(vehicle["_id"])
                if vehicle
                else None
            )
            customer = (
                customer_by_id.get(journey.get("customer_id"))
                if journey
                else None
            )

            vehicle_id = vehicle["_id"] if vehicle else None
            journey_id = journey["_id"] if journey else None
            customer_id = journey.get("customer_id") if journey else None

            owner_document = order.get("owner_document")
            customer_document = (
                clean_digits(customer.get("document"))
                if customer
                else None
            )

            if owner_document and customer_document:
                owner_match: bool | None = owner_document == customer_document
            else:
                owner_match = None

            sale_date = journey.get("sale_date") if journey else None
            service_date = order.get("service_date")

            post_sale = (
                bool(service_date and sale_date and service_date >= sale_date)
                if journey
                else None
            )

            if not vehicle:
                link_status = "unmatched_vehicle"
            elif not journey:
                link_status = "no_journey"
            elif post_sale is False:
                link_status = "pre_sale"
            elif owner_match is False:
                link_status = "owner_mismatch"
            else:
                link_status = "matched"

            eligible = (
                link_status == "matched"
                or (
                    link_status == "owner_mismatch"
                    and not settings.get("require_owner_match")
                )
            )

            order_set = {
                **order,
                "vehicle_id": vehicle_id,
                "journey_id": journey_id,
                "customer_id": customer_id,
                "current_customer_name": (
                    customer.get("name") if customer else None
                ),
                "current_customer_document": customer_document,
                "owner_match": owner_match,
                "post_sale": post_sale,
                "link_status": link_status,
                "eligible_reconciliation": eligible,
                "updated_at": now,
                "updated_by": user.get("email"),
                "last_import_job_id": job_id,
            }

            operations.append(
                UpdateOne(
                    {"_id": order["_id"]},
                    {
                        "$set": order_set,
                        "$setOnInsert": {
                            "created_at": now,
                            "created_by": user.get("email"),
                        },
                    },
                    upsert=True,
                )
            )

            if vehicle_id:
                affected_vehicle_ids.add(vehicle_id)
                result.matched_orders += 1
            else:
                result.unmatched_orders += 1

            if post_sale is True:
                result.post_sale_orders += 1
            if owner_match is False:
                result.owner_mismatches += 1

        bulk_result = (
            db.service_orders.bulk_write(operations, ordered=False)
            if operations
            else None
        )

        if bulk_result:
            result.orders_upserted = int(
                getattr(bulk_result, "upserted_count", 0)
            )
            result.orders_updated = int(
                getattr(bulk_result, "modified_count", 0)
            )

        # Atualiza os dados derivados de cada veículo já conhecido.
        for vehicle_id in affected_vehicle_ids:
            latest = db.service_orders.find_one(
                {"vehicle_id": vehicle_id},
                sort=[("service_date", -1)],
            )
            count = db.service_orders.count_documents(
                {"vehicle_id": vehicle_id}
            )

            db.vehicles.update_one(
                {"_id": vehicle_id},
                {
                    "$set": {
                        "service_order_count": count,
                        "last_service_at": (
                            latest.get("service_date") if latest else None
                        ),
                        "last_service_km": (
                            latest.get("os_km") if latest else None
                        ),
                        "updated_at": now,
                    }
                },
            )

            reconciliation = reconcile_vehicle_service_history(
                db,
                vehicle_id,
                user_email=user.get("email") or "system",
            )
            result.vehicles_reconciled += 1
            result.revision_candidates += int(
                reconciliation.get("candidates", 0)
            )

        finished_at = utcnow()
        db.import_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "success",
                    "finished_at": finished_at,
                    "summary": result.as_dict(),
                    "columns": list(df.columns),
                }
            },
        )

        audit(
            db,
            user,
            "import_success",
            "SERVICE_ORDERS",
            job_id,
            {"filename": filename, **result.as_dict()},
        )
        return result

    except Exception as exc:
        result.errors = (result.errors or []) + [str(exc)]
        db.import_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "finished_at": utcnow(),
                    "summary": result.as_dict(),
                }
            },
        )
        audit(
            db,
            user,
            "import_failed",
            "SERVICE_ORDERS",
            job_id,
            {"filename": filename, "error": str(exc)},
        )
        raise
