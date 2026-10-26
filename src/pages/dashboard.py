"""Visão Geral centrada exclusivamente nas cinco revisões da jornada.

Leitura somente; usa os status já registrados em revisions, sem inferir que
uma OS ou menção textual representa revisão concluída.
"""
from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..repositories import scoped_filter
from ..revision_audit import (
    STAGES,
    STAGE_LABELS,
    STATUS_LABELS,
    csv_bytes,
    evidence_quality,
    summarize_journeys,
    table_rows,
)
from ..security import can
from ..ui import page_header


def _chunks(seq: list[Any], size: int = 500):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _format_date(value: Any) -> str:
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else "—"


def _number(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _rate(value: int, total: int) -> str:
    return f"{(100.0 * value / total) if total else 0:.1f}%".replace(".", ",")


def _load_audit(db: Database, user: dict[str, Any], active_only: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    query = dict(scoped_filter(user))
    if active_only:
        query["status"] = "ativa"
    journeys = list(db.journeys.find(query, {
        "vehicle_id": 1, "customer_id": 1, "company_name": 1,
        "sale_date": 1, "status": 1, "company_code": 1,
    }))
    vehicle_ids = list({j["vehicle_id"] for j in journeys if j.get("vehicle_id") is not None})
    customer_ids = list({j["customer_id"] for j in journeys if j.get("customer_id") is not None})
    vehicle_map: dict[str, dict[str, Any]] = {}
    customer_map: dict[str, dict[str, Any]] = {}
    revisions: list[dict[str, Any]] = []
    selected_events: list[dict[str, Any]] = []
    for batch in _chunks(vehicle_ids):
        lookup = {"$in": batch}
        for v in db.vehicles.find({"_id": lookup}, {"plate": 1, "chassis": 1, "model": 1}):
            vehicle_map[str(v["_id"])] = v
        revisions.extend(db.revisions.find({"vehicle_id": lookup, "revision_number": {"$in": list(STAGES)}}, {
            "vehicle_id": 1, "revision_number": 1, "status": 1, "due_date": 1,
            "performed_at": 1, "performed_km": 1, "source": 1,
            "service_order_id": 1, "candidate_service_order_id": 1,
        }))
        selected_events.extend(db.revision_events.find({"vehicle_id": lookup}, {
            "vehicle_id": 1, "review_override": 1, "classification": 1,
            "revision_number": 1, "manual_revision_number": 1,
            "os_number": 1, "service_date": 1, "confidence": 1,
            "evidence_text": 1, "link_status": 1, "closed_at": 1,
            "owner_match": 1, "post_sale": 1,
        }))
    for batch in _chunks(customer_ids):
        for c in db.customers.find({"_id": {"$in": batch}}, {"name": 1}):
            customer_map[str(c["_id"])] = c
    overview = summarize_journeys(
        journeys, vehicle_map, customer_map, revisions, selected_events,
        now=datetime.now(timezone.utc),
    )
    return overview, {"vehicle_ids": vehicle_ids, "selected_events": selected_events}


def _read_quality(db: Database, user: dict[str, Any], valid_ids: set[str]) -> dict[str, Any]:
    # A contagem de eventos utiliza a mesma regra de escopo dos demais módulos.
    events = db.revision_events.find(scoped_filter(user), {
        "vehicle_id": 1, "revision_number": 1,
        "manual_revision_number": 1, "classification": 1,
        "review_override": 1, "link_status": 1, "confidence": 1,
    })
    return evidence_quality(events, valid_vehicle_ids=valid_ids)


def _stage_cards(data: dict[str, Any]) -> None:
    columns = st.columns(5, gap="small")
    for n, col in zip(STAGES, columns):
        count = data["by_stage"][n]
        confirmed = count.get("realizada", 0)
        eligible = int(data.get("stage_due_cohort", {}).get(n, 0))
        pct = f"{_rate(confirmed, eligible)} dos elegíveis" if eligible else "Sem coorte vencida"
        with col:
            st.markdown(
                '<div class="dh-five-stage">'
                f'<div class="dh-five-step">{n}ª REVISÃO</div>'
                f'<div class="dh-five-number">{_number(confirmed)}</div>'
                f'<div class="dh-five-sub">{pct} · {eligible} elegíveis</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"{_number(count.get('indicio', 0))} indício(s) · "
                f"{_number(count.get('vencida', 0))} vencida(s) · "
                f"{_number(count.get('lacuna', 0))} lacuna(s)"
            )


def _detail(db: Database, item: dict[str, Any]) -> None:
    st.markdown("#### Histórico da jornada selecionada")
    st.caption(
        "Os dados abaixo são do veículo selecionado. A fonte é o plano de revisões e "
        "as OS vinculadas ao seu chassi; a simples menção em uma observação não confirma execução."
    )
    st.write(
        f"**Cliente:** {item['customer_name']}  |  **Veículo:** {item['model'] or '—'}  "
        f"|  **Placa:** {item['plate']}  |  **Chassi:** {item['chassis'] or '—'}"
    )
    st.caption(
        f"Venda: {_format_date(item['sale_date'])} · "
        f"Concessionária: {item['company'] or '—'} · "
        f"Situação: {item['situation']}"
    )
    order_ids = list({
        item["stages"][n][field]
        for n in STAGES
        for field in ("service_order_id", "candidate_service_order_id")
        if item["stages"][n].get(field)
    })
    order_map = {}
    if order_ids:
        order_map = {str(o["_id"]): o for o in db.service_orders.find(
            {"_id": {"$in": order_ids}},
            {"os_number": 1, "service_date": 1, "os_km": 1},
        )}
    detail_rows = []
    for n in STAGES:
        stage = item["stages"][n]
        oid = stage.get("service_order_id") or stage.get("candidate_service_order_id")
        order = order_map.get(str(oid), {}) if oid else {}
        detail_rows.append({
            "Etapa": f"{n}ª revisão",
            "Situação": stage["status"],
            "Previsão": _format_date(stage["due_date"]),
            "Realizada em": _format_date(stage["performed_at"]),
            "KM": stage["performed_km"] if stage["performed_km"] is not None else "—",
            "OS": order.get("os_number") or ("Vinculada" if oid else "—"),
            "Origem": stage.get("source") or ("Sugestão de OS" if stage.get("candidate_service_order_id") else "—"),
            "Indícios vinculados": len(stage.get("events") or []),
        })
    st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)
    if item["has_gap"]:
        gaps = ", ".join(f"{n}ª" for n in item["gap_stages"])
        st.warning(
            f"Lacuna de sequência nas etapas {gaps}: existe revisão posterior registrada, "
            "mas essas etapas não constam como realizadas. Isso NÃO prova que o cliente "
            "pulou a revisão; verifique as OS antes de registrar evasão."
        )
    if item["has_external"]:
        st.error("Há revisão marcada como realizada fora da concessionária. Esse é um registro explícito da jornada.")
    event_rows = []
    for event in sorted(item["events"], key=lambda e: e.get("service_date") or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        stage = event.get("manual_revision_number") if event.get("review_override") == "confirmada" else event.get("revision_number")
        event_rows.append({
            "OS": event.get("os_number"),
            "Data": _format_date(event.get("service_date")),
            "Etapa indicada": f"{stage}ª" if stage else "Indefinida",
            "Classificação": event.get("review_override") or event.get("classification") or "—",
            "Tipo de evidência": event.get("confidence") or "—",
            "Descrição": event.get("evidence_text") or "—",
        })
    with st.expander(f"Evidências de OS associadas ao veículo ({len(event_rows)})"):
        if event_rows:
            st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum sinal ROF080 associado a este veículo na base atual.")
    if st.button("Abrir jornada para conferência/correção", type="primary", key="dh_open_revision_journey"):
        st.session_state["dh_target_vehicle_id"] = item["vehicle_id"]
        st.session_state["dh_active_page"] = "revisions"
        st.rerun()


def render(db: Database, user: dict[str, Any]) -> None:
    page_header(
        "Painel das 5 revisões",
        "Quem realizou cada revisão, quem completou o ciclo e onde existem lacunas a investigar.",
    )
    st.markdown(
        '<div class="dh-revision-focus-note">'
        '<strong>Critério de comprovação:</strong> somente revisão registrada como realizada na jornada. '
        'Manutenções genéricas e menções em observações ficam separadas para conferência. '
        'Uma lacuna não significa necessariamente que o cliente deixou de fazer a revisão.'
        '</div>',
        unsafe_allow_html=True,
    )

    active_only = st.toggle("Apenas jornadas ativas", value=True, key="dh_five_active")
    try:
        data, scope = _load_audit(db, user, active_only)
    except Exception as exc:
        st.error("Não foi possível consultar o histórico das cinco revisões.")
        st.caption(f"Erro técnico: {type(exc).__name__}. Consulte os logs do servidor.")
        return
    rows = data["rows"]
    situations = data["by_situation"]
    total = int(data["total"])
    complete = situations.get("completo", 0)
    completed_customers = len({r["customer_id"] for r in rows
                               if r["situation_key"] == "completo" and r["customer_id"]})
    gaps = sum(bool(r["has_gap"]) for r in rows)
    outside = sum(bool(r["has_external"]) for r in rows)
    with_evidence = sum(bool(r["has_pending_evidence"]) for r in rows)
    overdue = sum(bool(r["has_overdue"]) for r in rows)

    kpis = st.columns(5, gap="small")
    kpis[0].metric("Veículos acompanhados", _number(total))
    kpis[1].metric("Cinco revisões realizadas", _number(complete), help="Todos os cinco status estão como realizados")
    kpis[2].metric("Com lacunas na sequência", _number(gaps), help="Etapa posterior realizada e anterior sem comprovação")
    kpis[3].metric("Revisão fora da rede", _number(outside), help="Status de evasão explicitamente registrado")
    kpis[4].metric("Indícios a conferir", _number(with_evidence), help="Veículos com evidência de revisão ainda não confirmada")
    st.caption(
        f"{_number(completed_customers)} cliente(s) distinto(s) já têm veículo com as cinco revisões concluídas · "
        f"{_number(overdue)} veículo(s) com etapa vencida sem comprovação. "
        "São indicadores de veículos/jornadas, não de linhas de OS."
    )

    st.markdown("### Acompanhamento da 1ª à 5ª revisão")
    _stage_cards(data)
    st.caption(
        "Taxa por etapa: revisões realizadas divididas apenas pelas jornadas com prazo "
        "da etapa vencido por data, etapa realizada ou lacuna em sequência. "
        "A quilometragem atual não foi usada para antecipar prazos."
    )

    tab_fleet, tab_quality = st.tabs(["Clientes e veículos por revisão", "Diagnóstico das OS importadas"])
    with tab_fleet:
        if not can(user, "journey.view"):
            st.warning("Seu perfil não tem permissão para visualizar os detalhes das jornadas.")
        elif not rows:
            st.info("Nenhuma jornada encontrada neste escopo. Verifique as importações e os filtros.")
        else:
            filter_a, filter_b, filter_c = st.columns([2.1, 1.1, 1.1])
            with filter_a:
                term = st.text_input("Buscar cliente ou veículo", placeholder="Nome, placa, chassi ou modelo", key="dh_five_search").strip().casefold()
            with filter_b:
                situation_keys = ["Todos"] + list(STATUS_LABELS.keys())
                chosen_situation = st.selectbox(
                    "Situação da jornada", situation_keys,
                    format_func=lambda key: STATUS_LABELS.get(key, key), key="dh_five_situation",
                )
            with filter_c:
                chosen_stage = st.selectbox("Etapa", ["Todas"] + list(STAGES),
                                            format_func=lambda x: f"{x}ª revisão" if isinstance(x, int) else x,
                                            key="dh_five_stage")
            only_gaps = st.checkbox("Somente veículos com lacuna entre etapas", value=False,
                                    key="dh_five_only_gaps")
            chosen_stage_status = "Todas"
            if isinstance(chosen_stage, int):
                chosen_stage_status = st.selectbox("Situação da etapa escolhida", ["Todas"] + list(STAGE_LABELS.keys()),
                                                 format_func=lambda key: STAGE_LABELS.get(key, key), key="dh_five_stage_status")
            filtered = []
            for item in rows:
                search_blob = " ".join(str(item[k]) for k in ("customer_name", "plate", "chassis", "model")).casefold()
                if term and term not in search_blob:
                    continue
                if chosen_situation != "Todos" and item["situation_key"] != chosen_situation:
                    continue
                if only_gaps and not item["has_gap"]:
                    continue
                if isinstance(chosen_stage, int) and chosen_stage_status != "Todas" and item["stages"][chosen_stage]["state"] != chosen_stage_status:
                    continue
                filtered.append(item)
            st.markdown(f"**{_number(len(filtered))} veículo(s)** correspondem aos filtros.")
            if filtered:
                visible_rows = table_rows(filtered)
                df = pd.DataFrame(visible_rows)
                st.dataframe(
                    df,
                    hide_index=True,
                    use_container_width=True,
                    height=min(630, 110 + 34 * min(len(df), 15)),
                )
                if can(user, "reports.export"):
                    st.download_button(
                        "Exportar matriz das 5 revisões (CSV)",
                        csv_bytes(visible_rows),
                        file_name="dealer_hub_5_revisoes_veiculos.csv",
                        mime="text/csv",
                        key="dh_five_export",
                    )
                st.divider()
                labels = [
                    f"{r['plate']} · {r['customer_name']} · {r['model']} · {r['vehicle_id'][-6:]}"
                    for r in filtered
                ]
                index = st.selectbox("Escolha um veículo para ver OS e as cinco etapas", range(len(filtered)),
                                     format_func=lambda index: labels[index], key="dh_five_detail_select")
                _detail(db, filtered[index])
            else:
                st.info("Nenhum veículo corresponde aos filtros selecionados.")

    with tab_quality:
        st.markdown("#### Por que existem tantas manutenções sem revisão vinculada?")
        st.caption(
            "Esta auditoria conta **sinais de revisão encontrados em OS**. "
            "O histórico ROF080 pode incluir veículos antigos, OS anteriores à venda, "
            "observações sem serviço executado e chassis ausentes da frota de jornadas. "
            "Esses registros não podem ser classificados automaticamente como revisões realizadas."
        )
        if not st.toggle("Carregar diagnóstico completo do ROF080", value=False, key="dh_five_load_quality"):
            st.info("O diagnóstico detalhado é carregado sob demanda para manter a matriz das cinco revisões rápida.")
            return
        try:
            quality = _read_quality(db, user, {str(v) for v in scope["vehicle_ids"]})
        except Exception as exc:
            st.error("Falha ao consultar qualidade dos vínculos das OS.")
            st.caption(f"Erro técnico: {type(exc).__name__}. Consulte os logs do servidor.")
            return
        counters = quality["totals"]
        qa, qb, qc, qd = st.columns(4)
        qa.metric("Sinais de OS", _number(counters.get("all_events", 0)))
        qb.metric("Sem vínculo de veículo", _number(counters.get("unlinked_vehicle", 0)))
        qc.metric("Ligados à frota filtrada", _number(counters.get("linked_selected", 0)))
        qd.metric("Ligados, aguardando análise", _number(counters.get("linked_for_review", 0)))
        st.caption(
            f"{_number(counters.get('observation_only', 0))} sinais vêm apenas de observações de OS; "
            f"{_number(counters.get('first_five_identified', 0))} sinais associados à frota têm ordinal da 1ª à 5ª. "
            "São métricas de evidência, não de revisões concluídas."
        )
        reasons = quality.get("link_reasons") or {}
        if reasons:
            st.dataframe(
                pd.DataFrame([{"Motivo do vínculo": key, "Sinais de OS": value}
                              for key, value in sorted(reasons.items(), key=lambda x: x[1], reverse=True)]),
                hide_index=True,
                use_container_width=True,
            )
        st.info(
            "**Próxima ação operacional:** confira primeiro as evidências vinculadas aos "
            "veículos da jornada. Os demais registros dependem de conciliação segura de chassi, "
            "proprietário, data da venda e fechamento da OS; não serão forçados para uma etapa."
        )
