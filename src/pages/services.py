from __future__ import annotations

import re

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..appearance import get_appearance_settings
from ..charts import donut_chart
from ..maintenance import MAINTENANCE_LABELS
from ..repositories import array_scoped_filter
from ..security import can
from ..ui import page_header


def _fmt_date(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _fmt_km(value) -> str:
    if value in (None, ""):
        return "—"
    return f"{int(value):,}".replace(",", ".") + " km"


def render(db: Database, user: dict) -> None:
    appearance = get_appearance_settings(db)

    page_header(
        "Serviços e Manutenções",
        "Histórico de ordens de serviço conciliado por chassi com clientes, veículos e plano de revisões.",
    )

    vehicle_scope = array_scoped_filter(user)
    scoped_vehicle_ids = db.vehicles.distinct("_id", vehicle_scope)

    journey_query = {}
    if vehicle_scope:
        journey_query["vehicle_id"] = {"$in": scoped_vehicle_ids}

    journeys = list(
        db.journeys.find(journey_query).sort("sale_date", -1).limit(2000)
    )

    status_counts: dict[str, int] = {}
    for journey in journeys:
        key = journey.get("maintenance_status") or "sem_parametros"
        status_counts[key] = status_counts.get(key, 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Veículos acompanhados", len(journeys))
    c2.metric("Em dia", status_counts.get("em_dia", 0))
    c3.metric("OS a confirmar", status_counts.get("conciliar", 0))
    c4.metric("Atrasados", status_counts.get("atrasada", 0))

    chart_rows = [
        {
            "categoria": MAINTENANCE_LABELS.get(key, key),
            "valor": value,
        }
        for key, value in status_counts.items()
        if value
    ]
    if chart_rows:
        donut_chart(
            chart_rows,
            category_field="categoria",
            value_field="valor",
            appearance=appearance,
            height=260,
        )

    st.markdown("### Situação da frota")

    f1, f2 = st.columns([2, 1])
    search = f1.text_input(
        "Localizar",
        placeholder="Cliente, CPF/CNPJ, placa, chassi ou modelo",
    )
    status_filter = f2.selectbox(
        "Situação",
        ["Todos"] + list(MAINTENANCE_LABELS.values()),
    )

    vehicle_ids = [journey["vehicle_id"] for journey in journeys]
    customer_ids = [
        journey.get("customer_id")
        for journey in journeys
        if journey.get("customer_id")
    ]

    vehicles = list(
        db.vehicles.find({"_id": {"$in": vehicle_ids}})
    )
    customers = list(
        db.customers.find({"_id": {"$in": customer_ids}})
    )
    vehicle_map = {vehicle["_id"]: vehicle for vehicle in vehicles}
    customer_map = {customer["_id"]: customer for customer in customers}

    rows = []
    for journey in journeys:
        vehicle = vehicle_map.get(journey["vehicle_id"], {})
        customer = customer_map.get(journey.get("customer_id"), {})

        status_key = journey.get("maintenance_status") or "sem_parametros"
        status_label = MAINTENANCE_LABELS.get(status_key, status_key)

        searchable = " ".join(
            [
                str(customer.get("name") or ""),
                str(customer.get("document") or ""),
                str(vehicle.get("plate") or ""),
                str(vehicle.get("chassis") or ""),
                str(vehicle.get("model") or ""),
            ]
        ).lower()

        if search and search.strip().lower() not in searchable:
            continue
        if status_filter != "Todos" and status_label != status_filter:
            continue

        rows.append(
            {
                "Cliente": customer.get("name"),
                "Documento": customer.get("document"),
                "Placa": vehicle.get("plate"),
                "Chassi": vehicle.get("chassis"),
                "Veículo": vehicle.get("model"),
                "Situação": status_label,
                "Última OS": journey.get("latest_service_at"),
                "KM última OS": journey.get("latest_service_km"),
                "Próxima revisão": (
                    f"{journey.get('next_revision_number')}ª"
                    if journey.get("next_revision_number")
                    else "—"
                ),
                "Prazo": journey.get("next_due_date"),
                "KM alvo": journey.get("next_due_km"),
                "Motivo": journey.get("maintenance_status_reason"),
                "_vehicle_id": journey.get("vehicle_id"),
            }
        )

    if not rows:
        st.info(
            "Nenhum veículo corresponde aos filtros. Importe o REL_VEICULOS e, "
            "em seguida, a planilha de OS."
        )
        return

    display = pd.DataFrame(
        [
            {key: value for key, value in row.items() if key != "_vehicle_id"}
            for row in rows
        ]
    )
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("### Histórico por veículo")

    options = {}
    for row in rows:
        label = " • ".join(
            value
            for value in [
                row.get("Placa") or "SEM PLACA",
                row.get("Veículo"),
                row.get("Cliente"),
            ]
            if value
        )
        options[label] = row["_vehicle_id"]

    selected_label = st.selectbox(
        "Veículo / cliente",
        list(options.keys()),
    )
    vehicle_id = options[selected_label]
    selected_journey = next(
        journey for journey in journeys if journey["vehicle_id"] == vehicle_id
    )

    st.caption(
        selected_journey.get("maintenance_status_reason")
        or "Sem classificação calculada."
    )

    orders = list(
        db.service_orders.find({"vehicle_id": vehicle_id}).sort(
            "service_date", -1
        )
    )

    if orders:
        service_rows = []
        for order in orders:
            service_rows.append(
                {
                    "OS": order.get("os_number"),
                    "Data": order.get("service_date"),
                    "KM": order.get("os_km"),
                    "Empresa": order.get("company_name"),
                    "Tipo": order.get("type_description"),
                    "Serviços": order.get("service_amount"),
                    "Produtos": order.get("product_amount"),
                    "Total": order.get("total_amount"),
                    "Proprietário da OS": order.get("owner_name"),
                    "Vínculo": order.get("link_status"),
                }
            )

        st.dataframe(
            pd.DataFrame(service_rows),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Nenhuma OS vinculada a este veículo.")

    if can(user, "import.execute"):
        unmatched = db.service_orders.count_documents(
            {"vehicle_id": None}
        )
        if unmatched:
            with st.expander(
                f"OS ainda sem veículo no REL_VEICULOS ({unmatched})"
            ):
                sample = list(
                    db.service_orders.find(
                        {"vehicle_id": None},
                        {
                            "os_number": 1,
                            "service_date": 1,
                            "chassis": 1,
                            "plate": 1,
                            "owner_name": 1,
                            "company_name": 1,
                        },
                    ).sort("service_date", -1).limit(100)
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "OS": row.get("os_number"),
                                "Data": row.get("service_date"),
                                "Chassi": row.get("chassis"),
                                "Placa": row.get("plate"),
                                "Proprietário": row.get("owner_name"),
                                "Empresa": row.get("company_name"),
                            }
                            for row in sample
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
