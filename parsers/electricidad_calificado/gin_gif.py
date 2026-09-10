from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pdfplumber

from parsers.base import InvoiceParser
from parsers.electricidad_calificado.gin import GINInvoice

# ---------------------------------------------------------------------------
# Regex — Formato GIF (GIN 2025, plantilla nueva)
#
# Texto característico (pdfplumber):
#   GENERACION INDUSTRIAL
#   GIN040707G89 SERIE: GIF          ← RFC y SERIE en la misma línea
#   FOLIO: 0129
#   FECHA: 2025-03-11T12:23:06
#   R.F.C.: ITI170630377             ← receptor con prefijo "R.F.C.:"
#   Periodo de facturación: del 2025-02-01 al 2025-02-28   ← fechas ISO
#   83101800 Consumo de Energía Eléctrica 1,839,201.0000 KWH 2.1239 3,906,276.39
#   IMPORTE CON LETRA SUBTOTAL
#   $3,906,276.39                    ← importe en línea propia
#   IMPUESTOS TRASLADADOS $625,004.22
#   ... TOTAL
#   $4,531,280.61
#   FOLIO FISCAL: 22584568-2805-4167-9C85-92FECDFA01C7
# ---------------------------------------------------------------------------

RE_EMISOR_NOMBRE = re.compile(r'^(GENERACION\s+INDUSTRIAL[^\n]*)', re.IGNORECASE | re.MULTILINE)

# RFC emisor: aparece al inicio de línea seguido de " SERIE:"
RE_EMISOR_RFC = re.compile(r'^([A-Z&]{3,4}\d{6}[A-Z0-9]{3})\s+SERIE:', re.MULTILINE | re.IGNORECASE)

# RFC receptor: precedido por "R.F.C.:"
RE_RECEPTOR_RFC = re.compile(r'R\.F\.C\.\s*:\s*([A-Z&]{3,4}\d{6}[A-Z0-9]{3})', re.IGNORECASE)

# Serie: en la misma línea que el RFC emisor
RE_SERIE = re.compile(r'SERIE:\s*([A-Z0-9]+)', re.IGNORECASE)

# Folio: FOLIO: <número> — lookahead negativo para no capturar "FOLIO FISCAL:"
RE_FOLIO = re.compile(r'FOLIO(?!\s+FISCAL):\s*(\d+)', re.IGNORECASE)

# Fecha de emisión
RE_FECHA = re.compile(r'FECHA:\s*(\d{4}-\d{2}-\d{2})T', re.IGNORECASE)

# Periodo en fechas ISO
RE_PERIODO = re.compile(
    r'Periodo de facturaci[oó]n:\s*del\s+(\d{4}-\d{2}-\d{2})\s+al\s+(\d{4}-\d{2}-\d{2})',
    re.IGNORECASE,
)

# UUID: etiqueta explícita en este formato
RE_UUID = re.compile(
    r'FOLIO FISCAL:\s*([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})',
    re.IGNORECASE,
)

# Consumo: "... Consumo de Energía Eléctrica <kwh> KWH <precio> <importe>"
RE_CONSUMO = re.compile(
    r'Consumo de Energ[íi]a El[eé]ctrica\s+([\d,]+\.?\d*)\s+KWH\s+([\d.]+)\s+([\d,]+\.\d{2})',
    re.IGNORECASE,
)

# Subtotal: "SUBTOTAL\n$3,906,276.39"
RE_SUBTOTAL = re.compile(r'\bSUBTOTAL\s*\n\s*\$([\d,]+\.\d{2})', re.IGNORECASE)

# IVA: "IMPUESTOS TRASLADADOS $625,004.22"
RE_IVA = re.compile(r'IMPUESTOS TRASLADADOS\s+\$([\d,]+\.\d{2})', re.IGNORECASE)

# Total: "TOTAL\n$4,531,280.61"
RE_TOTAL = re.compile(r'\bTOTAL\s*\n\s*\$([\d,]+\.\d{2})', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _clean_decimal(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


class GINGIFParser(InvoiceParser):
    """
    Parser para facturas de electricidad calificada — emisor GIN, formato GIF (2025).

    Formato distinto al original GIN_A: serie y folio en líneas separadas,
    periodo en fechas ISO, importes con '$' en línea propia, sin campo RPU.
    Devuelve el mismo GINInvoice que GINParser.
    """

    VERSION = "1.0.0"

    def parse(self, pdf_path: Path) -> GINInvoice:
        pdf_path = Path(pdf_path)
        advertencias: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            paginas = [p.extract_text() or "" for p in pdf.pages]

        texto = "\n".join(paginas)

        # --- Emisor nombre ---
        suministrador: str | None = None
        m = RE_EMISOR_NOMBRE.search(texto)
        if m:
            suministrador = re.sub(r'\s+', ' ', m.group(1)).strip().upper()
        else:
            advertencias.append("Campo no encontrado: suministrador")

        # --- Emisor RFC ---
        rfc_suministrador: str | None = None
        m = RE_EMISOR_RFC.search(texto)
        if m:
            rfc_suministrador = m.group(1)
        else:
            advertencias.append("Campo no encontrado: rfc_suministrador")

        # --- Receptor RFC ---
        rfc_receptor: str | None = None
        m = RE_RECEPTOR_RFC.search(texto)
        if m:
            rfc_receptor = m.group(1)
        else:
            advertencias.append("Campo no encontrado: rfc_receptor")

        # --- Serie / Folio ---
        serie_folio: str | None = None
        m_serie = RE_SERIE.search(texto)
        m_folio = RE_FOLIO.search(texto)
        if m_serie and m_folio:
            serie_folio = f"{m_serie.group(1)}-{m_folio.group(1)}"
        else:
            advertencias.append("Campo no encontrado: serie_folio")

        # --- UUID CFDI ---
        folio_fiscal: str | None = None
        m = RE_UUID.search(texto)
        if m:
            folio_fiscal = m.group(1).upper()
        else:
            advertencias.append("Campo no encontrado: folio_fiscal")

        # --- Fecha de emisión ---
        fecha_factura: date | None = None
        m = RE_FECHA.search(texto)
        if m:
            partes = m.group(1).split("-")
            fecha_factura = date(int(partes[0]), int(partes[1]), int(partes[2]))
        else:
            advertencias.append("Campo no encontrado: fecha_factura")

        # --- Periodo (ISO dates) ---
        m = RE_PERIODO.search(texto)
        if not m:
            raise ValueError("No se encontró la línea de periodo en el PDF GIN-GIF")

        ini_partes = m.group(1).split("-")
        fin_partes = m.group(2).split("-")
        periodo_inicio = date(int(ini_partes[0]), int(ini_partes[1]), int(ini_partes[2]))
        periodo_fin    = date(int(fin_partes[0]), int(fin_partes[1]), int(fin_partes[2]))

        # --- Consumo ---
        m = RE_CONSUMO.search(texto)
        if not m:
            raise ValueError("No se encontró la línea de consumo KWH en el PDF GIN-GIF")

        consumo_kwh = _clean_decimal(m.group(1)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        precio_unitario_mxn_kwh = Decimal(m.group(2))
        subtotal_consumo = _clean_decimal(m.group(3))

        # --- Subtotal CFDI ---
        subtotal_mxn: Decimal
        m = RE_SUBTOTAL.search(texto)
        if m:
            subtotal_mxn = _clean_decimal(m.group(1))
        else:
            # Fallback: usar importe de la línea de consumo
            subtotal_mxn = subtotal_consumo
            advertencias.append("SUBTOTAL no encontrado; usando importe de línea de consumo")

        # --- IVA ---
        iva_mxn: Decimal | None = None
        m = RE_IVA.search(texto)
        if m:
            iva_mxn = _clean_decimal(m.group(1))
        else:
            advertencias.append("Campo no encontrado: iva_mxn")

        # --- Total ---
        total_mxn: Decimal | None = None
        m = RE_TOTAL.search(texto)
        if m:
            total_mxn = _clean_decimal(m.group(1))
        else:
            advertencias.append("Campo no encontrado: total_mxn")

        return GINInvoice(
            suministrador=suministrador,
            rfc_suministrador=rfc_suministrador,
            rfc_receptor=rfc_receptor,
            serie_folio=serie_folio,
            folio_fiscal=folio_fiscal,
            fecha_factura=fecha_factura,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            rpu=None,   # No presente en formato GIF
            consumo_kwh=consumo_kwh,
            precio_unitario_mxn_kwh=precio_unitario_mxn_kwh,
            subtotal_mxn=subtotal_mxn,
            iva_mxn=iva_mxn,
            total_mxn=total_mxn,
            advertencias=advertencias,
        )
