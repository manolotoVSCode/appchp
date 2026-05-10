#!/usr/bin/env python3
# scripts/migrar_seleccion_a_meses.py
"""
Migración: pobla columnas anio/mes en facturas existentes e inicializa
la tabla contrato_meses_seleccionados.

Parte 1. Para cada factura CFE y gas con contrato_id NOT NULL, calcula
         el mes asociado (año, mes) usando mes_asociado(periodo_inicio,
         periodo_fin) y actualiza las columnas anio y mes de la fila.

Parte 2. Inserta en contrato_meses_seleccionados todas las combinaciones
         únicas (contrato_id, anio, mes) presentes en facturas ya migradas.
         Usa upsert con ON CONFLICT DO NOTHING para ser idempotente.

Idempotente: re-ejecutar no duplica ni pierde datos.

Uso:
    python scripts/migrar_seleccion_a_meses.py

Variables de entorno requeridas:
    SUPABASE_URL
    SUPABASE_KEY
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from calc.periodo import mes_asociado  # noqa: E402

logger = logging.getLogger(__name__)


# ── Utilidades ────────────────────────────────────────────────────────────────

def _parse_date(valor: str | None) -> date | None:
    """Convierte string ISO (YYYY-MM-DD) a date. Devuelve None si falla."""
    if not valor:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except (ValueError, TypeError):
        return None


# ── Parte 1: poblar anio/mes en facturas ─────────────────────────────────────

def _migrar_anio_mes_tabla(
    client,
    tabla: str,
    stats: dict,
) -> set[tuple[int, int, int]]:
    """Actualiza anio y mes en todas las filas de `tabla` con contrato_id NOT NULL.

    Devuelve el conjunto de tripletas únicas (contrato_id, anio, mes)
    encontradas, para usarlas en la parte 2.
    """
    filas = (
        client.table(tabla)
        .select("id, contrato_id, periodo_inicio, periodo_fin, anio, mes")
        .not_.is_("contrato_id", "null")
        .execute()
        .data
    )

    tripletas: set[tuple[int, int, int]] = set()
    actualizadas = 0
    saltadas = 0
    errores_locales: list[str] = []

    for fila in filas:
        contrato_id = fila["contrato_id"]
        inicio = _parse_date(fila.get("periodo_inicio"))
        fin = _parse_date(fila.get("periodo_fin"))

        if inicio is None or fin is None:
            errores_locales.append(
                f"[{tabla} id={fila['id']}] periodo_inicio/fin inválido: "
                f"{fila.get('periodo_inicio')} / {fila.get('periodo_fin')}"
            )
            continue

        anio, mes = mes_asociado(inicio, fin)
        tripletas.add((contrato_id, anio, mes))

        # Solo actualizar si los valores aún no están poblados
        if fila.get("anio") == anio and fila.get("mes") == mes:
            saltadas += 1
            continue

        try:
            client.table(tabla).update(
                {"anio": anio, "mes": mes}
            ).eq("id", fila["id"]).execute()
            actualizadas += 1
            logger.debug(
                "%s id=%d → anio=%d mes=%d (contrato_id=%d)",
                tabla, fila["id"], anio, mes, contrato_id,
            )
        except Exception as exc:  # noqa: BLE001
            errores_locales.append(f"[{tabla} id={fila['id']}] {exc}")

    tipo = "electrico" if tabla == "cfe_facturas" else "gas"
    stats["facturas_actualizadas"][tipo] = actualizadas
    stats["facturas_saltadas"][tipo] = saltadas
    stats["total_filas"][tipo] = len(filas)
    stats["errores"].extend(errores_locales)

    return tripletas


# ── Parte 2: poblar contrato_meses_seleccionados ──────────────────────────────

def _migrar_meses_seleccionados(
    client,
    tripletas: set[tuple[int, int, int]],
    stats: dict,
) -> None:
    """Inserta en contrato_meses_seleccionados las tripletas únicas.

    Usa upsert con ignoreDuplicates=True (equivale a ON CONFLICT DO NOTHING).
    """
    if not tripletas:
        stats["meses_insertados"] = 0
        return

    filas = [
        {"contrato_id": cid, "anio": anio, "mes": mes}
        for cid, anio, mes in sorted(tripletas)
    ]

    try:
        client.table("contrato_meses_seleccionados").upsert(
            filas, ignore_duplicates=True
        ).execute()
        stats["meses_insertados"] = len(filas)
        logger.info("Insertadas %d combinaciones en contrato_meses_seleccionados.", len(filas))
    except Exception as exc:  # noqa: BLE001
        stats["errores"].append(f"[contrato_meses_seleccionados] {exc}")
        stats["meses_insertados"] = 0


# ── Punto de entrada de la migración ─────────────────────────────────────────

def migrar(client) -> dict:
    """Ejecuta ambas partes de la migración y devuelve estadísticas."""
    stats: dict = {
        "facturas_actualizadas": {"electrico": 0, "gas": 0},
        "facturas_saltadas": {"electrico": 0, "gas": 0},
        "total_filas": {"electrico": 0, "gas": 0},
        "meses_insertados": 0,
        "errores": [],
    }

    print("Parte 1: poblando anio/mes en cfe_facturas...")
    tripletas_cfe = _migrar_anio_mes_tabla(client, "cfe_facturas", stats)

    print("Parte 1: poblando anio/mes en gas_facturas...")
    tripletas_gas = _migrar_anio_mes_tabla(client, "gas_facturas", stats)

    todas_tripletas = tripletas_cfe | tripletas_gas

    print(f"Parte 2: insertando {len(todas_tripletas)} combinaciones únicas en contrato_meses_seleccionados...")
    _migrar_meses_seleccionados(client, todas_tripletas, stats)

    return stats


# ── Salida por consola ────────────────────────────────────────────────────────

def _imprimir_resumen(stats: dict) -> None:
    linea = "═" * 55
    print(f"\n{linea}")
    print("  MIGRACIÓN SELECCIÓN → MESES — RESUMEN")
    print(linea)
    print(f"  CFE facturas procesadas           : {stats['total_filas']['electrico']}")
    print(f"  CFE facturas actualizadas         : {stats['facturas_actualizadas']['electrico']}")
    print(f"  CFE facturas ya correctas         : {stats['facturas_saltadas']['electrico']}")
    print(f"  Gas facturas procesadas           : {stats['total_filas']['gas']}")
    print(f"  Gas facturas actualizadas         : {stats['facturas_actualizadas']['gas']}")
    print(f"  Gas facturas ya correctas         : {stats['facturas_saltadas']['gas']}")
    print(f"  Meses únicos insertados           : {stats['meses_insertados']}")
    if stats["errores"]:
        print(f"\n  ERRORES ({len(stats['errores'])}):")
        for e in stats["errores"]:
            print(f"    • {e}")
    else:
        print("\n  Sin errores.")
    print(f"{linea}\n")


# ── Entrada principal ─────────────────────────────────────────────────────────

def _main() -> None:
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("ERROR: Se requieren SUPABASE_URL y SUPABASE_KEY en variables de entorno.")
        sys.exit(1)

    client = create_client(url, key)
    print("Conectado a Supabase. Iniciando migración...")
    stats = migrar(client)
    _imprimir_resumen(stats)

    if stats["errores"]:
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _main()
