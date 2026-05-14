# models/factura_calificado.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class FacturaCalificado:
    id: int
    contrato_id: int
    cliente_id: int
    suministrador: str | None
    rpu: str | None
    serie_folio: str | None
    periodo_inicio: date
    periodo_fin: date
    dias_facturados: int | None
    anio: int | None
    mes: int | None
    nombre_canonico: str | None
    consumo_kwh: Decimal
    precio_unitario_mxn_kwh: Decimal
    subtotal_mxn: Decimal
    iva_mxn: Decimal | None
    total_mxn: Decimal | None
    excedente_detectado: bool
    advertencias: list = field(default_factory=list)
    pdf_url: str | None = None
    parser_version: str | None = None
    created_at: datetime | None = None
