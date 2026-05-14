# models/cogen_result.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class CoGenParams:
    """Parámetros técnicos del proyecto de cogeneración."""
    cobertura_electrica: Decimal = Decimal("0.75")
    rendimiento_electrico: Decimal = Decimal("0.40")
    rendimiento_termico: Decimal = Decimal("0.25")
    eficiencia_caldera: Decimal = Decimal("0.85")


@dataclass
class CoGenMes:
    """Resultado de cogeneración para un mes calendario."""
    periodo_inicio: date
    periodo_fin: date
    # Entradas CFE
    kwh_total: Decimal
    costo_cfe_mxn: Decimal
    costo_promedio_kwh: Decimal
    # Entradas Gas
    gj_consumido: Decimal
    costo_unitario_gj: Decimal
    costo_gas_actual_mxn: Decimal
    # Salidas cogeneración
    kwh_cubiertos: Decimal
    kwh_punta_cubierto: Decimal
    kwh_intermedia_cubierto: Decimal
    kwh_base_cubierto: Decimal
    ahorro_energia_mes_mxn: Decimal
    ahorro_capacidad_mes_mxn: Decimal
    ahorro_distribucion_mes_mxn: Decimal
    gj_gas_cogen: Decimal
    costo_gas_cogen_mxn: Decimal
    ahorro_electricidad_mxn: Decimal
    calor_recuperado_gj: Decimal
    ahorro_caldera_mxn: Decimal
    ebitda_mes_mxn: Decimal
    gasto_om_mes_mxn: Decimal = Decimal("0")
    kwh_punta_total: Decimal = Decimal("0")
    kwh_intermedia_total: Decimal = Decimal("0")
    kwh_base_total: Decimal = Decimal("0")
    cu_punta_kwh: Decimal = Decimal("0")
    cu_intermedia_kwh: Decimal = Decimal("0")
    cu_base_kwh: Decimal = Decimal("0")
    # Datos para slider JS (demanda y precios componentes MEM)
    kw_max: Decimal = Decimal("0")
    dias_facturados: int = 0
    kwh_total_orig: Decimal = Decimal("0")
    precio_capacidad_kw: Decimal = Decimal("0")
    precio_distribucion_kw: Decimal = Decimal("0")
    # Prorrateo (campo informativo, vacío si no se aplicó)
    prorrateado: bool = False
    nota_prorrateo: str = ""


@dataclass
class CoGenResultado:
    """Resultado anual de cogeneración con detalle mensual."""
    params: CoGenParams
    meses: list[CoGenMes]
    # Totales anuales
    kwh_total_anual: Decimal
    kwh_cubiertos_anual: Decimal
    gj_gas_cogen_anual: Decimal
    costo_gas_cogen_anual_mxn: Decimal
    ahorro_electricidad_anual_mxn: Decimal
    ahorro_caldera_anual_mxn: Decimal
    ebitda_anual_mxn: Decimal
    gasto_om_anual_mxn: Decimal = Decimal("0")
    ahorro_energia_anual_mxn: Decimal = Decimal("0")
    ahorro_capacidad_anual_mxn: Decimal = Decimal("0")
    ahorro_distribucion_anual_mxn: Decimal = Decimal("0")
    gj_gas_cogen_pci_anual: Decimal = Decimal("0")  # GJ en PCI (sin factor 1.11) — para CELs
    # Capacidad e inversión (None si no hay datos CFE suficientes)
    capacidad_nominal_kw: Decimal | None = None
    inversion_usd: Decimal | None = None
    inversion_mxn: Decimal | None = None
    tipo_cambio_mxn_usd: Decimal | None = None
    # Huella de carbono (None si no hay factores de emisión configurados)
    co2_actual_electricidad_kg_anual: Decimal | None = None
    co2_actual_gas_kg_anual: Decimal | None = None
    co2_actual_total_kg_anual: Decimal | None = None
    co2_proyectado_electricidad_kg_anual: Decimal | None = None
    co2_proyectado_gas_kg_anual: Decimal | None = None
    co2_proyectado_total_kg_anual: Decimal | None = None
    co2_reduccion_kg_anual: Decimal | None = None
    co2_reduccion_porcentaje: Decimal | None = None
