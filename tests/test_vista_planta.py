# tests/test_vista_planta.py
"""Tests para la ruta GET /clientes/<cliente_id>/planta/<planta_id> (vista_planta)."""
from __future__ import annotations

import pytest

# ── Fixtures reutilizadas ──────────────────────────────────────────────────────

_CLIENTE_BASE = {
    "id": 45,
    "nombre": "IBÉRICA TILES",
    "rfc": "ITI930101AAA",
    "notas": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "sector_industrial": "cerámico",
    "contacto_nombre": None,
    "contacto_cargo": None,
    "contacto_email": None,
    "contacto_telefono": None,
    "direccion": None,
    "estado": None,
    "codigo_postal": None,
    "tarifa_cfe": "GDMTH",
    "capacidad_instalada_kw": None,
    "demanda_contratada_kw": None,
    "anio_inicio_operacion": None,
    "regimen_operacion": None,
    "consumo_anual_estimado_mwh": None,
    "logo_url": None,
    "medio_termico": None,
    "medio_termico_vapor_pct": None,
    "nivel_tension_kv": None,
    "altitud_msnm": None,
    "tipo_motor": None,
    "num_electricidad": 12,
    "num_gas": 12,
    "activo": True,
    "ppa_suministrador": None,
    "ppa_rfc_suministrador": None,
    "ppa_rpu": None,
    "ppa_division": None,
    "ppa_zona_carga": None,
    "ppa_precio_fijo_usd_mwh": None,
    "ppa_fecha_inicio_suministro": None,
    "ppa_energia_contratada_mwh_anual": None,
    "ppa_capacidad_maxima_kw": None,
    "ppa_margen_reserva_cenace_pct": None,
    "ppa_pdf_contrato_url": None,
    "ppa_notas": None,
    "precio_gas_manual_mxn_gj_pcs": None,
}

_PLANTA_BASE = {
    "id": 9,
    "cliente_id": 45,
    "nombre": "Planta 1",
    "direccion_planta": "Calle Poniente 100",
    "notas": None,
    "activo": True,
}

_PLANTA_OTRA = {
    "id": 10,
    "cliente_id": 45,
    "nombre": "Planta 2",
    "direccion_planta": None,
    "notas": None,
    "activo": True,
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


def _make_client(app, *, rol: str, empresa_id: int | None = None):
    """Devuelve un test_client con sesión activa para el rol dado."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "test-uuid"
        sess["_user_email"] = "test@test.com"
        sess["_user_rol"] = rol
        sess["_empresa_id"] = empresa_id
    return c


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_vista_planta_master_admin_200(app, monkeypatch):
    """GET /clientes/45/planta/9 como master_admin → 200, muestra nombre planta."""
    monkeypatch.setattr("web.app.obtener_planta", lambda pid: _PLANTA_BASE)
    monkeypatch.setattr("web.app.obtener_plantas_por_cliente", lambda *a, **kw: [_PLANTA_BASE, _PLANTA_OTRA])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.app.get_mediciones_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr(
        "storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_BASE
    )
    c = _make_client(app, rol="master_admin")
    resp = c.get("/clientes/45/planta/9")
    assert resp.status_code == 200
    assert "Planta 1".encode() in resp.data


def test_vista_planta_admin_muestra_botones_escritura(app, monkeypatch):
    """GET como admin → botones de escritura visibles (Nuevo contrato, Subir medición)."""
    monkeypatch.setattr("web.app.obtener_planta", lambda pid: _PLANTA_BASE)
    monkeypatch.setattr("web.app.obtener_plantas_por_cliente", lambda *a, **kw: [_PLANTA_BASE])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.app.get_mediciones_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr(
        "storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_BASE
    )
    c = _make_client(app, rol="admin")
    resp = c.get("/clientes/45/planta/9")
    assert resp.status_code == 200
    assert b"Nuevo contrato" in resp.data
    assert b"Subir medici" in resp.data


def test_vista_planta_usuario_normal_propio_cliente_200(app, monkeypatch):
    """GET como usuario_normal de cliente 45 → 200 sin botones de escritura."""
    monkeypatch.setattr("web.app.obtener_planta", lambda pid: _PLANTA_BASE)
    monkeypatch.setattr("web.app.obtener_plantas_por_cliente", lambda *a, **kw: [_PLANTA_BASE])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.app.get_mediciones_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr(
        "storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_BASE
    )
    c = _make_client(app, rol="usuario_normal", empresa_id=45)
    resp = c.get("/clientes/45/planta/9")
    assert resp.status_code == 200
    assert b"Nuevo contrato" not in resp.data
    assert b"Subir medici" not in resp.data


def test_vista_planta_usuario_normal_otro_cliente_403(app, monkeypatch):
    """GET como usuario_normal de cliente 99 intentando ver cliente 45 → redirect."""
    monkeypatch.setattr("web.app.obtener_plantas_por_cliente", lambda *a, **kw: [])
    c = _make_client(app, rol="usuario_normal", empresa_id=99)
    resp = c.get("/clientes/45/planta/9", follow_redirects=False)
    assert resp.status_code == 302


def test_vista_planta_inexistente_redirige(app, monkeypatch):
    """GET /clientes/45/planta/100 con planta inexistente → redirect con flash."""
    monkeypatch.setattr("web.app.obtener_planta", lambda pid: None)
    monkeypatch.setattr("web.app.obtener_plantas_por_cliente", lambda *a, **kw: [])
    c = _make_client(app, rol="admin")
    resp = c.get("/clientes/45/planta/100", follow_redirects=False)
    assert resp.status_code == 302


def test_vista_planta_actualiza_sesion_planta_activa(app, monkeypatch):
    """GET actualiza session['planta_activa_id'] al planta_id visitado."""
    monkeypatch.setattr("web.app.obtener_planta", lambda pid: _PLANTA_BASE)
    monkeypatch.setattr("web.app.obtener_plantas_por_cliente", lambda *a, **kw: [_PLANTA_BASE, _PLANTA_OTRA])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr("web.app.get_mediciones_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr(
        "storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_BASE
    )
    c = _make_client(app, rol="admin")
    # Empezar con planta_activa_id diferente
    with c.session_transaction() as sess:
        sess["planta_activa_id"] = 10
    c.get("/clientes/45/planta/9")
    with c.session_transaction() as sess:
        assert sess.get("planta_activa_id") == 9


def test_vista_planta_contratos_filtrados_por_planta(app, monkeypatch):
    """Los contratos cargados corresponden al planta_id visitado, no a otro."""
    from models.contrato import Contrato
    contrato_p1 = Contrato(
        id=20, cliente_id=45, nombre="PPA Planta 1", tipo="electrico_calificado",
        identificador_real="GIN-001", notas=None, created_at=None, planta_id=9,
    )

    capturado: dict = {}

    def mock_contratos(cliente_id, planta_id=None):
        capturado["planta_id"] = planta_id
        return [contrato_p1] if planta_id == 9 else []

    monkeypatch.setattr("web.app.obtener_planta", lambda pid: _PLANTA_BASE)
    monkeypatch.setattr("web.app.obtener_plantas_por_cliente", lambda *a, **kw: [_PLANTA_BASE])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", mock_contratos)
    monkeypatch.setattr("web.app.get_mediciones_por_cliente", lambda *a, **kw: [])
    monkeypatch.setattr(
        "storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_BASE
    )
    c = _make_client(app, rol="admin")
    resp = c.get("/clientes/45/planta/9")
    assert resp.status_code == 200
    assert capturado.get("planta_id") == 9
    assert b"PPA Planta 1" in resp.data
