from __future__ import annotations

import html
from typing import Any

import streamlit as st

from .config import APP_SHORT_NAME, ROLES


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.45rem; padding-bottom: 2rem; max-width: 1500px;}
        [data-testid="stSidebar"] {border-right: 1px solid #E5E7EB;}
        [data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #E6E8EC; padding: 16px; border-radius: 14px;}
        .dh-login-wrap {text-align:center; margin-top: 7vh; margin-bottom: 1.1rem;}
        .dh-login-brand {font-size: 2.15rem; font-weight: 800; letter-spacing: .08em; color:#B5121B;}
        .dh-login-subtitle {font-size: 1rem; color:#6B7280; margin-top:.2rem;}
        .dh-title {font-size:1.8rem; font-weight:780; line-height:1.2; color:#17202A;}
        .dh-subtitle {color:#6B7280; margin-top:.25rem; margin-bottom:1.25rem;}
        .dh-card {background:#FFF; border:1px solid #E6E8EC; border-radius:14px; padding:16px;}
        .dh-chip {display:inline-block; padding:3px 9px; border-radius:999px; background:#F3F4F6; font-size:.78rem; color:#4B5563; margin-right:4px;}
        .dh-status-ok {color:#087F5B; font-weight:650;}
        .dh-status-warn {color:#B45309; font-weight:650;}
        .dh-status-bad {color:#B42318; font-weight:650;}
        div.stButton > button {border-radius:10px;}
        div[data-testid="stForm"] {background:#FFF; border:1px solid #E6E8EC; border-radius:14px; padding:1rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="dh-title">{html.escape(title)}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="dh-subtitle">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def sidebar_identity(user: dict[str, Any]) -> None:
    st.sidebar.markdown(f"### {APP_SHORT_NAME}")
    st.sidebar.caption("Revisões Autovema")
    st.sidebar.divider()
    st.sidebar.markdown(f"**{user.get('name', 'Usuário')}**")
    st.sidebar.caption(f"{ROLES.get(user.get('role'), user.get('role'))} • {user.get('email', '')}")
    companies = user.get("company_codes", []) or []
    st.sidebar.caption("Escopo: " + (", ".join(map(str, companies)) if companies else "Todas as empresas"))
