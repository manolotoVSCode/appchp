"""
CLI para procesar facturas CFE e insertarlas en SQLite.

Uso:
    python -m cli.main ruta/factura.pdf [--tarifa GDMTH] [--db chpapp.db]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from parsers.cfe import get_cfe_parser
from storage.schema import init_db
from storage.repository import save_cfe_invoice, list_cfe_invoices


def procesar_factura_cfe(
    pdf_path: Path,
    conn: sqlite3.Connection,
    tarifa: str = "GDMTH",
) -> int:
    """
    Parsea una factura CFE, valida coherencia y persiste en SQLite.

    Args:
        pdf_path: Ruta al archivo PDF.
        conn: Conexión SQLite ya inicializada.
        tarifa: Código de tarifa CFE. Default "GDMTH".

    Returns:
        ID de la factura insertada en cfe_facturas.

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
        print(f"[ADVERTENCIA] Errores de validación ({len(errores)}):")
        for e in errores:
            print(f"  - {e}")

    if invoice.advertencias:
        print(f"[INFO] Campos con advertencias ({len(invoice.advertencias)}):")
        for a in invoice.advertencias:
            print(f"  - {a}")

    factura_id = save_cfe_invoice(conn, invoice)
    print(
        f"[OK] Factura guardada: id={factura_id}, "
        f"periodo={invoice.periodo_inicio}→{invoice.periodo_fin}, "
        f"total_periodo=${invoice.facturacion_periodo_mxn:,.2f}"
    )
    return factura_id


def procesar_factura_gas(pdf_path: Path, conn: sqlite3.Connection) -> int:
    """Parsea y persiste una factura de gas ENGIE.

    Args:
        pdf_path: ruta al PDF.
        conn: conexión SQLite inicializada con init_db().

    Returns:
        id de la fila en gas_facturas.

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

    for adv in invoice.advertencias:
        print(f"  [ADVERTENCIA] {adv}")
    for err in errores:
        print(f"  [ERROR] {err}")

    factura_id = save_gas_invoice(conn, invoice)
    print(f"  [OK] {pdf_path.name} → gas_facturas.id={factura_id}  "
          f"GJ={invoice.consumo_total_gj:,.4f}  "
          f"total=${invoice.total_mxn:,.2f}")
    return factura_id


def generar_analisis_cogen(conn: sqlite3.Connection, output_path: Path) -> Path:
    """Carga todas las facturas de la BD, calcula cogeneración y genera Excel.

    Args:
        conn: conexión SQLite con facturas CFE y Gas ya persistidas.
        output_path: ruta del archivo .xlsx a generar.

    Returns:
        output_path (Path) del archivo generado.
    """
    from storage.repository import load_cfe_invoice
    from storage.repository import list_gas_invoices, load_gas_invoice
    from calc.cogen import calcular_cogen
    from models.cogen_result import CoGenParams
    from reports.excel import generar_excel

    cfe_rows = list_cfe_invoices(conn)
    cfe_invoices = [load_cfe_invoice(conn, r["id"]) for r in cfe_rows]

    gas_rows = list_gas_invoices(conn)
    gas_invoices = [load_gas_invoice(conn, r["id"]) for r in gas_rows]

    params = CoGenParams()
    resultado = calcular_cogen(cfe_invoices, gas_invoices, params)

    output_path = Path(output_path)
    generar_excel(resultado, output_path)

    print(f"[OK] Análisis generado: {output_path}")
    print(f"     Meses pareados:     {len(resultado.meses)}")
    print(f"     EBITDA anual:       ${resultado.ebitda_anual_mxn:>16,.2f}")
    print(f"     Ahorro electricidad:${resultado.ahorro_electricidad_anual_mxn:>16,.2f}")
    print(f"     Ahorro caldera:     ${resultado.ahorro_caldera_anual_mxn:>16,.2f}")
    print(f"     Costo gas cogen:    ${resultado.costo_gas_cogen_anual_mxn:>16,.2f}")
    return output_path


def _main() -> None:
    parser = argparse.ArgumentParser(description="Procesador de facturas CFE")
    parser.add_argument("pdf", help="Ruta al PDF de la factura CFE")
    parser.add_argument("--tarifa", default="GDMTH", help="Tarifa CFE (default: GDMTH)")
    parser.add_argument("--db", default="chpapp.db", help="Ruta a la base de datos SQLite")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)

    try:
        procesar_factura_cfe(Path(args.pdf), conn, tarifa=args.tarifa)
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
