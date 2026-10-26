from __future__ import annotations

import html
from typing import Any

import streamlit as st

from .appearance import logo_data_uri, normalize_appearance
from .config import ROLES


NAV_ICONS = {
    "dashboard": ":material/dashboard:",
    "customers": ":material/groups:",
    "vehicles": ":material/directions_car:",
    "revisions": ":material/route:",
    "loyalty": ":material/verified:",
    "services": ":material/build:",
    "import": ":material/upload_file:",
    "users": ":material/manage_accounts:",
    "audit": ":material/fact_check:",
    "settings": ":material/settings:",
    "appearance": ":material/palette:",
    "account": ":material/account_circle:",
}

# Vetores locais: dispensam fontes ou bibliotecas externas para o item ativo.
NAV_SVG_PATHS = {
    "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "customers": '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2"/><path d="M17 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5v1"/>',
    "vehicles": '<path d="M5 17H3v-5l3-6h12l3 6v5h-2"/><path d="M5 17h14M3 12h18"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>',
    "revisions": '<circle cx="5" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 5h7a5 5 0 0 1 0 10H9a4 4 0 0 0 0 8h8"/>',
    "loyalty": '<path d="m12 2 3 6 6.5 1-4.7 4.6 1.1 6.4L12 17l-5.9 3 1.1-6.4L2.5 9 9 8z"/>',
    "services": '<path d="M14 7a5 5 0 0 1-7 7l-4 4a2 2 0 0 0 3 3l4-4a5 5 0 0 0 7-7l-3 3-3-3z"/>',
    "import": '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 9h5m-2.5-2.5v5"/>',
    "audit": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6m-6 4 2 2 4-4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M19 5l-2 2M7 17l-2 2"/>',
    "appearance": '<path d="M12 3a9 9 0 1 0 9 9c0-2-2-3-4-3h-2a2 2 0 0 1-2-2V5a2 2 0 0 0-1-2z"/><circle cx="7" cy="12" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="17" cy="13" r="1"/>',
    "account": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
}


def _nav_icon_svg(key: str) -> str:
    path = NAV_SVG_PATHS.get(key, NAV_SVG_PATHS["dashboard"])
    return (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        + path
        + '</svg>'
    )



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



def _nav_icon(key: str) -> str:
    return NAV_ICONS.get(key, "•")



def inject_css(appearance: dict[str, Any] | None = None) -> None:
    theme = normalize_appearance(appearance)
    pr, pg, pb = _rgb(theme["primary_color"])
    sr, sg, sb = _rgb(theme["sidebar_text_color"])
    tr, tg, tb = _rgb(theme["text_color"])
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
            background:
                radial-gradient(circle at top right, rgba({pr},{pg},{pb},.055), transparent 28%),
                linear-gradient(180deg, var(--dh-bg), var(--dh-bg));
            color: var(--dh-text);
        }}

        .block-container {{
            padding-top: 3.9rem !important;
            padding-bottom: 3rem;
            max-width: 1540px;
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

        /* -------------------------------------------------
           SIDEBAR - CONTROLE RESILIENTE EM VERSOES RECENTES
           No desktop usamos initial_sidebar_state="locked".
           Em viewports moveis o controle nativo continua acessivel.
        ------------------------------------------------- */
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] {{
            position: fixed !important;
            top: .85rem !important;
            left: .92rem !important;
            z-index: 100005 !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }}

        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="collapsedControl"] button,
        [data-testid="stSidebarCollapseButton"] button {{
            min-height: 2.6rem !important;
            min-width: 2.6rem !important;
            border-radius: 12px !important;
            border: 1px solid rgba(255,255,255,.14) !important;
            background: #111827 !important;
            color: #F8FAFC !important;
            box-shadow: 0 10px 24px rgba(2, 6, 23, .22) !important;
            visibility: visible !important;
            pointer-events: auto !important;
        }}

        [data-testid="stSidebarCollapsedControl"] button:hover,
        [data-testid="collapsedControl"] button:hover,
        [data-testid="stSidebarCollapseButton"] button:hover {{
            background: #1F2937 !important;
            border-color: var(--dh-primary) !important;
        }}

        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="collapsedControl"] svg,
        [data-testid="stSidebarCollapseButton"] svg {{
            color: #F8FAFC !important;
            fill: none;
        }}

        header[data-testid="stHeader"] {{
            z-index: 100001 !important;
            pointer-events: auto !important;
        }}

        /* Barra de navegacao acessivel mesmo sem a barra lateral. */
        .dh-nav-top-title {{
            color: var(--dh-text);
            font-size: .75rem;
            font-weight: 730;
            text-transform: uppercase;
            letter-spacing: .09em;
        }}

        .dh-nav-top-subtitle {{
            color: var(--dh-muted);
            font-size: .72rem;
            margin-top: .15rem;
        }}

        .st-key-dh_main_nav_bar {{
            padding: .68rem .85rem;
            margin: 0 0 1.15rem;
            border: 1px solid var(--dh-border);
            border-radius: calc(var(--dh-radius) + 4px);
            background: var(--dh-surface);
            box-shadow: 0 6px 18px rgba({tr},{tg},{tb}, .035);
        }}

        .st-key-dh_main_nav_bar button {{
            font-weight: 650 !important;
            min-height: 2.55rem;
        }}

        .st-key-dh_main_nav_bar [data-testid="stPopover"] > button {{
            background: var(--dh-sidebar) !important;
            border: 1px solid var(--dh-sidebar) !important;
            color: var(--dh-sidebar-text) !important;
            box-shadow: none !important;
        }}

        .st-key-dh_main_nav_bar [data-testid="stPopover"] > button:hover {{
            border-color: var(--dh-primary) !important;
            background: var(--dh-sidebar) !important;
        }}

        /* -------------------------------------------------
           SIDEBAR - VISUAL MODERNO
        ------------------------------------------------- */
        section[data-testid="stSidebar"] {{
            background:
                radial-gradient(circle at top left, rgba({pr},{pg},{pb}, .15), transparent 28%),
                linear-gradient(180deg, color-mix(in srgb, var(--dh-sidebar) 94%, #0B1220 6%), var(--dh-sidebar));
            border-right: 1px solid rgba({sr},{sg},{sb}, .08);
            min-width: {sidebar_width}px;
            max-width: {sidebar_width}px;
            box-shadow: 14px 0 36px rgba(2, 6, 23, .10);
        }}

        section[data-testid="stSidebar"] > div:first-child {{
            padding-top: .55rem;
            padding-left: .9rem;
            padding-right: .9rem;
        }}

        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] label {{
            color: var(--dh-sidebar-text);
        }}

        [data-testid="stSidebar"] hr {{
            border-color: rgba({sr},{sg},{sb}, .08);
            margin: .7rem 0;
        }}

        .dh-brand {{
            position: relative;
            margin: .15rem 0 .9rem;
            padding: .82rem .88rem 1rem;
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,.08);
            background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.025));
            box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
        }}

        .dh-brand-top {{
            display: inline-flex;
            align-items: center;
            gap: .45rem;
            padding: .22rem .6rem;
            margin-bottom: .72rem;
            border-radius: 999px;
            background: rgba({pr},{pg},{pb}, .18);
            color: #fff;
            font-size: .68rem;
            font-weight: 700;
            letter-spacing: .04em;
            text-transform: uppercase;
        }}

        .dh-sidebar-logo {{
            display: flex;
            align-items: center;
            justify-content: flex-start;
            width: 100%;
            min-height: 52px;
            overflow: visible;
            background: transparent;
            border: 0;
        }}

        .dh-sidebar-logo img {{
            display: block;
            width: min(228px, 100%);
            height: auto;
            max-height: 52px;
            object-fit: contain;
            object-position: left center;
            background: transparent !important;
        }}

        .dh-brand-fallback {{
            display: flex;
            align-items: center;
            gap: .78rem;
            min-height: 52px;
        }}

        .dh-brand-mark {{
            width: 42px;
            height: 42px;
            min-width: 42px;
            border-radius: 13px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, var(--dh-primary), color-mix(in srgb, var(--dh-primary) 74%, white 26%));
            color: #fff;
            font-size: .88rem;
            font-weight: 800;
            box-shadow: 0 10px 24px rgba({pr},{pg},{pb}, .26);
        }}

        .dh-brand-name {{
            color: var(--dh-sidebar-text);
            font-size: 1.02rem;
            line-height: 1.05;
            font-weight: 760;
            letter-spacing: -.015em;
        }}

        .dh-brand-subtitle,
        .dh-sidebar-subtitle {{
            margin-top: .32rem;
            color: rgba({sr},{sg},{sb}, .64);
            font-size: .72rem;
            line-height: 1.25;
        }}

        .dh-user-card {{
            margin-bottom: .5rem;
            padding: .82rem .85rem;
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,.08);
            background: rgba(255,255,255,.035);
        }}

        .dh-user-head {{
            display: flex;
            align-items: center;
            gap: .75rem;
        }}

        .dh-user-avatar {{
            width: 40px;
            height: 40px;
            min-width: 40px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba({pr},{pg},{pb}, .18);
            color: #fff;
            font-size: .86rem;
            font-weight: 800;
        }}

        .dh-user-name {{
            color: var(--dh-sidebar-text);
            font-weight: 680;
            font-size: .86rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .dh-user-meta,
        .dh-user-scope {{
            color: rgba({sr},{sg},{sb}, .60);
            font-size: .68rem;
            margin-top: .18rem;
            line-height: 1.24;
            overflow-wrap: anywhere;
        }}

        .dh-nav-wrap {{
            margin-top: .65rem;
        }}

        .dh-nav-section {{
            color: rgba({sr},{sg},{sb}, .42);
            font-size: .62rem;
            font-weight: 760;
            letter-spacing: .12em;
            text-transform: uppercase;
            margin: 1rem .52rem .36rem;
        }}

        .dh-nav-active {{
            min-height: 2.65rem;
            display: flex;
            align-items: center;
            gap: .75rem;
            margin: .12rem 0;
            padding: .62rem .76rem;
            border-radius: 14px;
            color: #FFFFFF;
            font-size: .84rem;
            font-weight: 690;
            background: linear-gradient(90deg, rgba({pr},{pg},{pb}, .94), rgba({pr},{pg},{pb}, .74));
            border: 1px solid rgba({pr},{pg},{pb}, .72);
            box-shadow: 0 14px 28px rgba({pr},{pg},{pb}, .22);
        }}

        .dh-nav-icon {{
            width: 1.58rem;
            min-width: 1.58rem;
            height: 1.58rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            background: rgba(255,255,255,.16);
            font-size: .84rem;
            line-height: 1;
        }}

        [data-testid="stSidebar"] div.stButton {{
            margin: .18rem 0;
        }}

        [data-testid="stSidebar"] div.stButton > button {{
            width: 100%;
            min-height: 2.62rem;
            justify-content: flex-start;
            border-radius: 14px;
            border: 1px solid transparent !important;
            background: transparent !important;
            color: var(--dh-sidebar-text) !important;
            font-size: .84rem;
            font-weight: 540;
            padding-left: .76rem;
            box-shadow: none !important;
            transition: background .14s ease, border-color .14s ease, transform .14s ease;
        }}

        [data-testid="stSidebar"] div.stButton > button:hover {{
            background: rgba(255,255,255,.055) !important;
            border-color: rgba(255,255,255,.08) !important;
            transform: translateX(1px);
        }}

        [data-testid="stSidebar"] div.stButton > button:focus {{
            outline: none !important;
            border-color: rgba({pr},{pg},{pb}, .46) !important;
        }}

        .dh-quick-note {{
            margin-top: .7rem;
            padding: .78rem .85rem;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,.08);
            background: rgba(255,255,255,.03);
            color: rgba({sr},{sg},{sb}, .72);
            font-size: .70rem;
            line-height: 1.35;
        }}

        .dh-sidebar-footer {{
            margin-top: .3rem;
            color: rgba({sr},{sg},{sb}, .38);
            text-align: left;
            font-size: .64rem;
            padding: .2rem .35rem .55rem;
        }}

        /* -------------------------------------------------
           COMPONENTES GLOBAIS
        ------------------------------------------------- */
        [data-testid="stMetric"] {{
            background: var(--dh-surface);
            border: 1px solid var(--dh-border);
            padding: .95rem 1rem;
            border-radius: calc(var(--dh-radius) + 2px);
            box-shadow: 0 12px 28px rgba({tr},{tg},{tb}, .04);
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
            border-radius: calc(var(--dh-radius) + 2px);
        }}

        div[data-testid="stForm"] {{
            padding: 1rem;
            box-shadow: 0 10px 26px rgba({tr},{tg},{tb}, .03);
        }}

        button,
        div.stButton > button,
        div.stDownloadButton > button,
        div.stFormSubmitButton > button {{
            border-radius: max(10px, calc(var(--dh-radius) - 2px)) !important;
        }}

        [data-testid="stBaseButton-primary"],
        div.stButton > button[kind="primary"],
        div.stFormSubmitButton > button[kind="primary"] {{
            background: linear-gradient(90deg, var(--dh-primary), color-mix(in srgb, var(--dh-primary) 84%, white 16%)) !important;
            border-color: var(--dh-primary) !important;
            color: #fff !important;
            box-shadow: 0 10px 24px rgba({pr},{pg},{pb}, .18) !important;
        }}

        [data-testid="stBaseButton-primary"]:hover,
        div.stButton > button[kind="primary"]:hover,
        div.stFormSubmitButton > button[kind="primary"]:hover {{
            filter: brightness(.96);
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
            border-radius: max(10px, calc(var(--dh-radius) - 2px)) !important;
        }}

        [data-baseweb="input"] > div:focus-within,
        [data-baseweb="textarea"] > div:focus-within,
        [data-baseweb="select"] > div:focus-within {{
            border-color: var(--dh-primary) !important;
            box-shadow: 0 0 0 1px var(--dh-primary) !important;
        }}

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

        [data-baseweb="tab-list"] [aria-selected="true"] {{
            color: var(--dh-primary) !important;
        }}

        [data-baseweb="tab-highlight"] {{
            background-color: var(--dh-primary) !important;
        }}

        a {{
            color: var(--dh-primary);
        }}

        [data-testid="stProgressBar"] > div > div > div {{
            background-color: var(--dh-primary) !important;
        }}

        .dh-title {{
            font-size: 1.82rem;
            font-weight: 780;
            letter-spacing: -.032em;
            line-height: 1.12;
            color: var(--dh-text);
        }}

        .dh-subtitle {{
            color: var(--dh-muted);
            margin-top: .32rem;
            margin-bottom: 1.2rem;
        }}

        .dh-card {{
            background: var(--dh-surface);
            border: 1px solid var(--dh-border);
            border-radius: calc(var(--dh-radius) + 2px);
            padding: 1rem;
        }}

        .dh-chip {{
            display: inline-block;
            padding: 3px 9px;
            border-radius: 999px;
            background: rgba({pr},{pg},{pb}, .09);
            color: var(--dh-primary);
            font-size: .76rem;
            margin-right: 4px;
        }}

        .dh-status-ok {{ color: #087F5B; font-weight: 650; }}
        .dh-status-warn {{ color: #B45309; font-weight: 650; }}
        .dh-status-bad {{ color: #B42318; font-weight: 650; }}

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
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            background: linear-gradient(135deg, var(--dh-primary), color-mix(in srgb, var(--dh-primary) 76%, white 24%));
            font-size: 1rem;
            font-weight: 800;
            box-shadow: 0 18px 36px rgba({pr},{pg},{pb}, .18);
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
            border-radius: calc(var(--dh-radius) + 2px);
            border: 1px solid var(--dh-border);
            background: var(--dh-bg);
        }}

        .dh-preview-card {{
            background: var(--dh-surface);
            color: var(--dh-text);
            border: 1px solid var(--dh-border);
            border-radius: calc(var(--dh-radius) + 2px);
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

        .dh-top-band {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin: .25rem 0 1.1rem;
            padding: 1rem 1.05rem;
            border: 1px solid var(--dh-border);
            border-radius: 18px;
            background: linear-gradient(180deg, var(--dh-surface), color-mix(in srgb, var(--dh-surface) 88%, var(--dh-bg) 12%));
            box-shadow: 0 14px 28px rgba({tr},{tg},{tb}, .035);
        }}

        .dh-top-band-label {{
            color: var(--dh-primary);
            font-size: .68rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .1em;
            margin-bottom: .35rem;
        }}

        .dh-top-band-title {{
            color: var(--dh-text);
            font-size: 1.08rem;
            font-weight: 760;
            line-height: 1.2;
        }}

        .dh-top-band-subtitle {{
            color: var(--dh-muted);
            font-size: .84rem;
            margin-top: .22rem;
            line-height: 1.42;
            max-width: 760px;
        }}

        .dh-top-band-badge {{
            min-width: 235px;
            padding: .72rem .82rem;
            border-radius: 14px;
            border: 1px solid var(--dh-border);
            background: color-mix(in srgb, var(--dh-bg) 55%, white 45%);
            color: var(--dh-text);
            font-size: .75rem;
            line-height: 1.35;
        }}

        .dh-panel-shell {{
            display: flex;
            flex-direction: column;
            gap: .8rem;
            margin-bottom: 1.1rem;
        }}

        .dh-stack-title {{
            color: var(--dh-text);
            font-size: .95rem;
            font-weight: 750;
            letter-spacing: -.01em;
        }}

        .dh-stack-tile {{
            position: relative;
            overflow: hidden;
            padding: 1rem 1rem 1rem 1.1rem;
            border: 1px solid var(--dh-border);
            border-left: 6px solid var(--dh-primary);
            border-radius: 18px;
            background: var(--dh-surface);
            box-shadow: 0 14px 28px rgba({tr},{tg},{tb}, .03);
        }}

        .dh-stack-label,
        .dh-metric-label {{
            color: var(--dh-muted);
            font-size: .79rem;
            margin-bottom: .42rem;
        }}

        .dh-stack-value,
        .dh-metric-value {{
            color: var(--dh-text);
            font-size: 1.9rem;
            font-weight: 800;
            line-height: 1.05;
            letter-spacing: -.03em;
        }}

        .dh-stack-note,
        .dh-metric-note {{
            color: var(--dh-muted);
            font-size: .72rem;
            margin-top: .34rem;
            line-height: 1.35;
        }}

        .dh-metric-tile {{
            position: relative;
            min-height: 132px;
            padding: .95rem 1rem 1rem;
            border: 1px solid var(--dh-border);
            border-radius: 18px;
            background: var(--dh-surface);
            box-shadow: 0 12px 26px rgba({tr},{tg},{tb}, .03);
        }}

        .dh-metric-accent {{
            margin-top: .7rem;
            display: inline-flex;
            align-items: center;
            padding: .26rem .54rem;
            border-radius: 999px;
            background: rgba({pr},{pg},{pb}, .10);
            color: var(--dh-primary);
            font-size: .71rem;
            font-weight: 700;
        }}

        .dh-section-head {{
            margin: 1.35rem 0 .75rem;
        }}

        .dh-section-kicker {{
            color: var(--dh-primary);
            font-size: .68rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .1em;
            margin-bottom: .28rem;
        }}

        .dh-section-title {{
            color: var(--dh-text);
            font-size: 1.15rem;
            font-weight: 780;
            line-height: 1.18;
            letter-spacing: -.02em;
        }}

        .dh-section-subtitle {{
            color: var(--dh-muted);
            font-size: .83rem;
            margin-top: .18rem;
            line-height: 1.4;
        }}

        .dh-chart-title {{
            color: var(--dh-text);
            font-size: .88rem;
            font-weight: 720;
            margin-bottom: .25rem;
        }}

        /* Painel da jornada: leitura em cinco etapas, alinhada à referência. */
        .dh-revision-focus-note {{
            padding: .82rem 1rem;
            margin: .1rem 0 .9rem;
            background: color-mix(in srgb, var(--dh-primary) 5%, var(--dh-surface));
            border: 1px solid var(--dh-border);
            border-left: 4px solid var(--dh-primary);
            border-radius: 12px;
            color: var(--dh-text);
            font-size: .84rem;
            line-height: 1.48;
        }}
        .dh-five-stage {{
            min-height: 122px;
            margin-top: .25rem;
            padding: .95rem 1rem;
            border: 1px solid var(--dh-border);
            border-radius: 16px;
            background: var(--dh-surface);
            box-shadow: 0 8px 23px rgba({tr},{tg},{tb}, .035);
        }}
        .dh-five-step {{
            color: var(--dh-primary);
            font-size: .72rem;
            font-weight: 780;
            letter-spacing: .06em;
        }}
        .dh-five-number {{
            margin-top: .3rem;
            color: var(--dh-text);
            font-size: 2.1rem;
            font-weight: 800;
            letter-spacing: -.035em;
            line-height: 1.05;
        }}
        .dh-five-sub {{
            color: var(--dh-muted);
            margin-top: .32rem;
            font-size: .72rem;
        }}
        @media (max-width: 900px) {{
            .dh-five-stage {{ min-height: 112px; }}
        }}

        @media (max-width: 900px) {{
            .dh-top-band {{
                flex-direction: column;
            }}

            .dh-top-band-badge {{
                min-width: 0;
                width: 100%;
            }}
        }}

        @media (max-width: 900px) {{
            section[data-testid="stSidebar"] {{
                min-width: min({sidebar_width}px, 86vw);
                max-width: min({sidebar_width}px, 86vw);
            }}

            .block-container {{
                padding-top: 4.15rem !important;
            }}

            [data-testid="stSidebarCollapsedControl"],
            [data-testid="collapsedControl"] {{
                top: .85rem !important;
                left: .85rem !important;
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
        brand_main = (
            f'<div class="dh-sidebar-logo">'
            f'<img src="{logo_uri}" alt="{html.escape(theme["system_name"])}">'
            f"</div>"
            f'<div class="dh-sidebar-subtitle">{html.escape(theme["system_subtitle"])}</div>'
        )
    else:
        brand_main = f"""
        <div class="dh-brand-fallback">
          <div class="dh-brand-mark">{html.escape(_initials(theme["system_name"]))}</div>
          <div>
            <div class="dh-brand-name">{html.escape(theme["system_name"])}</div>
            <div class="dh-brand-subtitle">{html.escape(theme["system_subtitle"])}</div>
          </div>
        </div>
        """

    st.sidebar.markdown(
        f"""
        <div class="dh-brand">
          <div class="dh-brand-top">Dealer Hub</div>
          {brand_main}
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
          <div class="dh-user-head">
            <div class="dh-user-avatar">{html.escape(_initials(str(user.get("name") or "Usuário")))}</div>
            <div>
              <div class="dh-user-name">{html.escape(str(user.get("name") or "Usuário"))}</div>
              <div class="dh-user-meta">{html.escape(str(role))}</div>
            </div>
          </div>
          <div class="dh-user-meta">{html.escape(str(user.get("email") or ""))}</div>
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

    st.sidebar.markdown('<div class="dh-nav-wrap">', unsafe_allow_html=True)

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
                      <span class="dh-nav-icon">{_nav_icon_svg(item["key"])}</span>
                      <span>{html.escape(item["label"])}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                if st.sidebar.button(
                    item["label"],
                    icon=_nav_icon(item["key"]),
                    key=f"dh_nav_{item['key']}",
                    use_container_width=True,
                ):
                    st.session_state["dh_active_page"] = item["key"]
                    st.rerun()

    st.sidebar.markdown(
        '<div class="dh-quick-note">O menu permanece aberto no desktop. Em telas menores, use o botão do Streamlit ou Navegação no topo.</div>',
        unsafe_allow_html=True,
    )
    return str(st.session_state["dh_active_page"])




def render_main_navigation(items: list[dict[str, str]], selected: str) -> None:
    """Navegacao alternativa, independente do estado visual da sidebar.

    Compartilha a chave dh_active_page com sidebar_navigation e so mostra
    paginas previamente filtradas pelas permissoes do usuario em app.py.
    """
    if not items:
        return

    current = next((item for item in items if item["key"] == selected), items[0])
    import_allowed = any(item["key"] == "import" for item in items)

    with st.container(key="dh_main_nav_bar"):
        left, center, right = st.columns([2.2, 5.2, 2.2], vertical_alignment="center")

        with left:
            with st.popover("☰  Navegação", use_container_width=True):
                st.caption("Acesse qualquer página liberada para o seu perfil.")
                previous_group = None
                for item in items:
                    group = item.get("group") or "Navegação"
                    if group != previous_group:
                        st.caption(group.upper())
                        previous_group = group
                    if st.button(
                        item["label"],
                        icon=_nav_icon(item["key"]),
                        key=f"dh_top_nav_{item['key']}",
                        use_container_width=True,
                        disabled=item["key"] == selected,
                    ):
                        st.session_state["dh_active_page"] = item["key"]
                        st.rerun()

        with center:
            st.markdown(
                '<div class="dh-nav-top-title">DEALER HUB / '
                + html.escape(current["label"])
                + '</div><div class="dh-nav-top-subtitle">'
                + 'Navegação rápida disponível mesmo em telas menores.'
                + '</div>',
                unsafe_allow_html=True,
            )

        with right:
            if import_allowed:
                if st.button(
                    "Importações",
                    icon=":material/upload_file:",
                    key="dh_top_import_shortcut",
                    use_container_width=True,
                    type="primary" if selected == "import" else "secondary",
                    disabled=selected == "import",
                ):
                    st.session_state["dh_active_page"] = "import"
                    st.rerun()
            else:
                st.caption("Acesso conforme seu perfil")


def sidebar_footer() -> None:
    st.sidebar.markdown(
        '<div class="dh-sidebar-footer">Dealer Hub · Ambiente corporativo · Sidebar revisada para facilitar navegação e importações.</div>',
        unsafe_allow_html=True,
    )
