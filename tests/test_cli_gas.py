from __future__ import annotations
import sqlite3
import pytest
from pathlib import Path

from storage.schema import init_db
from storage.repository import load_gas_invoice
from cli.main import procesar_factura_gas

FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    yield c
    c.close()


def test_procesar_factura_gas_devuelve_id(conn):
    fid = procesar_factura_gas(FIXTURE, conn)
    assert isinstance(fid, int) and fid > 0


def test_factura_gas_persiste_en_db(conn):
    fid = procesar_factura_gas(FIXTURE, conn)
    inv = load_gas_invoice(conn, fid)
    assert inv.folio == "I00000547"


def test_pdf_gas_inexistente_lanza_error(conn):
    with pytest.raises(FileNotFoundError):
        procesar_factura_gas(Path("invoices/Gas/no_existe.pdf"), conn)
