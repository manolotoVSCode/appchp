# tests/test_usuario_avanzado.py
"""Tests de permisos de usuario_avanzado.

Verifica que un usuario_avanzado asignado al cliente 45:
  a) Puede ver la ficha de su propio cliente (200).
  b) No puede ver la ficha de otro cliente (302/403).
  c) No puede ver el listado global de clientes (redirect a su ficha).
  d) Puede editar la ficha de su cliente (302).
  e) Puede crear contratos en su cliente (no 403).
  f) Puede subir mediciones en su cliente (no 403).
  g) No puede borrar el cliente (302, nada borrado).
  h) Puede crear plantas en su cliente (no 403).
  i) Ve la ficha completa (nombre_canonico en respuesta).
"""
from __future__ import annotations

import pytest

_CLIENTE_45 = {
    "id": 45,
    "nombre": "IBERICA TILES",
    "rfc": "ITI930101AAA",
    "notas": "Cliente industrial",
    "created_at": "2024-01-15T10:00:00+00:00",
    "num_cfe": 5,
    "num_electricidad": 5,
    "num_gas": 3,
    "logo_url": None,
    "sector_industrial": None,
    "contacto_nombre": None,
    "contacto_cargo": None,
    "contacto_email": None,
    "contacto_telefono": None,
    "direccion": None,
    "estado": None,
    "codigo_postal": None,
    "tarifa_cfe": None,
    "capacidad_instalada_kw": None,
    "demanda_contratada_kw": None,
    "anio_inicio_operacion": None,
    "regimen_operacion": None,
    "consumo_anual_estimado_mwh": None,
}

_CLIENTE_44 = {**_CLIENTE_45, "id": 44, "nombre": "OTRO CLIENTE"}


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


def _avanzado_client(app, cliente_id=45):
    """Cliente HTTP autenticado como usuario_avanzado asignado al cliente dado."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "avanzado-user-uuid"
        sess["_user_email"] = "iberica@chpmex.com"
        sess["_user_rol"] = "usuario_avanzado"
        sess["_empresa_id"] = cliente_id
        sess["_clientes_ids"] = [cliente_id]
    return c


def _patch_ficha(monkeypatch, cliente=None):
    c = cliente or _CLIENTE_45
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: c)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: c)
    monkeypatch.setattr("web.clientes.get_contratos_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("storage.repository.get_ppa_bloques_mensuales", lambda id: [])
    monkeypatch.setattr("web.clientes.obtener_plantas_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.clientes.get_mediciones_por_cliente", lambda id: [])
    monkeypatch.setattr("web.clientes.get_ultimas_cfe_invoices", lambda id, n=50: [])
    monkeypatch.setattr("web.clientes.get_ultimas_gas_invoices", lambda id, n=50: [])
    monkeypatch.setattr("web.clientes.get_facturas_calificado_por_cliente", lambda id: [])


# ── a) GET ficha del propio cliente → 200 ────────────────────────────────────

def test_usuario_avanzado_ficha_propio_cliente_200(app, monkeypatch):
    """usuario_avanzado GET /clientes/45 → 200, nombre visible."""
    _patch_ficha(monkeypatch)
    c = _avanzado_client(app, cliente_id=45)
    resp = c.get("/clientes/45", follow_redirects=False)
    assert resp.status_code == 200
    assert b"IBERICA TILES" in resp.data


# ── b) GET ficha de otro cliente → redirect ───────────────────────────────────

def test_usuario_avanzado_ficha_otro_cliente_redirect(app, monkeypatch):
    """usuario_avanzado con acceso al cliente 45, GET /clientes/44 → redirect."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_44)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_44)
    c = _avanzado_client(app, cliente_id=45)
    resp = c.get("/clientes/44", follow_redirects=False)
    assert resp.status_code == 302


# ── c) GET listado → redirect a su ficha ─────────────────────────────────────

def test_usuario_avanzado_listado_redirect(app, monkeypatch):
    """usuario_avanzado GET /clientes → redirect a ficha de su cliente."""
    c = _avanzado_client(app, cliente_id=45)
    resp = c.get("/clientes/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/45" in resp.headers["Location"]


# ── d) POST editar ficha → 302 ────────────────────────────────────────────────

def test_usuario_avanzado_editar_ficha_302(app, monkeypatch):
    """usuario_avanzado POST /clientes/45/editar → 302 (éxito)."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_45)
    monkeypatch.setattr("web.clientes.update_cliente", lambda *a, **kw: None)
    monkeypatch.setattr("web.clientes.update_cliente_chp_params", lambda *a, **kw: None)
    c = _avanzado_client(app, cliente_id=45)
    resp = c.post("/clientes/45/editar", data={
        "nombre": "IBERICA TILES SA", "rfc": "ITI930101AAA", "notas": "",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/45" in resp.headers["Location"]


# ── e) POST contrato_nuevo → no 401/403 ──────────────────────────────────────

def test_usuario_avanzado_contrato_nuevo_no_403(app, monkeypatch):
    """usuario_avanzado POST /clientes/45/contratos/nuevo → no 403."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_45)
    monkeypatch.setattr("web.clientes.obtener_plantas_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.clientes.create_contrato", lambda *a, **kw: 99)
    c = _avanzado_client(app, cliente_id=45)
    resp = c.post("/clientes/45/contratos/nuevo", data={
        "nombre": "Contrato Test",
        "tipo": "electrico_basico",
        "identificador_real": "123456789",
        "notas": "",
    }, follow_redirects=False)
    assert resp.status_code not in (401, 403)


# ── f) POST subir medición → no 401/403 ──────────────────────────────────────

def test_usuario_avanzado_medicion_subir_no_403(app, monkeypatch):
    """usuario_avanzado POST /clientes/45/mediciones/cincominutal/subir → no 403."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_45)
    monkeypatch.setattr("web.clientes.obtener_plantas_por_cliente", lambda *a, **kw: [])
    c = _avanzado_client(app, cliente_id=45)
    resp = c.post("/clientes/45/mediciones/cincominutal/subir",
                  data={"anio": "2024", "mes": "1"},
                  follow_redirects=False)
    assert resp.status_code not in (401, 403)


# ── g) POST borrar cliente → 302 sin borrar ───────────────────────────────────

def test_usuario_avanzado_borrar_cliente_bloqueado(app, monkeypatch):
    """usuario_avanzado POST /clientes/45/borrar → redirect (sin permiso)."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_45)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_cliente", lambda id: borrado.append(id))
    c = _avanzado_client(app, cliente_id=45)
    resp = c.post("/clientes/45/borrar", data={
        "confirmacion": "IBERICA TILES",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert len(borrado) == 0  # no se borró nada


# ── h) POST planta_nueva → no 401/403 ────────────────────────────────────────

def test_usuario_avanzado_planta_nueva_no_403(app, monkeypatch):
    """usuario_avanzado POST /clientes/45/planta/nueva → no 403."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_45)
    monkeypatch.setattr("web.clientes.crear_planta", lambda *a, **kw: 10)
    c = _avanzado_client(app, cliente_id=45)
    resp = c.post("/clientes/45/planta/nueva", data={
        "nombre": "Planta Test",
        "direccion": "",
        "estado": "",
        "codigo_postal": "",
    }, follow_redirects=False)
    assert resp.status_code not in (401, 403)


# ── i) Ficha completa visible ─────────────────────────────────────────────────

def test_usuario_avanzado_ficha_completa(app, monkeypatch):
    """usuario_avanzado ve la ficha completa del cliente (mismo acceso que admin)."""
    _patch_ficha(monkeypatch)
    c = _avanzado_client(app, cliente_id=45)
    resp = c.get("/clientes/45", follow_redirects=False)
    assert resp.status_code == 200
    # El bloque principal de la ficha debe renderizar con el nombre del cliente
    assert b"IBERICA TILES" in resp.data
