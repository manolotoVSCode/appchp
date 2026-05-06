# tests/test_web.py
from __future__ import annotations
import pytest
from pathlib import Path
from web.app import create_app

INVOICES_DIR = "invoices"


@pytest.fixture(scope="module")
def client():
    """Flask test client cargado con los 24 PDFs reales.
    scope=module para parsear los PDFs sólo una vez.
    Espera a que el hilo de carga termine antes de ceder el cliente.
    """
    import time
    app = create_app(INVOICES_DIR)
    app.config["TESTING"] = True
    while app.config.get("CARGANDO", False):
        time.sleep(0.5)
    with app.test_client() as c:
        yield c


def test_dashboard_status_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_dashboard_es_html(client):
    resp = client.get("/")
    assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data


def test_dashboard_contiene_ebitda(client):
    resp = client.get("/")
    assert b"EBITDA" in resp.data


def test_dashboard_contiene_12_periodos(client):
    """La tabla debe tener filas para los 12 meses."""
    resp = client.get("/")
    assert resp.data.count(b"mes-row") == 12


def test_dashboard_contiene_total_anual(client):
    resp = client.get("/")
    assert b"TOTAL ANUAL" in resp.data


def test_carga_desde_db_existente(tmp_path):
    """Si existe un db_path, la app carga desde él sin parsear todos los PDFs."""
    import sqlite3
    import time
    from storage.schema import init_db
    from cli.main import procesar_factura_cfe, procesar_factura_gas

    # Construir un DB mínimo con 1 factura CFE + 1 gas
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    procesar_factura_cfe(Path("invoices/CFE/P2 2023_11 NOVIEMBRE.pdf"), conn)
    procesar_factura_gas(Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf"), conn)
    conn.close()

    # Crear app con db_path — debe cargar desde la DB
    app = create_app("invoices", db_path=str(db_file))
    app.config["TESTING"] = True
    while app.config.get("CARGANDO", False):
        time.sleep(0.1)

    with app.test_client() as c:
        resp = c.get("/")
    assert resp.status_code == 200
    assert resp.data.count(b"mes-row") == 1
