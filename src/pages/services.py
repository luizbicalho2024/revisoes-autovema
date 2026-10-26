"""Ordens de serviço ROF080 separadas de manutenções sem revisão comprovada."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..revision_audit import verified_service_event
from ..revision_views import load_five, filtered_rows, five_table
from ..repositories import scoped_filter
from ..security import can
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header("Serviços · revisão x manutenção", "Diferencie revisões comprovadas por OS de menções e serviços que não comprovam uma etapa.")
    data=load_five(db,user)
    rows=data["rows"]
    vehicle_ids={r["vehicle_id"] for r in rows}
    events=[]
    for i in range(0,len(vehicle_ids),400):
        batch=list(vehicle_ids)[i:i+400]
        events.extend(db.revision_events.find({"vehicle_id":{"$in":batch}},
            {"_id":1,"vehicle_id":1,"os_number":1,"service_date":1,"closed_at":1,
             "post_sale":1,"owner_match":1,"link_status":1,"revision_number":1,
             "manual_revision_number":1,"review_override":1,"classification":1,
             "confidence":1,"evidence_source":1,"evidence_text":1,"os_km":1}))
    verified=[e for e in events if verified_service_event(e)]
    pending=[e for e in events if not verified_service_event(e) and e.get("review_override")!="descartada"]
    a,b,c=st.columns(3)
    a.metric("OS de revisão comprovada",len(verified))
    b.metric("Evidências a conferir (veículos vinculados)",len(pending))
    c.metric("Veículos com cinco revisões",sum(r["completed"]==5 for r in rows))
    st.caption("Números desta seção abrangem somente os veículos presentes na jornada consultada. "
               "OS de toda a base e divergências de importação estão no Diagnóstico, acessível ao superadmin.")
    by_id={r["vehicle_id"]:r for r in rows}
    t1,t2,t3=st.tabs(["Revisões comprovadas por OS","Evidências a conferir","Histórico das cinco etapas"])
    def records(collection):
        out=[]
        for e in collection:
            r=by_id.get(str(e.get("vehicle_id")),{})
            n=e.get("manual_revision_number") if e.get("review_override")=="confirmada" else e.get("revision_number")
            out.append({"Cliente":r.get("customer_name","—"),"Placa":r.get("plate","—"),
                "OS":e.get("os_number"),"Data":e.get("service_date"),
                "Revisão":f"{n}ª" if n else "Indefinida", "Confiança":e.get("confidence"),
                "Origem":e.get("evidence_source"),"KM":e.get("os_km"),
                "Vínculo":e.get("link_status"),"Descrição":e.get("evidence_text")})
        return out
    with t1:
        verified_rows=records(verified)
        if verified_rows: st.dataframe(pd.DataFrame(verified_rows),hide_index=True,use_container_width=True)
        else: st.info("Nenhuma OS ROF080 com requisitos de comprovação preenchidos no escopo atual.")
    with t2:
        pending_rows=records(pending)
        st.caption("Menções em observações e manutenções comuns não são promovidas a revisão realizada.")
        if pending_rows: st.dataframe(pd.DataFrame(pending_rows[:1000]),hide_index=True,use_container_width=True)
        else: st.success("Sem evidências pendentes vinculadas aos veículos deste escopo.")
    with t3:
        five_table(rows,user,key="services",show_details=True)


# Mantém a tela anterior acessível, sem misturar manutenção genérica nas métricas de revisão.
    with st.expander("Outras manutenções e histórico genérico de OS"):
        from . import services_legacy
        services_legacy.render(db, user)
