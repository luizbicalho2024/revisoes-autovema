from __future__ import annotations

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..repositories import array_scoped_filter, combine_filters, text_search_filter
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header("Clientes", "Base consolidada por CPF/CNPJ, sem duplicidade entre importações.")
    col1, col2 = st.columns([2, 1])
    with col1:
        search = st.text_input("Pesquisar", placeholder="Nome, CPF/CNPJ, telefone ou e-mail")
    with col2:
        limit = st.selectbox("Registros", [50, 100, 250, 500], index=1)

    query = combine_filters(
        array_scoped_filter(user),
        text_search_filter(search, ["name", "document", "phone", "email"]),
    )
    docs = list(db.customers.find(query).sort("last_purchase_at", -1).limit(limit))
    if not docs:
        st.info("Nenhum cliente encontrado.")
        return

    rows = []
    for d in docs:
        rows.append(
            {
                "Cliente": d.get("name"),
                "CPF/CNPJ": d.get("document"),
                "Telefone": d.get("phone"),
                "E-mail": d.get("email"),
                "Cidade/UF": " / ".join([x for x in [d.get("city"), d.get("state")] if x]),
                "Compras": d.get("sales_count", 0),
                "Veículos": d.get("vehicles_count", 0),
                "Última compra": d.get("last_purchase_at"),
                "Empresas": ", ".join(map(str, d.get("company_codes", []) or [])),
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Baixar resultado em CSV", csv, "clientes_dealer_hub.csv", "text/csv")
