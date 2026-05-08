# tests/test_contrato_upload.py
"""Tests para el endpoint de upload de facturas por contrato y borrado de facturas."""
from __future__ import annotations

import io
import logging

import pytest
from unittest.mock import MagicMock
from werkzeug.security import generate_password_hash

from models.contrato import Contrato

_HASH = generate_password_hash("test_pass", method="pbkdf2:sha256")

_CLIENTE = {
    "id": 1,
    "nombre": "IBERICA TILES",
    "rfc": "ITI930101AAA",
    "notas": None,
    "created_at": "2024-01-15T10:00:00+00:00",
    "num_cfe": 9,
    "num_gas": 0,
}

_CONTRATO_ELECTRICO = Contrato(
    id=10,
    cliente_id=1,
    nombre="CFE Planta 1",
    tipo="electrico",
    identificador_real="812990300016",
    notas=None,
    created_at="2024-01-15T10:00:00+00:00",
)

_CONTRATO_GAS = Contrato(
    id=20,
    cliente_id=1,
    nombre="Gas Planta 1",
    tipo="gas",
    identificador_real="CUENTA-001",
    notas=None,
    created_at="2024-01-15T10:00:00+00:00",
)


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("APP_USER", "operador")
    monkeypatch.setenv("APP_PASSWORD_HASH", _HASH)
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture()
def auth_client(app, monkeypatch):
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE])
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})
    return c


def _fake_pdf(nombre="factura.pdf"):
    return (io.BytesIO(b"%PDF-1.4 fake"), nombre)


def _mock_cfe_invoice(numero_servicio="812990300016"):
    inv = MagicMock()
    inv.numero_servicio = numero_servicio
    inv.advertencias = []
    return inv


def _mock_gas_invoice(cuenta_contrato="CUENTA-001"):
    inv = MagicMock()
    inv.cuenta_contrato = cuenta_contrato
    inv.advertencias = []
    return inv


def _setup_electrico(monkeypatch):
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)


def _setup_gas(monkeypatch):
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_GAS)


# ── Test 1: Upload CFE exitoso ────────────────────────────────────────────────

def test_upload_cfe_exitoso(auth_client, monkeypatch):
    """Upload válido de factura CFE → procesados=1, exitosos con nombre_canonico."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice()
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, contrato_id=None: (1, "2024 ENE CFE 812990300016"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert data["exitosos"][0]["nombre_canonico"] == "2024 ENE CFE 812990300016"
    assert data["errores"] == []
    assert data["pendientes_confirmacion"] == []


# ── Test 2: Upload Gas exitoso ────────────────────────────────────────────────

def test_upload_gas_exitoso(auth_client, monkeypatch):
    """Upload válido de factura Gas → procesados=1."""
    _setup_gas(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "gas")
    parser = MagicMock()
    parser.parse.return_value = _mock_gas_invoice()
    monkeypatch.setattr("web.clientes.get_gas_parser", lambda: parser)
    monkeypatch.setattr(
        "web.clientes.save_gas_invoice",
        lambda inv, contrato_id=None: (2, "2024 ENE GAS CUENTA-001"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/20/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert data["errores"] == []


# ── Test 3: Error de parseo queda en log ──────────────────────────────────────

def test_upload_error_queda_en_log(auth_client, monkeypatch, caplog):
    """Error de parseo → registro ERROR con exc_info y JSON con errores."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.side_effect = ValueError("Campo no encontrado: PERIODO FACTURADO")
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)

    with caplog.at_level(logging.ERROR, logger="web.clientes"):
        resp = auth_client.post(
            "/clientes/1/contratos/10/upload",
            data={"facturas": _fake_pdf()},
            content_type="multipart/form-data",
        )

    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["errores"]) == 1
    assert "PERIODO FACTURADO" in data["errores"][0]["error"]
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "Se esperaba al menos un registro ERROR en el log"
    assert error_records[0].exc_info is not None


# ── Test 4: CFE a contrato Gas → error bloqueante ────────────────────────────

def test_upload_tipo_cfe_a_contrato_gas_es_error(auth_client, monkeypatch):
    """Factura CFE subida a contrato de gas → error bloqueante, no se intenta parsear."""
    _setup_gas(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")

    resp = auth_client.post(
        "/clientes/1/contratos/20/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["errores"]) == 1
    assert "no coincide" in data["errores"][0]["error"]


# ── Test 5: Identificador discrepante → pendiente_confirmacion ───────────────

def test_upload_identificador_discrepante_queda_pendiente(auth_client, monkeypatch):
    """Factura con numero_servicio diferente al del contrato → pendientes_confirmacion, no se guarda."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice(numero_servicio="OTRO-NUMERO")
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado = []
    monkeypatch.setattr("web.clientes.save_cfe_invoice", lambda *a, **kw: guardado.append(1) or (1, "x"))

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["pendientes_confirmacion"]) == 1
    assert data["pendientes_confirmacion"][0]["identificador_factura"] == "OTRO-NUMERO"
    assert data["pendientes_confirmacion"][0]["identificador_contrato"] == "812990300016"
    assert len(guardado) == 0


# ── Test 6: Confirmación de discrepancia → guarda con contrato_id correcto ───

def test_upload_confirmado_pese_a_discrepancia_guarda(auth_client, monkeypatch):
    """Con confirmado_pese_a_discrepancia → guarda la factura con el contrato_id del contrato."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice(numero_servicio="OTRO-NUMERO")
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado_con = []
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, contrato_id=None: guardado_con.append(contrato_id) or (1, "nombre"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf(), "confirmado_pese_a_discrepancia": "factura.pdf"},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert len(guardado_con) == 1
    assert guardado_con[0] == 10  # contrato_id correcto


# ── Test 7: Gas a contrato eléctrico → error bloqueante ──────────────────────

def test_upload_tipo_gas_a_contrato_electrico_es_error(auth_client, monkeypatch):
    """Factura Gas subida a contrato eléctrico → error bloqueante."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "gas")

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["errores"]) == 1
    assert "no coincide" in data["errores"][0]["error"]


# ── Test 8: Borrar factura CFE ────────────────────────────────────────────────

def test_contrato_factura_borrar_exitoso(auth_client, monkeypatch, app):
    """POST a /facturas/42/borrar con tipo=cfe → ok=True, factura eliminada."""
    _setup_electrico(monkeypatch)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_cfe_factura", lambda id: borrado.append(id))

    resp = auth_client.post(
        "/clientes/1/contratos/10/facturas/42/borrar",
        data={"tipo": "cfe"},
    )
    data = resp.get_json()
    assert data["ok"] is True
    assert 42 in borrado


# ── Test 9: Upload sin archivos → 400 ────────────────────────────────────────

def test_upload_sin_archivos(auth_client, monkeypatch):
    """POST sin archivos → 400 con mensaje de error."""
    _setup_electrico(monkeypatch)

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["procesados"] == 0
    assert data["errores"][0]["error"] == "No se enviaron archivos"
