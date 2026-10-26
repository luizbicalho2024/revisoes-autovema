from __future__ import annotations

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..repositories import array_scoped_filter, combine_filters, text_search_filter
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header("Veículos", "Veículos consolidados por chassi, com proprietário atual e vínculo à venda.")
    c1, c2 = st.columns([2, 1])
    with c1:
        search = st.text_input("Pesquisar veículo", placeholder="Chassi, placa, modelo, marca ou cliente")
    with c2:
        limit = st.selectbox("Registros", [50, 100, 250, 500], index=1, key="vehicle_limit")

    query = combine_filters(
        array_scoped_filter(user),
        text_search_filter(search, ["chassis", "plate", "model", "brand"]),
    )
    docs = list(db.vehicles.find(query).sort("last_sale_at", -1).limit(limit))

    if search and len(docs) < limit:
        customer_ids = [c["_id"] for c in db.customers.find(text_search_filter(search, ["name", "document"]), {"_id": 1}).limit(limit)]
        if customer_ids:
            extra = list(db.vehicles.find(combine_filters(array_scoped_filter(user), {"customer_id": {"$in": customer_ids}})).limit(limit))
            by_id = {d["_id"]: d for d in docs}
            by_id.update({d["_id"]: d for d in extra})
            docs = list(by_id.values())[:limit]

    if not docs:
        st.info("Nenhum veículo encontrado.")
        return

    customer_ids = list({d.get("customer_id") for d in docs if d.get("customer_id")})
    customer_map = {d["_id"]: d.get("name") for d in db.customers.find({"_id": {"$in": customer_ids}}, {"name": 1})}
    rows = []
    for d in docs:
        rows.append(
            {
                "Placa": d.get("plate"),
                "Chassi": d.get("chassis"),
                "Marca": d.get("brand"),
                "Modelo": d.get("model"),
                "Ano": d.get("model_year"),
                "Cliente": customer_map.get(d.get("customer_id")),
                "Última venda": d.get("last_sale_at"),
                "Empresa": d.get("current_company_name"),
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button("Baixar resultado em CSV", df.to_csv(index=False).encode("utf-8-sig"), "veiculos_dealer_hub.csv", "text/csv")
