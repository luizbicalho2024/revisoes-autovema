"""Administração visual SIGMEC em Configurações do Programa."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .catalog_admin import catalog_rows, disable_code, save_code
from .sigmec_resync import sync_existing_orders


def render_catalog_settings(db, user) -> None:
    st.markdown("### Códigos SIGMEC de revisões")
    st.caption(
        "Cadastre, edite ou exclua (desative) códigos. O catálogo afeta as análises imediatamente; "
        "a sincronização atualiza os vínculos e evidências das OS já importadas. "
        "As alterações permanecem auditáveis."
    )
    rows = catalog_rows(db)
    active = [row for row in rows if row["active"]]
    c1, c2, c3 = st.columns(3)
    c1.metric("Códigos ativos", len(active))
    c2.metric("Códigos desativados", len(rows) - len(active))
    c3.metric("OS SIGMEC armazenadas", db.sigmec_orders.count_documents({}))
    q1, q2 = st.columns([3, 1])
    term = q1.text_input("Localizar código ou descrição", key="sigmec_admin_search")
    show_disabled = q2.checkbox("Mostrar desativados", value=False, key="sigmec_admin_disabled")
    selected_rows = [row for row in rows if (show_disabled or row["active"]) and (
        not term or term.casefold() in (row["code"] + " " + row["description"]).casefold()
    )]
    if selected_rows:
        st.dataframe(pd.DataFrame([{
            "Código": row["code"], "Descrição": row["description"],
            "Origem": "Padrão" if row["default"] else "Personalizado",
            "Situação": "Ativo" if row["active"] else "Desativado",
        } for row in selected_rows]), hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum código encontrado com os filtros atuais.")

    t_edit, t_add = st.tabs(["Editar / desativar", "Incluir / reativar"])
    with t_edit:
        if rows:
            options = {row["code"]: row for row in rows}
            code = st.selectbox("Código cadastrado", sorted(options), key="sigmec_admin_choose")
            current = options[code]
            with st.form(f"sigmec_edit_{code}"):
                description = st.text_area("Descrição / motorização / etapa", value=current["description"])
                submitted = st.form_submit_button("Salvar alterações", type="primary")
            if submitted:
                try:
                    save_code(db, user, code, description)
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Código {code} salvo. Sincronize as OS para aplicar.")
                    st.rerun()
            if current["active"]:
                confirm = st.checkbox(f"Confirmo a desativação do código {code}",
                                      key=f"sigmec_disable_confirm_{code}")
                if st.button("Excluir (desativar) código", disabled=not confirm, key=f"sigmec_disable_{code}"):
                    disable_code(db, user, code)
                    st.success(f"Código {code} desativado. Sincronize as OS para aplicar.")
                    st.rerun()
            else:
                st.info("Código desativado. Utilize Salvar alterações para reativá-lo.")
    with t_add:
        with st.form("sigmec_new_code"):
            new_code = st.text_input("Novo código SIGMEC", placeholder="0010XXXX", max_chars=24)
            new_description = st.text_area("Descrição da revisão", placeholder="1ª REVISÃO FLEX - KM OU TEMPO")
            create = st.form_submit_button("Cadastrar / reativar código", type="primary")
        if create:
            try:
                save_code(db, user, new_code, new_description)
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
            else:
                st.success("Código salvo. Execute a sincronização abaixo.")
                st.rerun()

    st.markdown("#### Sincronizar OS já importadas")
    st.caption("Reconsulta o vínculo das OS SIGMEC com o ROF080 e classifica os códigos usando "
               "o catálogo atual, sem solicitar novo upload. Confirmações manuais são preservadas; "
               "mudanças de etapa em evidências automáticas ficam pendentes de revisão.")
    confirm_sync = st.checkbox("Confirmo o reprocessamento das OS SIGMEC armazenadas",
                               key="sigmec_sync_confirm")
    if st.button("Sincronizar OS e identificar novos códigos", type="primary",
                 disabled=not confirm_sync, key="sigmec_sync_button"):
        bar = st.progress(0.0)
        def report(done: int, total: int) -> None:
            bar.progress(min(1.0, done / max(total, 1)))
        try:
            with st.spinner("Sincronizando OS SIGMEC já importadas..."):
                result = sync_existing_orders(db, user, progress=report)
        except Exception as exc:
            st.error(f"Falha na sincronização: {type(exc).__name__}. Consulte os logs da aplicação.")
        else:
            st.success("Sincronização concluída.")
            st.json(result)
            st.info("Confira a jornada e os registros pendentes antes de confirmar novas revisões ou bônus.")
