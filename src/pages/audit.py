from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..security import require_permission
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    require_permission(user, "audit.view")
    page_header("Auditoria", "Rastreabilidade de logins, importações e alterações operacionais.")
    c1, c2 = st.columns([2, 1])
    with c1:
        action = st.text_input("Filtrar ação", placeholder="import_success, revision_updated...")
    with c2:
        limit = st.selectbox("Quantidade", [100, 250, 500, 1000], index=1)

    query = {}
    if action.strip():
        query["action"] = {"$regex": action.strip(), "$options": "i"}
    docs = list(db.audit_logs.find(query).sort("created_at", -1).limit(limit))
    rows = []
    for d in docs:
        rows.append(
            {
                "Data": d.get("created_at"),
                "Usuário": d.get("user_email"),
                "Ação": d.get("action"),
                "Entidade": d.get("entity"),
                "ID": d.get("entity_id"),
                "Detalhes": json.dumps(d.get("details") or {}, ensure_ascii=False, default=str),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
