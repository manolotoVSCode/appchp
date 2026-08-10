"""Tests para calc/telemetria_atribucion.py.

Todas las pruebas usan funciones puras con resolver_fuente simulado (sin BD).
"""
import math
import os
import pytest
from datetime import datetime, timezone, timedelta

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from calc.telemetria_atribucion import (
    agregar_por_camino,
    integrar_por_segmentos,
    resolver_caminos,
)


# ── Utilidades de test ────────────────────────────────────────────────────────

def _n(s: str) -> str:
    """Normaliza ISO 8601 a UTC +00:00 (misma convención que _norm en el módulo)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()


# Instantes del rango de prueba: enero 2024
D  = _n("2024-01-01T00:00:00Z")   # inicio
M  = _n("2024-01-15T12:00:00Z")   # mitad
M2 = _n("2024-01-20T00:00:00Z")   # un punto más adelante
H  = _n("2024-01-31T23:59:59Z")   # fin


def make_resolver(tabla: dict) -> callable:
    """Crea un resolver simulado a partir de un dict {activo_id: [(fuente_id, desde, hasta|None)]}.

    La función recorta cada intervalo al [desde_iso, hasta_iso] solicitado, replicando
    la semántica de resolver_intervalos_fuente. hasta=None significa intervalo abierto.
    """
    def resolver(activo_id: int, desde_iso: str, hasta_iso: str) -> list[dict]:
        result = []
        for fuente_id, f_d, f_h in tabla.get(activo_id, []):
            iv_d = max(f_d, desde_iso)
            iv_h = min(f_h, hasta_iso) if f_h is not None else hasta_iso
            if iv_d < iv_h:
                result.append({
                    "fuente_activo_id": fuente_id,
                    "intervalo_desde":  iv_d,
                    "intervalo_hasta":  iv_h,
                    "motivo":           "test",
                })
        return result
    return resolver


def _meds_lineales(n: int, kw: float, desde: str, hasta: str) -> list[dict]:
    """Genera n mediciones de kW constante igualmente espaciadas en [desde, hasta]."""
    dt0 = datetime.fromisoformat(desde.replace("Z", "+00:00"))
    dt1 = datetime.fromisoformat(hasta.replace("Z", "+00:00"))
    total_s = (dt1 - dt0).total_seconds()
    return [
        {
            "ts": (dt0 + timedelta(seconds=total_s * i / (n - 1))).isoformat(),
            "kw": kw,
        }
        for i in range(n)
    ]


def _integral_trapezoid(meds: list[dict]) -> float:
    """Integral trapezoidal de referencia sobre la serie completa."""
    total = 0.0
    for i in range(1, len(meds)):
        t0 = datetime.fromisoformat(meds[i - 1]["ts"].replace("Z", "+00:00")).timestamp()
        t1 = datetime.fromisoformat(meds[i]["ts"].replace("Z", "+00:00")).timestamp()
        kw0 = meds[i - 1]["kw"]
        kw1 = meds[i]["kw"]
        total += (kw0 + kw1) / 2.0 * (t1 - t0) / 3600.0
    return total


# ── Test a — Carga sin cambios en el rango ────────────────────────────────────

def test_carga_sin_cambios():
    """Un activo con fuente constante durante todo el rango → un segmento completo."""
    resolver = make_resolver({
        10: [(1, D, None)],   # carga 10 → acometida 1, sin cambios
        # acometida 1 no tiene entradas → base case
    })
    caminos = resolver_caminos(10, D, H, resolver)

    assert len(caminos) == 1
    assert caminos[0]["camino"] == [1]
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == H


# ── Test b — Cambio de alimentación a mitad del rango ────────────────────────

def test_cambio_alimentacion():
    """La carga cambia de transformador a mitad del rango → dos segmentos."""
    resolver = make_resolver({
        20: [(2, D, M), (3, M, None)],   # carga 20: fuente 2 → fuente 3
        # transformadores 2 y 3 son raíces (acometidas): sin entradas
    })
    caminos = resolver_caminos(20, D, H, resolver)

    assert len(caminos) == 2
    assert caminos[0]["camino"] == [2]
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == M

    assert caminos[1]["camino"] == [3]
    assert caminos[1]["completo"] is True
    assert caminos[1]["desde"] == M
    assert caminos[1]["hasta"] == H


# ── Test c — Cambio en el nodo padre, sin cambio en la carga ─────────────────

def test_cambio_en_nodo_padre_subdivide():
    """El transformador (padre de la carga) cambia de subestación.
    La carga no cambia de padre, pero la intersección subdivide sus intervalos.
    """
    # Topología: carga 30 → transformador 5 (todo el rango)
    # Transformador 5: fuente 6 hasta M, luego fuente 7 desde M
    resolver = make_resolver({
        30: [(5, D, None)],         # carga → transformador (todo el rango)
        5:  [(6, D, M), (7, M, None)],  # transformador cambia de subestación
        # 6 y 7 son acometidas: sin entradas
    })
    caminos = resolver_caminos(30, D, H, resolver)

    assert len(caminos) == 2, f"esperados 2 segmentos, obtenidos {len(caminos)}"

    assert caminos[0]["camino"] == [5, 6]
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == M

    assert caminos[1]["camino"] == [5, 7]
    assert caminos[1]["completo"] is True
    assert caminos[1]["desde"] == M
    assert caminos[1]["hasta"] == H


# ── Test d — Cambio de medidor a mitad del rango ─────────────────────────────

def test_cambio_de_medidor_conserva_energia():
    """Con dos medidores distintos en dos mitades, la energía total se conserva.

    Simula el caso de dos medidores: M1 mide la primera mitad, M2 la segunda.
    Las mediciones se mezclan y la energía integrada debe ser la suma de ambas.
    """
    # Mediciones de M1: [D, M], kw=100
    # Mediciones de M2: [M, H], kw=200
    meds_m1 = _meds_lineales(5, 100.0, D, M)
    meds_m2 = _meds_lineales(5, 200.0, M, H)
    meds_merged = sorted(meds_m1 + meds_m2, key=lambda r: r["ts"])

    # Un único segmento que cubre todo el rango (sin cambio de alimentación)
    segmentos = [{"desde": D, "hasta": H, "camino": [1], "completo": True}]
    resultado = integrar_por_segmentos(meds_merged, segmentos, bucket_min=5)

    energia_esperada = _integral_trapezoid(meds_merged)
    # La energía integrada sobre las mediciones mezcladas de ambos medidores
    # debe coincidir con la integral trapezoidal directa.
    assert abs(resultado[0]["energia_kwh"] - energia_esperada) < 1e-4
    # hueco_datos_min puede ser > 0 dado que las mediciones sintéticas están
    # espaciadas varios días, excediendo el umbral 2×bucket_min. Lo que se
    # verifica aquí es la conservación de energía, no la densidad de datos.


# ── Test e — Hueco de vigencia ────────────────────────────────────────────────

def test_hueco_de_vigencia():
    """Activo sin vigencia entre M y M2 → segmento incompleto en ese intervalo."""
    resolver = make_resolver({
        40: [
            (1, D, M),    # vigencia hasta M
            (1, M2, None),  # vigencia desde M2 (hueco entre M y M2)
        ],
    })
    caminos = resolver_caminos(40, D, H, resolver)

    # Tres segmentos: [D,M] completo, [M,M2] incompleto, [M2,H] completo
    assert len(caminos) == 3

    assert caminos[0]["completo"] is True
    assert caminos[0]["camino"] == [1]
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == M

    assert caminos[1]["completo"] is False
    assert caminos[1]["camino"] == []
    assert caminos[1]["desde"] == M
    assert caminos[1]["hasta"] == M2

    assert caminos[2]["completo"] is True
    assert caminos[2]["camino"] == [1]
    assert caminos[2]["desde"] == M2
    assert caminos[2]["hasta"] == H


# ── Test f — Acometida como activo consultado ─────────────────────────────────

def test_acometida_caso_base():
    """El activo consultado no tiene entradas en la tabla → segmento completo, camino vacío."""
    resolver = make_resolver({})   # acometida: sin ninguna entrada
    caminos = resolver_caminos(1, D, H, resolver)

    assert len(caminos) == 1
    assert caminos[0]["camino"] == []
    assert caminos[0]["completo"] is True
    assert caminos[0]["desde"] == D
    assert caminos[0]["hasta"] == H


# ── Test g — Invariante: suma de energías == integral trapezoidal completa ────

def test_invariante_suma_energia():
    """La suma de energia_kwh de todos los segmentos iguala la integral trapezoidal total."""
    # Mediciones con kW variable sobre el rango completo
    dt0 = datetime.fromisoformat(D.replace("Z", "+00:00"))
    dt1 = datetime.fromisoformat(H.replace("Z", "+00:00"))
    total_s = (dt1 - dt0).total_seconds()
    n = 10
    meds = [
        {
            "ts": (dt0 + timedelta(seconds=total_s * i / (n - 1))).isoformat(),
            "kw": 50.0 + 30.0 * math.sin(2 * math.pi * i / n),
        }
        for i in range(n)
    ]

    # Dos segmentos que dividen el rango exactamente por la mitad
    segmentos = [
        {"desde": D, "hasta": M, "camino": [1], "completo": True},
        {"desde": M, "hasta": H, "camino": [2], "completo": True},
    ]
    resultado = integrar_por_segmentos(meds, segmentos, bucket_min=5)

    energia_total_segs = sum(s["energia_kwh"] for s in resultado)
    energia_trapezoid = _integral_trapezoid(meds)

    # Tolerancia 1e-6: el round(..., 6) intermedio en integrar_por_segmentos
    # introduce hasta ~5e-7 por segmento. Con dos segmentos la cota es ~1e-6.
    # La invariante es exacta en matemática exacta; la tolerancia es float.
    assert abs(energia_total_segs - energia_trapezoid) < 1e-6, (
        f"Invariante violada: suma segmentos={energia_total_segs:.9f}, "
        f"trapezoid={energia_trapezoid:.9f}"
    )
