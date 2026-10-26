"""Situação individual das cinco primeiras revisões por veículo."""
from __future__ import annotations

import streamlit as st
from pymongo.database import Database

from ..revision_audit import STATUS_LABELS
from ..revision_views import filtered_rows, five_table, load_five, summary_cards
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header("Veículos · 5 revisões", "Consulte placa, chassi, modelo, cliente e histórico comprovado por etapa.")
    data = load_five(db,user)
    rows = data["rows"]
    summary_cards(rows)
    a,b = st.columns([2,1])
    term = a.text_input("Buscar veículo/cliente", placeholder="Placa, chassi, modelo ou cliente", key="vehicles_rev_search")
    situation = b.selectbox("Situação", ["Todos"]+list(STATUS_LABELS),
                  format_func=lambda k: STATUS_LABELS.get(k,k), key="vehicle_rev_status")
    filtered = filtered_rows(rows,term,situation)
    st.caption(f"{len(filtered)} veículo(s) neste filtro. Etapas não vinculadas ao veículo não são atribuídas automaticamente.")
    five_table(filtered,user,key="vehicles")


# Mantém a tela anterior acessível, sem misturar manutenção genérica nas métricas de revisão.
    with st.expander("Cadastro completo de veículos (consulta tradicional)"):
        from . import vehicles_legacy
        vehicles_legacy.render(db, user)
