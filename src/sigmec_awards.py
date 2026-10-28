"""Elegibilidade para premiacao baseada EXCLUSIVAMENTE em codigos SIGMEC.

ROF080 e usado apenas como indice de identificacao (chassi/cliente) e evidencia
auxiliar de encerramento/data da OS. Revisions, journeys e eventos nao participam
da classificacao. Nenhum registro e alterado por este modulo.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Iterable

from .revision_bi import stage_from_code

STAGES = (1, 2, 3, 4, 5)
LEVELS = {1: "Somente 1ª", 2: "1ª à 2ª", 3: "1ª à 3ª", 4: "1ª à 4ª", 5: "1ª à 5ª"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", _text(value))


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _codes_for_order(row: dict[str, Any], catalog: dict[str, str], model: str) -> tuple[list[str], int | None, str]:
    codes: set[str] = set()
    stages: set[int] = set()
    ambiguous = False
    for item in row.get("interventions") or []:
        if not isinstance(item, dict):
            continue
        code = _text(item.get("code")).upper()
        if code == "0010A14" or code not in catalog:
            continue
        from .revision_taxonomy import possible_revision_numbers
        numbers = possible_revision_numbers(catalog[code], model)
        if not any(n in STAGES for n in numbers):
            # Codigos exclusivamente da 6a revisao em diante nao entram no BI.
            continue
        codes.add(code)
        stage = stage_from_code(code, catalog, model)
        if stage is not None:
            stages.add(stage)
        else:
            ambiguous = True
    if not codes:
        return [], None, "sem_codigo_1a5"
    if ambiguous or len(stages) > 1:
        return sorted(codes), None, "etapa_ambigua"
    if not stages:
        return sorted(codes), None, "fora_1a5"
    return sorted(codes), next(iter(stages)), "etapa_identificada"


def analyze_awards(
    sigmec_orders: Iterable[dict[str, Any]],
    service_orders: dict[str, dict[str, Any]],
    catalog: dict[str, str],
) -> dict[str, Any]:
    """Classifica por chassi + proprietario da OS, nunca apenas por placa.

    Premiacoes sao candidaturas, nunca entregas automaticamente autorizadas.
    Owner sem CPF/CNPJ verificavel pode entrar no diagnostico, nao na premiacao.
    """
    seen: set[str] = set()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for row in sigmec_orders:
        key = _text(row.get("_id")) or f"{row.get('dealer_code')}:{row.get('os_normalized')}"
        if key in seen:
            continue
        seen.add(key)
        counters["os_sigmec"] += 1
        ref = _text(row.get("rof080_order_id"))
        service = service_orders.get(ref, {}) if ref else {}
        model = _text(service.get("model"))
        codes, stage, status = _codes_for_order(row, catalog, model)
        if status == "sem_codigo_1a5" or status == "fora_1a5":
            continue
        counters["os_com_codigo_revisao"] += 1
        os_number = _text(row.get("os_number"))
        date_value = _date(service.get("closed_at"))
        chassis = _text(service.get("chassis")).upper()
        document = _digits(service.get("owner_document"))
        valid_owner = len(document) in (11, 14)
        client_name = _text(service.get("owner_name"))
        plate = _text(service.get("plate"))
        case = {
            "os": os_number,
            "codigo": ", ".join(codes),
            "etapa": stage,
            "cliente": client_name,
            "documento": document,
            "chassi": chassis,
            "placa": plate,
            "modelo": model,
            "data": date_value,
            "motivo": "",
            "vinculo": bool(service),
        }
        if status != "etapa_identificada":
            case["motivo"] = "Etapa ambígua: código ou motorização"
        elif not service:
            case["motivo"] = "OS SIGMEC não localizada no ROF080"
        elif _text(service.get("source")) != "rof080":
            case["motivo"] = "Origem da OS não reconhecida"
        elif not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", chassis):
            case["motivo"] = "Sem chassi VIN de 17 caracteres válido"
        elif not date_value:
            case["motivo"] = "OS sem encerramento comprovado"
        if case["motivo"]:
            counters["pendentes"] += 1
            issues.append(case)
            continue
        counters["os_classificadas"] += 1
        # Nao misturar pessoas diferentes. Sem documento, agrupar apenas para
        # investigacao e bloquear elegibilidade automatica.
        owner_key = document if valid_owner else f"SEM_DOCUMENTO:{client_name.casefold() or os_number}"
        group_key = (chassis, owner_key)
        grp = groups.setdefault(group_key, {
            "chassi": chassis, "cliente": client_name or "Não identificado",
            "documento": document, "cliente_verificavel": valid_owner,
            "placa": plate, "modelo": model, "etapas": defaultdict(list),
        })
        grp["etapas"][stage].append(case)
        # Exibir informacao mais recente sem perder o vinculo da identidade.
        current_date = max((_date(c.get("data")) or date.min for vals in grp["etapas"].values() for c in vals), default=date.min)
        if date_value >= current_date:
            grp.update(cliente=client_name or grp["cliente"], placa=plate or grp["placa"], modelo=model or grp["modelo"])

    records: list[dict[str, Any]] = []
    bands = Counter()
    distinct_os: set[str] = set()
    for group in groups.values():
        stages = sorted(group["etapas"])
        prefix = 0
        chronology_ok = True
        last_date: date | None = None
        for step in STAGES:
            if step not in group["etapas"]:
                break
            first = min(c["data"] for c in group["etapas"][step])
            # Duas etapas no mesmo dia nao demonstram uma ordem cronologica.
            if last_date is not None and first <= last_date:
                chronology_ok = False
                break
            last_date = first
            prefix = step
        no_gap = stages == list(range(1, prefix + 1))
        if not chronology_ok:
            band = "Cronologia a conferir"
        elif not stages or not no_gap:
            band = "Fora da sequência"
        else:
            band = LEVELS[prefix]
        verified = bool(group["cliente_verificavel"] and band in LEVELS.values())
        if band in LEVELS.values() and not group["cliente_verificavel"]:
            band = "Proprietário a validar"
        records.append({
            "cliente": group["cliente"], "chassi": group["chassi"],
            "placa": group["placa"], "modelo": group["modelo"],
            "documento": group["documento"], "cliente_verificavel": group["cliente_verificavel"],
            "faixa": band, "progresso": prefix, "etapas_registradas": tuple(stages),
            "premiacao_candidata": verified,
            "etapas": {
                n: sorted(group["etapas"].get(n, []), key=lambda x: x["data"])
                for n in STAGES
            },
        })
        bands[band] += 1
        for values in group["etapas"].values():
            for c in values:
                distinct_os.add(f"{c['os']}:{c['chassi']}")
    records.sort(key=lambda r: (-r["progresso"], not r["premiacao_candidata"], r["cliente"].casefold(), r["chassi"]))
    return {
        "records": records,
        "issues": issues,
        "bands": dict(bands),
        "counters": dict(counters),
        "unique_vehicles": len({r["chassi"] for r in records}),
        "unique_clients": len({r["documento"] for r in records if r["cliente_verificavel"]}),
        "classified_os_distinct": len(distinct_os),
    }
