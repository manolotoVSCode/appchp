"""
CLI para procesar facturas CFE e insertarlas en Supabase.

Uso:
    python -m cli.main ruta/factura.pdf [--tarifa GDMTH]
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from parsers.cfe import get_cfe_parser
from storage.repository import save_cfe_invoice, get_all_cfe_invoices

logger = logging.getLogger(__name__)


def procesar_factura_cfe(
    pdf_path: Path,
    tarifa: str = "GDMTH",
) -> tuple[int, str]:
    """
    Parsea una factura CFE, valida coherencia y persiste en Supabase.

    Args:
        pdf_path: Ruta al archivo PDF.
        tarifa: Código de tarifa CFE. Default "GDMTH".

    Returns:
        Tupla (id de la factura en cfe_facturas, nombre_canonico).

    Raises:
        FileNotFoundError: Si el PDF no existe.
        ValueError: Si la tarifa no está soportada.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    parser = get_cfe_parser(tarifa)  # lanza ValueError si tarifa no existe
    invoice = parser.parse(pdf_path)
    errores = parser.validate(invoice)

    if errores:
        logger.warning(
            "Factura CFE '%s': %d error(es) de validación: %s",
            pdf_path.name, len(errores), "; ".join(errores),
        )

    if invoice.advertencias:
        logger.warning(
            "Factura CFE '%s': %d advertencia(s): %s",
            pdf_path.name, len(invoice.advertencias), "; ".join(invoice.advertencias),
        )

    factura_id, nombre_canonico = save_cfe_invoice(invoice)
    logger.info(
        "Factura CFE guardada: id=%d, nombre='%s', periodo=%s→%s, total_periodo=$%s",
        factura_id, nombre_canonico, invoice.periodo_inicio, invoice.periodo_fin,
        f"{invoice.facturacion_periodo_mxn:,.2f}",
    )
    return factura_id, nombre_canonico


def procesar_factura_gas(pdf_path: Path) -> tuple[int, str]:
    """Parsea y persiste una factura de gas ENGIE.

    Args:
        pdf_path: ruta al PDF.

    Returns:
        Tupla (id de la fila en gas_facturas, nombre_canonico).

    Raises:
        FileNotFoundError: si el PDF no existe.
    """
    from parsers.gas import get_gas_parser
    from storage.repository import save_gas_invoice

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    parser = get_gas_parser()
    invoice = parser.parse(pdf_path)
    errores = parser.validate(invoice)

    if invoice.advertencias:
        logger.warning(
            "Factura gas '%s': %d advertencia(s): %s",
            pdf_path.name, len(invoice.advertencias), "; ".join(invoice.advertencias),
        )
    if errores:
        logger.warning(
            "Factura gas '%s': %d error(es) de validación: %s",
            pdf_path.name, len(errores), "; ".join(errores),
        )

    factura_id, nombre_canonico = save_gas_invoice(invoice)
    logger.info(
        "Factura gas guardada: id=%d, nombre='%s', GJ=%s, total=$%s",
        factura_id, nombre_canonico, f"{invoice.consumo_total_gj:,.4f}", f"{invoice.total_mxn:,.2f}",
    )
    return factura_id, nombre_canonico


def generar_analisis_cogen(output_path: Path) -> Path:
    """Carga todas las facturas de Supabase, calcula cogeneración y genera Excel.

    Args:
        output_path: ruta del archivo .xlsx a generar.

    Returns:
        output_path (Path) del archivo generado.
    """
    from storage.repository import get_all_cfe_invoices, get_all_gas_invoices
    from calc.cogen import calcular_cogen
    from models.cogen_result import CoGenParams
    from reports.excel import generar_excel

    cfe_invoices = get_all_cfe_invoices()
    gas_invoices = get_all_gas_invoices()

    params = CoGenParams()
    resultado = calcular_cogen(cfe_invoices, gas_invoices, params)

    output_path = Path(output_path)
    generar_excel(resultado, output_path)

    logger.info("Análisis generado: %s", output_path)
    logger.info(
        "Meses pareados: %d | EBITDA anual: $%s | Ahorro elec: $%s | "
        "Ahorro caldera: $%s | Costo gas cogen: $%s",
        len(resultado.meses),
        f"{resultado.ebitda_anual_mxn:,.2f}",
        f"{resultado.ahorro_electricidad_anual_mxn:,.2f}",
        f"{resultado.ahorro_caldera_anual_mxn:,.2f}",
        f"{resultado.costo_gas_cogen_anual_mxn:,.2f}",
    )
    return output_path


def _main() -> None:
    parser = argparse.ArgumentParser(description="Procesador de facturas CFE")
    parser.add_argument("pdf", help="Ruta al PDF de la factura CFE")
    parser.add_argument("--tarifa", default="GDMTH", help="Tarifa CFE (default: GDMTH)")
    args = parser.parse_args()

    procesar_factura_cfe(Path(args.pdf), tarifa=args.tarifa)


if __name__ == "__main__":
    _main()
