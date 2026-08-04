"""Tests para modelo jerárquico de medidores y generador por tipo de carga."""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_supabase():
    """Crea un mock de _supabase con cadena fluente."""
    sb = MagicMock()
    tbl = MagicMock()
    sb.table.return_value = tbl
    tbl.insert.return_value  = tbl
    tbl.select.return_value  = tbl
    tbl.update.return_value  = tbl
    tbl.delete.return_value  = tbl
    tbl.eq.return_value      = tbl
    tbl.order.return_value   = tbl
    tbl.limit.return_value   = tbl
    tbl.single.return_value  = tbl
    tbl.in_.return_value     = tbl
    return sb, tbl


# ── a) crear_medidor_jerarquico ───────────────────────────────────────────────

def test_crear_medidor_jerarquico_persiste_campos():
    """a: crear_medidor_jerarquico envía medidor_padre_id, tipo_carga y
    potencia_nominal_kw a Supabase."""
    from storage import repository
    sb, tbl = _mock_supabase()
    tbl.execute.return_value = MagicMock(data=[{
        "id": 99, "cliente_id": 44, "nombre": "Horno 1",
        "medidor_padre_id": 10, "tipo_carga": "horno_tunel",
        "potencia_nominal_kw": 1500,
    }])

    with patch.object(repository, "_supabase", sb):
        resultado = repository.crear_medidor_jerarquico(
            cliente_id=44,
            nombre="Horno 1",
            punto_medicion="carga_final",
            medidor_padre_id=10,
            tipo_carga="horno_tunel",
            potencia_nominal_kw=1500,
        )

    # Verificar que se llamó insert con el payload correcto
    call_args = tbl.insert.call_args[0][0]
    assert call_args["medidor_padre_id"] == 10
    assert call_args["tipo_carga"] == "horno_tunel"
    assert call_args["potencia_nominal_kw"] == 1500
    assert resultado["id"] == 99


# ── b) obtener_hijos ──────────────────────────────────────────────────────────

def test_obtener_hijos_filtra_por_padre():
    """b: obtener_hijos usa eq('medidor_padre_id', medidor_id)."""
    from storage import repository
    sb, tbl = _mock_supabase()
    tbl.execute.return_value = MagicMock(data=[
        {"id": 11, "medidor_padre_id": 5},
        {"id": 12, "medidor_padre_id": 5},
    ])

    with patch.object(repository, "_supabase", sb):
        hijos = repository.obtener_hijos(5)

    tbl.eq.assert_any_call("medidor_padre_id", 5)
    assert len(hijos) == 2
    assert hijos[0]["id"] == 11


# ── c) obtener_descendientes_ids ──────────────────────────────────────────────

def test_obtener_descendientes_ids_arbol_3_niveles():
    """c: obtener_descendientes_ids devuelve nietos y biznietos de una acometida."""
    from storage import repository

    # Árbol: acometida(1) → transformadores(2, 3) → cargas(4, 5, 6, 7)
    def mock_obtener_hijos(mid):
        arbol = {
            1: [{"id": 2}, {"id": 3}],
            2: [{"id": 4}, {"id": 5}],
            3: [{"id": 6}, {"id": 7}],
            4: [], 5: [], 6: [], 7: [],
        }
        return arbol.get(mid, [])

    with patch.object(repository, "obtener_hijos", side_effect=mock_obtener_hijos):
        ids = repository.obtener_descendientes_ids(1)

    assert set(ids) == {2, 3, 4, 5, 6, 7}


# ── d) obtener_arbol_medidores ────────────────────────────────────────────────

def test_obtener_arbol_medidores_aplica_limit_20000():
    """d: obtener_arbol_medidores llama .limit(20000)."""
    from storage import repository
    sb, tbl = _mock_supabase()
    tbl.execute.return_value = MagicMock(data=[])

    with patch.object(repository, "_supabase", sb):
        repository.obtener_arbol_medidores(44)

    tbl.limit.assert_called_with(20000)


# ── e) horno_tunel dentro de rango ───────────────────────────────────────────

def test_horno_tunel_rango_potencia():
    """e: horno_tunel produce potencias en [0.72, 0.93] × nominal en 96 muestras."""
    from telemetria.seed import generar_mediciones_por_carga
    medidor = {"id": 999, "tipo_carga": "horno_tunel",
               "potencia_nominal_kw": 1000.0, "punto_medicion": "carga_final"}
    desde = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = generar_mediciones_por_carga(medidor, desde, n=96, intervalo=15)
    assert len(meds) == 96
    for m in meds:
        p = m["potencia_activa_kw"]
        assert 0.72 * 1000.0 <= p <= 0.93 * 1000.0, f"horno fuera de rango: {p}"


# ── f) prensa nocturna ≤15% nominal ──────────────────────────────────────────

def test_prensa_nocturna_bajo_15pct():
    """f: prensa produce ≤0.15 × nominal entre 22:00-06:00 UTC."""
    from telemetria.seed import generar_mediciones_por_carga
    medidor = {"id": 888, "tipo_carga": "prensa",
               "potencia_nominal_kw": 700.0, "punto_medicion": "carga_final"}
    # Empezar a las 22:00 UTC, generar 8h (32 intervalos) → cubre 22-06
    desde = datetime(2024, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
    meds = generar_mediciones_por_carga(medidor, desde, n=32, intervalo=15)
    for m in meds:
        ts_hora = datetime.fromisoformat(m["timestamp"]).hour
        if ts_hora >= 22 or ts_hora < 6:
            assert m["potencia_activa_kw"] <= 0.15 * 700.0, \
                f"prensa nocturna fuera de rango: {m['potencia_activa_kw']} a hora {ts_hora}"


# ── g) atomizador madrugada ≤30% nominal ─────────────────────────────────────

def test_atomizador_madrugada_bajo_30pct():
    """g: atomizador produce ≤0.30 × nominal entre 00:00-05:00 UTC."""
    from telemetria.seed import generar_mediciones_por_carga
    medidor = {"id": 777, "tipo_carga": "atomizador",
               "potencia_nominal_kw": 1200.0, "punto_medicion": "carga_final"}
    desde = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = generar_mediciones_por_carga(medidor, desde, n=20, intervalo=15)  # 0-5h
    for m in meds:
        ts_hora = datetime.fromisoformat(m["timestamp"]).hour
        if ts_hora < 5:
            assert m["potencia_activa_kw"] <= 0.30 * 1200.0, \
                f"atomizador madrugada fuera de rango: {m['potencia_activa_kw']}"


# ── h) claves exactas del esquema ────────────────────────────────────────────

_COLUMNAS_ESPERADAS = frozenset({
    "medidor_id", "timestamp",
    "potencia_activa_kw", "potencia_reactiva_kvar", "potencia_aparente_kva",
    "factor_potencia",
    "energia_activa_importada_kwh", "energia_activa_exportada_kwh",
    "energia_reactiva_importada_kvarh", "energia_reactiva_exportada_kvarh",
    "voltaje_l1_v", "voltaje_l2_v", "voltaje_l3_v",
    "corriente_l1_a", "corriente_l2_a", "corriente_l3_a",
    "frecuencia_hz", "secuencia_fases",
})

def test_claves_exactas_esquema():
    """h: las claves del dict son EXACTAMENTE las columnas de mediciones_tiempo_real."""
    from telemetria.seed import generar_mediciones_por_carga
    medidor = {"id": 1, "tipo_carga": "motor",
               "potencia_nominal_kw": 500.0, "punto_medicion": "carga_final"}
    desde = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = generar_mediciones_por_carga(medidor, desde, n=1, intervalo=15)
    assert set(meds[0].keys()) == _COLUMNAS_ESPERADAS


# ── i) energía activa monótona creciente ─────────────────────────────────────

def test_energia_activa_monotona_creciente():
    """i: energia_activa_importada_kwh es monotónamente creciente."""
    from telemetria.seed import generar_mediciones_por_carga
    medidor = {"id": 42, "tipo_carga": "molino",
               "potencia_nominal_kw": 900.0, "punto_medicion": "carga_final"}
    desde = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = generar_mediciones_por_carga(medidor, desde, n=96, intervalo=15)
    energias = [m["energia_activa_importada_kwh"] for m in meds]
    for i in range(1, len(energias)):
        assert energias[i] >= energias[i - 1], \
            f"energía no creciente en posición {i}: {energias[i-1]} → {energias[i]}"


# ── j) voltajes por nivel de tensión ─────────────────────────────────────────

def test_voltajes_carga_final_baja_tension():
    """j (parte 1): voltajes en carga_final ∈ [251, 257] V."""
    from telemetria.seed import generar_mediciones_por_carga
    medidor = {"id": 55, "tipo_carga": "motor",
               "potencia_nominal_kw": 200.0, "punto_medicion": "carga_final"}
    desde = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = generar_mediciones_por_carga(medidor, desde, n=10, intervalo=15)
    for m in meds:
        for fase in ("voltaje_l1_v", "voltaje_l2_v", "voltaje_l3_v"):
            v = m[fase]
            assert 251 <= v <= 257, f"voltaje BT fuera de rango: {v}"


def test_voltajes_transformador_media_tension():
    """j (parte 2): voltajes en transformador ∈ [7887, 8047] V."""
    from telemetria.seed import generar_mediciones_por_carga
    medidor = {"id": 66, "tipo_carga": None,
               "potencia_nominal_kw": 2425.0, "punto_medicion": "transformador"}
    desde = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = generar_mediciones_por_carga(medidor, desde, n=10, intervalo=15)
    for m in meds:
        for fase in ("voltaje_l1_v", "voltaje_l2_v", "voltaje_l3_v"):
            v = m[fase]
            assert 7887 <= v <= 8047, f"voltaje MT fuera de rango: {v}"
