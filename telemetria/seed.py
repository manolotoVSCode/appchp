# telemetria/seed.py
"""Generador de mediciones sintéticas para validación de UI de telemetría.

Las claves de cada dict producido son EXACTAMENTE las columnas de
mediciones_tiempo_real (information_schema es la fuente de verdad):

    medidor_id, timestamp, potencia_activa_kw, potencia_reactiva_kvar,
    potencia_aparente_kva, factor_potencia, energia_activa_importada_kwh,
    energia_activa_exportada_kwh, energia_reactiva_importada_kvarh,
    energia_reactiva_exportada_kvarh, voltaje_l1_v, voltaje_l2_v, voltaje_l3_v,
    corriente_l1_a, corriente_l2_a, corriente_l3_a, frecuencia_hz,
    secuencia_fases.

Reutilizable desde rutas web y CLI (entrega B).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

_V_BASE = 13_800.0   # V — media tensión, acometida típica industrial
_SQRT3 = math.sqrt(3)

# Claves exactas del esquema real (sin medidor_id ni timestamp que se inyectan)
_COLUMNAS_REALES: frozenset[str] = frozenset({
    "medidor_id", "timestamp",
    "potencia_activa_kw", "potencia_reactiva_kvar", "potencia_aparente_kva",
    "factor_potencia",
    "energia_activa_importada_kwh", "energia_activa_exportada_kwh",
    "energia_reactiva_importada_kvarh", "energia_reactiva_exportada_kvarh",
    "voltaje_l1_v", "voltaje_l2_v", "voltaje_l3_v",
    "corriente_l1_a", "corriente_l2_a", "corriente_l3_a",
    "frecuencia_hz", "secuencia_fases",
})


def _perfil_kw(hora_fraccion: float) -> float:
    """kW base para una hora del día (0-24). Perfil industrial realista."""
    if 6 <= hora_fraccion < 8:
        t = (hora_fraccion - 6) / 2
        return 400.0 + 600.0 * t
    if 8 <= hora_fraccion < 18:
        t = (hora_fraccion - 8) / 10
        return 1_000.0 + 400.0 * math.sin(math.pi * t)
    if 18 <= hora_fraccion < 22:
        t = (hora_fraccion - 18) / 4
        return 1_400.0 - 1_000.0 * t
    return 400.0


def generar_mediciones_sinteticas(
    medidor_id: int,
    desde_utc: datetime,
    n_intervalos: int = 96,
    intervalo_min: int = 15,
) -> list[dict[str, Any]]:
    """Genera *n_intervalos* lecturas sintéticas del medidor.

    Parámetros
    ----------
    medidor_id   : id del medidor (semilla RNG → resultados reproducibles).
    desde_utc    : timestamp de inicio (con tzinfo).
    n_intervalos : número de lecturas (default 96 = 24 h a 15 min).
    intervalo_min: minutos entre lecturas (default 15).

    Retorna
    -------
    Lista de dicts cuyas claves son EXACTAMENTE las columnas de
    mediciones_tiempo_real.
    """
    rng = random.Random(medidor_id)
    mediciones: list[dict[str, Any]] = []

    kwh_acc = rng.uniform(10_000.0, 50_000.0)
    kvarh_acc = rng.uniform(2_000.0, 8_000.0)

    for i in range(n_intervalos):
        ts = desde_utc + timedelta(minutes=i * intervalo_min)
        hora = ts.hour + ts.minute / 60.0

        pact = _perfil_kw(hora) * rng.uniform(0.95, 1.05)
        fp = rng.uniform(0.88, 0.97)
        preact = pact * math.tan(math.acos(fp))
        papar = math.sqrt(pact ** 2 + preact ** 2)  # == pact / fp
        freq = 60.0 + rng.uniform(-0.05, 0.05)

        # Voltajes L-N ≈ 13 800 V ±1 %
        v1 = _V_BASE * rng.uniform(0.99, 1.01)
        v2 = _V_BASE * rng.uniform(0.99, 1.01)
        v3 = _V_BASE * rng.uniform(0.99, 1.01)
        v_ll = (v1 + v2 + v3) / 3.0 * _SQRT3   # LL promedio

        # Corrientes por fase: I = S*1000 / (√3 × V_LL), con ±2% desbalance
        i_base = papar * 1_000.0 / (_SQRT3 * v_ll)
        i1 = i_base * rng.uniform(0.98, 1.02)
        i2 = i_base * rng.uniform(0.98, 1.02)
        i3 = i_base * rng.uniform(0.98, 1.02)

        # Acumuladores monótonos crecientes
        kwh_acc += pact * (intervalo_min / 60.0)
        kvarh_acc += preact * (intervalo_min / 60.0)

        def r(v: float, d: int = 3) -> float:
            return round(v, d)

        mediciones.append({
            "medidor_id":                      medidor_id,
            "timestamp":                       ts.isoformat(),
            "potencia_activa_kw":              r(pact, 4),
            "potencia_reactiva_kvar":          r(preact, 4),
            "potencia_aparente_kva":           r(papar, 4),
            "factor_potencia":                 r(fp, 4),
            "energia_activa_importada_kwh":    r(kwh_acc),
            "energia_activa_exportada_kwh":    0.0,
            "energia_reactiva_importada_kvarh": r(kvarh_acc),
            "energia_reactiva_exportada_kvarh": 0.0,
            "voltaje_l1_v":                    r(v1),
            "voltaje_l2_v":                    r(v2),
            "voltaje_l3_v":                    r(v3),
            "corriente_l1_a":                  r(i1),
            "corriente_l2_a":                  r(i2),
            "corriente_l3_a":                  r(i3),
            "frecuencia_hz":                   r(freq),
            "secuencia_fases":                 "positiva",
        })

    return mediciones
