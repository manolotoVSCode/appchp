from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pdfplumber

from parsers.base import InvoiceParser

# ---------------------------------------------------------------------------
# Mapa de meses en español
# ---------------------------------------------------------------------------
_MESES: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# Emisor RFC — único "RFC:" en el documento corresponde al emisor
RE_EMISOR_RFC = re.compile(r'RFC:\s*([A-Z&]{3,4}\d{6}[A-Z0-9]{3})')

# Emisor nombre — captura todo hasta el fin de línea para no truncar razón social
RE_EMISOR_NOMBRE = re.compile(r'^(GENERACION\s+INDUSTRIAL[^\n]*)', re.IGNORECASE | re.MULTILINE)

# Receptor RFC — aparece al inicio de línea seguido de " Fecha" (sin prefijo "RFC:")
# Línea ejemplo: "ITI170630377 Fecha 2024-10-09T00:00:00"
RE_RECEPTOR_RFC = re.compile(r'^([A-Z&]{3,4}\d{6}[A-Z0-9]{3})\s+Fecha\b', re.MULTILINE)

# Serie-Folio: "Serie - Folio GI01 01312"
RE_SERIE_FOLIO = re.compile(r'Serie\s*-\s*Folio\s+([A-Z]{2,4}\d{2})\s+(\d{4,})', re.IGNORECASE)

# UUID CFDI — puede aparecer partido en dos líneas; se normaliza el texto
RE_UUID = re.compile(
    r'([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})',
    re.IGNORECASE,
)

# Fecha de emisión — el RFC del receptor precede a "Fecha" en la misma línea;
# anclar con el RFC receptor para no colisionar con otras fechas del documento.
RE_FECHA = re.compile(
    r'[A-Z&]{3,4}\d{6}[A-Z0-9]{3}\s+Fecha\s+(\d{4}-\d{2}-\d{2})T',
    re.IGNORECASE,
)

# Periodo: "Energía del 01 al 30 de septiembre del 2024 RPU 52200951158"
RE_PERIODO = re.compile(
    r'Energ[íi]a\s+del\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+(\w+)\s+del\s+(\d{4})\s+RPU\s+(\S+)',
    re.IGNORECASE,
)

# Consumo: "83101800 / FACT-66 2,060,135.000000 KWH Kilowatt hora 2.030600 0.00 4,183,310.13"
RE_CONSUMO = re.compile(
    r'FACT-\d+\s+([\d,]+\.?\d*)\s+KWH\s+Kilowatt\s+hora\s+([\d.]+)\s+[\d.]+\s+([\d,]+\.\d{2})',
    re.IGNORECASE,
)

# IVA — línea limpia del resumen: "IVA 669,329.62"
# (distinto de la línea de tabla de impuestos que termina en .620000)
RE_IVA = re.compile(r'^IVA\s+([\d,]+\.\d{2})\s*$', re.MULTILINE)

# Total
RE_TOTAL = re.compile(r'^Total\s+([\d,]+\.\d{2})\s*$', re.MULTILINE)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class GINInvoice:
    # CFDI metadata
    suministrador: str | None
    rfc_suministrador: str | None
    rfc_receptor: str | None
    serie_folio: str | None
    folio_fiscal: str | None

    # Periodo
    fecha_factura: date | None
    periodo_inicio: date
    periodo_fin: date
    rpu: str | None

    # Energía y precios
    consumo_kwh: Decimal
    precio_unitario_mxn_kwh: Decimal
    subtotal_mxn: Decimal
    iva_mxn: Decimal | None
    total_mxn: Decimal | None

    advertencias: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _clean_decimal(s: str) -> Decimal:
    """Convierte string con comas a Decimal."""
    return Decimal(s.replace(",", ""))


class GINParser(InvoiceParser):
    """Parser para facturas de electricidad calificada — emisor GIN (Generación Industrial)."""

    VERSION = "1.0.0"

    def parse(self, pdf_path: Path) -> GINInvoice:
        pdf_path = Path(pdf_path)
        advertencias: list[str] = []

        # --- Extracción de texto ---
        with pdfplumber.open(pdf_path) as pdf:
            paginas = [p.extract_text() or "" for p in pdf.pages]

        texto = "\n".join(paginas)

        # Normalizar UUID partido en dos líneas.
        # Patrón A: "XXXX-XXXX-XXXX-XXXX-\nXXXXXXXXXXXX"
        texto = re.sub(
            r'([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-)\n([A-F0-9]{12})',
            r'\1\2',
            texto,
            flags=re.IGNORECASE,
        )
        # Patrón B: "XXXX-XXXX-XXXX-XXXX- <cert>\nXXXXXXXXXXXX"
        # (el sufijo de 12 hex en la línea siguiente)
        texto = re.sub(
            r'([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-)\s+\S+\n([A-F0-9]{12})',
            r'\1\2',
            texto,
            flags=re.IGNORECASE,
        )

        # --- Emisor nombre ---
        m_nombre = RE_EMISOR_NOMBRE.search(texto)
        suministrador: str | None = None
        if m_nombre:
            suministrador = m_nombre.group(1).strip().upper()
            # Normalizar espacios múltiples internos
            suministrador = re.sub(r'\s+', ' ', suministrador)
        else:
            advertencias.append("Campo no encontrado: suministrador")

        # --- Emisor RFC ---
        m_emisor_rfc = RE_EMISOR_RFC.search(texto)
        rfc_suministrador: str | None = None
        if m_emisor_rfc:
            rfc_suministrador = m_emisor_rfc.group(1)
        else:
            advertencias.append("Campo no encontrado: rfc_suministrador")

        # --- Receptor RFC ---
        # El RFC del receptor aparece al inicio de línea seguido de " Fecha"
        rfc_receptor: str | None = None
        m_rfc_rec = RE_RECEPTOR_RFC.search(texto)
        if m_rfc_rec:
            rfc_receptor = m_rfc_rec.group(1)
        else:
            advertencias.append("Campo no encontrado: rfc_receptor")

        # --- Serie / Folio ---
        serie_folio: str | None = None
        m_sf = RE_SERIE_FOLIO.search(texto)
        if m_sf:
            serie_folio = f"{m_sf.group(1)} {m_sf.group(2)}"
        else:
            advertencias.append("Campo no encontrado: serie_folio")

        # --- UUID CFDI ---
        folio_fiscal: str | None = None
        m_uuid = RE_UUID.search(texto)
        if m_uuid:
            folio_fiscal = m_uuid.group(1).upper()
        else:
            advertencias.append("Campo no encontrado: folio_fiscal")

        # --- Fecha de emisión ---
        fecha_factura: date | None = None
        m_fecha = RE_FECHA.search(texto)
        if m_fecha:
            partes = m_fecha.group(1).split("-")
            fecha_factura = date(int(partes[0]), int(partes[1]), int(partes[2]))
        else:
            advertencias.append("Campo no encontrado: fecha_factura")

        # --- Periodo y RPU ---
        m_periodo = RE_PERIODO.search(texto)
        if not m_periodo:
            raise ValueError("No se encontró la línea de periodo/RPU en el PDF GIN")

        dia_ini = int(m_periodo.group(1))
        dia_fin = int(m_periodo.group(2))
        mes_str = m_periodo.group(3).lower()
        anio = int(m_periodo.group(4))
        rpu = m_periodo.group(5)

        mes = _MESES.get(mes_str)
        if mes is None:
            raise ValueError(f"Mes desconocido en periodo: '{mes_str}'")

        periodo_inicio = date(anio, mes, dia_ini)
        periodo_fin = date(anio, mes, dia_fin)

        # --- Consumo ---
        m_consumo = RE_CONSUMO.search(texto)
        if not m_consumo:
            raise ValueError("No se encontró la línea de consumo KWH en el PDF GIN")

        consumo_raw = m_consumo.group(1)       # e.g. "2,060,135.000000"
        precio_raw = m_consumo.group(2)         # e.g. "2.030600"
        subtotal_raw = m_consumo.group(3)       # e.g. "4,183,310.13"

        # Consumo: redondear al entero más cercano preservando fracciones de kWh
        consumo_kwh = _clean_decimal(consumo_raw).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        precio_unitario_mxn_kwh = Decimal(precio_raw)
        subtotal_mxn = _clean_decimal(subtotal_raw)

        # --- IVA ---
        iva_mxn: Decimal | None = None
        m_iva = RE_IVA.search(texto)
        if m_iva:
            iva_mxn = _clean_decimal(m_iva.group(1))
        else:
            advertencias.append("Campo no encontrado: iva_mxn")

        # --- Total ---
        total_mxn: Decimal | None = None
        m_total = RE_TOTAL.search(texto)
        if m_total:
            total_mxn = _clean_decimal(m_total.group(1))
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
            rpu=rpu,
            consumo_kwh=consumo_kwh,
            precio_unitario_mxn_kwh=precio_unitario_mxn_kwh,
            subtotal_mxn=subtotal_mxn,
            iva_mxn=iva_mxn,
            total_mxn=total_mxn,
            advertencias=advertencias,
        )
