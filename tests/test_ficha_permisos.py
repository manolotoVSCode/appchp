# tests/test_ficha_permisos.py
"""Tests de permisos de usuario_normal en la ficha del cliente.

Verifica que iberica@chpmex.com (usuario_normal con acceso al cliente 1):
  a) Ve la ficha completa.
  b) Puede editar la ficha.
  c) Puede subir mediciones.
  d) Puede crear contratos.
  e) Puede crear plantas.
  f) NO puede borrar el cliente.
  g) NO puede ver la ficha de otro cliente.
"""
from __future__ import annotations

import pytest
from models.contrato import Contrato

_CLIENTE_1 = {
    "id": 1,
    "nombre": "IBERICA TILES",
    "rfc": "ITI930101AAA",
    "notas": "Cliente industrial",
    "created_at": "2024-01-15T10:00:00+00:00",
    "num_cfe": 12,
    "num_electricidad": 12,
    "num_gas": 12,
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

_CLIENTE_2 = {**_CLIENTE_1, "id": 2, "nombre": "OTRO CLIENTE"}


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


def _usuario_normal_client(app, cliente_id=1):
    """Cliente HTTP autenticado como usuario_normal del cliente dado."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "normal-user-uuid"
        sess["_user_email"] = "iberica@chpmex.com"
        sess["_user_rol"] = "usuario_normal"
        sess["_empresa_id"] = cliente_id
        sess["_clientes_ids"] = [cliente_id]
    return c


def _patch_ficha(monkeypatch, cliente=None):
    """Aplica todos los monkeypatches necesarios para GET /clientes/<id>."""
    c = cliente or _CLIENTE_1
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


# ── a) GET ficha del propio cliente → 200 ─────────────────────────────────────

def test_usuario_normal_ficha_propio_cliente_200(app, monkeypatch):
    """usuario_normal GET /clientes/1 → 200, nombre visible."""
    _patch_ficha(monkeypatch)
    c = _usuario_normal_client(app, cliente_id=1)
    resp = c.get("/clientes/1", follow_redirects=False)
    assert resp.status_code == 200
    assert b"IBERICA TILES" in resp.data


# ── b) POST editar ficha → 302 ────────────────────────────────────────────────

def test_usuario_normal_editar_ficha_302(app, monkeypatch):
    """usuario_normal POST /clientes/1/editar → 302 (éxito)."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_1)
    monkeypatch.setattr("web.clientes.update_cliente", lambda *a, **kw: None)
    monkeypatch.setattr("web.clientes.update_cliente_chp_params", lambda *a, **kw: None)
    c = _usuario_normal_client(app, cliente_id=1)
    resp = c.post("/clientes/1/editar", data={
        "nombre": "IBERICA TILES SA", "rfc": "ITI930101AAA", "notas": "",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/1" in resp.headers["Location"]


# ── c) POST subir medición → no 401/403 ──────────────────────────────────────

def test_usuario_normal_medicion_subir_no_403(app, monkeypatch):
    """usuario_normal POST /clientes/1/mediciones/cincominutal/subir → no 403."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_1)
    monkeypatch.setattr("web.clientes.obtener_plantas_por_cliente", lambda *a, **kw: [])
    c = _usuario_normal_client(app, cliente_id=1)
    resp = c.post("/clientes/1/mediciones/cincominutal/subir",
                  data={"anio": "2024", "mes": "1"},
                  follow_redirects=False)
    assert resp.status_code not in (401, 403)


# ── d) POST contrato_nuevo → no 401/403 ──────────────────────────────────────

def test_usuario_normal_contrato_nuevo_no_403(app, monkeypatch):
    """usuario_normal POST /clientes/1/contratos/nuevo → no 403."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_1)
    monkeypatch.setattr("web.clientes.obtener_plantas_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.clientes.create_contrato", lambda *a, **kw: 99)
    c = _usuario_normal_client(app, cliente_id=1)
    resp = c.post("/clientes/1/contratos/nuevo", data={
        "nombre": "Contrato Test",
        "tipo": "electrico_basico",
        "identificador_real": "123456789",
        "notas": "",
    }, follow_redirects=False)
    assert resp.status_code not in (401, 403)


# ── e) POST planta_nueva → no 401/403 ────────────────────────────────────────

def test_usuario_normal_planta_nueva_no_403(app, monkeypatch):
    """usuario_normal POST /clientes/1/planta/nueva → no 403."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_1)
    monkeypatch.setattr("web.clientes.crear_planta", lambda *a, **kw: 10)
    c = _usuario_normal_client(app, cliente_id=1)
    resp = c.post("/clientes/1/planta/nueva", data={
        "nombre": "Planta Test",
        "direccion": "",
        "estado": "",
        "codigo_postal": "",
    }, follow_redirects=False)
    assert resp.status_code not in (401, 403)


# ── f) POST borrar cliente → 302 sin borrar ───────────────────────────────────

def test_usuario_normal_borrar_cliente_bloqueado(app, monkeypatch):
    """usuario_normal POST /clientes/1/borrar → redirect (sin permiso)."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_1)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_cliente", lambda id: borrado.append(id))
    c = _usuario_normal_client(app, cliente_id=1)
    resp = c.post("/clientes/1/borrar", data={
        "confirmacion": "IBERICA TILES",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert len(borrado) == 0  # no se borró nada


# ── g) GET ficha de otro cliente → redirect ───────────────────────────────────

def test_usuario_normal_ficha_otro_cliente_redirect(app, monkeypatch):
    """usuario_normal con acceso al cliente 1, GET /clientes/2 → redirect."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_2)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_2)
    c = _usuario_normal_client(app, cliente_id=1)
    resp = c.get("/clientes/2", follow_redirects=False)
    assert resp.status_code == 302
