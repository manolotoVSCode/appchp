# tests/test_web.py
from __future__ import annotations
import pytest
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
