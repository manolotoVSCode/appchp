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


def obtener_precio_unitario_por_contrato(contrato_id: int, anio: int, mes: int) -> dict:
    """Determina el precio unitario para (contrato, año, mes).

    Cascada restringida al contrato especificado:
    1. Factura CFE del contrato en (anio, mes) exacto.
    2. Factura CFE más reciente del contrato (hasta 12 meses atrás).
    3. Factura PPA del contrato en (anio, mes) exacto.
    4. Factura PPA más reciente del contrato.
    5. sin_datos.

    Retorna:
        {
          "precio_mxn_kwh": float | None,
          "fuente": "factura_mes_exacto" | "factura_mes_anterior" | "sin_datos",
          "mes_referencia": "AAAA-MM" | None,
        }
    """
    from storage.repository import (
        obtener_factura_cfe_contrato_mes,
        obtener_ultimas_facturas_cfe_contrato,
        obtener_factura_ppa_contrato_mes,
        obtener_ultimas_facturas_ppa_contrato,
    )

    fac = obtener_factura_cfe_contrato_mes(contrato_id, anio, mes)
    if fac:
        precio, _ = _precio_de_factura_cfe(fac)
        if precio is not None:
            return {"precio_mxn_kwh": precio, "fuente": "factura_mes_exacto",
                    "mes_referencia": f"{anio}-{mes:02d}"}

    facturas_cfe = obtener_ultimas_facturas_cfe_contrato(contrato_id, n=12)
    if facturas_cfe:
        for f in facturas_cfe:
            precio, _ = _precio_de_factura_cfe(f)
            if precio is not None:
                ref_anio = f.get("anio") or anio
                ref_mes = f.get("mes") or mes
                return {"precio_mxn_kwh": precio, "fuente": "factura_mes_anterior",
                        "mes_referencia": f"{ref_anio}-{ref_mes:02d}"}

    fac_ppa = obtener_factura_ppa_contrato_mes(contrato_id, anio, mes)
    if fac_ppa:
        precio = _precio_de_factura_ppa(fac_ppa)
        if precio is not None:
            return {"precio_mxn_kwh": precio, "fuente": "factura_mes_exacto",
                    "mes_referencia": f"{anio}-{mes:02d}"}

    facturas_ppa = obtener_ultimas_facturas_ppa_contrato(contrato_id, n=12)
    if facturas_ppa:
        for f in facturas_ppa:
            precio = _precio_de_factura_ppa(f)
            if precio is not None:
                ref_anio = f.get("anio") or anio
                ref_mes = f.get("mes") or mes
                return {"precio_mxn_kwh": precio, "fuente": "factura_mes_anterior",
                        "mes_referencia": f"{ref_anio}-{ref_mes:02d}"}

    return {"precio_mxn_kwh": None, "fuente": "sin_datos", "mes_referencia": None}


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
