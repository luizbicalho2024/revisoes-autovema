"""Painel histórico de oficina (superadmin): cruzamento de chassi x ROF080."""
from __future__ import annotations

import hashlib
import hmac
import io
import secrets
from datetime import datetime

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..ui import page_header
from ..workshop_history import STAGES, is_service_candidate, stage_number, summarize_workshop, year_value


def _fmt(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _load(db: Database) -> tuple[dict, list[dict]]:
    # Global por design: a oficina histórica não dispõe de company_code
    # para a maioria das OS. Somente superadmin pode executar esta consulta.
    fleet = [v.get("chassis") for v in db.vehicles.find({}, {"chassis": 1}) if v.get("chassis")]
    projection = {
        "_id": 1, "chassis": 1, "vehicle_id": 1, "model": 1,
        "service_order_id": 1, "os_number": 1, "service_date": 1,
        "closed_at": 1, "os_km": 1, "revision_number": 1,
        "manual_revision_number": 1, "classification": 1,
        "confidence": 1, "evidence_source": 1, "evidence_text": 1,
        "review_override": 1, "post_sale": 1, "owner_match": 1,
        "link_status": 1, "company_name": 1,
    }
    events = list(db.revision_events.find({}, projection))
    return summarize_workshop(events, fleet), events


def render(db: Database, user: dict) -> None:
    if user.get("role") != "superadmin" or not st.session_state.get("authenticated"):
        st.error("Histórico da oficina exclusivo para superadministrador autenticado.")
        st.stop()

    page_header("Histórico de revisões da oficina", "Cruze todas as OS ROF080 com o cadastro de veículos e identifique as cinco primeiras revisões sem misturar vendas atuais com serviços antigos.")
    st.warning(
        "**Universos diferentes:** a base de vendas atual não contém necessariamente todos os veículos atendidos pela oficina desde 2021. "
        "Uma OS encerrada com serviço de revisão é uma **evidência técnica**, não comprovação automática de retenção do comprador atual. "
        "Os dados desta tela são somente leitura."
    )

    if st.button("Atualizar leitura do histórico", key="workshop_refresh"):
        st.rerun()
    try:
        stats, events = _load(db)
    except Exception as exc:
        st.error("Não foi possível analisar o histórico da oficina.")
        st.caption(f"Falha na leitura: {type(exc).__name__}")
        return

    sigmec_total = db.sigmec_orders.count_documents({})
    if sigmec_total:
        sigmec_linked = db.sigmec_orders.count_documents({"link_status": "os_localizada"})
        st.caption(
            f"SIGMEC importado: {_fmt(sigmec_total)} OS com intervenções codificadas; "
            f"{_fmt(sigmec_linked)} conciliadas com OS do ROF080. "
            "A classificação por código das revisões aparece nas evidências do histórico "
            "quando a correspondência é inequívoca."
        )

    k = st.columns(5)
    for col, label, value, help_text in zip(k, [
        "Veículos vendidos na base", "Chassis nas OS", "Chassis nas duas bases",
        "OS com revisão 1ª–5ª indicada", "Chassis com essas OS",
    ], [
        stats["fleet_chassis"], stats["historic_chassis"], stats["chassis_overlap"],
        stats["candidate_os"], stats["candidate_chassis"],
    ], [
        "Cadastro de veículos importado", "Histórico completo do ROF080",
        "Interseção por chassi exato", "Serviço de revisão com etapa, em OS encerrada",
        "Não representam necessariamente compradores de 2026",
    ]):
        col.metric(label, _fmt(value), help=help_text)

    a,b,c,d=st.columns(4)
    a.metric("Confirmadas após venda atual",_fmt(stats["confirmed_current"]))
    b.metric("Serviços antes da venda atual",_fmt(stats["candidate_pre_sale"]))
    c.metric("Candidatas fora da frota atual",_fmt(stats["candidate_outside_current_fleet"]))
    d.metric("Revisão sem etapa definida",_fmt(stats["service_without_stage"]))
    st.caption(
        f"Foram registrados {_fmt(stats['total_events'])} sinais no total: "
        f"{_fmt(stats['observation_only'])} apenas em observações e "
        f"{_fmt(stats['ambiguous'])} com etapa ambígua. "
        "Esses grupos não entram nas revisões realizadas."
    )

    tab1,tab2,tab3 = st.tabs(["Auditoria por etapa e ano", "Veículos e histórico de OS", "Motivos da falta de vínculo"])
    with tab1:
        st.markdown("#### Serviços identificados da 1ª à 5ª revisão")
        st.dataframe(pd.DataFrame([
            {"Revisão":f"{step}ª", "OS encerradas com serviço identificado":stats["by_stage"].get(step,0)}
            for step in STAGES
        ]),hide_index=True,use_container_width=True)
        annual_rows = [
            {"Ano da OS":year,"Sinais totais":count} for year,count in stats["by_year"].items()
        ]
        st.markdown("#### Evolução do histórico importado")
        st.dataframe(pd.DataFrame(annual_rows),hide_index=True,use_container_width=True)
        cross_rows = [{"Ano":row["year"], "Etapa":f"{row['stage']}ª", "OS":row["count"]} for row in stats["by_year_stage"]]
        if cross_rows:
            st.dataframe(pd.DataFrame(cross_rows),hide_index=True,use_container_width=True)

    with tab2:
        search = st.text_input("Buscar chassi ou modelo",key="workshop_search",placeholder="Chassi completo ou parte do modelo")
        relation = st.selectbox("Vínculo com os veículos vendidos",["Todos","Na base atual","Fora da base atual"],key="workshop_relation")
        step_filter = st.selectbox("Etapa identificada",["Todas",1,2,3,4,5],format_func=lambda x:f"{x}ª revisão" if isinstance(x,int) else x,key="workshop_step")
        yr_filter = st.selectbox("Ano da OS",["Todos"]+sorted((x for x in stats["by_year"] if x!="Sem data"),reverse=True),key="workshop_year")
        visible=[]
        term=(search or "").strip().casefold()
        for item in stats["vehicles"]:
            if term and term not in (item["chassis"]+" "+item["model"]).casefold():
                continue
            if relation=="Na base atual" and not item["in_current_fleet"]:
                continue
            if relation=="Fora da base atual" and item["in_current_fleet"]:
                continue
            if isinstance(step_filter,int) and step_filter not in item["stages"]:
                continue
            if yr_filter!="Todos" and yr_filter not in item["years"]:
                continue
            visible.append(item)
        st.markdown(f"**{_fmt(len(visible))} chassis** encontrados nos filtros.")
        display=[]
        for item in visible[:3000]:
            display.append({
                "Chassi":item["chassis"],"Modelo":item["model"],
                "Na base vendida": "Sim" if item["in_current_fleet"] else "Não",
                "Etapas com serviço":", ".join(f"{n}ª" for n in item["stages"]),
                "OS de revisão":item["orders"], "Anos":", ".join(item["years"]),
                "OS anteriores à venda":item["pre_sale"],
                "Comprovações do comprador atual":item["confirmed_current"],
            })
        if display:
            st.dataframe(pd.DataFrame(display),hide_index=True,use_container_width=True,height=420)
            if len(visible)>3000:
                st.caption("Tabela limitada aos primeiros 3.000 chassis filtrados. Refine a busca.")
            choices = {f"{i['chassis']} · {i['model']}" : i for i in visible[:3000]}
            selected_label = st.selectbox("Detalhar histórico de um chassi",list(choices),key="workshop_selected_chassis")
            chosen = choices[selected_label]
            related=[]
            for event in events:
                if event.get("chassis")!=chosen["chassis"]:
                    continue
                if yr_filter!="Todos" and year_value(event.get("service_date"))!=yr_filter:
                    continue
                stage = stage_number(event)
                if isinstance(step_filter,int) and stage!=step_filter:
                    continue
                related.append({
                    "OS":event.get("os_number"),"Data":str(event.get("service_date") or "")[:10],
                    "Etapa":f"{stage}ª" if stage else "Indefinida",
                    "Situação":"Serviço de revisão na OS" if is_service_candidate(event) else "Indício / classificação pendente",
                    "Confiança":event.get("confidence"),
                    "Vínculo":event.get("link_status"),
                    "KM":event.get("os_km"),
                    "Descrição":event.get("evidence_text") or "—",
                })
            st.dataframe(pd.DataFrame(related),hide_index=True,use_container_width=True,height=360)
        else:
            st.info("Não há chassis com os filtros selecionados.")

    with tab3:
        st.markdown("#### Motivos de vínculo das evidências importadas")
        st.dataframe(pd.DataFrame([
            {"Situação":reason,"Sinais":count}
            for reason,count in sorted(stats["by_link"].items(),key=lambda x:-x[1])
        ]),hide_index=True,use_container_width=True)
        st.info(
            "**Interpretação:** um chassi fora das vendas recentes não significa que a OS esteja errada. "
            "Pode ser um cliente de anos anteriores ou um veículo atendido na oficina sem venda na base atual. "
            "Para medir retenção histórica por cliente será necessária uma base de vendas/transferências compatível "
            "com o mesmo período do ROF080."
        )
        if "dh_workshop_export_salt" not in st.session_state:
            st.session_state["dh_workshop_export_salt"] = secrets.token_bytes(32)
        salt=st.session_state["dh_workshop_export_salt"]
        export=[]
        for item in stats["vehicles"]:
            chassis_ref="REF-"+hmac.new(salt,item["chassis"].encode(),hashlib.sha256).hexdigest()[:14]
            export.append({
                "chassi_anonimizado":chassis_ref,"na_base_atual":item["in_current_fleet"],
                "etapas_de_servico":",".join(str(n) for n in item["stages"]),
                "os_de_revisao":item["orders"],"anos":",".join(item["years"]),
                "os_anteriores_venda":item["pre_sale"],
                "comprovadas_pos_venda_atual":item["confirmed_current"],
            })
        buffer=io.StringIO()
        pd.DataFrame(export).to_csv(buffer,index=False)
        st.download_button(
            "Exportar cruzamento anonimizado (CSV)",
            data=buffer.getvalue().encode("utf-8-sig"),
            file_name="cruzamento_oficina_anonimizado.csv",mime="text/csv",
            key="workshop_export",
        )
        st.caption("O arquivo compartilhável não contém chassis, placas, nomes, contatos ou descrições de OS.")
