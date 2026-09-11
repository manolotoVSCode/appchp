# parsers/electricidad_calificado/nxe.py
from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from parsers.base import InvoiceParser
from models.nxe_invoice import NXEInvoice

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_MESES_ABREV: dict[str, int] = {
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dic': 12,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(s: str | None) -> Decimal | None:
    """Convierte una celda de texto con $, comas o guión a Decimal. None si falla."""
    if s is None:
        return None
    s = s.strip()
    if s in ("-", "$-", "$ -", "—", ""):
        return Decimal("0")
    s = re.sub(r'[$,\s]', '', s)
    # Signo negativo puede venir como "-$123" → ya quitamos el $
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _clean_req(s: str | None, campo: str, advertencias: list[str]) -> Decimal:
    """Como _clean pero lanza advertencia si falla y devuelve 0."""
    v = _clean(s)
    if v is None:
        advertencias.append(f"Campo no encontrado: {campo}")
        return Decimal("0")
    return v


def _parse_date_dmy(s: str | None) -> date | None:
    """Parsea 'DD/MM/YYYY' → date. None si no encaja."""
    if not s:
        return None
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', s.strip())
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _is_date_row(row: list) -> bool:
    """True si el primer campo de la fila parece una fecha DD/MM/YYYY."""
    return bool(row and re.match(r'\d{2}/\d{2}/\d{4}', (row[0] or "").strip()))


def _is_totals_row(row: list) -> bool:
    """True si el primer campo contiene 'TOTAL' (mayúsculas o minúsculas)."""
    return bool(row and re.search(r'total', (row[0] or ""), re.IGNORECASE))


def _extract_totals_row(table: list[list] | None) -> list | None:
    """Devuelve la primera fila de totales en la tabla, o None."""
    if not table:
        return None
    for row in reversed(table):
        if _is_totals_row(row):
            return row
    return None


def _table_data_rows(table: list[list] | None) -> list[list]:
    """Devuelve solo filas de datos (fecha DD/MM/YYYY) de una tabla pdfplumber."""
    if not table:
        return []
    return [row for row in table if _is_date_row(row)]


def _rows_tabla13_from_text(text: str) -> list[list]:
    """
    Extrae filas de datos de Tabla 1.3 desde texto plano de la página.
    Produce listas de 10 elementos (misma estructura que extract_table),
    con None en la columna basura (índice 7).
    Los valores monetarios pueden tener espacios inyectados (p.ej. "$ 2 ,385,418.75").
    """
    rows: list[list] = []
    for m in _RE_DATE_LINE.finditer(text):
        date_str = m.group(1)
        rest = m.group(2)
        amts = [(s + v) for s, v in _RE_AMT.findall(rest)]
        if len(amts) < 6:
            continue
        # 8 importes en texto → cols 1..6 (energia..pdp), None en col 7, cols 8..9 (total, reliq)
        row: list = [date_str] + amts[:6] + [None]
        if len(amts) >= 7:
            row.append(amts[6])   # col 8: total
        else:
            row.append(None)
        if len(amts) >= 8:
            row.append(amts[7])   # col 9: reliquidaciones
        else:
            row.append(None)
        rows.append(row)
    return rows


def _rows_tabla11_from_text(text: str) -> list[list]:
    """
    Extrae filas de datos de Tabla 1.1 desde texto plano (valores sin signo $).
    Produce listas de 5 elementos: [fecha, pron_mwh, consumo_sin_perd, consumo_con_perd, perd_tec].
    """
    rows: list[list] = []
    for m in _RE_DATE_LINE.finditer(text):
        date_str = m.group(1)
        rest = m.group(2)
        vals = re.findall(r'[\d,]+\.\d+', rest)
        if not vals:
            continue
        rows.append([date_str] + vals)
    return rows


def _rows_tabla12_from_text(text: str) -> list[list]:
    """
    Extrae filas de datos de Tabla 1.2 desde texto plano.
    Produce listas de 7 elementos: [fecha, perd_tec_no_tec, dist, trans, sc_no_mem, oper, gsi].
    Los valores pueden tener $ o ser decimales sin $.
    """
    rows: list[list] = []
    for m in _RE_DATE_LINE.finditer(text):
        date_str = m.group(1)
        rest = m.group(2)
        # Tabla 1.2 puede tener $ o no según la versión del PDF
        if '$' in rest:
            amts = [(s + v) for s, v in _RE_AMT.findall(rest)]
        else:
            amts = re.findall(r'-?[\d,]+\.\d+', rest)
        if not amts:
            continue
        rows.append([date_str] + list(amts))
    return rows


# ---------------------------------------------------------------------------
# Regexes — página 1
# ---------------------------------------------------------------------------

RE_HEADER = re.compile(
    r'FACTURA\s*[-–]\s*([A-Za-záéíóúÁÉÍÓÚ]+)\s+(\d{2})\b',
    re.IGNORECASE,
)
RE_RFC = re.compile(r'RFC:\s*([A-Z]{3}\d{6}[A-Z0-9]{2,3})', re.IGNORECASE)
RE_DOC_REF = re.compile(r'Factura\s+(NXE[^\s\n]+)', re.IGNORECASE)

# Campos etiquetados (etiqueta + valor en la misma línea)
RE_PRECIO_ENERGIA    = re.compile(r'Precio\s+Energ[íi]a\s*\([^)]*\)\s*\$\s*([\d.]+)', re.IGNORECASE)
RE_TIPO_CAMBIO       = re.compile(r'Tipo\s+de\s+Cambio\s+\$\s*([\d.]+)', re.IGNORECASE)
RE_PRECIO_CELS       = re.compile(r'Precio\s+CELS?\s*\([^)]*\)\s*\$\s*([\d.]+)', re.IGNORECASE)
RE_PRECIO_POTENCIA   = re.compile(r'Precio\s+de\s+Potencia\s*\([^)]*\)\s*\$\s*([\d.]+)', re.IGNORECASE)
RE_PRECIO_MONOCOMICO = re.compile(r'Precio\s+Mon[oó]mico\s*\([^)]*\)\s*\$\s*([\d.]+)', re.IGNORECASE)
RE_PAGO_PROV_CEL     = re.compile(r'Pago\s+Provisional\s+CEL\s*\([^)]*\)\s*\$\s*([\d,]+\.\d{2})', re.IGNORECASE)
RE_REQ_CELS          = re.compile(r'Requerimiento\s+de\s+CELs?\s+estimado\s*\([^)]*\)\s*([\d.]+)', re.IGNORECASE)

# Layout de dos columnas: en página 1 las columnas se entrelazan.
# Los siguientes campos tienen el valor en la línea SIGUIENTE a la etiqueta.

# "Factor de Potencia\n93.03%"
RE_FACTOR_POTENCIA = re.compile(r'Factor\s+de\s+Potencia\s*\n\s*([\d.]+)%', re.IGNORECASE)

# "Energía Contratada (KWh) <junk-col-derecha>\n2,608,522 (USD/CEL)"
RE_ENERGIA_CONTRATADA = re.compile(
    r'Energ[íi]a\s+Contratada\s*\([^)]*\)[^\n]*\n\s*([\d,]+)', re.IGNORECASE,
)

# "Energía Consumida (KWh) <junk>\n2,413,311 estimado"
RE_ENERGIA_CONSUMIDA_CTX = re.compile(
    r'Energ[íi]a\s+Consumida\s*\([^)]*\)[^\n]*\n\s*([\d,]+)', re.IGNORECASE,
)

# "Desviación de consumo vs energía contratada $1,197,088\n-7.48% Reguladas (MXN)"
# El porcentaje aparece en la línea siguiente; el monto (tarifas_reguladas) en la misma.
RE_DESVIACION = re.compile(
    r'Desviaci[oó]n\s+de\s+consumo[^\n]*\n\s*(-?\d+[\.,]\d+)%', re.IGNORECASE,
)
RE_TARIFAS_REG = re.compile(
    r'Desviaci[oó]n\s+de\s+consumo[^\n]*\$([\d,]+)', re.IGNORECASE,
)

# "Cobro por energía no consumida (2.5.2) $312,879\n$ 991.07 Complementarios (MXN)"
# El importe del cobro (servicios MEM / cargos regulados) aparece en la misma línea;
# el cobro_energia_no_consumida es el valor antes de "Complementarios" en la línea sig.
RE_SERV_COMP = re.compile(
    r'Cobro\s+por\s+energ[íi]a\s+no\s+consumida[^\n]*\$([\d,]+)', re.IGNORECASE,
)
RE_COBRO_NO_CONSUMIDA = re.compile(
    r'\$\s*([\d,]+\.\d{2})\s+Complementarios', re.IGNORECASE,
)

RE_COBRO_EXCESO_CERO = re.compile(
    r'\$\s*-\s*\n', re.IGNORECASE,
)

# Campos etiquetados en la parte inferior de la página 1 (una sola línea cada uno)
# "Potencia Contratada (KWmes) 2,609"
RE_POTENCIA_CONTRATADA_CTX = re.compile(
    r'Potencia\s+Contratada\s*\([^)]*\)\s+([\d,]+)', re.IGNORECASE,
)
# "Costo de desvíos (PDP) (MXN) $30,840"
RE_COSTO_PDP = re.compile(
    r'Costo\s+de\s+desv[íi]os[^$\n]*\$\s*([\d,]+)', re.IGNORECASE,
)
# "Costo por Reliquidaciones (MXN) $19,720"
RE_COSTO_RELIQ = re.compile(
    r'Costo\s+por\s+Reliquidaciones\s*\([^)]*\)\s*\$\s*([\d,]+)', re.IGNORECASE,
)
# "Cobro total (MXN) $ 5,111,624.74"
RE_COBRO_TOTAL = re.compile(
    r'Cobro\s+total\s*\([^)]*\)\s*\$\s*([\d,]+\.\d{2})', re.IGNORECASE,
)

# Regex de respaldo para totales de Tabla 1.3 (texto plano de página 6)
RE_TOTALES_13 = re.compile(
    # Los valores pueden tener espacios inyectados por el renderizador PDF, p.ej. "$ 2 ,385,418.75"
    # [\d][\d\s,]* captura el número con espacios; _clean() los elimina después.
    r'[Tt]otales\s+'
    r'\$\s*([\d][\d\s,]*\.\d{2})\s+'   # 1: cargo_energia
    r'\$\s*([\d][\d\s,]*\.\d{2})\s+'   # 2: cargo_cel
    r'\$\s*([\d][\d\s,]*\.\d{2})\s+'   # 3: cargo_potencia
    r'\$\s*([\d][\d\s,]*\.\d{2})\s+'   # 4: cargos_regulados
    r'\$\s*([\d][\d\s,]*\.\d{2})\s+'   # 5: cargo_servicios_mem
    r'\$\s*([\d][\d\s,]*\.\d{2})\s+'   # 6: desvios_pdp
    r'\$\s*([\d][\d\s,]*\.\d{2})\s+'   # 7: cobro_total
    r'\$\s*([\d][\d\s,]*(?:\.\d+)?)',   # 8: reliquidaciones (puede venir sin decimales)
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Regexes y helpers para parseo de datos diarios desde texto (pdfplumber
# sólo extrae la cabecera como tabla; los datos vienen del texto plano)
# ---------------------------------------------------------------------------

# Línea con fecha DD/MM/YYYY seguida del resto de la fila
_RE_DATE_LINE = re.compile(r'^(\d{2}/\d{2}/\d{4})\s+(.*)', re.MULTILINE)

# Importe en formato "$ 1,234.56", "$ 1 ,234.56", "-$ 1,234.56", "$ -"
# Captura: (signo, parte_numérica) — signo puede ser '' o '-'
_RE_AMT = re.compile(r'(-?)\$\s*([\d][\d\s,]*(?:\.\d+)?|-)')

# Respaldo consumo desde Tabla 1.1 texto
RE_TOTALES_11 = re.compile(
    r'[Tt]OTALES\s+'
    r'([\d,]+\.\d+)\s+'   # 1: pronostico_mwh
    r'([\d,]+\.\d+)\s+'   # 2: consumo_sin_perdidas_mwh
    r'([\d,]+\.\d+)\s+'   # 3: consumo_con_perdidas_mwh
    r'([\d,]+\.\d+)',      # 4: perdidas_tecnicas_mwh
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

class NXEParser(InvoiceParser):
    """
    Parser para estados de cuenta de NX Energía S.A. de C.V. (RFC: NEN230613SE2).

    No es un CFDI. Extrae:
    - Parámetros contratados (página 1)
    - 5 categorías del resumen (de la fila TOTALES de la Tabla 1.3)
    - Detalle diario de las Tablas 1.1, 1.2 y 1.3 (31 días)
    """

    VERSION = "1.0.0"

    def parse(self, pdf_path: Path) -> NXEInvoice:  # type: ignore[override]
        pdf_path = Path(pdf_path)
        advertencias: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            paginas = pdf.pages
            n = len(paginas)

            texto_p1 = paginas[0].extract_text() or "" if n > 0 else ""
            texto_p3 = paginas[2].extract_text() or "" if n > 2 else ""
            texto_p4 = paginas[3].extract_text() or "" if n > 3 else ""
            texto_p6 = paginas[5].extract_text() or "" if n > 5 else ""

            tabla_11 = paginas[2].extract_table() if n > 2 else None
            tabla_12 = paginas[3].extract_table() if n > 3 else None
            tabla_13 = paginas[5].extract_table() if n > 5 else None

        # ── Suministrador / RFC ───────────────────────────────────────────────
        rfc_suministrador: str | None = None
        m = RE_RFC.search(texto_p1)
        if m:
            rfc_suministrador = m.group(1).upper()
        else:
            advertencias.append("Campo no encontrado: rfc_suministrador")

        suministrador = "NX ENERGIA S.A. DE C.V."

        # ── Documento ref (cabecera de páginas 3+) ────────────────────────────
        documento_ref: str | None = None
        m = RE_DOC_REF.search(texto_p3)
        if m:
            documento_ref = m.group(1).strip()

        # ── Periodo (de "FACTURA - Ago 25") ──────────────────────────────────
        m = RE_HEADER.search(texto_p1)
        if not m:
            raise ValueError("No se encontró la cabecera FACTURA - Mes AA en el PDF NXE")
        mes_str = m.group(1).lower()[:3]
        mes = _MESES_ABREV.get(mes_str)
        if not mes:
            raise ValueError(f"Mes no reconocido en cabecera NXE: {m.group(1)!r}")
        anio = 2000 + int(m.group(2))
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        periodo_inicio = date(anio, mes, 1)
        periodo_fin = date(anio, mes, ultimo_dia)

        # ── Parámetros etiquetados (misma línea) ─────────────────────────────
        def _get(pattern: re.Pattern, campo: str) -> Decimal | None:
            mm = pattern.search(texto_p1)
            if not mm:
                advertencias.append(f"Campo no encontrado: {campo}")
                return None
            return _clean(mm.group(1))

        precio_energia_usd_mwh    = _get(RE_PRECIO_ENERGIA,    "precio_energia_usd_mwh")
        tipo_cambio_mxn_usd       = _get(RE_TIPO_CAMBIO,       "tipo_cambio_mxn_usd")
        precio_cels_usd           = _get(RE_PRECIO_CELS,       "precio_cels_usd")
        precio_potencia_usd_kwmes = _get(RE_PRECIO_POTENCIA,   "precio_potencia_usd_kwmes")
        factor_potencia_pct       = _get(RE_FACTOR_POTENCIA,   "factor_potencia_pct")
        precio_monocomico_mxn_kwh = _get(RE_PRECIO_MONOCOMICO, "precio_monocomico_mxn_kwh")
        tarifas_reguladas_mxn     = _get(RE_TARIFAS_REG,       "tarifas_reguladas_mxn")
        cargo_servicios_mem_mxn   = _get(RE_SERV_COMP,         "cargo_servicios_mem_mxn")

        # ── Valores standalone con contexto ───────────────────────────────────
        energia_contratada_kwh: Decimal | None = None
        m = RE_ENERGIA_CONTRATADA.search(texto_p1)
        if m:
            energia_contratada_kwh = _clean(m.group(1))
        else:
            advertencias.append("Campo no encontrado: energia_contratada_kwh")

        energia_consumida_kwh: Decimal | None = None
        m = RE_ENERGIA_CONSUMIDA_CTX.search(texto_p1)
        if m:
            energia_consumida_kwh = _clean(m.group(1))

        desviacion_pct: Decimal | None = None
        m = RE_DESVIACION.search(texto_p1)
        if m:
            desviacion_pct = _clean(m.group(1).replace(',', '.'))

        cobro_energia_no_consumida_usd: Decimal | None = None
        m = RE_COBRO_NO_CONSUMIDA.search(texto_p1)
        if m:
            cobro_energia_no_consumida_usd = _clean(m.group(1))

        cobro_exceso_consumo_usd: Decimal = Decimal("0")
        if RE_COBRO_EXCESO_CERO.search(texto_p1):
            cobro_exceso_consumo_usd = Decimal("0")

        # Campos individuales de la parte inferior de la página 1
        potencia_contratada_kwmes: Decimal | None = None
        m = RE_POTENCIA_CONTRATADA_CTX.search(texto_p1)
        if m:
            potencia_contratada_kwmes = _clean(m.group(1))
        else:
            advertencias.append("Campo no encontrado: potencia_contratada_kwmes")

        costo_desvios_pdp_mxn: Decimal | None = None
        m = RE_COSTO_PDP.search(texto_p1)
        if m:
            costo_desvios_pdp_mxn = _clean(m.group(1))

        costo_reliquidaciones_mxn: Decimal | None = None
        m = RE_COSTO_RELIQ.search(texto_p1)
        if m:
            costo_reliquidaciones_mxn = _clean(m.group(1))

        cobro_total_mxn: Decimal | None = None
        m = RE_COBRO_TOTAL.search(texto_p1)
        if m:
            cobro_total_mxn = _clean(m.group(1))

        # ── Tabla 1.3 — TOTALES (fuente principal de los 5 componentes) ───────
        cargo_energia_mxn: Decimal | None = None
        cargo_cel_mxn: Decimal | None = None
        cargo_potencia_mxn: Decimal | None = None
        cargos_regulados_mxn: Decimal | None = None
        ajustes_penalizaciones_mxn: Decimal | None = None

        totals_13 = _extract_totals_row(tabla_13)

        # Tabla 1.3 tiene 10 columnas (índices 0-9):
        # [0]=Fecha, [1]=Energía, [2]=CEL, [3]=Potencia, [4]=Cargos Regulados,
        # [5]=Cargo Servicios MEM, [6]=Desvíos MEM (PDP), [7]=columna basura,
        # [8]=Total (Mes vencido), [9]=Reliquidaciones CENACE
        if totals_13 and len(totals_13) >= 9:
            cargo_energia_mxn  = _clean(totals_13[1])
            cargo_cel_mxn      = _clean(totals_13[2])
            cargo_potencia_mxn = _clean(totals_13[3])
            t_reg              = _clean(totals_13[4])
            t_mem              = _clean(totals_13[5])
            t_pdp              = _clean(totals_13[6])
            # totals_13[7] = columna basura — se omite
            t_total            = _clean(totals_13[8]) if len(totals_13) > 8 else None
            t_reliq            = _clean(totals_13[9]) if len(totals_13) > 9 else Decimal("0")

            if cobro_total_mxn is None:
                cobro_total_mxn = t_total
            if costo_desvios_pdp_mxn is None:
                costo_desvios_pdp_mxn = t_pdp
            if costo_reliquidaciones_mxn is None:
                costo_reliquidaciones_mxn = t_reliq or Decimal("0")
            if tarifas_reguladas_mxn is None and t_reg is not None:
                tarifas_reguladas_mxn = t_reg
            if cargo_servicios_mem_mxn is None and t_mem is not None:
                cargo_servicios_mem_mxn = t_mem

            # 5 categorías
            reg_total = (tarifas_reguladas_mxn or Decimal("0")) + (cargo_servicios_mem_mxn or Decimal("0"))
            cargos_regulados_mxn = reg_total
            pdp = costo_desvios_pdp_mxn or Decimal("0")
            reliq = costo_reliquidaciones_mxn or Decimal("0")
            ajustes_penalizaciones_mxn = pdp + reliq

        # Fallback: regex sobre texto plano de página 6
        if cargo_energia_mxn is None:
            m = RE_TOTALES_13.search(texto_p6)
            if m:
                cargo_energia_mxn  = _clean(m.group(1))
                cargo_cel_mxn      = _clean(m.group(2))
                cargo_potencia_mxn = _clean(m.group(3))
                t_reg = _clean(m.group(4))
                t_mem = _clean(m.group(5))
                t_pdp = _clean(m.group(6))
                if cobro_total_mxn is None:
                    cobro_total_mxn = _clean(m.group(7))
                t_reliq = _clean(m.group(8)) or Decimal("0")
                if costo_desvios_pdp_mxn is None:
                    costo_desvios_pdp_mxn = t_pdp
                if costo_reliquidaciones_mxn is None:
                    costo_reliquidaciones_mxn = t_reliq
                if tarifas_reguladas_mxn is None:
                    tarifas_reguladas_mxn = t_reg
                if cargo_servicios_mem_mxn is None:
                    cargo_servicios_mem_mxn = t_mem
                cargos_regulados_mxn = (tarifas_reguladas_mxn or Decimal("0")) + (cargo_servicios_mem_mxn or Decimal("0"))
                ajustes_penalizaciones_mxn = (costo_desvios_pdp_mxn or Decimal("0")) + (costo_reliquidaciones_mxn or Decimal("0"))
            else:
                advertencias.append("Tabla 1.3 TOTALES no encontrada — componentes del resumen no disponibles")

        # ── energia_consumida_kwh desde Tabla 1.1 (fallback) ─────────────────
        if energia_consumida_kwh is None:
            totals_11 = _extract_totals_row(tabla_11)
            if totals_11 and len(totals_11) >= 3:
                cols_11 = [c for c in totals_11[1:] if c is not None and str(c).strip() not in ("", "None")]
                if len(cols_11) >= 2:
                    # col 0 = pronóstico, col 1 = consumo_sin_perdidas (MWh)
                    v = _clean(cols_11[1])
                    if v is not None:
                        energia_consumida_kwh = (v * 1000).quantize(Decimal("1"))
            if energia_consumida_kwh is None:
                # Segundo fallback: regex en texto Tabla 1.1
                m = RE_TOTALES_11.search(texto_p3)
                if m:
                    v = _clean(m.group(2))
                    if v is not None:
                        energia_consumida_kwh = (v * 1000).quantize(Decimal("1"))
            if energia_consumida_kwh is None:
                raise ValueError("No se pudo extraer energia_consumida_kwh del PDF NXE")

        if cobro_total_mxn is None:
            raise ValueError("No se pudo extraer cobro_total_mxn del PDF NXE")

        # ── 5 categorías: cálculo final ───────────────────────────────────────
        if cargos_regulados_mxn is None:
            cargos_regulados_mxn = (tarifas_reguladas_mxn or Decimal("0")) + (cargo_servicios_mem_mxn or Decimal("0"))

        # ajustes incluye los cargos en USD convertidos a MXN (cobro_energia_no_consumida,
        # cobro_exceso_consumo) más los cargos MXN directos (PDP, reliquidaciones).
        # Documentado en CLAUDE.md: "Detalle dentro de ajustes".
        _cobro_no_consumida_mxn = (
            cobro_energia_no_consumida_usd * tipo_cambio_mxn_usd
            if cobro_energia_no_consumida_usd is not None and tipo_cambio_mxn_usd is not None
            else Decimal("0")
        )
        _cobro_exceso_mxn = (
            cobro_exceso_consumo_usd * tipo_cambio_mxn_usd
            if cobro_exceso_consumo_usd is not None and tipo_cambio_mxn_usd is not None
            else Decimal("0")
        )
        ajustes_penalizaciones_mxn = (
            _cobro_no_consumida_mxn
            + _cobro_exceso_mxn
            + (costo_desvios_pdp_mxn or Decimal("0"))
            + (costo_reliquidaciones_mxn or Decimal("0"))
        )

        # ── Validación de 5 categorías vs cobro_total ─────────────────────────
        if all(v is not None for v in [cargo_energia_mxn, cargo_potencia_mxn, cargo_cel_mxn,
                                        cargos_regulados_mxn, ajustes_penalizaciones_mxn]):
            suma = (cargo_energia_mxn + cargo_potencia_mxn + cargo_cel_mxn  # type: ignore[operator]
                    + cargos_regulados_mxn + ajustes_penalizaciones_mxn)    # type: ignore[operator]
            diff = abs(suma - cobro_total_mxn)
            if diff > Decimal("100"):
                advertencias.append(
                    f"Diferencia entre suma de 5 categorías ({suma:,.2f}) y "
                    f"cobro_total ({cobro_total_mxn:,.2f}): {diff:,.2f} MXN"
                )

        # ── Detalle diario ────────────────────────────────────────────────────
        detalle_diario = _build_detalle_diario(
            tabla_11, tabla_12, tabla_13, advertencias,
            texto_p3=texto_p3, texto_p4=texto_p4, texto_p6=texto_p6,
        )

        return NXEInvoice(
            documento_ref=documento_ref,
            suministrador=suministrador,
            rfc_suministrador=rfc_suministrador,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            precio_energia_usd_mwh=precio_energia_usd_mwh,
            tipo_cambio_mxn_usd=tipo_cambio_mxn_usd,
            precio_cels_usd=precio_cels_usd,
            precio_potencia_usd_kwmes=precio_potencia_usd_kwmes,
            factor_potencia_pct=factor_potencia_pct,
            energia_contratada_kwh=energia_contratada_kwh,
            potencia_contratada_kwmes=potencia_contratada_kwmes,
            energia_consumida_kwh=energia_consumida_kwh,
            desviacion_pct=desviacion_pct,
            precio_monocomico_mxn_kwh=precio_monocomico_mxn_kwh,
            cargo_energia_mxn=cargo_energia_mxn,
            cargo_potencia_mxn=cargo_potencia_mxn,
            cargo_cel_mxn=cargo_cel_mxn,
            cargos_regulados_mxn=cargos_regulados_mxn,
            ajustes_penalizaciones_mxn=ajustes_penalizaciones_mxn,
            cobro_total_mxn=cobro_total_mxn,
            cobro_energia_no_consumida_usd=cobro_energia_no_consumida_usd,
            cobro_exceso_consumo_usd=cobro_exceso_consumo_usd,
            costo_desvios_pdp_mxn=costo_desvios_pdp_mxn,
            costo_reliquidaciones_mxn=costo_reliquidaciones_mxn,
            tarifas_reguladas_mxn=tarifas_reguladas_mxn,
            cargo_servicios_mem_mxn=cargo_servicios_mem_mxn,
            detalle_diario=detalle_diario,
            advertencias=advertencias,
            parser_version=NXEParser.VERSION,
        )


# ---------------------------------------------------------------------------
# Construcción del detalle diario
# ---------------------------------------------------------------------------

def _build_detalle_diario(
    tabla_11: list[list] | None,
    tabla_12: list[list] | None,
    tabla_13: list[list] | None,
    advertencias: list[str],
    *,
    texto_p3: str = "",
    texto_p4: str = "",
    texto_p6: str = "",
) -> list[dict]:
    """Fusiona las tres tablas diarias por fecha. Devuelve lista de dicts.

    Si pdfplumber sólo extrae la cabecera como tabla (sin filas de datos),
    recurre al texto plano de la página para extraer las filas manualmente.
    """

    rows_11 = _table_data_rows(tabla_11) or _rows_tabla11_from_text(texto_p3)
    rows_12 = _table_data_rows(tabla_12) or _rows_tabla12_from_text(texto_p4)
    rows_13 = _table_data_rows(tabla_13) or _rows_tabla13_from_text(texto_p6)

    if not rows_11 and not rows_13:
        advertencias.append("Tablas de detalle diario no encontradas o vacías")
        return []

    # Índice por fecha (string DD/MM/YYYY como clave)
    by_date: dict[str, dict] = {}

    # Tabla 1.1: Pronósticos y consumos
    for row in rows_11:
        fecha_str = (row[0] or "").strip()
        d = _parse_date_dmy(fecha_str)
        if d is None:
            continue
        key = d.isoformat()
        by_date.setdefault(key, {"fecha": key})
        by_date[key]["t11"] = {
            "pronostico_mwh":           _s(_clean(row[1] if len(row) > 1 else None)),
            "consumo_sin_perdidas_mwh": _s(_clean(row[2] if len(row) > 2 else None)),
            "consumo_con_perdidas_mwh": _s(_clean(row[3] if len(row) > 3 else None)),
            "perdidas_tecnicas_mwh":    _s(_clean(row[4] if len(row) > 4 else None)),
        }

    # Tabla 1.2: Costos regulados MXN
    for row in rows_12:
        fecha_str = (row[0] or "").strip()
        d = _parse_date_dmy(fecha_str)
        if d is None:
            continue
        key = d.isoformat()
        by_date.setdefault(key, {"fecha": key})
        by_date[key]["t12"] = {
            "perdidas_tecnicas_no_tecnicas_mxn": _s(_clean(row[1] if len(row) > 1 else None)),
            "distribucion_mxn":                  _s(_clean(row[2] if len(row) > 2 else None)),
            "transmision_mxn":                   _s(_clean(row[3] if len(row) > 3 else None)),
            "sc_no_mem_mxn":                     _s(_clean(row[4] if len(row) > 4 else None)),
            "operacion_mxn":                     _s(_clean(row[5] if len(row) > 5 else None)),
            "gsi_mxn":                           _s(_clean(row[6] if len(row) > 6 else None)),
        }

    # Tabla 1.3: Monto a liquidar
    # Columnas fijas: [0]=Fecha, [1]=Energía, [2]=CEL, [3]=Potencia, [4]=Regulados,
    # [5]=ServMEM, [6]=PDP, [7]=basura, [8]=Total, [9]=Reliquidaciones
    for row in rows_13:
        fecha_str = (row[0] or "").strip()
        d = _parse_date_dmy(fecha_str)
        if d is None:
            continue
        key = d.isoformat()
        by_date.setdefault(key, {"fecha": key})
        by_date[key]["t13"] = {
            "cargo_energia_mxn":          _s(_clean(row[1] if len(row) > 1 else None)),
            "cargo_cel_mxn":              _s(_clean(row[2] if len(row) > 2 else None)),
            "cargo_potencia_mxn":         _s(_clean(row[3] if len(row) > 3 else None)),
            "cargos_regulados_mxn":       _s(_clean(row[4] if len(row) > 4 else None)),
            "cargo_servicios_mem_mxn":    _s(_clean(row[5] if len(row) > 5 else None)),
            "desvios_pdp_mxn":            _s(_clean(row[6] if len(row) > 6 else None)),
            # row[7] = columna basura — se omite
            "total_mes_vencido_mxn":      _s(_clean(row[8] if len(row) > 8 else None)),
            "reliquidaciones_cenace_mxn": _s(_clean(row[9] if len(row) > 9 else None)),
        }

    return [by_date[k] for k in sorted(by_date)]


def _s(v: Decimal | None) -> str | None:
    """Convierte Decimal a string para almacenamiento JSON. None si None."""
    return str(v) if v is not None else None
