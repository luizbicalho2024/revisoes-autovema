from __future__ import annotations

import streamlit as st

from src.appearance import get_appearance_settings, page_icon_value
from src.auth import render_login
from src.config import APP_NAME, get_settings
from src.db import (
    bootstrap_database,
    clear_database_caches,
    is_transient_mongo_error,
)
from src.security import (
    can,
    initialize_session,
    logout,
    session_expired,
    touch_session,
)
from src.ui import (
    inject_css,
    sidebar_footer,
    sidebar_identity,
    sidebar_navigation,
)
from src.pages import (
    account,
    appearance,
    audit,
    customers,
    dashboard,
    import_page,
    loyalty,
    revisions,
    services,
    settings,
    users,
    vehicles,
)


st.set_page_config(
    page_title=APP_NAME,
    page_icon=":material/directions_car:",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialize_session()

try:
    db, _bootstrap_message = bootstrap_database()
except Exception as exc:
    st.error("Não foi possível inicializar o Dealer Hub.")

    if is_transient_mongo_error(exc):
        st.warning(
            "O MongoDB Atlas está temporariamente sem um primário gravável "
            "ou acabou de concluir uma eleição de nó. O sistema já tentou "
            "reconectar automaticamente."
        )
        st.caption(
            "Esse tipo de falha é transitório e não indica problema nos "
            "Secrets nem perda dos dados."
        )
        st.code(f"{type(exc).__name__}: {exc}")
        if st.button("Tentar reconectar agora", type="primary", use_container_width=True):
            clear_database_caches()
            st.rerun()
    else:
        st.code(f"{type(exc).__name__}: {exc}")
        st.info(
            "Para erros persistentes, revise os Secrets do Streamlit Cloud, "
            "a URI do MongoDB Atlas e as regras de Network Access."
        )
    st.stop()

appearance_obj = get_appearance_settings(db)

st.set_page_config(
    page_title=appearance_obj["system_name"],
    page_icon=page_icon_value(appearance_obj),
)

inject_css(appearance_obj)

settings_obj = get_settings()
if (
    st.session_state.get("authenticated")
    and session_expired(settings_obj.session_timeout_hours)
):
    logout()
    st.warning("Sua sessão expirou. Faça login novamente.")

if not st.session_state.get("authenticated"):
    render_login(db, appearance_obj)
    st.stop()

user = st.session_state.auth_user
touch_session()
sidebar_identity(user, appearance_obj)

nav: list[dict[str, str]] = []

if can(user, "dashboard.view"):
    nav.append(
        {"label": "Visão Geral", "key": "dashboard", "group": "Principal"}
    )

if can(user, "customers.view"):
    nav.append({"label": "Clientes", "key": "customers", "group": "Base"})
if can(user, "vehicles.view"):
    nav.append({"label": "Veículos", "key": "vehicles", "group": "Base"})

if can(user, "journey.view"):
    nav.append(
        {
            "label": "Jornada de Revisões",
            "key": "revisions",
            "group": "Operação",
        }
    )
if can(user, "loyalty.view"):
    nav.append(
        {
            "label": "Fidelidade / Recompra",
            "key": "loyalty",
            "group": "Operação",
        }
    )
if can(user, "journey.view"):
    nav.append(
        {
            "label": "Serviços / Manutenções",
            "key": "services",
            "group": "Operação",
        }
    )

if can(user, "import.execute"):
    nav.append(
        {
            "label": "Importar REL_VEICULOS",
            "key": "import",
            "group": "Administração",
        }
    )
if can(user, "users.manage"):
    nav.append(
        {
            "label": "Usuários e Acessos",
            "key": "users",
            "group": "Administração",
        }
    )
if can(user, "audit.view"):
    nav.append(
        {
            "label": "Auditoria",
            "key": "audit",
            "group": "Administração",
        }
    )
if can(user, "settings.manage"):
    nav.append(
        {
            "label": "Configurações",
            "key": "settings",
            "group": "Administração",
        }
    )
    nav.append(
        {
            "label": "Aparência",
            "key": "appearance",
            "group": "Administração",
        }
    )

nav.append(
    {
        "label": "Minha Conta",
        "key": "account",
        "group": "Conta",
    }
)

selected = sidebar_navigation(nav)

st.sidebar.divider()
if st.sidebar.button(
    "Sair",
    use_container_width=True,
    key="dh_logout",
):
    logout()
    st.rerun()

sidebar_footer()

if user.get("must_change_password") and selected != "account":
    st.warning(
        "Você está usando a senha inicial. "
        "Altere-a em **Minha Conta**."
    )

PAGES = {
    "dashboard": dashboard.render,
    "customers": customers.render,
    "vehicles": vehicles.render,
    "revisions": revisions.render,
    "loyalty": loyalty.render,
    "services": services.render,
    "import": import_page.render,
    "users": users.render,
    "audit": audit.render,
    "settings": settings.render,
    "appearance": appearance.render,
    "account": account.render,
}

PAGES[selected](db, user)
