from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..config import ROLES
from ..repositories import audit
from ..security import hash_password, normalize_email, password_is_strong, require_permission, valid_email
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    require_permission(user, "users.manage")
    page_header("Usuários e Acessos", "Controle de perfis, escopo por empresa e credenciais.")

    tabs = st.tabs(["Usuários", "Novo usuário / edição"])
    with tabs[0]:
        docs = list(db.users.find({}, {"password_hash": 0}).sort("name", 1))
        rows = []
        for d in docs:
            rows.append(
                {
                    "Nome": d.get("name"),
                    "E-mail": d.get("email"),
                    "Perfil": ROLES.get(d.get("role"), d.get("role")),
                    "Empresas": ", ".join(map(str, d.get("company_codes", []) or [])) or "Todas",
                    "Ativo": "Sim" if d.get("active", True) else "Não",
                    "Último login": d.get("last_login_at"),
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with tabs[1]:
        users = list(db.users.find({}, {"password_hash": 0}).sort("name", 1))
        mode = st.radio("Ação", ["Criar novo", "Editar existente"], horizontal=True)
        selected = None
        if mode == "Editar existente":
            labels = {f"{u.get('name')} • {u.get('email')}": u for u in users}
            if labels:
                selected = labels[st.selectbox("Usuário", list(labels.keys()))]

        with st.form("user_form"):
            name = st.text_input("Nome", value=(selected or {}).get("name", ""))
            email = st.text_input("E-mail", value=(selected or {}).get("email", ""), disabled=bool(selected))
            role_keys = list(ROLES.keys())
            current_role = (selected or {}).get("role", "consulta")
            role = st.selectbox("Perfil", role_keys, index=role_keys.index(current_role) if current_role in role_keys else 0, format_func=lambda x: ROLES[x])
            company_text = st.text_input(
                "Códigos de empresa permitidos (separados por vírgula)",
                value=", ".join(map(str, (selected or {}).get("company_codes", []) or [])),
                help="Deixe vazio para acesso a todas as empresas.",
            )
            password = st.text_input("Nova senha" if selected else "Senha inicial", type="password")
            active = st.checkbox("Usuário ativo", value=(selected or {}).get("active", True))
            must_change = st.checkbox("Solicitar troca de senha", value=(selected or {}).get("must_change_password", True))
            save = st.form_submit_button("Salvar", type="primary")

        if save:
            normalized_email = normalize_email(email)
            if not name.strip():
                st.error("Informe o nome.")
                return
            if not selected and not valid_email(normalized_email):
                st.error("Informe um e-mail válido.")
                return
            if role == "superadmin" and user.get("role") != "superadmin":
                st.error("Somente um superadministrador pode conceder esse perfil.")
                return

            company_codes = []
            for raw in company_text.split(","):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    company_codes.append(int(raw))
                except ValueError:
                    st.error(f"Código de empresa inválido: {raw}")
                    return

            payload = {
                "name": name.strip(),
                "role": role,
                "company_codes": sorted(set(company_codes)),
                "active": active,
                "must_change_password": must_change,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": user.get("email"),
            }
            if password:
                ok, message = password_is_strong(password)
                if not ok:
                    st.error(message)
                    return
                payload["password_hash"] = hash_password(password)

            if selected:
                if selected.get("role") == "superadmin" and not active:
                    active_superadmins = db.users.count_documents({"role": "superadmin", "active": True})
                    if active_superadmins <= 1:
                        st.error("Não é permitido desativar o último superadministrador ativo.")
                        return
                db.users.update_one({"_id": selected["_id"]}, {"$set": payload})
                audit(db, user, "user_updated", "user", selected["_id"], {"role": role, "active": active, "company_codes": company_codes})
                st.success("Usuário atualizado.")
            else:
                if not password:
                    st.error("Informe uma senha inicial.")
                    return
                if db.users.find_one({"email": normalized_email}):
                    st.error("Já existe um usuário com esse e-mail.")
                    return
                payload.update(
                    {
                        "_id": f"user:{normalized_email}",
                        "email": normalized_email,
                        "created_at": datetime.now(timezone.utc),
                        "created_by": user.get("email"),
                        "last_login_at": None,
                    }
                )
                db.users.insert_one(payload)
                audit(db, user, "user_created", "user", payload["_id"], {"role": role, "company_codes": company_codes})
                st.success("Usuário criado.")
            st.rerun()
