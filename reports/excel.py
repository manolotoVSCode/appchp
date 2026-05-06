# reports/excel.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from models.cogen_result import CoGenResultado

# Colores
_AZUL_HEADER = "1F4E79"
_GRIS_TOTALES = "D9E1F2"
_VERDE_EBITDA = "E2EFDA"


def generar_excel(resultado: CoGenResultado, output_path: Path) -> Path:
    """Genera reporte Excel con análisis mensual de cogeneración.

    Crea dos hojas:
    - 'Análisis Mensual': tabla con 12 meses + totales
    - 'Parámetros': parámetros técnicos usados

    Args:
        resultado: CoGenResultado con todos los meses calculados
        output_path: ruta donde guardar el .xlsx

    Returns:
        output_path (para encadenamiento)
    """
    output_path = Path(output_path)
    wb = openpyxl.Workbook()

    _escribir_hoja_analisis(wb, resultado)
    _escribir_hoja_parametros(wb, resultado.params)

    # Eliminar hoja vacía por defecto
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    wb.save(output_path)
    return output_path


# ── Hoja 1: Análisis Mensual ──────────────────────────────────────────────────

_COLUMNAS = [
    ("Periodo",               "periodo_inicio",             "fecha"),
    ("kWh Total",             "kwh_total",                  "numero"),
    ("Costo CFE (MXN)",       "costo_cfe_mxn",              "moneda"),
    ("$/kWh Promedio",        "costo_promedio_kwh",         "decimal4"),
    ("GJ Gas Real",           "gj_consumido",               "numero"),
    ("$/GJ Gas",              "costo_unitario_gj",          "decimal4"),
    ("Costo Gas Real (MXN)",  "costo_gas_actual_mxn",       "moneda"),
    ("kWh Cubiertos",         "kwh_cubiertos",              "numero"),
    ("GJ Cogen",              "gj_gas_cogen",               "numero"),
    ("Costo Gas Cogen (MXN)", "costo_gas_cogen_mxn",        "moneda"),
    ("Ahorro Elec. (MXN)",    "ahorro_electricidad_mxn",    "moneda"),
    ("Calor Recup. (GJ)",     "calor_recuperado_gj",        "numero"),
    ("Ahorro Caldera (MXN)",  "ahorro_caldera_mxn",         "moneda"),
    ("EBITDA Mes (MXN)",      "ebitda_mes_mxn",             "moneda"),
]

_TOTALES_COLS = {
    "kwh_total":                  "kwh_total_anual",
    "kwh_cubiertos":              "kwh_cubiertos_anual",
    "gj_gas_cogen":               "gj_gas_cogen_anual",
    "costo_gas_cogen_mxn":        "costo_gas_cogen_anual_mxn",
    "ahorro_electricidad_mxn":    "ahorro_electricidad_anual_mxn",
    "ahorro_caldera_mxn":         "ahorro_caldera_anual_mxn",
    "ebitda_mes_mxn":             "ebitda_anual_mxn",
}


def _escribir_hoja_analisis(wb: openpyxl.Workbook, resultado: CoGenResultado) -> None:
    ws = wb.create_sheet("Análisis Mensual")

    # Encabezados
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=_AZUL_HEADER)
    for col_idx, (titulo, _, _fmt) in enumerate(_COLUMNAS, 1):
        cell = ws.cell(1, col_idx, titulo)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Filas de datos
    for row_idx, mes in enumerate(resultado.meses, 2):
        for col_idx, (_titulo, attr, fmt) in enumerate(_COLUMNAS, 1):
            valor = getattr(mes, attr)
            cell = ws.cell(row_idx, col_idx, _formatear(valor, fmt))
            if fmt == "moneda":
                cell.number_format = '#,##0.00'
            elif fmt == "numero":
                cell.number_format = '#,##0.0000'
            elif fmt == "decimal4":
                cell.number_format = '0.0000'
            if attr == "ebitda_mes_mxn":
                cell.fill = PatternFill("solid", fgColor=_VERDE_EBITDA)

    # Fila de totales
    totales_row = len(resultado.meses) + 2
    totales_fill = PatternFill("solid", fgColor=_GRIS_TOTALES)
    totales_font = Font(bold=True)
    ws.cell(totales_row, 1, "TOTAL ANUAL").font = totales_font
    ws.cell(totales_row, 1).fill = totales_fill

    for col_idx, (_titulo, attr, fmt) in enumerate(_COLUMNAS, 1):
        if attr in _TOTALES_COLS:
            valor = getattr(resultado, _TOTALES_COLS[attr])
            cell = ws.cell(totales_row, col_idx, float(valor))
            cell.number_format = '#,##0.00' if fmt == "moneda" else '#,##0.0000'
            cell.font = totales_font
            cell.fill = totales_fill

    # Anchos de columna
    anchos = [12, 14, 18, 12, 14, 10, 18, 14, 12, 18, 18, 14, 18, 18]
    for i, ancho in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    ws.freeze_panes = "B2"


def _formatear(valor: object, fmt: str) -> object:
    """Convierte Decimal/date al tipo nativo que openpyxl acepta mejor."""
    if isinstance(valor, date):
        return valor.strftime("%b %Y")
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


# ── Hoja 2: Parámetros ────────────────────────────────────────────────────────

def _escribir_hoja_parametros(wb: openpyxl.Workbook, params) -> None:
    ws = wb.create_sheet("Parámetros")

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=_AZUL_HEADER)

    ws.cell(1, 1, "Parámetro").font = header_font
    ws.cell(1, 1).fill = header_fill
    ws.cell(1, 2, "Valor").font = header_font
    ws.cell(1, 2).fill = header_fill

    filas = [
        ("Cobertura eléctrica",  f"{float(params.cobertura_electrica)*100:.0f}%"),
        ("Rendimiento eléctrico",f"{float(params.rendimiento_electrico)*100:.0f}%"),
        ("Rendimiento térmico",  f"{float(params.rendimiento_termico)*100:.0f}%"),
        ("Eficiencia caldera",   f"{float(params.eficiencia_caldera)*100:.0f}%"),
        ("Factor kWh→GJ",        "0.0036 GJ/kWh"),
    ]
    for row_idx, (nombre, valor) in enumerate(filas, 2):
        ws.cell(row_idx, 1, nombre)
        ws.cell(row_idx, 2, valor)

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 16
