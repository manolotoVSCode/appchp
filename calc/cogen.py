# calc/cogen.py
from __future__ import annotations

import calendar
import logging
import math
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

from models.cfe_invoice import CFEInvoice
from models.factura_calificado import FacturaCalificado
from models.gas_invoice import GasInvoice
from models.cogen_result import CoGenMes, CoGenParams, CoGenResultado
from calc.periodo import mes_asociado, prorratear_cfe, prorratear_gas

# Factor de conversión: 1 kWh = 0.0036 GJ
_KWH_A_GJ = Decimal("0.0036")
# Corrección PCI→PCS: el gas se comercializa en PCS pero la termodinámica usa PCI
_FACTOR_PCI_A_PCS = Decimal("1.11")
# O&M estimado: 0.3 MXN fijos por kWh cubierto (costo de operación y mantenimiento)
_FACTOR_OM = Decimal("0.3")
# Dimensionamiento de motor: costo USD/kW instalado
_USD_POR_KW = Decimal("1400")
# Tipo de cambio MXN/USD por defecto (se sobreescribe con valor de BD)
_TC_DEFAULT = Decimal("17.50")
# Periodos horarios que deben estar presentes para calcular capacidad nominal
_PERIODOS_COMPLETOS = frozenset({"base", "intermedio", "punta"})
# Factor de carga para derivar demanda efectiva post-cogeneración
_FACTOR_DEMANDA = Decimal("0.57")

_CENTAVO = Decimal("0.01")
_DIEZMILAVO = Decimal("0.0001")
# Tasa ISR para cálculo de beneficio fiscal
_TASA_ISR = Decimal("0.30")


def _capacidad_nominal_kw(cfe_invoices: list[CFEInvoice]) -> Decimal | None:
    """max(kWh_total_mes / (días × 24 h)) sobre facturas con los tres horarios completos."""
    maximos: list[Decimal] = []
    for cfe in cfe_invoices:
        nombres = {p.periodo for p in cfe.periodos}
        if not _PERIODOS_COMPLETOS.issubset(nombres):
            continue
        kwh = sum(p.consumo_kwh for p in cfe.periodos)
        dias = (cfe.periodo_fin - cfe.periodo_inicio).days
        if kwh > 0 and dias > 0:
            horas = Decimal(dias * 24)
            maximos.append(kwh / horas)
    if not maximos:
        return None
    return Decimal(math.ceil(max(maximos)))


def calcular_payback_decimal(
    inversion_mxn: Decimal,
    flujo_anio_1: Decimal,
    ahorro_neto_anual: Decimal,
    horizonte: int = 15,
) -> Decimal | None:
    """Payback con interpolación lineal entre años, retorna Decimal con 2 decimales.

    - Decimal: años de payback (puede ser fraccionario, p.ej. 2.05).
    - None: no se alcanza en el horizonte dado, o inversión/ahorro inválidos.

    flujo_anio_1 puede incluir beneficio fiscal (año 1 diferente al resto).
    ahorro_neto_anual se usa para años 2+.
    """
    if inversion_mxn <= 0:
        return Decimal("0")
    if flujo_anio_1 <= 0 and ahorro_neto_anual <= 0:
        return None

    acumulado = -inversion_mxn

    for anio in range(1, horizonte + 1):
        flujo_anio = flujo_anio_1 if anio == 1 else ahorro_neto_anual
        if flujo_anio <= 0:
            # Año sin flujo positivo no puede cruzar
            continue
        prev_acumulado = acumulado
        acumulado += flujo_anio

        if acumulado >= 0 and prev_acumulado < 0:
            payback = Decimal(anio - 1) + abs(prev_acumulado) / flujo_anio
            return payback.quantize(Decimal("0.01"))

    return None


def calcular_flujo_acumulado(
    inversion_mxn: Decimal,
    ahorro_neto_anual: Decimal,
    horizonte: int = 15,
) -> list[Decimal]:
    """Flujo de caja acumulado: año 0 = -inversión; año N = año N-1 + ahorro."""
    flujo = [-inversion_mxn]
    for _ in range(horizonte):
        flujo.append(flujo[-1] + ahorro_neto_anual)
    return flujo


def calcular_cogen(
    cfe_invoices: list[CFEInvoice],
    gas_invoices: list[GasInvoice],
    params: CoGenParams,
    tipo_cambio: Decimal = _TC_DEFAULT,
    factor_emision_elec: Decimal | None = None,
    factor_emision_gas: Decimal | None = None,
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
            logger.warning(
                "Sin factura de gas para %s (CFE: %s–%s)",
                clave, cfe_orig.periodo_inicio, cfe_orig.periodo_fin,
            )
            continue

        # Prorrateo si el periodo es corto
        cfe, factor_cfe = prorratear_cfe(cfe_orig)
        gas, factor_gas = prorratear_gas(gas_orig)

        kwh_total = sum(p.consumo_kwh for p in cfe.periodos)
        if kwh_total == 0:
            continue

        costo_cfe = cfe.subtotal_mxn
        costo_prom_kwh = (costo_cfe / kwh_total).quantize(_CENTAVO, ROUND_HALF_UP)
        costo_unit_gj = gas.costo_unitario_total_gj

        kwh_cubiertos = (kwh_total * params.cobertura_electrica).quantize(_CENTAVO, ROUND_HALF_UP)
        gj_gas_cogen = (kwh_cubiertos * _KWH_A_GJ * _FACTOR_PCI_A_PCS / params.rendimiento_electrico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        costo_gas_cogen = (gj_gas_cogen * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)

        # Metodología GDMTH 3 componentes:
        # Paso 1 — Cobertura greedy: se cubre primero el periodo más caro (punta)
        sorted_periodos = sorted(cfe.periodos, key=lambda p: p.costo_unitario_kwh, reverse=True)
        remaining = kwh_cubiertos
        kwh_por_periodo: dict[str, Decimal] = {}
        for p in sorted_periodos:
            covered = min(remaining, p.consumo_kwh)
            kwh_por_periodo[p.periodo] = covered
            remaining -= covered
            if remaining <= Decimal("0"):
                break
        # Periodos no alcanzados reciben cero
        for p in cfe.periodos:
            kwh_por_periodo.setdefault(p.periodo, Decimal("0"))

        # Paso 2 — Ahorro Energía: suma por periodo de kWh_cubierto × costo_unitario
        ahorro_energia = sum(
            (kwh_por_periodo[p.periodo] * p.costo_unitario_kwh for p in cfe.periodos),
            Decimal("0"),
        ).quantize(_CENTAVO, ROUND_HALF_UP)

        # Paso 3 — Ahorro Capacidad y Distribución (metodología GDMTH con redondeo ceiling)
        # CFE GDMTH factura demanda derivando kW como ceil(kWh / horas / 0.57).
        # Los precios unitarios se obtienen desde cargo_demanda_mxn del componente MEM.
        # Asunción conservadora: kw_max NO cambia con cogeneración (paradas mensuales).
        kw_max = cfe_orig.kw_max
        kw_punta = next(
            (p.demanda_kw for p in cfe_orig.periodos if p.periodo == "punta"),
            kw_max,  # fallback a kw_max si no existe periodo punta
        )

        # Datos originales (sin prorrateo) para derivar demanda facturada
        kwh_total_orig = sum(p.consumo_kwh for p in cfe_orig.periodos)
        dias_orig = (cfe_orig.periodo_fin - cfe_orig.periodo_inicio).days

        nombres_mem = [c.nombre for c in cfe_orig.componentes_mem]
        comp_cap  = next((c for c in cfe_orig.componentes_mem if "capacidad" in c.nombre.lower()), None)
        comp_dist = next((c for c in cfe_orig.componentes_mem if "distribu"  in c.nombre.lower()), None)

        if dias_orig > 0:
            # Demanda promedio actual → ceiling de ceil(D_avg / 0.57)
            d_avg_actual = kwh_total_orig / (Decimal("24") * dias_orig)
            d_ceil_actual = Decimal(math.ceil(d_avg_actual / _FACTOR_DEMANDA))

            # kW facturado = min(kW real del periodo, demanda derivada con ceiling)
            kw_facturado_capacidad    = min(kw_punta, d_ceil_actual)
            kw_facturado_distribucion = min(kw_max,   d_ceil_actual)

            # Precio unitario desde cargo_demanda_mxn (usa cfe_orig, no prorratado)
            if comp_cap is None:
                if nombres_mem and kw_punta > 0:
                    logger.warning("Sin componente Capacidad para %s. Componentes: %s", clave, nombres_mem)
                precio_cap = Decimal("0")
            elif kw_facturado_capacidad <= 0:
                precio_cap = Decimal("0")
            else:
                precio_cap = (comp_cap.cargo_demanda_mxn / kw_facturado_capacidad).quantize(_DIEZMILAVO, ROUND_HALF_UP)

            if comp_dist is None:
                if nombres_mem and kw_max > 0:
                    logger.warning("Sin componente Distribución para %s. Componentes: %s", clave, nombres_mem)
                precio_dist = Decimal("0")
            elif kw_facturado_distribucion <= 0:
                precio_dist = Decimal("0")
            else:
                precio_dist = (comp_dist.cargo_demanda_mxn / kw_facturado_distribucion).quantize(_DIEZMILAVO, ROUND_HALF_UP)

            # Demanda post-cogeneración con ceiling
            kwh_post_cogen = kwh_total_orig - (kwh_total_orig * params.cobertura_electrica)
            d_avg_post = kwh_post_cogen / (Decimal("24") * dias_orig)
            d_ceil_post = Decimal(math.ceil(d_avg_post / _FACTOR_DEMANDA))

            kw_efectiva_capacidad_post    = min(kw_facturado_capacidad,    d_ceil_post)
            kw_efectiva_distribucion_post = min(kw_facturado_distribucion, d_ceil_post)

            reduccion_cap  = max(kw_facturado_capacidad    - kw_efectiva_capacidad_post,    Decimal("0"))
            reduccion_dist = max(kw_facturado_distribucion - kw_efectiva_distribucion_post, Decimal("0"))
        else:
            kw_facturado_capacidad        = Decimal("0")
            kw_facturado_distribucion     = Decimal("0")
            kw_efectiva_capacidad_post    = Decimal("0")
            kw_efectiva_distribucion_post = Decimal("0")
            precio_cap                    = Decimal("0")
            precio_dist                   = Decimal("0")
            reduccion_cap                 = Decimal("0")
            reduccion_dist                = Decimal("0")

        ahorro_capacidad    = (precio_cap  * reduccion_cap ).quantize(_CENTAVO, ROUND_HALF_UP)
        ahorro_distribucion = (precio_dist * reduccion_dist).quantize(_CENTAVO, ROUND_HALF_UP)

        # Paso 4 — Ahorro Otros Servicios: Transmisión + CENACE + SCnMEM
        # Estos cargos son proporcionales al consumo (kWh), por lo que si la cogeneración
        # reduce el consumo en X%, estos cargos se reducen en X%.
        # Se usa importe_mxn (cargo total del período) de cada componente MEM.
        comp_trans  = next((c for c in cfe_orig.componentes_mem if c.nombre == "Transmisión"), None)
        comp_cenace = next((c for c in cfe_orig.componentes_mem if c.nombre == "CENACE"), None)
        comp_scnmem = next((c for c in cfe_orig.componentes_mem if c.nombre == "SCnMEM"), None)

        cargo_trans_mxn  = comp_trans.importe_mxn  if comp_trans  else Decimal("0")
        cargo_cenace_mxn = comp_cenace.importe_mxn if comp_cenace else Decimal("0")
        cargo_scnmem_mxn = comp_scnmem.importe_mxn if comp_scnmem else Decimal("0")
        cargo_otros_total = cargo_trans_mxn + cargo_cenace_mxn + cargo_scnmem_mxn

        if kwh_total_orig > 0 and cargo_otros_total > 0:
            precio_otros_mxn_kwh = (cargo_otros_total / kwh_total_orig).quantize(_DIEZMILAVO, ROUND_HALF_UP)
            ahorro_otros_servicios = (kwh_cubiertos * precio_otros_mxn_kwh).quantize(_CENTAVO, ROUND_HALF_UP)
        else:
            precio_otros_mxn_kwh = Decimal("0")
            ahorro_otros_servicios = Decimal("0")

        # Paso 5 — Ahorro eléctrico total (4 componentes)
        ahorro_electricidad = ahorro_energia + ahorro_capacidad + ahorro_distribucion + ahorro_otros_servicios

        # Paso 6 — kWh por periodo (para campos informativos)
        kwh_punta_cubierto = kwh_por_periodo.get("punta", Decimal("0"))
        kwh_intermedia_cubierto = kwh_por_periodo.get("intermedio", Decimal("0"))
        kwh_base_cubierto = kwh_por_periodo.get("base", Decimal("0"))

        calor_recuperado = (gj_gas_cogen * params.rendimiento_termico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        ahorro_caldera = (calor_recuperado / params.eficiencia_caldera * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)
        gasto_om = (kwh_cubiertos * _FACTOR_OM).quantize(_CENTAVO, ROUND_HALF_UP)
        ebitda = ahorro_electricidad + ahorro_caldera - costo_gas_cogen - gasto_om

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
            kwh_punta_cubierto=kwh_punta_cubierto,
            kwh_intermedia_cubierto=kwh_intermedia_cubierto,
            kwh_base_cubierto=kwh_base_cubierto,
            ahorro_energia_mes_mxn=ahorro_energia,
            ahorro_capacidad_mes_mxn=ahorro_capacidad,
            ahorro_distribucion_mes_mxn=ahorro_distribucion,
            cargo_otros_total_mxn=cargo_otros_total,
            precio_otros_mxn_kwh=precio_otros_mxn_kwh,
            ahorro_otros_servicios_mes_mxn=ahorro_otros_servicios,
            gj_gas_cogen=gj_gas_cogen,
            costo_gas_cogen_mxn=costo_gas_cogen,
            ahorro_electricidad_mxn=ahorro_electricidad,
            calor_recuperado_gj=calor_recuperado,
            ahorro_caldera_mxn=ahorro_caldera,
            ebitda_mes_mxn=ebitda,
            gasto_om_mes_mxn=gasto_om,
            kwh_punta_total=next((p.consumo_kwh for p in cfe.periodos if p.periodo == "punta"), Decimal("0")),
            # Los valores de p.periodo son: "punta", "intermedio", "base" (ver schema.sql cfe_periodos)
            kwh_intermedia_total=next((p.consumo_kwh for p in cfe.periodos if p.periodo == "intermedio"), Decimal("0")),
            kwh_base_total=next((p.consumo_kwh for p in cfe.periodos if p.periodo == "base"), Decimal("0")),
            cu_punta_kwh=next((p.costo_unitario_kwh for p in cfe.periodos if p.periodo == "punta"), Decimal("0")),
            cu_intermedia_kwh=next((p.costo_unitario_kwh for p in cfe.periodos if p.periodo == "intermedio"), Decimal("0")),
            cu_base_kwh=next((p.costo_unitario_kwh for p in cfe.periodos if p.periodo == "base"), Decimal("0")),
            kw_max=kw_max,
            kw_punta_orig=kw_punta,
            dias_facturados=dias_orig,
            kwh_total_orig=kwh_total_orig,
            precio_capacidad_kw=precio_cap,
            precio_distribucion_kw=precio_dist,
            kw_facturado_capacidad=kw_facturado_capacidad,
            kw_facturado_distribucion=kw_facturado_distribucion,
            kw_efectiva_capacidad_post=kw_efectiva_capacidad_post,
            kw_efectiva_distribucion_post=kw_efectiva_distribucion_post,
            prorrateado=prorrateado,
            nota_prorrateo=nota,
        ))

    def _sum(attr: str) -> Decimal:
        return sum(getattr(m, attr) for m in meses) if meses else Decimal("0")

    capacidad_kw = _capacidad_nominal_kw(cfe_invoices)
    if capacidad_kw is not None and capacidad_kw > 0:
        inv_usd = (capacidad_kw * _USD_POR_KW).quantize(_CENTAVO, ROUND_HALF_UP)
        inv_mxn = (inv_usd * tipo_cambio).quantize(_CENTAVO, ROUND_HALF_UP)
    else:
        inv_usd = inv_mxn = None

    # ── Huella de carbono ────────────────────────────────────────────────────
    co2_elec_actual = co2_gas_actual = co2_actual = None
    co2_elec_proy = co2_gas_proy = co2_proy = None
    co2_reduccion = co2_reduccion_pct = None

    if factor_emision_elec is not None and factor_emision_gas is not None and meses:
        kwh_anual        = _sum("kwh_total")
        kwh_cub_anual    = _sum("kwh_cubiertos")
        gj_caldera_anual = _sum("gj_consumido")
        gj_cogen_anual   = _sum("gj_gas_cogen")
        calor_rec_anual  = _sum("calor_recuperado_gj")

        co2_elec_actual = (kwh_anual * factor_emision_elec).quantize(_CENTAVO, ROUND_HALF_UP)
        co2_gas_actual  = (gj_caldera_anual * factor_emision_gas).quantize(_CENTAVO, ROUND_HALF_UP)
        co2_actual      = co2_elec_actual + co2_gas_actual

        co2_elec_proy = ((kwh_anual - kwh_cub_anual) * factor_emision_elec).quantize(_CENTAVO, ROUND_HALF_UP)
        gj_caldera_con_cogen = max(
            gj_caldera_anual - (calor_rec_anual / params.eficiencia_caldera),
            Decimal("0"),
        )
        gj_gas_total_proy = gj_cogen_anual + gj_caldera_con_cogen
        co2_gas_proy = (gj_gas_total_proy * factor_emision_gas).quantize(_CENTAVO, ROUND_HALF_UP)
        co2_proy     = co2_elec_proy + co2_gas_proy

        co2_reduccion = co2_actual - co2_proy
        if co2_actual > 0:
            co2_reduccion_pct = ((co2_reduccion / co2_actual) * 100).quantize(_CENTAVO, ROUND_HALF_UP)
        else:
            co2_reduccion_pct = Decimal("0")

    if inv_mxn is not None and inv_mxn > 0:
        beneficio_fiscal = (inv_mxn * _TASA_ISR).quantize(_CENTAVO, ROUND_HALF_UP)
        flujo_anio_1_ben = (_sum("ebitda_mes_mxn") + beneficio_fiscal).quantize(_CENTAVO, ROUND_HALF_UP)
    else:
        beneficio_fiscal = None
        flujo_anio_1_ben = None

    return CoGenResultado(
        params=params,
        meses=meses,
        kwh_total_anual=_sum("kwh_total"),
        kwh_cubiertos_anual=_sum("kwh_cubiertos"),
        gj_gas_cogen_anual=(_gj_cogen_anual := _sum("gj_gas_cogen")),
        gj_gas_cogen_pci_anual=(_gj_cogen_anual / _FACTOR_PCI_A_PCS).quantize(_DIEZMILAVO, ROUND_HALF_UP),
        costo_gas_cogen_anual_mxn=_sum("costo_gas_cogen_mxn"),
        ahorro_electricidad_anual_mxn=_sum("ahorro_electricidad_mxn"),
        ahorro_energia_anual_mxn=_sum("ahorro_energia_mes_mxn"),
        ahorro_capacidad_anual_mxn=_sum("ahorro_capacidad_mes_mxn"),
        ahorro_distribucion_anual_mxn=_sum("ahorro_distribucion_mes_mxn"),
        ahorro_otros_servicios_anual_mxn=_sum("ahorro_otros_servicios_mes_mxn"),
        ahorro_caldera_anual_mxn=_sum("ahorro_caldera_mxn"),
        ebitda_anual_mxn=_sum("ebitda_mes_mxn"),
        gasto_om_anual_mxn=_sum("gasto_om_mes_mxn"),
        capacidad_nominal_kw=capacidad_kw,
        inversion_usd=inv_usd,
        inversion_mxn=inv_mxn,
        tipo_cambio_mxn_usd=tipo_cambio,
        co2_actual_electricidad_kg_anual=co2_elec_actual,
        co2_actual_gas_kg_anual=co2_gas_actual,
        co2_actual_total_kg_anual=co2_actual,
        co2_proyectado_electricidad_kg_anual=co2_elec_proy,
        co2_proyectado_gas_kg_anual=co2_gas_proy,
        co2_proyectado_total_kg_anual=co2_proy,
        co2_reduccion_kg_anual=co2_reduccion,
        co2_reduccion_porcentaje=co2_reduccion_pct,
        beneficio_fiscal_anio_1_mxn=beneficio_fiscal,
        flujo_anio_1_con_beneficio_mxn=flujo_anio_1_ben,
    )


def _capacidad_nominal_kw_ppa(ppa_invoices: list[FacturaCalificado]) -> Decimal | None:
    """max(consumo_kwh / (días × 24 h)) sobre facturas PPA con consumo positivo."""
    maximos: list[Decimal] = []
    for ppa in ppa_invoices:
        if ppa.consumo_kwh > 0:
            dias = (ppa.periodo_fin - ppa.periodo_inicio).days
            if dias > 0:
                horas = Decimal(dias * 24)
                maximos.append(ppa.consumo_kwh / horas)
    if not maximos:
        return None
    return Decimal(math.ceil(max(maximos)))


def calcular_cogen_ppa(
    ppa_invoices: list[FacturaCalificado],
    gas_invoices: list[GasInvoice],
    params: CoGenParams,
    tipo_cambio: Decimal = _TC_DEFAULT,
    factor_emision_elec: Decimal | None = None,
    factor_emision_gas: Decimal | None = None,
) -> CoGenResultado:
    """Calcula el EBITDA mensual para suministro eléctrico calificado (PPA).

    Empareja facturas PPA con facturas de gas por mes asociado.
    Sin desglose horario: el ahorro eléctrico se calcula como kWh cubiertos × precio promedio.
    Los campos exclusivos de GDMTH (Capacidad, Distribución, periodos horarios) se fijan en 0.
    """
    gas_por_mes: dict[tuple[int, int], GasInvoice] = {
        mes_asociado(g.periodo_inicio, g.periodo_fin): g
        for g in gas_invoices
    }

    meses: list[CoGenMes] = []

    for ppa in sorted(ppa_invoices, key=lambda x: x.periodo_inicio):
        clave = mes_asociado(ppa.periodo_inicio, ppa.periodo_fin)
        gas = gas_por_mes.get(clave)
        if gas is None:
            logger.warning(
                "Sin factura de gas para %s (PPA: %s–%s)",
                clave, ppa.periodo_inicio, ppa.periodo_fin,
            )
            continue

        kwh_total = ppa.consumo_kwh
        if kwh_total == 0:
            continue

        costo_ppa = ppa.subtotal_mxn
        costo_prom_kwh = (costo_ppa / kwh_total).quantize(_CENTAVO, ROUND_HALF_UP)
        costo_unit_gj = gas.costo_unitario_total_gj

        kwh_cubiertos = (kwh_total * params.cobertura_electrica).quantize(_CENTAVO, ROUND_HALF_UP)

        # Ahorro eléctrico simplificado PPA: kWh cubiertos × precio promedio
        ahorro_electricidad = (kwh_cubiertos * costo_prom_kwh).quantize(_CENTAVO, ROUND_HALF_UP)
        ahorro_energia = ahorro_electricidad
        ahorro_capacidad = Decimal("0")
        ahorro_distribucion = Decimal("0")

        # Gas cogen, caldera, O&M — idéntico a GDMTH
        gj_gas_cogen = (kwh_cubiertos * _KWH_A_GJ * _FACTOR_PCI_A_PCS / params.rendimiento_electrico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        costo_gas_cogen = (gj_gas_cogen * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)
        calor_recuperado = (gj_gas_cogen * params.rendimiento_termico).quantize(_DIEZMILAVO, ROUND_HALF_UP)
        ahorro_caldera = (calor_recuperado / params.eficiencia_caldera * costo_unit_gj).quantize(_CENTAVO, ROUND_HALF_UP)
        gasto_om = (kwh_cubiertos * _FACTOR_OM).quantize(_CENTAVO, ROUND_HALF_UP)
        ebitda = ahorro_electricidad + ahorro_caldera - costo_gas_cogen - gasto_om

        dias_orig = (ppa.periodo_fin - ppa.periodo_inicio).days

        mes_anio, mes_mes = clave
        ultimo_dia = calendar.monthrange(mes_anio, mes_mes)[1]

        meses.append(CoGenMes(
            periodo_inicio=date(mes_anio, mes_mes, 1),
            periodo_fin=date(mes_anio, mes_mes, ultimo_dia),
            kwh_total=kwh_total,
            costo_cfe_mxn=costo_ppa,
            costo_promedio_kwh=costo_prom_kwh,
            gj_consumido=gas.consumo_total_gj,
            costo_unitario_gj=costo_unit_gj,
            costo_gas_actual_mxn=gas.subtotal_mxn,
            kwh_cubiertos=kwh_cubiertos,
            kwh_punta_cubierto=Decimal("0"),
            kwh_intermedia_cubierto=Decimal("0"),
            kwh_base_cubierto=Decimal("0"),
            ahorro_energia_mes_mxn=ahorro_energia,
            ahorro_capacidad_mes_mxn=Decimal("0"),
            ahorro_distribucion_mes_mxn=Decimal("0"),
            cargo_otros_total_mxn=Decimal("0"),
            precio_otros_mxn_kwh=Decimal("0"),
            ahorro_otros_servicios_mes_mxn=Decimal("0"),
            gj_gas_cogen=gj_gas_cogen,
            costo_gas_cogen_mxn=costo_gas_cogen,
            ahorro_electricidad_mxn=ahorro_electricidad,
            calor_recuperado_gj=calor_recuperado,
            ahorro_caldera_mxn=ahorro_caldera,
            ebitda_mes_mxn=ebitda,
            gasto_om_mes_mxn=gasto_om,
            kwh_punta_total=Decimal("0"),
            kwh_intermedia_total=Decimal("0"),
            kwh_base_total=Decimal("0"),
            cu_punta_kwh=Decimal("0"),
            cu_intermedia_kwh=Decimal("0"),
            cu_base_kwh=Decimal("0"),
            kw_max=Decimal("0"),
            kw_punta_orig=Decimal("0"),
            dias_facturados=dias_orig,
            kwh_total_orig=kwh_total,
            precio_capacidad_kw=Decimal("0"),
            precio_distribucion_kw=Decimal("0"),
            kw_facturado_capacidad=Decimal("0"),
            kw_facturado_distribucion=Decimal("0"),
            kw_efectiva_capacidad_post=Decimal("0"),
            kw_efectiva_distribucion_post=Decimal("0"),
            prorrateado=False,
            nota_prorrateo="",
        ))

    def _sum(attr: str) -> Decimal:
        return sum(getattr(m, attr) for m in meses) if meses else Decimal("0")

    capacidad_kw = _capacidad_nominal_kw_ppa(ppa_invoices)
    if capacidad_kw is not None and capacidad_kw > 0:
        inv_usd = (capacidad_kw * _USD_POR_KW).quantize(_CENTAVO, ROUND_HALF_UP)
        inv_mxn = (inv_usd * tipo_cambio).quantize(_CENTAVO, ROUND_HALF_UP)
    else:
        inv_usd = inv_mxn = None

    # ── Huella de carbono ────────────────────────────────────────────────────
    co2_elec_actual = co2_gas_actual = co2_actual = None
    co2_elec_proy = co2_gas_proy = co2_proy = None
    co2_reduccion = co2_reduccion_pct = None

    if factor_emision_elec is not None and factor_emision_gas is not None and meses:
        kwh_anual        = _sum("kwh_total")
        kwh_cub_anual    = _sum("kwh_cubiertos")
        gj_caldera_anual = _sum("gj_consumido")
        gj_cogen_anual   = _sum("gj_gas_cogen")
        calor_rec_anual  = _sum("calor_recuperado_gj")

        co2_elec_actual = (kwh_anual * factor_emision_elec).quantize(_CENTAVO, ROUND_HALF_UP)
        co2_gas_actual  = (gj_caldera_anual * factor_emision_gas).quantize(_CENTAVO, ROUND_HALF_UP)
        co2_actual      = co2_elec_actual + co2_gas_actual

        co2_elec_proy = ((kwh_anual - kwh_cub_anual) * factor_emision_elec).quantize(_CENTAVO, ROUND_HALF_UP)
        gj_caldera_con_cogen = max(
            gj_caldera_anual - (calor_rec_anual / params.eficiencia_caldera),
            Decimal("0"),
        )
        gj_gas_total_proy = gj_cogen_anual + gj_caldera_con_cogen
        co2_gas_proy = (gj_gas_total_proy * factor_emision_gas).quantize(_CENTAVO, ROUND_HALF_UP)
        co2_proy     = co2_elec_proy + co2_gas_proy

        co2_reduccion = co2_actual - co2_proy
        if co2_actual > 0:
            co2_reduccion_pct = ((co2_reduccion / co2_actual) * 100).quantize(_CENTAVO, ROUND_HALF_UP)
        else:
            co2_reduccion_pct = Decimal("0")

    if inv_mxn is not None and inv_mxn > 0:
        beneficio_fiscal = (inv_mxn * _TASA_ISR).quantize(_CENTAVO, ROUND_HALF_UP)
        flujo_anio_1_ben = (_sum("ebitda_mes_mxn") + beneficio_fiscal).quantize(_CENTAVO, ROUND_HALF_UP)
    else:
        beneficio_fiscal = None
        flujo_anio_1_ben = None

    return CoGenResultado(
        params=params,
        meses=meses,
        kwh_total_anual=_sum("kwh_total"),
        kwh_cubiertos_anual=_sum("kwh_cubiertos"),
        gj_gas_cogen_anual=(_gj_cogen_anual := _sum("gj_gas_cogen")),
        gj_gas_cogen_pci_anual=(_gj_cogen_anual / _FACTOR_PCI_A_PCS).quantize(_DIEZMILAVO, ROUND_HALF_UP),
        costo_gas_cogen_anual_mxn=_sum("costo_gas_cogen_mxn"),
        ahorro_electricidad_anual_mxn=_sum("ahorro_electricidad_mxn"),
        ahorro_energia_anual_mxn=_sum("ahorro_energia_mes_mxn"),
        ahorro_capacidad_anual_mxn=_sum("ahorro_capacidad_mes_mxn"),
        ahorro_distribucion_anual_mxn=_sum("ahorro_distribucion_mes_mxn"),
        ahorro_otros_servicios_anual_mxn=Decimal("0"),
        ahorro_caldera_anual_mxn=_sum("ahorro_caldera_mxn"),
        ebitda_anual_mxn=_sum("ebitda_mes_mxn"),
        gasto_om_anual_mxn=_sum("gasto_om_mes_mxn"),
        capacidad_nominal_kw=capacidad_kw,
        inversion_usd=inv_usd,
        inversion_mxn=inv_mxn,
        tipo_cambio_mxn_usd=tipo_cambio,
        co2_actual_electricidad_kg_anual=co2_elec_actual,
        co2_actual_gas_kg_anual=co2_gas_actual,
        co2_actual_total_kg_anual=co2_actual,
        co2_proyectado_electricidad_kg_anual=co2_elec_proy,
        co2_proyectado_gas_kg_anual=co2_gas_proy,
        co2_proyectado_total_kg_anual=co2_proy,
        co2_reduccion_kg_anual=co2_reduccion,
        co2_reduccion_porcentaje=co2_reduccion_pct,
        beneficio_fiscal_anio_1_mxn=beneficio_fiscal,
        flujo_anio_1_con_beneficio_mxn=flujo_anio_1_ben,
    )
