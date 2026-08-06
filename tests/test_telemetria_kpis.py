"""Tests para calc/telemetria_kpis.py (Task 1 — D7-A)."""
import os
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import datetime, timedelta, timezone

import pytest

from calc.telemetria_kpis import (
    atribuir_produccion_a_nodo,
    calcular_kpis_economicos,
    calcular_kpis_energeticos,
    calcular_kpis_produccion,
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


def test_f_produccion_para_periodo_usa_promedio():
    """Si no hay datos en el rango y usar_promedio_historico=True, usa el promedio histórico."""
    from datetime import datetime, timezone
    from unittest.mock import patch
    from storage.repository import obtener_produccion_para_periodo

    historico_data = [
        {"fecha": "2024-01-01", "m2_producidos": 5000.0},
        {"fecha": "2024-01-02", "m2_producidos": 5000.0},
        {"fecha": "2024-01-03", "m2_producidos": 0.0},  # domingo
    ]

    desde = datetime(2024, 2, 1, tzinfo=timezone.utc)
    hasta = datetime(2024, 2, 3, tzinfo=timezone.utc)

    with patch("storage.repository.obtener_produccion_diaria") as mock_opd:
        mock_opd.side_effect = [
            [],             # primera llamada: sin datos en el rango [2024-02-01, 2024-02-03]
            historico_data, # segunda llamada: datos históricos de hasta 90 días atrás
        ]
        result = obtener_produccion_para_periodo(44, desde, hasta, usar_promedio_historico=True)

    # Promedio de [5000, 5000, 0] = 10000/3 ≈ 3333.33; × 3 días = 10000
    assert abs(result - 10000.0) < 1.0


def test_f2_produccion_para_periodo_sin_historico_retorna_cero():
    """Si no hay datos y usar_promedio_historico=True pero tampoco hay histórico, retorna 0."""
    from datetime import datetime, timezone
    from unittest.mock import patch
    from storage.repository import obtener_produccion_para_periodo

    desde = datetime(2024, 2, 1, tzinfo=timezone.utc)
    hasta = datetime(2024, 2, 3, tzinfo=timezone.utc)

    with patch("storage.repository.obtener_produccion_diaria") as mock_opd:
        mock_opd.side_effect = [[], []]  # sin datos en ambas llamadas
        result = obtener_produccion_para_periodo(44, desde, hasta, usar_promedio_historico=True)

    assert result == 0.0


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
    app.config["WTF_CSRF_ENABLED"] = False
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
        "storage.repository.obtener_mediciones_para_rango": MagicMock(side_effect=[
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
    """pct_sobre_factura tiene oculto_en_nodo; costo_unitario_mxn_kwh tiene fuente_precio."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    energeticos = data["kpis_paneles"]["energeticos"]
    # indice_utilizacion_pct ya NO existe en la nueva estructura
    assert "indice_utilizacion_pct" not in energeticos
    pct = data["kpis_paneles"]["economicos"]["pct_sobre_factura"]
    assert pct["oculto_en_nodo"] == ["acometida_cfe"]
    costo_u = data["kpis_paneles"]["economicos"]["costo_unitario_mxn_kwh"]
    assert "fuente_precio" in costo_u


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


def test_j_determinar_periodo_anterior():
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


def test_k_obtener_mediciones_para_rango_elige_tabla():
    """rango='24h' llama a obtener_agregados_5min;
    '7d' y '30d' llaman a obtener_agregados_horarios."""
    from unittest.mock import patch, MagicMock
    from storage.repository import obtener_mediciones_para_rango

    fila_5min   = {"bucket_5min":  "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0,
                   "factor_potencia": 0.90, "energia_activa_importada_kwh": 8.33}
    fila_hora   = {"bucket_hora":  "2024-01-01T00:00:00Z", "potencia_activa_kw": 95.0,
                   "factor_potencia": 0.88, "energia_activa_importada_kwh": 95.0}

    with patch("storage.repository.obtener_agregados_5min", return_value=[fila_5min]) as mock_5m, \
         patch("storage.repository.obtener_agregados_horarios", return_value=[fila_hora]) as mock_ho:

        # 24h → 5min
        r24 = obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "24h")
        mock_5m.assert_called_once()
        mock_ho.assert_not_called()
        assert r24[0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert r24[0]["potencia_activa_kw"] == 100.0

        mock_5m.reset_mock()
        mock_ho.reset_mock()

        # 7d → horario
        r7 = obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-08T00:00:00Z", "7d")
        mock_ho.assert_called_once()
        mock_5m.assert_not_called()
        assert r7[0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert r7[0]["potencia_activa_kw"] == 95.0

        mock_5m.reset_mock()
        mock_ho.reset_mock()

        # 30d → horario
        obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-31T00:00:00Z", "30d")
        mock_ho.assert_called_once()
        mock_5m.assert_not_called()


# ── Tests e, l-o (nuevos) ─────────────────────────────────────────────────────


def test_e_precio_unitario_usa_historico_completo():
    """Si historico_completo tiene (anio, mes), retorna desde cache sin llamar a la BD."""
    from unittest.mock import patch
    from calc.telemetria_costos import obtener_precio_unitario

    historico = {
        (2024, 1): {
            "precio_mxn_kwh": 3.5,
            "fuente": "cache_test",
            "mes_referencia": "2024-01",
        }
    }

    with patch(
        "calc.telemetria_costos.obtener_precio_unitario_mxn_kwh"
    ) as mock_db:
        result = obtener_precio_unitario(44, 2024, 1, historico_completo=historico)
        mock_db.assert_not_called()

    assert result["precio_mxn_kwh"] == 3.5
    assert result["fuente"] == "cache_test"


def test_l_produccion_solo_en_rango(_client_fase2):
    """kpis_paneles.produccion incluye solo_en_rango: ['30d']."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [{"fecha": "2024-01-01", "m2_producidos": 100.0}])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    produccion = data["kpis_paneles"]["produccion"]
    assert produccion.get("solo_en_rango") == ["30d"]


def test_m_post_telemetria_produccion_distribuye(_client_fase2):
    """POST /telemetria/produccion llama a upsert_produccion_mes y retorna ok."""
    _inyectar_sesion(_client_fase2)
    with patch("storage.repository.upsert_produccion_mes", return_value=31) as mock_up, \
         patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente):
        resp = _client_fase2.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 1, "m2_mes": 120000.0},
        )
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["ok"] is True
    assert body["registros"] == 31
    mock_up.assert_called_once_with(44, 2024, 1, 120000.0)


def test_n_post_telemetria_produccion_valida_input(_client_fase2):
    """POST con valores inválidos retorna 400."""
    _inyectar_sesion(_client_fase2)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente):
        # mes fuera de rango
        r1 = _client_fase2.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 13, "m2_mes": 1000.0},
        )
        assert r1.status_code == 400

        # m2_mes negativo
        r2 = _client_fase2.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 1, "m2_mes": -1.0},
        )
        assert r2.status_code == 400


def test_o_post_telemetria_produccion_requiere_auth(_client_fase2):
    """POST sin sesión retorna 401 o redirige a login."""
    resp = _client_fase2.post(
        "/clientes/44/telemetria/produccion",
        json={"anio": 2024, "mes": 1, "m2_mes": 1000.0},
    )
    assert resp.status_code in (401, 302)
