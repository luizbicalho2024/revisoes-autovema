from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..journey import get_loyalty_bonuses, get_revision_rules, recalculate_revision_plan
from ..repositories import audit
from ..security import require_permission
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    require_permission(user, "settings.manage")
    page_header(
        "Configurações do Programa",
        "Parametrize prazos de revisão e os bônus do programa sem alterar código.",
    )

    st.warning(
        "Os prazos de revisão por tempo/quilometragem devem seguir o manual da montadora. O sistema não presume periodicidade: preencha os valores homologados pela operação."
    )

    rules = get_revision_rules(db)
    with st.form("revision_rules_form"):
        st.markdown("### Regras de revisão")
        new_rules = []
        for rule in rules:
            n = int(rule["revision_number"])
            c1, c2, c3 = st.columns([1, 1, 1])
            c1.markdown(f"**{n}ª revisão**")
            months_raw = c2.text_input(
                f"Meses após a venda — {n}ª",
                value="" if rule.get("months_after_sale") in (None, "") else str(rule.get("months_after_sale")),
                key=f"months_{n}",
                label_visibility="collapsed",
                placeholder="Meses",
            )
            km_raw = c3.text_input(
                f"KM alvo — {n}ª",
                value="" if rule.get("km") in (None, "") else str(rule.get("km")),
                key=f"km_{n}",
                label_visibility="collapsed",
                placeholder="Quilometragem",
            )
            try:
                months = int(months_raw) if months_raw.strip() else None
                km = int(km_raw) if km_raw.strip() else None
            except ValueError:
                months, km = "invalid", "invalid"
            new_rules.append({"revision_number": n, "months_after_sale": months, "km": km})
        save_rules = st.form_submit_button("Salvar regras de revisão", type="primary")

    if save_rules:
        if any(r["months_after_sale"] == "invalid" or r["km"] == "invalid" for r in new_rules):
            st.error("Use apenas números inteiros nos campos de prazo e quilometragem.")
        else:
            db.settings.update_one(
                {"_id": "revision_rules"},
                {"$set": {"rules": new_rules, "updated_at": datetime.now(timezone.utc), "updated_by": user.get("email")}},
                upsert=True,
            )
            audit(db, user, "settings_updated", "revision_rules", "revision_rules", {"rules": new_rules})
            st.success("Regras salvas.")

    st.markdown("### Programa Recompra Garantida")
    bonuses = get_loyalty_bonuses(db)
    with st.form("loyalty_form"):
        c1, c2, c3 = st.columns(3)
        b3 = c1.number_input("Bônus após 3ª revisão (%)", min_value=0.0, max_value=100.0, value=float(bonuses.get(3, 1.0)), step=0.1)
        b4 = c2.number_input("Bônus após 4ª revisão (%)", min_value=0.0, max_value=100.0, value=float(bonuses.get(4, 2.0)), step=0.1)
        b5 = c3.number_input("Bônus após 5ª revisão ou mais (%)", min_value=0.0, max_value=100.0, value=float(bonuses.get(5, 3.0)), step=0.1)
        save_bonus = st.form_submit_button("Salvar bônus")
    if save_bonus:
        payload = {"3": float(b3), "4": float(b4), "5": float(b5)}
        db.settings.update_one(
            {"_id": "loyalty"},
            {"$set": {"bonuses": payload, "updated_at": datetime.now(timezone.utc), "updated_by": user.get("email")}},
            upsert=True,
        )
        audit(db, user, "settings_updated", "loyalty", "loyalty", {"bonuses": payload})
        st.success("Bônus salvos.")

    st.divider()
    st.markdown("### Recalcular planos de revisão")
    st.caption("Gera/atualiza as 5 revisões para todas as jornadas usando a data de venda e as regras acima. Status já lançados não são apagados.")
    if st.button("Recalcular planos", type="primary"):
        with st.spinner("Recalculando..."):
            result = recalculate_revision_plan(db, user.get("email", "system"))
        audit(db, user, "revision_plan_recalculated", "settings", "revision_rules", result)
        st.success(f"Concluído: {result['journeys']} jornadas e {result['revision_records']} registros de revisão processados.")

    st.markdown("### Resumo atual")
    df = pd.DataFrame(get_revision_rules(db))
    df.columns = ["Revisão", "Meses após venda", "KM alvo"]
    st.dataframe(df, hide_index=True, use_container_width=True)
