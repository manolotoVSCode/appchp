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
