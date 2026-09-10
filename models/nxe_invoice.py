# models/nxe_invoice.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class NXEInvoice:
    """Estado de cuenta mensual — NX Energía S.A. de C.V. (no es CFDI).

    Las 5 categorías del resumen agrupan todos los cargos:
      cargo_energia_mxn            ← Cargo por Energía
      cargo_potencia_mxn           ← Cargo por Potencia
      cargo_cel_mxn                ← Cargo por CEL
      cargos_regulados_mxn         ← Tarifas Reguladas + Cargo Servicios MEM
      ajustes_penalizaciones_mxn   ← Desvíos PDP + Reliquidaciones CENACE
    La suma de las 5 debe coincidir con cobro_total_mxn (validación del parser).
    """

    # ── Identificación ────────────────────────────────────────────────────────
    documento_ref: str | None        # "NXE_ITI_2025.02"
    suministrador: str               # "NX ENERGIA S.A. DE C.V."
    rfc_suministrador: str | None    # "NEN230613SE2"

    # ── Periodo ───────────────────────────────────────────────────────────────
    periodo_inicio: date
    periodo_fin: date

    # ── Parámetros contratados (página 1) ─────────────────────────────────────
    precio_energia_usd_mwh: Decimal | None     # 52.84
    tipo_cambio_mxn_usd: Decimal | None        # 18.71
    precio_cels_usd: Decimal | None            # 15.00
    precio_potencia_usd_kwmes: Decimal | None  # 21.58 (label del PDF dice MWh pero es kW-mes)
    factor_potencia_pct: Decimal | None        # 93.03
    energia_contratada_kwh: Decimal | None     # 2,608,522
    potencia_contratada_kwmes: Decimal | None  # 2,609

    # ── Consumo ───────────────────────────────────────────────────────────────
    energia_consumida_kwh: Decimal             # 2,413,311 ← campo principal
    desviacion_pct: Decimal | None             # -7.48  (puede ser negativo)
    precio_monocomico_mxn_kwh: Decimal | None  # 2.1181 ← precio unitario

    # ── 5 categorías del resumen (MXN) ───────────────────────────────────────
    cargo_energia_mxn: Decimal | None
    cargo_potencia_mxn: Decimal | None
    cargo_cel_mxn: Decimal | None
    cargos_regulados_mxn: Decimal | None       # tarifas_reguladas + cargo_servicios_mem
    ajustes_penalizaciones_mxn: Decimal | None  # costo_desvios_pdp + costo_reliquidaciones
    cobro_total_mxn: Decimal                   # ← total

    # ── Detalle dentro de ajustes (para visibilidad operativa) ───────────────
    cobro_energia_no_consumida_usd: Decimal | None  # cláusula 2.5.2
    cobro_exceso_consumo_usd: Decimal | None         # cláusula 2.5.3
    costo_desvios_pdp_mxn: Decimal | None
    costo_reliquidaciones_mxn: Decimal | None

    # ── Subtotales regulados (para auditoría) ────────────────────────────────
    tarifas_reguladas_mxn: Decimal | None     # "Monto de las Tarifas Reguladas"
    cargo_servicios_mem_mxn: Decimal | None   # "Costo por Servicios Complementarios MEM"

    # ── Detalle diario (Tablas 1.1 + 1.2 + 1.3 fusionadas, 31 días) ─────────
    detalle_diario: list[dict] = field(default_factory=list)

    # ── Metadatos ─────────────────────────────────────────────────────────────
    advertencias: list[str] = field(default_factory=list)
    parser_version: str = "1.0.0"
