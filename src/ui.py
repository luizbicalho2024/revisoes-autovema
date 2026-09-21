from __future__ import annotations

import html
from typing import Any

import streamlit as st

from .appearance import logo_data_uri, normalize_appearance
from .config import ROLES


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _initials(name: str) -> str:
    parts = [part for part in (name or "").replace("-", " ").split() if part]
    if not parts:
        return "DH"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def inject_css(appearance: dict[str, Any] | None = None) -> None:
    theme = normalize_appearance(appearance)
    pr, pg, pb = _rgb(theme["primary_color"])
    sr, sg, sb = _rgb(theme["sidebar_text_color"])
    radius = int(theme["border_radius"])
    sidebar_width = int(theme["sidebar_width"])

    st.markdown(
        f"""
        <style>
        :root,
        .stApp,
        [data-testid="stAppViewContainer"] {{
            --dh-primary: {theme["primary_color"]};
            --dh-secondary: {theme["secondary_color"]};
            --dh-accent: {theme["accent_color"]};
            --dh-bg: {theme["background_color"]};
            --dh-surface: {theme["surface_color"]};
            --dh-text: {theme["text_color"]};
            --dh-muted: {theme["muted_color"]};
            --dh-border: {theme["border_color"]};
            --dh-sidebar: {theme["sidebar_color"]};
            --dh-sidebar-text: {theme["sidebar_text_color"]};
            --dh-radius: {radius}px;

            --primary-color: {theme["primary_color"]} !important;
            --background-color: {theme["background_color"]} !important;
            --secondary-background-color: {theme["surface_color"]} !important;
            --text-color: {theme["text_color"]} !important;
        }}

        html, body, [class*="css"] {{
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}

        .stApp {{
            background: var(--dh-bg);
            color: var(--dh-text);
        }}

        .block-container {{
            padding-top: 1.35rem;
            padding-bottom: 3rem;
            max-width: 1540px;
        }}

        header[data-testid="stHeader"] {{
            background: color-mix(in srgb, var(--dh-bg) 92%, transparent);
            backdrop-filter: blur(8px);
        }}

        /* -------------------------------------------------
           SIDEBAR MINIMALISTA
        ------------------------------------------------- */
        [data-testid="stSidebar"] {{
            background: var(--dh-sidebar);
            border-right: 1px solid rgba({sr},{sg},{sb},.10);
            min-width: {sidebar_width}px;
            max-width: {sidebar_width}px;
            box-shadow: none;
        }}

        [data-testid="stSidebar"] > div:first-child {{
            padding-top: .55rem;
        }}

        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] .stCaption {{
            color: var(--dh-sidebar-text);
        }}

        [data-testid="stSidebar"] hr {{
            border-color: rgba({sr},{sg},{sb},.10);
            margin: .7rem 0;
        }}

        .dh-brand {{
            padding: .25rem .25rem .85rem;
        }}

        .dh-sidebar-logo {{
            display: flex;
            align-items: center;
            justify-content: flex-start;
            width: 100%;
            min-height: 50px;
            overflow: visible;
            background: transparent;
            border: 0;
        }}

        .dh-sidebar-logo img {{
            display: block;
            width: min(245px, 100%);
            height: auto;
            max-height: 50px;
            object-fit: contain;
            object-position: left center;
            background: transparent !important;
        }}

        .dh-brand-fallback {{
            display: flex;
            align-items: center;
            gap: .68rem;
            min-height: 50px;
        }}

        .dh-brand-mark {{
            width: 36px;
            height: 36px;
            min-width: 36px;
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--dh-primary);
            color: #fff;
            font-size: .82rem;
            font-weight: 800;
        }}

        .dh-brand-name {{
            color: var(--dh-sidebar-text);
            font-size: .98rem;
            line-height: 1.05;
            font-weight: 720;
            letter-spacing: -.012em;
        }}

        .dh-brand-subtitle {{
            margin-top: .22rem;
            color: rgba({sr},{sg},{sb},.52);
            font-size: .69rem;
            line-height: 1.15;
        }}

        .dh-sidebar-subtitle {{
            margin-top: .38rem;
            color: rgba({sr},{sg},{sb},.48);
            font-size: .68rem;
            line-height: 1.2;
        }}

        .dh-user-card {{
            padding: .68rem .25rem .74rem;
            margin-bottom: .2rem;
            border-top: 1px solid rgba({sr},{sg},{sb},.09);
            border-bottom: 1px solid rgba({sr},{sg},{sb},.09);
            background: transparent;
        }}

        .dh-user-name {{
            color: var(--dh-sidebar-text);
            font-weight: 620;
            font-size: .82rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .dh-user-meta,
        .dh-user-scope {{
            color: rgba({sr},{sg},{sb},.48);
            font-size: .66rem;
            margin-top: .14rem;
            line-height: 1.22;
            overflow-wrap: anywhere;
        }}

        .dh-nav-section {{
            color: rgba({sr},{sg},{sb},.36);
            font-size: .60rem;
            font-weight: 720;
            letter-spacing: .11em;
            text-transform: uppercase;
            margin: .86rem .62rem .26rem;
        }}

        .dh-nav-active {{
            min-height: 2.35rem;
            display: flex;
            align-items: center;
            gap: .58rem;
            margin: .03rem 0;
            padding: .48rem .66rem;
            border-radius: max(7px, calc(var(--dh-radius) - 4px));
            color: var(--dh-sidebar-text);
            font-size: .82rem;
            font-weight: 650;
            background: rgba({pr},{pg},{pb},.11);
            border-left: 2px solid var(--dh-primary);
        }}

        .dh-nav-dot {{
            width: 4px;
            height: 4px;
            border-radius: 50%;
            background: var(--dh-primary);
        }}

        [data-testid="stSidebar"] div.stButton > button {{
            width: 100%;
            min-height: 2.35rem;
            justify-content: flex-start;
            border-radius: max(7px, calc(var(--dh-radius) - 4px));
            border: 0 !important;
            background: transparent !important;
            color: var(--dh-sidebar-text) !important;
            font-size: .82rem;
            font-weight: 520;
            padding-left: .66rem;
            box-shadow: none !important;
            transition: background .14s ease;
        }}

        [data-testid="stSidebar"] div.stButton > button:hover {{
            background: rgba({sr},{sg},{sb},.055) !important;
            transform: none;
        }}

        .dh-sidebar-footer {{
            color: rgba({sr},{sg},{sb},.30);
            text-align: left;
            font-size: .60rem;
            padding: .2rem .25rem .45rem;
        }}

        /* -------------------------------------------------
           COMPONENTES GLOBAIS
        ------------------------------------------------- */
        [data-testid="stMetric"] {{
            background: var(--dh-surface);
            border: 1px solid var(--dh-border);
            padding: .95rem 1rem;
            border-radius: var(--dh-radius);
            box-shadow: 0 2px 8px rgba(16,24,40,.025);
        }}

        [data-testid="stMetric"] label {{
            color: var(--dh-muted) !important;
        }}

        [data-testid="stMetricValue"] {{
            color: var(--dh-text);
            font-weight: 740;
        }}

        div[data-testid="stForm"],
        [data-testid="stExpander"] {{
            background: var(--dh-surface);
            border: 1px solid var(--dh-border);
            border-radius: var(--dh-radius);
        }}

        div[data-testid="stForm"] {{
            padding: 1rem;
        }}

        /* Botões */
        button,
        div.stButton > button,
        div.stDownloadButton > button,
        div.stFormSubmitButton > button {{
            border-radius: max(7px, calc(var(--dh-radius) - 3px)) !important;
        }}

        [data-testid="stBaseButton-primary"],
        div.stButton > button[kind="primary"],
        div.stFormSubmitButton > button[kind="primary"] {{
            background: var(--dh-primary) !important;
            border-color: var(--dh-primary) !important;
            color: #fff !important;
            box-shadow: none !important;
        }}

        [data-testid="stBaseButton-primary"]:hover,
        div.stButton > button[kind="primary"]:hover,
        div.stFormSubmitButton > button[kind="primary"]:hover {{
            filter: brightness(.93);
        }}

        [data-testid="stBaseButton-secondary"],
        div.stButton > button[kind="secondary"],
        div.stDownloadButton > button {{
            background: var(--dh-surface) !important;
            color: var(--dh-text) !important;
            border-color: var(--dh-border) !important;
            box-shadow: none !important;
        }}

        [data-testid="stBaseButton-secondary"]:hover,
        div.stButton > button[kind="secondary"]:hover,
        div.stDownloadButton > button:hover {{
            border-color: var(--dh-primary) !important;
            color: var(--dh-primary) !important;
        }}

        /* Inputs / selects */
        input,
        textarea {{
            color: var(--dh-text) !important;
            caret-color: var(--dh-primary) !important;
        }}

        [data-baseweb="input"] > div,
        [data-baseweb="textarea"] > div,
        [data-baseweb="select"] > div {{
            background: var(--dh-surface) !important;
            border-color: var(--dh-border) !important;
        }}

        [data-baseweb="input"] > div:focus-within,
        [data-baseweb="textarea"] > div:focus-within,
        [data-baseweb="select"] > div:focus-within {{
            border-color: var(--dh-primary) !important;
            box-shadow: 0 0 0 1px var(--dh-primary) !important;
        }}

        /* Checkboxes / radios / toggles / sliders */
        input[type="checkbox"],
        input[type="radio"],
        input[type="range"] {{
            accent-color: var(--dh-primary) !important;
        }}

        [data-testid="stCheckbox"] svg,
        [data-testid="stRadio"] svg {{
            color: var(--dh-primary);
        }}

        [data-testid="stSlider"] [role="slider"] {{
            background: var(--dh-primary) !important;
            border-color: var(--dh-primary) !important;
        }}

        [data-testid="stToggle"] [role="switch"][aria-checked="true"] {{
            background: var(--dh-primary) !important;
        }}

        /* Tabs */
        [data-baseweb="tab-list"] [aria-selected="true"] {{
            color: var(--dh-primary) !important;
        }}

        [data-baseweb="tab-highlight"] {{
            background-color: var(--dh-primary) !important;
        }}

        /* Links e progresso */
        a {{
            color: var(--dh-primary);
        }}

        [data-testid="stProgressBar"] > div > div > div {{
            background-color: var(--dh-primary) !important;
        }}

        .dh-title {{
            font-size: 1.78rem;
            font-weight: 760;
            letter-spacing: -.032em;
            line-height: 1.16;
            color: var(--dh-text);
        }}

        .dh-subtitle {{
            color: var(--dh-muted);
            margin-top: .28rem;
            margin-bottom: 1.2rem;
        }}

        .dh-card {{
            background: var(--dh-surface);
            border: 1px solid var(--dh-border);
            border-radius: var(--dh-radius);
            padding: 1rem;
        }}

        .dh-chip {{
            display: inline-block;
            padding: 3px 9px;
            border-radius: 999px;
            background: rgba({pr},{pg},{pb},.09);
            color: var(--dh-primary);
            font-size: .76rem;
            margin-right: 4px;
        }}

        .dh-status-ok {{ color: #087F5B; font-weight: 650; }}
        .dh-status-warn {{ color: #B45309; font-weight: 650; }}
        .dh-status-bad {{ color: #B42318; font-weight: 650; }}

        /* -------------------------------------------------
           LOGIN - LOGO HORIZONTAL, SEM FUNDO
        ------------------------------------------------- */
        .dh-login-wrap {{
            text-align: center;
            margin-top: 6vh;
            margin-bottom: 1.1rem;
        }}

        .dh-login-logo {{
            display: flex;
            justify-content: center;
            align-items: center;
            width: 100%;
            margin: 0 auto .85rem;
            background: transparent;
        }}

        .dh-login-logo img {{
            display: block;
            width: min(245px, 100%);
            max-width: 245px;
            height: auto;
            max-height: 50px;
            object-fit: contain;
            background: transparent !important;
        }}

        .dh-login-mark {{
            width: 54px;
            height: 54px;
            margin: 0 auto .8rem;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            background: var(--dh-primary);
            font-size: 1rem;
            font-weight: 800;
        }}

        .dh-login-brand {{
            font-size: 1.85rem;
            font-weight: 780;
            letter-spacing: -.032em;
            color: var(--dh-text);
        }}

        .dh-login-subtitle {{
            font-size: .92rem;
            color: var(--dh-muted);
            margin-top: .22rem;
        }}

        .dh-preview {{
            padding: 1rem;
            min-height: 155px;
            border-radius: var(--dh-radius);
            border: 1px solid var(--dh-border);
            background: var(--dh-bg);
        }}

        .dh-preview-card {{
            background: var(--dh-surface);
            color: var(--dh-text);
            border: 1px solid var(--dh-border);
            border-radius: var(--dh-radius);
            padding: 1rem;
        }}

        .dh-preview-bar {{
            width: 44px;
            height: 4px;
            border-radius: 99px;
            background: var(--dh-primary);
            margin-bottom: .72rem;
        }}

        .dh-preview-muted {{
            color: var(--dh-muted);
            font-size: .8rem;
        }}

        @media (max-width: 900px) {{
            [data-testid="stSidebar"] {{
                min-width: min({sidebar_width}px, 86vw);
                max-width: min({sidebar_width}px, 86vw);
            }}
        }}

        /* HOTFIX_HEADER_V62 */
        .block-container {{
            padding-top: 3.75rem !important;
        }}

        header[data-testid="stHeader"] {{
            background: transparent !important;
            backdrop-filter: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"],
        [data-testid="stDecoration"] {{
            display: none !important;
        }}

        @media (max-width: 900px) {{
            .block-container {{
                padding-top: 4rem !important;
            }}
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )


def login_identity(appearance: dict[str, Any] | None = None) -> None:
    theme = normalize_appearance(appearance)
    logo_uri = logo_data_uri(appearance)

    if logo_uri:
        mark = f'<div class="dh-login-logo"><img src="{logo_uri}" alt="Logo"></div>'
        title = ""
    else:
        mark = (
            f'<div class="dh-login-mark">'
            f'{html.escape(_initials(theme["system_name"]))}'
            f"</div>"
        )
        title = f'<div class="dh-login-brand">{html.escape(theme["system_name"])}</div>'

    st.markdown(
        f"""
        <div class="dh-login-wrap">
          {mark}
          {title}
          <div class="dh-login-subtitle">{html.escape(theme["system_subtitle"])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="dh-title">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f'<div class="dh-subtitle">{html.escape(subtitle)}</div>',
            unsafe_allow_html=True,
        )


def sidebar_identity(
    user: dict[str, Any],
    appearance: dict[str, Any] | None = None,
) -> None:
    theme = normalize_appearance(appearance)
    logo_uri = logo_data_uri(appearance)

    if logo_uri:
        brand = (
            f'<div class="dh-sidebar-logo">'
            f'<img src="{logo_uri}" alt="{html.escape(theme["system_name"])}">'
            f"</div>"
            f'<div class="dh-sidebar-subtitle">{html.escape(theme["system_subtitle"])}</div>'
        )
    else:
        brand = f"""
        <div class="dh-brand-fallback">
          <div class="dh-brand-mark">{html.escape(_initials(theme["system_name"]))}</div>
          <div>
            <div class="dh-brand-name">{html.escape(theme["system_name"])}</div>
            <div class="dh-brand-subtitle">{html.escape(theme["system_subtitle"])}</div>
          </div>
        </div>
        """

    st.sidebar.markdown(
        f'<div class="dh-brand">{brand}</div>',
        unsafe_allow_html=True,
    )

    role = ROLES.get(user.get("role"), user.get("role") or "")
    companies = user.get("company_codes", []) or []
    scope = ", ".join(map(str, companies)) if companies else "Todas as empresas"
    scope_line = (
        f'<div class="dh-user-scope">Escopo: {html.escape(scope)}</div>'
        if theme.get("show_scope", True)
        else ""
    )

    st.sidebar.markdown(
        f"""
        <div class="dh-user-card">
          <div class="dh-user-name">{html.escape(str(user.get("name") or "Usuário"))}</div>
          <div class="dh-user-meta">{html.escape(str(role))} · {html.escape(str(user.get("email") or ""))}</div>
          {scope_line}
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_navigation(items: list[dict[str, str]]) -> str:
    if not items:
        return ""

    allowed = {item["key"] for item in items}
    selected = st.session_state.get("dh_active_page")
    if selected not in allowed:
        selected = items[0]["key"]
        st.session_state["dh_active_page"] = selected

    groups: list[str] = []
    for item in items:
        group = item.get("group") or "Navegação"
        if group not in groups:
            groups.append(group)

    for group in groups:
        st.sidebar.markdown(
            f'<div class="dh-nav-section">{html.escape(group)}</div>',
            unsafe_allow_html=True,
        )

        for item in [x for x in items if (x.get("group") or "Navegação") == group]:
            if item["key"] == selected:
                st.sidebar.markdown(
                    f"""
                    <div class="dh-nav-active">
                      <span class="dh-nav-dot"></span>
                      {html.escape(item["label"])}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                if st.sidebar.button(
                    item["label"],
                    key=f"dh_nav_{item['key']}",
                    use_container_width=True,
                ):
                    st.session_state["dh_active_page"] = item["key"]
                    st.rerun()

    return str(st.session_state["dh_active_page"])


def sidebar_footer() -> None:
    st.sidebar.markdown(
        '<div class="dh-sidebar-footer">Dealer Hub · Ambiente corporativo</div>',
        unsafe_allow_html=True,
    )
