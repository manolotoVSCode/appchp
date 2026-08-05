"""Cálculo de KPIs de paneles para telemetría (Fase 2 D7-A).

Funciones puras: reciben datos ya fetcheados, no acceden a Supabase.
"""
from __future__ import annotations

from datetime import datetime


def calcular_kpis_energeticos(
    mediciones: list[dict],
    potencia_nominal_kw: float | None,
) -> dict:
    """Calcula KPIs energéticos sobre la serie temporal del nodo.

    mediciones: lista de dicts {"ts": str ISO, "kw": float, "fp": float}
    Retorna dict con: energia_kwh, demanda_pico_kw, demanda_promedio_kw,
                      factor_potencia_promedio, indice_utilizacion_pct
    """
    if not mediciones:
        return {
            "energia_kwh": 0.0,
            "demanda_pico_kw": 0.0,
            "demanda_promedio_kw": 0.0,
            "factor_potencia_promedio": None,
            "indice_utilizacion_pct": None,
        }

    kw_vals = [m["kw"] for m in mediciones]
    fp_vals = [m.get("fp", 0.0) for m in mediciones]

    # Energía: integración trapezoidal
    energia = 0.0
    for i in range(1, len(mediciones)):
        try:
            t0 = datetime.fromisoformat(mediciones[i - 1]["ts"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(mediciones[i]["ts"].replace("Z", "+00:00"))
            dt_h = (t1 - t0).total_seconds() / 3600.0
            energia += (kw_vals[i - 1] + kw_vals[i]) / 2.0 * dt_h
        except Exception:
            pass

    demanda_pico = max(kw_vals)
    demanda_prom = sum(kw_vals) / len(kw_vals)

    # FP ponderado por potencia activa
    total_kw = sum(kw_vals)
    fp_pond: float | None = None
    if total_kw > 0:
        fp_pond = sum(fp_vals[i] * kw_vals[i] for i in range(len(mediciones))) / total_kw

    # Índice de utilización: pico / nominal
    idx_util: float | None = None
    if potencia_nominal_kw and potencia_nominal_kw > 0:
        idx_util = round(demanda_pico / potencia_nominal_kw * 100, 2)

    return {
        "energia_kwh": round(energia, 3),
        "demanda_pico_kw": round(demanda_pico, 3),
        "demanda_promedio_kw": round(demanda_prom, 3),
        "factor_potencia_promedio": round(fp_pond, 4) if fp_pond is not None else None,
        "indice_utilizacion_pct": idx_util,
    }


def calcular_kpis_economicos(
    energia_kwh: float,
    precio_mxn_kwh: float | None,
    costo_cliente_factura_total: float | None,
    baseline_kwh: float | None,
) -> dict:
    """Calcula KPIs económicos del nodo.

    Retorna dict con: costo_total_mxn, costo_unitario_mxn_kwh,
                      pct_sobre_factura, ahorro_potencial_mxn
    """
    if precio_mxn_kwh is None:
        return {
            "costo_total_mxn": None,
            "costo_unitario_mxn_kwh": None,
            "pct_sobre_factura": None,
            "ahorro_potencial_mxn": None,
        }

    costo_total = round(energia_kwh * precio_mxn_kwh, 2)

    pct_factura: float | None = None
    if costo_cliente_factura_total and costo_cliente_factura_total > 0:
        pct_factura = round(costo_total / costo_cliente_factura_total * 100, 2)

    ahorro: float | None = None
    if baseline_kwh is not None:
        ahorro = round((baseline_kwh - energia_kwh) * precio_mxn_kwh, 2)

    return {
        "costo_total_mxn": costo_total,
        "costo_unitario_mxn_kwh": precio_mxn_kwh,
        "pct_sobre_factura": pct_factura,
        "ahorro_potencial_mxn": ahorro,
    }


def calcular_kpis_produccion(
    energia_kwh: float,
    costo_total_mxn: float | None,
    m2_producidos_atribuidos: float,
) -> dict:
    """Calcula KPIs de producción del nodo.

    Retorna dict con: consumo_especifico_kwh_m2, costo_especifico_mxn_m2,
                      pct_costo_especifico, m2_producidos
    """
    if m2_producidos_atribuidos <= 0:
        return {
            "consumo_especifico_kwh_m2": None,
            "costo_especifico_mxn_m2": None,
            "pct_costo_especifico": None,
            "m2_producidos": 0.0,
        }

    consumo_esp = round(energia_kwh / m2_producidos_atribuidos, 4)
    costo_esp: float | None = None
    pct_costo_esp: float | None = None
    if costo_total_mxn is not None and costo_total_mxn > 0:
        costo_esp = round(costo_total_mxn / m2_producidos_atribuidos, 4)
        pct_costo_esp = round(costo_esp / costo_total_mxn * 100, 2)

    return {
        "consumo_especifico_kwh_m2": consumo_esp,
        "costo_especifico_mxn_m2": costo_esp,
        "pct_costo_especifico": pct_costo_esp,
        "m2_producidos": round(m2_producidos_atribuidos, 2),
    }


def atribuir_produccion_a_nodo(
    m2_totales_planta: float,
    energia_nodo_kwh: float,
    energia_total_planta_kwh: float,
) -> float:
    """Atribuye m² de producción al nodo proporcionalmente a su consumo eléctrico."""
    if energia_total_planta_kwh <= 0:
        return 0.0
    return m2_totales_planta * (energia_nodo_kwh / energia_total_planta_kwh)


def calcular_baseline_movil(mediciones_historicas: list[dict]) -> float | None:
    """Calcula la energía total del periodo histórico como baseline provisional.

    mediciones_historicas: lista de dicts {"ts": str ISO, "kw": float}
    Retorna kWh integrados, o None si no hay datos.
    NOTA: fórmula final (promedio diario, p90, etc.) por definir por el usuario.
    """
    if not mediciones_historicas:
        return None

    kw_vals = [m.get("kw", 0.0) for m in mediciones_historicas]
    energia = 0.0
    for i in range(1, len(mediciones_historicas)):
        try:
            t0 = datetime.fromisoformat(
                mediciones_historicas[i - 1]["ts"].replace("Z", "+00:00")
            )
            t1 = datetime.fromisoformat(
                mediciones_historicas[i]["ts"].replace("Z", "+00:00")
            )
            dt_h = (t1 - t0).total_seconds() / 3600.0
            energia += (kw_vals[i - 1] + kw_vals[i]) / 2.0 * dt_h
        except Exception:
            pass

    return round(energia, 3) if energia > 0 else None


def generar_sparkline(
    mediciones: list[dict],
    n_puntos: int,
    tipo: str = "energia",
) -> list[float]:
    """Reduce mediciones a n_puntos agrupando por bucket temporal.

    mediciones: lista de dicts {"ts": str ISO, "kw": float, "fp": float (opcional)}
    tipo='energia':         kWh acumulados por bucket (integral trapezoidal).
    tipo='potencia':        promedio de kw por bucket.
    tipo='factor_potencia': promedio ponderado de fp por kw, por bucket.
    Retorna lista de n_puntos floats.
    """
    if not mediciones or n_puntos <= 0:
        return [0.0] * max(n_puntos, 0)

    try:
        t_inicio = datetime.fromisoformat(mediciones[0]["ts"].replace("Z", "+00:00"))
        t_fin = datetime.fromisoformat(mediciones[-1]["ts"].replace("Z", "+00:00"))
    except Exception:
        return [0.0] * n_puntos

    duracion = (t_fin - t_inicio).total_seconds()
    if duracion <= 0:
        return [0.0] * n_puntos

    bucket_size = duracion / n_puntos

    if tipo == "energia":
        buckets = [0.0] * n_puntos
        for i in range(1, len(mediciones)):
            try:
                t0 = datetime.fromisoformat(mediciones[i - 1]["ts"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(mediciones[i]["ts"].replace("Z", "+00:00"))
                dt_h = (t1 - t0).total_seconds() / 3600.0
                kwh = (mediciones[i - 1]["kw"] + mediciones[i]["kw"]) / 2.0 * dt_h
                t_mid = t0 + (t1 - t0) / 2
                idx = min(int((t_mid - t_inicio).total_seconds() / bucket_size), n_puntos - 1)
                buckets[idx] += kwh
            except Exception:
                pass
        return [round(b, 3) for b in buckets]

    elif tipo == "potencia":
        # Promedio de kw por bucket
        sumas = [0.0] * n_puntos
        conteos = [0] * n_puntos
        for m in mediciones:
            try:
                t = datetime.fromisoformat(m["ts"].replace("Z", "+00:00"))
                idx = min(int((t - t_inicio).total_seconds() / bucket_size), n_puntos - 1)
                sumas[idx] += m["kw"]
                conteos[idx] += 1
            except Exception:
                pass
        return [round(sumas[i] / conteos[i], 3) if conteos[i] > 0 else 0.0 for i in range(n_puntos)]

    else:  # factor_potencia: promedio ponderado por kw
        fp_peso = [0.0] * n_puntos
        kw_peso = [0.0] * n_puntos
        for m in mediciones:
            try:
                t = datetime.fromisoformat(m["ts"].replace("Z", "+00:00"))
                idx = min(int((t - t_inicio).total_seconds() / bucket_size), n_puntos - 1)
                kw = m.get("kw", 0.0)
                fp = m.get("fp", 0.0)
                fp_peso[idx] += fp * kw
                kw_peso[idx] += kw
            except Exception:
                pass
        return [
            round(fp_peso[i] / kw_peso[i], 4) if kw_peso[i] > 0 else 0.0
            for i in range(n_puntos)
        ]


def determinar_periodo_anterior(
    rango: str,
    ahora: datetime,
) -> tuple[datetime, datetime, str]:
    """Calcula el periodo anterior equivalente al rango, desplazado 30 días atrás.

    - 24h: hasta = ahora - 30d; desde = hasta - 24h
    - 7d:  hasta = ahora - 30d; desde = hasta - 7d
    - 30d: hasta = ahora - 30d; desde = hasta - 30d

    Retorna (desde_ant, hasta_ant, etiqueta).
    """
    from datetime import timedelta

    hasta_ant = ahora - timedelta(days=30)
    if rango == "7d":
        desde_ant = hasta_ant - timedelta(days=7)
        etiqueta = "misma semana 30 días antes"
    elif rango == "30d":
        desde_ant = hasta_ant - timedelta(days=30)
        etiqueta = "mismo mes 30 días antes"
    else:  # 24h (default)
        desde_ant = hasta_ant - timedelta(hours=24)
        etiqueta = "mismo momento 30 días antes"

    return desde_ant, hasta_ant, etiqueta
