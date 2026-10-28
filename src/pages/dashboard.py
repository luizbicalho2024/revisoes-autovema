"""Painel unico de sequencia de revisoes: SIGMEC como unica fonte das etapas.

Nenhuma revisao e inferida da jornada, texto do ROF080 ou bonus.
O ROF080 so fornece dados auxiliares para localizar veiculo, proprietario e data.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..revision_audit import csv_bytes
from ..revision_taxonomy import catalog_from_database
from ..security import can, get_user_scope
from ..sigmec_awards import LEVELS, STAGES, analyze_awards
from ..ui import page_header


ALL_BANDS = [LEVELS[n] for n in range(5, 0, -1)]
OTHER_BANDS = ["Fora da sequência", "Cronologia a conferir", "Proprietário a validar"]


def _fmt(value: Any) -> str:
    return f"{int(value or 0):,}".replace(",", ".")


def _date(value: Any) -> str:
    return value.strftime("%d/%m/%Y") if isinstance(value, date) else "—"


def _load(db: Database, user: dict[str, Any]) -> dict[str, Any]:
    rows = list(db.sigmec_orders.find({}, {
        "_id": 1, "os_number": 1, "dealer_code": 1, "os_normalized": 1,
        "interventions": 1, "rof080_order_id": 1,
    }))
    refs = {str(row["rof080_order_id"]) for row in rows if row.get("rof080_order_id")}
    services: dict[str, dict[str, Any]] = {}
    ids = list(refs)
    for pos in range(0, len(ids), 350):
        batch = ids[pos:pos + 350]
        for doc in db.service_orders.find({"_id": {"$in": batch}}, {
            "source": 1, "chassis": 1, "owner_document": 1,
            "owner_name": 1, "plate": 1, "model": 1, "closed_at": 1,
            "company_code": 1,
        }):
            services[str(doc["_id"])] = doc
    if user.get("role") != "superadmin":
        scope = {str(code) for code in get_user_scope(user)}
        # OS sem empresa atribuida nao pode ser exibida a usuarios limitados.
        services = {k: v for k, v in services.items()
                    if scope and str(v.get("company_code")) in scope}
        rows = [r for r in rows if str(r.get("rof080_order_id")) in services]
    return analyze_awards(rows, services, catalog_from_database(db))


def _summary_card(col: Any, title: str, number: int) -> None:
    with col:
        st.metric(title, _fmt(number))


def _table_record(row: dict[str, Any]) -> dict[str, Any]:
    output = {
        "Faixa": row["faixa"],
        "Cliente da OS": row["cliente"],
        "Placa": row["placa"] or "—",
        "Modelo": row["modelo"] or "—",
        "Chassi": row["chassi"],
    }
    for n in STAGES:
        entries = row["etapas"].get(n) or []
        output[f"{n}ª revisão"] = (
            " | ".join(f"{_date(v['data'])} · OS {v['os']}" for v in entries)
            if entries else "—"
        )
    output["Candidato à premiação"] = "Sim — validar" if row["premiacao_candidata"] else "Não"
    return output


def render(db: Database, user: dict[str, Any]) -> None:
    page_header("Revisões", "Sequência da 1ª à 5ª revisão por cliente e veículo.")
    try:
        data = _load(db, user)
    except Exception as exc:
        st.error("Não foi possível calcular o painel SIGMEC.")
        st.caption(f"Erro técnico: {type(exc).__name__}")
        return

    bands = data["bands"]
    cols = st.columns(5, gap="small")
    for col, n in zip(cols, (5, 4, 3, 2, 1)):
        _summary_card(col, LEVELS[n], bands.get(LEVELS[n], 0))

    st.caption("Faixas exclusivas por conjunto cliente–veículo: mesmas etapas, mesmo proprietário e datas em sequência. Cada OS conta uma vez por etapa.")

    g1, g2 = st.columns([1.45, 1], gap="large")
    with g1:
        with st.container(border=True):
            st.markdown("**Conjuntos cliente–veículo por sequência**")
            values = pd.DataFrame([
                {"Faixa": LEVELS[n], "Clientes/veículos": bands.get(LEVELS[n], 0)}
                for n in (1, 2, 3, 4, 5)
            ]).set_index("Faixa")
            st.bar_chart(values, horizontal=True, height=275)
    with g2:
        with st.container(border=True):
            st.markdown("**Qualidade da identificação**")
            qa = [
                {"Situação": "Com sequência regular", "Quantidade": sum(bands.get(label, 0) for label in LEVELS.values())},
                {"Situação": "Etapa fora da sequência", "Quantidade": bands.get("Fora da sequência", 0)},
                {"Situação": "Cronologia a conferir", "Quantidade": bands.get("Cronologia a conferir", 0)},
                {"Situação": "Proprietário a validar", "Quantidade": bands.get("Proprietário a validar", 0)},
                {"Situação": "OS sem conciliação", "Quantidade": len(data["issues"])},
            ]
            st.bar_chart(pd.DataFrame(qa).set_index("Situação"), horizontal=True, height=275)

    st.markdown("#### Clientes e veículos por faixa")
    f1, f2, f3 = st.columns([1.8, 1.1, 1], gap="small")
    with f1:
        search = st.text_input("Buscar cliente ou veículo", placeholder="Cliente, placa, chassi ou modelo", key="dh_awards_search").strip().casefold()
    with f2:
        band_filter = st.selectbox("Revisões realizadas em sequência", ["Todas"] + ALL_BANDS + OTHER_BANDS, key="dh_awards_band")
    with f3:
        owner_filter = st.selectbox("Validação do cliente", ["Todos", "Identificado", "A verificar"], key="dh_awards_owner")
    filtered = []
    for row in data["records"]:
        terms = " ".join(str(row.get(k) or "") for k in ("cliente", "placa", "chassi", "modelo")).casefold()
        if search and search not in terms:
            continue
        if band_filter != "Todas" and row["faixa"] != band_filter:
            continue
        if owner_filter == "Identificado" and not row["cliente_verificavel"]:
            continue
        if owner_filter == "A verificar" and row["cliente_verificavel"]:
            continue
        filtered.append(row)

    st.caption(f"{_fmt(len(filtered))} registro(s) de veículo e proprietário nos filtros.")
    if filtered:
        table = [_table_record(row) for row in filtered]
        st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True, height=425)
        if can(user, "reports.export"):
            st.download_button("Exportar relatório filtrado (CSV)", data=csv_bytes(table),
                               file_name="autovema_premiacao_revisoes_sigmec.csv", mime="text/csv",
                               key="dh_awards_csv")
        st.markdown("**Histórico das cinco revisões**")
        chosen_idx = st.selectbox("Selecionar cliente e veículo", range(len(filtered)),
                                  format_func=lambda i: f"{filtered[i]['cliente']} · {filtered[i]['placa'] or filtered[i]['chassi']} · {filtered[i]['faixa']}",
                                  key="dh_awards_choose")
        chosen = filtered[chosen_idx]
        details = []
        for n in STAGES:
            records = chosen["etapas"].get(n) or []
            if records:
                for entry in records:
                    details.append({"Etapa": f"{n}ª revisão", "Data encerramento": _date(entry["data"]),
                                    "OS": entry["os"], "Código SIGMEC": entry["codigo"]})
            else:
                details.append({"Etapa": f"{n}ª revisão", "Data encerramento": "—", "OS": "—", "Código SIGMEC": "—"})
        st.dataframe(pd.DataFrame(details), hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum registro encontrado com os filtros atuais.")

    if user.get("role") == "superadmin":
        with st.expander(f"OS SIGMEC ainda sem classificação segura ({_fmt(len(data['issues']))})", expanded=False):
            st.caption("São códigos SIGMEC sem OS vinculada, com etapa ambígua ou sem encerramento. Não entram nas faixas de premiação.")
            if data["issues"]:
                pending = [{"OS": c["os"], "Código": c["codigo"],
                            "Cliente": c["cliente"] or "—", "Placa": c["placa"] or "—",
                            "Chassi": c["chassi"] or "—", "Motivo": c["motivo"]} for c in data["issues"]]
                st.dataframe(pd.DataFrame(pending), hide_index=True, use_container_width=True, height=280)
                st.download_button("Exportar OS a conferir", data=csv_bytes(pending),
                                   file_name="autovema_sigmec_pendencias.csv", mime="text/csv")
    st.caption("Fonte das etapas: exclusivamente os códigos SIGMEC. O ROF080 identifica chassi, proprietário e encerramento da OS. As faixas são candidaturas para auditoria, não autorizações automáticas de prêmio.")
