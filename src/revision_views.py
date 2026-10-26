"""Leituras reutilizáveis das cinco revisões sem alterar fidelidade/OS."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd
import streamlit as st

from .revision_audit import STAGES, STAGE_LABELS, STATUS_LABELS, csv_bytes, table_rows
from .security import can


def load_five(db: Any, user: dict[str, Any], active_only: bool = True) -> dict[str, Any]:
    # A mesma consulta consolidada empregada pelo BI, evitando indicadores
    # contraditórios entre Clientes, Veículos, Jornada, Fidelidade e Serviços.
    from .pages.dashboard import _load_audit
    data, _ = _load_audit(db, user, active_only)
    return data


def summary_cards(rows: list[dict[str, Any]]) -> None:
    c = st.columns(4)
    c[0].metric("Veículos em análise", f"{len(rows):,}".replace(",", "."))
    c[1].metric("Com 5 revisões", sum(r["completed"] == 5 for r in rows))
    c[2].metric("Lacunas na sequência", sum(bool(r["has_gap"]) for r in rows))
    c[3].metric("Etapas confirmadas via ROF080", sum(r.get("completed_from_rof080", 0) for r in rows))


def filtered_rows(rows: list[dict[str, Any]], term: str = "", situation: str = "Todos") -> list[dict[str, Any]]:
    term = (term or "").strip().casefold()
    return [r for r in rows
            if (situation == "Todos" or r["situation_key"] == situation)
            and (not term or term in " ".join(str(r.get(k) or "") for k in
                ("customer_name", "plate", "chassis", "model", "company")).casefold())]


def five_table(rows: list[dict[str, Any]], user: dict[str, Any], *, key: str, show_details: bool = True) -> None:
    if not rows:
        st.info("Não há clientes/veículos para os filtros selecionados.")
        return
    df = pd.DataFrame(table_rows(rows))
    st.dataframe(df, hide_index=True, use_container_width=True)
    if can(user, "reports.export"):
        st.download_button("Exportar matriz (CSV)", csv_bytes(df.to_dict("records")),
                           f"matriz_5_revisoes_{key}.csv", "text/csv", key=f"export_{key}")
    if show_details:
        options = {f"{r['customer_name']} · {r['plate']} · {r['model']} · {r['vehicle_id'][-5:]}": r
                   for r in rows[:1000]}
        chosen = st.selectbox("Consultar veículo e suas cinco etapas", list(options), key=f"vselect_{key}")
        selected = options[chosen]
        stage_df = pd.DataFrame([{
            "Etapa": f"{n}ª", "Situação": selected["stages"][n]["status"],
            "Realizada em": selected["stages"][n]["performed_at"],
            "KM": selected["stages"][n]["performed_km"],
            "Origem": selected["stages"][n].get("source") or "—",
            "OS vinculada": selected["stages"][n].get("service_order_id") or "—",
        } for n in STAGES])
        st.dataframe(stage_df, hide_index=True, use_container_width=True)
        if st.button("Abrir jornada deste veículo", key=f"goto_journey_{key}"):
            st.session_state["dh_target_vehicle_id"] = selected["vehicle_id"]
            st.session_state["dh_active_page"] = "revisions"
            st.rerun()
