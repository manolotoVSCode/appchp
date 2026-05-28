# calc/modelado_chp.py
"""Motor de cálculo del modelado CHP sobre medición cincominutal.

Recibe la serie de datos de potencia (5 min) de un mes, simula la operación
del sistema CHP intervalo a intervalo y devuelve KPIs anualizados + curva.
"""
from __future__ import annotations

import math
from typing import Any

# Factores de conversión
_KWH_A_GJ = 0.0036          # 1 kWh = 0.0036 GJ
_MIN_CARGA_PCT = 0.60        # Carga mínima del motor (60 %)
_LIMITE_HORAS_ANUALES = 8_000.0
_LIMITE_HORAS_MES = _LIMITE_HORAS_ANUALES / 12.0   # ≈ 666.67 h/mes por motor
_INTERVALO_H = 5.0 / 60.0   # 5 min en horas = 1/12 h


def modelar_chp(
    datos: list[dict],
    capacidad_nominal_kw: float,
    num_motores: int,
    margen_kw: float,
    rendimiento_electrico: float,
    costo_om_kwh: float,
    autoconsumo_pct: float,
    consumo_gas_mes_kwh: float,  # noqa: ARG001 — reservado para cálculos futuros
) -> dict[str, Any]:
    """Simula la operación CHP sobre la serie de potencia mensual.

    Parámetros
    ----------
    datos : lista de dicts {"ts": str ISO, "potencia_kw": float}
    capacidad_nominal_kw : capacidad total del sistema CHP (todos los motores)
    num_motores : número de motores idénticos en paralelo (1–4)
    margen_kw : margen de seguridad — la generación neta nunca supera
                (demanda - margen_kw)
    rendimiento_electrico : fracción (ej. 0.42)
    costo_om_kwh : MXN/kWh sobre generación bruta
    autoconsumo_pct : consumo auxiliar del propio sistema (fracción, ej. 0.03)
    consumo_gas_mes_kwh : consumo total de gas del cliente en el mes (kWh)

    Retorna
    -------
    dict con claves "kpis" y "curva".
    """
    if not datos:
        return _resultado_vacio()

    if num_motores < 1:
        num_motores = 1
    if capacidad_nominal_kw <= 0:
        return _resultado_vacio()

    cap_unitaria_kw = capacidad_nominal_kw / num_motores

    # Horas acumuladas por motor en el mes (índice 0 … num_motores-1)
    horas_motor: list[float] = [0.0] * num_motores

    gen_neta_mes_kwh = 0.0
    consumo_cliente_mes_kwh = 0.0
    curva: list[dict] = []

    for punto in datos:
        ts = punto["ts"]
        demanda_kw = float(punto["potencia_kw"])
        consumo_cliente_mes_kwh += demanda_kw * _INTERVALO_H

        # ── Paso 1: calcular motores activos y generación neta ──────────────
        objetivo_neto_kw = demanda_kw - margen_kw

        if objetivo_neto_kw <= 0:
            gen_neta_kw = 0.0
            motores_activos = 0
        elif objetivo_neto_kw >= capacidad_nominal_kw:
            gen_neta_kw = capacidad_nominal_kw
            motores_activos = num_motores
        else:
            motores_activos = math.ceil(objetivo_neto_kw / cap_unitaria_kw)
            motores_activos = max(1, min(motores_activos, num_motores))
            cap_activa = cap_unitaria_kw * motores_activos
            gen_neta_kw = min(objetivo_neto_kw, cap_activa)

            # Verificar piso del 60 %
            piso_kw = _MIN_CARGA_PCT * cap_unitaria_kw * motores_activos
            if gen_neta_kw < piso_kw:
                motores_activos -= 1
                if motores_activos == 0:
                    gen_neta_kw = 0.0
                else:
                    cap_activa = cap_unitaria_kw * motores_activos
                    gen_neta_kw = min(objetivo_neto_kw, cap_activa)
                    piso_kw = _MIN_CARGA_PCT * cap_unitaria_kw * motores_activos
                    if gen_neta_kw < piso_kw:
                        gen_neta_kw = 0.0
                        motores_activos = 0

        # ── Paso 2: respetar límite de horas mensuales por motor ────────────
        if motores_activos > 0:
            # Usar los primeros `motores_activos` motores que aún tengan horas
            motores_disponibles = [
                i for i in range(num_motores) if horas_motor[i] < _LIMITE_HORAS_MES
            ]
            if not motores_disponibles:
                gen_neta_kw = 0.0
                motores_activos = 0
            else:
                motores_activos = min(motores_activos, len(motores_disponibles))
                for i in motores_disponibles[:motores_activos]:
                    horas_motor[i] += _INTERVALO_H

        # ── Paso 3: acumular ────────────────────────────────────────────────
        gen_neta_mes_kwh += gen_neta_kw * _INTERVALO_H
        curva.append({
            "ts": ts,
            "demanda_kw": demanda_kw,
            "gen_neta_kw": gen_neta_kw,
            "motores_activos": motores_activos,
        })

    # ── Cálculos finales ────────────────────────────────────────────────────
    gen_bruta_mes_kwh = (
        gen_neta_mes_kwh / (1.0 - autoconsumo_pct) if autoconsumo_pct < 1.0 else 0.0
    )

    horas_mes_motor = sum(horas_motor) / num_motores  # promedio entre motores
    cap_promedio_kw = (
        gen_bruta_mes_kwh / horas_mes_motor if horas_mes_motor > 0 else 0.0
    )

    consumo_gas_mes_gj = (
        (gen_bruta_mes_kwh * _KWH_A_GJ) / rendimiento_electrico
        if rendimiento_electrico > 0 else 0.0
    )
    costo_om_mes_mxn = gen_bruta_mes_kwh * costo_om_kwh

    cobertura_pct = (
        gen_neta_mes_kwh / consumo_cliente_mes_kwh
        if consumo_cliente_mes_kwh > 0 else 0.0
    )

    # Anualizar ×12
    kpis = {
        "gen_neta_anual_kwh":   gen_neta_mes_kwh * 12,
        "gen_bruta_anual_kwh":  gen_bruta_mes_kwh * 12,
        "cobertura_pct":        cobertura_pct,
        "consumo_gas_anual_gj": consumo_gas_mes_gj * 12,
        "costo_om_anual_mxn":   costo_om_mes_mxn * 12,
        "horas_anuales_motor":  horas_mes_motor * 12,
        "capacidad_promedio_kw": cap_promedio_kw,
        "consumo_cliente_mes_kwh": consumo_cliente_mes_kwh,
    }

    return {"kpis": kpis, "curva": curva}


def _resultado_vacio() -> dict[str, Any]:
    kpis = {k: 0.0 for k in (
        "gen_neta_anual_kwh", "gen_bruta_anual_kwh", "cobertura_pct",
        "consumo_gas_anual_gj", "costo_om_anual_mxn", "horas_anuales_motor",
        "capacidad_promedio_kw", "consumo_cliente_mes_kwh",
    )}
    return {"kpis": kpis, "curva": []}
