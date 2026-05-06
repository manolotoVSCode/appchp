# calc/cogen.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from models.cfe_invoice import CFEInvoice
from models.gas_invoice import GasInvoice
from models.cogen_result import CoGenMes, CoGenParams, CoGenResultado

# Factor de conversión: 1 kWh = 0.0036 GJ
_KWH_A_GJ = Decimal("0.0036")
_CENTAVO = Decimal("0.01")
_DIEZMILAVO = Decimal("0.0001")


def calcular_cogen(
    cfe_invoices: list[CFEInvoice],
    gas_invoices: list[GasInvoice],
    params: CoGenParams,
) -> CoGenResultado:
    """Calcula el EBITDA mensual de cogeneración emparejando facturas por (año, mes).

    Los meses sin par CFE-Gas se omiten silenciosamente.
    """
    # Indexar gas por (año, mes) de periodo_inicio
    gas_por_mes: dict[tuple[int, int], GasInvoice] = {
        (g.periodo_inicio.year, g.periodo_inicio.month): g
        for g in gas_invoices
    }

    meses: list[CoGenMes] = []

    for cfe in sorted(cfe_invoices, key=lambda x: x.periodo_inicio):
        clave = (cfe.periodo_inicio.year, cfe.periodo_inicio.month)
        gas = gas_por_mes.get(clave)
        if gas is None:
            continue

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

        meses.append(CoGenMes(
            periodo_inicio=cfe.periodo_inicio,
            periodo_fin=cfe.periodo_fin,
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
