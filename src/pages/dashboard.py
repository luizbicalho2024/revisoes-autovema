"""Visão geral minimalista: cinco revisões da frota e SIGMEC sem misturar universos.

Os dados são somente leitura. A medição da frota mantém critérios de
comprovação da jornada e ROF080; SIGMEC histórico tem indicadores separados.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..repositories import scoped_filter
from ..revision_audit import STAGES, STAGE_LABELS, STATUS_LABELS, csv_bytes, summarize_journeys, table_rows
from ..revision_bi import summarize_customers, summarize_sigmec
from ..revision_taxonomy import catalog_from_database
from ..security import can
from ..ui import page_header


STATUS_SIGMEC = {
    "confirmada_pos_venda": "Comprovação pós-venda",
    "ja_comprovada": "Já comprovada anteriormente",
    "pendente_validacao": "Etapa identificada; conferir",
    "sem_rof080": "OS sem vínculo ROF080",
    "etapa_ambigua": "Etapa não determinada",
    "divergencia": "Divergência de etapa",
    "descartada": "Descartada manualmente",
}


def _chunks(items: list[Any], size: int = 400):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _fmt(number: Any) -> str:
    return f"{int(number or 0):,}".replace(",", ".")


def _pct(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator * 100:.1f}%".replace(".", ",") if denominator else "—"


def _when(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    return "—"


def _load_journeys(db: Database, user: dict[str, Any]) -> dict[str, Any]:
    scope = dict(scoped_filter(user))
    scope["status"] = "ativa"
    journeys = list(db.journeys.find(scope, {
        "vehicle_id": 1, "customer_id": 1, "company_name": 1,
        "sale_date": 1, "status": 1, "company_code": 1,
    }))
    v_ids = list({j["vehicle_id"] for j in journeys if j.get("vehicle_id") is not None})
    c_ids = list({j["customer_id"] for j in journeys if j.get("customer_id") is not None})
    vehicle_map: dict[str, dict[str, Any]] = {}
    customer_map: dict[str, dict[str, Any]] = {}
    revisions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for chunk in _chunks(v_ids):
        key = {"$in": chunk}
        for doc in db.vehicles.find({"_id": key}, {"plate": 1, "chassis": 1, "model": 1}):
            vehicle_map[str(doc["_id"])] = doc
        revisions.extend(db.revisions.find({"vehicle_id": key, "revision_number": {"$in": list(STAGES)}}, {
            "vehicle_id": 1, "revision_number": 1, "status": 1, "due_date": 1,
            "performed_at": 1, "performed_km": 1, "source": 1,
            "service_order_id": 1, "candidate_service_order_id": 1,
        }))
        events.extend(db.revision_events.find({"vehicle_id": key}, {
            "vehicle_id": 1, "review_override": 1, "classification": 1,
            "revision_number": 1, "manual_revision_number": 1,
            "os_number": 1, "service_date": 1, "confidence": 1,
            "evidence_text": 1, "link_status": 1, "closed_at": 1,
            "owner_match": 1, "post_sale": 1, "evidence_source": 1,
            "service_order_id": 1, "os_km": 1,
        }))
    for chunk in _chunks(c_ids):
        for doc in db.customers.find({"_id": {"$in": chunk}}, {"name": 1}):
            customer_map[str(doc["_id"])] = doc
    return summarize_journeys(journeys, vehicle_map, customer_map, revisions, events,
                              now=datetime.now(timezone.utc))


def _load_sigmec(db: Database) -> dict[str, Any]:
    orders = list(db.sigmec_orders.find({}, {
        "dealer_code": 1, "os_number": 1, "os_normalized": 1,
        "interventions": 1, "revision_results": 1, "rof080_order_id": 1,
        "link_status": 1,
    }))
    service_ids = list({item["rof080_order_id"] for item in orders if item.get("rof080_order_id")})
    services: dict[str, dict[str, Any]] = {}
    for batch in _chunks(service_ids):
        for order in db.service_orders.find({"_id": {"$in": batch}}, {
            "model": 1, "chassis": 1, "plate": 1, "owner_name": 1,
            "closed_at": 1, "service_date": 1, "vehicle_id": 1,
        }):
            services[str(order["_id"])] = order
    return summarize_sigmec(orders, services, catalog_from_database(db))


def _show_kpi(label: str, value: Any, help_text: str) -> None:
    st.metric(label, _fmt(value), help=help_text)


def _fleet_overview(data: dict[str, Any]) -> None:
    rows = data["rows"]
    total = len(rows)
    with_any = sum(int(row["completed"] > 0) for row in rows)
    all_five = sum(int(row["completed"] == 5) for row in rows)
    gaps = sum(int(bool(row["has_gap"])) for row in rows)
    indications = sum(int(bool(row["has_pending_evidence"])) for row in rows)
    headings = (
        ("Veículos na jornada", total, "Jornadas ativas da base de vendas atual"),
        ("Com 1+ revisão", with_any, "Veículos com ao menos uma das cinco etapas comprovadas"),
        ("Ciclo completo (5/5)", all_five, "Veículos com as cinco etapas realizadas"),
        ("Com lacuna", gaps, "Revisão posterior comprovada sem registro de etapa anterior"),
        ("Com indício", indications, "Veículos com evidência que ainda exige análise"),
    )
    for col, (label, value, hint) in zip(st.columns(5, gap="small"), headings):
        with col:
            _show_kpi(label, value, hint)

    st.markdown("#### Acompanhamento por etapa")
    stage_table = []
    for n in STAGES:
        stage = data["by_stage"][n]
        done = int(stage.get("realizada", 0))
        eligible = int(data.get("stage_due_cohort", {}).get(n, 0))
        stage_table.append({
            "Etapa": f"{n}ª revisão",
            "Realizadas": done,
            "Indícios": int(stage.get("indicio", 0)),
            "Vencidas": int(stage.get("vencida", 0)),
            "Lacunas": int(stage.get("lacuna", 0)),
            "Elegíveis": eligible,
            "% da coorte": _pct(done, eligible),
        })
    left, right = st.columns([1.3, 1], gap="large")
    with left:
        with st.container(border=True):
            st.caption("Revisões realizadas e indícios por etapa")
            chart_df = pd.DataFrame(stage_table).set_index("Etapa")
            st.bar_chart(chart_df[["Realizadas", "Indícios"]], height=275)
    with right:
        with st.container(border=True):
            st.caption("Situação por etapa")
            st.dataframe(pd.DataFrame(stage_table), hide_index=True, use_container_width=True,
                         height=275)
    st.caption("As taxas usam somente a coorte elegível de cada etapa. Indícios não são somados às revisões realizadas.")

    bottom_left, bottom_right = st.columns([1, 1], gap="large")
    with bottom_left:
        with st.container(border=True):
            st.caption("Distribuição dos veículos por número de revisões concluídas")
            distribution = Counter(int(row["completed"]) for row in rows)
            df = pd.DataFrame([
                {"Revisões concluídas": str(n), "Veículos": distribution[n]}
                for n in range(6)
            ]).set_index("Revisões concluídas")
            st.bar_chart(df, height=220)
    with bottom_right:
        with st.container(border=True):
            st.caption("Situação das jornadas")
            situations = Counter(row["situation"] for row in rows)
            chart = pd.DataFrame([
                {"Situação": key, "Veículos": number}
                for key, number in situations.most_common()
            ])
            if not chart.empty:
                st.bar_chart(chart.set_index("Situação"), height=220, horizontal=True)
            else:
                st.info("Sem jornadas neste escopo.")


def _fleet_reports(data: dict[str, Any], db: Database, user: dict[str, Any]) -> None:
    if not can(user, "journey.view"):
        return
    rows = data["rows"]
    st.markdown("#### Clientes e veículos")
    st.caption("Selecione o cliente, a etapa ou a situação para investigar registros comprovados e pendências.")
    t1, t2 = st.tabs(["Por cliente", "Por veículo"])
    with t1:
        customer_report = summarize_customers(rows)
        search = st.text_input("Buscar cliente", placeholder="Nome do cliente", key="dh_bi_client_search").strip().casefold()
        show_completed = st.checkbox("Somente clientes com revisões comprovadas", key="dh_bi_client_done")
        visible = [r for r in customer_report if (not search or search in r["Cliente"].casefold())
                   and (not show_completed or r["Revisões comprovadas"] > 0)]
        st.caption(f"{_fmt(len(visible))} cliente(s) nos filtros.")
        if visible:
            st.dataframe(pd.DataFrame(visible), use_container_width=True, hide_index=True, height=350)
            if can(user, "reports.export"):
                st.download_button("Exportar clientes (CSV)", data=csv_bytes(visible),
                                   file_name="autovema_clientes_5_revisoes.csv", mime="text/csv",
                                   key="dh_bi_clients_export")
        else:
            st.info("Nenhum cliente com esses filtros.")
    with t2:
        q1, q2, q3 = st.columns([2, 1, 1], gap="small")
        with q1:
            term = st.text_input("Buscar veículo ou cliente", placeholder="Placa, chassi, modelo ou nome",
                                 key="dh_bi_vehicle_search").strip().casefold()
        with q2:
            step = st.selectbox("Revisão", ["Todas", 1, 2, 3, 4, 5],
                                format_func=lambda x: f"{x}ª" if isinstance(x, int) else x,
                                key="dh_bi_stage")
        with q3:
            state = st.selectbox("Situação da etapa", ["Todas"] + list(STAGE_LABELS),
                                 format_func=lambda x: STAGE_LABELS.get(x, x),
                                 disabled=not isinstance(step, int), key="dh_bi_stage_status")
        filter_done = st.checkbox("Apenas veículos com revisão comprovada", key="dh_bi_has_revision")
        filter_gap = st.checkbox("Somente lacunas na sequência", key="dh_bi_has_gap")
        filtered = []
        for row in rows:
            haystack = " ".join(str(row.get(field) or "") for field in ("customer_name", "model", "plate", "chassis")).casefold()
            if term and term not in haystack:
                continue
            if filter_done and row["completed"] == 0:
                continue
            if filter_gap and not row["has_gap"]:
                continue
            if isinstance(step, int) and state != "Todas" and row["stages"][step]["state"] != state:
                continue
            filtered.append(row)
        filtered.sort(key=lambda row: (-row["completed"], -int(row["has_gap"]), row["customer_name"]))
        st.caption(f"{_fmt(len(filtered))} veículo(s) encontrados.")
        if not filtered:
            st.info("Nenhum veículo corresponde aos filtros.")
            return
        tabular = table_rows(filtered)
        st.dataframe(pd.DataFrame(tabular), hide_index=True, use_container_width=True, height=370)
        if can(user, "reports.export"):
            st.download_button("Exportar veículos (CSV)", data=csv_bytes(tabular),
                               file_name="autovema_veiculos_5_revisoes.csv", mime="text/csv",
                               key="dh_bi_vehicles_export")
        selected_idx = st.selectbox("Detalhar veículo e histórico das OS", range(len(filtered)),
                                    format_func=lambda i: f"{filtered[i]['plate']} · {filtered[i]['customer_name']} · {filtered[i]['model']}",
                                    key="dh_bi_vehicle_detail")
        chosen = filtered[selected_idx]
        detail = []
        order_ids = [s.get("service_order_id") for s in chosen["stages"].values() if s.get("service_order_id")]
        orders = {}
        if order_ids:
            orders = {str(o["_id"]): o for o in db.service_orders.find({"_id": {"$in": order_ids}},
                                                               {"os_number": 1})}
        for n in STAGES:
            item = chosen["stages"][n]
            o = orders.get(str(item.get("service_order_id")), {})
            detail.append({
                "Etapa": f"{n}ª revisão", "Situação": item["status"],
                "Previsão": _when(item.get("due_date")),
                "Realizada": _when(item.get("performed_at")),
                "KM": item.get("performed_km") if item.get("performed_km") is not None else "—",
                "OS": o.get("os_number") or "—",
                "Fonte": item.get("source") or "—",
            })
        with st.expander("Ver cinco etapas, datas e ordens de serviço", expanded=False):
            st.dataframe(pd.DataFrame(detail), hide_index=True, use_container_width=True)
            if st.button("Abrir Jornada de Revisões", key="dh_bi_open_journey"):
                st.session_state["dh_target_vehicle_id"] = chosen["vehicle_id"]
                st.session_state["dh_active_page"] = "revisions"
                st.rerun()


def _historical_sigmec(db: Database, user: dict[str, Any]) -> None:
    # Histórico integral, inclusive veículos fora do escopo de venda, é superadmin.
    if user.get("role") != "superadmin":
        return
    try:
        stats = _load_sigmec(db)
    except Exception as exc:
        st.error("Não foi possível consultar os códigos SIGMEC importados.")
        st.caption(f"Detalhe técnico: {type(exc).__name__}")
        return
    cols = st.columns(4, gap="small")
    measures = [
        ("OS SIGMEC importadas", stats["total_os"], "OS distintas; arquivos duplicados não são contados novamente"),
        ("OS com código de revisão", stats["revision_os"], "OS com algum código do catálogo de revisão, excluindo entrega"),
        ("Cruzadas com ROF080", stats["revision_linked"], "OS codificadas com documento ROF080 localizado"),
        ("Sem cruzamento ROF080", stats["revision_unlinked"], "OS com código mas sem referência segura à OS do ROF080"),
    ]
    for col, (name, value, help_text) in zip(cols, measures):
        with col:
            _show_kpi(name, value, help_text)
    st.caption("Histórico de códigos por OS: não equivale à quantidade de veículos da frota atual que realizaram revisão.")
    hist_a, hist_b = st.columns([1.1, 1], gap="large")
    stage_rows = [{"Etapa": f"{n}ª revisão", "OS com etapa identificada": int(stats["by_stage"].get(n, 0))}
                  for n in STAGES]
    with hist_a:
        with st.container(border=True):
            st.caption("OS codificadas por etapa inequívoca (histórico)")
            st.bar_chart(pd.DataFrame(stage_rows).set_index("Etapa"), height=280)
    with hist_b:
        with st.container(border=True):
            st.caption("Qualidade do cruzamento SIGMEC × ROF080")
            statuses = pd.DataFrame([
                {"Situação": STATUS_SIGMEC.get(key, key), "OS": value}
                for key, value in sorted(stats["by_status"].items(), key=lambda pair: -pair[1])
            ])
            if len(statuses):
                st.bar_chart(statuses.set_index("Situação"), horizontal=True, height=280)
            else:
                st.info("Ainda não foram encontrados códigos periódicos na importação SIGMEC.")

    st.markdown("#### Localizar OS, cliente e veículo no histórico")
    st.caption("Os dados de chassi e proprietário vêm do ROF080 somente quando a OS SIGMEC foi conciliada.")
    f1, f2, f3 = st.columns([2, 1, 1], gap="small")
    with f1:
        query = st.text_input("Buscar OS, código, chassi, placa ou cliente", key="dh_bi_sigmec_search").strip().casefold()
    with f2:
        wanted_stage = st.selectbox("Etapa", ["Todas", 1, 2, 3, 4, 5, "Indefinida"],
                                    format_func=lambda x: f"{x}ª" if isinstance(x, int) else x,
                                    key="dh_bi_sigmec_stage")
    with f3:
        wanted_link = st.selectbox("Vínculo ROF080", ["Todos", "Com vínculo", "Sem vínculo"],
                                   key="dh_bi_sigmec_link")
    visible = []
    for item in stats["details"]:
        if wanted_stage != "Todas":
            if wanted_stage == "Indefinida" and item["etapa"] is not None:
                continue
            if isinstance(wanted_stage, int) and item["etapa"] != wanted_stage:
                continue
        if wanted_link == "Com vínculo" and not item["vinculo_rof080"]:
            continue
        if wanted_link == "Sem vínculo" and item["vinculo_rof080"]:
            continue
        text = " ".join(str(item.get(k) or "") for k in
                        ("os", "codigos", "cliente_os", "chassi", "placa", "modelo")).casefold()
        if query and query not in text:
            continue
        visible.append({
            "OS": item["os"], "Código(s)": item["codigos"],
            "Etapa": f"{item['etapa']}ª" if item["etapa"] else "A conferir",
            "Situação": STATUS_SIGMEC.get(item["situacao"], item["situacao"]),
            "ROF080": "Sim" if item["vinculo_rof080"] else "Não",
            "Cliente da OS": item["cliente_os"] or "—",
            "Placa": item["placa"] or "—", "Modelo": item["modelo"] or "—",
            "Chassi": item["chassi"] or "—", "Data OS": _when(item["data_os"]),
        })
    st.caption(f"{_fmt(len(visible))} OS com código de revisão correspondem aos filtros.")
    if visible:
        st.dataframe(pd.DataFrame(visible[:2000]), hide_index=True, use_container_width=True, height=360)
        if len(visible) > 2000:
            st.caption("Visualização limitada a 2.000 linhas; refine os filtros ou exporte os resultados.")
        if can(user, "reports.export"):
            st.download_button("Exportar OS codificadas (CSV)", csv_bytes(visible),
                               file_name="autovema_sigmec_codigos_rof080.csv",
                               mime="text/csv", key="dh_bi_sigmec_export")
    else:
        st.info("Nenhuma OS corresponde aos filtros selecionados.")


def render(db: Database, user: dict[str, Any]) -> None:
    page_header("Visão geral · 5 revisões", "Clientes, veículos, etapas realizadas e histórico codificado.")
    try:
        data = _load_journeys(db, user)
    except Exception as exc:
        st.error("Não foi possível consultar as cinco revisões da frota.")
        st.caption(f"Erro técnico: {type(exc).__name__}. Consulte os logs.")
        return
    if user.get("role") == "superadmin":
        current, historical = st.tabs(["Frota atual · 5 revisões", "Histórico SIGMEC · OS codificadas"])
        with current:
            _fleet_overview(data)
            _fleet_reports(data, db, user)
        with historical:
            _historical_sigmec(db, user)
    else:
        _fleet_overview(data)
        _fleet_reports(data, db, user)
