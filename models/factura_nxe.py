# models/factura_nxe.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class FacturaNXE:
    """Estado de cuenta mensual NX Energía persistido en Supabase."""

    id: int
    contrato_id: int
    cliente_id: int

    # Identificación
    documento_ref: str | None
    suministrador: str
    rfc_suministrador: str | None

    # Periodo
    periodo_inicio: date
    periodo_fin: date
    anio: int | None
    mes: int | None
    nombre_canonico: str | None

    # Parámetros contratados
    precio_energia_usd_mwh: Decimal | None
    tipo_cambio_mxn_usd: Decimal | None
    precio_cels_usd: Decimal | None
    precio_potencia_usd_kwmes: Decimal | None
    factor_potencia_pct: Decimal | None
    energia_contratada_kwh: Decimal | None
    potencia_contratada_kwmes: Decimal | None

    # Consumo
    energia_consumida_kwh: Decimal
    desviacion_pct: Decimal | None
    precio_monocomico_mxn_kwh: Decimal | None

    # 5 categorías del resumen (MXN)
    cargo_energia_mxn: Decimal | None
    cargo_potencia_mxn: Decimal | None
    cargo_cel_mxn: Decimal | None
    cargos_regulados_mxn: Decimal | None
    ajustes_penalizaciones_mxn: Decimal | None
    cobro_total_mxn: Decimal

    # Detalle dentro de ajustes
    cobro_energia_no_consumida_usd: Decimal | None
    cobro_exceso_consumo_usd: Decimal | None
    costo_desvios_pdp_mxn: Decimal | None
    costo_reliquidaciones_mxn: Decimal | None

    # Subtotales regulados
    tarifas_reguladas_mxn: Decimal | None
    cargo_servicios_mem_mxn: Decimal | None

    # Detalle diario
    detalle_diario: list = field(default_factory=list)

    # Metadatos
    advertencias: list = field(default_factory=list)
    pdf_url: str | None = None
    parser_version: str | None = None
    created_at: datetime | None = None
