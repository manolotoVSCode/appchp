from __future__ import annotations
import sqlite3
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from models.gas_invoice import GasInvoice, GasConcepto
from storage.schema import init_db
from storage.repository import save_gas_invoice, load_gas_invoice, list_gas_invoices
from parsers.gas import get_gas_parser

FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    yield c
    c.close()


@pytest.fixture
def inv():
    return get_gas_parser().parse(FIXTURE)


def test_save_devuelve_id(conn, inv):
    fid = save_gas_invoice(conn, inv)
    assert isinstance(fid, int) and fid > 0


def test_load_recupera_campos_simples(conn, inv):
    fid = save_gas_invoice(conn, inv)
    cargada = load_gas_invoice(conn, fid)
    assert cargada.uuid_cfdi.lower() == "59030c00-01f5-4dc9-bda1-25d579b23095"
    assert cargada.periodo_inicio == date(2023, 11, 1)
    assert cargada.consumo_total_gj == Decimal("106445.1830")
    assert cargada.subtotal_mxn == Decimal("8460263.13")
    assert cargada.total_mxn == Decimal("9813905.23")


def test_load_recupera_conceptos(conn, inv):
    fid = save_gas_invoice(conn, inv)
    cargada = load_gas_invoice(conn, fid)
    assert len(cargada.conceptos) == 2
    claves = {c.clave_producto for c in cargada.conceptos}
    assert claves == {"83101601", "78102101"}


def test_load_factura_inexistente(conn):
    with pytest.raises(ValueError, match="Factura de gas"):
        load_gas_invoice(conn, 9999)


def test_list_devuelve_facturas(conn, inv):
    save_gas_invoice(conn, inv)
    rows = list_gas_invoices(conn)
    assert len(rows) == 1
    assert rows[0]["folio"] == "I00000547"


def test_mismo_cliente_no_duplica(conn, inv):
    save_gas_invoice(conn, inv)
    save_gas_invoice(conn, inv)
    cur = conn.execute("SELECT COUNT(*) FROM clientes WHERE rfc = 'ITI170630377'")
    assert cur.fetchone()[0] == 1
