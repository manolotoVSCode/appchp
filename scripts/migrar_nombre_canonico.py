#!/usr/bin/env python3
# scripts/migrar_nombre_canonico.py
"""
Migración: calcula y persiste nombre_canonico en todas las facturas CFE y gas.

Idempotente: si una factura ya tiene nombre_canonico, lo recalcula y actualiza.

Uso:
    python scripts/migrar_nombre_canonico.py

Variables de entorno requeridas:
    SUPABASE_URL
    SUPABASE_KEY
"""
from __future__ import annotations

import os
import sys
from datetime import date

# Asegurar que el raíz del proyecto esté en sys.path al ejecutar directamente
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from calc.nombre_canonico import generar_nombre_canonico_raw


def migrar(client) -> dict[str, int]:
    """Recorre cfe_facturas y gas_facturas, actualiza nombre_canonico en cada fila.

    Args:
        client: cliente Supabase (o mock compatible).

    Returns:
        Dict con claves cfe_ok, gas_ok, errores.
    """
    cfe_ok = 0
    gas_ok = 0
    errores = 0
    errores_detalle: list[str] = []

    # ── CFE ───────────────────────────────────────────────────────────────────
    cfe_rows = client.table("cfe_facturas").select(
        "id, periodo_inicio, periodo_fin, numero_servicio"
    ).execute().data

    for row in cfe_rows:
        try:
            nombre = generar_nombre_canonico_raw(
                date.fromisoformat(row["periodo_inicio"]),
                date.fromisoformat(row["periodo_fin"]),
                tipo="cfe",
                numero_servicio=row.get("numero_servicio"),
            )
            client.table("cfe_facturas").update(
                {"nombre_canonico": nombre}
            ).eq("id", row["id"]).execute()
            cfe_ok += 1
        except Exception as exc:
            errores += 1
            errores_detalle.append(f"cfe id={row.get('id')}: {exc}")

    # ── Gas ───────────────────────────────────────────────────────────────────
    gas_rows = client.table("gas_facturas").select(
        "id, periodo_inicio, periodo_fin, nombre_proveedor"
    ).execute().data

    for row in gas_rows:
        try:
            nombre = generar_nombre_canonico_raw(
                date.fromisoformat(row["periodo_inicio"]),
                date.fromisoformat(row["periodo_fin"]),
                tipo="gas",
                nombre_proveedor=row.get("nombre_proveedor"),
            )
            client.table("gas_facturas").update(
                {"nombre_canonico": nombre}
            ).eq("id", row["id"]).execute()
            gas_ok += 1
        except Exception as exc:
            errores += 1
            errores_detalle.append(f"gas id={row.get('id')}: {exc}")

    return {"cfe_ok": cfe_ok, "gas_ok": gas_ok, "errores": errores, "detalle": errores_detalle}


def _main() -> None:
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("ERROR: Se requieren SUPABASE_URL y SUPABASE_KEY en variables de entorno.")
        sys.exit(1)

    client = create_client(url, key)
    print("Iniciando migración de nombre_canonico...")
    resultado = migrar(client)

    print(f"\nFacturas CFE actualizadas : {resultado['cfe_ok']}")
    print(f"Facturas gas actualizadas : {resultado['gas_ok']}")
    print(f"Errores                   : {resultado['errores']}")
    if resultado["detalle"]:
        print("\nDetalle de errores:")
        for d in resultado["detalle"]:
            print(f"  {d}")


if __name__ == "__main__":
    _main()
