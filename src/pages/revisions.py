from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..config import REVISION_STATUSES
from ..journey import refresh_loyalty_for_vehicle
from ..repositories import audit, combine_filters, scoped_filter
from ..security import can
from ..ui import page_header


def _vehicle_label(vehicle: dict, customer_name: str | None) -> str:
    return " • ".join(
        [x for x in [vehicle.get("plate") or "SEM PLACA", vehicle.get("model"), customer_name] if x]
    )


def render(db: Database, user: dict) -> None:
    page_header(
        "Jornada de Revisões",
        "Controle da 1ª à 5ª revisão, retenção, evasão e elegibilidade do programa de recompra.",
    )

    scope = scoped_filter(user)
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        search = st.text_input("Localizar jornada", placeholder="Placa, chassi, modelo, cliente")
    with f2:
        status_filter = st.selectbox("Status da revisão", ["Todos"] + list(REVISION_STATUSES.values()))
    with f3:
        overdue_only = st.checkbox("Somente vencidas")

    vehicle_query = {}
    if search:
        import re
        term = re.escape(search.strip())
        vehicle_query = {"$or": [{"plate": {"$regex": term, "$options": "i"}}, {"chassis": {"$regex": term, "$options": "i"}}, {"model": {"$regex": term, "$options": "i"}}]}
    vehicles = list(db.vehicles.find(vehicle_query).sort("last_sale_at", -1).limit(300))
    vehicle_ids = [v["_id"] for v in vehicles]

    journey_query = dict(scope)
    if vehicle_ids:
        journey_query["vehicle_id"] = {"$in": vehicle_ids}
    elif search:
        customer_ids = [c["_id"] for c in db.customers.find({"name": {"$regex": __import__("re").escape(search), "$options": "i"}}, {"_id": 1}).limit(300)]
        journey_query["customer_id"] = {"$in": customer_ids}

    journeys = list(db.journeys.find(journey_query).sort("sale_date", -1).limit(300))
    if not journeys:
        st.info("Nenhuma jornada encontrada. Importe o REL_VEICULOS para criar a base.")
        return

    vehicle_map = {v["_id"]: v for v in db.vehicles.find({"_id": {"$in": [j["vehicle_id"] for j in journeys]}})}
    customer_map = {c["_id"]: c for c in db.customers.find({"_id": {"$in": [j.get("customer_id") for j in journeys]}})}

    options = {}
    for j in journeys:
        vehicle = vehicle_map.get(j["vehicle_id"], {})
        customer = customer_map.get(j.get("customer_id"), {})
        label = _vehicle_label(vehicle, customer.get("name"))
        options[label] = j

    selected_label = st.selectbox("Veículo / cliente", list(options.keys()))
    journey = options[selected_label]
    vehicle = vehicle_map.get(journey["vehicle_id"], {})
    customer = customer_map.get(journey.get("customer_id"), {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cliente", customer.get("name") or "—")
    c2.metric("Veículo", vehicle.get("model") or "—")
    c3.metric("Compra", journey.get("sale_date").strftime("%d/%m/%Y") if journey.get("sale_date") else "—")
    if journey.get("loyalty_cancelled"):
        c4.metric("Fidelidade", "Cancelada")
    else:
        c4.metric("Bônus atual", f"{float(journey.get('loyalty_bonus_pct') or 0):.0f}%")

    revisions = list(db.revisions.find({"vehicle_id": journey["vehicle_id"]}).sort("revision_number", 1))
    if not revisions:
        st.warning("O plano de revisões ainda não foi gerado. Vá em Configurações e execute 'Recalcular planos'.")
        return

    if status_filter != "Todos" or overdue_only:
        wanted_status = next((k for k, v in REVISION_STATUSES.items() if v == status_filter), None)
        filtered = []
        now = datetime.now(timezone.utc)
        for r in revisions:
            if wanted_status and r.get("status") != wanted_status:
                continue
            if overdue_only and not (r.get("due_date") and r["due_date"] < now and r.get("status") in {"pendente", "agendada"}):
                continue
            filtered.append(r)
        revisions = filtered

    if not revisions:
        st.info("Nenhuma revisão corresponde aos filtros atuais.")
        return

    can_edit = can(user, "journey.edit")
    for rev in revisions:
        n = int(rev.get("revision_number", 0))
        with st.expander(f"{n}ª revisão — {REVISION_STATUSES.get(rev.get('status'), rev.get('status'))}", expanded=n == 1):
            info1, info2, info3 = st.columns(3)
            info1.write(f"**Prazo:** {rev.get('due_date').strftime('%d/%m/%Y') if rev.get('due_date') else 'não parametrizado'}")
            info2.write(f"**KM alvo:** {int(rev.get('due_km')):,}".replace(",", ".") if rev.get("due_km") else "**KM alvo:** não parametrizado")
            info3.write(f"**Realizada:** {rev.get('performed_at').strftime('%d/%m/%Y') if rev.get('performed_at') else '—'}")

            if can_edit:
                with st.form(f"revision_form_{rev['_id']}"):
                    status_keys = list(REVISION_STATUSES.keys())
                    current_index = status_keys.index(rev.get("status")) if rev.get("status") in status_keys else 0
                    status = st.selectbox("Status", status_keys, index=current_index, format_func=lambda x: REVISION_STATUSES[x])
                    date_default = rev.get("performed_at")
                    has_performed_date = st.checkbox("Informar data de realização", value=bool(date_default), key=f"has_date_{rev['_id']}")
                    performed_date = st.date_input(
                        "Data de realização",
                        value=date_default.date() if date_default else datetime.now(timezone.utc).date(),
                        disabled=not has_performed_date,
                        key=f"date_{rev['_id']}",
                    )
                    km = st.number_input("KM na revisão", min_value=0, value=int(rev.get("performed_km") or 0), step=100)
                    notes = st.text_area("Observações", value=rev.get("notes") or "")
                    save = st.form_submit_button("Salvar revisão", type="primary")
                    if save:
                        performed_at = None
                        if has_performed_date and performed_date:
                            performed_at = datetime.combine(performed_date, datetime.min.time(), tzinfo=timezone.utc)
                        db.revisions.update_one(
                            {"_id": rev["_id"]},
                            {"$set": {"status": status, "performed_at": performed_at, "performed_km": km or None, "notes": notes.strip() or None, "updated_at": datetime.now(timezone.utc), "updated_by": user.get("email")}},
                        )
                        refresh_loyalty_for_vehicle(db, journey["vehicle_id"])
                        audit(db, user, "revision_updated", "revision", str(rev["_id"]), {"vehicle_id": journey["vehicle_id"], "revision_number": n, "status": status})
                        st.success("Revisão atualizada.")
                        st.rerun()

    st.divider()
    rows = []
    for rev in db.revisions.find({"vehicle_id": journey["vehicle_id"]}).sort("revision_number", 1):
        rows.append({
            "Revisão": f"{rev.get('revision_number')}ª",
            "Status": REVISION_STATUSES.get(rev.get("status"), rev.get("status")),
            "Prazo": rev.get("due_date"),
            "Realizada": rev.get("performed_at"),
            "KM": rev.get("performed_km"),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
