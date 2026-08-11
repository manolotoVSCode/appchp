"""Tests para el dashboard de telemetría de cliente (Fase 2 D2)."""
import json
import pytest
from unittest.mock import patch, MagicMock

PLANTA_MOCK_TD = {"id": 1, "nombre": "Planta Norte", "activo": True}

ARBOL_MOCK = [
    {"id": 1, "nombre": "Acometida CFE-1", "punto_medicion": "acometida_cfe",
     "activo_padre_id": None, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": None, "potencia_nominal_kw": None, "medidor_id": None},
    {"id": 2, "nombre": "T-1.1", "punto_medicion": "transformador",
     "activo_padre_id": 1, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": None, "potencia_nominal_kw": 500.0, "medidor_id": None},
    {"id": 3, "nombre": "Horno 1", "punto_medicion": "carga_final",
     "activo_padre_id": 2, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": "horno_tunel", "potencia_nominal_kw": 200.0, "medidor_id": 10},
    {"id": 4, "nombre": "Horno 2", "punto_medicion": "carga_final",
     "activo_padre_id": 2, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": "horno_tunel", "potencia_nominal_kw": 250.0, "medidor_id": 11},
]

# Activos planos para la vista HTML (sin punto_medicion — tabla activos_electricos)
ACTIVOS_PLANOS_MOCK = [
    {"id": a["id"], "nombre": a["nombre"], "tipo": a.get("punto_medicion", "carga"),
     "activo": True, "planta_id": 1, "plantas": {"nombre": "Planta Norte"},
     "activo_padre_id": a["activo_padre_id"]}
    for a in ARBOL_MOCK
]

MEDICIONES_MOCK = [
    {"timestamp": "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0, "factor_potencia": 0.90},
    {"timestamp": "2024-01-01T00:15:00Z", "potencia_activa_kw": 120.0, "factor_potencia": 0.91},
    {"timestamp": "2024-01-01T00:30:00Z", "potencia_activa_kw": 110.0, "factor_potencia": 0.89},
]


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
        # Cache de plantas y context_processor para evitar llamadas a Supabase en
        # before_request (_resolver_planta_activa) y context_processor (_inject_globals)
        sess["_plantas_cache"] = {
            "cliente_id": cliente_activo_id, "ts": now,
            "plantas": [PLANTA_MOCK_TD],
        }
        sess["_cp_cache"] = {
            "id": cliente_activo_id, "planta_id": 1, "ts": now,
            "data": {
                "id": cliente_activo_id, "nombre": "Iberica Tiles",
                "contratos": [], "logo_url": None,
            },
        }


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
         patch("web.app.obtener_plantas_por_cliente", return_value=[PLANTA_MOCK_TD]), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_todos_activos_cliente", return_value=ACTIVOS_PLANOS_MOCK), \
         patch("storage.repository.get_mediciones_por_cliente", return_value=[]), \
         patch("storage.repository.get_contratos_por_planta", return_value=[]):
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria")
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
         patch("web.app.obtener_plantas_por_cliente", return_value=[PLANTA_MOCK_TD]), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_todos_activos_cliente", return_value=ACTIVOS_PLANOS_MOCK), \
         patch("storage.repository.get_mediciones_por_cliente", return_value=[]), \
         patch("storage.repository.get_contratos_por_planta", return_value=[]):
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria")
    assert resp.status_code == 200


# ── Test d ─────────────────────────────────────────────────────────────────
def test_telemetria_fase2_deshabilitada_404(client, app):
    """Con FASE2_HABILITADA=False la ruta devuelve 404."""
    app.config["FASE2_HABILITADA"] = False
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("web.app.obtener_plantas_por_cliente", return_value=[PLANTA_MOCK_TD]):
        resp = client.get("/clientes/44/dashboard/telemetria")
    assert resp.status_code == 404


# Patches comunes para el endpoint /data (D3 añade 4 funciones de repo de costos)
_PATCHES_COSTO = dict(
    obtener_factura_cfe_cliente_mes=None,
    obtener_ultimas_facturas_cfe=[],
    obtener_factura_ppa_cliente_mes=None,
    obtener_ultimas_facturas_ppa=[],
)


def _default_rir(medidor_id, desde_iso, hasta_iso):
    """Default resolver_intervalos_rol: todo carga."""
    return [{"rol": "carga", "intervalo_desde": desde_iso,
             "intervalo_hasta": hasta_iso, "motivo": None}]


def _patch_costo():
    """Retorna context managers de patch para el endpoint /data.

    Índices fijos (usado por los tests como patches[N]):
      [0] obtener_factura_cfe_cliente_mes
      [1] obtener_ultimas_facturas_cfe
      [2] obtener_factura_ppa_cliente_mes
      [3] obtener_ultimas_facturas_ppa
      [4] obtener_produccion_diaria
      [5] obtener_ultimo_timestamp_cliente  ← ancla temporal sintética
      [6] resolver_intervalos_medidor       ← devuelve [] (sin historial de medidor)
      [7] resolver_intervalos_fuente        ← devuelve [] (todos activos son raíz)
      [8] obtener_plantas_por_cliente       ← evita HTTP en before_request
      [9] resolver_intervalos_contrato      ← devuelve [] (sin contrato asignado)
      [10] resolver_intervalos_rol          ← devuelve todo como carga
    """
    from datetime import datetime, timezone
    _ts_fijo = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    return [
        patch("storage.repository.obtener_factura_cfe_cliente_mes", return_value=None),
        patch("storage.repository.obtener_ultimas_facturas_cfe", return_value=[]),
        patch("storage.repository.obtener_factura_ppa_cliente_mes", return_value=None),
        patch("storage.repository.obtener_ultimas_facturas_ppa", return_value=[]),
        patch("storage.repository.obtener_produccion_diaria", return_value=[]),
        # Ancla temporal sintética: evita llamada real a Supabase en tests
        patch("storage.repository.obtener_ultimo_timestamp_cliente", return_value=_ts_fijo),
        # Pipeline de atribución: sin historial de vigencias → energía cero sin HTTP
        patch("storage.repository.resolver_intervalos_medidor", return_value=[]),
        patch("storage.repository.resolver_intervalos_fuente", return_value=[]),
        # before_request _resolver_planta_activa: sin HTTP a Supabase
        patch("web.app.obtener_plantas_por_cliente",
              return_value=[{"id": 1, "nombre": "Planta 1", "activo": True}]),
        # Contrato de acometida: sin asignación por defecto
        patch("storage.repository.resolver_intervalos_contrato", return_value=[]),
        # Rol de medidor: todo carga por defecto
        patch("storage.repository.resolver_intervalos_rol", side_effect=_default_rir),
    ]


# ── Test e ─────────────────────────────────────────────────────────────────
def test_telemetria_data_json_claves_esperadas(client, app):
    """GET .../data devuelve JSON con nodo_seleccionado, serie_temporal, kpis, arbol_sunburst."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_mediciones_para_rango", return_value=MEDICIONES_MOCK), \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")
    assert resp.status_code == 200
    data = resp.get_json()
    for clave in ("nodo_seleccionado", "serie_temporal", "kpis", "arbol_sunburst"):
        assert clave in data, f"Falta clave: {clave}"


# ── Test f ─────────────────────────────────────────────────────────────────
def test_telemetria_data_sunburst_consistencia_energia(client, app):
    """Suma de kWh de cargas del anillo externo es consistente con su transformador (tolerancia 0.1%)."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_mediciones_para_rango", return_value=MEDICIONES_MOCK), \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")
    data = resp.get_json()
    arbol = data["arbol_sunburst"]
    # El arbol_sunburst empieza en la acometida; sus hijos son transformadores
    for t in arbol.get("hijos", []):
        suma_cargas = sum(c["energia_kwh"] for c in t.get("hijos", []))
        energia_t = t["energia_kwh"]
        if energia_t > 0:
            diff_pct = abs(suma_cargas - energia_t) / energia_t * 100
            assert diff_pct < 0.1, f"Activo {t['nombre']}: {diff_pct:.4f}% de desviación"


# ── Test g ─────────────────────────────────────────────────────────────────
def test_telemetria_data_nodo_carga_final_sin_agregacion(client, app):
    """Con nodo_id de una carga_final la serie refleja solo esa carga.

    Fix 4: el endpoint ahora consulta TODAS las cargas del árbol para que el
    sunburst muestre energía correcta en cualquier vista.  Los KPIs siguen
    proviniendo únicamente de la carga seleccionada.  En ARBOL_MOCK, los
    medidores 3 y 4 son carga_final; el endpoint consulta ambos para el
    periodo actual (sunburst) y solo el 3 para la comparativa (-30 d).
    """
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    carga_mock = MEDICIONES_MOCK
    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_mediciones_para_rango", return_value=carga_mock) as mock_omr, \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h&nodo_id=3")
    assert resp.status_code == 200
    # Las mediciones se consultan por medidor_id (10 y 11), no por activo_id (3 y 4)
    calls = mock_omr.call_args_list
    consulted_ids = {c[0][0] for c in calls}
    assert 10 in consulted_ids, "El medidor 10 (activo 3) debe consultarse"
    assert 11 in consulted_ids, "El medidor 11 (activo 4) debe consultarse para el sunburst"
    assert consulted_ids <= {10, 11}, f"Solo deben consultarse medidores 10 y 11, no {consulted_ids}"


# ── Test h ─────────────────────────────────────────────────────────────────
def test_telemetria_sin_medidores_estado_vacio_200(client, app):
    """Sin medidores, el dashboard devuelve 200 con texto de estado vacío."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("web.app.obtener_plantas_por_cliente", return_value=[PLANTA_MOCK_TD]), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=[]), \
         patch("storage.repository.obtener_todos_activos_cliente", return_value=[]), \
         patch("storage.repository.get_mediciones_por_cliente", return_value=[]), \
         patch("storage.repository.get_contratos_por_planta", return_value=[]):
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria")
    assert resp.status_code == 200
    assert "aún no tiene medidores" in resp.get_data(as_text=True)


# ── Test i ─────────────────────────────────────────────────────────────────
def test_post_produccion_ok(client, app):
    """POST válido con m2_mes ≥ 0 → 200, ok=True, registros=N."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.upsert_produccion_mes", return_value=20):
        resp = client.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 6, "m2_mes": 12000.0},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["registros"] == 20


# ── Test j ─────────────────────────────────────────────────────────────────
def test_post_produccion_sin_m2_mes_400(client, app):
    """POST sin campo m2_mes → 400."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente_con_conteos):
        resp = client.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 6},
        )
    assert resp.status_code == 400


# ── Test k ─────────────────────────────────────────────────────────────────
def test_post_produccion_m2_negativo_400(client, app):
    """POST con m2_mes negativo → 400."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente_con_conteos):
        resp = client.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 6, "m2_mes": -100.0},
        )
    assert resp.status_code == 400


# ── Test l ─────────────────────────────────────────────────────────────────
def test_post_produccion_sin_autenticacion_redirige(client, app):
    """POST sin sesión activa → before_request redirige a login (302).

    El hook _require_login redirige antes de que el route pueda devolver 401.
    """
    app.config["FASE2_HABILITADA"] = True
    # Sin _injectar_sesion: usuario no autenticado
    resp = client.post(
        "/clientes/44/telemetria/produccion",
        json={"anio": 2024, "mes": 6, "m2_mes": 12000.0},
    )
    assert resp.status_code == 302


# ── Test m ─────────────────────────────────────────────────────────────────
def test_post_produccion_fase2_deshabilitada_404(client, app):
    """POST con FASE2_HABILITADA=False → 404."""
    app.config["FASE2_HABILITADA"] = False
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    # Parchea render_template para que devuelva solo HTML sin llamar a Supabase
    def dummy_render(template, **context):
        return "<html>Error 404</html>"

    with patch("web.app.render_template", side_effect=dummy_render), \
         patch("web.app.log_error"):
        resp = client.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 6, "m2_mes": 12000.0},
        )
    assert resp.status_code == 404


# ── Test n ─────────────────────────────────────────────────────────────────
# Árbol de integración: acometida 100 → transformador 101 → carga 102 (medidor cambia
# de 10 → 12 a T_MID); acometida 100 → carga 103 (medidor 11, sin fuente → incompleto).
_T0_INT  = "2024-01-01T00:00:00Z"
_T_MID   = "2024-01-01T12:00:00Z"
_T1_INT  = "2024-01-02T00:00:00Z"

ARBOL_MOCK_INT = [
    {"id": 100, "nombre": "Acometida", "punto_medicion": "acometida_cfe",
     "activo_padre_id": None, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": None, "potencia_nominal_kw": None, "medidor_id": None},
    {"id": 101, "nombre": "T-Int", "punto_medicion": "transformador",
     "activo_padre_id": 100, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": None, "potencia_nominal_kw": 500.0, "medidor_id": None},
    # medidor_id=12 representa el medidor vigente actual tras el cambio
    {"id": 102, "nombre": "Carga-A", "punto_medicion": "carga_final",
     "activo_padre_id": 101, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": "horno", "potencia_nominal_kw": 200.0, "medidor_id": 12},
    # medidor_id=11, fuente con fuente_activo_id=None → segmento incompleto
    {"id": 103, "nombre": "Carga-B", "punto_medicion": "carga_final",
     "activo_padre_id": 100, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": "compresor", "potencia_nominal_kw": 100.0, "medidor_id": 11},
]


def _meds_constantes(desde_iso: str, hasta_iso: str, kw: float) -> list[dict]:
    """Dos mediciones a los extremos con kW constante (datos sintéticos)."""
    return [
        {"timestamp": desde_iso, "potencia_activa_kw": kw, "factor_potencia": 0.90},
        {"timestamp": hasta_iso,  "potencia_activa_kw": kw, "factor_potencia": 0.90},
    ]


def test_atribucion_cambio_medidor_y_alimentacion(client, app):
    """Pipeline de atribución: cambio de medidor y fuente sin alimentación.

    Verifica tres invariantes:
      1. Energía del nodo raíz == energía atribuida por activo 102 (2 × 100 kW × 12 h = 2400 kWh).
      2. El nodo 103 expone cobertura_incompleta=True en el JSON (fuente_activo_id=None).
      3. obtener_mediciones_para_rango se invoca con el desde/hasta RECORTADO al tramo,
         nunca con el rango completo para el medidor 10 (que solo estuvo activo hasta T_MID).
    """
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)

    # ── side_effect: tramos de medidor por activo ──────────────────────────
    def _rim_se(activo_id, desde_iso, hasta_iso):
        if activo_id == 102:
            return [
                {"medidor_id": 10, "intervalo_desde": _T0_INT,  "intervalo_hasta": _T_MID,   "motivo": "inicial"},
                {"medidor_id": 12, "intervalo_desde": _T_MID,   "intervalo_hasta": _T1_INT,  "motivo": "cambio"},
            ]
        if activo_id == 103:
            return [{"medidor_id": 11, "intervalo_desde": _T0_INT, "intervalo_hasta": _T1_INT, "motivo": "inicial"}]
        return []

    # ── side_effect: cadena de alimentación ascendente ────────────────────
    _ISO0 = "2024-01-01T00:00:00+00:00"
    _ISO1 = "2024-01-02T00:00:00+00:00"

    def _rif_se(activo_id, desde_dt, hasta_dt):
        if activo_id == 102:
            return [{"fuente_activo_id": 101, "intervalo_desde": _ISO0, "intervalo_hasta": _ISO1, "motivo": "test"}]
        if activo_id == 101:
            return [{"fuente_activo_id": 100, "intervalo_desde": _ISO0, "intervalo_hasta": _ISO1, "motivo": "test"}]
        if activo_id == 103:
            # fuente_activo_id=None → segmento completo=False
            return [{"fuente_activo_id": None, "intervalo_desde": _ISO0, "intervalo_hasta": _ISO1, "motivo": "test"}]
        return []  # activo 100: acometida raíz

    # ── side_effect: mediciones por medidor ───────────────────────────────
    def _omfr_se(medidor_id, desde, hasta, rango):
        kw_map = {10: 100.0, 12: 100.0, 11: 50.0}
        kw = kw_map.get(medidor_id, 0.0)
        return _meds_constantes(desde, hasta, kw)

    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK_INT), \
         patch("storage.repository.obtener_mediciones_para_rango", side_effect=_omfr_se) as mock_omfr, \
         patch("storage.repository.resolver_intervalos_medidor", side_effect=_rim_se), \
         patch("storage.repository.resolver_intervalos_fuente",  side_effect=_rif_se), \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[8], patches[9], patches[10]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")

    assert resp.status_code == 200
    data = resp.get_json()

    arbol = data["arbol_sunburst"]
    assert arbol["id"] == 100, "Raíz del sunburst debe ser la acometida (id=100)"

    # ── Invariante 1: energía de la raíz == energía atribuida por activo 102 ──
    # Activo 102: dos tramos × 100 kW × 12 h = 2400 kWh
    # Activo 103: completo=False → camino vacío → no propaga energía a la raíz
    assert arbol["energia_kwh"] == pytest.approx(2400.0, abs=1.0), (
        f"Energía raíz esperada 2400 kWh, obtenida {arbol['energia_kwh']}"
    )

    # ── Invariante 2: nodo 103 expone cobertura_incompleta=True ──────────────
    def _buscar_nodo(nodo_dict, nodo_id):
        if nodo_dict["id"] == nodo_id:
            return nodo_dict
        for hijo in nodo_dict.get("hijos", []):
            encontrado = _buscar_nodo(hijo, nodo_id)
            if encontrado:
                return encontrado
        return None

    nodo_103 = _buscar_nodo(arbol, 103)
    assert nodo_103 is not None, "Activo 103 debe aparecer en arbol_sunburst"
    assert nodo_103["cobertura_incompleta"] is True, (
        "Activo 103 tiene fuente_activo_id=None → cobertura_incompleta debe ser True"
    )

    # ── Invariante 3: _omfr llamada con tramo recortado para medidor 10 ──────
    calls = mock_omfr.call_args_list
    # El medidor 10 solo estuvo activo hasta T_MID; la llamada debe usar hasta=T_MID
    calls_med10 = [c for c in calls if c[0][0] == 10]
    assert len(calls_med10) >= 1, "Debe existir al menos una llamada a _omfr con medidor_id=10"
    for c in calls_med10:
        hasta_arg = c[0][2]
        assert hasta_arg == _T_MID, (
            f"Llamada con medidor 10 debe usar hasta={_T_MID} (tramo), "
            f"no el rango completo. Obtenido: hasta={hasta_arg}"
        )
    # El medidor 12 en la atribución debe usar desde=T_MID (tramo recortado)
    calls_med12_attr = [c for c in calls if c[0][0] == 12 and c[0][1] == _T_MID]
    assert len(calls_med12_attr) >= 1, (
        f"Debe existir call (12, {_T_MID}, {_T1_INT}) para el tramo atributivo"
    )


# ── Test o ─────────────────────────────────────────────────────────────────
# Escenario: cambio de contrato en la acometida a mitad del rango.
# Contrato 5 (precio 2.0 MXN/kWh) en la primera mitad,
# contrato 6 (precio 3.0 MXN/kWh) en la segunda mitad.
# Activo 200: acometida sin medidor
# Activo 201: carga, medidor 20, alimentada por acometida 200 todo el rango

_T0_CONT  = "2024-01-01T00:00:00Z"
_T_MID_C  = "2024-01-01T12:00:00Z"
_T1_CONT  = "2024-01-02T00:00:00Z"

ARBOL_MOCK_CONT = [
    {"id": 200, "nombre": "Acometida-C", "punto_medicion": "acometida_cfe",
     "activo_padre_id": None, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": None, "potencia_nominal_kw": None, "medidor_id": None,
     "tipo": "acometida"},
    {"id": 201, "nombre": "Carga-C", "punto_medicion": "carga_final",
     "activo_padre_id": 200, "cliente_id": 44, "planta_id": 1,
     "tipo_carga": "horno", "potencia_nominal_kw": 200.0, "medidor_id": 20,
     "tipo": "carga"},
]


def test_contrato_cambia_a_mitad_del_rango(client, app):
    """El JSON expone costos con dos precios distintos al cambiar contrato en la acometida.

    Verifica:
      1. El nodo raíz tiene costo_mxn != None (hay al menos un segmento con precio).
      2. Los segmentos valorados incluyen al menos dos contrato_id distintos (5 y 6).
      3. El costo total del nodo raíz coincide con la suma de los costes por segmento.
    """
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)

    # La acometida 200 cambia de contrato 5 → 6 en T_MID_C
    def _ric_se(activo_id, desde_iso, hasta_iso):
        if activo_id == 200:
            return [
                {"contrato_id": 5, "intervalo_desde": _T0_CONT,  "intervalo_hasta": _T_MID_C, "motivo": "inicial"},
                {"contrato_id": 6, "intervalo_desde": _T_MID_C,  "intervalo_hasta": _T1_CONT, "motivo": "cambio"},
            ]
        return []

    # Activo 201 se alimenta de la acometida 200 todo el rango
    def _rif_se(activo_id, desde_dt, hasta_dt):
        _ISO0 = "2024-01-01T00:00:00+00:00"
        _ISO1 = "2024-01-02T00:00:00+00:00"
        if activo_id == 201:
            return [{"fuente_activo_id": 200, "intervalo_desde": _ISO0, "intervalo_hasta": _ISO1, "motivo": "test"}]
        return []  # acometida 200: raíz

    # Medidor 20: 100 kW constante todo el rango
    def _omfr_se(medidor_id, desde, hasta, rango):
        return [
            {"timestamp": desde, "potencia_activa_kw": 100.0, "factor_potencia": 0.9},
            {"timestamp": hasta,  "potencia_activa_kw": 100.0, "factor_potencia": 0.9},
        ]

    # Contrato 5: 2.0 MXN/kWh; contrato 6: 3.0 MXN/kWh
    def _opupc_se(contrato_id, anio, mes):
        precios = {5: 2.0, 6: 3.0}
        precio = precios.get(contrato_id)
        return {"precio_mxn_kwh": precio, "fuente": "factura_mes_exacto", "mes_referencia": f"{anio}-{mes:02d}"}

    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK_CONT), \
         patch("storage.repository.obtener_mediciones_para_rango", side_effect=_omfr_se), \
         patch("storage.repository.resolver_intervalos_medidor", return_value=[
             {"medidor_id": 20, "intervalo_desde": _T0_CONT, "intervalo_hasta": _T1_CONT, "motivo": "test"}
         ]), \
         patch("storage.repository.resolver_intervalos_fuente", side_effect=_rif_se), \
         patch("storage.repository.resolver_intervalos_contrato", side_effect=_ric_se), \
         patch("calc.telemetria_costos.obtener_precio_unitario_por_contrato", side_effect=_opupc_se), \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[8], patches[10]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")

    assert resp.status_code == 200
    data = resp.get_json()
    arbol = data["arbol_sunburst"]
    assert arbol["id"] == 200

    # Invariante 1: el nodo raíz tiene costo (algún segmento tiene precio)
    assert arbol["costo_mxn"] is not None, "El nodo raíz debe tener costo_mxn cuando hay contratos vigentes"

    # Invariante 2: el costo total refleja ambos precios
    # 100 kW × 12 h = 1200 kWh × 2.0 MXN/kWh = 2400 MXN (contrato 5)
    # 100 kW × 12 h = 1200 kWh × 3.0 MXN/kWh = 3600 MXN (contrato 6)
    # Total esperado = 6000 MXN
    # (con tolerancia por mediciones sintéticas de 2 puntos)
    assert arbol["costo_mxn"] == pytest.approx(6000.0, abs=50.0), (
        f"Costo esperado ~6000 MXN (dos contratos × 1200 kWh a tarifas 2.0 y 3.0), obtenido {arbol['costo_mxn']}"
    )

    # Invariante 3: campos nuevos presentes en el sunburst
    assert "energia_sin_costo_kwh" in arbol


# ── Test p ─────────────────────────────────────────────────────────────────
def test_medidor_centro_carga_no_altera_raiz(client, app):
    """Medidor con rol centro_carga → energía del nodo raíz en el sunburst es 0.

    Los segmentos de cabecera no entran en la atribución por camino.
    Solo alimentan magnitudes_planta.energia_cabecera.
    """
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)

    # Árbol mínimo: acometida 300 → carga 301 (medidor 30)
    arbol_mock_p = [
        {"id": 300, "nombre": "Acometida-P", "punto_medicion": "acometida_cfe",
         "activo_padre_id": None, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": None, "potencia_nominal_kw": None, "medidor_id": None,
         "tipo": "acometida"},
        {"id": 301, "nombre": "Carga-P", "punto_medicion": "carga_final",
         "activo_padre_id": 300, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": "horno", "potencia_nominal_kw": 200.0, "medidor_id": 30,
         "tipo": "carga"},
    ]

    def _omfr_se(medidor_id, desde, hasta, rango):
        return [
            {"timestamp": desde, "potencia_activa_kw": 100.0, "factor_potencia": 0.9},
            {"timestamp": hasta, "potencia_activa_kw": 100.0, "factor_potencia": 0.9},
        ]

    # resolver_intervalos_rol: medidor 30 es centro_carga todo el rango
    def _rir_se(medidor_id, desde_iso, hasta_iso):
        if medidor_id == 30:
            return [{"rol": "centro_carga", "intervalo_desde": desde_iso,
                      "intervalo_hasta": hasta_iso, "motivo": None}]
        return [{"rol": "carga", "intervalo_desde": desde_iso,
                  "intervalo_hasta": hasta_iso, "motivo": None}]

    _ISO0 = "2024-01-01T00:00:00+00:00"
    _ISO1 = "2024-01-02T00:00:00+00:00"

    def _rif_se(activo_id, desde_dt, hasta_dt):
        if activo_id == 301:
            return [{"fuente_activo_id": 300, "intervalo_desde": _ISO0,
                      "intervalo_hasta": _ISO1, "motivo": "test"}]
        return []

    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=arbol_mock_p), \
         patch("storage.repository.obtener_mediciones_para_rango", side_effect=_omfr_se), \
         patch("storage.repository.resolver_intervalos_medidor", return_value=[
             {"medidor_id": 30, "intervalo_desde": "2024-01-01T00:00:00Z",
              "intervalo_hasta": "2024-01-02T00:00:00Z", "motivo": "test"}
         ]), \
         patch("storage.repository.resolver_intervalos_fuente", side_effect=_rif_se), \
         patch("storage.repository.resolver_intervalos_rol", side_effect=_rir_se), \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[8], patches[9]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")

    assert resp.status_code == 200
    data = resp.get_json()
    arbol = data["arbol_sunburst"]

    # Nodo raíz: energía de carga es 0 (todo fue filtrado como cabecera)
    assert arbol["energia_kwh"] == pytest.approx(0.0, abs=0.1), (
        f"Con medidor centro_carga, la energía del sunburst raíz debe ser 0, obtenida {arbol['energia_kwh']}"
    )

    # magnitudes_planta.energia_cabecera debe contener centro_carga > 0
    mp = data.get("magnitudes_planta", {})
    assert mp.get("energia_cabecera", {}).get("centro_carga", 0) > 0, (
        "La energía del medidor centro_carga debe aparecer en magnitudes_planta.energia_cabecera"
    )


# ── Test q: balance_residuo presente cuando los 3 roles existen ──────────
def test_residuo_balance_presente(client, app):
    """Endpoint retorna balance_residuo cuando los 3 roles de cabecera existen."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)

    # Tres cargas, cada una con un rol de cabecera distinto
    arbol_mock_q = [
        {"id": 400, "nombre": "Acometida-Q", "punto_medicion": "acometida_cfe",
         "activo_padre_id": None, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": None, "potencia_nominal_kw": None, "medidor_id": None,
         "tipo": "acometida"},
        {"id": 401, "nombre": "Med-Interc", "punto_medicion": "carga_final",
         "activo_padre_id": 400, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": "medidor_cabecera", "potencia_nominal_kw": None, "medidor_id": 41,
         "tipo": "carga"},
        {"id": 402, "nombre": "Med-GenNeta", "punto_medicion": "carga_final",
         "activo_padre_id": 400, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": "medidor_cabecera", "potencia_nominal_kw": None, "medidor_id": 42,
         "tipo": "carga"},
        {"id": 403, "nombre": "Med-CC", "punto_medicion": "carga_final",
         "activo_padre_id": 400, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": "medidor_cabecera", "potencia_nominal_kw": None, "medidor_id": 43,
         "tipo": "carga"},
    ]

    def _omfr_se(medidor_id, desde, hasta, rango):
        kw_map = {41: 60.0, 42: 40.0, 43: 110.0}
        kw = kw_map.get(medidor_id, 0.0)
        return [
            {"timestamp": desde, "potencia_activa_kw": kw, "factor_potencia": 0.9},
            {"timestamp": hasta, "potencia_activa_kw": kw, "factor_potencia": 0.9},
        ]

    def _rir_se(medidor_id, desde_iso, hasta_iso):
        rol_map = {41: "interconexion", 42: "generacion_neta", 43: "centro_carga"}
        rol = rol_map.get(medidor_id, "carga")
        return [{"rol": rol, "intervalo_desde": desde_iso, "intervalo_hasta": hasta_iso, "motivo": None}]

    _ISO0 = "2024-01-01T00:00:00+00:00"
    _ISO1 = "2024-01-02T00:00:00+00:00"

    def _rif_se(activo_id, desde_dt, hasta_dt):
        if activo_id in (401, 402, 403):
            return [{"fuente_activo_id": 400, "intervalo_desde": _ISO0,
                      "intervalo_hasta": _ISO1, "motivo": "test"}]
        return []

    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=arbol_mock_q), \
         patch("storage.repository.obtener_mediciones_para_rango", side_effect=_omfr_se), \
         patch("storage.repository.resolver_intervalos_medidor", return_value=[
             {"medidor_id": 41, "intervalo_desde": "2024-01-01T00:00:00Z",
              "intervalo_hasta": "2024-01-02T00:00:00Z", "motivo": "test"}
         ]), \
         patch("storage.repository.resolver_intervalos_fuente", side_effect=_rif_se), \
         patch("storage.repository.resolver_intervalos_rol", side_effect=_rir_se), \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[8], patches[9]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")

    assert resp.status_code == 200
    data = resp.get_json()
    mp = data.get("magnitudes_planta", {})
    assert mp.get("balance_residuo") is not None, "balance_residuo debe estar presente con los 3 roles"
    assert "residuo_kwh" in mp["balance_residuo"]


# ── Test r: balance_residuo ausente cuando falta un rol ──────────────────
def test_residuo_balance_ausente(client, app):
    """Endpoint retorna balance_residuo=None cuando falta un rol de cabecera."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)

    # Solo un medidor con rol interconexion, sin generacion_neta ni centro_carga
    arbol_mock_r = [
        {"id": 500, "nombre": "Acometida-R", "punto_medicion": "acometida_cfe",
         "activo_padre_id": None, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": None, "potencia_nominal_kw": None, "medidor_id": None,
         "tipo": "acometida"},
        {"id": 501, "nombre": "Med-I", "punto_medicion": "carga_final",
         "activo_padre_id": 500, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": "medidor_cabecera", "potencia_nominal_kw": None, "medidor_id": 51,
         "tipo": "carga"},
    ]

    def _omfr_se(medidor_id, desde, hasta, rango):
        return [
            {"timestamp": desde, "potencia_activa_kw": 100.0, "factor_potencia": 0.9},
            {"timestamp": hasta, "potencia_activa_kw": 100.0, "factor_potencia": 0.9},
        ]

    def _rir_se(medidor_id, desde_iso, hasta_iso):
        if medidor_id == 51:
            return [{"rol": "interconexion", "intervalo_desde": desde_iso,
                      "intervalo_hasta": hasta_iso, "motivo": None}]
        return [{"rol": "carga", "intervalo_desde": desde_iso,
                  "intervalo_hasta": hasta_iso, "motivo": None}]

    _ISO0 = "2024-01-01T00:00:00+00:00"
    _ISO1 = "2024-01-02T00:00:00+00:00"

    def _rif_se(activo_id, desde_dt, hasta_dt):
        if activo_id == 501:
            return [{"fuente_activo_id": 500, "intervalo_desde": _ISO0,
                      "intervalo_hasta": _ISO1, "motivo": "test"}]
        return []

    patches = _patch_costo()
    with patch("storage.repository.get_cliente_con_conteos", side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=arbol_mock_r), \
         patch("storage.repository.obtener_mediciones_para_rango", side_effect=_omfr_se), \
         patch("storage.repository.resolver_intervalos_medidor", return_value=[
             {"medidor_id": 51, "intervalo_desde": "2024-01-01T00:00:00Z",
              "intervalo_hasta": "2024-01-02T00:00:00Z", "motivo": "test"}
         ]), \
         patch("storage.repository.resolver_intervalos_fuente", side_effect=_rif_se), \
         patch("storage.repository.resolver_intervalos_rol", side_effect=_rir_se), \
         patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[8], patches[9]:
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")

    assert resp.status_code == 200
    data = resp.get_json()
    mp = data.get("magnitudes_planta", {})
    assert mp.get("balance_residuo") is None, "balance_residuo debe ser None sin los 3 roles"
