"""Auditoria de historico de OS vs. vendas atuais, sem gravar revisoes.

A existencia de servico de revisao numa OS encerrada e um candidato tecnico.
So e comprovacao de revisao do cliente atual se houver vinculo pos-venda
validado; uma OS antiga nunca e atribuida retroativamente ao comprador atual.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable

STAGES = (1, 2, 3, 4, 5)


def stage_number(event: dict[str, Any]) -> int | None:
    number = (event.get("manual_revision_number") if event.get("review_override") == "confirmada"
              else event.get("revision_number"))
    try:
        n = int(number)
    except (ValueError, TypeError):
        return None
    return n if n in STAGES else None


def is_service_candidate(event: dict[str, Any]) -> bool:
    """Servico efetivo *indicado* pela OS, nao comprovacao contratual."""
    return bool(
        event.get("closed_at")
        and event.get("review_override") != "descartada"
        and event.get("confidence") == "servico"
        and event.get("evidence_source") in ("servico", "codigo")
        and stage_number(event) is not None
        and event.get("chassis")
    )


def is_current_customer_confirmed(event: dict[str, Any]) -> bool:
    """Evidencia do comprador atual; manter a mesma regra de auditoria V7."""
    from .revision_audit import verified_service_event
    return verified_service_event(event)


def year_value(date: Any) -> str:
    if isinstance(date, datetime):
        return str(date.year)
    s = str(date or "")
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else "Sem data"


def _ref(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def summarize_workshop(
    events: Iterable[dict[str, Any]],
    current_chassis: Iterable[str],
) -> dict[str, Any]:
    """Gera indicadores de OS e chassi sem transformar evidencia em revisao.

    O universo de OS e do historico completo (todas as concessionarias da
    exportacao). O universo de compradores e so o cadastro atual. Nunca
    inferir clientes/proprietarios de uma OS sem verificacao pos-venda.
    """
    fleet = {_ref(x) for x in current_chassis if _ref(x)}
    counters = Counter()
    link_counts = Counter()
    annual = Counter()
    stage_counter = Counter()
    unique = set()
    event_chassis = set()
    chassis_rows: dict[str, dict[str, Any]] = {}
    confirmed_vehicle_ids = set()
    candidate_chassis = set()
    candidate_os_keys = set()
    by_year_stage = Counter()

    for event in events:
        counters["all_events"] += 1
        chassis = _ref(event.get("chassis"))
        if chassis:
            event_chassis.add(chassis)
        link = str(event.get("link_status") or "nao_classificado")
        link_counts[link] += 1
        yr = year_value(event.get("service_date") or event.get("closed_at"))
        annual[yr] += 1
        stage = stage_number(event)
        if not is_service_candidate(event):
            if event.get("confidence") == "sem_numero":
                counters["service_without_stage"] += 1
            elif event.get("confidence") in {"observacao", "observacao_sem_numero"}:
                counters["observation_only"] += 1
            elif event.get("confidence") == "ambiguo":
                counters["ambiguous"] += 1
            continue
        # Uma linha consolidada ROF080 equivale a uma OS; protecao adicional.
        osref = _ref(event.get("service_order_id") or event.get("_id") or event.get("os_number"))
        key = (chassis, osref, stage)
        if key in unique:
            counters["duplicate_evidences"] += 1
            continue
        unique.add(key)
        candidate_chassis.add(chassis)
        candidate_os_keys.add((chassis, osref))
        stage_counter[stage] += 1
        by_year_stage[(yr, stage)] += 1
        counters["stage_service_candidates"] += 1
        if chassis in fleet:
            counters["candidate_in_current_fleet"] += 1
        else:
            counters["candidate_outside_current_fleet"] += 1
        if link == "pre_sale":
            counters["candidate_pre_sale"] += 1
        if is_current_customer_confirmed(event):
            counters["confirmed_current_customer"] += 1
            if event.get("vehicle_id"):
                confirmed_vehicle_ids.add(_ref(event["vehicle_id"]))
        entry = chassis_rows.setdefault(chassis, {
            "chassis": chassis,
            "model": event.get("model") or "",
            "in_current_fleet": chassis in fleet,
            "candidates": 0,
            "stages": set(),
            "years": set(),
            "confirmed_current": 0,
            "pre_sale": 0,
            "os_count": set(),
        })
        entry["candidates"] += 1
        entry["stages"].add(stage)
        entry["years"].add(yr)
        entry["os_count"].add(osref)
        if link == "pre_sale":
            entry["pre_sale"] += 1
        if is_current_customer_confirmed(event):
            entry["confirmed_current"] += 1

    summary = {
        "total_events": counters["all_events"],
        "fleet_chassis": len(fleet),
        "historic_chassis": len(event_chassis),
        "chassis_overlap": len(event_chassis & fleet),
        "candidate_os": len(candidate_os_keys),
        "candidate_events": counters["stage_service_candidates"],
        "candidate_chassis": len(candidate_chassis),
        "confirmed_current": counters["confirmed_current_customer"],
        "confirmed_current_vehicles": len(confirmed_vehicle_ids),
        "candidate_pre_sale": counters["candidate_pre_sale"],
        "candidate_in_current_fleet": counters["candidate_in_current_fleet"],
        "candidate_outside_current_fleet": counters["candidate_outside_current_fleet"],
        "service_without_stage": counters["service_without_stage"],
        "observation_only": counters["observation_only"],
        "ambiguous": counters["ambiguous"],
        "duplicates": counters["duplicate_evidences"],
        "by_link": dict(link_counts),
        "by_year": dict(sorted(annual.items())),
        "by_stage": {n: stage_counter[n] for n in STAGES},
        "by_year_stage": [
            {"year": yr, "stage": n, "count": count}
            for (yr, n), count in sorted(by_year_stage.items())
        ],
        "vehicles": [
            {
                **{k: v for k, v in item.items() if k not in {"stages", "years", "os_count"}},
                "stages": sorted(item["stages"]),
                "years": sorted(item["years"]),
                "orders": len(item["os_count"]),
            }
            for item in chassis_rows.values()
        ],
    }
    summary["vehicles"].sort(key=lambda x: (-len(x["stages"]), -x["candidates"], x["chassis"]))
    return summary
