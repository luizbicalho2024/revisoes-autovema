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
from ..revision_taxonomy import read_catalog
from ..rof080_importer import import_rof080, preview_rof080
from ..sigmec_importer import import_sigmec, preview_sigmec
from ..revision_taxonomy import catalog_from_database
from ..repositories import audit
from datetime import datetime, timezone


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


def _render_catalog_tab(db: Database, user: dict) -> None:
    st.markdown("### Catálogo de códigos de revisão")
    st.caption("Importe os códigos locais da planilha anomalias_revisao.xlsx. "
               "Os 23 códigos conhecidos já são suportados; reimportar o catálogo os atualiza.")
    uploaded = st.file_uploader("Catálogo de anomalias (.xlsx)", type=["xlsx"], key="revision_catalog")
    if not uploaded:
        st.metric("Códigos personalizados cadastrados", db.revision_catalog.count_documents({}))
        return
    try:
        rows = read_catalog(uploaded.getvalue())
    except Exception as exc:
        st.error(f"Erro ao ler catálogo: {exc}")
        return
    st.dataframe(pd.DataFrame(rows).head(35), hide_index=True, use_container_width=True)
    if st.button("Importar/atualizar códigos", type="primary", key="catalog_save"):
        now = datetime.now(timezone.utc)
        for row in rows:
            db.revision_catalog.update_one({"_id": row["code"]},
                {"$set": {"description": row["description"], "updated_at": now,
                          "updated_by": user.get("email")}}, upsert=True)
        audit(db, user, "revision_catalog_imported", "revision_catalog", "catalog",
              {"codes": len(rows)})
        st.success(f"{len(rows)} códigos de revisão cadastrados/atualizados.")


def _render_rof080_tab(db: Database, user: dict) -> None:
    st.markdown("### ROF080 – Histórico de serviços de oficina")
    st.caption("Importe a planilha AUTOVEMA PVH.xlsx. Agrupamos itens pela OS e "
               "identificamos revisões pelas linhas de serviço, pelo catálogo e "
               "pelas observações. Só OS encerrada e vinculada ao veículo pode ser "
               "confirmada automaticamente. Observações isoladas exigem conferência.")
    uploaded = st.file_uploader("ROF080 (.xlsx)", type=["xlsx"], key="rof080_upload")
    if not uploaded:
        return
    content = uploaded.getvalue()
    try:
        preview = preview_rof080(content)
    except Exception as exc:
        st.error(f"Planilha ROF080 inválida: {exc}")
        return
    st.dataframe(pd.DataFrame(preview), hide_index=True, use_container_width=True)
    imported = _already_imported(db, content, "rof080")
    if imported:
        st.info("Este mesmo arquivo já foi importado integralmente. Não será processado novamente.")
    confirm = st.checkbox("Confirmo que a planilha contém dados operacionais autorizados.", key="rof080_confirm")
    if st.button("Importar histórico e calcular revisões", type="primary", key="rof080_process",
                 use_container_width=True, disabled=not confirm or bool(imported)):
        status = st.empty()
        def progress(n: int) -> None:
            status.caption(f"Linhas analisadas: {n:,}".replace(",", "."))
        try:
            with st.spinner("Processando arquivo grande, consolidando OS e vinculando revisões..."):
                summary = import_rof080(db, content, uploaded.name, user, progress=progress)
        except Exception as exc:
            st.error(f"Importação interrompida: {exc}")
            return
        status.empty()
        st.success("Importação ROF080 concluída; dados disponíveis nas métricas.")
        cols = st.columns(4)
        cols[0].metric("Linhas", summary.get("rows_received", 0))
        cols[1].metric("OS distintas", summary.get("unique_orders", 0))
        cols[2].metric("Revisões comprovadas", summary.get("confirmed_revisions", 0))
        cols[3].metric("Para análise", summary.get("orders_with_revision_signal", 0)
                       - summary.get("confirmed_revisions", 0))
        st.json(summary, expanded=False)


def _render_sigmec_tab(db: Database, user: dict) -> None:
    st.markdown("### SIGMEC (.001) – Códigos de intervenções das revisões")
    st.caption(
        "Importe arquivos SIGMEC de 2024, 2025 e 2026. O sistema lê os registros #C/#E, "
        "reconhece a OS e o código local, e cruza com o histórico ROF080. "
        "Não usa placa ou modelo isoladamente para confirmar revisões. "
        "Revisão de entrega não conta como revisão periódica."
    )
    uploaded = st.file_uploader(
        "Arquivos SIGMEC (.001) – selecione um ou vários",
        type=["001"], accept_multiple_files=True, key="sigmec001_upload",
    )
    if not uploaded:
        st.info("Importe o ROF080 e o catálogo de códigos antes dos arquivos SIGMEC para aumentar o aproveitamento.")
        return
    catalog = catalog_from_database(db)
    content_by_hash = {}
    preview_rows = []
    for file in uploaded:
        content = file.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        if digest in content_by_hash:
            preview_rows.append({
                "Arquivo": file.name, "OS": "—", "Códigos de revisão": "—", "Outras revisões para análise": "—",
                "Situação": "Duplicado de " + content_by_hash[digest][0],
            })
            continue
        try:
            report = preview_sigmec(content, file.name, catalog)
        except Exception as exc:
            st.error(f"Não foi possível validar {file.name}: {exc}")
            return
        existing = _already_imported(db, content, "sigmec001")
        content_by_hash[digest] = (file.name, content)
        preview_rows.append({
            "Arquivo": file.name,
            "OS": report["orders"],
            "Códigos de revisão": report["revision_codes"],
            "Outras revisões para análise": report["unmapped_revision_items"],
            "Situação": "Já importado" if existing else "Pronto para processar",
        })
    st.dataframe(pd.DataFrame(preview_rows), hide_index=True, use_container_width=True)
    st.info(
        "O código confirma qual intervenção foi registrada. Para atualizar uma revisão como "
        "comprovada, exigimos OS correspondente no ROF080, etapa inequívoca, "
        "encerramento, vínculo do veículo e elegibilidade após a venda. "
        "As demais ficam disponíveis para conferência."
    )
    confirmation = st.checkbox(
        "Confirmo a importação dos arquivos SIGMEC e a conciliação pelos códigos de OS.",
        key="sigmec001_confirm",
    )
    if st.button("Importar SIGMEC e cruzar revisões", type="primary",
                 disabled=not confirmation, use_container_width=True,
                 key="sigmec001_process"):
        result_rows = []
        progress_status = st.empty()
        for digest, (filename, content) in content_by_hash.items():
            try:
                with st.spinner(f"Analisando {filename} ..."):
                    def progress(done: int, total: int) -> None:
                        progress_status.caption(f"{filename}: {done:,}/{total:,} OS analisadas".replace(",", "."))
                    result = import_sigmec(db, content, filename, user, progress=progress)
            except Exception as exc:
                st.error(f"Importação de {filename} interrompida: {type(exc).__name__}: {exc}")
                break
            result_rows.append({
                "Arquivo": filename,
                "OS lidas": result.get("orders", 0),
                "OS no ROF080": result.get("os_localizada", 0),
                "Códigos de revisão": result.get("catalog_revision_items", 0),
                "Outras revisões para análise": result.get("unmapped_revision_items", 0),
                "Evidências qualificadas": result.get("events_qualified", 0),
                "Elegíveis para comprovação": result.get("events_eligible_for_confirming", 0),
                "Situação": "Já importado" if result.get("already_imported") else "Concluído",
            })
        progress_status.empty()
        if result_rows:
            st.success("Processamento SIGMEC finalizado para os arquivos indicados.")
            st.dataframe(pd.DataFrame(result_rows), hide_index=True, use_container_width=True)
        st.caption(
            "Uma evidência qualificada não equivale necessariamente a uma revisão confirmada "
            "para o comprador atual. Consulte Histórico da Oficina e Diagnóstico de Dados."
        )


def render(db: Database, user: dict) -> None:
    require_permission(user, "import.execute")
    page_header(
        "Importações",
        "Atualize a base comercial e o histórico de pós-venda sem duplicidade.",
    )

    rel_tab, service_tab, catalog_tab, rof080_tab, sigmec_tab = st.tabs(
        ["REL_VEICULOS", "ROF001 / OS", "Códigos de revisão", "ROF080 / Histórico", "SIGMEC / Códigos"]
    )

    with rel_tab:
        _render_rel_tab(db, user)

    with service_tab:
        _render_service_tab(db, user)

    with catalog_tab:
        _render_catalog_tab(db, user)

    with rof080_tab:
        _render_rof080_tab(db, user)

    with sigmec_tab:
        _render_sigmec_tab(db, user)
