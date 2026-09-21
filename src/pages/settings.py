from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..journey import (
    get_loyalty_bonuses,
    get_revision_rules,
    recalculate_revision_plan,
)
from ..maintenance import (
    get_service_reconciliation_settings,
    reconcile_all_service_history,
)
from ..repositories import audit
from ..security import require_permission
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    require_permission(user, "settings.manage")
    page_header(
        "Configurações do Programa",
        "Parametrize revisões, conciliação de OS e bônus sem alterar código.",
    )

    st.markdown("### Regras de revisão")
    st.warning(
        "Os prazos por tempo/quilometragem devem seguir o manual da montadora. "
        "Preencha somente valores homologados pela operação."
    )

    rules = get_revision_rules(db)
    with st.form("revision_rules_form"):
        new_rules = []
        for rule in rules:
            number = int(rule["revision_number"])
            c1, c2, c3 = st.columns([1, 1, 1])
            c1.markdown(f"**{number}ª revisão**")
            months_raw = c2.text_input(
                f"Meses após a venda — {number}ª",
                value=(
                    ""
                    if rule.get("months_after_sale") in (None, "")
                    else str(rule.get("months_after_sale"))
                ),
                key=f"months_{number}",
                label_visibility="collapsed",
                placeholder="Meses",
            )
            km_raw = c3.text_input(
                f"KM alvo — {number}ª",
                value=(
                    ""
                    if rule.get("km") in (None, "")
                    else str(rule.get("km"))
                ),
                key=f"km_{number}",
                label_visibility="collapsed",
                placeholder="Quilometragem",
            )

            try:
                months = int(months_raw) if months_raw.strip() else None
                km = int(km_raw) if km_raw.strip() else None
            except ValueError:
                months, km = "invalid", "invalid"

            new_rules.append(
                {
                    "revision_number": number,
                    "months_after_sale": months,
                    "km": km,
                }
            )

        save_rules = st.form_submit_button(
            "Salvar regras de revisão",
            type="primary",
        )

    if save_rules:
        if any(
            rule["months_after_sale"] == "invalid"
            or rule["km"] == "invalid"
            for rule in new_rules
        ):
            st.error(
                "Use apenas números inteiros nos campos de prazo e quilometragem."
            )
        else:
            db.settings.update_one(
                {"_id": "revision_rules"},
                {
                    "$set": {
                        "rules": new_rules,
                        "updated_at": datetime.now(timezone.utc),
                        "updated_by": user.get("email"),
                    }
                },
                upsert=True,
            )
            audit(
                db,
                user,
                "settings_updated",
                "revision_rules",
                "revision_rules",
                {"rules": new_rules},
            )
            st.success("Regras de revisão salvas.")

    st.divider()
    st.markdown("### Conciliação automática das ordens de serviço")
    service_rules = get_service_reconciliation_settings(db)

    with st.form("service_reconciliation_form"):
        c1, c2 = st.columns(2)
        km_tolerance = c1.number_input(
            "Tolerância de quilometragem (+/- km)",
            min_value=0,
            max_value=10000,
            value=int(service_rules["km_tolerance"]),
            step=100,
            help=(
                "Ex.: alvo de 10.000 km com tolerância de 1.500 considera "
                "OS entre 8.500 e 11.500 km como candidata."
            ),
        )
        days_tolerance = c2.number_input(
            "Tolerância de data (+/- dias)",
            min_value=0,
            max_value=365,
            value=int(service_rules["days_tolerance"]),
            step=5,
        )

        require_owner_match = st.toggle(
            "Exigir CPF/CNPJ do proprietário da OS igual ao cliente da venda",
            value=bool(service_rules["require_owner_match"]),
            help=(
                "Recomendado. Evita atribuir ao cliente atual uma OS realizada "
                "por outro proprietário do mesmo veículo."
            ),
        )

        save_service_rules = st.form_submit_button(
            "Salvar regras de conciliação",
            type="primary",
        )

    if save_service_rules:
        payload = {
            "km_tolerance": int(km_tolerance),
            "days_tolerance": int(days_tolerance),
            "require_owner_match": bool(require_owner_match),
        }
        db.settings.update_one(
            {"_id": "service_reconciliation"},
            {
                "$set": {
                    "rules": payload,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": user.get("email"),
                }
            },
            upsert=True,
        )
        audit(
            db,
            user,
            "settings_updated",
            "service_reconciliation",
            "service_reconciliation",
            payload,
        )
        st.success("Regras de conciliação salvas.")

    if st.button(
        "Reconciliar novamente todo o histórico de OS",
        use_container_width=True,
    ):
        with st.spinner("Recalculando conciliações..."):
            result = reconcile_all_service_history(
                db,
                user_email=user.get("email") or "system",
            )
        st.success(
            f"Concluído: {result['vehicles']} veículos analisados e "
            f"{result['candidates']} sugestões de revisão encontradas."
        )

    st.divider()
    st.markdown("### Programa Recompra Garantida")
    bonuses = get_loyalty_bonuses(db)

    with st.form("loyalty_form"):
        c1, c2, c3 = st.columns(3)
        b3 = c1.number_input(
            "Bônus após 3ª revisão (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(bonuses.get(3, 1.0)),
            step=0.1,
        )
        b4 = c2.number_input(
            "Bônus após 4ª revisão (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(bonuses.get(4, 2.0)),
            step=0.1,
        )
        b5 = c3.number_input(
            "Bônus após 5ª revisão ou mais (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(bonuses.get(5, 3.0)),
            step=0.1,
        )
        save_bonus = st.form_submit_button("Salvar bônus")

    if save_bonus:
        payload = {
            "3": float(b3),
            "4": float(b4),
            "5": float(b5),
        }
        db.settings.update_one(
            {"_id": "loyalty"},
            {
                "$set": {
                    "bonuses": payload,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": user.get("email"),
                }
            },
            upsert=True,
        )
        audit(
            db,
            user,
            "settings_updated",
            "loyalty",
            "loyalty",
            {"bonuses": payload},
        )
        st.success("Bônus salvos.")

    st.divider()
    st.markdown("### Recalcular planos de revisão")
    st.caption(
        "Gera/atualiza as 5 revisões usando a data de venda e as regras acima. "
        "Status já lançados não são apagados."
    )

    if st.button("Recalcular planos", type="primary"):
        with st.spinner("Recalculando..."):
            result = recalculate_revision_plan(
                db,
                user.get("email", "system"),
            )
            reconciliation = reconcile_all_service_history(
                db,
                user_email=user.get("email") or "system",
            )

        audit(
            db,
            user,
            "revision_plan_recalculated",
            "settings",
            "revision_rules",
            {**result, **reconciliation},
        )
        st.success(
            f"Concluído: {result['journeys']} jornadas, "
            f"{result['revision_records']} revisões e "
            f"{reconciliation['candidates']} sugestões de OS."
        )

    st.markdown("### Resumo atual")
    df = pd.DataFrame(get_revision_rules(db))
    df.columns = ["Revisão", "Meses após venda", "KM alvo"]
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
    )
