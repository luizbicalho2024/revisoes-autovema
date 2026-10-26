from __future__ import annotations

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..repositories import scoped_filter
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header(
        "Fidelidade / Recompra Garantida",
        "Elegibilidade progressiva conforme a realização integral das revisões na concessionária.",
    )
    st.info("Regra do MVP: 3ª revisão = 1%, 4ª = 2% e 5ª ou mais = 3% de bônus sobre a avaliação FIPE, desde que não exista evasão em nenhuma revisão obrigatória.")

    query = {"status": "ativa", **scoped_filter(user)}
    filter_bonus = st.multiselect("Bônus atual", [0, 1, 2, 3], default=[0, 1, 2, 3], format_func=lambda x: f"{x}%")
    if filter_bonus:
        query["loyalty_bonus_pct"] = {"$in": [float(x) for x in filter_bonus]}

    journeys = list(db.journeys.find(query).sort([("loyalty_bonus_pct", -1), ("sale_date", -1)]).limit(1000))
    if not journeys:
        st.info("Nenhuma jornada encontrada para os filtros selecionados.")
        return

    vehicle_map = {v["_id"]: v for v in db.vehicles.find({"_id": {"$in": [j["vehicle_id"] for j in journeys]}})}
    customer_map = {c["_id"]: c for c in db.customers.find({"_id": {"$in": [j.get("customer_id") for j in journeys]}})}
    rows = []
    for j in journeys:
        vehicle = vehicle_map.get(j["vehicle_id"], {})
        customer = customer_map.get(j.get("customer_id"), {})
        rows.append({
            "Cliente": customer.get("name"),
            "CPF/CNPJ": customer.get("document"),
            "Placa": vehicle.get("plate"),
            "Modelo": vehicle.get("model"),
            "Revisão consecutiva": j.get("current_revision", 0),
            "Bônus": f"{float(j.get('loyalty_bonus_pct') or 0):.0f}%",
            "Cancelado": "Sim" if j.get("loyalty_cancelled") else "Não",
            "Motivo": j.get("loyalty_cancel_reason"),
            "Compra": j.get("sale_date"),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button("Baixar elegibilidade em CSV", df.to_csv(index=False).encode("utf-8-sig"), "elegibilidade_recompra.csv", "text/csv")
