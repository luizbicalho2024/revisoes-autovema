from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..importer import import_rel_veiculos, preview_rel
from ..security import require_permission
from ..service_importer import (
    import_service_orders,
    preview_service_orders,
)
from ..ui import page_header


def _already_imported(db: Database, file_bytes: bytes, import_type: str | None = None):
    query = {
        "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "status": "success",
    }
    if import_type:
        query["import_type"] = import_type
    return db.import_jobs.find_one(
        query,
        sort=[("started_at", -1)],
    )


def _render_rel_tab(db: Database, user: dict) -> None:
    st.markdown("### Clientes, veículos e vendas")
    st.caption(
        "Use o relatório REL_VEICULOSVENDIDOSPORPERIODO. "
        "A reimportação atualiza registros existentes sem duplicá-los."
    )

    uploaded = st.file_uploader(
        "REL_VEICULOS (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=False,
        key="rel_veiculos_upload",
    )
    if not uploaded:
        return

    file_bytes = uploaded.getvalue()
    try:
        preview, errors = preview_rel(file_bytes, max_rows=12)
    except Exception as exc:
        st.error(f"Não foi possível ler a planilha: {exc}")
        return

    if errors:
        for error in errors:
            st.error(error)
        return

    st.success("Estrutura REL_VEICULOS reconhecida.")
    st.dataframe(preview, hide_index=True, use_container_width=True)

    if _already_imported(db, file_bytes):
        st.warning(
            "Este arquivo já foi importado. Reimportar é seguro: "
            "os registros serão atualizados, não duplicados."
        )

    confirm = st.checkbox(
        "Confirmo a importação da base de clientes e veículos.",
        key="rel_confirm",
    )
    if st.button(
        "Importar REL_VEICULOS",
        type="primary",
        disabled=not confirm,
        use_container_width=True,
        key="rel_process",
    ):
        with st.spinner(
            "Consolidando clientes, veículos, vendas e jornadas..."
        ):
            try:
                result = import_rel_veiculos(
                    db,
                    file_bytes,
                    uploaded.name,
                    user,
                )
            except Exception as exc:
                st.error(f"Falha na importação: {exc}")
                return

        data = result.as_dict()
        st.success("REL_VEICULOS importado.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Linhas válidas", data["rows_valid"])
        c2.metric("Clientes novos", data["customers_upserted"])
        c3.metric("Veículos novos", data["vehicles_upserted"])
        c4.metric("Vendas novas", data["sales_upserted"])


def _render_service_tab(db: Database, user: dict) -> None:
    st.markdown("### Ordens de serviço / pós-venda")
    st.caption(
        "Use o relatório ROF001 de OS. O sistema consolida linhas repetidas da "
        "mesma OS, concilia o chassi com a base de veículos e separa OS anterior "
        "à venda, troca de proprietário e histórico válido do cliente atual."
    )

    uploaded = st.file_uploader(
        "ROF001_OS (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=False,
        key="service_orders_upload",
    )
    if not uploaded:
        return

    file_bytes = uploaded.getvalue()

    try:
        preview, errors = preview_service_orders(
            file_bytes,
            max_rows=12,
        )
    except Exception as exc:
        st.error(f"Não foi possível ler a planilha de OS: {exc}")
        return

    if errors:
        for error in errors:
            st.error(error)
        return

    st.success("Estrutura de ordens de serviço reconhecida.")
    st.dataframe(preview, hide_index=True, use_container_width=True)

    if _already_imported(db, file_bytes, "service_orders"):
        st.warning(
            "Este mesmo relatório de OS já foi importado. A reimportação é "
            "idempotente e atualizará as ordens existentes."
        )

    st.info(
        "Importante: este relatório não identifica explicitamente '1ª revisão', "
        "'2ª revisão' etc. O sistema cria sugestões por chassi, data e quilometragem; "
        "a confirmação da revisão continua auditável na Jornada de Revisões."
    )

    confirm = st.checkbox(
        "Confirmo a importação e conciliação das ordens de serviço.",
        key="service_confirm",
    )

    if st.button(
        "Importar e conciliar OS",
        type="primary",
        disabled=not confirm,
        use_container_width=True,
        key="service_process",
    ):
        with st.spinner(
            "Consolidando ordens de serviço e conciliando com veículos..."
        ):
            try:
                result = import_service_orders(
                    db,
                    file_bytes,
                    uploaded.name,
                    user,
                )
            except Exception as exc:
                st.error(f"Falha na importação de OS: {exc}")
                return

        data = result.as_dict()
        st.success("Ordens de serviço importadas e conciliadas.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("OS únicas", data["unique_orders"])
        c2.metric("OS vinculadas", data["matched_orders"])
        c3.metric("Veículos conciliados", data["vehicles_reconciled"])
        c4.metric("Sugestões de revisão", data["revision_candidates"])

        details = pd.DataFrame(
            [
                {
                    "Indicador": "Linhas recebidas",
                    "Quantidade": data["rows_received"],
                },
                {
                    "Indicador": "OS sem veículo na base",
                    "Quantidade": data["unmatched_orders"],
                },
                {
                    "Indicador": "OS posteriores à venda",
                    "Quantidade": data["post_sale_orders"],
                },
                {
                    "Indicador": "Divergência de proprietário",
                    "Quantidade": data["owner_mismatches"],
                },
                {
                    "Indicador": "OS novas",
                    "Quantidade": data["orders_upserted"],
                },
                {
                    "Indicador": "OS atualizadas",
                    "Quantidade": data["orders_updated"],
                },
            ]
        )
        st.dataframe(
            details,
            hide_index=True,
            use_container_width=True,
        )


def render(db: Database, user: dict) -> None:
    require_permission(user, "import.execute")
    page_header(
        "Importações",
        "Atualize a base comercial e o histórico de pós-venda sem duplicidade.",
    )

    rel_tab, service_tab = st.tabs(
        ["REL_VEICULOS", "OS / Serviços"]
    )

    with rel_tab:
        _render_rel_tab(db, user)

    with service_tab:
        _render_service_tab(db, user)
