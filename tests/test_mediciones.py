# tests/test_mediciones.py
"""Tests para los endpoints PATCH/DELETE de mediciones y borrar-lote."""
from __future__ import annotations

import pytest

_MED_BASE = {
    "id": 42,
    "cliente_id": 1,
    "anio": 2026,
    "mes": 3,
    "nombre": "planta_mar26.xlsx",
    "uploaded_at": "2026-03-31T10:00:00+00:00",
    "uploaded_by": "operador@test.com",
}


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


@pytest.fixture()
def auth_admin(app):
    """Cliente autenticado con rol admin."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "admin-uuid"
        sess["_user_email"] = "admin@test.com"
        sess["_user_rol"] = "admin"
        sess["_empresa_id"] = None
    return c


@pytest.fixture()
def auth_usuario_normal(app):
    """Cliente autenticado con rol usuario_normal (sin permiso de borrar)."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "user-uuid"
        sess["_user_email"] = "usuario@test.com"
        sess["_user_rol"] = "usuario_normal"
        sess["_empresa_id"] = 1
    return c


# ── PATCH /clientes/<id>/mediciones/<id> ──────────────────────────────────────

def test_patch_medicion_nombre(auth_admin, monkeypatch):
    """PATCH actualiza el nombre correctamente."""
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: dict(_MED_BASE))
    monkeypatch.setattr(
        "web.clientes.update_medicion",
        lambda _id, campos: {**_MED_BASE, **campos},
    )
    resp = auth_admin.patch(
        "/clientes/1/mediciones/42",
        json={"nombre": "nuevo_archivo.xlsx"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["medicion"]["nombre"] == "nuevo_archivo.xlsx"


def test_patch_medicion_mes_anio(auth_admin, monkeypatch):
    """PATCH actualiza mes y anio correctamente."""
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: dict(_MED_BASE))
    monkeypatch.setattr(
        "web.clientes.update_medicion",
        lambda _id, campos: {**_MED_BASE, **campos},
    )
    resp = auth_admin.patch(
        "/clientes/1/mediciones/42",
        json={"mes": 6, "anio": 2025},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["medicion"]["mes"] == 6
    assert data["medicion"]["anio"] == 2025


def test_patch_medicion_anio_invalido(auth_admin, monkeypatch):
    """PATCH con año fuera de rango devuelve 422."""
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: dict(_MED_BASE))
    resp = auth_admin.patch(
        "/clientes/1/mediciones/42",
        json={"anio": 1900},
        content_type="application/json",
    )
    assert resp.status_code == 422


def test_patch_medicion_mes_invalido(auth_admin, monkeypatch):
    """PATCH con mes fuera de rango (>12) devuelve 422."""
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: dict(_MED_BASE))
    resp = auth_admin.patch(
        "/clientes/1/mediciones/42",
        json={"mes": 13},
        content_type="application/json",
    )
    assert resp.status_code == 422


def test_patch_medicion_sin_campos(auth_admin, monkeypatch):
    """PATCH con body vacío devuelve 422."""
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: dict(_MED_BASE))
    resp = auth_admin.patch(
        "/clientes/1/mediciones/42",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 422


def test_patch_medicion_no_autorizado(auth_usuario_normal, monkeypatch):
    """PATCH sin rol suficiente devuelve 403."""
    resp = auth_usuario_normal.patch(
        "/clientes/1/mediciones/42",
        json={"nombre": "hack"},
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_patch_medicion_sin_sesion(client):
    """PATCH sin sesión devuelve 403 (redirigido a login antes de llegar al endpoint)."""
    resp = client.patch(
        "/clientes/1/mediciones/42",
        json={"nombre": "test"},
        content_type="application/json",
        follow_redirects=False,
    )
    # Sin sesión: bien puede ser 302 (redirect a login) o 403 dependiendo del decorador
    assert resp.status_code in (302, 403)


def test_patch_medicion_cliente_incorrecto(auth_admin, monkeypatch):
    """PATCH sobre medición de otro cliente devuelve 404."""
    med_otro_cliente = {**_MED_BASE, "cliente_id": 99}
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: med_otro_cliente)
    resp = auth_admin.patch(
        "/clientes/1/mediciones/42",
        json={"nombre": "otro"},
        content_type="application/json",
    )
    assert resp.status_code == 404


# ── DELETE /clientes/<id>/mediciones/<id> ─────────────────────────────────────

def test_delete_medicion_ok(auth_admin, monkeypatch):
    """DELETE borra la medición y devuelve ok."""
    deleted = []
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: dict(_MED_BASE))
    monkeypatch.setattr("web.clientes.delete_medicion", lambda _id: deleted.append(_id))
    resp = auth_admin.delete("/clientes/1/mediciones/42")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert 42 in deleted


def test_delete_medicion_no_autorizado(auth_usuario_normal):
    """DELETE sin rol suficiente devuelve 403."""
    resp = auth_usuario_normal.delete("/clientes/1/mediciones/42")
    assert resp.status_code == 403


def test_delete_medicion_no_encontrada(auth_admin, monkeypatch):
    """DELETE sobre medición inexistente devuelve 404."""
    monkeypatch.setattr("web.clientes.get_medicion", lambda _id: None)
    resp = auth_admin.delete("/clientes/1/mediciones/999")
    assert resp.status_code == 404


# ── POST /clientes/<id>/mediciones/borrar-lote ────────────────────────────────

def test_borrar_lote_ok(auth_admin, monkeypatch):
    """POST borrar-lote elimina las mediciones correctas y devuelve conteo."""
    calls = []
    def _get(mid):
        return {"id": mid, "cliente_id": 1, "anio": 2026, "mes": mid, "nombre": None}
    monkeypatch.setattr("web.clientes.get_medicion", _get)
    monkeypatch.setattr("web.clientes.delete_medicion", lambda mid: calls.append(mid))
    resp = auth_admin.post(
        "/clientes/1/mediciones/borrar-lote",
        json={"ids": [1, 2, 3]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["eliminadas"] == 3
    assert data["errores"] == 0
    assert calls == [1, 2, 3]


def test_borrar_lote_ids_vacios(auth_admin):
    """POST borrar-lote con ids vacío devuelve 422."""
    resp = auth_admin.post(
        "/clientes/1/mediciones/borrar-lote",
        json={"ids": []},
        content_type="application/json",
    )
    assert resp.status_code == 422


def test_borrar_lote_no_autorizado(auth_usuario_normal):
    """POST borrar-lote sin rol suficiente devuelve 403."""
    resp = auth_usuario_normal.post(
        "/clientes/1/mediciones/borrar-lote",
        json={"ids": [1]},
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_borrar_lote_ignora_ajenos(auth_admin, monkeypatch):
    """POST borrar-lote no borra mediciones de otro cliente."""
    calls = []
    def _get(mid):
        if mid == 1:
            return {"id": 1, "cliente_id": 1, "anio": 2026, "mes": 1, "nombre": None}
        return {"id": mid, "cliente_id": 99, "anio": 2026, "mes": 2, "nombre": None}
    monkeypatch.setattr("web.clientes.get_medicion", _get)
    monkeypatch.setattr("web.clientes.delete_medicion", lambda mid: calls.append(mid))
    resp = auth_admin.post(
        "/clientes/1/mediciones/borrar-lote",
        json={"ids": [1, 2]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["eliminadas"] == 1
    assert data["errores"] == 1   # la ajena cuenta como error (no le pertenece)
    assert calls == [1]
