from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import re

import pdfplumber

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from parsers.cfe.base import CFEParser

# Regex calibrados al texto real de pdfplumber
RE_SERVICIO    = re.compile(r'NO\.?\s*DE\s*SERVICIO\s*:\s*(\d+)')
RE_RMU         = re.compile(r'RMU\s*:\s*(.+?)(?:\n|$)')
RE_PERIODO     = re.compile(
    r'PERIODO\s+FACTURADO\s*:\s*(\d{1,2}\s+\w+\s+\d{2,4})\s*-\s*(\d{1,2}\s+\w+\s+\d{2,4})',
    re.IGNORECASE,
)
RE_TARIFA      = re.compile(r'TARIFA:\s*(\w+)')
RE_MEDIDOR     = re.compile(r'NO\.?\s*MEDIDOR:\s*(\S+)')
RE_MULTIPLIC   = re.compile(r'MULTIPLICADOR:\s*(\d+)')
RE_CARGA       = re.compile(r'CARGA\s+CONECTADA\s+kW:\s*(\d+)')
RE_DEMANDA_C   = re.compile(r'DEMANDA\s+CONTRATADA\s+kW:\s*(\d+)')
RE_FECHA_LIMITE= re.compile(r'FECHA\s+L[IÍ]MITE\s+DE\s+PAGO:\s*(\d{1,2}\s+\w+\s+\d{2,4})', re.IGNORECASE)
RE_FECHA_IMP   = re.compile(r'(\d{2}\s+\w+\s+\d{4})\s+\d{2}:\d{2}:\d{2}')

# Consumo — el valor está directamente después del nombre de periodo
RE_KWH_BASE    = re.compile(r'kWh\s+base\s+([\d,]+)')
RE_KWH_INTER   = re.compile(r'kWh\s+intermedia\s+([\d,]+)')
RE_KWH_PUNTA   = re.compile(r'kWh\s+punta\s+([\d,]+)')
RE_KW_BASE     = re.compile(r'kW\s+base\s+([\d,]+)')
RE_KW_INTER    = re.compile(r'kW\s+intermedia\s+([\d,]+)')
RE_KW_PUNTA    = re.compile(r'kW\s+punta\s+([\d,]+)')
RE_KW_MAX      = re.compile(r'[Kk][Ww][Mm]ax\s+([\d,]+)')
RE_KVARH       = re.compile(r'kVArh\s+([\d,]+)')
RE_FP          = re.compile(r'Factor\s+de\s+potencia\s+%\s+([\d.]+)')

# MEM — 4 valores numéricos por fila. SCnMEM tiene (¹) después del nombre.
RE_MEM_SUMINISTRO  = re.compile(r'Suministro\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_DISTRIBUCION= re.compile(r'Distribuci[oó]n\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_TRANSMISION = re.compile(r'Transmisi[oó]n\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_CENACE      = re.compile(r'CENACE\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_GEN_B       = re.compile(r'Generaci[oó]n\s+B\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_GEN_I       = re.compile(r'Generaci[oó]n\s+I\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_GEN_P       = re.compile(r'Generaci[oó]n\s+P\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
RE_MEM_CAPACIDAD   = re.compile(r'Capacidad\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')
# SCnMEM(¹)/(1) — anotación superscript o paréntesis antes de los valores
RE_MEM_SCNMEM      = re.compile(r'SCnMEM\s*(?:\([^)]+\))?\s*([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)')

# Notación 2023: superíndice ³ (ej. "Cargo Fijo³ 362.60")
# Notación 2024: paréntesis (ej. "Cargo Fijo(3) 362.60")
_SUPERSCRIPT = r'(?:\s*(?:[¹²³]|\(\d\)))?\s+'
RE_CARGO_FIJO      = re.compile(r'Cargo\s+Fijo' + _SUPERSCRIPT + r'([\d,]+\.?\d*)')
RE_ENERGIA         = re.compile(r'Energ[íi]a\s+([\d,]+\.?\d*)')
RE_CARGO_FP        = re.compile(r'Cargo\s+Factor\s+de\s+Potencia' + _SUPERSCRIPT + r'([\d,]+\.?\d*)')
RE_SUBTOTAL        = re.compile(r'Subtotal\s+([\d,]+\.?\d*)')
RE_IVA             = re.compile(r'IVA\s+16\s*%\s+([\d,]+\.?\d*)')
RE_FACT_PERIODO    = re.compile(r'Facturaci[oó]n\s+del\s+Periodo\s+([\d,]+\.?\d*)')
RE_DAP             = re.compile(r'Derecho\s+de\s+Alumbrado\s+P[úu]blico' + _SUPERSCRIPT + r'([\d,]+\.?\d*)')
RE_CREDITO         = re.compile(r'Cr[eé]dito\s+Aplic\.\s*Fac\.' + _SUPERSCRIPT + r'([\d,]+\.?\d*)-')
RE_ADEUDO          = re.compile(r'Adeudo\s+Anterior\s+([\d,]+\.?\d*)')
RE_SU_PAGO         = re.compile(r'Su\s+Pago\s+-?\s*([\d,]+\.?\d*)')
# 2023: "Total $1,126,771.85" mid-line (requires $); 2024: "Total 4,743,510.51" at line start
RE_TOTAL_CON_SIGNO = re.compile(r'Total\s+\$([\d,]+\.\d{2})')
RE_TOTAL_SIN_SIGNO = re.compile(r'^Total\s+([\d,]+\.\d{2})', re.MULTILINE)

# CFDI datos (página 2)
RE_RFC_RECEPTOR    = re.compile(r'RFC:\s*([A-Z&]{3,4}\d{6}[A-Z0-9]{3})')
RE_SERIE           = re.compile(r'Serie:\s*(\w+)')
RE_FOLIO           = re.compile(r'Folio:\s*(\d+)')
RE_UUID            = re.compile(
    r'Folio\s+Fiscal:\s*([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})',
    re.IGNORECASE,
)

# Nombre cliente: está en la misma línea que "TOTAL A PAGAR:"
RE_NOMBRE_CLIENTE  = re.compile(r'^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+?)\s+TOTAL\s+A\s+PAGAR', re.MULTILINE)


def _extract_total(texto: str, advertencias: list) -> str | None:
    """Extrae el total de la factura.

    2023: 'Total $1,126,771.85' aparece a mitad de línea — requiere '$'.
    2024: 'Total 4,743,510.51' aparece al inicio de línea — sin '$'.
    """
    m = RE_TOTAL_CON_SIGNO.search(texto)
    if m:
        return m.group(1)
    m = RE_TOTAL_SIN_SIGNO.search(texto)
    if m:
        return m.group(1)
    advertencias.append("Campo no encontrado: total")
    return None


def _req(texto: str, patron: re.Pattern, nombre: str, advertencias: list) -> str | None:
    m = patron.search(texto)
    if m:
        return m.group(1).strip()
    advertencias.append(f"Campo no encontrado: {nombre}")
    return None


def _parse_mem_row(texto: str, patron: re.Pattern, nombre: str, advertencias: list) -> MEMComponente:
    m = patron.search(texto)
    if not m:
        advertencias.append(f"Componente MEM no encontrado: {nombre}")
        return MEMComponente(nombre, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
    vals = [CFEParser._parse_decimal(m.group(i)) for i in range(1, 5)]
    return MEMComponente(
        nombre=nombre,
        cargo_fijo_mxn=vals[0],
        cargo_demanda_mxn=vals[1],
        cargo_energia_mxn=vals[2],
        importe_mxn=vals[3],
    )


class GDMTHParser(CFEParser):
    """Parser para tarifa CFE GDMTH (Gran Demanda Media Tensión Horaria)."""

    def parse(self, pdf_path: Path) -> CFEInvoice:
        pdf_path = Path(pdf_path)
        advertencias: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            texto_p1 = pdf.pages[0].extract_text() or ""
            texto_p2 = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ""

        texto = texto_p1 + "\n" + texto_p2

        # --- Nombre del cliente ---
        m_nombre = RE_NOMBRE_CLIENTE.search(texto_p1)
        nombre_cliente = m_nombre.group(1).strip() if m_nombre else ""
        if not nombre_cliente:
            advertencias.append("Campo no encontrado: nombre_cliente")

        # --- Metadata ---
        tarifa_raw    = _req(texto, RE_TARIFA,    "tarifa",            advertencias)
        servicio      = _req(texto, RE_SERVICIO,  "numero_servicio",   advertencias) or ""
        rmu           = _req(texto, RE_RMU,       "rmu",               advertencias)
        medidor       = _req(texto, RE_MEDIDOR,   "numero_medidor",    advertencias) or ""
        multiplic_raw = _req(texto, RE_MULTIPLIC, "multiplicador",     advertencias)
        carga_raw     = _req(texto, RE_CARGA,     "carga_conectada_kw",advertencias)
        demanda_c_raw = _req(texto, RE_DEMANDA_C, "demanda_contratada_kw", advertencias)

        m_periodo = RE_PERIODO.search(texto)
        if m_periodo:
            periodo_inicio = CFEParser._parse_fecha_es(m_periodo.group(1))
            periodo_fin    = CFEParser._parse_fecha_es(m_periodo.group(2))
        else:
            from datetime import date as _date
            advertencias.append("Campo no encontrado: PERIODO FACTURADO")
            periodo_inicio = periodo_fin = _date.today()

        fecha_limite_raw = _req(texto, RE_FECHA_LIMITE, "fecha_limite_pago", advertencias)
        fecha_limite = CFEParser._parse_fecha_es(fecha_limite_raw) if fecha_limite_raw else periodo_fin

        # Fecha de emisión: "04 DEC 2023 14:59:38" (mes en inglés)
        MESES_EN = {"JAN": "ENE", "FEB": "FEB", "MAR": "MAR", "APR": "ABR",
                    "MAY": "MAY", "JUN": "JUN", "JUL": "JUL", "AUG": "AGO",
                    "SEP": "SEP", "OCT": "OCT", "NOV": "NOV", "DEC": "DIC"}
        m_imp = RE_FECHA_IMP.search(texto_p1)
        fecha_emision = periodo_fin
        if m_imp:
            partes = m_imp.group(1).split()
            if len(partes) == 3:
                mes_es = MESES_EN.get(partes[1].upper(), partes[1])
                try:
                    fecha_emision = CFEParser._parse_fecha_es(f"{partes[0]} {mes_es} {partes[2]}")
                except ValueError:
                    advertencias.append(f"No se pudo parsear fecha de emisión: {m_imp.group(1)}")

        # CFDI datos (página 2)
        rfc_cliente = _req(texto_p2, RE_RFC_RECEPTOR, "rfc_cliente", advertencias) or ""
        serie       = _req(texto_p2, RE_SERIE,        "serie",       advertencias)
        folio       = _req(texto_p2, RE_FOLIO,        "folio",       advertencias) or ""
        uuid_cfdi   = _req(texto_p2, RE_UUID,         "uuid_cfdi",   advertencias)

        # --- Consumo ---
        def _d(raw: str | None) -> Decimal:
            return CFEParser._parse_decimal(raw) if raw else Decimal("0")

        kwh_base  = _d(_req(texto, RE_KWH_BASE,  "kWh base",      advertencias))
        kwh_inter = _d(_req(texto, RE_KWH_INTER, "kWh intermedia",advertencias))
        kwh_punta = _d(_req(texto, RE_KWH_PUNTA, "kWh punta",     advertencias))
        kw_base   = _d(_req(texto, RE_KW_BASE,   "kW base",       advertencias))
        kw_inter  = _d(_req(texto, RE_KW_INTER,  "kW intermedia", advertencias))
        kw_punta  = _d(_req(texto, RE_KW_PUNTA,  "kW punta",      advertencias))

        # --- MEM ---
        componentes = [
            _parse_mem_row(texto, RE_MEM_SUMINISTRO,   "Suministro",   advertencias),
            _parse_mem_row(texto, RE_MEM_DISTRIBUCION, "Distribución", advertencias),
            _parse_mem_row(texto, RE_MEM_TRANSMISION,  "Transmisión",  advertencias),
            _parse_mem_row(texto, RE_MEM_CENACE,       "CENACE",       advertencias),
            _parse_mem_row(texto, RE_MEM_GEN_B,        "Generación B", advertencias),
            _parse_mem_row(texto, RE_MEM_GEN_I,        "Generación I", advertencias),
            _parse_mem_row(texto, RE_MEM_GEN_P,        "Generación P", advertencias),
            _parse_mem_row(texto, RE_MEM_CAPACIDAD,    "Capacidad",    advertencias),
            _parse_mem_row(texto, RE_MEM_SCNMEM,       "SCnMEM",       advertencias),
        ]

        # --- Costos unitarios derivados por periodo ---
        gen_b       = next(c for c in componentes if c.nombre == "Generación B")
        gen_i       = next(c for c in componentes if c.nombre == "Generación I")
        gen_p       = next(c for c in componentes if c.nombre == "Generación P")
        transmision = next(c for c in componentes if c.nombre == "Transmisión")
        cenace      = next(c for c in componentes if c.nombre == "CENACE")
        scnmem      = next(c for c in componentes if c.nombre == "SCnMEM")

        kwh_total = kwh_base + kwh_inter + kwh_punta
        shared_kwh = (
            (transmision.importe_mxn + cenace.importe_mxn + scnmem.importe_mxn) / kwh_total
            if kwh_total > 0 else Decimal("0")
        )

        prec = Decimal("0.000001")
        costo_base  = (gen_b.importe_mxn / kwh_base  + shared_kwh).quantize(prec) if kwh_base  > 0 else Decimal("0")
        costo_inter = (gen_i.importe_mxn / kwh_inter + shared_kwh).quantize(prec) if kwh_inter > 0 else Decimal("0")
        costo_punta = (gen_p.importe_mxn / kwh_punta + shared_kwh).quantize(prec) if kwh_punta > 0 else Decimal("0")

        periodos = [
            CFEConsumoHorario("base",       kwh_base,  kw_base,  costo_base),
            CFEConsumoHorario("intermedio", kwh_inter, kw_inter, costo_inter),
            CFEConsumoHorario("punta",      kwh_punta, kw_punta, costo_punta),
        ]

        # --- Financiero ---
        # 2023: "Credito Aplic. Fac.(3) 123,456.78-"  → negativo
        # 2024: "Adeudo Anterior X" / "Su Pago -X"   → net = adeudo - pago
        credito_raw = RE_CREDITO.search(texto)
        if credito_raw:
            credito = -_d(credito_raw.group(1))
        else:
            adeudo_raw = RE_ADEUDO.search(texto)
            pago_raw   = RE_SU_PAGO.search(texto)
            if adeudo_raw and pago_raw:
                credito = _d(adeudo_raw.group(1)) - _d(pago_raw.group(1))
            elif adeudo_raw:
                credito = _d(adeudo_raw.group(1))
            else:
                credito = Decimal("0")

        return CFEInvoice(
            uuid_cfdi=uuid_cfdi,
            folio=folio,
            serie=serie,
            fecha_emision=fecha_emision,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            fecha_limite_pago=fecha_limite,
            nombre_cliente=nombre_cliente,
            rfc_cliente=rfc_cliente,
            numero_servicio=servicio,
            rmu=rmu,
            tarifa=tarifa_raw or "GDMTH",
            numero_medidor=medidor,
            multiplicador=int(CFEParser._parse_decimal(multiplic_raw)) if multiplic_raw else 0,
            carga_conectada_kw=_d(carga_raw),
            demanda_contratada_kw=_d(demanda_c_raw),
            periodos=periodos,
            kw_max=_d(_req(texto, RE_KW_MAX,  "kWMax",  advertencias)),
            kvArh=_d(_req(texto, RE_KVARH,    "kVArh",  advertencias)),
            factor_potencia_pct=_d(_req(texto, RE_FP,   "factor_potencia", advertencias)),
            componentes_mem=componentes,
            cargo_fijo_mxn=_d(_req(texto, RE_CARGO_FIJO,   "cargo_fijo",   advertencias)),
            energia_total_mxn=_d(_req(texto, RE_ENERGIA,   "energia",      advertencias)),
            cargo_factor_potencia_mxn=_d(_req(texto, RE_CARGO_FP, "cargo_fp", advertencias)),
            subtotal_mxn=_d(_req(texto, RE_SUBTOTAL,       "subtotal",     advertencias)),
            iva_mxn=_d(_req(texto, RE_IVA,                 "iva",          advertencias)),
            facturacion_periodo_mxn=_d(_req(texto, RE_FACT_PERIODO, "fact_periodo", advertencias)),
            derecho_alumbrado_publico_mxn=_d(_req(texto, RE_DAP,   "dap",          advertencias)),
            credito_aplicado_mxn=credito,
            total_mxn=_d(_extract_total(texto, advertencias)),
            pdf_path=str(pdf_path),
            advertencias=advertencias,
        )
