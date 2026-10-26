"""Leitura conservadora das cinco primeiras revisões por jornada/veículo.

Somente `revisions.status == realizada` equivale a revisão comprovada.
Uma revisão posterior confirmada sem anterior é uma *lacuna de evidência*,
não uma evasão comprovada. O módulo não grava nem altera registros.
"""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

STAGES = (1, 2, 3, 4, 5)
STAGE_LABELS = {
    "realizada": "Realizada",
    "indicio": "Indício a validar",
    "lacuna": "Lacuna na sequência",
    "externa": "Fora da rede (registrada)",
    "vencida": "Vencida sem comprovação",
    "pendente": "Pendente",
    "agendada": "Agendada",
    "cancelada": "Cancelada",
    "nao_aplicavel": "Não aplicável",
    "sem_regra": "Sem regra configurada",
    "sem_plano": "Sem plano gerado",
}
STATUS_LABELS = {
    "completo": "5 revisões realizadas",
    "evasao": "Revisão fora da rede registrada",
    "lacuna": "Lacuna entre revisões",
    "indicios": "Revisões a validar",
    "atraso": "Revisão vencida",
    "parcial": "Sequência em acompanhamento",
    "nenhuma": "Nenhuma revisão comprovada",
}
LINK_LABELS = {
    "unmatched_vehicle": "Chassi fora da base de veículos",
    "no_journey": "Sem jornada vinculada",
    "pre_sale": "OS anterior à venda",
    "owner_mismatch": "Divergência de proprietário",
    "open_order": "OS ainda sem encerramento",
    "matched": "Vínculo identificado",
}


def _id(value: Any) -> str:
    return str(value) if value is not None else ""


def _date(value: Any):
    if hasattr(value, "date"):
        return value.date()
    return value


def _event_confirmed(e: dict[str, Any]) -> bool:
    override = e.get("review_override")
    return override == "confirmada" or (
        e.get("classification") == "confirmada" and override != "descartada"
    )


def _stage_from_event(e: dict[str, Any]) -> int | None:
    number = e.get("manual_revision_number") if e.get("review_override") == "confirmada" else e.get("revision_number")
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    return n if n in STAGES else None


def _stage_from_revision(revision: dict[str, Any]) -> int | None:
    try:
        number = int(revision.get("revision_number"))
    except (TypeError, ValueError):
        return None
    return number if number in STAGES else None


def summarize_journeys(
    journeys: Iterable[dict[str, Any]],
    vehicles: dict[str, dict[str, Any]],
    customers: dict[str, dict[str, Any]],
    revisions: Iterable[dict[str, Any]],
    events: Iterable[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Retorna uma linha por jornada, matriz das 5 etapas e indicadores."""
    now = now or datetime.now(timezone.utc)
    today = _date(now)
    plans: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for revision in revisions:
        vid = _id(revision.get("vehicle_id"))
        number = _stage_from_revision(revision)
        if vid and number:
            plans[vid][number] = revision

    evidence: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    event_by_vehicle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        vid = _id(e.get("vehicle_id"))
        if not vid or e.get("review_override") == "descartada":
            continue
        event_by_vehicle[vid].append(e)
        number = _stage_from_event(e)
        if number is not None:
            evidence[vid][number].append(e)

    rows: list[dict[str, Any]] = []
    stage_counts = {n: Counter() for n in STAGES}
    stage_due_cohort: Counter[int] = Counter()
    situations: Counter[str] = Counter()
    for journey in journeys:
        vid = _id(journey.get("vehicle_id"))
        if not vid:
            continue
        vehicle = vehicles.get(vid, {})
        customer = customers.get(_id(journey.get("customer_id")), {})
        planned = plans.get(vid, {})
        completed = {
            n for n in STAGES if planned.get(n, {}).get("status") == "realizada"
        }
        confirmed_5 = len(completed) == 5
        gaps = {
            n for n in STAGES
            if n not in completed and any(later > n for later in completed)
        }
        stages: dict[int, dict[str, Any]] = {}
        for n in STAGES:
            rev = planned.get(n, {})
            raw = str(rev.get("status") or "")
            candidate = evidence.get(vid, {}).get(n, [])
            open_evidence = [e for e in candidate if not _event_confirmed(e)]
            due = _date(rev.get("due_date"))
            if raw == "realizada":
                state = "realizada"
            elif raw == "externa_perdida":
                state = "externa"
            elif raw == "cancelada":
                state = "cancelada"
            elif raw == "nao_aplicavel":
                state = "nao_aplicavel"
            elif n in gaps:
                state = "lacuna"
            elif open_evidence:
                state = "indicio"
            elif due is not None and due < today:
                state = "vencida"
            elif raw == "agendada":
                state = "agendada"
            elif raw == "nao_parametrizada":
                state = "sem_regra"
            elif raw == "pendente":
                state = "pendente"
            elif not rev:
                state = "sem_plano"
            else:
                state = "pendente"
            stage_counts[n][state] += 1
            # Elegibilidade por tempo: nunca considerar automaticamente uma
            # revisão futura como retida ou perdida. Etapas comprovadas ou
            # lacunas de sequência entram no grupo auditável mesmo sem data.
            if (due is not None and due <= today) or state in {"realizada", "externa", "lacuna"}:
                stage_due_cohort[n] += 1
            stages[n] = {
                "state": state,
                "status": STAGE_LABELS[state],
                "due_date": due,
                "performed_at": _date(rev.get("performed_at")),
                "performed_km": rev.get("performed_km"),
                "source": rev.get("source"),
                "service_order_id": rev.get("service_order_id"),
                "candidate_service_order_id": rev.get("candidate_service_order_id"),
                "events": candidate,
                "revision": rev,
            }
        lost = any(stage["state"] == "externa" for stage in stages.values())
        has_gaps = bool(gaps)
        has_indications = any(stage["state"] == "indicio" for stage in stages.values())
        overdue = any(stage["state"] == "vencida" for stage in stages.values())
        if confirmed_5:
            situation = "completo"
        elif lost:
            situation = "evasao"
        elif has_gaps:
            situation = "lacuna"
        elif has_indications:
            situation = "indicios"
        elif overdue:
            situation = "atraso"
        elif completed:
            situation = "parcial"
        else:
            situation = "nenhuma"
        situations[situation] += 1
        rows.append({
            "vehicle_id": vid,
            "customer_id": _id(journey.get("customer_id")),
            "customer_name": customer.get("name") or "Cliente não identificado",
            "plate": vehicle.get("plate") or "Sem placa",
            "chassis": vehicle.get("chassis") or "",
            "model": vehicle.get("model") or "",
            "company": journey.get("company_name") or "",
            "sale_date": _date(journey.get("sale_date")),
            "journey_status": journey.get("status"),
            "completed": len(completed),
            "has_gap": has_gaps,
            "gap_stages": sorted(gaps),
            "has_external": lost,
            "has_pending_evidence": has_indications,
            "has_overdue": overdue,
            "situation_key": situation,
            "situation": STATUS_LABELS[situation],
            "stages": stages,
            "events": event_by_vehicle.get(vid, []),
        })

    return {
        "rows": rows, "by_stage": stage_counts, "by_situation": situations,
        "stage_due_cohort": dict(stage_due_cohort), "total": len(rows),
    }


def evidence_quality(events: Iterable[dict[str, Any]], valid_vehicle_ids: set[str] | None = None) -> dict[str, Any]:
    """Diagnóstico de eventos ROF080 sem misturar OS e veículos em denominadores."""
    counter: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    valid_ids = valid_vehicle_ids or set()
    for event in events:
        counter["all_events"] += 1
        vid = _id(event.get("vehicle_id"))
        if not vid:
            counter["unlinked_vehicle"] += 1
        elif vid not in valid_ids:
            counter["outside_selected_journeys"] += 1
        else:
            counter["linked_selected"] += 1
            if _stage_from_event(event) is not None:
                counter["first_five_identified"] += 1
            if _event_confirmed(event):
                counter["confirmed_events"] += 1
            elif event.get("review_override") != "descartada":
                counter["linked_for_review"] += 1
        if event.get("review_override") == "descartada":
            counter["discarded"] += 1
        if event.get("confidence") in ("observacao", "observacao_sem_numero"):
            counter["observation_only"] += 1
        reasons[LINK_LABELS.get(event.get("link_status"), "Sem vínculo definido")] += 1
    return {"totals": dict(counter), "link_reasons": dict(reasons)}


def table_rows(rows: Iterable[dict[str, Any]], *, names: bool = True) -> list[dict[str, Any]]:
    result = []
    for item in rows:
        info = {
            "Situação": item["situation"],
            "Revisões confirmadas": item["completed"],
            "Lacunas": ", ".join(f"{n}ª" for n in item["gap_stages"]) or "—",
            "Cliente": item["customer_name"] if names else "Restrito",
            "Placa": item["plate"] if names else "Restrito",
            "Modelo": item["model"] if names else "Restrito",
            "Chassi": item["chassis"] if names else "Restrito",
        }
        for n in STAGES:
            info[f"{n}ª revisão"] = item["stages"][n]["status"]
        result.append(info)
    return result


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), delimiter=";")
    writer.writeheader()
    for row in rows:
        safe: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, str):
                # Evita injeção de fórmulas em planilhas abertas no Excel.
                trimmed = value.lstrip()
                if trimmed.startswith(("=", "+", "-", "@")):
                    value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return ("\ufeff" + output.getvalue()).encode("utf-8")
