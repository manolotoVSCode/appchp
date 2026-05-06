from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest
from cli.main import procesar_factura_cfe
from storage.schema import init_db
from storage.repository import load_cfe_invoice

FIXTURE = Path("tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf")


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    yield conn
    conn.close()


def test_procesar_factura_cfe_devuelve_id(db_conn):
    factura_id = procesar_factura_cfe(FIXTURE, db_conn, tarifa="GDMTH")
    assert isinstance(factura_id, int)
    assert factura_id > 0


def test_factura_persiste_en_db(db_conn):
    factura_id = procesar_factura_cfe(FIXTURE, db_conn, tarifa="GDMTH")
    inv = load_cfe_invoice(db_conn, factura_id)
    assert inv.tarifa == "GDMTH"
    assert inv.numero_servicio == "052231189271"


def test_procesar_tarifa_no_soportada_lanza_error(db_conn):
    with pytest.raises(ValueError, match="no soportada"):
        procesar_factura_cfe(FIXTURE, db_conn, tarifa="GDMTO")


def test_procesar_pdf_inexistente_lanza_error(db_conn):
    with pytest.raises(FileNotFoundError):
        procesar_factura_cfe(Path("no_existe.pdf"), db_conn)
