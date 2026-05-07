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
    gj_gas_cogen: Decimal
    costo_gas_cogen_mxn: Decimal
    ahorro_electricidad_mxn: Decimal
    calor_recuperado_gj: Decimal
    ahorro_caldera_mxn: Decimal
    ebitda_mes_mxn: Decimal
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
