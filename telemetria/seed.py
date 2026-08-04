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


# ── Generador por tipo de carga ───────────────────────────────────────────────

_V_MT = _V_BASE / _SQRT3   # ~7967 V L-N media tensión (13 800 / √3)
_V_BT = 440.0 / _SQRT3     # ~254 V L-N baja tensión (440 / √3)

_FP_RANGES: dict[str, tuple[float, float]] = {
    "horno_tunel":        (0.92, 0.96),
    "prensa":             (0.85, 0.92),
    "motor":              (0.85, 0.92),
    "atomizador":         (0.83, 0.90),
    "molino":             (0.83, 0.90),
    "ventilador":         (0.83, 0.90),
    "pulidora":           (0.85, 0.92),
    "generico":           (0.88, 0.95),
    "servicios_auxiliares": (0.88, 0.95),
}


def _fraccion_carga(tipo_carga: str | None, hora: float, rng: random.Random) -> float:
    """Fracción de potencia nominal para el tipo de carga y hora del día (0-24)."""
    if tipo_carga == "horno_tunel":
        # Casi plano, senoidal muy leve. base ∈ [0.75, 0.90], ruido ±3 %.
        base = 0.75 + 0.15 * (0.5 + 0.5 * math.sin(2 * math.pi * (hora / 24 - 0.25)))
        return base + rng.uniform(-0.03, 0.03)

    if tipo_carga == "atomizador":
        if hora < 5:
            return 0.10
        if hora < 7:
            t = (hora - 5) / 2.0
            return 0.10 + 0.75 * t
        if hora < 20:
            return 0.80 + rng.uniform(0.0, 0.10)
        if hora < 22:
            t = (hora - 20) / 2.0
            return 0.85 - 0.65 * t
        return 0.20

    if tipo_carga == "prensa":
        if hora < 6:
            return 0.05
        if hora < 22:
            raw = 0.85 + rng.uniform(-0.10, 0.10)
            return max(0.60, min(0.95, raw))
        return 0.10

    # Default: senoidal industrial, valle 0.30 madrugada, pico 0.85 mediodía.
    base = 0.575 + 0.275 * math.sin(math.pi * (hora / 12.0 - 0.5))
    return max(0.30, min(0.85, base)) + rng.uniform(-0.05, 0.05)


def generar_mediciones_por_carga(
    medidor: dict,
    desde_utc: datetime,
    n: int = 96,
    intervalo: int = 15,
) -> list[dict[str, Any]]:
    """Genera *n* mediciones con perfil realista según tipo_carga del medidor.

    Parámetros
    ----------
    medidor      : dict con al menos id, tipo_carga, potencia_nominal_kw,
                   punto_medicion.
    desde_utc    : timestamp de inicio (con tzinfo).
    n            : número de lecturas (default 96 = 24 h a 15 min).
    intervalo    : minutos entre lecturas (default 15).

    Retorna
    -------
    Lista de dicts cuyas claves son EXACTAMENTE las columnas de
    mediciones_tiempo_real.
    """
    medidor_id         = medidor["id"]
    tipo_carga         = medidor.get("tipo_carga")
    potencia_nominal   = float(medidor.get("potencia_nominal_kw") or 1000.0)
    punto_medicion     = medidor.get("punto_medicion", "carga_final")

    # Voltaje base según nivel de tensión
    v_base = _V_MT if punto_medicion in ("acometida_cfe", "transformador") else _V_BT

    fp_min, fp_max = _FP_RANGES.get(tipo_carga or "generico", (0.88, 0.95))

    rng = random.Random(medidor_id)
    kwh_acc  = rng.uniform(10_000.0, 50_000.0)
    kvarh_acc = rng.uniform(2_000.0,  8_000.0)

    mediciones: list[dict[str, Any]] = []

    for i in range(n):
        ts   = desde_utc + timedelta(minutes=i * intervalo)
        hora = ts.hour + ts.minute / 60.0

        frac = _fraccion_carga(tipo_carga, hora, rng)
        frac = max(0.0, min(0.95, frac))          # nunca supera 95 % del nominal

        pact   = potencia_nominal * frac
        fp     = rng.uniform(fp_min, fp_max)
        preact = pact * math.tan(math.acos(fp)) if pact > 0 else 0.0
        papar  = math.sqrt(pact ** 2 + preact ** 2)
        freq   = 60.0 + rng.uniform(-0.05, 0.05)

        v1 = v_base * rng.uniform(0.99, 1.01)
        v2 = v_base * rng.uniform(0.99, 1.01)
        v3 = v_base * rng.uniform(0.99, 1.01)
        v_ll = (v1 + v2 + v3) / 3.0 * _SQRT3

        if v_ll > 0 and papar > 0:
            i_base = papar * 1_000.0 / (_SQRT3 * v_ll)
        else:
            i_base = 0.0

        i1 = i_base * rng.uniform(0.98, 1.02)
        i2 = i_base * rng.uniform(0.98, 1.02)
        i3 = i_base * rng.uniform(0.98, 1.02)

        kwh_acc  += pact   * (intervalo / 60.0)
        kvarh_acc += preact * (intervalo / 60.0)

        def r(v: float, d: int = 4) -> float:
            return round(v, d)

        mediciones.append({
            "medidor_id":                       medidor_id,
            "timestamp":                        ts.isoformat(),
            "potencia_activa_kw":               r(pact),
            "potencia_reactiva_kvar":           r(preact),
            "potencia_aparente_kva":            r(papar),
            "factor_potencia":                  r(fp),
            "energia_activa_importada_kwh":     r(kwh_acc),
            "energia_activa_exportada_kwh":     0.0,
            "energia_reactiva_importada_kvarh": r(kvarh_acc),
            "energia_reactiva_exportada_kvarh": 0.0,
            "voltaje_l1_v":                     r(v1),
            "voltaje_l2_v":                     r(v2),
            "voltaje_l3_v":                     r(v3),
            "corriente_l1_a":                   r(i1),
            "corriente_l2_a":                   r(i2),
            "corriente_l3_a":                   r(i3),
            "frecuencia_hz":                    r(freq),
            "secuencia_fases":                  "positiva",
        })

    return mediciones
