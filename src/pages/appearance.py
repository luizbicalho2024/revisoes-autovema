from __future__ import annotations

import base64
import html

import streamlit as st
from pymongo.database import Database

from ..appearance import (
    DEFAULT_APPEARANCE,
    get_appearance_settings,
    reset_appearance_settings,
    save_appearance_settings,
)
from ..repositories import audit
from ..security import require_permission
from ..ui import page_header


def _logo_preview(current: dict) -> None:
    if not current.get("logo_b64"):
        st.caption("Nenhum logotipo personalizado cadastrado.")
        return

    try:
        uri = f'data:{current.get("logo_mime")};base64,{current["logo_b64"]}'
        st.markdown(
            f"""
            <div style="
                min-height:72px;
                display:flex;
                align-items:center;
                justify-content:flex-start;
                background:transparent;
                padding:8px 0;
            ">
                <img src="{uri}" alt="Logo" style="
                    width:min(245px,100%);
                    height:auto;
                    max-height:50px;
                    object-fit:contain;
                    object-position:left center;
                    background:transparent;
                ">
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(current.get("logo_name") or "Logo atual")
    except Exception:
        st.warning("O logotipo salvo não pôde ser exibido.")


def render(db: Database, user: dict) -> None:
    require_permission(user, "settings.manage")
    current = get_appearance_settings(db)

    page_header(
        "Aparência do Sistema",
        "Personalize logo, cores e layout. As mudanças são aplicadas globalmente.",
    )

    preview_col, logo_col = st.columns([1.35, 1])

    with preview_col:
        st.markdown("### Prévia")
        st.markdown(
            f"""
            <div class="dh-preview">
              <div class="dh-preview-card">
                <div class="dh-preview-bar"></div>
                <strong>{html.escape(current["system_name"])}</strong>
                <div class="dh-preview-muted">
                  {html.escape(current["system_subtitle"])}
                </div>
                <div style="margin-top:.85rem">
                  <span class="dh-chip">Clientes</span>
                  <span class="dh-chip">Veículos</span>
                  <span class="dh-chip">Revisões</span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with logo_col:
        st.markdown("### Logotipo")
        _logo_preview(current)
        st.caption(
            "O mesmo arquivo é utilizado na sidebar, no login e como favicon do navegador."
        )

    with st.form("appearance_form", clear_on_submit=False):
        st.markdown("### Identidade")
        c1, c2 = st.columns(2)
        system_name = c1.text_input(
            "Nome do sistema",
            value=current["system_name"],
            max_chars=60,
        )
        system_subtitle = c2.text_input(
            "Subtítulo",
            value=current["system_subtitle"],
            max_chars=90,
        )

        logo = st.file_uploader(
            "Enviar novo logotipo",
            type=["png", "jpg", "jpeg", "webp"],
            help=(
                "Recomendado: PNG ou WEBP transparente, horizontal, aproximadamente "
                "245 x 50 px. Máximo de 1,5 MB."
            ),
        )
        remove_logo = st.checkbox(
            "Remover o logotipo atual",
            value=False,
            disabled=not bool(current.get("logo_b64")),
        )

        st.markdown("### Cores institucionais")
        c1, c2, c3 = st.columns(3)
        primary_color = c1.color_picker(
            "Cor principal",
            value=current["primary_color"],
        )
        secondary_color = c2.color_picker(
            "Cor secundária",
            value=current["secondary_color"],
        )
        accent_color = c3.color_picker(
            "Cor de destaque",
            value=current["accent_color"],
        )

        st.markdown("### Conteúdo")
        c1, c2, c3 = st.columns(3)
        background_color = c1.color_picker(
            "Fundo da aplicação",
            value=current["background_color"],
        )
        surface_color = c2.color_picker(
            "Cards e superfícies",
            value=current["surface_color"],
        )
        border_color = c3.color_picker(
            "Bordas",
            value=current["border_color"],
        )

        c1, c2 = st.columns(2)
        text_color = c1.color_picker(
            "Texto principal",
            value=current["text_color"],
        )
        muted_color = c2.color_picker(
            "Texto secundário",
            value=current["muted_color"],
        )

        st.markdown("### Sidebar")
        c1, c2 = st.columns(2)
        sidebar_color = c1.color_picker(
            "Fundo da sidebar",
            value=current["sidebar_color"],
        )
        sidebar_text_color = c2.color_picker(
            "Texto da sidebar",
            value=current["sidebar_text_color"],
        )

        st.markdown("### Layout")
        c1, c2 = st.columns(2)
        border_radius = c1.slider(
            "Arredondamento dos componentes",
            min_value=4,
            max_value=24,
            value=int(current["border_radius"]),
            step=1,
        )
        sidebar_width = c2.slider(
            "Largura da sidebar",
            min_value=260,
            max_value=360,
            value=int(current["sidebar_width"]),
            step=2,
        )

        show_scope = st.toggle(
            "Mostrar o escopo de empresas no perfil lateral",
            value=bool(current.get("show_scope", True)),
        )

        save = st.form_submit_button(
            "Salvar personalização",
            type="primary",
            use_container_width=True,
        )

    if save:
        values = {
            "system_name": system_name,
            "system_subtitle": system_subtitle,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "accent_color": accent_color,
            "background_color": background_color,
            "surface_color": surface_color,
            "text_color": text_color,
            "muted_color": muted_color,
            "border_color": border_color,
            "sidebar_color": sidebar_color,
            "sidebar_text_color": sidebar_text_color,
            "border_radius": border_radius,
            "sidebar_width": sidebar_width,
            "show_scope": show_scope,
        }

        try:
            updated = save_appearance_settings(
                db,
                values,
                user.get("email", "system"),
                logo_bytes_value=logo.getvalue() if logo is not None else None,
                logo_name=logo.name if logo is not None else None,
                remove_logo=remove_logo,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            audit(
                db,
                user,
                "appearance_updated",
                "settings",
                "appearance",
                {
                    "system_name": updated["system_name"],
                    "primary_color": updated["primary_color"],
                    "sidebar_color": updated["sidebar_color"],
                    "logo_changed": bool(logo) or remove_logo,
                },
            )
            st.success("Personalização salva.")
            st.rerun()

    st.divider()

    with st.expander("Restaurar aparência padrão"):
        st.caption(
            "Restaura nome, cores e layout originais e remove o logotipo personalizado."
        )
        confirm = st.checkbox(
            "Confirmo que desejo restaurar a aparência padrão",
            key="appearance_reset_confirm",
        )
        if st.button(
            "Restaurar padrão",
            disabled=not confirm,
            use_container_width=True,
        ):
            reset_appearance_settings(db, user.get("email", "system"))
            audit(
                db,
                user,
                "appearance_reset",
                "settings",
                "appearance",
                {"defaults": DEFAULT_APPEARANCE},
            )
            st.success("Aparência padrão restaurada.")
            st.rerun()
