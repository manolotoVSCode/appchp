# telemetria/seed.py
"""Generador de mediciones sintéticas para validación de UI de telemetría.

Reutilizable desde rutas web y desde CLI de semilla (entrega B).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any


_V_BASE = 13_800.0   # V (media tensión, acometida típica)
_SQRT3 = math.sqrt(3)


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
    """Genera *n_intervalos* lecturas sintéticas del Acuvim II.

    Parámetros
    ----------
    medidor_id   : id del medidor (determina la semilla RNG → reproducible).
    desde_utc    : timestamp de inicio (UTC con tzinfo).
    n_intervalos : número de lecturas (default 96 = 24 h a 15 min).
    intervalo_min: minutos entre lecturas (default 15).

    Retorna
    -------
    Lista de dicts compatibles con las columnas de mediciones_tiempo_real.
    """
    rng = random.Random(medidor_id)
    mediciones: list[dict[str, Any]] = []

    kwh_acc = rng.uniform(10_000.0, 50_000.0)
    kvarh_acc = rng.uniform(2_000.0, 8_000.0)

    for i in range(n_intervalos):
        ts = desde_utc + timedelta(minutes=i * intervalo_min)
        hora = ts.hour + ts.minute / 60.0

        kw_total = _perfil_kw(hora) * rng.uniform(0.95, 1.05)
        pf = rng.uniform(0.88, 0.97)
        kva_total = kw_total / pf
        kvar_total = math.sqrt(max(0.0, kva_total ** 2 - kw_total ** 2))
        freq = 60.0 + rng.uniform(-0.05, 0.05)

        # Voltajes L-N ≈ 13 800 V ±1 %
        v_an = _V_BASE * rng.uniform(0.99, 1.01)
        v_bn = _V_BASE * rng.uniform(0.99, 1.01)
        v_cn = _V_BASE * rng.uniform(0.99, 1.01)
        v_avg_ln = (v_an + v_bn + v_cn) / 3.0
        v_ab = v_an * _SQRT3
        v_bc = v_bn * _SQRT3
        v_ca = v_cn * _SQRT3
        v_avg_ll = (v_ab + v_bc + v_ca) / 3.0

        # Corrientes: P = √3 × VLL × I × pf
        i_base = kw_total * 1_000.0 / (_SQRT3 * v_avg_ll * pf)
        i_a = i_base * rng.uniform(0.98, 1.02)
        i_b = i_base * rng.uniform(0.98, 1.02)
        i_c = i_base * rng.uniform(0.98, 1.02)
        i_n = abs(i_a + i_b + i_c - 3 * i_base) * 0.1
        i_avg = (i_a + i_b + i_c) / 3.0

        # Distribución por fase (equilibrada con pequeño desbalance)
        kw_a = kw_total / 3 * rng.uniform(0.97, 1.03)
        kw_b = kw_total / 3 * rng.uniform(0.97, 1.03)
        kw_c = kw_total - kw_a - kw_b
        kvar_a = kvar_total / 3 * rng.uniform(0.97, 1.03)
        kvar_b = kvar_total / 3 * rng.uniform(0.97, 1.03)
        kvar_c = kvar_total - kvar_a - kvar_b
        kva_a = math.sqrt(kw_a ** 2 + kvar_a ** 2)
        kva_b = math.sqrt(kw_b ** 2 + kvar_b ** 2)
        kva_c = math.sqrt(kw_c ** 2 + kvar_c ** 2)
        pf_a = kw_a / kva_a if kva_a else pf
        pf_b = kw_b / kva_b if kva_b else pf
        pf_c = kw_c / kva_c if kva_c else pf

        # Acumuladores monótonos crecientes
        kwh_acc += kw_total * (intervalo_min / 60.0)
        kvarh_acc += kvar_total * (intervalo_min / 60.0)

        def r(v: float, d: int = 3) -> float:
            return round(v, d)

        mediciones.append({
            "medidor_id":      medidor_id,
            "timestamp":       ts.isoformat(),
            "secuencia_fases": "positiva",
            "v_an":            r(v_an),
            "v_bn":            r(v_bn),
            "v_cn":            r(v_cn),
            "v_avg_ln":        r(v_avg_ln),
            "v_ab":            r(v_ab),
            "v_bc":            r(v_bc),
            "v_ca":            r(v_ca),
            "v_avg_ll":        r(v_avg_ll),
            "i_a":             r(i_a),
            "i_b":             r(i_b),
            "i_c":             r(i_c),
            "i_n":             r(i_n),
            "i_avg":           r(i_avg),
            "kw_a":            r(kw_a, 4),
            "kw_b":            r(kw_b, 4),
            "kw_c":            r(kw_c, 4),
            "kw_total":        r(kw_total, 4),
            "kvar_a":          r(kvar_a, 4),
            "kvar_b":          r(kvar_b, 4),
            "kvar_c":          r(kvar_c, 4),
            "kvar_total":      r(kvar_total, 4),
            "kva_a":           r(kva_a, 4),
            "kva_b":           r(kva_b, 4),
            "kva_c":           r(kva_c, 4),
            "kva_total":       r(kva_total, 4),
            "pf_a":            r(pf_a, 4),
            "pf_b":            r(pf_b, 4),
            "pf_c":            r(pf_c, 4),
            "pf_total":        r(pf, 4),
            "frecuencia_hz":   r(freq),
            "kwh_importado":   r(kwh_acc),
            "kwh_exportado":   0.0,
            "kvarh_importado": r(kvarh_acc),
            "kvarh_exportado": 0.0,
            "thd_v_a":         r(rng.uniform(1.0, 3.5)),
            "thd_v_b":         r(rng.uniform(1.0, 3.5)),
            "thd_v_c":         r(rng.uniform(1.0, 3.5)),
            "thd_i_a":         r(rng.uniform(5.0, 15.0)),
            "thd_i_b":         r(rng.uniform(5.0, 15.0)),
            "thd_i_c":         r(rng.uniform(5.0, 15.0)),
            "demanda_kw":      r(kw_total, 4),
            "demanda_kva":     r(kva_total, 4),
            "demanda_max_kw":  r(kw_total * 1.1, 4),
            "demanda_max_kva": r(kva_total * 1.1, 4),
        })

    return mediciones
