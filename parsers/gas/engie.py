# parsers/gas/engie.py
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

import pdfplumber

from models.gas_invoice import GasConcepto, GasInvoice
from parsers.base import InvoiceParser

# ── Regex ────────────────────────────────────────────────────────────────────
RE_UUID = re.compile(
    r'FACTURA\s+([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}'
    r'-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
)
# Folio aparece al final de la línea de dirección: "...Piso 16, I00000547"
RE_FOLIO = re.compile(r',\s*(I\d+)\s*$', re.MULTILINE)
# Fecha emisión en ISO: "11000, 2023-12-14T15:52:02"
RE_FECHA_EMISION = re.compile(r'(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}')
# Periodo: "De 01.11.2023 a 30.11.2023"
RE_PERIODO = re.compile(r'De\s+(\d{2}\.\d{2}\.\d{4})\s+a\s+(\d{2}\.\d{2}\.\d{4})')
# Bloque: "NÚMERO DE CLIENTE CUENTA CONTRATO FECHA LÍMITE DE PAGO\n610002800 5100096634 25.12.2023"
RE_CLIENTE_BLOQUE = re.compile(
    r'N[ÚU]MERO\s+DE\s+CLIENTE\s+CUENTA\s+CONTRATO\s+FECHA\s+L[IÍ]MITE\s+DE\s+PAGO'
    r'\s*\n(\d+)\s+(\d+)\s+(\d{2}\.\d{2}\.\d{4})',
    re.IGNORECASE,
)
# RFC proveedor: línea propia "RFC TRA0002119W1"
RE_RFC_PROVEEDOR = re.compile(r'^RFC\s+([A-Z&]{3,4}\d{6}[A-Z0-9]{3})\s*$', re.MULTILINE)
# RFC cliente: siguiente línea después de "RFC MÉTODO DE PAGO ..." comienza con el RFC + PPD
RE_RFC_CLIENTE = re.compile(r'^([A-Z&]{3,4}\d{6}[A-Z0-9]{3})\s+PPD\b', re.MULTILINE)
# Nombre proveedor: primera línea después de "FOLIO"
RE_NOMBRE_PROVEEDOR = re.compile(r'FOLIO\s*\n(.+)\n', re.IGNORECASE)
# Nombre cliente: primera línea después de "CLIENTE Y DOMICILIO"
RE_NOMBRE_CLIENTE = re.compile(r'CLIENTE\s+Y\s+DOMICILIO\s*\n(.+)', re.IGNORECASE)
# Punto suministro: antes de "COMERCIALIZACION"
RE_PUNTO_SUMINISTRO = re.compile(
    r'PUNTO\s+DE\s+SUMINISTRO.*?\n(.+?)\s+COMERCIALIZACION',
    re.IGNORECASE,
)
# Bloque medidor: "TIPO DE MEDIDOR NÚMERO DE CASETA TIPO DE LECTURA\n11067 11067-01 REAL"
RE_MEDIDOR_BLOQUE = re.compile(
    r'TIPO\s+DE\s+MEDIDOR\s+N[ÚU]MERO\s+DE\s+CASETA\s+TIPO\s+DE\s+LECTURA'
    r'\s*\n\d+\s+(\S+)\s+(\w+)',
    re.IGNORECASE,
)
# Consumo: "2,960,411.81 0.00 0.035958531,Gj/m3"
RE_CONSUMO_BLOQUE = re.compile(
    r'CONSUMO\s+M3\s+CORREGIDOS.*?\n([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d.]+),Gj/m3',
    re.IGNORECASE | re.DOTALL,
)
# Líneas de conceptos
RE_COMPRAVENTA = re.compile(
    r'83101601\s+Compraventa de Gas Natural'
    r'\s+[\d.]+\s+[\d.]+\s+([\d,.]+)\s+GJ\s+\$([\d,.]+)\s+\$([\d,.]+)'
)
RE_TRANSPORTE = re.compile(
    r'78102101\s+Transporte por Ducto Gas Natural'
    r'\s+[\d.]+\s+[\d.]+\s+([\d,.]+)\s+GJ\s+\$([\d,.]+)\s+\$([\d,.]+)'
)
RE_SUBTOTAL = re.compile(r'SUB-TOTAL:\s*([\d,]+\.?\d*)')
RE_IVA = re.compile(r'TASA\s+IVA\s+16\s*%\s+([\d,]+\.?\d*)')
RE_TOTAL = re.compile(r'TOTAL\s*:\$\s*([\d,]+\.?\d*)')


def _parse_decimal(texto: str) -> Decimal:
    try:
        return Decimal(texto.strip().replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"No se puede convertir a Decimal: '{texto}'")


def _parse_fecha(texto: str) -> date:
    """Convierte 'DD.MM.YYYY' a date."""
    d, m, y = texto.strip().split(".")
    return date(int(y), int(m), int(d))


class ENGIEParser(InvoiceParser):
    """Parser para facturas de gas natural ENGIE / GDF Suez Mexico."""

    def parse(self, pdf_path: Path) -> GasInvoice:
        pdf_path = Path(pdf_path)
        advertencias: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            texto = pdf.pages[0].extract_text() or ""

        def _req(patron: re.Pattern, nombre: str) -> str | None:
            m = patron.search(texto)
            if m:
                return m.group(1).strip()
            advertencias.append(f"Campo no encontrado: {nombre}")
            return None

        def _d(raw: str | None) -> Decimal:
            return _parse_decimal(raw) if raw else Decimal("0")

        # UUID
        uuid_raw = _req(RE_UUID, "uuid_cfdi") or ""

        # Fecha de emisión
        m_emision = RE_FECHA_EMISION.search(texto)
        if m_emision:
            y, mo, d = m_emision.group(1).split("-")
            fecha_emision = date(int(y), int(mo), int(d))
        else:
            advertencias.append("Campo no encontrado: fecha_emision")
            fecha_emision = date.today()

        # Periodo
        m_periodo = RE_PERIODO.search(texto)
        if m_periodo:
            periodo_inicio = _parse_fecha(m_periodo.group(1))
            periodo_fin    = _parse_fecha(m_periodo.group(2))
        else:
            advertencias.append("Campo no encontrado: periodo")
            periodo_inicio = periodo_fin = date.today()

        # Bloque cliente: número de cliente, cuenta contrato, fecha límite
        m_bloque = RE_CLIENTE_BLOQUE.search(texto)
        if m_bloque:
            numero_cliente  = m_bloque.group(1)
            cuenta_contrato = m_bloque.group(2)
            fecha_limite    = _parse_fecha(m_bloque.group(3))
        else:
            advertencias.append("Campo no encontrado: bloque_cliente")
            numero_cliente = cuenta_contrato = ""
            fecha_limite = periodo_fin

        # Medidor / caseta / lectura
        m_med = RE_MEDIDOR_BLOQUE.search(texto)
        if m_med:
            numero_caseta = m_med.group(1)
            tipo_lectura  = m_med.group(2)
        else:
            advertencias.append("Campo no encontrado: medidor")
            numero_caseta = tipo_lectura = ""

        # Consumo
        m_consumo = RE_CONSUMO_BLOQUE.search(texto)
        if m_consumo:
            consumo_m3  = _parse_decimal(m_consumo.group(1))
            consumo_sin = _parse_decimal(m_consumo.group(2))
            poder_cal   = _parse_decimal(m_consumo.group(3))
        else:
            advertencias.append("Campo no encontrado: consumo_bloque")
            consumo_m3 = consumo_sin = poder_cal = Decimal("0")

        # Conceptos
        conceptos: list[GasConcepto] = []
        m_comp = RE_COMPRAVENTA.search(texto)
        if m_comp:
            conceptos.append(GasConcepto(
                descripcion="Compraventa de Gas Natural",
                clave_producto="83101601",
                cantidad_gj=_parse_decimal(m_comp.group(1)),
                precio_unitario_gj=_parse_decimal(m_comp.group(2)),
                importe_mxn=_parse_decimal(m_comp.group(3)),
            ))
        else:
            advertencias.append("Campo no encontrado: compraventa")

        m_trans = RE_TRANSPORTE.search(texto)
        if m_trans:
            conceptos.append(GasConcepto(
                descripcion="Transporte por Ducto Gas Natural",
                clave_producto="78102101",
                cantidad_gj=_parse_decimal(m_trans.group(1)),
                precio_unitario_gj=_parse_decimal(m_trans.group(2)),
                importe_mxn=_parse_decimal(m_trans.group(3)),
            ))
        else:
            advertencias.append("Campo no encontrado: transporte")

        compraventa = next((c for c in conceptos if c.clave_producto == "83101601"), None)
        consumo_total_gj    = compraventa.cantidad_gj if compraventa else Decimal("0")
        costo_unitario_total = sum((c.precio_unitario_gj for c in conceptos), Decimal("0"))

        return GasInvoice(
            uuid_cfdi=uuid_raw,
            folio=_req(RE_FOLIO, "folio") or "",
            fecha_emision=fecha_emision,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            fecha_limite_pago=fecha_limite,
            nombre_proveedor=_req(RE_NOMBRE_PROVEEDOR, "nombre_proveedor") or "",
            rfc_proveedor=_req(RE_RFC_PROVEEDOR, "rfc_proveedor") or "",
            nombre_cliente=_req(RE_NOMBRE_CLIENTE, "nombre_cliente") or "",
            rfc_cliente=_req(RE_RFC_CLIENTE, "rfc_cliente") or "",
            numero_cliente=numero_cliente,
            cuenta_contrato=cuenta_contrato,
            punto_suministro=_req(RE_PUNTO_SUMINISTRO, "punto_suministro") or "",
            numero_caseta=numero_caseta,
            tipo_lectura=tipo_lectura,
            consumo_m3_corregidos=consumo_m3,
            consumo_sin_corregir_m3=consumo_sin,
            poder_calorifico_gj_m3=poder_cal,
            consumo_total_gj=consumo_total_gj,
            conceptos=conceptos,
            costo_unitario_total_gj=costo_unitario_total,
            subtotal_mxn=_d(_req(RE_SUBTOTAL, "subtotal")),
            iva_mxn=_d(_req(RE_IVA, "iva")),
            total_mxn=_d(_req(RE_TOTAL, "total")),
            pdf_path=str(pdf_path),
            advertencias=advertencias,
        )

    def validate(self, invoice: GasInvoice) -> list[str]:
        """Valida coherencia interna. Devuelve lista de errores (vacía = válido)."""
        errores = []
        if invoice.periodo_fin <= invoice.periodo_inicio:
            errores.append("periodo_fin debe ser posterior a periodo_inicio")
        suma = sum(c.importe_mxn for c in invoice.conceptos)
        if abs(suma - invoice.subtotal_mxn) > Decimal("1.00"):
            errores.append(
                f"Subtotal no cuadra: suma_conceptos={suma}, subtotal={invoice.subtotal_mxn}"
            )
        total_calc = invoice.subtotal_mxn + invoice.iva_mxn
        if abs(total_calc - invoice.total_mxn) > Decimal("1.00"):
            errores.append(
                f"Total no cuadra: calculado={total_calc}, factura={invoice.total_mxn}"
            )
        return errores
