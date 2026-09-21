from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st
from pymongo.database import Database

from ..repositories import audit
from ..security import hash_password, password_is_strong, verify_password
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    page_header("Minha Conta", "Atualize sua senha de acesso ao Dealer Hub.")
    current = db.users.find_one({"_id": user.get("_id")})
    if not current:
        st.error("Usuário não encontrado.")
        return

    if current.get("must_change_password"):
        st.warning("Troca de senha obrigatória no primeiro acesso.")

    with st.form("change_password_form"):
        old_password = st.text_input("Senha atual", type="password")
        new_password = st.text_input("Nova senha", type="password")
        confirm = st.text_input("Confirme a nova senha", type="password")
        save = st.form_submit_button("Alterar senha", type="primary")

    if save:
        if not verify_password(old_password, current.get("password_hash", "")):
            st.error("Senha atual incorreta.")
            return
        ok, message = password_is_strong(new_password)
        if not ok:
            st.error(message)
            return
        if new_password != confirm:
            st.error("A confirmação da nova senha não confere.")
            return
        db.users.update_one(
            {"_id": current["_id"]},
            {"$set": {"password_hash": hash_password(new_password), "must_change_password": False, "updated_at": datetime.now(timezone.utc), "updated_by": user.get("email")}},
        )
        audit(db, user, "password_changed", "user", current["_id"])
        st.session_state.auth_user["must_change_password"] = False
        st.success("Senha alterada com sucesso.")
