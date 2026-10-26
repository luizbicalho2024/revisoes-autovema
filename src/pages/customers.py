"""Clientes e histórico das cinco revisões dos veículos vinculados."""
from __future__ import annotations
from collections import defaultdict

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..revision_views import filtered_rows, five_table, load_five, summary_cards
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header("Clientes · 5 revisões", "Clientes com seus veículos, revisões realizadas, lacunas e pendências por etapa.")
    data = load_five(db, user)
    rows = data["rows"]
    summary_cards(rows)
    term = st.text_input("Localizar cliente", placeholder="Nome, placa, modelo ou chassi", key="customer_rev_search")
    selected = filtered_rows(rows, term)
    grouped = defaultdict(list)
    for row in selected:
        grouped[row["customer_id"] or f"veic:{row['vehicle_id']}"].append(row)
    report = []
    for items in grouped.values():
        name = items[0]["customer_name"]
        report.append({"Cliente": name, "Veículos": len(items),
            "Veículos com 5 revisões": sum(x["completed"] == 5 for x in items),
            "Veículos com lacunas": sum(x["has_gap"] for x in items),
            "Revisões realizadas (1ª–5ª)": sum(x["completed"] for x in items),
            "Com evidências a conferir": sum(x["has_pending_evidence"] for x in items)})
    st.markdown("### Resultado por cliente")
    if report:
        st.dataframe(pd.DataFrame(sorted(report,key=lambda x:(-x["Veículos com 5 revisões"],x["Cliente"]))),
                     hide_index=True,use_container_width=True)
    st.markdown("### Veículos e etapas do cliente")
    five_table(selected, user, key="customers")


# Mantém a tela anterior acessível, sem misturar manutenção genérica nas métricas de revisão.
    with st.expander("Cadastro completo de clientes (consulta tradicional)"):
        from . import customers_legacy
        customers_legacy.render(db, user)
