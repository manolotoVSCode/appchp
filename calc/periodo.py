# calc/periodo.py
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from models.cfe_invoice import CFEInvoice
from models.gas_invoice import GasInvoice

UMBRAL_PRORRATEO_DIAS: int = 25
_DIAS_EQUIVALENTES = Decimal("30")
_DOS_DEC = Decimal("0.01")
_CUATRO_DEC = Decimal("0.0001")


def mes_asociado(periodo_inicio: date, periodo_fin: date) -> tuple[int, int]:
    """Devuelve (año, mes) del mes calendario con más días facturados.

    En empate exacto se asigna al mes posterior (mayor (año, mes)).
    """
    dias_por_mes: dict[tuple[int, int], int] = {}
    current = periodo_inicio
    while current < periodo_fin:
        key = (current.year, current.month)
        dias_por_mes[key] = dias_por_mes.get(key, 0) + 1
        current += timedelta(days=1)
    return max(dias_por_mes, key=lambda k: (dias_por_mes[k], k))


# Nota: demanda_kw (potencia instantánea) NO se prorratea — es un valor de pico registrado
# en el medidor, no un consumo acumulado. Solo se escalan kwh y cargos monetarios.
def prorratear_cfe(
    invoice: CFEInvoice,
    umbral_dias: int = UMBRAL_PRORRATEO_DIAS,
) -> tuple[CFEInvoice, Decimal | None]:
    """Escala consumo y costo de una CFEInvoice a 30 días equivalentes si el periodo es corto.

    Condición: (periodo_fin - periodo_inicio).days < umbral_dias (umbral exclusivo).
    Devuelve (invoice_normalizado, factor) donde factor es None si no aplica prorrateo.
    La instancia original no se modifica.
    """
    dias_reales = (invoice.periodo_fin - invoice.periodo_inicio).days
    if dias_reales >= umbral_dias:
        return invoice, None

    factor = (_DIAS_EQUIVALENTES / Decimal(dias_reales)).quantize(_CUATRO_DEC, ROUND_HALF_UP)

    nuevos_periodos = [
        replace(p, consumo_kwh=(p.consumo_kwh * factor).quantize(_DOS_DEC, ROUND_HALF_UP))
        for p in invoice.periodos
    ]
    nuevos_componentes = [
        replace(
            c,
            cargo_fijo_mxn=(c.cargo_fijo_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
            cargo_demanda_mxn=(c.cargo_demanda_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
            cargo_energia_mxn=(c.cargo_energia_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
            importe_mxn=(c.importe_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
        )
        for c in invoice.componentes_mem
    ]
    return replace(
        invoice,
        periodos=nuevos_periodos,
        componentes_mem=nuevos_componentes,
        subtotal_mxn=(invoice.subtotal_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
        cargo_factor_potencia_mxn=(invoice.cargo_factor_potencia_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
        facturacion_periodo_mxn=(invoice.facturacion_periodo_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
    ), factor


def prorratear_gas(
    invoice: GasInvoice,
    umbral_dias: int = UMBRAL_PRORRATEO_DIAS,
) -> tuple[GasInvoice, Decimal | None]:
    """Escala consumo y costo de una GasInvoice a 30 días equivalentes si el periodo es corto.

    costo_unitario_total_gj no se escala (es precio por unidad, no volumen total).
    Condición: (periodo_fin - periodo_inicio).days < umbral_dias (umbral exclusivo).
    Devuelve (invoice_normalizado, factor) donde factor es None si no aplica prorrateo.
    La instancia original no se modifica.
    """
    dias_reales = (invoice.periodo_fin - invoice.periodo_inicio).days
    if dias_reales >= umbral_dias:
        return invoice, None

    factor = (_DIAS_EQUIVALENTES / Decimal(dias_reales)).quantize(_CUATRO_DEC, ROUND_HALF_UP)

    return replace(
        invoice,
        consumo_total_gj=(invoice.consumo_total_gj * factor).quantize(_CUATRO_DEC, ROUND_HALF_UP),
        subtotal_mxn=(invoice.subtotal_mxn * factor).quantize(_DOS_DEC, ROUND_HALF_UP),
    ), factor
