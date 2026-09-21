from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..config import REVISION_STATUSES
from ..journey import refresh_loyalty_for_vehicle
from ..maintenance import reconcile_vehicle_service_history
from ..repositories import audit, scoped_filter
from ..security import can
from ..ui import page_header


def _vehicle_label(
    vehicle: dict,
    customer_name: str | None,
) -> str:
    return " • ".join(
        [
            value
            for value in [
                vehicle.get("plate") or "SEM PLACA",
                vehicle.get("model"),
                customer_name,
            ]
            if value
        ]
    )


def _fmt_date(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def render(db: Database, user: dict) -> None:
    page_header(
        "Jornada de Revisões",
        "Controle da 1ª à 5ª revisão com sugestões conciliadas a partir das ordens de serviço.",
    )

    scope = scoped_filter(user)
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        search = st.text_input(
            "Localizar jornada",
            placeholder="Placa, chassi, modelo, cliente",
        )
    with f2:
        status_filter = st.selectbox(
            "Status da revisão",
            ["Todos"] + list(REVISION_STATUSES.values()),
        )
    with f3:
        overdue_only = st.checkbox("Somente vencidas")

    vehicle_query = {}
    if search:
        import re

        term = re.escape(search.strip())
        vehicle_query = {
            "$or": [
                {"plate": {"$regex": term, "$options": "i"}},
                {"chassis": {"$regex": term, "$options": "i"}},
                {"model": {"$regex": term, "$options": "i"}},
            ]
        }

    vehicles = list(
        db.vehicles.find(vehicle_query).sort("last_sale_at", -1).limit(300)
    )
    vehicle_ids = [vehicle["_id"] for vehicle in vehicles]

    journey_query = dict(scope)
    if vehicle_ids:
        journey_query["vehicle_id"] = {"$in": vehicle_ids}
    elif search:
        customer_ids = [
            customer["_id"]
            for customer in db.customers.find(
                {
                    "name": {
                        "$regex": __import__("re").escape(search),
                        "$options": "i",
                    }
                },
                {"_id": 1},
            ).limit(300)
        ]
        journey_query["customer_id"] = {"$in": customer_ids}

    journeys = list(
        db.journeys.find(journey_query).sort("sale_date", -1).limit(300)
    )
    if not journeys:
        st.info(
            "Nenhuma jornada encontrada. Importe o REL_VEICULOS para criar a base."
        )
        return

    vehicle_map = {
        vehicle["_id"]: vehicle
        for vehicle in db.vehicles.find(
            {"_id": {"$in": [journey["vehicle_id"] for journey in journeys]}}
        )
    }
    customer_map = {
        customer["_id"]: customer
        for customer in db.customers.find(
            {
                "_id": {
                    "$in": [
                        journey.get("customer_id")
                        for journey in journeys
                        if journey.get("customer_id")
                    ]
                }
            }
        )
    }

    options = {}
    for journey in journeys:
        vehicle = vehicle_map.get(journey["vehicle_id"], {})
        customer = customer_map.get(journey.get("customer_id"), {})
        options[_vehicle_label(vehicle, customer.get("name"))] = journey

    selected_label = st.selectbox(
        "Veículo / cliente",
        list(options.keys()),
    )
    journey = options[selected_label]
    vehicle = vehicle_map.get(journey["vehicle_id"], {})
    customer = customer_map.get(journey.get("customer_id"), {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cliente", customer.get("name") or "—")
    c2.metric("Veículo", vehicle.get("model") or "—")
    c3.metric("Compra", _fmt_date(journey.get("sale_date")))
    if journey.get("loyalty_cancelled"):
        c4.metric("Fidelidade", "Cancelada")
    else:
        c4.metric(
            "Bônus atual",
            f"{float(journey.get('loyalty_bonus_pct') or 0):.0f}%",
        )

    if journey.get("maintenance_status_reason"):
        st.caption(
            "Situação de manutenção: "
            + journey.get("maintenance_status_reason")
        )

    revisions = list(
        db.revisions.find(
            {"vehicle_id": journey["vehicle_id"]}
        ).sort("revision_number", 1)
    )
    if not revisions:
        st.warning(
            "O plano ainda não foi gerado. Vá em Configurações e execute "
            "'Recalcular planos'."
        )
        return

    if status_filter != "Todos" or overdue_only:
        wanted_status = next(
            (
                key
                for key, value in REVISION_STATUSES.items()
                if value == status_filter
            ),
            None,
        )
        filtered = []
        now = datetime.now(timezone.utc)

        for revision in revisions:
            if wanted_status and revision.get("status") != wanted_status:
                continue
            if overdue_only and not (
                revision.get("due_date")
                and revision["due_date"] < now
                and revision.get("status") in {"pendente", "agendada"}
            ):
                continue
            filtered.append(revision)

        revisions = filtered

    if not revisions:
        st.info("Nenhuma revisão corresponde aos filtros atuais.")
        return

    can_edit = can(user, "journey.edit")

    for revision in revisions:
        number = int(revision.get("revision_number", 0))
        title_status = REVISION_STATUSES.get(
            revision.get("status"),
            revision.get("status"),
        )

        with st.expander(
            f"{number}ª revisão — {title_status}",
            expanded=number == 1,
        ):
            info1, info2, info3 = st.columns(3)
            info1.write(
                f"**Prazo:** {_fmt_date(revision.get('due_date'))}"
            )
            info2.write(
                (
                    f"**KM alvo:** {int(revision.get('due_km')):,}"
                    .replace(",", ".")
                    if revision.get("due_km")
                    else "**KM alvo:** não parametrizado"
                )
            )
            info3.write(
                f"**Realizada:** {_fmt_date(revision.get('performed_at'))}"
            )

            candidate_id = revision.get("candidate_service_order_id")
            if candidate_id and revision.get("status") != "realizada":
                order = db.service_orders.find_one({"_id": candidate_id})
                if order:
                    confidence = (
                        "alta"
                        if revision.get("candidate_confidence") == "alta"
                        else "média"
                    )

                    st.info(
                        f"OS {order.get('os_number')} sugerida para esta revisão "
                        f"({confidence} confiança): {_fmt_date(order.get('service_date'))}, "
                        f"{int(order.get('os_km') or 0):,} km, "
                        f"{order.get('company_name') or 'concessionária'}."
                        .replace(",", ".")
                    )

                    if can_edit:
                        accept_col, reject_col = st.columns(2)

                        if accept_col.button(
                            "Confirmar OS como revisão realizada",
                            key=f"accept_os_{revision['_id']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            notes = (
                                f"Revisão confirmada pela OS {order.get('os_number')} "
                                "importada do pós-venda."
                            )

                            db.revisions.update_one(
                                {"_id": revision["_id"]},
                                {
                                    "$set": {
                                        "status": "realizada",
                                        "performed_at": order.get("service_date"),
                                        "performed_km": order.get("os_km"),
                                        "notes": notes,
                                        "source": "service_order",
                                        "service_order_id": order["_id"],
                                        "updated_at": datetime.now(timezone.utc),
                                        "updated_by": user.get("email"),
                                    },
                                    "$unset": {
                                        "candidate_service_order_id": "",
                                        "candidate_confidence": "",
                                        "candidate_km_delta": "",
                                        "candidate_days_delta": "",
                                        "candidate_score": "",
                                    },
                                },
                            )

                            refresh_loyalty_for_vehicle(
                                db,
                                journey["vehicle_id"],
                            )
                            reconcile_vehicle_service_history(
                                db,
                                journey["vehicle_id"],
                                user_email=user.get("email") or "system",
                            )
                            audit(
                                db,
                                user,
                                "revision_confirmed_from_service_order",
                                "revision",
                                str(revision["_id"]),
                                {
                                    "vehicle_id": journey["vehicle_id"],
                                    "revision_number": number,
                                    "service_order_id": order["_id"],
                                },
                            )
                            st.rerun()

                        if reject_col.button(
                            "Ignorar esta sugestão",
                            key=f"reject_os_{revision['_id']}",
                            use_container_width=True,
                        ):
                            db.revisions.update_one(
                                {"_id": revision["_id"]},
                                {
                                    "$addToSet": {
                                        "rejected_service_order_ids": order["_id"]
                                    }
                                },
                            )
                            reconcile_vehicle_service_history(
                                db,
                                journey["vehicle_id"],
                                user_email=user.get("email") or "system",
                            )
                            st.rerun()

            if can_edit:
                with st.form(f"revision_form_{revision['_id']}"):
                    status_keys = list(REVISION_STATUSES.keys())
                    current_index = (
                        status_keys.index(revision.get("status"))
                        if revision.get("status") in status_keys
                        else 0
                    )
                    status = st.selectbox(
                        "Status",
                        status_keys,
                        index=current_index,
                        format_func=lambda value: REVISION_STATUSES[value],
                    )

                    date_default = revision.get("performed_at")
                    has_performed_date = st.checkbox(
                        "Informar data de realização",
                        value=bool(date_default),
                        key=f"has_date_{revision['_id']}",
                    )
                    performed_date = st.date_input(
                        "Data de realização",
                        value=(
                            date_default.date()
                            if date_default
                            else datetime.now(timezone.utc).date()
                        ),
                        disabled=not has_performed_date,
                        key=f"date_{revision['_id']}",
                    )
                    km = st.number_input(
                        "KM na revisão",
                        min_value=0,
                        value=int(revision.get("performed_km") or 0),
                        step=100,
                    )
                    notes = st.text_area(
                        "Observações",
                        value=revision.get("notes") or "",
                    )

                    save = st.form_submit_button(
                        "Salvar revisão",
                        type="primary",
                    )

                    if save:
                        performed_at = None
                        if has_performed_date and performed_date:
                            performed_at = datetime.combine(
                                performed_date,
                                datetime.min.time(),
                                tzinfo=timezone.utc,
                            )

                        db.revisions.update_one(
                            {"_id": revision["_id"]},
                            {
                                "$set": {
                                    "status": status,
                                    "performed_at": performed_at,
                                    "performed_km": km or None,
                                    "notes": notes.strip() or None,
                                    "updated_at": datetime.now(timezone.utc),
                                    "updated_by": user.get("email"),
                                }
                            },
                        )
                        refresh_loyalty_for_vehicle(
                            db,
                            journey["vehicle_id"],
                        )
                        reconcile_vehicle_service_history(
                            db,
                            journey["vehicle_id"],
                            user_email=user.get("email") or "system",
                        )
                        audit(
                            db,
                            user,
                            "revision_updated",
                            "revision",
                            str(revision["_id"]),
                            {
                                "vehicle_id": journey["vehicle_id"],
                                "revision_number": number,
                                "status": status,
                            },
                        )
                        st.rerun()

    st.divider()
    st.markdown("### Histórico de ordens de serviço")

    service_orders = list(
        db.service_orders.find(
            {"vehicle_id": journey["vehicle_id"]}
        ).sort("service_date", -1)
    )

    if service_orders:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "OS": order.get("os_number"),
                        "Data": order.get("service_date"),
                        "KM": order.get("os_km"),
                        "Empresa": order.get("company_name"),
                        "Total": order.get("total_amount"),
                        "Proprietário": order.get("owner_name"),
                        "Vínculo": order.get("link_status"),
                    }
                    for order in service_orders
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Nenhuma OS importada para este veículo.")
