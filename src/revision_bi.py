"""Indicadores SIGMEC por OS, separados da retenção do comprador atual.

Importante: código de revisão não é, isoladamente, comprovação de serviço
realizado por determinado cliente. Não altera jornadas nem bonificações.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .revision_taxonomy import DEFAULT_CATALOG, possible_revision_numbers, fuel_for_model

STAGES = (1, 2, 3, 4, 5)


def stage_from_code(code: str, catalog: dict[str, str], model: str | None = None) -> int | None:
    if code == "0010A14":  # serviço de entrega; não é revisão periódica
        return None
    description = catalog.get(str(code or "").strip().upper(), "")
    if not description:
        return None
    fuel = fuel_for_model(model)
    upper = description.upper()
    if fuel == "diesel" and "FLEX" in upper and "DIESEL" not in upper:
        return None
    if fuel == "flex" and "DIESEL" in upper and "FLEX" not in upper:
        return None
    stages = possible_revision_numbers(description, model)
    return stages[0] if len(stages) == 1 and stages[0] in STAGES else None


def _relevant_code(code: str, catalog: dict[str, str], model: str | None) -> bool:
    if code == "0010A14" or code not in catalog:
        return False
    # O catálogo também contém 6ª–18ª revisão. O BI não deve misturá-las
    # às cinco primeiras. Códigos mistos sem motorização ficam ambíguos.
    numbers = possible_revision_numbers(catalog[code], model)
    return any(n in STAGES for n in numbers)


def summarize_sigmec(
    rows: Iterable[dict[str, Any]],
    related_orders: dict[str, dict[str, Any]] | None = None,
    catalog: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Uma OS SIGMEC é contada uma vez em cada etapa identificada.

    O status de vínculo e a etapa são independentes. Quando não há modelo e o
    código é flex/diesel misto, permanece ambíguo. Não inventa chassi/cliente.
    """
    related_orders = related_orders or {}
    catalog = catalog or dict(DEFAULT_CATALOG)
    total = 0
    linked_all = 0
    revision_os = 0
    revision_linked = 0
    review_status = Counter()
    by_stage = Counter()
    by_code = Counter()
    ambiguous = 0
    missing_rof080 = 0
    confirmed_current = 0
    detail: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("_id") or f"{row.get('dealer_code')}:{row.get('os_normalized')}")
        if key in seen:
            continue
        seen.add(key)
        total += 1
        order_id = row.get("rof080_order_id")
        order = related_orders.get(str(order_id), {}) if order_id else {}
        linked = bool(order_id and order)
        linked_all += int(linked)
        # Sem cadastro do modelo, um código flex/diesel misto não define etapa.
        model = str(order.get("model") or "")
        interventions = row.get("interventions") or []
        results = row.get("revision_results") or []
        result_status = {str(r.get("code") or "").upper(): str(r.get("status") or "")
                         for r in results if isinstance(r, dict)}
        stages = set()
        selected_codes = set()
        ambiguous_codes = set()
        for intervention in interventions:
            if not isinstance(intervention, dict):
                continue
            code = str(intervention.get("code") or "").strip().upper()
            if not _relevant_code(code, catalog, model):
                continue
            selected_codes.add(code)
            stage = stage_from_code(code, catalog, model)
            if stage is None:
                ambiguous_codes.add(code)
            else:
                stages.add(stage)
        if not selected_codes:
            continue
        revision_os += 1
        revision_linked += int(linked)
        missing_rof080 += int(not linked)
        ambiguous += int(bool(ambiguous_codes) or len(stages) > 1)
        for code in selected_codes:
            by_code[code] += 1
        if len(stages) == 1 and not ambiguous_codes:
            for n in stages:
                by_stage[n] += 1
        else:
            # OS com etapas divergentes ou ambíguas não é atribuída a uma etapa arbitrária.
            stages = set()
        statuses = {result_status.get(c, "nao_processado") for c in selected_codes}
        if "confirmada" in statuses and len(stages) == 1 and linked:
            status = "confirmada_pos_venda"
            confirmed_current += 1
        elif not linked:
            status = "sem_rof080"
        elif "divergencia_etapa" in statuses or "multiplas_etapas_mesma_os" in statuses:
            status = "divergencia"
        elif not stages:
            status = "etapa_ambigua"
        elif "descartada_manualmente" in statuses:
            status = "descartada"
        elif "confirmacao_manual_preservada" in statuses or "confirmacao_existente_preservada" in statuses:
            status = "ja_comprovada"
        else:
            status = "pendente_validacao"
        review_status[status] += 1
        detail.append({
            "os": str(row.get("os_number") or ""),
            "concessionaria": str(row.get("dealer_code") or ""),
            "etapa": (next(iter(stages)) if len(stages) == 1 else None),
            "codigos": ", ".join(sorted(selected_codes)),
            "situacao": status,
            "vinculo_rof080": linked,
            "cliente_os": str(order.get("owner_name") or ""),
            "chassi": str(order.get("chassis") or ""),
            "placa": str(order.get("plate") or ""),
            "modelo": model,
            "data_os": order.get("closed_at") or order.get("service_date"),
            "vehicle_id": str(order.get("vehicle_id") or ""),
        })
    return {
        "total_os": total,
        "all_linked": linked_all,
        "revision_os": revision_os,
        "revision_linked": revision_linked,
        "revision_unlinked": missing_rof080,
        "ambiguous": ambiguous,
        "confirmed_current": confirmed_current,
        "by_stage": dict(by_stage),
        "by_code": dict(by_code),
        "by_status": dict(review_status),
        "details": detail,
    }


def summarize_customers(journeys: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in journeys:
        cid = str(row.get("customer_id") or "")
        key = cid or f"sem-cliente:{row.get('vehicle_id')}"
        entry = grouped.setdefault(key, {
            "Cliente": str(row.get("customer_name") or "Não identificado"),
            "Veículos": 0, "Com alguma revisão": 0,
            "Revisões comprovadas": 0, "Com 5 revisões": 0,
            "Com lacunas": 0, "Com indícios": 0,
        })
        entry["Veículos"] += 1
        completed = int(row.get("completed") or 0)
        entry["Com alguma revisão"] += int(completed > 0)
        entry["Revisões comprovadas"] += completed
        entry["Com 5 revisões"] += int(completed == 5)
        entry["Com lacunas"] += int(bool(row.get("has_gap")))
        entry["Com indícios"] += int(bool(row.get("has_pending_evidence")))
    return sorted(grouped.values(), key=lambda r: (-r["Revisões comprovadas"], -r["Com alguma revisão"], r["Cliente"]))
