"""Tests para el dashboard de telemetría de cliente (Fase 2 D2)."""
import json
import pytest
from unittest.mock import patch, MagicMock

ARBOL_MOCK = [
    {"id": 1, "nombre": "Acometida CFE-1", "punto_medicion": "acometida_cfe",
     "medidor_padre_id": None, "cliente_id": 44, "tipo_carga": None, "potencia_nominal_kw": None},
    {"id": 2, "nombre": "T-1.1", "punto_medicion": "transformador",
     "medidor_padre_id": 1, "cliente_id": 44, "tipo_carga": None, "potencia_nominal_kw": 500.0},
    {"id": 3, "nombre": "Horno 1", "punto_medicion": "carga_final",
     "medidor_padre_id": 2, "cliente_id": 44, "tipo_carga": "horno_tunel", "potencia_nominal_kw": 200.0},
    {"id": 4, "nombre": "Horno 2", "punto_medicion": "carga_final",
     "medidor_padre_id": 2, "cliente_id": 44, "tipo_carga": "horno_tunel", "potencia_nominal_kw": 250.0},
]

MEDICIONES_MOCK = [
    {"timestamp": "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0, "factor_potencia": 0.90},
    {"timestamp": "2024-01-01T00:15:00Z", "potencia_activa_kw": 120.0, "factor_potencia": 0.91},
    {"timestamp": "2024-01-01T00:30:00Z", "potencia_activa_kw": 110.0, "factor_potencia": 0.89},
]

DESC_IDS_MOCK = [3, 4]  # Hijos de T-1.1


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


def _injectar_sesion(client, rol, empresa_id=44, cliente_activo_id=44, clientes_ids=None):
    """Inyecta sesión Flask directamente (sin llamar a Supabase)."""
    from time import time
    now = time()
    with client.session_transaction() as sess:
        sess["_user_id"] = "mock-uuid"
        sess["_user_email"] = "test@test.com"
        sess["_user_rol"] = rol
        sess["_empresa_id"] = empresa_id
        sess["_access_token"] = "mock-token"
        sess["cliente_activo_id"] = cliente_activo_id
        if clientes_ids is not None:
            sess["_clientes_ids"] = clientes_ids
        # Cache de verificación de sesión para no llamar a Supabase en before_request
        sess["_session_version"] = 1
        sess["_activo_check"] = {"user_id": "mock-uuid", "ts": now, "activo": True}
        sess["_sv_check"] = {"user_id": "mock-uuid", "ts": now, "version": 1}


def _mock_get_cliente_con_conteos(cid):
    if cid == 44:
        return {"id": 44, "nombre": "Iberica Tiles Planta 1", "num_cfe": 12,
                "num_gas": 12, "num_electricidad": 12, "contratos": []}
    return None


# ── Test a ─────────────────────────────────────────────────────────────────
def test_telemetria_usuario_normal_empresa_propia_200(client, app):
    """usuario_normal asignada a empresa 44 obtiene 200."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "usuario_normal", empresa_id=44,
                     cliente_activo_id=44, clientes_ids=[44])
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository._supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = ARBOL_MOCK
        resp = client.get("/clientes/44/dashboard/telemetria")
    assert resp.status_code == 200


# ── Test b ─────────────────────────────────────────────────────────────────
def test_telemetria_usuario_normal_otra_empresa_redirige(client, app):
    """usuario_normal de empresa 99 no puede ver cliente 44 — redirect."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "usuario_normal", empresa_id=99,
                     cliente_activo_id=99, clientes_ids=[99])
    resp = client.get("/clientes/44/dashboard/telemetria")
    assert resp.status_code in (302, 403)


# ── Test c ─────────────────────────────────────────────────────────────────
def test_telemetria_master_admin_cualquier_cliente_200(client, app):
    """master_admin puede ver cualquier cliente."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", empresa_id=None, cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository._supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = ARBOL_MOCK
        resp = client.get("/clientes/44/dashboard/telemetria")
    assert resp.status_code == 200


# ── Test d ─────────────────────────────────────────────────────────────────
def test_telemetria_fase2_deshabilitada_404(client, app):
    """Con FASE2_HABILITADA=False la ruta devuelve 404."""
    app.config["FASE2_HABILITADA"] = False
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository._supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        resp = client.get("/clientes/44/dashboard/telemetria")
    assert resp.status_code == 404


# ── Test e ─────────────────────────────────────────────────────────────────
def test_telemetria_data_json_claves_esperadas(client, app):
    """GET .../data devuelve JSON con nodo_seleccionado, serie_temporal, kpis, arbol_sunburst."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_medidores", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_descendientes_ids", return_value=DESC_IDS_MOCK), \
         patch("storage.repository.obtener_mediciones_recientes", return_value=MEDICIONES_MOCK):
        resp = client.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    assert resp.status_code == 200
    data = resp.get_json()
    for clave in ("nodo_seleccionado", "serie_temporal", "kpis", "arbol_sunburst"):
        assert clave in data, f"Falta clave: {clave}"


# ── Test f ─────────────────────────────────────────────────────────────────
def test_telemetria_data_sunburst_consistencia_energia(client, app):
    """Suma de kWh de cargas del anillo externo es consistente con su transformador (tolerancia 0.1%)."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_medidores", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_descendientes_ids", return_value=DESC_IDS_MOCK), \
         patch("storage.repository.obtener_mediciones_recientes", return_value=MEDICIONES_MOCK):
        resp = client.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = resp.get_json()
    arbol = data["arbol_sunburst"]
    # El arbol_sunburst empieza en la acometida; sus hijos son transformadores
    for t in arbol.get("hijos", []):
        suma_cargas = sum(c["energia_kwh"] for c in t.get("hijos", []))
        energia_t = t["energia_kwh"]
        if energia_t > 0:
            diff_pct = abs(suma_cargas - energia_t) / energia_t * 100
            assert diff_pct < 0.1, f"Transformador {t['nombre']}: {diff_pct:.4f}% de desviación"


# ── Test g ─────────────────────────────────────────────────────────────────
def test_telemetria_data_nodo_carga_final_sin_agregacion(client, app):
    """Con nodo_id de una carga_final, la serie refleja solo esa carga."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    carga_mock = MEDICIONES_MOCK
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_medidores", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_descendientes_ids", return_value=[]), \
         patch("storage.repository.obtener_mediciones_recientes", return_value=carga_mock) as mock_omr:
        resp = client.get("/clientes/44/dashboard/telemetria/data?rango=24h&nodo_id=3")
    assert resp.status_code == 200
    data = resp.get_json()
    # Solo se consultó el medidor 3
    calls = mock_omr.call_args_list
    assert len(calls) == 1
    assert calls[0][0][0] == 3


# ── Test h ─────────────────────────────────────────────────────────────────
def test_telemetria_sin_medidores_estado_vacio_200(client, app):
    """Sin medidores, el dashboard devuelve 200 con texto de estado vacío."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository._supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        resp = client.get("/clientes/44/dashboard/telemetria")
    assert resp.status_code == 200
    assert "aún no tiene medidores" in resp.get_data(as_text=True)
