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
        :root {{
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
        }}

        html, body, [class*="css"] {{
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}

        .stApp {{
            background:
                radial-gradient(circle at 94% -8%, rgba({pr},{pg},{pb},.055), transparent 29rem),
                var(--dh-bg);
            color: var(--dh-text);
        }}

        .block-container {{
            padding-top: 1.45rem;
            padding-bottom: 3rem;
            max-width: 1540px;
        }}

        header[data-testid="stHeader"] {{
            background: transparent;
        }}

        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, var(--dh-sidebar) 0%, var(--dh-secondary) 145%);
            border-right: 1px solid rgba(255,255,255,.07);
            min-width: {sidebar_width}px;
            max-width: {sidebar_width}px;
            box-shadow: 18px 0 44px rgba(16,24,40,.08);
        }}

        [data-testid="stSidebar"] > div:first-child {{
            padding-top: .7rem;
        }}

        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] .stCaption {{
            color: var(--dh-sidebar-text);
        }}

        [data-testid="stSidebar"] hr {{
            border-color: rgba(255,255,255,.09);
            margin: .8rem 0;
        }}

        .dh-brand-card {{
            margin: .1rem 0 .72rem;
            padding: .95rem;
            border-radius: calc(var(--dh-radius) + 2px);
            border: 1px solid rgba(255,255,255,.10);
            background:
                radial-gradient(circle at 100% 0%, rgba({pr},{pg},{pb},.44), transparent 65%),
                rgba(255,255,255,.05);
            box-shadow: 0 16px 34px rgba(0,0,0,.10);
        }}

        .dh-brand-row {{
            display: flex;
            align-items: center;
            gap: .76rem;
        }}

        .dh-logo,
        .dh-brand-mark {{
            width: 48px;
            height: 48px;
            min-width: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}

        .dh-logo {{
            background: #fff;
            border: 1px solid rgba(255,255,255,.25);
        }}

        .dh-logo img {{
            max-width: 42px;
            max-height: 42px;
            object-fit: contain;
        }}

        .dh-brand-mark {{
            background: var(--dh-primary);
            color: #fff;
            font-weight: 850;
            letter-spacing: -.02em;
            box-shadow: 0 8px 20px rgba({pr},{pg},{pb},.25);
        }}

        .dh-brand-name {{
            color: var(--dh-sidebar-text);
            font-size: 1.02rem;
            line-height: 1.05;
            font-weight: 780;
            letter-spacing: -.015em;
        }}

        .dh-brand-subtitle {{
            margin-top: .3rem;
            color: rgba({sr},{sg},{sb},.65);
            font-size: .73rem;
            line-height: 1.15;
        }}

        .dh-user-card {{
            padding: .8rem .88rem;
            margin-bottom: .72rem;
            border-radius: var(--dh-radius);
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.07);
        }}

        .dh-user-name {{
            color: var(--dh-sidebar-text);
            font-weight: 690;
            font-size: .88rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .dh-user-meta,
        .dh-user-scope {{
            color: rgba({sr},{sg},{sb},.58);
            font-size: .69rem;
            margin-top: .19rem;
            line-height: 1.28;
            overflow-wrap: anywhere;
        }}

        .dh-nav-section {{
            color: rgba({sr},{sg},{sb},.43);
            font-size: .62rem;
            font-weight: 820;
            letter-spacing: .12em;
            text-transform: uppercase;
            margin: .95rem .72rem .32rem;
        }}

        .dh-nav-active {{
            min-height: 2.55rem;
            display: flex;
            align-items: center;
            gap: .64rem;
            margin: .08rem 0;
            padding: .54rem .78rem;
            border-radius: max(9px, calc(var(--dh-radius) - 3px));
            color: var(--dh-sidebar-text);
            font-size: .875rem;
            font-weight: 700;
            background: linear-gradient(
                90deg,
                rgba({pr},{pg},{pb},.31),
                rgba(255,255,255,.06)
            );
            border: 1px solid rgba({pr},{pg},{pb},.34);
            box-shadow: inset 3px 0 0 var(--dh-primary);
        }}

        .dh-nav-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--dh-accent);
            box-shadow: 0 0 0 4px rgba({pr},{pg},{pb},.11);
        }}

        [data-testid="stSidebar"] div.stButton > button {{
            width: 100%;
            min-height: 2.55rem;
            justify-content: flex-start;
            border-radius: max(9px, calc(var(--dh-radius) - 3px));
            border: 1px solid transparent !important;
            background: transparent !important;
            color: var(--dh-sidebar-text) !important;
            font-weight: 570;
            padding-left: .78rem;
            box-shadow: none !important;
            transition: background .16s ease, border-color .16s ease, transform .16s ease;
        }}

        [data-testid="stSidebar"] div.stButton > button:hover {{
            background: rgba(255,255,255,.065) !important;
            border-color: rgba(255,255,255,.075) !important;
            transform: translateX(2px);
        }}

        .dh-sidebar-footer {{
            color: rgba({sr},{sg},{sb},.38);
            text-align: center;
            font-size: .64rem;
            padding: .3rem .4rem .5rem;
        }}

        [data-testid="stMetric"] {{
            background: var(--dh-surface);
            border: 1px solid var(--dh-border);
            padding: 1rem 1.05rem;
            border-radius: var(--dh-radius);
            box-shadow: 0 5px 18px rgba(16,24,40,.035);
        }}

        [data-testid="stMetric"] label {{
            color: var(--dh-muted) !important;
        }}

        [data-testid="stMetricValue"] {{
            color: var(--dh-text);
            font-weight: 760;
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

        div.stButton > button,
        div.stDownloadButton > button,
        div.stFormSubmitButton > button {{
            border-radius: max(9px, calc(var(--dh-radius) - 3px));
        }}

        div.stButton > button[kind="primary"],
        div.stFormSubmitButton > button[kind="primary"] {{
            background: var(--dh-primary);
            border-color: var(--dh-primary);
            color: #fff;
        }}

        a {{
            color: var(--dh-primary);
        }}

        .dh-login-wrap {{
            text-align: center;
            margin-top: 6vh;
            margin-bottom: 1.2rem;
        }}

        .dh-login-logo,
        .dh-login-mark {{
            width: 76px;
            height: 76px;
            margin: 0 auto .88rem;
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            box-shadow: 0 14px 34px rgba(16,24,40,.10);
        }}

        .dh-login-logo {{
            background: #fff;
            border: 1px solid var(--dh-border);
        }}

        .dh-login-logo img {{
            max-width: 66px;
            max-height: 66px;
            object-fit: contain;
        }}

        .dh-login-mark {{
            color: #fff;
            background: linear-gradient(135deg, var(--dh-primary), var(--dh-secondary));
            font-size: 1.35rem;
            font-weight: 850;
        }}

        .dh-login-brand {{
            font-size: 2rem;
            font-weight: 820;
            letter-spacing: -.035em;
            color: var(--dh-text);
        }}

        .dh-login-subtitle {{
            font-size: .96rem;
            color: var(--dh-muted);
            margin-top: .25rem;
        }}

        .dh-title {{
            font-size: 1.85rem;
            font-weight: 790;
            letter-spacing: -.035em;
            line-height: 1.16;
            color: var(--dh-text);
        }}

        .dh-subtitle {{
            color: var(--dh-muted);
            margin-top: .32rem;
            margin-bottom: 1.3rem;
        }}

        .dh-card {{
            background: var(--dh-surface);
            border: 1px solid var(--dh-border);
            border-radius: var(--dh-radius);
            padding: 1rem;
            box-shadow: 0 5px 18px rgba(16,24,40,.035);
        }}

        .dh-chip {{
            display: inline-block;
            padding: 3px 9px;
            border-radius: 999px;
            background: rgba({pr},{pg},{pb},.10);
            color: var(--dh-primary);
            font-size: .78rem;
            margin-right: 4px;
        }}

        .dh-status-ok {{ color: #087F5B; font-weight: 650; }}
        .dh-status-warn {{ color: #B45309; font-weight: 650; }}
        .dh-status-bad {{ color: #B42318; font-weight: 650; }}

        .dh-preview {{
            padding: 1rem;
            min-height: 160px;
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
            box-shadow: 0 8px 24px rgba(16,24,40,.055);
        }}

        .dh-preview-bar {{
            width: 46px;
            height: 5px;
            border-radius: 99px;
            background: var(--dh-primary);
            margin-bottom: .75rem;
        }}

        .dh-preview-muted {{
            color: var(--dh-muted);
            font-size: .82rem;
        }}

        @media (max-width: 900px) {{
            [data-testid="stSidebar"] {{
                min-width: min({sidebar_width}px, 86vw);
                max-width: min({sidebar_width}px, 86vw);
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
    else:
        mark = (
            f'<div class="dh-login-mark">'
            f'{html.escape(_initials(theme["system_name"]))}'
            f"</div>"
        )

    st.markdown(
        f"""
        <div class="dh-login-wrap">
          {mark}
          <div class="dh-login-brand">{html.escape(theme["system_name"])}</div>
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
        mark = f'<div class="dh-logo"><img src="{logo_uri}" alt="Logo"></div>'
    else:
        mark = (
            f'<div class="dh-brand-mark">'
            f'{html.escape(_initials(theme["system_name"]))}'
            f"</div>"
        )

    st.sidebar.markdown(
        f"""
        <div class="dh-brand-card">
          <div class="dh-brand-row">
            {mark}
            <div>
              <div class="dh-brand-name">{html.escape(theme["system_name"])}</div>
              <div class="dh-brand-subtitle">{html.escape(theme["system_subtitle"])}</div>
            </div>
          </div>
        </div>
        """,
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
