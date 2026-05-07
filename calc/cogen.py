# calc/cogen.py
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from models.cfe_invoice import CFEInvoice
from models.gas_invoice import GasInvoice
from models.cogen_result import CoGenMes, CoGenParams, CoGenResultado
from calc.periodo import mes_asociado, prorratear_cfe, prorratear_gas

# Factor de conversión: 1 kWh = 0.0036 GJ
_KWH_A_GJ = Decimal("0.0036")
_CENTAVO = Decimal("0.01")
_DIEZMILAVO = Decimal("0.0001")


def calcular_cogen(
    cfe_invoices: list[CFEInvoice],
    gas_invoices: list[GasInvoice],
    params: CoGenParams,
) -> CoGenResultado:
    """Calcula el EBITDA mensual emparejando facturas por mes asociado.

    Cada factura se asigna al mes calendario donde tenga más días facturados.
    Las facturas con periodo corto (< 25 días por defecto) se prorratean a 30 días equivalentes.
    Los meses sin par CFE-Gas se omiten con warning en logs.
    """
    # Indexar gas por mes asociado (no por periodo_inicio crudo)
    gas_por_mes: dict[tuple[int, int], GasInvoice] = {
        mes_asociado(g.periodo_inicio, g.periodo_fin): g
        for g in gas_invoices
    }

    meses: list[CoGenMes] = []

    for cfe_orig in sorted(cfe_invoices, key=lambda x: x.periodo_inicio):
        clave = mes_asociado(cfe_orig.periodo_inicio, cfe_orig.periodo_fin)
        gas_orig = gas_por_mes.get(clave)
        if gas_orig is None:
            print(f"WARNING: Sin factura de gas para {clave} "
                  f"(CFE: {cfe_orig.periodo_inicio}–{cfe_orig.periodo_fin})")
            continue

        # Prorrateo si el periodo es corto
        cfe, factor_cfe = prorratear_cfe(cfe_orig)
        gas, factor_gas = prorratear_gas(gas_orig)

        kwh_total = sum(p.consumo_kwh for p in cfe.periodos)
        if kwh_total == 0:
            continue

        costo_cfe = cfe.facturacion_periodo_mxn
        costo_prom_kwh = (costo_cfe / kwh_total).quantize(_CENTAVO, ROUND_HALF_UP)
        costo_unit_gj = gas.costo_unitario_total_gj

        kwh_cubiertos = (kwh_total * params.cobertura_electrica).quantize(_CENTAVO, ROUND_HALF_UP)
        gj_gas_cogen = (kwh_cubiertos * _KWH_A_GJ / params.rendimiento_electrico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        costo_gas_cogen = (gj_gas_cogen * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)
        ahorro_electricidad = (kwh_cubiertos * costo_prom_kwh).quantize(_CENTAVO, ROUND_HALF_UP)
        calor_recuperado = (gj_gas_cogen * params.rendimiento_termico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        ahorro_caldera = (calor_recuperado / params.eficiencia_caldera * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)
        ebitda = ahorro_electricidad + ahorro_caldera - costo_gas_cogen

        # Nota de prorrateo para trazabilidad
        prorrateado = factor_cfe is not None or factor_gas is not None
        nota = ""
        if factor_cfe is not None:
            dias_cfe = (cfe_orig.periodo_fin - cfe_orig.periodo_inicio).days
            nota += f"CFE {dias_cfe}→30 días (×{factor_cfe})"
        if factor_gas is not None:
            dias_gas = (gas_orig.periodo_fin - gas_orig.periodo_inicio).days
            if nota:
                nota += "; "
            nota += f"Gas {dias_gas}→30 días (×{factor_gas})"

        # periodo_inicio/fin del CoGenMes = mes calendario completo (para display correcto)
        mes_anio, mes_mes = clave
        ultimo_dia = calendar.monthrange(mes_anio, mes_mes)[1]

        meses.append(CoGenMes(
            periodo_inicio=date(mes_anio, mes_mes, 1),
            periodo_fin=date(mes_anio, mes_mes, ultimo_dia),
            kwh_total=kwh_total,
            costo_cfe_mxn=costo_cfe,
            costo_promedio_kwh=costo_prom_kwh,
            gj_consumido=gas.consumo_total_gj,
            costo_unitario_gj=costo_unit_gj,
            costo_gas_actual_mxn=gas.subtotal_mxn,
            kwh_cubiertos=kwh_cubiertos,
            gj_gas_cogen=gj_gas_cogen,
            costo_gas_cogen_mxn=costo_gas_cogen,
            ahorro_electricidad_mxn=ahorro_electricidad,
            calor_recuperado_gj=calor_recuperado,
            ahorro_caldera_mxn=ahorro_caldera,
            ebitda_mes_mxn=ebitda,
            prorrateado=prorrateado,
            nota_prorrateo=nota,
        ))

    def _sum(attr: str) -> Decimal:
        return sum(getattr(m, attr) for m in meses) if meses else Decimal("0")

    return CoGenResultado(
        params=params,
        meses=meses,
        kwh_total_anual=_sum("kwh_total"),
        kwh_cubiertos_anual=_sum("kwh_cubiertos"),
        gj_gas_cogen_anual=_sum("gj_gas_cogen"),
        costo_gas_cogen_anual_mxn=_sum("costo_gas_cogen_mxn"),
        ahorro_electricidad_anual_mxn=_sum("ahorro_electricidad_mxn"),
        ahorro_caldera_anual_mxn=_sum("ahorro_caldera_mxn"),
        ebitda_anual_mxn=_sum("ebitda_mes_mxn"),
    )
