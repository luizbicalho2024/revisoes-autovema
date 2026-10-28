"""Diagnóstico de dados importados: relações completas, exportação sem PII/segredos.

Acesso imposto pela página superadmin. Não exportar documentos, nomes, placas,
chassis, e-mails, descrições livres ou hashes de senha em claro.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
from collections import Counter
from datetime import date, datetime
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED

COLLECTIONS = (
    "import_jobs", "customers", "vehicles", "sales", "journeys",
    "revisions", "revision_events", "service_orders", "sigmec_orders", "revision_catalog",
)

# Campos de contexto não identificadores; demais strings são pseudonimizadas.
SAFE_TEXT = {
    "source", "import_type", "status", "classification", "confidence",
    "evidence_source", "link_status", "maintenance_status", "journey_status",
    "review_override", "source_type", "source_revision", "origin", "type",
    "brand", "model", "fuel", "fuel_type", "company_code",
    "revision_number", "revision_stage", "manual_revision_number", "os_km",
    "eligible_reconciliation", "owner_match", "post_sale", "is_cancelled",
    "loyalty_cancelled", "current_revision", "loyalty_bonus_pct",
    "performed_km", "next_revision_number", "next_due_km",
}
DROP_KEYS = {
    "password_hash", "password", "mongo_uri", "uri", "secret", "token", "access_token",
    "refresh_token", "api_key", "authorization", "credential", "logo_b64", "logo_mime",
    "source_raw",
}


def _safe_key(key: str) -> bool:
    lower = key.casefold()
    return not any(block in lower for block in DROP_KEYS)


def _token(value: Any, salt: bytes) -> str:
    raw = str(value).encode("utf-8", errors="replace")
    return "REF-" + hmac.new(salt, raw, hashlib.sha256).hexdigest()[:14]


def anonymize(value: Any, salt: bytes, key: str = "") -> Any:
    if not _safe_key(key):
        return "[OMITIDO]"
    if isinstance(value, dict):
        return {str(k): anonymize(v, salt, str(k)) for k, v in value.items() if _safe_key(str(k))}
    if isinstance(value, (list, tuple)):
        return [anonymize(v, salt, key) for v in value[:100]]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    if key.casefold() in {"document", "cpf", "cnpj", "phone", "mobile", "email", "plate", "chassis",
                          "customer_id", "vehicle_id", "journey_id", "service_order_id", "os_number", "_id",
                          "owner_document", "owner_name", "name", "contact", "zipcode", "postal_code"}:
        return _token(value, salt)
    if isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    if key in SAFE_TEXT or (key.endswith("_at") or key.endswith("_date")):
        # Campos de fonte/status/classificação; textos longos vindos da OS
        # não estão entre os campos explicitamente permitidos.
        if len(text) <= 90 and not any(x in key.lower() for x in ("name", "description", "text")):
            return text
    if key in {"evidence_text", "services", "description", "notes", "observation", "type_description"}:
        return "[TEXTO LIVRE SUPRIMIDO]"
    return _token(text, salt) if text else ""


def safe_document(collection: str, doc: dict[str, Any], salt: bytes) -> dict[str, Any]:
    """Preserva códigos técnicos do catálogo; protege textos livres das OS."""
    result = anonymize(doc, salt)
    if collection == "revision_catalog":
        code = str(doc.get("_id") or "").strip()
        description = str(doc.get("description") or "").strip()
        if re.fullmatch(r"[A-Za-z0-9]{3,24}", code):
            result["codigo_revisao"] = code
        if re.search(r"REV(?:IS[AÃ]O|ISAO|\.)", description.upper()) and "@" not in description:
            result["descricao_catalogo"] = description[:160]
    elif collection == "sigmec_orders":
        # Códigos técnicos de 7 caracteres são seguros; nunca exportar
        # texto livre de atendimento ou identificadores sem pseudonimizar.
        items = doc.get("interventions") or []
        result["codigos_sigmec"] = sorted({
            str(item.get("code") or "") for item in items
            if re.fullmatch(r"[0-9]{4}[A-Z][0-9]{2}", str(item.get("code") or ""))
        })[:100]
        result["resultado_cruzamento"] = [
            {"code": str(item.get("code") or "") if re.fullmatch(r"[0-9]{4}[A-Z][0-9]{2}",str(item.get("code") or "")) else "—",
             "status": str(item.get("status") or "")[:50]}
            for item in (doc.get("revision_results") or [])[:25]
        ]
    elif collection == "service_orders":
        matches: set[str] = set()
        for label in (doc.get("services") or [])[:100]:
            matches.update(re.findall(r"\b[0-9]{4}[A-Z][0-9]{2}\b", str(label).upper()))
        if matches:
            result["codigos_tecnicos_encontrados"] = sorted(matches)
    return result


def collection_stats(db: Any) -> list[dict[str, Any]]:
    result = []
    for name in COLLECTIONS:
        coll = db[name]
        total = coll.count_documents({})
        sample = coll.find_one({}, {"_id": 0}) or {}
        result.append({"collection": name, "records": total,
                       "sample_fields": sorted(sample.keys())})
    return result


def diagnostic_summary(db: Any) -> dict[str, Any]:
    event_counts = {}
    order_counts = {}
    for name, field, target in (
        ("revision_events", "link_status", event_counts),
        ("revision_events", "classification", event_counts),
        ("revision_events", "confidence", event_counts),
        ("service_orders", "source", order_counts),
        ("service_orders", "link_status", order_counts),
    ):
        rows = list(db[name].aggregate([
            {"$group": {"_id": f"${field}", "total": {"$sum": 1}}},
            {"$sort": {"total": -1}}, {"$limit": 100},
        ]))
        target[field] = [{"value": str(r.get("_id") or "não informado"),
                          "records": int(r.get("total", 0))} for r in rows]
    counts = collection_stats(db)
    return {"collections": counts, "events": event_counts, "orders": order_counts,
            "explanation": "Dados anonimizados; REF preserva ligação entre registros no mesmo arquivo."}


def page_records(db: Any, name: str, salt: bytes, *, offset: int = 0,
                 limit: int = 50) -> list[dict[str, Any]]:
    if name not in COLLECTIONS:
        raise ValueError("Coleção não permitida")
    limit = max(1, min(100, int(limit)))
    return [safe_document(name, d, salt) for d in db[name].find({}).sort("_id", 1).skip(max(0, offset)).limit(limit)]


def build_safe_archive(db: Any, salt: bytes, *, per_collection_limit: int = 20000,
                       max_bytes: int = 24_000_000) -> bytes:
    """Exportação abrangente, paginada e limitada. Indica truncamento por coleção."""
    limit = max(1, min(100000, int(per_collection_limit)))
    summary = diagnostic_summary(db)
    report = {"collections": {}, "privacy": "Identificadores pseudonimizados por HMAC por exportação; textos livres omitidos."}
    sink = io.BytesIO()
    current_size = 0
    with ZipFile(sink, "w", ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("resumo.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        for name in COLLECTIONS:
            total = int(db[name].count_documents({}))
            count = 0
            buffer = io.StringIO()
            for doc in db[name].find({}).sort("_id", 1).limit(limit):
                line = json.dumps(safe_document(name, doc, salt), ensure_ascii=False, default=str)
                if current_size + len(line) > max_bytes:
                    break
                buffer.write(line + "\n")
                current_size += len(line) + 1
                count += 1
            z.writestr(f"colecoes/{name}.jsonl", buffer.getvalue())
            report["collections"][name] = {"total": total, "exported": count,
                                            "truncated": count < total}
        z.writestr("manifesto.json", json.dumps(report, ensure_ascii=False, indent=2))
    return sink.getvalue()
