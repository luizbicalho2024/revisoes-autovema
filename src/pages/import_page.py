from __future__ import annotations

import pandas as pd
import streamlit as st
from pymongo.database import Database

from ..importer import import_rel_veiculos, preview_rel
from ..security import require_permission
from ..ui import page_header


def render(db: Database, user: dict) -> None:
    require_permission(user, "import.execute")
    page_header(
        "Importar REL_VEICULOS",
        "Atualização idempotente: clientes, veículos e vendas existentes são atualizados por chaves estáveis, sem duplicação.",
    )

    st.markdown(
        """
        A importação aceita a mesma estrutura do relatório **REL_VEICULOSVENDIDOSPORPERIODO**.  
        O sistema usa CPF/CNPJ (ou código da pessoa), chassi (ou código do veículo) e código da nota fiscal para identificar registros existentes.
        """
    )

    uploaded = st.file_uploader("Selecione o arquivo .xlsx", type=["xlsx"], accept_multiple_files=False)
    if not uploaded:
        st.caption("Nenhum dado é armazenado no GitHub. O arquivo é processado em memória e os registros são gravados diretamente no MongoDB Atlas.")
        return

    file_bytes = uploaded.getvalue()
    try:
        preview, errors = preview_rel(file_bytes, max_rows=12)
    except Exception as exc:
        st.error(f"Não foi possível ler a planilha: {exc}")
        return

    if errors:
        for err in errors:
            st.error(err)
        return

    st.success("Estrutura reconhecida.")
    st.markdown("#### Prévia")
    st.dataframe(preview, hide_index=True, use_container_width=True)

    previous = db.import_jobs.find_one({"file_sha256": __import__("hashlib").sha256(file_bytes).hexdigest(), "status": "success"}, sort=[("started_at", -1)])
    if previous:
        st.warning("Este mesmo arquivo já foi importado anteriormente. Reimportar é seguro: os registros serão atualizados, não duplicados.")

    confirm = st.checkbox("Confirmo a importação desta base no MongoDB Atlas.")
    if st.button("Processar importação", type="primary", disabled=not confirm, use_container_width=True):
        with st.spinner("Validando e consolidando clientes, veículos, vendas e jornadas..."):
            try:
                result = import_rel_veiculos(db, file_bytes, uploaded.name, user)
            except Exception as exc:
                st.error(f"Falha na importação: {exc}")
                return

        st.success("Importação concluída.")
        data = result.as_dict()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Linhas válidas", data["rows_valid"])
        c2.metric("Clientes novos", data["customers_upserted"])
        c3.metric("Veículos novos", data["vehicles_upserted"])
        c4.metric("Vendas novas", data["sales_upserted"])

        st.dataframe(
            pd.DataFrame(
                [
                    {"Indicador": "Clientes atualizados", "Quantidade": data["customers_updated"]},
                    {"Indicador": "Veículos atualizados", "Quantidade": data["vehicles_updated"]},
                    {"Indicador": "Vendas atualizadas", "Quantidade": data["sales_updated"]},
                    {"Indicador": "Jornadas criadas", "Quantidade": data["journeys_upserted"]},
                    {"Indicador": "Linhas ignoradas", "Quantidade": data["rows_skipped"]},
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        if data["errors"]:
            with st.expander("Avisos de linhas ignoradas"):
                st.write("\n".join(data["errors"][:100]))
