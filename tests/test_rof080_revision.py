"""Cobertura de código, motorização, deduplicação de OS e evidência não conclusiva."""
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook

from src.revision_taxonomy import (
    DEFAULT_CATALOG, fuel_for_model, parse_evidence, possible_revision_numbers, read_catalog,
)
from src.rof080_importer import _aggregate, _choose_evidence, preview_rof080


def test_flex_diesel_share_code_without_mixing_ordinals():
    codes = dict(DEFAULT_CATALOG)
    assert parse_evidence("0010F38", "", "", "STRADA 1.3 FLEX", codes)["revision_number"] == 4
    assert parse_evidence("0010F38", "", "", "TORO DIESEL", codes)["revision_number"] == 2
    assert parse_evidence("0010F38", "", "", "SEM MODELO", codes)["confidence"] == "ambiguo"
    assert parse_evidence("4A.REV.FLEX/2A.REV.DIESEL", "", "", "TORO DIESEL", codes)["revision_number"] == 2


def test_conservative_signal_classification():
    codes = dict(DEFAULT_CATALOG)
    assert parse_evidence("ALINHAMENTO", "", "2° revisão feita", "ARGO FLEX", codes)["confidence"] == "observacao"
    assert parse_evidence("REVISÃO 20.000 KM", "", "", "ARGO FLEX", codes)["revision_number"] is None
    assert parse_evidence("REVISAO GERAL DO CABECOTE", "", "", "ARGO FLEX", codes) is None
    assert parse_evidence("SEXTA REVISAO FLEX /TERC", "", "", "TORO DIESEL", codes)["confidence"] == "ambiguo"
    assert possible_revision_numbers("18A. REV, FLEX/9A. REV. DIESEL", "TORO DIESEL") == [9]


def _workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "ROF080_ServicoOficinaMod2_Excel"
    ws.append(["Mala Direta - Serviços Oficina"])
    for _ in range(4):
        ws.append([None])
    headers = ["DEALER NUMBER", "CNPJ/CPF DO CLIENTE", "NOME DO CLIENTE",
               "ORDEM SERV.", "OS  OBSERVAÇÃO", "SERVICOS", "DESCRIÇÃO",
               "DATA ABERT.", "DATA ENCER.", "KM", "PLACA", "CHASSI",
               "MODELO DESCRICAO", "TOTAL PECAS", "TOTAL SERVICOS",
               "CNPJ CONCESSIONARIA", "NOME CONCESSIONARIA"]
    ws.append(headers)
    def line(os, service, note=""):
        ws.append(["91342", "00000000001", "Nome", os, note, service, "",
                   datetime(2025, 3, 10), datetime(2025, 3, 11), 20200,
                   "ABC1D23", "9BD00000000000000", "TORO DIESEL",
                   50, 100, "00000000000100", "AUTOVEMA"])
    line("321", "4A.REV.FLEX/2A.REV.DIESEL", "2ª revisão")
    line("321", "ALINHAMENTO", "2ª revisão")
    line("322", "ALINHAMENTO", "3ª revisão")
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_preview_and_aggregation_deduplicates_order():
    data = _workbook()
    preview = preview_rof080(data)
    assert len(preview) == 3
    orders, stats = _aggregate(data, dict(DEFAULT_CATALOG), None)
    assert stats["rows_received"] == 3
    assert stats["unique_orders"] == 2
    first = next(o for o in orders.values() if o["os_number"] == "321")
    second = next(o for o in orders.values() if o["os_number"] == "322")
    assert first["service_amount"] == 200
    assert _choose_evidence(first)["revision_number"] == 2
    assert _choose_evidence(first)["confidence"] == "servico"
    assert _choose_evidence(second)["confidence"] == "observacao"


def test_catalog_preserves_codes_with_leading_zeros():
    wb = Workbook()
    ws = wb.active
    ws.title = "Anomalias"
    ws.append(["CÓDIGO LOCAL", "ANOMALIA", "DESCRIÇÃO"])
    ws.append(["0010F38", "AC", "4ª REVISÃO FLEX / 2ª REVISÃO DIESEL"])
    stream = BytesIO()
    wb.save(stream)
    rows = read_catalog(stream.getvalue())
    assert rows == [{"code": "0010F38", "description": "4ª REVISÃO FLEX / 2ª REVISÃO DIESEL"}]
