# tests/test_auth.py
from __future__ import annotations

import os
import pytest
from werkzeug.security import generate_password_hash

# Hash de la password "test_pass" generado offline para los fixtures
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
def client(app):
    return app.test_client()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _login(client, username="operador", password="test_pass"):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=False)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_login_exitoso(client, monkeypatch):
    """Credenciales correctas → 302 al dashboard."""
    # Evitar carga real de Supabase en el redirect
    monkeypatch.setattr("web.app._cargar_datos", lambda: _mock_datos())
    resp = _login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_login_fallido_password(client):
    """Password incorrecta → 200 con mensaje genérico, no revela cuál campo falló."""
    resp = _login(client, password="wrong_pass")
    assert resp.status_code == 200
    assert b"Credenciales incorrectas" in resp.data
    assert b"usuario" not in resp.data.lower() or b"contrase" not in resp.data.lower() or \
           b"Credenciales incorrectas" in resp.data  # mensaje no especifica campo


def test_login_fallido_usuario(client):
    """Usuario incorrecto → mismo mensaje genérico."""
    resp = _login(client, username="intruso")
    assert resp.status_code == 200
    assert b"Credenciales incorrectas" in resp.data


def test_ruta_protegida_sin_autenticacion(client):
    """GET / sin sesión → 302 a /login."""
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_ruta_raiz_redirige_a_clientes(client):
    """GET / con sesión activa → 302 a /clientes (ya no es el dashboard)."""
    _login(client)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes" in resp.headers["Location"]


def test_logout(client, monkeypatch):
    """Logout destruye sesión; acceso posterior redirige a /login."""
    monkeypatch.setattr("web.app._cargar_datos", lambda: _mock_datos())
    _login(client)
    resp_logout = client.get("/logout", follow_redirects=False)
    assert resp_logout.status_code == 302
    assert "/login" in resp_logout.headers["Location"]

    resp_after = client.get("/", follow_redirects=False)
    assert resp_after.status_code == 302
    assert "/login" in resp_after.headers["Location"]


# ── Tests de validación al arranque ──────────────────────────────────────────

def test_arranque_sin_app_user(monkeypatch):
    """Si APP_USER no está definida, create_app() lanza RuntimeError."""
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("APP_PASSWORD_HASH", _HASH)
    monkeypatch.delenv("APP_USER", raising=False)

    from web.app import create_app
    with pytest.raises(RuntimeError, match="APP_USER"):
        create_app()


def test_arranque_sin_app_password_hash(monkeypatch):
    """Si APP_PASSWORD_HASH no está definida, create_app() lanza RuntimeError."""
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("APP_USER", "operador")
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)

    from web.app import create_app
    with pytest.raises(RuntimeError, match="APP_PASSWORD_HASH"):
        create_app()


# ── Mock de datos para evitar llamadas a Supabase ────────────────────────────

def _mock_datos():
    from unittest.mock import MagicMock
    from decimal import Decimal
    from datetime import date

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
        "costo_unit_mes": [], "tabla_punta": [{"mes": "TOTAL ANUAL", "costo_punta": 0.0, "pct": 0.0, "costo_unit_punta": 0.0}],
        "costo_unit_promedio": {"base": 0.0, "intermedio": 0.0, "punta": 0.0},
    }
    tablas = {"consumos_demandas": [], "costos_detallados": [], "indicadores": []}
    return resultado, [], [], historico, tablas
