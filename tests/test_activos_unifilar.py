"""Tests para el esquema unifilar interactivo de activos electricos."""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock


# ── Mock data ─────────────────────────────────────────────────────────────────

ACTIVOS_PLANTA = [
    {"id": 1, "nombre": "Acometida-1", "tipo": "acometida", "activo_padre_id": None,
     "cliente_id": 44, "planta_id": 10, "activo": True, "capacidad_kva": None,
     "potencia_nominal_kw": None, "tipo_carga": None, "notas": None,
     "medidor_vigente": None},
    {"id": 2, "nombre": "T-1.1 500kVA", "tipo": "transformador", "activo_padre_id": 1,
     "cliente_id": 44, "planta_id": 10, "activo": True, "capacidad_kva": 500,
     "potencia_nominal_kw": None, "tipo_carga": None, "notas": None,
     "medidor_vigente": None},
    {"id": 3, "nombre": "Horno 1", "tipo": "carga", "activo_padre_id": 2,
     "cliente_id": 44, "planta_id": 10, "activo": True, "capacidad_kva": None,
     "potencia_nominal_kw": 200, "tipo_carga": "horno", "notas": None,
     "medidor_vigente": {"medidor_id": 10, "medidores": {"nombre": "MED-10"}}},
    {"id": 4, "nombre": "CHP Motor", "tipo": "generacion", "activo_padre_id": 2,
     "cliente_id": 44, "planta_id": 10, "activo": True, "capacidad_kva": None,
     "potencia_nominal_kw": 1000, "tipo_carga": None, "notas": None,
     "medidor_vigente": None},
]

TODOS_ACTIVOS = ACTIVOS_PLANTA[:]

PLANTA_MOCK = {"id": 10, "cliente_id": 44, "nombre": "Planta Norte", "activo": True}
CLIENTE_MOCK = {"id": 44, "nombre": "Iberica Tiles", "num_cfe": 12,
                "num_gas": 12, "num_electricidad": 12, "contratos": []}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FASE2_HABILITADA", "true")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _inject_session(client, rol="admin", empresa_id=44, clientes_ids=None):
    """Inyecta sesion Flask directamente."""
    from time import time
    now = time()
    with client.session_transaction() as sess:
        sess["_user_id"] = "mock-uuid"
        sess["_user_email"] = "test@test.com"
        sess["_user_rol"] = rol
        sess["_empresa_id"] = empresa_id
        sess["_access_token"] = "mock-token"
        sess["cliente_activo_id"] = 44
        if clientes_ids is not None:
            sess["_clientes_ids"] = clientes_ids
        sess["_session_version"] = 1
        sess["_activo_check"] = {"user_id": "mock-uuid", "ts": now, "activo": True}
        sess["_sv_check"] = {"user_id": "mock-uuid", "ts": now, "version": 1}
        # Cache de plantas para evitar llamada a Supabase en before_request
        sess["_plantas_cache"] = {
            "cliente_id": 44, "ts": now,
            "plantas": [PLANTA_MOCK],
        }
        # Cache de context_processor _inject_globals para evitar Supabase
        sess["_cp_cache"] = {
            "id": 44, "planta_id": 10, "ts": now,
            "data": {
                "id": 44, "nombre": "Iberica Tiles",
                "contratos": [], "logo_url": None,
            },
        }


# ── Test a: GET /telemetria responde 200 para admin ───────────────────────────

def test_activos_planta_200(client, app):
    """El dashboard de telemetria (que integra los activos) responde 200 para admin."""
    app.config["FASE2_HABILITADA"] = True
    from time import time
    now = time()
    with client.session_transaction() as sess:
        sess["_user_id"] = "mock-uuid"
        sess["_user_email"] = "test@test.com"
        sess["_user_rol"] = "admin"
        sess["_empresa_id"] = 44
        sess["_access_token"] = "mock-token"
        sess["cliente_activo_id"] = 44
        sess["_session_version"] = 1
        sess["_activo_check"] = {"user_id": "mock-uuid", "ts": now, "activo": True}
        sess["_sv_check"] = {"user_id": "mock-uuid", "ts": now, "version": 1}
        sess["_plantas_cache"] = {
            "cliente_id": 44, "ts": now,
            "plantas": [PLANTA_MOCK],
        }
        sess["_cp_cache"] = {
            "id": 44, "planta_id": 10, "ts": now,
            "data": {"id": 44, "nombre": "Iberica Tiles", "contratos": [], "logo_url": None},
        }
    with patch("storage.repository.get_cliente_con_conteos", return_value=CLIENTE_MOCK), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ACTIVOS_PLANTA), \
         patch("storage.repository.obtener_todos_activos_cliente", return_value=TODOS_ACTIVOS), \
         patch("storage.repository.get_mediciones_por_cliente", return_value=[]), \
         patch("storage.repository.get_contratos_por_planta", return_value=[]):
        resp = client.get("/clientes/44/planta/10/dashboard/telemetria")
    assert resp.status_code == 200


# ── Test b: GET /activos/topologia con padres_validos coherente ───────────────

def test_activos_topologia_padres_validos(client, app):
    """El endpoint topologia devuelve padres_validos coherentes con _PADRES_VALIDOS."""
    _inject_session(client, "admin")
    with patch("web.clientes.obtener_planta", return_value=PLANTA_MOCK), \
         patch("web.clientes.obtener_arbol_activos", return_value=ACTIVOS_PLANTA), \
         patch("web.clientes.obtener_todos_activos_cliente", return_value=TODOS_ACTIVOS), \
         patch("web.clientes.obtener_historial_contrato_acometida", return_value=[]), \
         patch("web.clientes.resolver_intervalos_rol", return_value=[]):
        resp = client.get("/clientes/44/planta/10/activos/topologia")
    assert resp.status_code == 200
    data = resp.get_json()
    pv = data["padres_validos"]
    assert sorted(pv.keys()) == ["acometida", "carga", "generacion", "subestacion", "transformador"]
    assert pv["carga"] == ["transformador"]
    assert pv["acometida"] == []
    assert sorted(pv["subestacion"]) == ["acometida", "subestacion"]
    assert sorted(pv["transformador"]) == ["acometida", "subestacion"]
    assert sorted(pv["generacion"]) == ["subestacion", "transformador"]
    assert data["raiz"] is not None
    assert data["raiz"]["id"] == 1
    assert data["es_admin"] is True


# ── Test c: POST cambio-alimentacion con ciclo → 422 ─────────────────────────

def test_cambio_alimentacion_ciclo_422(client, app):
    """Cambiar alimentacion creando ciclo debe devolver 422."""
    _inject_session(client, "admin")
    # Activo 1 (acometida) → Activo 2 (transformador, padre=1) → Activo 3 (carga, padre=2)
    # Intentar que activo 1 sea alimentado por activo 3 → ciclo
    # Pero acometida no acepta padres, asi que probemos con transformador
    # Activo 2 alimentado por Activo 3 (carga) → tipo padre invalido Y ciclo
    activo_mock = {"id": 2, "nombre": "T-1.1", "tipo": "transformador",
                   "activo_padre_id": 1, "cliente_id": 44, "planta_id": 10, "activo": True}
    fuente_mock = {"id": 3, "nombre": "Horno 1", "tipo": "carga",
                   "activo_padre_id": 2, "cliente_id": 44, "planta_id": 10, "activo": True}

    with patch("web.clientes.obtener_planta", return_value=PLANTA_MOCK), \
         patch("web.clientes.obtener_activo") as mock_oa, \
         patch("web.clientes.obtener_todos_activos_cliente", return_value=TODOS_ACTIVOS), \
         patch("web.app.obtener_plantas_por_cliente", return_value=[PLANTA_MOCK]):
        mock_oa.side_effect = lambda aid: activo_mock if aid == 2 else fuente_mock
        resp = client.post("/clientes/44/planta/10/activos/2/cambio-alimentacion",
                           json={"fuente_activo_id": 3, "desde": "2026-01-15T08:00:00+00:00", "motivo": "test"})
    assert resp.status_code == 422


# ── Test d: POST cambio-alimentacion tipo padre invalido → 422 ────────────────

def test_cambio_alimentacion_tipo_invalido_422(client, app):
    """Un transformador no puede tener un carga como padre."""
    _inject_session(client, "admin")
    activo_mock = {"id": 2, "nombre": "T-1.1", "tipo": "transformador",
                   "activo_padre_id": 1, "cliente_id": 44, "planta_id": 10, "activo": True}
    fuente_mock = {"id": 3, "nombre": "Horno 1", "tipo": "carga",
                   "activo_padre_id": 2, "cliente_id": 44, "planta_id": 10, "activo": True}

    with patch("web.clientes.obtener_planta", return_value=PLANTA_MOCK), \
         patch("web.clientes.obtener_activo") as mock_oa, \
         patch("web.clientes.obtener_todos_activos_cliente", return_value=TODOS_ACTIVOS), \
         patch("web.app.obtener_plantas_por_cliente", return_value=[PLANTA_MOCK]):
        mock_oa.side_effect = lambda aid: activo_mock if aid == 2 else fuente_mock
        resp = client.post("/clientes/44/planta/10/activos/2/cambio-alimentacion",
                           json={"fuente_activo_id": 3, "desde": "2026-01-15T08:00:00+00:00"})
    assert resp.status_code == 422
    data = resp.get_json()
    assert "carga" in data["error"].lower() or "tipo" in data["error"].lower()


# ── Test e: POST cambio-alimentacion valido → 201 ────────────────────────────

def test_cambio_alimentacion_valido_201(client, app):
    """Cambio valido de alimentacion devuelve 201."""
    _inject_session(client, "admin")
    activo_mock = {"id": 3, "nombre": "Horno 1", "tipo": "carga",
                   "activo_padre_id": 2, "cliente_id": 44, "planta_id": 10, "activo": True}
    fuente_mock = {"id": 2, "nombre": "T-1.1", "tipo": "transformador",
                   "activo_padre_id": 1, "cliente_id": 44, "planta_id": 10, "activo": True}

    nueva_vigencia = {"id": 99, "activo_id": 3, "fuente_activo_id": 2,
                      "vigente_desde": "2026-01-15T08:00:00+00:00", "vigente_hasta": None,
                      "motivo": "test"}

    with patch("web.clientes.obtener_planta", return_value=PLANTA_MOCK), \
         patch("web.clientes.obtener_activo") as mock_oa, \
         patch("web.clientes.obtener_todos_activos_cliente", return_value=TODOS_ACTIVOS), \
         patch("web.clientes.declarar_cambio_alimentacion", return_value=nueva_vigencia), \
         patch("web.app.obtener_plantas_por_cliente", return_value=[PLANTA_MOCK]):
        mock_oa.side_effect = lambda aid: activo_mock if aid == 3 else (
            fuente_mock if aid == 2 else None
        )
        resp = client.post("/clientes/44/planta/10/activos/3/cambio-alimentacion",
                           json={"fuente_activo_id": 2, "desde": "2026-01-15T08:00:00+00:00", "motivo": "test"},
                           content_type="application/json")
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.get_json()}"
    data = resp.get_json()
    assert data["ok"] is True
    assert data["vigencia"]["activo_id"] == 3
