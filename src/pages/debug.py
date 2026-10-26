"""Área exclusiva para superadmin: inventário e exportação segura de importações."""
from __future__ import annotations

import json
import secrets

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..debug_export import COLLECTIONS, build_safe_archive, diagnostic_summary, page_records
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    # Não basta esconder o menu: bloqueia execução direta para outros perfis.
    if user.get("role") != "superadmin" or not st.session_state.get("authenticated"):
        st.error("Diagnóstico restrito ao superadministrador autenticado.")
        st.stop()
    page_header("Diagnóstico de importações", "Inspecione o que foi efetivamente armazenado e encontre os vínculos ausentes.")
    st.warning("O material para compartilhamento suprime nomes, documentos, placas, chassis, e-mails, "
               "observações e segredos. Não compartilhe capturas da área operacional com dados pessoais.")
    if "dh_debug_salt" not in st.session_state:
        st.session_state["dh_debug_salt"] = secrets.token_bytes(32)
    salt = st.session_state["dh_debug_salt"]
    summary = diagnostic_summary(db)
    st.markdown("### Inventário das coleções importadas")
    st.dataframe(pd.DataFrame([{"Coleção": c["collection"], "Registros": c["records"],
                               "Campos detectados": len(c["sample_fields"])}
                              for c in summary["collections"]]),
                 use_container_width=True, hide_index=True)
    a,b = st.columns(2)
    with a:
        st.markdown("#### Vínculo das evidências ROF080")
        st.dataframe(pd.DataFrame(summary["events"].get("link_status", [])),
                     hide_index=True,use_container_width=True)
        st.markdown("#### Confiança/classificação")
        st.dataframe(pd.DataFrame(summary["events"].get("confidence", [])),
                     hide_index=True,use_container_width=True)
    with b:
        st.markdown("#### Classificação das revisões")
        st.dataframe(pd.DataFrame(summary["events"].get("classification", [])),
                     hide_index=True,use_container_width=True)
        st.markdown("#### Situação das OS")
        st.dataframe(pd.DataFrame(summary["orders"].get("link_status", [])),
                     hide_index=True,use_container_width=True)
    st.markdown("### Inspecionar registros importados")
    collection=st.selectbox("Coleção",COLLECTIONS,key="debug_col")
    limit=st.selectbox("Linhas por página",[20,50,100],index=1,key="debug_page_size")
    total=db[collection].count_documents({})
    pages=max(1,(total+limit-1)//limit)
    idx=st.number_input("Página",min_value=1,max_value=pages,value=1,step=1,key=f"debug_page_{collection}")
    docs=page_records(db,collection,salt,offset=(idx-1)*limit,limit=limit)
    if docs:
        st.dataframe(pd.json_normalize(docs,max_level=2),use_container_width=True,hide_index=True)
        st.caption(f"Exibindo até {limit} registros da coleção {collection} · página {idx} de {pages}. "
                   "As referências anonimizadas são consistentes dentro do mesmo pacote.")
    else:
        st.info("Coleção vazia.")
    with st.expander("Campos detectados nas coleções"):
        for x in summary["collections"]:
            st.markdown(f"**{x['collection']} ({x['records']} registros):** {', '.join(x['sample_fields']) or 'Sem registros'}")
    st.markdown("### Preparar pacote de diagnóstico para compartilhar")
    cap=st.selectbox("Máximo de registros por coleção",[1000,5000,20000,100000],index=2)
    st.caption("O ZIP contém JSONL por coleção, estatísticas e manifesto com totais/exportados. "
               "Se houver truncamento, ele estará indicado no manifesto. Limite adicional: 24 MB de JSON não comprimido.")
    if st.button("Gerar pacote anonimizado",type="primary",key="debug_generate"):
        with st.spinner("Preparando exportação por lotes..."):
            st.session_state["dh_debug_export_bytes"] = build_safe_archive(db,salt,per_collection_limit=cap)
    if st.session_state.get("dh_debug_export_bytes"):
        st.download_button("Baixar diagnóstico para análise (ZIP)",
                           data=st.session_state["dh_debug_export_bytes"],
                           file_name="autovema_diagnostico_anonimizado.zip",mime="application/zip",
                           key="debug_download")
