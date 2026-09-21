from __future__ import annotations

import time
from typing import Any

import streamlit as st
from pymongo.database import Database

from .repositories import audit
from .security import normalize_email, set_authenticated, verify_password


def authenticate(db: Database, email: str, password: str) -> tuple[bool, str, dict[str, Any] | None]:
    email = normalize_email(email)
    user = db.users.find_one({"email": email})
    if not user or not user.get("active", True):
        audit(db, {"email": email, "name": "Desconhecido"}, "login_failed", "session", details={"reason": "invalid_user"})
        return False, "E-mail ou senha inválidos.", None

    if not verify_password(password, user.get("password_hash", "")):
        audit(db, user, "login_failed", "session", details={"reason": "invalid_password"})
        return False, "E-mail ou senha inválidos.", None

    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}})
    audit(db, user, "login_success", "session")
    user = db.users.find_one({"_id": user["_id"]})
    return True, "Login realizado.", user


def render_login(db: Database) -> None:
    st.markdown(
        """
        <div class="dh-login-wrap">
          <div class="dh-login-brand">DEALER HUB</div>
          <div class="dh-login-subtitle">Jornada de Revisões • Autovema</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([1.15, 1, 1.15])
    with center:
        with st.form("login_form", clear_on_submit=False):
            st.subheader("Acesso ao sistema")
            email = st.text_input("E-mail", placeholder="nome@empresa.com.br")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if submit:
            failures = int(st.session_state.get("login_failures", 0))
            if failures >= 5:
                st.error("Muitas tentativas nesta sessão. Recarregue a página para tentar novamente.")
                return
            if failures > 1:
                time.sleep(min(failures * 0.4, 2.0))
            ok, message, user = authenticate(db, email, password)
            if ok and user:
                set_authenticated(user)
                st.rerun()
            st.session_state.login_failures = failures + 1
            st.error(message)

        st.caption("As credenciais são validadas no MongoDB e as senhas são armazenadas apenas como hash bcrypt.")
