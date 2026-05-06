# tests/test_cli_cogen.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from cli.main import procesar_factura_cfe, procesar_factura_gas, generar_analisis_cogen

CFE_FIXTURE = Path("invoices/CFE/P2 2023_11 NOVIEMBRE.pdf")
GAS_FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


def _make_supabase_mock():
    """Mock del cliente Supabase para insert/upsert de CFE y Gas."""
    mock = MagicMock()
    _cfe_id_counter = iter(range(1, 1000))
    _gas_id_counter = iter(range(1001, 2000))

    def table_router(name):
        t = MagicMock()
        if name == "clientes":
            t.upsert.return_value.execute.return_value.data = [{"id": 1}]
        elif name == "cfe_facturas":
            t.insert.return_value.execute.return_value.data = [{"id": next(_cfe_id_counter)}]
        elif name == "gas_facturas":
            t.insert.return_value.execute.return_value.data = [{"id": next(_gas_id_counter)}]
        else:
            t.insert.return_value.execute.return_value.data = []
        return t

    mock.table.side_effect = table_router
    return mock


@pytest.fixture
def facturas_en_supabase(tmp_path):
    """Parsea las facturas reales y las persiste via mock. Devuelve (cfe_invoices, gas_invoices, tmp_path)."""
    from parsers.cfe import get_cfe_parser
    from parsers.gas import get_gas_parser

    cfe_parser = get_cfe_parser("GDMTH")
    cfe_invoice = cfe_parser.parse(CFE_FIXTURE)

    gas_parser = get_gas_parser()
    gas_invoice = gas_parser.parse(GAS_FIXTURE)

    return [cfe_invoice], [gas_invoice], tmp_path


def test_genera_archivo_xlsx(facturas_en_supabase, tmp_path):
    cfe_invoices, gas_invoices, _ = facturas_en_supabase
    out = tmp_path / "analisis.xlsx"

    with patch("storage.repository.get_all_cfe_invoices", return_value=cfe_invoices), \
         patch("storage.repository.get_all_gas_invoices", return_value=gas_invoices), \
         patch("storage.repository._supabase", MagicMock()):
        result = generar_analisis_cogen(out)

    assert result.exists()
    assert result.suffix == ".xlsx"


def test_xlsx_tiene_datos(facturas_en_supabase, tmp_path):
    cfe_invoices, gas_invoices, _ = facturas_en_supabase
    out = tmp_path / "analisis.xlsx"

    with patch("storage.repository.get_all_cfe_invoices", return_value=cfe_invoices), \
         patch("storage.repository.get_all_gas_invoices", return_value=gas_invoices), \
         patch("storage.repository._supabase", MagicMock()):
        generar_analisis_cogen(out)

    import openpyxl
    wb = openpyxl.load_workbook(out)
    ws = wb["Análisis Mensual"]
    assert ws.max_row >= 3  # encabezado + 1 mes + totales


def test_devuelve_path(facturas_en_supabase, tmp_path):
    cfe_invoices, gas_invoices, _ = facturas_en_supabase
    out = tmp_path / "analisis.xlsx"

    with patch("storage.repository.get_all_cfe_invoices", return_value=cfe_invoices), \
         patch("storage.repository.get_all_gas_invoices", return_value=gas_invoices), \
         patch("storage.repository._supabase", MagicMock()):
        result = generar_analisis_cogen(out)

    assert isinstance(result, Path)
    assert result == out
