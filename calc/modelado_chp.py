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
    consumo_anual_kwh: float,  # consumo real anual de facturas (para proyección)
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
    consumo_anual_kwh : consumo real anual del cliente (facturas) para proyección

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

    # ── Cálculos mensuales ──────────────────────────────────────────────────
    gen_neta_mes_kwh        = sum(p["gen_neta_kw"] * _INTERVALO_H for p in curva)
    gen_bruta_mes_kwh       = (
        gen_neta_mes_kwh / (1.0 - autoconsumo_pct) if autoconsumo_pct < 1.0 else 0.0
    )
    consumo_cliente_mes_kwh = sum(d["potencia_kw"] * _INTERVALO_H for d in datos)
    cobertura_pct = (
        gen_neta_mes_kwh / consumo_cliente_mes_kwh
        if consumo_cliente_mes_kwh > 0 else 0.0
    )

    intervalos_activos = sum(1 for p in curva if p["gen_neta_kw"] > 0)
    horas_mes_motor    = intervalos_activos * _INTERVALO_H  # h reales de operación

    if intervalos_activos > 0 and autoconsumo_pct < 1.0:
        gen_bruta_activa_kwh = sum(
            p["gen_neta_kw"] / (1.0 - autoconsumo_pct) * _INTERVALO_H
            for p in curva if p["gen_neta_kw"] > 0
        )
        cap_promedio_kw = min(gen_bruta_activa_kwh / horas_mes_motor, capacidad_nominal_kw)
    else:
        cap_promedio_kw = 0.0

    # ── Proyección anual por cobertura sobre consumo real de facturas ───────
    gen_neta_anual_kwh  = consumo_anual_kwh * cobertura_pct
    gen_bruta_anual_kwh = (
        gen_neta_anual_kwh / (1.0 - autoconsumo_pct) if autoconsumo_pct < 1.0 else 0.0
    )
    horas_anuales_motor  = horas_mes_motor * 12
    consumo_gas_anual_gj = (
        (gen_bruta_anual_kwh * _KWH_A_GJ) / rendimiento_electrico
        if rendimiento_electrico > 0 else 0.0
    )
    costo_om_anual_mxn = gen_bruta_anual_kwh * costo_om_kwh

    kpis = {
        "gen_neta_anual_kwh":    gen_neta_anual_kwh,
        "gen_bruta_anual_kwh":   gen_bruta_anual_kwh,
        "cobertura_pct":         cobertura_pct,
        "consumo_gas_anual_gj":  consumo_gas_anual_gj,
        "costo_om_anual_mxn":    costo_om_anual_mxn,
        "horas_anuales_motor":   horas_anuales_motor,
        "capacidad_promedio_kw": cap_promedio_kw,
        "consumo_cliente_mes_kwh": consumo_cliente_mes_kwh,
    }

    return {"kpis": kpis, "curva": curva}


def calcular_cogen_desde_modelado(
    kpis_modelado: dict,
    rendimiento_electrico: float,
    rendimiento_termico: float,
    eficiencia_caldera: float,
    cfe_invoices: list,
    gas_invoices: list,
    tipo_cambio: Any,
    factor_emision_elec: Any = None,
    factor_emision_gas: Any = None,
    inversion_usd_override: float | None = None,
    deduccion_fiscal: bool = False,
    anios_deduccion: int = 1,
) -> Any:
    """Adapta los KPIs del modelado CHP como inputs del motor de cogeneración.

    La cobertura eléctrica usada proviene de kpis_modelado["cobertura_pct"],
    que es el resultado de la simulación CHP intervalo a intervalo.
    El resto del cálculo (ahorro eléctrico por horario, ahorro caldera,
    costo gas adicional, O&M, EBITDA, flujo 15 años) es idéntico a
    calcular_cogen() del dashboard estándar.

    No modifica calc/cogen.py ni sus interfaces.

    Parámetros opcionales:
    - inversion_usd_override: si se proporciona, sobreescribe r.inversion_usd
      y r.inversion_mxn tras el cálculo (precio USD/kW del usuario).
    - deduccion_fiscal: si True aplica ISR 30% sobre inversion_mxn repartido
      en anios_deduccion, sobreescribiendo r.beneficio_fiscal_anio_1_mxn.
    - anios_deduccion: número de años (1-5) en que se reparte la deducción.
    """
    from decimal import Decimal as _D, ROUND_HALF_UP
    from calc.cogen import calcular_cogen
    from models.cogen_result import CoGenParams

    params = CoGenParams(
        cobertura_electrica=_D(str(kpis_modelado["cobertura_pct"])),
        rendimiento_electrico=_D(str(rendimiento_electrico)),
        rendimiento_termico=_D(str(rendimiento_termico)),
        eficiencia_caldera=_D(str(eficiencia_caldera)),
    )
    r = calcular_cogen(
        cfe_invoices=cfe_invoices,
        gas_invoices=gas_invoices,
        params=params,
        tipo_cambio=_D(str(tipo_cambio)),
        factor_emision_elec=_D(str(factor_emision_elec)) if factor_emision_elec is not None else None,
        factor_emision_gas=_D(str(factor_emision_gas)) if factor_emision_gas is not None else None,
    )

    # energia_limpia_pct: si calcular_cogen() no lo calculó, intentar desde
    # kpis del modelado y datos de CELs disponibles en r
    _cels_mwh = getattr(r, "cels_mwh_anual", None)
    if r.energia_limpia_pct is None and _cels_mwh is not None:
        kwh_total = kpis_modelado.get("consumo_cliente_mes_kwh", 0)
        kwh_anual = float(kwh_total) * 12
        if kwh_anual > 0:
            r.energia_limpia_pct = (
                _D(str(_cels_mwh)) * _D("1000")
                / _D(str(kwh_anual)) * _D("100")
            ).quantize(_D("0.01"), rounding=ROUND_HALF_UP)

    # Sobreescribir inversión si el usuario proporcionó precio USD/kW manual
    if inversion_usd_override is not None and inversion_usd_override > 0:
        r.inversion_usd = _D(str(round(inversion_usd_override, 2)))
        r.inversion_mxn = (r.inversion_usd * _D(str(tipo_cambio))).quantize(
            _D("0.01"), rounding=ROUND_HALF_UP
        )

    # Aplicar deducción fiscal ISR 30% repartida en anios_deduccion
    _anos = max(1, int(anios_deduccion))
    if deduccion_fiscal and r.inversion_mxn is not None and r.inversion_mxn > 0:
        beneficio = (r.inversion_mxn * _D("0.30") / _D(str(_anos))).quantize(
            _D("0.01"), rounding=ROUND_HALF_UP
        )
        r.beneficio_fiscal_anio_1_mxn    = beneficio
        r.flujo_anio_1_con_beneficio_mxn = (r.ebitda_anual_mxn + beneficio).quantize(
            _D("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        r.beneficio_fiscal_anio_1_mxn    = None
        r.flujo_anio_1_con_beneficio_mxn = None

    return r


def _resultado_vacio() -> dict[str, Any]:
    kpis = {k: 0.0 for k in (
        "gen_neta_anual_kwh", "gen_bruta_anual_kwh", "cobertura_pct",
        "consumo_gas_anual_gj", "costo_om_anual_mxn", "horas_anuales_motor",
        "capacidad_promedio_kw", "consumo_cliente_mes_kwh",
    )}
    return {"kpis": kpis, "curva": []}
