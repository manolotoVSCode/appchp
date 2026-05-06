# tests/test_cli_cogen.py
from __future__ import annotations
import sqlite3
import pytest
from pathlib import Path

from storage.schema import init_db
from cli.main import procesar_factura_cfe, procesar_factura_gas, generar_analisis_cogen

CFE_FIXTURE = Path("invoices/CFE/P2 2023_11 NOVIEMBRE.pdf")
GAS_FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture
def conn_con_facturas(tmp_path):
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    procesar_factura_cfe(CFE_FIXTURE, c)
    procesar_factura_gas(GAS_FIXTURE, c)
    yield c, tmp_path
    c.close()


def test_genera_archivo_xlsx(conn_con_facturas):
    conn, tmp_path = conn_con_facturas
    out = tmp_path / "analisis.xlsx"
    result = generar_analisis_cogen(conn, out)
    assert result.exists()
    assert result.suffix == ".xlsx"


def test_xlsx_tiene_datos(conn_con_facturas):
    conn, tmp_path = conn_con_facturas
    out = tmp_path / "analisis.xlsx"
    generar_analisis_cogen(conn, out)
    import openpyxl
    wb = openpyxl.load_workbook(out)
    ws = wb["Análisis Mensual"]
    assert ws.max_row >= 3  # encabezado + 1 mes + totales


def test_devuelve_path(conn_con_facturas):
    conn, tmp_path = conn_con_facturas
    out = tmp_path / "analisis.xlsx"
    result = generar_analisis_cogen(conn, out)
    assert isinstance(result, Path)
    assert result == out
