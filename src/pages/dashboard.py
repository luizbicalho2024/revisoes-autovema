from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..appearance import get_appearance_settings
from ..charts import column_chart, donut_chart, line_chart
from ..repositories import array_scoped_filter, scoped_filter
from ..ui import page_header


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


def render(db: Database, user: dict) -> None:
    appearance = get_appearance_settings(db)

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
    sales_filter = {**sale_filter, "is_cancelled": False}
    journey_active_filter = {**journey_filter, "status": "ativa"}

    sales = db.sales.count_documents(sales_filter)
    active_journeys = db.journeys.count_documents(journey_active_filter)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes", f"{customers:,}".replace(",", "."))
    c2.metric("Veículos", f"{vehicles:,}".replace(",", "."))
    c3.metric("Vendas válidas", f"{sales:,}".replace(",", "."))
    c4.metric("Jornadas ativas", f"{active_journeys:,}".replace(",", "."))

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

    m1, m2, m3 = st.columns(3)
    m1.metric("Manutenção em dia", maintenance_counts.get("em_dia", 0))
    m2.metric("OS a confirmar", maintenance_counts.get("conciliar", 0))
    m3.metric("Manutenção atrasada", maintenance_counts.get("atrasada", 0))

    st.markdown("### Retenção por revisão")
    rows = []
    total_base = max(active_journeys, 1)

    for number in range(1, 6):
        query = {"revision_number": number, "status": "realizada"}
        if journey_filter.get("company_code"):
            query["company_code"] = journey_filter["company_code"]

        completed = len(db.revisions.distinct("vehicle_id", query))
        rows.append(
            {
                "Revisão": f"{number}ª",
                "Veículos retidos": completed,
                "Taxa": completed / total_base * 100,
            }
        )

    retention_df = pd.DataFrame(rows)
    left, right = st.columns([1.45, 1])

    with left:
        if retention_df["Veículos retidos"].sum() > 0:
            column_chart(
                [
                    {
                        "categoria": row["Revisão"],
                        "valor": int(row["Veículos retidos"]),
                    }
                    for row in rows
                ],
                category_field="categoria",
                value_field="valor",
                appearance=appearance,
                height=300,
            )
        else:
            st.info(
                "Ainda não há revisões registradas como realizadas. "
                "Parametrize as regras e atualize a jornada para iniciar a medição."
            )

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
        loyalty_rows = [
            {
                "categoria": f"{float(row.get('_id') or 0):.0f}% de bônus",
                "valor": int(row["total"]),
            }
            for row in loyalty
        ]

        chart_col, table_col = st.columns([1.1, 1])
        with chart_col:
            donut_chart(
                loyalty_rows,
                category_field="categoria",
                value_field="valor",
                appearance=appearance,
                height=270,
            )
        with table_col:
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

    st.markdown("### Vendas por mês")
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
            height=310,
        )

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

        st.dataframe(
            pd.DataFrame(data),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Nenhuma importação executada.")
