from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo.database import Database

from ..repositories import array_scoped_filter, scoped_filter
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header(
        "Visão Geral",
        "Acompanhamento da base importada, jornada de revisões e retenção do pós-venda.",
    )

    customer_filter = array_scoped_filter(user)
    vehicle_filter = array_scoped_filter(user)
    sale_filter = scoped_filter(user)
    journey_filter = scoped_filter(user)

    customers = db.customers.count_documents(customer_filter)
    vehicles = db.vehicles.count_documents(vehicle_filter)
    sales = db.sales.count_documents({**sale_filter, "is_cancelled": False}) if sale_filter else db.sales.count_documents({"is_cancelled": False})
    active_journeys = db.journeys.count_documents({**journey_filter, "status": "ativa"}) if journey_filter else db.journeys.count_documents({"status": "ativa"})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes", f"{customers:,}".replace(",", "."))
    c2.metric("Veículos", f"{vehicles:,}".replace(",", "."))
    c3.metric("Vendas válidas", f"{sales:,}".replace(",", "."))
    c4.metric("Jornadas ativas", f"{active_journeys:,}".replace(",", "."))

    st.markdown("### Retenção por revisão")
    rows = []
    total_base = max(active_journeys, 1)
    for n in range(1, 6):
        q = {"revision_number": n, "status": "realizada"}
        if journey_filter.get("company_code"):
            q["company_code"] = journey_filter["company_code"]
        completed = len(db.revisions.distinct("vehicle_id", q))
        rows.append({"Revisão": f"{n}ª", "Veículos retidos": completed, "Taxa": completed / total_base * 100})

    retention_df = pd.DataFrame(rows)
    left, right = st.columns([1.4, 1])
    with left:
        if retention_df["Veículos retidos"].sum() > 0:
            fig = px.bar(retention_df, x="Revisão", y="Veículos retidos", text="Veículos retidos")
            fig.update_layout(height=330, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Ainda não há revisões registradas como realizadas. Parametrize as regras e atualize a jornada para iniciar a medição.")
    with right:
        st.dataframe(
            retention_df.style.format({"Taxa": "{:.1f}%"}),
            hide_index=True,
            use_container_width=True,
        )

    st.markdown("### Programa de fidelidade por revisões")
    loyalty_query = {"status": "ativa"}
    if journey_filter.get("company_code"):
        loyalty_query["company_code"] = journey_filter["company_code"]
    pipeline = [
        {"$match": loyalty_query},
        {"$group": {"_id": "$loyalty_bonus_pct", "total": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    loyalty = list(db.journeys.aggregate(pipeline))
    if loyalty:
        loyalty_df = pd.DataFrame(
            [{"Bônus atual": f"{float(r.get('_id') or 0):.0f}%", "Veículos": r["total"]} for r in loyalty]
        )
        st.dataframe(loyalty_df, hide_index=True, use_container_width=True)
    else:
        st.caption("Nenhuma jornada elegível calculada até o momento.")

    st.markdown("### Vendas por mês")
    pipeline = []
    if sale_filter:
        pipeline.append({"$match": {**sale_filter, "is_cancelled": False, "sale_date": {"$ne": None}}})
    else:
        pipeline.append({"$match": {"is_cancelled": False, "sale_date": {"$ne": None}}})
    pipeline.extend(
        [
            {"$group": {"_id": {"year": {"$year": "$sale_date"}, "month": {"$month": "$sale_date"}}, "vendas": {"$sum": 1}, "valor": {"$sum": {"$ifNull": ["$sale_value", 0]}}}},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ]
    )
    monthly = list(db.sales.aggregate(pipeline))
    if monthly:
        df = pd.DataFrame(
            [
                {
                    "Mês": datetime(r["_id"]["year"], r["_id"]["month"], 1, tzinfo=timezone.utc),
                    "Vendas": r["vendas"],
                    "Valor": r["valor"],
                }
                for r in monthly
            ]
        )
        fig = px.line(df, x="Mês", y="Vendas", markers=True)
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Últimas importações")
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
        st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
    else:
        st.caption("Nenhuma importação executada.")
