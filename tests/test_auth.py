# tests/test_auth.py
"""Tests del nuevo sistema de autenticación basado en Supabase Auth + sesiones Flask."""
from __future__ import annotations

import pytest


@pytest.fixture()
def app(monkeypatch):
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


def _inject_session(client, rol="admin"):
    """Inyecta sesión de usuario autenticado directamente (sin llamar a Supabase)."""
    with client.session_transaction() as sess:
        sess["_user_id"] = "test-user-uuid"
        sess["_user_email"] = "operador@test.com"
        sess["_user_rol"] = rol
        sess["_empresa_id"] = None


# ── Tests de acceso sin autenticación ─────────────────────────────────────────

def test_ruta_protegida_sin_autenticacion(client):
    """GET / sin sesión → 302 a /auth/login."""
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_clientes_protegido_sin_autenticacion(client):
    """GET /clientes/ sin sesión → 302 a /auth/login."""
    resp = client.get("/clientes/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_login_page_accesible_sin_autenticacion(client):
    """GET /auth/login sin sesión → 200."""
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Correo electr" in resp.data


def test_reset_password_ruta_eliminada(client):
    """GET /auth/reset-password → 404 (ruta eliminada en v2.32.0)."""
    resp = client.get("/auth/reset-password", follow_redirects=False)
    assert resp.status_code == 404


def test_aceptar_invitacion_ruta_eliminada(client):
    """GET /auth/aceptar-invitacion → 404 (ruta eliminada en v2.32.0)."""
    resp = client.get("/auth/aceptar-invitacion", follow_redirects=False)
    assert resp.status_code == 404


def test_mi_perfil_requiere_autenticacion(client):
    """GET /mi-perfil sin sesión → 302 a /auth/login."""
    resp = client.get("/mi-perfil", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


# ── Tests con sesión inyectada ────────────────────────────────────────────────

def test_ruta_raiz_redirige_a_clientes_con_sesion(client, monkeypatch):
    """GET / con sesión activa → 302 a /clientes."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [])
    _inject_session(client)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes" in resp.headers["Location"]


def test_login_ya_autenticado_redirige(client, monkeypatch):
    """GET /auth/login con sesión activa → 302 a /."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [])
    _inject_session(client)
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 302


# ── Tests de logout ───────────────────────────────────────────────────────────

def test_logout_limpia_sesion(client):
    """GET /auth/logout destruye sesión; acceso posterior redirige a /auth/login."""
    _inject_session(client)

    # Verificar que la sesión está activa
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "test-user-uuid"

    resp_logout = client.get("/auth/logout", follow_redirects=False)
    assert resp_logout.status_code == 302
    assert "/auth/login" in resp_logout.headers["Location"]

    # Verificar que la sesión fue limpiada
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None

    resp_after = client.get("/", follow_redirects=False)
    assert resp_after.status_code == 302
    assert "/auth/login" in resp_after.headers["Location"]


# ── Tests de health endpoints (públicos) ──────────────────────────────────────

def test_healthz_sin_autenticacion(client):
    """GET /healthz → 200 sin autenticación."""
    resp = client.get("/healthz")
    assert resp.status_code == 200


def test_health_sin_autenticacion(client):
    """GET /health → 200 sin autenticación."""
    resp = client.get("/health")
    assert resp.status_code == 200
