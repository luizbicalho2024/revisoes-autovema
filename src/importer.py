from __future__ import annotations

import hashlib
import io
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from pymongo import UpdateOne
from pymongo.database import Database

from .repositories import audit


REQUIRED_COLUMNS = {
    "NotaFiscal_EmpresaCod",
    "NotaFiscal_EmpresaNom",
    "NotaFiscal_Codigo",
    "NotaFiscal_PessoaCod",
    "NotaFiscal_PessoaNom",
    "NotaFiscal_DataEmissao",
    "Veiculo_Codigo",
    "Veiculo_Chassi",
}

IDENTITY_COLUMNS = {
    "NotaFiscal_Pessoa_DocIdentificador",
    "NotaFiscal_PessoaCod",
    "Veiculo_Chassi",
    "Veiculo_Codigo",
    "NotaFiscal_Codigo",
}


@dataclass
class ImportResult:
    rows_received: int = 0
    rows_valid: int = 0
    rows_skipped: int = 0
    customers_upserted: int = 0
    customers_updated: int = 0
    vehicles_upserted: int = 0
    vehicles_updated: int = 0
    sales_upserted: int = 0
    sales_updated: int = 0
    journeys_upserted: int = 0
    errors: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_received": self.rows_received,
            "rows_valid": self.rows_valid,
            "rows_skipped": self.rows_skipped,
            "customers_upserted": self.customers_upserted,
            "customers_updated": self.customers_updated,
            "vehicles_upserted": self.vehicles_upserted,
            "vehicles_updated": self.vehicles_updated,
            "sales_upserted": self.sales_upserted,
            "sales_updated": self.sales_updated,
            "journeys_upserted": self.journeys_upserted,
            "errors": self.errors or [],
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_null(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def clean_text(value: Any) -> str | None:
    if _is_null(value):
        return None
    text = str(value).strip()
    return text or None


def clean_digits(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return digits or None


def clean_code(value: Any) -> str | None:
    if _is_null(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def clean_int(value: Any) -> int | None:
    if _is_null(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def clean_float(value: Any) -> float | None:
    if _is_null(value):
        return None
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def clean_chassis(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    result = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    return result or None


def clean_plate(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.upper().split("-")[0]
    result = re.sub(r"[^A-Z0-9]", "", text)
    return result or None


def clean_date(value: Any) -> datetime | None:
    if _is_null(value):
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        # Datas seriais do Excel usam 1899-12-30 como origem prática.
        try:
            return (datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=float(value)))
        except Exception:
            return None
    try:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            return None
        dt = parsed.to_pydatetime()
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def mongo_safe(value: Any) -> Any:
    if _is_null(value):
        return None
    if isinstance(value, pd.Timestamp):
        return clean_date(value)
    if isinstance(value, datetime):
        return clean_date(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    return str(value)


def file_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def read_rel_veiculos(file_bytes: bytes) -> pd.DataFrame:
    bio = io.BytesIO(file_bytes)
    workbook = pd.ExcelFile(bio, engine="openpyxl")
    sheet_name = "Dados" if "Dados" in workbook.sheet_names else workbook.sheet_names[0]
    df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def validate_rel_dataframe(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        errors.append("Colunas obrigatórias ausentes: " + ", ".join(missing))
    if not any(col in df.columns for col in IDENTITY_COLUMNS):
        errors.append("A planilha não contém colunas suficientes para identificar cliente, veículo e venda.")
    if df.empty:
        errors.append("A planilha não possui registros.")
    return errors


def _customer_id(row: dict[str, Any], company_code: int | None) -> str | None:
    document = clean_digits(row.get("NotaFiscal_Pessoa_DocIdentificador"))
    if document:
        return f"doc:{document}"
    person_code = clean_code(row.get("NotaFiscal_PessoaCod"))
    if person_code:
        return f"person:{company_code or 0}:{person_code}"
    return None


def _vehicle_id(row: dict[str, Any], company_code: int | None) -> str | None:
    chassis = clean_chassis(row.get("Veiculo_Chassi"))
    if chassis:
        return f"chassis:{chassis}"
    vehicle_code = clean_code(row.get("Veiculo_Codigo"))
    if vehicle_code:
        return f"vehicle:{company_code or 0}:{vehicle_code}"
    return None


def _sale_id(row: dict[str, Any], company_code: int | None) -> str | None:
    invoice_code = clean_code(row.get("NotaFiscal_Codigo"))
    if invoice_code:
        return f"nf:{company_code or 0}:{invoice_code}"
    invoice_number = clean_code(row.get("NotaFiscal_Numero"))
    chassis = clean_chassis(row.get("Veiculo_Chassi"))
    if invoice_number and chassis:
        return f"nfnum:{company_code or 0}:{invoice_number}:{chassis}"
    return None


def _prepare_records(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, series in df.iterrows():
        row = {str(k): mongo_safe(v) for k, v in series.to_dict().items()}
        company_code = clean_int(row.get("NotaFiscal_EmpresaCod"))
        customer_id = _customer_id(row, company_code)
        vehicle_id = _vehicle_id(row, company_code)
        sale_id = _sale_id(row, company_code)
        sale_date = clean_date(row.get("NotaFiscal_DataEmissao"))

        if not customer_id or not vehicle_id or not sale_id:
            errors.append(
                f"Linha {idx + 2}: não foi possível formar chave estável de cliente, veículo ou venda."
            )
            continue

        records.append(
            {
                "row_number": idx + 2,
                "row": row,
                "company_code": company_code,
                "company_name": clean_text(row.get("NotaFiscal_EmpresaNom")),
                "customer_id": customer_id,
                "vehicle_id": vehicle_id,
                "sale_id": sale_id,
                "sale_date": sale_date,
            }
        )

    # Do mais antigo para o mais recente: o registro mais novo prevalece nos campos atuais.
    records.sort(key=lambda x: x.get("sale_date") or datetime.min.replace(tzinfo=timezone.utc))
    return records, errors


def _bulk_count(result: Any) -> tuple[int, int]:
    if result is None:
        return 0, 0
    return int(getattr(result, "upserted_count", 0)), int(getattr(result, "modified_count", 0))


def import_rel_veiculos(
    db: Database,
    file_bytes: bytes,
    filename: str,
    user: dict[str, Any],
) -> ImportResult:
    started_at = utcnow()
    digest = file_sha256(file_bytes)
    job_id = f"import:{digest[:16]}:{int(started_at.timestamp())}"
    result = ImportResult(errors=[])

    db.import_jobs.insert_one(
        {
            "_id": job_id,
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
        df = read_rel_veiculos(file_bytes)
        result.rows_received = len(df)
        validation_errors = validate_rel_dataframe(df)
        if validation_errors:
            raise ValueError(" | ".join(validation_errors))

        records, row_errors = _prepare_records(df)
        result.errors = row_errors[:100]
        result.rows_valid = len(records)
        result.rows_skipped = result.rows_received - result.rows_valid

        now = utcnow()
        customer_ops: dict[str, UpdateOne] = {}
        vehicle_ops: dict[str, UpdateOne] = {}
        sale_ops: dict[str, UpdateOne] = {}
        journey_ops: dict[str, UpdateOne] = {}
        customer_company_codes: dict[str, set[int]] = defaultdict(set)
        customer_company_names: dict[str, set[str]] = defaultdict(set)
        vehicle_company_codes: dict[str, set[int]] = defaultdict(set)
        vehicle_company_names: dict[str, set[str]] = defaultdict(set)

        for item in records:
            row = item["row"]
            company_code = item["company_code"]
            company_name = item["company_name"]
            customer_id = item["customer_id"]
            vehicle_id = item["vehicle_id"]
            sale_id = item["sale_id"]
            sale_date = item["sale_date"]

            document = clean_digits(row.get("NotaFiscal_Pessoa_DocIdentificador"))
            if company_code is not None:
                customer_company_codes[customer_id].add(company_code)
                vehicle_company_codes[vehicle_id].add(company_code)
            if company_name:
                customer_company_names[customer_id].add(company_name)
                vehicle_company_names[vehicle_id].add(company_name)

            customer_values = {
                "name": clean_text(row.get("NotaFiscal_PessoaNom")),
                "document": document,
                "person_type": clean_text(row.get("NotaFiscal_PessoaTipo")),
                "phone": clean_text(row.get("NotaFiscal_PessoaFone")),
                "email": (clean_text(row.get("NotaFiscal_PessoaEmail")) or "").lower() or None,
                "city": clean_text(row.get("NotaFiscal_Municipio_Nome")),
                "state": clean_text(row.get("NotaFiscal_Estado_Codigo")),
                "source_person_code": clean_code(row.get("NotaFiscal_PessoaCod")),
            }
            customer_set = {k: v for k, v in customer_values.items() if v is not None}
            customer_set.update({"updated_at": now, "updated_by": user.get("email")})
            customer_update: dict[str, Any] = {
                "$set": customer_set,
                "$setOnInsert": {"created_at": now, "created_by": user.get("email")},
            }
            add_to_set: dict[str, Any] = {}
            if customer_company_codes[customer_id]:
                add_to_set["company_codes"] = {"$each": sorted(customer_company_codes[customer_id])}
            if customer_company_names[customer_id]:
                add_to_set["company_names"] = {"$each": sorted(customer_company_names[customer_id])}
            if add_to_set:
                customer_update["$addToSet"] = add_to_set
            if sale_date:
                customer_update["$max"] = {"last_purchase_at": sale_date}
            customer_ops[customer_id] = UpdateOne({"_id": customer_id}, customer_update, upsert=True)

            chassis = clean_chassis(row.get("Veiculo_Chassi"))
            vehicle_values = {
                "customer_id": customer_id,
                "source_vehicle_code": clean_code(row.get("Veiculo_Codigo")),
                "chassis": chassis,
                "plate": clean_plate(row.get("Veiculo_PlacaUF")),
                "renavam": clean_digits(row.get("Veiculo_NroRenavam")),
                "brand": clean_text(row.get("VeiculoMarca_Descricao")),
                "model": clean_text(row.get("VeiculoModeloVeiculo_Descricao")),
                "family": clean_text(row.get("VeiculoFamiliaVeiculo_Descricao")),
                "model_year": clean_int(row.get("VeiculoAno_Modelo")),
                "manufacture_year": clean_int(row.get("VeiculoAno_Fabricacao")),
                "color": clean_text(row.get("VeiculoCor_Descricao")),
                "fuel": clean_text(row.get("VeiculoCombustivel_Descricao")),
                "km_at_sale": clean_float(row.get("Veiculo_Km")),
                "current_company_code": company_code,
                "current_company_name": company_name,
                "last_sale_id": sale_id,
                "last_sale_at": sale_date,
            }
            vehicle_set = {k: v for k, v in vehicle_values.items() if v is not None}
            vehicle_set.update({"updated_at": now, "updated_by": user.get("email")})
            vehicle_update: dict[str, Any] = {
                "$set": vehicle_set,
                "$setOnInsert": {"created_at": now, "created_by": user.get("email")},
            }
            vehicle_add_to_set: dict[str, Any] = {}
            if vehicle_company_codes[vehicle_id]:
                vehicle_add_to_set["company_codes"] = {"$each": sorted(vehicle_company_codes[vehicle_id])}
            if vehicle_company_names[vehicle_id]:
                vehicle_add_to_set["company_names"] = {"$each": sorted(vehicle_company_names[vehicle_id])}
            if vehicle_add_to_set:
                vehicle_update["$addToSet"] = vehicle_add_to_set
            vehicle_ops[vehicle_id] = UpdateOne({"_id": vehicle_id}, vehicle_update, upsert=True)

            status = (clean_text(row.get("NotaFiscal_Status")) or "").upper()
            raw = {k: mongo_safe(v) for k, v in row.items()}
            sale_set = {
                "company_code": company_code,
                "company_name": company_name,
                "invoice_code": clean_code(row.get("NotaFiscal_Codigo")),
                "invoice_number": clean_code(row.get("NotaFiscal_Numero")),
                "invoice_series": clean_text(row.get("NotaFiscal_Serie")),
                "sale_date": sale_date,
                "cancel_date": clean_date(row.get("NotaFiscal_DataCancelamento")),
                "invoice_status": status,
                "is_cancelled": bool(clean_date(row.get("NotaFiscal_DataCancelamento"))) or status in {"CAN", "CANCELADO"},
                "customer_id": customer_id,
                "vehicle_id": vehicle_id,
                "seller_code": clean_code(row.get("NotaFiscal_UsuCodVendedor")),
                "seller_name": clean_text(row.get("NotaFiscal_UsuNomVendedor")),
                "seller_document": clean_digits(row.get("NotaFiscal_UsuCPFVendedor")) or clean_digits(row.get("CPFVendedor")),
                "stock_type": clean_text(row.get("NotaFiscal_EstoqueTipo")),
                "billing_type": clean_text(row.get("TipoFaturamento")),
                "sale_value": clean_float(row.get("Valor_Venda")),
                "present_value": clean_float(row.get("Valor_Presente")),
                "public_value": clean_float(row.get("Valor_Publico")),
                "gross_profit": clean_float(row.get("Valor_LucroBruto")),
                "management_margin": clean_float(row.get("Valor_MargemGerencial")),
                "management_margin_pct": clean_float(row.get("Valor_PercentualMargemGerencial")),
                "contact_channel": clean_text(row.get("Atendimento_MeioContato")),
                "source_raw": raw,
                "updated_at": now,
                "updated_by": user.get("email"),
                "last_import_job_id": job_id,
            }
            sale_ops[sale_id] = UpdateOne(
                {"_id": sale_id},
                {"$set": sale_set, "$setOnInsert": {"created_at": now, "created_by": user.get("email")}},
                upsert=True,
            )

            if not sale_set["is_cancelled"]:
                journey_ops[vehicle_id] = UpdateOne(
                    {"_id": f"journey:{vehicle_id}"},
                    {
                        "$set": {
                            "vehicle_id": vehicle_id,
                            "customer_id": customer_id,
                            "sale_id": sale_id,
                            "company_code": company_code,
                            "company_name": company_name,
                            "sale_date": sale_date,
                            "status": "ativa",
                            "updated_at": now,
                        },
                        "$setOnInsert": {
                            "created_at": now,
                            "current_revision": 0,
                            "loyalty_cancelled": False,
                            "loyalty_cancel_reason": None,
                        },
                    },
                    upsert=True,
                )

        customer_res = db.customers.bulk_write(list(customer_ops.values()), ordered=False) if customer_ops else None
        vehicle_res = db.vehicles.bulk_write(list(vehicle_ops.values()), ordered=False) if vehicle_ops else None
        sale_res = db.sales.bulk_write(list(sale_ops.values()), ordered=False) if sale_ops else None
        journey_res = db.journeys.bulk_write(list(journey_ops.values()), ordered=False) if journey_ops else None

        result.customers_upserted, result.customers_updated = _bulk_count(customer_res)
        result.vehicles_upserted, result.vehicles_updated = _bulk_count(vehicle_res)
        result.sales_upserted, result.sales_updated = _bulk_count(sale_res)
        result.journeys_upserted, _ = _bulk_count(journey_res)

        # Recalcula contadores derivados sem duplicar registros.
        affected_customers = list(customer_ops.keys())
        for cid in affected_customers:
            sales_count = db.sales.count_documents({"customer_id": cid, "is_cancelled": False})
            vehicles_count = len(db.sales.distinct("vehicle_id", {"customer_id": cid, "is_cancelled": False}))
            db.customers.update_one(
                {"_id": cid},
                {"$set": {"sales_count": sales_count, "vehicles_count": vehicles_count, "updated_at": now}},
            )

        finished = utcnow()
        db.import_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "success",
                    "finished_at": finished,
                    "summary": result.as_dict(),
                    "columns": list(df.columns),
                }
            },
        )
        audit(db, user, "import_success", "REL_VEICULOS", job_id, {"filename": filename, **result.as_dict()})
        return result

    except Exception as exc:
        finished = utcnow()
        result.errors = (result.errors or []) + [str(exc)]
        db.import_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "finished_at": finished, "summary": result.as_dict(), "error": str(exc)}},
        )
        audit(db, user, "import_failed", "REL_VEICULOS", job_id, {"filename": filename, "error": str(exc)})
        raise


def preview_rel(file_bytes: bytes, max_rows: int = 10) -> tuple[pd.DataFrame, list[str]]:
    df = read_rel_veiculos(file_bytes)
    errors = validate_rel_dataframe(df)
    preferred = [
        "NotaFiscal_EmpresaNom",
        "NotaFiscal_DataEmissao",
        "NotaFiscal_PessoaNom",
        "NotaFiscal_Pessoa_DocIdentificador",
        "Veiculo_Chassi",
        "Veiculo_PlacaUF",
        "VeiculoMarca_Descricao",
        "VeiculoModeloVeiculo_Descricao",
        "Valor_Venda",
        "NotaFiscal_UsuNomVendedor",
    ]
    cols = [c for c in preferred if c in df.columns]
    return df[cols].head(max_rows).copy(), errors
