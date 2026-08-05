"""Tests para calc/telemetria_kpis.py (Task 1 — D7-A)."""
from datetime import datetime, timedelta, timezone

import pytest

from calc.telemetria_kpis import (
    atribuir_produccion_a_nodo,
    calcular_baseline_movil,
    calcular_kpis_economicos,
    calcular_kpis_energeticos,
    calcular_kpis_produccion,
    generar_sparkline,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _meds(pares_ts_kw_fp):
    """[(ts_str, kw, fp), ...] → lista de dicts."""
    return [{"ts": ts, "kw": kw, "fp": fp} for ts, kw, fp in pares_ts_kw_fp]


# ── Tests a-f ─────────────────────────────────────────────────────────────────

def test_a_kpis_energeticos_basicos():
    """energia, demanda_pico y demanda_promedio con valores esperados."""
    meds = _meds([
        ("2024-01-01T00:00:00Z", 100.0, 0.90),
        ("2024-01-01T01:00:00Z", 120.0, 0.91),
        ("2024-01-01T02:00:00Z", 110.0, 0.89),
    ])
    r = calcular_kpis_energeticos(meds, 200.0)
    # Trapezoidal: (100+120)/2*1h + (120+110)/2*1h = 110 + 115 = 225 kWh
    assert abs(r["energia_kwh"] - 225.0) < 0.01
    assert r["demanda_pico_kw"] == 120.0
    assert abs(r["demanda_promedio_kw"] - 110.0) < 0.01   # (100+120+110)/3


def test_b_fp_ponderado_por_kw_no_promedio_simple():
    """FP se pondera por potencia_activa_kw, no por conteo de muestras."""
    meds = _meds([
        ("2024-01-01T00:00:00Z", 100.0, 0.90),
        ("2024-01-01T00:15:00Z", 1000.0, 0.80),
    ])
    r = calcular_kpis_energeticos(meds, None)
    esperado = (100.0 * 0.90 + 1000.0 * 0.80) / (100.0 + 1000.0)   # ≈ 0.8091
    assert abs(r["factor_potencia_promedio"] - esperado) < 0.001
    assert r["factor_potencia_promedio"] < 0.85   # promedio simple sería 0.85


def test_c_costo_total_con_precio_y_energia():
    """costo_total_mxn = energia_kwh * precio_mxn_kwh."""
    r = calcular_kpis_economicos(
        energia_kwh=1000.0,
        precio_mxn_kwh=2.5,
        costo_cliente_factura_total=None,
        baseline_kwh=None,
    )
    assert r["costo_total_mxn"] == 2500.0
    assert r["costo_unitario_mxn_kwh"] == 2.5
    assert r["pct_sobre_factura"] is None
    assert r["ahorro_potencial_mxn"] is None


def test_d_atribuir_produccion_proporcional():
    """Nodo con 40 % de energía recibe 40 % de los m²."""
    m2 = atribuir_produccion_a_nodo(
        m2_totales_planta=10_000.0,
        energia_nodo_kwh=400.0,
        energia_total_planta_kwh=1_000.0,
    )
    assert abs(m2 - 4_000.0) < 0.01


def test_d_atribuir_produccion_energia_cero():
    """Si energia_total_planta_kwh <= 0, retorna 0.0."""
    assert atribuir_produccion_a_nodo(10_000.0, 400.0, 0.0) == 0.0


def test_e_baseline_vacio_retorna_none():
    assert calcular_baseline_movil([]) is None


def test_f_sparkline_96_a_24_puntos():
    """generar_sparkline con 96 muestras (15 min) y n_puntos=24 retorna 24 floats."""
    inicio = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = [
        {
            "ts": (inicio + timedelta(minutes=i * 15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kw": 100.0,
            "fp": 0.90,
        }
        for i in range(96)
    ]
    r = generar_sparkline(meds, 24)
    assert len(r) == 24
    assert all(isinstance(v, float) for v in r)


# ── Tests g-i (integración con endpoint) ─────────────────────────────────────

import json
from unittest.mock import MagicMock, patch


@pytest.fixture()
def _app_fase2(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FASE2_HABILITADA", "true")
    from web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def _client_fase2(_app_fase2):
    return _app_fase2.test_client()


def _inyectar_sesion(client):
    from time import time
    now = time()
    with client.session_transaction() as sess:
        sess["_user_id"] = "test-uid"
        sess["_user_email"] = "test@test.com"
        sess["_user_rol"] = "master_admin"
        sess["_empresa_id"] = 44
        sess["_access_token"] = "fake-token"
        sess["cliente_activo_id"] = 44
        sess["_session_version"] = 1
        sess["_activo_check"] = {"user_id": "test-uid", "ts": now, "activo": True}
        sess["_sv_check"] = {"user_id": "test-uid", "ts": now, "version": 1}


def _mock_get_cliente(cid):
    if cid == 44:
        return {"id": 44, "nombre": "Test Cliente", "num_cfe": 0,
                "num_gas": 0, "num_electricidad": 0, "contratos": []}
    return None


_ARBOL = [
    {"id": 1, "nombre": "Acometida", "punto_medicion": "acometida_cfe",
     "medidor_padre_id": None, "cliente_id": 44, "tipo_carga": None, "potencia_nominal_kw": None},
    {"id": 2, "nombre": "T-1.1", "punto_medicion": "transformador",
     "medidor_padre_id": 1, "cliente_id": 44, "tipo_carga": None, "potencia_nominal_kw": 500.0},
    {"id": 3, "nombre": "CBT-Horno", "punto_medicion": "carga_final",
     "medidor_padre_id": 2, "cliente_id": 44, "tipo_carga": "horno_tunel", "potencia_nominal_kw": 200.0},
]

_MEDS = [
    {"timestamp": "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0, "factor_potencia": 0.90},
    {"timestamp": "2024-01-01T01:00:00Z", "potencia_activa_kw": 120.0, "factor_potencia": 0.91},
]


def _mock_repo(mock_arbol, mock_meds_act, mock_meds_ant, mock_prod):
    """Retorna dict de patches para el endpoint de telemetría."""
    return {
        "storage.repository.get_cliente_con_conteos": MagicMock(side_effect=_mock_get_cliente),
        "storage.repository.obtener_arbol_medidores": MagicMock(return_value=mock_arbol),
        "storage.repository.obtener_descendientes_ids": MagicMock(return_value=[3]),
        "storage.repository.obtener_mediciones_recientes": MagicMock(side_effect=[
            mock_meds_act,   # periodo actual (hoja 3)
            mock_meds_ant,   # periodo anterior (hoja 3)
        ]),
        "storage.repository.obtener_produccion_diaria": MagicMock(return_value=mock_prod),
        "calc.telemetria_costos.calcular_costo_periodo": MagicMock(return_value={
            "costo_mxn": 5000.0, "precio_mxn_kwh": 2.5,
            "fuente": "factura_mes_exacto", "mes_referencia": "2024-01",
        }),
    }


def test_g_endpoint_devuelve_kpis_paneles(_client_fase2):
    """Endpoint /telemetria/data incluye kpis_paneles con las tres subclaves y meta."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [{"fecha": "2024-01-01", "m2_producidos": 5000.0}])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get(
            "/clientes/44/dashboard/telemetria/data?rango=24h",
            headers={"Accept": "application/json"},
        )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "kpis_paneles" in data
    kp = data["kpis_paneles"]
    assert "energeticos" in kp
    assert "economicos" in kp
    assert "produccion" in kp
    assert "meta" in kp


def test_h_kpis_flags_aplica_y_oculto(_client_fase2):
    """indice_utilizacion_pct tiene aplica_a_nodo; pct_sobre_factura tiene oculto_en_nodo."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    idx = data["kpis_paneles"]["energeticos"]["indice_utilizacion_pct"]
    assert idx["aplica_a_nodo"] == ["carga_final"]
    pct = data["kpis_paneles"]["economicos"]["pct_sobre_factura"]
    assert pct["oculto_en_nodo"] == ["acometida_cfe"]


def test_i_anterior_null_sin_datos_historicos(_client_fase2):
    """Si no hay mediciones históricas, los valores 'anterior' y 'delta_pct' son null."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, [], [])   # anterior vacío
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    kpi = data["kpis_paneles"]["energeticos"]["energia_kwh"]
    assert kpi["anterior"] is None
    assert kpi["delta_pct"] is None


def test_g_determinar_periodo_anterior():
    """Para cada rango, la ventana anterior termina 30 días antes de ahora
    y tiene la misma anchura que el rango."""
    from datetime import datetime, timezone, timedelta
    from calc.telemetria_kpis import determinar_periodo_anterior

    ahora = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 24h: anterior termina en ahora-30d, dura 24h
    d, h, etiq = determinar_periodo_anterior("24h", ahora)
    esperado_hasta = ahora - timedelta(days=30)
    esperado_desde = esperado_hasta - timedelta(hours=24)
    assert abs((h - esperado_hasta).total_seconds()) < 1
    assert abs((d - esperado_desde).total_seconds()) < 1
    assert "30" in etiq or "anterior" in etiq.lower()

    # 7d: dura 7 días
    d7, h7, _ = determinar_periodo_anterior("7d", ahora)
    assert abs((h7 - esperado_hasta).total_seconds()) < 1
    assert abs((d7 - (esperado_hasta - timedelta(days=7))).total_seconds()) < 1

    # 30d: dura 30 días
    d30, h30, _ = determinar_periodo_anterior("30d", ahora)
    assert abs((h30 - esperado_hasta).total_seconds()) < 1
    assert abs((d30 - (esperado_hasta - timedelta(days=30))).total_seconds()) < 1
