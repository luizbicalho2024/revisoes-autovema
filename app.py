from __future__ import annotations

import streamlit as st

from src.auth import render_login
from src.config import APP_NAME, get_settings
from src.db import bootstrap_database
from src.security import can, initialize_session, logout, session_expired, touch_session
from src.ui import inject_css, sidebar_identity
from src.pages import account, audit, customers, dashboard, import_page, loyalty, revisions, settings, users, vehicles


st.set_page_config(
    page_title=APP_NAME,
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
initialize_session()

try:
    db, _bootstrap_message = bootstrap_database()
except Exception as exc:
    st.error("Não foi possível inicializar o Dealer Hub.")
    st.code(str(exc))
    st.info("Revise os Secrets do Streamlit Cloud e a liberação de rede do MongoDB Atlas.")
    st.stop()

settings_obj = get_settings()
if st.session_state.get("authenticated") and session_expired(settings_obj.session_timeout_hours):
    logout()
    st.warning("Sua sessão expirou. Faça login novamente.")

if not st.session_state.get("authenticated"):
    render_login(db)
    st.stop()

user = st.session_state.auth_user
touch_session()
sidebar_identity(user)

nav = []
if can(user, "dashboard.view"):
    nav.append(("Visão Geral", "dashboard"))
if can(user, "customers.view"):
    nav.append(("Clientes", "customers"))
if can(user, "vehicles.view"):
    nav.append(("Veículos", "vehicles"))
if can(user, "journey.view"):
    nav.append(("Jornada de Revisões", "revisions"))
if can(user, "loyalty.view"):
    nav.append(("Fidelidade / Recompra", "loyalty"))
if can(user, "import.execute"):
    nav.append(("Importar REL_VEICULOS", "import"))
if can(user, "users.manage"):
    nav.append(("Usuários e Acessos", "users"))
if can(user, "audit.view"):
    nav.append(("Auditoria", "audit"))
if can(user, "settings.manage"):
    nav.append(("Configurações", "settings"))
nav.append(("Minha Conta", "account"))

labels = [item[0] for item in nav]
selected_label = st.sidebar.radio("Navegação", labels, label_visibility="collapsed")
selected = dict(nav)[selected_label]

st.sidebar.divider()
if st.sidebar.button("Sair", use_container_width=True):
    logout()
    st.rerun()

if user.get("must_change_password") and selected != "account":
    st.warning("Você está usando a senha inicial. Altere-a em **Minha Conta**.")

PAGES = {
    "dashboard": dashboard.render,
    "customers": customers.render,
    "vehicles": vehicles.render,
    "revisions": revisions.render,
    "loyalty": loyalty.render,
    "import": import_page.render,
    "users": users.render,
    "audit": audit.render,
    "settings": settings.render,
    "account": account.render,
}

PAGES[selected](db, user)
