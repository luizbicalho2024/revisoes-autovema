from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..appearance import get_appearance_settings
from ..charts import column_chart, donut_chart, line_chart, horizontal_bar_chart
from ..repositories import array_scoped_filter, scoped_filter
from ..ui import page_header
from ..revision_metrics import get_revision_metrics


MONTHS_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except Exception:
        return "0"



def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%"



def _safe_div(num: float, den: float) -> float:
    return (num / den * 100) if den else 0.0



def _metric_tile(label: str, value: Any, note: str = "", accent: str = "") -> str:
    accent_html = f'<div class="dh-metric-accent">{accent}</div>' if accent else ""
    note_html = f'<div class="dh-metric-note">{note}</div>' if note else ""
    return (
        '<div class="dh-metric-tile">'
        f'<div class="dh-metric-label">{label}</div>'
        f'<div class="dh-metric-value">{value}</div>'
        f'{note_html}'
        f'{accent_html}'
        '</div>'
    )



def _stack_tile(label: str, value: Any, note: str = "") -> str:
    note_html = f'<div class="dh-stack-note">{note}</div>' if note else ""
    return (
        '<div class="dh-stack-tile">'
        f'<div class="dh-stack-label">{label}</div>'
        f'<div class="dh-stack-value">{value}</div>'
        f'{note_html}'
        '</div>'
    )



def _section_heading(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'''
        <div class="dh-section-head">
          <div class="dh-section-kicker">{kicker}</div>
          <div class="dh-section-title">{title}</div>
          <div class="dh-section-subtitle">{subtitle}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )



def _latest_import_badge(job: dict[str, Any] | None) -> str:
    if not job:
        return "Sem importações recentes"
    filename = str(job.get("filename") or "Importação")
    status = str(job.get("status") or "desconhecido").upper()
    started = job.get("started_at")
    when = ""
    if isinstance(started, datetime):
        when = started.strftime("%d/%m/%Y %H:%M")
    if when:
        return f"Última carga: {filename} · {status} · {when}"
    return f"Última carga: {filename} · {status}"



def _insight_message(metrics: dict[str, Any], customers: int, vehicles: int) -> tuple[str, str]:
    confirmed = int(metrics.get("confirmed", 0))
    pending = int(metrics.get("pending", 0))
    total = int(metrics.get("total", 0))
    linked = int(metrics.get("linked", 0))

    if total == 0:
        return (
            "Sem leitura histórica consolidada",
            "Importe o catálogo de anomalias e o ROF080 para começar a medir as revisões automaticamente.",
        )
    if pending > confirmed * 5:
        return (
            "Alta fila de conferência manual",
            "A maior parte dos sinais de revisão ainda depende de validação. Priorize conferência das OS ambíguas e por observação.",
        )
    if confirmed > 0 and linked < total:
        return (
            "Base já começou a comprovar revisões",
            "Há revisões confirmadas, mas ainda existem eventos sem vínculo completo com veículo ou jornada. Vale revisar cadastros e chassis.",
        )
    if vehicles and customers:
        return (
            "Painel operacional atualizado",
            "Clientes, veículos e jornada estão coerentes com a base importada. O próximo passo é elevar a taxa de revisões comprovadas.",
        )
    return (
        "Painel carregado",
        "Revise as importações mais recentes e valide a classificação para melhorar a leitura executiva.",
    )



def render(db: Database, user: dict) -> None:
    appearance = get_appearance_settings(db)

    customer_filter = array_scoped_filter(user)
    vehicle_filter = array_scoped_filter(user)
    sale_filter = scoped_filter(user)
    journey_filter = scoped_filter(user)

    customers = db.customers.count_documents(customer_filter)
    vehicles = db.vehicles.count_documents(vehicle_filter)
    sales_filter = {**sale_filter, "is_cancelled": False}
    journey_active_filter = {**journey_filter, "status": "ativa"}

    sales = db.sales.count_documents(sales_filter)
    active_journeys = db.journeys.count_documents(journey_active_filter)

    maintenance_query = dict(journey_filter)
    maintenance_pipeline = [
        {"$match": maintenance_query},
        {
            "$group": {
                "_id": {"$ifNull": ["$maintenance_status", "sem_parametros"]},
                "total": {"$sum": 1},
            }
        },
    ]
    maintenance_rows = list(db.journeys.aggregate(maintenance_pipeline))
    maintenance_counts = {
        str(row.get("_id")): int(row.get("total", 0))
        for row in maintenance_rows
    }

    metrics = get_revision_metrics(db, user)
    latest_job = db.import_jobs.find_one({}, sort=[("started_at", -1)])
    headline, support = _insight_message(metrics, customers, vehicles)

    page_header(
        "Visão Geral",
        "Painel executivo das importações, retenção por revisão e qualidade do histórico ROF080.",
    )

    st.markdown(
        f'''
        <div class="dh-top-band">
          <div>
            <div class="dh-top-band-label">Resumo executivo</div>
            <div class="dh-top-band-title">{headline}</div>
            <div class="dh-top-band-subtitle">{support}</div>
          </div>
          <div class="dh-top-band-badge">{_latest_import_badge(latest_job)}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    shell_left, shell_right = st.columns([0.9, 2.8], gap="large")

    with shell_left:
        st.markdown('<div class="dh-panel-shell">', unsafe_allow_html=True)
        st.markdown('<div class="dh-stack-title">Base atual</div>', unsafe_allow_html=True)
        st.markdown(
            _stack_tile("Clientes", _fmt_int(customers), "Base ativa importada"),
            unsafe_allow_html=True,
        )
        st.markdown(
            _stack_tile("Veículos", _fmt_int(vehicles), "Com chassi vinculado"),
            unsafe_allow_html=True,
        )
        st.markdown(
            _stack_tile("Vendas válidas", _fmt_int(sales), "Exclui canceladas"),
            unsafe_allow_html=True,
        )
        st.markdown(
            _stack_tile("Jornadas ativas", _fmt_int(active_journeys), "Elegíveis para revisão"),
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with shell_right:
        top_a, top_b, top_c, top_d = st.columns(4)
        top_a.markdown(
            _metric_tile(
                "Manutenção em dia",
                _fmt_int(maintenance_counts.get("em_dia", 0)),
                note="Jornadas sem atraso",
                accent=_fmt_pct(_safe_div(maintenance_counts.get("em_dia", 0), active_journeys)),
            ),
            unsafe_allow_html=True,
        )
        top_b.markdown(
            _metric_tile(
                "OS para conferência",
                _fmt_int(maintenance_counts.get("conciliar", 0)),
                note="Aguardando conciliação",
                accent=_fmt_pct(_safe_div(maintenance_counts.get("conciliar", 0), active_journeys)),
            ),
            unsafe_allow_html=True,
        )
        top_c.markdown(
            _metric_tile(
                "Manutenção atrasada",
                _fmt_int(maintenance_counts.get("atrasada", 0)),
                note="Jornadas fora da meta",
                accent=_fmt_pct(_safe_div(maintenance_counts.get("atrasada", 0), active_journeys)),
            ),
            unsafe_allow_html=True,
        )
        top_d.markdown(
            _metric_tile(
                "Cobertura da jornada",
                _fmt_pct(_safe_div(active_journeys, vehicles)),
                note="Jornadas ativas / veículos",
                accent=f"{_fmt_int(active_journeys)}/{_fmt_int(vehicles)}",
            ),
            unsafe_allow_html=True,
        )

        _section_heading(
            "retenção",
            "Retenção por revisão",
            "Leitura das revisões já marcadas como realizadas e reflexo sobre a frota ativa.",
        )

        retention_rows = []
        total_base = max(active_journeys, 1)
        for number in range(1, 6):
            query = {"revision_number": number, "status": "realizada"}
            if journey_filter.get("company_code"):
                query["company_code"] = journey_filter["company_code"]
            completed = len(db.revisions.distinct("vehicle_id", query))
            retention_rows.append(
                {
                    "Revisão": f"{number}ª",
                    "Veículos retidos": completed,
                    "Taxa": completed / total_base * 100,
                }
            )
        retention_df = pd.DataFrame(retention_rows)

        ret_left, ret_right = st.columns([1.25, 1], gap="large")
        with ret_left:
            if retention_df["Veículos retidos"].sum() > 0:
                column_chart(
                    [
                        {
                            "categoria": row["Revisão"],
                            "valor": int(row["Veículos retidos"]),
                        }
                        for _, row in retention_df.iterrows()
                    ],
                    category_field="categoria",
                    value_field="valor",
                    appearance=appearance,
                    height=300,
                )
            else:
                st.info(
                    "Ainda não há revisões registradas como realizadas. Parametrize as regras e atualize a jornada para iniciar a medição."
                )
        with ret_right:
            st.markdown(
                _metric_tile(
                    "Veículos retidos",
                    _fmt_int(retention_df["Veículos retidos"].sum()),
                    note="Soma das 5 primeiras etapas",
                    accent=_fmt_pct(retention_df["Taxa"].sum()),
                ),
                unsafe_allow_html=True,
            )
            st.dataframe(
                retention_df.style.format({"Taxa": "{:.1f}%"}),
                hide_index=True,
                use_container_width=True,
            )

        _section_heading(
            "rof080",
            "Qualidade do histórico de revisões",
            "Métricas de leitura do histórico importado, separando sinais identificados, comprovações e pendências.",
        )

        total_signals = int(metrics.get("total", 0))
        confirmed = int(metrics.get("confirmed", 0))
        pending = int(metrics.get("pending", 0))
        linked = int(metrics.get("linked", 0))
        confirmation_rate = _safe_div(confirmed, total_signals)
        linking_rate = _safe_div(linked, total_signals)

        q1, q2, q3, q4 = st.columns(4)
        q1.markdown(
            _metric_tile(
                "Sinais de revisão",
                _fmt_int(total_signals),
                note="Eventos encontrados no ROF080",
                accent="Histórico importado",
            ),
            unsafe_allow_html=True,
        )
        q2.markdown(
            _metric_tile(
                "Revisões comprovadas",
                _fmt_int(confirmed),
                note="Com serviço, OS encerrada e elegível",
                accent=_fmt_pct(confirmation_rate),
            ),
            unsafe_allow_html=True,
        )
        q3.markdown(
            _metric_tile(
                "Pendências",
                _fmt_int(pending),
                note="Exigem validação manual",
                accent=_fmt_pct(_safe_div(pending, total_signals)),
            ),
            unsafe_allow_html=True,
        )
        q4.markdown(
            _metric_tile(
                "Com vínculo de veículo",
                _fmt_int(linked),
                note="Eventos ligados a um veículo",
                accent=_fmt_pct(linking_rate),
            ),
            unsafe_allow_html=True,
        )

        hist_left, hist_right = st.columns([1.2, 1.15], gap="large")
        with hist_left:
            if metrics["monthly"]:
                st.markdown('<div class="dh-chart-title">Revisões comprovadas por mês</div>', unsafe_allow_html=True)
                line_chart(
                    [{"categoria": row["_id"], "valor": int(row["total"])} for row in metrics["monthly"][-24:]],
                    category_field="categoria",
                    value_field="valor",
                    appearance=appearance,
                    height=290,
                )
            else:
                st.info("Ainda não há revisões comprovadas suficientes para formar a série mensal.")
        with hist_right:
            if metrics["by_revision"]:
                st.markdown('<div class="dh-chart-title">Revisões comprovadas por etapa</div>', unsafe_allow_html=True)
                horizontal_bar_chart(
                    [
                        {
                            "categoria": f"{int(row['_id'])}ª revisão",
                            "valor": int(row["orders"]),
                        }
                        for row in metrics["by_revision"]
                    ],
                    category_field="categoria",
                    value_field="valor",
                    appearance=appearance,
                    height=290,
                )
            else:
                st.info("Ainda não há etapas confirmadas suficientes para montar o ranking.")

        with st.expander("Qualidade da classificação e pendências do ROF080"):
            conf_cols = st.columns([1.05, 1.2])
            with conf_cols[0]:
                st.markdown(
                    _metric_tile(
                        "Taxa de confirmação",
                        _fmt_pct(confirmation_rate),
                        note="Revisões comprovadas / sinais identificados",
                    ),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    _metric_tile(
                        "Taxa de vínculo",
                        _fmt_pct(linking_rate),
                        note="Eventos ligados a um veículo / sinais identificados",
                    ),
                    unsafe_allow_html=True,
                )
            with conf_cols[1]:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Classificação": row.get("_id") or "não classificada",
                                "Eventos": row["total"],
                            }
                            for row in metrics["by_confidence"]
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

        _section_heading(
            "fidelidade",
            "Programa de fidelidade",
            "Distribuição atual das jornadas pelo percentual de bônus calculado.",
        )

        loyalty_query = {"status": "ativa"}
        if journey_filter.get("company_code"):
            loyalty_query["company_code"] = journey_filter["company_code"]

        pipeline = [
            {"$match": loyalty_query},
            {"$group": {"_id": "$loyalty_bonus_pct", "total": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        loyalty = list(db.journeys.aggregate(pipeline))

        loyalty_left, loyalty_right = st.columns([1.15, 1], gap="large")
        if loyalty:
            loyalty_rows = [
                {
                    "categoria": f"{float(row.get('_id') or 0):.0f}% de bônus",
                    "valor": int(row["total"]),
                }
                for row in loyalty
            ]
            with loyalty_left:
                donut_chart(
                    loyalty_rows,
                    category_field="categoria",
                    value_field="valor",
                    appearance=appearance,
                    height=280,
                )
            with loyalty_right:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Bônus atual": row["categoria"],
                                "Veículos": row["valor"],
                            }
                            for row in loyalty_rows
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.caption("Nenhuma jornada elegível calculada até o momento.")

        _section_heading(
            "tendência",
            "Vendas por mês",
            "Evolução mensal das vendas válidas importadas para acompanhamento da base comercial.",
        )

        monthly_pipeline = [
            {
                "$match": {
                    **sale_filter,
                    "is_cancelled": False,
                    "sale_date": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$sale_date"},
                        "month": {"$month": "$sale_date"},
                    },
                    "vendas": {"$sum": 1},
                    "valor": {"$sum": {"$ifNull": ["$sale_value", 0]}},
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ]

        monthly = list(db.sales.aggregate(monthly_pipeline))
        if monthly:
            monthly_rows = []
            for row in monthly:
                year = int(row["_id"]["year"])
                month = int(row["_id"]["month"])
                monthly_rows.append(
                    {
                        "mes": f"{MONTHS_PT[month]}/{str(year)[-2:]}",
                        "vendas": int(row["vendas"]),
                    }
                )

            line_chart(
                monthly_rows,
                category_field="mes",
                value_field="vendas",
                appearance=appearance,
                height=330,
            )

        _section_heading(
            "cargas",
            "Últimas importações",
            "Conferência rápida das cargas executadas e do aproveitamento obtido em cada arquivo.",
        )
        jobs = list(db.import_jobs.find({}).sort("started_at", -1).limit(8))
        if jobs:
            data = []
            for job in jobs:
                summary = job.get("summary") or {}
                data.append(
                    {
                        "Arquivo": job.get("filename"),
                        "Status": job.get("status"),
                        "Linhas": summary.get("rows_received", 0),
                        "Válidas": summary.get("rows_valid", 0),
                        "Clientes novos": summary.get("customers_upserted", 0),
                        "Veículos novos": summary.get("vehicles_upserted", 0),
                        "Início": job.get("started_at"),
                    }
                )
            st.dataframe(
                pd.DataFrame(data),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("Nenhuma importação executada.")
