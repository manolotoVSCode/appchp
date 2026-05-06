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
