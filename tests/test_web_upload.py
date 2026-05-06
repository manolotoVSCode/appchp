# tests/test_web_upload.py
from __future__ import annotations
import io
import pytest
from pathlib import Path
from web.app import create_app

INVOICES_DIR = "invoices"


@pytest.fixture(scope="module")
def client():
    import time
    app = create_app(INVOICES_DIR)
    app.config["TESTING"] = True
    while app.config.get("CARGANDO", False):
        time.sleep(0.5)
    with app.test_client() as c:
        yield c


def test_upload_cfe_pdf_returns_200(client):
    """Uploading a real CFE PDF must return 200 with procesados=1."""
    pdf_path = Path("invoices/CFE/P2 2023_11 NOVIEMBRE.pdf")
    with open(pdf_path, "rb") as f:
        data = {"facturas": (io.BytesIO(f.read()), pdf_path.name)}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["procesados"] >= 1
    assert body["errores"] == []


def test_upload_gas_pdf_returns_200(client):
    """Uploading a real Gas PDF must return 200 with procesados=1."""
    pdf_path = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")
    with open(pdf_path, "rb") as f:
        data = {"facturas": (io.BytesIO(f.read()), pdf_path.name)}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["procesados"] >= 1
    assert body["errores"] == []


def test_upload_non_pdf_returns_error(client):
    """Uploading a non-PDF file must return 200 with an error entry."""
    data = {"facturas": (io.BytesIO(b"not a pdf"), "fake.pdf")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["errores"] != []


def test_upload_refreshes_dashboard(client):
    """After upload, dashboard must return 200."""
    resp = client.get("/")
    assert resp.status_code == 200
