# tests/test_upload_logging.py
from __future__ import annotations

import io
import logging

import pytest
from werkzeug.security import generate_password_hash

_HASH = generate_password_hash("test_pass", method="pbkdf2:sha256")


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
    """Cliente con sesión activa y datos mockeados para no tocar Supabase."""
    monkeypatch.setattr("web.app._cargar_datos", lambda: _mock_datos())
    client = app.test_client()
    client.post("/login", data={"username": "operador", "password": "test_pass"})
    return client


def _fake_pdf():
    """Objeto FileStorage-compatible con contenido mínimo."""
    return (io.BytesIO(b"%PDF-1.4 fake"), "factura.pdf")


# ── Test 1: error queda en log con stack trace ────────────────────────────────

def test_error_queda_en_log_con_stack_trace(auth_client, monkeypatch, caplog):
    """Cuando procesar_factura_cfe lanza excepción, el log registra ERROR con exc_info."""
    monkeypatch.setattr("web.app._detect_tipo", lambda _: "cfe")
    monkeypatch.setattr(
        "web.app.procesar_factura_cfe",
        lambda *a, **kw: (_ for _ in ()).throw(
            ValueError("Campo no encontrado: PERIODO FACTURADO")
        ),
    )

    with caplog.at_level(logging.ERROR, logger="web.app"):
        auth_client.post(
            "/upload",
            data={"facturas": _fake_pdf()},
            content_type="multipart/form-data",
        )

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "Se esperaba al menos un registro ERROR en el log"

    record = error_records[0]
    assert record.exc_info is not None, "El registro ERROR debe incluir exc_info (stack trace)"
    assert "factura.pdf" in record.message
    assert "PERIODO FACTURADO" in record.message or "PERIODO FACTURADO" in str(record.exc_info)


# ── Test 2: respuesta JSON incluye mensaje descriptivo ────────────────────────

def test_respuesta_json_incluye_mensaje_descriptivo(auth_client, monkeypatch):
    """El JSON de respuesta incluye el mensaje de error en errores[0]['error']."""
    monkeypatch.setattr("web.app._detect_tipo", lambda _: "cfe")
    monkeypatch.setattr(
        "web.app.procesar_factura_cfe",
        lambda *a, **kw: (_ for _ in ()).throw(
            ValueError("Campo no encontrado: PERIODO FACTURADO")
        ),
    )

    resp = auth_client.post(
        "/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )

    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["errores"]) == 1
    assert data["errores"][0]["nombre"] == "factura.pdf"
    assert "PERIODO FACTURADO" in data["errores"][0]["error"]


# ── Test 3: éxito queda en log con id de factura ─────────────────────────────

def test_exito_queda_en_log_con_id(auth_client, monkeypatch, caplog):
    """Cuando el procesamiento es exitoso, el log registra INFO con el id de la factura."""
    monkeypatch.setattr("web.app._detect_tipo", lambda _: "cfe")
    monkeypatch.setattr("web.app.procesar_factura_cfe", lambda *a, **kw: (42, "2024 ENERO CFE 812990300016"))
    monkeypatch.setattr("web.app._cargar_datos", lambda: _mock_datos())

    with caplog.at_level(logging.INFO, logger="web.app"):
        resp = auth_client.post(
            "/upload",
            data={"facturas": _fake_pdf()},
            content_type="multipart/form-data",
        )

    data = resp.get_json()
    assert data["procesados"] == 1
    assert data["errores"] == []
    assert data["exitosos"][0]["nombre_canonico"] == "2024 ENERO CFE 812990300016"

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    exito_records = [r for r in info_records if "id=42" in r.message]
    assert exito_records, "Se esperaba un registro INFO con 'id=42'"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_datos():
    from unittest.mock import MagicMock
    from decimal import Decimal

    resultado = MagicMock()
    resultado.meses = []
    resultado.ebitda_anual_mxn = Decimal("0")
    resultado.ahorro_electricidad_anual_mxn = Decimal("0")
    resultado.ahorro_caldera_anual_mxn = Decimal("0")
    resultado.costo_gas_cogen_anual_mxn = Decimal("0")
    resultado.params = MagicMock(
        cobertura_electrica=Decimal("0.75"),
        rendimiento_electrico=Decimal("0.40"),
        rendimiento_termico=Decimal("0.25"),
        eficiencia_caldera=Decimal("0.85"),
    )
    historico = {
        "labels": [], "demanda_punta": [], "demanda_intermedio": [], "demanda_base": [],
        "consumo_punta": [], "consumo_intermedio": [], "consumo_base": [],
        "costo_unit_mes": [],
        "tabla_punta": [{"mes": "TOTAL ANUAL", "costo_punta": 0.0, "pct": 0.0, "costo_unit_punta": 0.0}],
        "costo_unit_promedio": {"base": 0.0, "intermedio": 0.0, "punta": 0.0},
    }
    tablas = {"consumos_demandas": [], "costos_detallados": [], "indicadores": []}
    return resultado, [], [], historico, tablas
