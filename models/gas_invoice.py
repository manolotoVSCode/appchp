from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class GasConcepto:
    descripcion: str
    clave_producto: str
    cantidad_gj: Decimal
    precio_unitario_gj: Decimal
    importe_mxn: Decimal


@dataclass
class GasInvoice:
    # Identificación CFDI
    uuid_cfdi: str
    folio: str
    fecha_emision: date
    periodo_inicio: date
    periodo_fin: date
    fecha_limite_pago: date

    # Proveedor
    nombre_proveedor: str
    rfc_proveedor: str

    # Cliente
    nombre_cliente: str
    rfc_cliente: str
    numero_cliente: str
    cuenta_contrato: str
    punto_suministro: str

    # Medición
    numero_caseta: str
    tipo_lectura: str
    consumo_m3_corregidos: Decimal
    consumo_sin_corregir_m3: Decimal
    poder_calorifico_gj_m3: Decimal
    consumo_total_gj: Decimal

    # Conceptos
    conceptos: list[GasConcepto]

    # Costo unitario derivado (suma de todos los conceptos / GJ)
    costo_unitario_total_gj: Decimal

    # Totales
    subtotal_mxn: Decimal
    iva_mxn: Decimal
    total_mxn: Decimal

    # Trazabilidad
    pdf_path: str
    advertencias: list[str] = field(default_factory=list)

    # Vínculos operativos (opcionales, hidratados desde BD)
    contrato_id: int | None = None
    planta_id: int | None = None
    anio: int | None = None
    mes: int | None = None
    nombre_canonico: str | None = None
