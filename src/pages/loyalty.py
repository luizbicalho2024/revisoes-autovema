"""Fidelidade e cinco revisões com distinção entre medição e bônus persistido."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..repositories import scoped_filter
from ..revision_audit import STAGES
from ..revision_views import load_five, five_table
from ..security import can
from ..ui import page_header


def _fmt(value) -> str:
    return f"{float(value or 0):.0f}%"


def render(db: Database, user: dict) -> None:
    page_header("Fidelidade · 5 revisões", "Compare o histórico efetivo das etapas com a bonificação atualmente registrada.")
    st.caption("Regra vigente preservada: 3ª = 1%, 4ª = 2%, 5ª = 3%, desde que cumpridas as condições do programa e sem evasão obrigatória.")
    data = load_five(db,user)
    rows = data["rows"]
    valid_ids = [r["vehicle_id"] for r in rows]
    journeys = {}
    for i in range(0,len(valid_ids),400):
        for j in db.journeys.find({"vehicle_id":{"$in":valid_ids[i:i+400]}, **scoped_filter(user)},
                                  {"vehicle_id":1,"loyalty_bonus_pct":1,"loyalty_cancelled":1,"loyalty_cancel_reason":1,"current_revision":1}):
            journeys[str(j["vehicle_id"])]=j
    records=[]
    for r in rows:
        j=journeys.get(r["vehicle_id"],{})
        records.append({"Cliente":r["customer_name"],"Placa":r["plate"],"Modelo":r["model"],
            "Revisões comprovadas":r["completed"],
            "Consecutivas":sum(1 for n in STAGES if all(r["stages"][i]["state"]=="realizada" for i in range(1,n+1))),
            "Bônus gravado":_fmt(j.get("loyalty_bonus_pct")),
            "Programa cancelado":"Sim" if j.get("loyalty_cancelled") else "Não",
            "Motivo":j.get("loyalty_cancel_reason") or "—",
            "Lacunas":"Sim" if r["has_gap"] else "Não",
            "ROF080 confirmadas fora do plano":r.get("completed_from_rof080",0)})
    a,b,c=st.columns(3)
    a.metric("Veículos avaliados",len(records))
    b.metric("5 revisões comprovadas",sum(r["completed"]==5 for r in rows))
    c.metric("Revisões ROF080 ainda fora do plano",sum(r.get("completed_from_rof080",0) for r in rows))
    st.caption("A V7 não recalcula nem concede bônus automaticamente com base no BI. Diferenças entre OS confirmada e plano devem ser auditadas antes de atualizar os benefícios.")
    if records:
        st.dataframe(pd.DataFrame(records),hide_index=True,use_container_width=True)
        if can(user,"reports.export"):
            from ..revision_audit import csv_bytes
            st.download_button("Exportar elegibilidade",csv_bytes(records),"fidelidade_5_revisoes.csv","text/csv",key="loyalty_five_export")
    with st.expander("Ver situação de cada revisão por veículo"):
        five_table(rows,user,key="loyalty",show_details=False)

    with st.expander("Consulta tradicional dos bônus gravados"):
        from . import loyalty_legacy
        loyalty_legacy.render(db,user)
