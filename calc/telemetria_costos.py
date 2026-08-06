"""Cálculo de costo en pesos para telemetría (Fase 2 D3).

Precio unitario derivado de facturas CFE o PPA del cliente.
Sin desglose por horario tarifario (queda como mejora futura).
"""
from __future__ import annotations
from datetime import datetime, timezone


def obtener_precio_unitario_mxn_kwh(cliente_id: int, anio: int, mes: int) -> dict:
    """Determina el precio unitario a aplicar para (cliente, año, mes).

    Lógica:
    1. Buscar factura CFE del (cliente_id, anio, mes) exacto.
       Si existe: retornar subtotal_mxn / kwh_total, fuente="factura_mes_exacto".
    2. Si no: buscar la factura CFE más reciente disponible (hasta 12 meses atrás).
       Si existe: retornar su precio, fuente="factura_mes_anterior".
    3. Si no hay ninguna CFE: buscar factura PPA del mes exacto.
       Si existe: retornar precio_unitario_mxn_kwh directamente, fuente="factura_mes_exacto".
    4. Si no hay ninguna PPA: buscar la PPA más reciente.
       Si existe: fuente="factura_mes_anterior".
    5. Si no hay nada: retornar precio=None, fuente="sin_datos".

    Retorna:
        {
          "precio_mxn_kwh": float | None,
          "fuente": "factura_mes_exacto" | "factura_mes_anterior" | "promedio_12m" | "sin_datos",
          "mes_referencia": "AAAA-MM" | None,
        }
    """
    from storage.repository import (
        obtener_factura_cfe_cliente_mes,
        obtener_ultimas_facturas_cfe,
        obtener_factura_ppa_cliente_mes,
        obtener_ultimas_facturas_ppa,
    )

    # ── Intentar CFE mes exacto ────────────────────────────────────────────
    fac = obtener_factura_cfe_cliente_mes(cliente_id, anio, mes)
    if fac:
        precio, ref = _precio_de_factura_cfe(fac)
        if precio is not None:
            return {"precio_mxn_kwh": precio, "fuente": "factura_mes_exacto",
                    "mes_referencia": f"{anio}-{mes:02d}"}

    # ── Intentar CFE más reciente (últimas 12) ─────────────────────────────
    facturas_cfe = obtener_ultimas_facturas_cfe(cliente_id, n=12)
    if facturas_cfe:
        for f in facturas_cfe:
            precio, _ = _precio_de_factura_cfe(f)
            if precio is not None:
                ref_anio = f.get("anio") or anio
                ref_mes = f.get("mes") or mes
                return {"precio_mxn_kwh": precio, "fuente": "factura_mes_anterior",
                        "mes_referencia": f"{ref_anio}-{ref_mes:02d}"}

    # ── Intentar PPA mes exacto ────────────────────────────────────────────
    fac_ppa = obtener_factura_ppa_cliente_mes(cliente_id, anio, mes)
    if fac_ppa:
        precio = _precio_de_factura_ppa(fac_ppa)
        if precio is not None:
            return {"precio_mxn_kwh": precio, "fuente": "factura_mes_exacto",
                    "mes_referencia": f"{anio}-{mes:02d}"}

    # ── Intentar PPA más reciente ──────────────────────────────────────────
    facturas_ppa = obtener_ultimas_facturas_ppa(cliente_id, n=12)
    if facturas_ppa:
        for f in facturas_ppa:
            precio = _precio_de_factura_ppa(f)
            if precio is not None:
                ref_anio = f.get("anio") or anio
                ref_mes = f.get("mes") or mes
                return {"precio_mxn_kwh": precio, "fuente": "factura_mes_anterior",
                        "mes_referencia": f"{ref_anio}-{ref_mes:02d}"}

    return {"precio_mxn_kwh": None, "fuente": "sin_datos", "mes_referencia": None}


def _precio_de_factura_cfe(fac: dict) -> tuple[float | None, str | None]:
    """Extrae precio unitario de una fila de cfe_facturas con cfe_periodos embebidos."""
    try:
        subtotal = float(fac.get("subtotal_mxn") or 0)
        periodos = fac.get("cfe_periodos") or []
        kwh_total = sum(float(p.get("consumo_kwh") or 0) for p in periodos)
        if kwh_total > 0 and subtotal > 0:
            return round(subtotal / kwh_total, 4), None
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return None, None


def _precio_de_factura_ppa(fac: dict) -> float | None:
    """Extrae precio_unitario_mxn_kwh de una fila de facturas_electricidad_calificado."""
    try:
        val = fac.get("precio_unitario_mxn_kwh")
        if val is not None:
            return round(float(val), 4)
    except (TypeError, ValueError):
        pass
    return None


def calcular_costo_periodo(
    cliente_id: int,
    energia_kwh: float,
    desde_utc: datetime,
    hasta_utc: datetime,
) -> dict:
    """Wrapper que determina el mes principal y calcula el costo del periodo.

    El mes principal es el mes con más días en el rango [desde_utc, hasta_utc].
    Si el rango cae en un solo mes, ese es el mes principal.

    Retorna:
        {
          "costo_mxn": float | None,
          "precio_mxn_kwh": float | None,
          "fuente": str,
          "mes_referencia": str | None,
        }
    """
    anio, mes = _mes_principal(desde_utc, hasta_utc)
    info = obtener_precio_unitario_mxn_kwh(cliente_id, anio, mes)
    precio = info["precio_mxn_kwh"]
    costo = round(energia_kwh * precio, 2) if precio is not None else None
    return {
        "costo_mxn": costo,
        "precio_mxn_kwh": precio,
        "fuente": info["fuente"],
        "mes_referencia": info["mes_referencia"],
    }


def _mes_principal(desde: datetime, hasta: datetime) -> tuple[int, int]:
    """Retorna (anio, mes) del mes que abarca más días en el rango."""
    from collections import defaultdict
    conteo: dict[tuple[int, int], int] = defaultdict(int)
    cur = desde
    from datetime import timedelta
    while cur <= hasta:
        conteo[(cur.year, cur.month)] += 1
        cur += timedelta(hours=1)
    if not conteo:
        return hasta.year, hasta.month
    return max(conteo, key=lambda k: (conteo[k], k[0], k[1]))


def obtener_precio_unitario(
    cliente_id: int,
    anio: int,
    mes: int,
    historico_completo: dict | None = None,
) -> dict:
    """Retorna {precio_mxn_kwh, fuente, mes_referencia} para (cliente, año, mes).

    Si historico_completo es un dict con clave (anio, mes), retorna desde el
    cache sin consultar la BD (útil para evitar N+1 queries en series de meses).
    Si no, delega a obtener_precio_unitario_mxn_kwh().

    Retorna:
        {
          "precio_mxn_kwh": float | None,
          "fuente": str,
          "mes_referencia": str | None,
        }
    """
    if historico_completo is not None and (anio, mes) in historico_completo:
        return historico_completo[(anio, mes)]
    return obtener_precio_unitario_mxn_kwh(cliente_id, anio, mes)
