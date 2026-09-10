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
RE_FACTOR_POTENCIA   = re.compile(r'Factor\s+de\s+Potencia\s+([\d.]+)%', re.IGNORECASE)
RE_PRECIO_MONOCOMICO = re.compile(r'Precio\s+Mon[oó]mico\s*\([^)]*\)\s*\$\s*([\d.]+)', re.IGNORECASE)
RE_TARIFAS_REG       = re.compile(r'Monto\s+de\s+las\s+Tarifas\s+Reguladas\s*\([^)]*\)\s*\$([\d,]+)', re.IGNORECASE)
RE_SERV_COMP         = re.compile(r'Costo\s+por\s+Servicios\s+Complementarios\s*\([^)]*\)\s*\$([\d,]+)', re.IGNORECASE)
RE_PAGO_PROV_CEL     = re.compile(r'Pago\s+Provisional\s+CEL\s*\([^)]*\)\s*\$\s*([\d,]+\.\d{2})', re.IGNORECASE)
RE_REQ_CELS          = re.compile(r'Requerimiento\s+de\s+CELs?\s+estimado\s*\([^)]*\)\s*([\d.]+)', re.IGNORECASE)

# Valores standalone con contexto (el layout de dos columnas separa etiqueta de valor)
RE_ENERGIA_CONTRATADA = re.compile(
    r'([\d,]+)\s*\n\s*Precio\s+de\s+referencia\s+por\s+CELs', re.IGNORECASE,
)
RE_ENERGIA_CONSUMIDA_CTX = re.compile(
    r'([\d,]+)\s*\n\s*Requerimiento\s+de\s+CELs', re.IGNORECASE,
)
RE_DESVIACION = re.compile(
    r'(-?\d+[\.,]\d+)%\s*\n\s*Monto\s+de\s+las\s+Tarifas', re.IGNORECASE,
)
RE_COBRO_NO_CONSUMIDA = re.compile(
    r'\$\s*([\d,]+\.\d{2})\s*\n\s*Costo\s+por\s+Servicios\s+Complementarios', re.IGNORECASE,
)
RE_COBRO_EXCESO_CERO = re.compile(
    r'Costo\s+por\s+Servicios.*?\n\s*\$\s*-\s*\n', re.IGNORECASE | re.DOTALL,
)

# Bloque de cola: secuencia de valores después de "Precio Monómico ... $ X.XXXX"
# Captura: potencia_contratada, precio_mensual_potencia, pago_provisional_potencia,
#          costo_pdp, costo_reliquidaciones, cobro_total
RE_TAIL_BLOCK = re.compile(
    r'Precio\s+Mon[oó]mico\s*\([^)]*\)\s*\$\s*[\d.]+\s*\n'
    r'\s*([\d,]+)\s*\n'               # 1: potencia_contratada
    r'\s*\$\s*([\d.]+)\s*\n'          # 2: precio_mensual_potencia
    r'\s*\$\s*([\d,]+\.\d{2})\s*\n'   # 3: pago_provisional_potencia
    r'\s*\$([\d,]+)\s*\n'             # 4: costo_pdp
    r'\s*\$([\d,]+)\s*\n'             # 5: costo_reliquidaciones
    r'\s*\$\s*([\d,]+\.\d{2})',       # 6: cobro_total
    re.IGNORECASE,
)

# Regex de respaldo para totales de Tabla 1.3 (texto plano)
RE_TOTALES_13 = re.compile(
    r'[Tt]otales\s+'
    r'\$\s*([\d,]+\.\d{2})\s+'   # 1: cargo_energia
    r'\$\s*([\d,]+\.\d{2})\s+'   # 2: cargo_cel
    r'\$\s*([\d,]+\.\d{2})\s+'   # 3: cargo_potencia
    r'\$\s*([\d,]+\.\d{2})\s+'   # 4: cargos_regulados
    r'\$\s*([\d,]+\.\d{2})\s+'   # 5: cargo_servicios_mem
    r'\$\s*([\d,]+\.\d{2})\s+'   # 6: desvios_pdp
    r'\$\s*([\d,]+\.\d{2})\s+'   # 7: cobro_total
    r'\$\s*([\d,]+)',             # 8: reliquidaciones
    re.IGNORECASE,
)

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

        # Bloque de cola: potencia_contratada, precio_mensual_potencia,
        # pago_provisional_potencia, costo_pdp, costo_reliquidaciones, cobro_total
        potencia_contratada_kwmes: Decimal | None = None
        costo_desvios_pdp_mxn: Decimal | None = None
        costo_reliquidaciones_mxn: Decimal | None = None
        cobro_total_mxn: Decimal | None = None

        m = RE_TAIL_BLOCK.search(texto_p1)
        if m:
            potencia_contratada_kwmes = _clean(m.group(1))
            # m.group(2) = precio_mensual_potencia (ya tenemos de PRECIO_POTENCIA)
            # m.group(3) = pago_provisional_potencia (informativo)
            costo_desvios_pdp_mxn    = _clean(m.group(4))
            costo_reliquidaciones_mxn = _clean(m.group(5))
            cobro_total_mxn           = _clean(m.group(6))
        else:
            advertencias.append("Bloque de cola no encontrado; PDP, reliquidaciones y cobro_total desde Tabla 1.3")

        # ── Tabla 1.3 — TOTALES (fuente principal de los 5 componentes) ───────
        cargo_energia_mxn: Decimal | None = None
        cargo_cel_mxn: Decimal | None = None
        cargo_potencia_mxn: Decimal | None = None
        cargos_regulados_mxn: Decimal | None = None
        ajustes_penalizaciones_mxn: Decimal | None = None

        totals_13 = _extract_totals_row(tabla_13)

        if totals_13 and len(totals_13) >= 8:
            # Columnas: [Fecha, Energía, CEL, Potencia, Reg, ServMEM, PDP, (Otras?), Total, Reliq]
            # Buscamos por posición: primeras 8 columnas de datos después de Fecha
            cols = [c for c in totals_13[1:] if c is not None and str(c).strip() not in ("", "None")]
            if len(cols) >= 7:
                cargo_energia_mxn  = _clean(cols[0])
                cargo_cel_mxn      = _clean(cols[1])
                cargo_potencia_mxn = _clean(cols[2])
                t_reg              = _clean(cols[3])   # Tarifas Reguladas (tabla 1.3)
                t_mem              = _clean(cols[4])   # Cargo Servicios MEM
                t_pdp              = _clean(cols[5])   # Desvíos MEM (PDP)
                # Total (Mes vencido) está antes de Reliquidaciones
                t_total            = _clean(cols[6])
                t_reliq            = _clean(cols[7]) if len(cols) > 7 else Decimal("0")

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
        # Si no se obtuvieron desde la tabla, intentar calcular
        if cargos_regulados_mxn is None:
            cargos_regulados_mxn = (tarifas_reguladas_mxn or Decimal("0")) + (cargo_servicios_mem_mxn or Decimal("0"))
        if ajustes_penalizaciones_mxn is None:
            ajustes_penalizaciones_mxn = (costo_desvios_pdp_mxn or Decimal("0")) + (costo_reliquidaciones_mxn or Decimal("0"))

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
        detalle_diario = _build_detalle_diario(tabla_11, tabla_12, tabla_13, advertencias)

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
) -> list[dict]:
    """Fusiona las tres tablas diarias por fecha. Devuelve lista de dicts."""

    rows_11 = _table_data_rows(tabla_11)
    rows_12 = _table_data_rows(tabla_12)
    rows_13 = _table_data_rows(tabla_13)

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
    for row in rows_13:
        fecha_str = (row[0] or "").strip()
        d = _parse_date_dmy(fecha_str)
        if d is None:
            continue
        key = d.isoformat()
        by_date.setdefault(key, {"fecha": key})
        # Columnas: Energía, CEL, Potencia, Regulados, ServMEM, PDP, (Otras), Total, Reliq
        cols = [c for c in row[1:] if c is not None]
        by_date[key]["t13"] = {
            "cargo_energia_mxn":         _s(_clean(cols[0] if len(cols) > 0 else None)),
            "cargo_cel_mxn":             _s(_clean(cols[1] if len(cols) > 1 else None)),
            "cargo_potencia_mxn":        _s(_clean(cols[2] if len(cols) > 2 else None)),
            "cargos_regulados_mxn":      _s(_clean(cols[3] if len(cols) > 3 else None)),
            "cargo_servicios_mem_mxn":   _s(_clean(cols[4] if len(cols) > 4 else None)),
            "desvios_pdp_mxn":           _s(_clean(cols[5] if len(cols) > 5 else None)),
            "total_mes_vencido_mxn":     _s(_clean(cols[6] if len(cols) > 6 else None)),
            "reliquidaciones_cenace_mxn": _s(_clean(cols[7] if len(cols) > 7 else None)),
        }

    return [by_date[k] for k in sorted(by_date)]


def _s(v: Decimal | None) -> str | None:
    """Convierte Decimal a string para almacenamiento JSON. None si None."""
    return str(v) if v is not None else None
