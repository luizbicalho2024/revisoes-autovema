"""Leitor de relatórios SIGMEC .001 (registros de largura fixa).

A fonte fornecida utiliza #A, #B, #C, #D, #E e #F, em Windows-1252.
Não presume que a data do registro #C seja a data de encerramento da OS
nem que placa/modelo substituam chassi na conciliação.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime
from typing import Any

CATALOG_PREFIX = "0010"
OS_RE = re.compile(r"^\d{1,12}$")
CODE_RE = re.compile(r"^[A-Z0-9]{7}$")


def normalize_os(value: Any) -> str:
    text = str(value or "").strip()
    if not OS_RE.fullmatch(text):
        return ""
    return text.lstrip("0") or "0"


def _date_hint(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except (ValueError, TypeError):
        return None


def parse_sigmec(data: bytes, filename: str = "arquivo.001") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(data) > 35_000_000:
        raise ValueError("Arquivo acima do limite de 35 MB por envio.")
    if not data.lstrip().startswith(b"#A"):
        raise ValueError("Formato SIGMEC não identificado: cabeçalho #A ausente.")
    try:
        content = data.decode("cp1252")
    except UnicodeError as exc:
        raise ValueError("O SIGMEC precisa estar codificado em Windows-1252.") from exc

    counters = Counter()
    orders: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    seen_keys: set[tuple[str, str]] = set()

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        if not current["interventions"]:
            counters["orders_without_intervention"] += 1
        key = (current["dealer_code"], current["os_normalized"])
        if key in seen_keys:
            counters["repeated_orders_in_file"] += 1
            # Mesmo relatório: manter a última versão somente se houver
            # intervenção adicional, mas não duplicar OS.
            existing = next(row for row in orders if (row["dealer_code"], row["os_normalized"]) == key)
            for intervention in current["interventions"]:
                if intervention not in existing["interventions"]:
                    existing["interventions"].append(intervention)
        else:
            orders.append(current)
            seen_keys.add(key)
        current = None

    for raw in content.splitlines():
        counters["lines_received"] += 1
        if len(raw) < 2:
            counters["invalid_lines"] += 1
            continue
        kind = raw[:2]
        if kind == "#C":
            flush()
            if len(raw) != 1324:
                counters["invalid_c_lines"] += 1
                continue
            os_number = raw[2:10]
            dealer = raw[10:17]
            normalized = normalize_os(os_number)
            if not normalized or not dealer.isdigit():
                counters["invalid_identifiers"] += 1
                continue
            current = {
                "dealer_code": dealer,
                "os_number": os_number,
                "os_normalized": normalized,
                "report_date_hint": _date_hint(raw[50:58]),
                "vehicle_date_hint": _date_hint(raw[114:122]),
                "last_date_hint": _date_hint(raw[122:130]),
                # Apenas referência para conferência. O campo não é VIN.
                "plate_hint_raw": raw[106:114].strip(),
                "interventions": [],
            }
            counters["c_records"] += 1
        elif kind == "#E":
            if len(raw) != 292:
                counters["invalid_e_lines"] += 1
                continue
            if current is None or current["os_number"] != raw[2:10] or current["dealer_code"] != raw[10:17]:
                counters["orphan_e_lines"] += 1
                continue
            code = raw[97:104].strip().upper()
            if not CODE_RE.fullmatch(code):
                counters["invalid_codes"] += 1
                continue
            label = raw[105:145].strip()
            description = raw[26:97].strip()
            item = {"code": code, "label": label[:100], "description": description[:100]}
            if item not in current["interventions"]:
                current["interventions"].append(item)
            counters["e_records"] += 1
        elif kind in {"#A", "#B", "#D", "#F"}:
            pass
        else:
            counters["unknown_lines"] += 1
    flush()
    if not orders:
        raise ValueError("Nenhuma OS SIGMEC foi identificada. Verifique o arquivo .001.")
    summary = {
        **dict(counters),
        "orders": len(orders),
        "interventions": sum(len(o["interventions"]) for o in orders),
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "filename": filename,
    }
    return orders, summary


def catalog_candidates(orders: list[dict[str, Any]], catalog: dict[str, str]) -> dict[str, Any]:
    code_counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    for order in orders:
        for intervention in order["interventions"]:
            code = intervention["code"]
            if code in catalog and code != "0010A14":
                code_counts[code] += 1
            elif code not in catalog:
                label = (intervention.get("label") or "") + " " + (intervention.get("description") or "")
                normalized = "".join(c for c in label.upper() if c.isalpha() or c.isspace())
                if ("REVISAO" in normalized or "REV" in normalized) and "ENTREGA" not in normalized:
                    unmapped[code] += 1
    return {
        "revision_codes": sum(code_counts.values()),
        "by_code": dict(sorted(code_counts.items())),
        "unmapped_revision_items": sum(unmapped.values()),
        "unmapped_revision_codes": dict(sorted(unmapped.items())),
    }
