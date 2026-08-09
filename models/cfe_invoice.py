from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class MEMComponente:
    nombre: str
    cargo_fijo_mxn: Decimal
    cargo_demanda_mxn: Decimal
    cargo_energia_mxn: Decimal
    importe_mxn: Decimal


@dataclass
class CFEConsumoHorario:
    periodo: str           # "base" | "intermedio" | "punta"
    consumo_kwh: Decimal
    demanda_kw: Decimal
    costo_unitario_kwh: Decimal


@dataclass
class CFEInvoice:
    # Identificación CFDI
    uuid_cfdi: str | None
    folio: str
    serie: str | None
    fecha_emision: date
    periodo_inicio: date
    periodo_fin: date
    fecha_limite_pago: date

    # Cliente
    nombre_cliente: str
    rfc_cliente: str
    numero_servicio: str
    rmu: str | None

    # Suministro
    tarifa: str
    numero_medidor: str
    multiplicador: int
    carga_conectada_kw: Decimal
    demanda_contratada_kw: Decimal

    # Consumo por periodo
    periodos: list[CFEConsumoHorario]

    # Otros registros del medidor
    kw_max: Decimal
    kvArh: Decimal
    factor_potencia_pct: Decimal

    # MEM en bruto
    componentes_mem: list[MEMComponente]

    # Desglose financiero
    cargo_fijo_mxn: Decimal
    energia_total_mxn: Decimal
    cargo_factor_potencia_mxn: Decimal
    subtotal_mxn: Decimal
    iva_mxn: Decimal
    facturacion_periodo_mxn: Decimal   # = subtotal_mxn + iva_mxn; NO usar en cálculos, solo para trazabilidad
    derecho_alumbrado_publico_mxn: Decimal
    credito_aplicado_mxn: Decimal      # negativo si aplica, Decimal("0") si no
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
