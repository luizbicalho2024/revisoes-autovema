from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import streamlit as st

from .config import ROLE_PERMISSIONS


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(value)))


def password_is_strong(password: str) -> tuple[bool, str]:
    password = password or ""
    if len(password) < 10:
        return False, "A senha precisa ter pelo menos 10 caracteres."
    if not re.search(r"[A-Z]", password):
        return False, "Inclua pelo menos uma letra maiúscula."
    if not re.search(r"[a-z]", password):
        return False, "Inclua pelo menos uma letra minúscula."
    if not re.search(r"\d", password):
        return False, "Inclua pelo menos um número."
    return True, ""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def can(user: dict[str, Any] | None, permission: str) -> bool:
    if not user:
        return False
    perms = ROLE_PERMISSIONS.get(str(user.get("role", "consulta")), set())
    return "*" in perms or permission in perms


def require_permission(user: dict[str, Any], permission: str) -> None:
    if not can(user, permission):
        st.error("Seu perfil não possui permissão para acessar esta função.")
        st.stop()


def get_user_scope(user: dict[str, Any]) -> list[int]:
    result: list[int] = []
    for item in user.get("company_codes", []) or []:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return sorted(set(result))


def initialize_session() -> None:
    defaults = {
        "auth_user": None,
        "authenticated": False,
        "last_activity": None,
        "login_failures": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_authenticated(user: dict[str, Any]) -> None:
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    st.session_state.auth_user = safe_user
    st.session_state.authenticated = True
    st.session_state.last_activity = utcnow()
    st.session_state.login_failures = 0


def logout() -> None:
    st.session_state.auth_user = None
    st.session_state.authenticated = False
    st.session_state.last_activity = None


def session_expired(timeout_hours: int) -> bool:
    last = st.session_state.get("last_activity")
    if not last:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return utcnow() - last > timedelta(hours=timeout_hours)


def touch_session() -> None:
    st.session_state.last_activity = utcnow()
