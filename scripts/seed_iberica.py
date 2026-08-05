#!/usr/bin/env python3
"""Seed masivo de telemetría jerárquica — Ibérica Tiles Planta 1 (c44) y Planta 2 (c45).

Uso:
    python scripts/seed_iberica.py
    python scripts/seed_iberica.py --forzar
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

from storage.repository import (
    crear_medidor_jerarquico,
    obtener_medidores_por_cliente,
    insertar_mediciones_batch,
)
from telemetria.seed import generar_mediciones_por_carga

# ── Definición de la jerarquía ─────────────────────────────────────────────────

PLANTA_1 = {
    "cliente_id": 44,
    "acometida": {
        "nombre": "Acometida CFE-1 SE Poniente",
        "relacion_tc": "150/5",
    },
    "transformadores": [
        {
            "nombre": "T-1.1 (2500 kVA, MMC1)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-MMC1", "tipo_carga": "motor", "potencia_nominal_kw": 2400},
            ],
        },
        {
            "nombre": "T-1.2 (800 kVA, Vent. Atomizador 1)",
            "potencia_nominal_kw": 776,
            "cargas": [
                {"nombre": "CBT-Vent. Atomizador 1", "tipo_carga": "ventilador", "potencia_nominal_kw": 750},
            ],
        },
        {
            "nombre": "T-1.3 (1600 kVA, Zona Atomizado 1)",
            "potencia_nominal_kw": 1552,
            "cargas": [
                {"nombre": "CBT-Zona Atomizado 1", "tipo_carga": "atomizador", "potencia_nominal_kw": 1500},
            ],
        },
        {
            "nombre": "T-2.1 (2000 kVA, Zona Prensas)",
            "potencia_nominal_kw": 1940,
            "cargas": [
                {"nombre": "CBT-Zona Prensas", "tipo_carga": "prensa", "potencia_nominal_kw": 1900},
            ],
        },
        {
            "nombre": "T-3.1 (2000 kVA, Zona Hornos)",
            "potencia_nominal_kw": 1940,
            "cargas": [
                {"nombre": "CBT-Zona Hornos", "tipo_carga": "horno_tunel", "potencia_nominal_kw": 1900},
            ],
        },
        {
            "nombre": "T-SA (112.5 kVA, Serv. Auxiliares)",
            "potencia_nominal_kw": 109.125,
            "cargas": [
                {"nombre": "CBT-Serv. Auxiliares", "tipo_carga": "generico", "potencia_nominal_kw": 105},
            ],
        },
    ],
}

PLANTA_2 = {
    "cliente_id": 45,
    "acometida": {
        "nombre": "Acometida CFE-2 SE Sur",
        "relacion_tc": "150/5",
    },
    "transformadores": [
        {
            "nombre": "T-4.1 (2500 kVA, MMC2)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-MMC2", "tipo_carga": "motor", "potencia_nominal_kw": 2400},
            ],
        },
        {
            "nombre": "T-4.2 (800 kVA, Vent. Atomizador 2)",
            "potencia_nominal_kw": 776,
            "cargas": [
                {"nombre": "CBT-Vent. Atomizador 2", "tipo_carga": "ventilador", "potencia_nominal_kw": 750},
            ],
        },
        {
            "nombre": "T-4.3 (1000 kVA, Zona Atomizado 2)",
            "potencia_nominal_kw": 970,
            "cargas": [
                {"nombre": "CBT-Zona Atomizado 2", "tipo_carga": "atomizador", "potencia_nominal_kw": 950},
            ],
        },
        {
            "nombre": "T-5.1 (2500 kVA, Zona Prensas P2)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-Zona Prensas P2", "tipo_carga": "prensa", "potencia_nominal_kw": 2400},
            ],
        },
        {
            "nombre": "T-6.1 (2000 kVA, Zona Hornos P2)",
            "potencia_nominal_kw": 1940,
            "cargas": [
                {"nombre": "CBT-Zona Hornos P2", "tipo_carga": "horno_tunel", "potencia_nominal_kw": 1900},
            ],
        },
        {
            "nombre": "T-6.2 (2500 kVA, Pulido y Líneas 7-8)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-Pulido y Líneas 7-8", "tipo_carga": "pulidora", "potencia_nominal_kw": 2400},
            ],
        },
    ],
}

PLANTAS = [PLANTA_1, PLANTA_2]


def _verificar_existencia() -> bool:
    """Retorna True si el árbol ya está sembrado (medidor acometida encontrado)."""
    from storage.repository import _supabase
    for planta in PLANTAS:
        nombre = planta["acometida"]["nombre"]
        cid    = planta["cliente_id"]
        resp   = (
            _supabase.table("medidores")
            .select("id")
            .eq("cliente_id", cid)
            .eq("nombre", nombre)
            .limit(1)
            .execute()
        )
        if resp.data:
            return True
    return False


def _borrar_existentes() -> None:
    """Borra mediciones y medidores de los clientes en orden jerárquico."""
    from storage.repository import _supabase
    for planta in PLANTAS:
        cid = planta["cliente_id"]
        # Obtener todos los medidor_ids
        resp = (
            _supabase.table("medidores")
            .select("id")
            .eq("cliente_id", cid)
            .limit(20000)
            .execute()
        )
        ids = [r["id"] for r in (resp.data or [])]
        if not ids:
            continue
        # Borrar mediciones primero
        _supabase.table("mediciones_tiempo_real").delete().in_("medidor_id", ids).execute()
        # Borrar cargas finales
        _supabase.table("medidores").delete().eq("cliente_id", cid).eq("punto_medicion", "carga_final").execute()
        # Borrar transformadores
        _supabase.table("medidores").delete().eq("cliente_id", cid).eq("punto_medicion", "transformador").execute()
        # Borrar acometidas
        _supabase.table("medidores").delete().eq("cliente_id", cid).eq("punto_medicion", "acometida_cfe").execute()
    print("  → Registros existentes eliminados.")


def _crear_jerarquia(planta: dict) -> tuple[int, int, int]:
    """Crea acometida, transformadores y cargas. Retorna (n_acom, n_trafo, n_cargas)."""
    cid = planta["cliente_id"]

    # Acometida
    acom_def = planta["acometida"]
    acometida = crear_medidor_jerarquico(
        cliente_id=cid,
        nombre=acom_def["nombre"],
        punto_medicion="acometida_cfe",
        relacion_tc=acom_def.get("relacion_tc"),
    )
    n_acom = 1

    n_trafo  = 0
    n_cargas = 0

    for t_def in planta["transformadores"]:
        trafo = crear_medidor_jerarquico(
            cliente_id=cid,
            nombre=t_def["nombre"],
            punto_medicion="transformador",
            medidor_padre_id=acometida["id"],
            potencia_nominal_kw=t_def["potencia_nominal_kw"],
        )
        n_trafo += 1

        for c_def in t_def["cargas"]:
            crear_medidor_jerarquico(
                cliente_id=cid,
                nombre=c_def["nombre"],
                punto_medicion="carga_final",
                medidor_padre_id=trafo["id"],
                tipo_carga=c_def["tipo_carga"],
                potencia_nominal_kw=c_def["potencia_nominal_kw"],
            )
            n_cargas += 1

    return n_acom, n_trafo, n_cargas


def _sembrar_mediciones(planta: dict, dias: int = 7) -> int:
    """Genera y persiste mediciones para las cargas finales. Retorna total insertado."""
    from storage.repository import _supabase
    cid   = planta["cliente_id"]
    hasta = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    desde = hasta - timedelta(days=dias)

    # Obtener solo cargas finales
    resp = (
        _supabase.table("medidores")
        .select("*")
        .eq("cliente_id", cid)
        .eq("punto_medicion", "carga_final")
        .limit(20000)
        .execute()
    )
    cargas = resp.data or []

    n_intervalo = dias * 24 * 4   # 15-min → 4/h → 672 por día × días
    total = 0
    for carga in cargas:
        meds = generar_mediciones_por_carga(carga, desde, n=n_intervalo, intervalo=15)
        total += insertar_mediciones_batch(meds)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed masivo de telemetría jerárquica Ibérica Tiles."
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Borrar datos existentes y resembrar desde cero.",
    )
    args = parser.parse_args()

    t0 = time.time()
    print("=== Seed Ibérica Tiles — Telemetría jerárquica ===")

    if _verificar_existencia():
        if not args.forzar:
            print("\n⚠ Árbol ya sembrado. Use --forzar para recrear.")
            sys.exit(0)
        print("  --forzar activo: borrando registros existentes…")
        _borrar_existentes()

    totales = {"acometidas": 0, "transformadores": 0, "cargas": 0, "mediciones": 0}

    for planta in PLANTAS:
        cid = planta["cliente_id"]
        print(f"\n→ Planta cliente_id={cid}…")
        na, nt, nc = _crear_jerarquia(planta)
        print(f"    Acometidas: {na}  Transformadores: {nt}  Cargas: {nc}")
        nm = _sembrar_mediciones(planta)
        print(f"    Mediciones insertadas: {nm}")
        totales["acometidas"]     += na
        totales["transformadores"] += nt
        totales["cargas"]         += nc
        totales["mediciones"]     += nm

    elapsed = time.time() - t0
    print(f"\n=== Completado en {elapsed:.1f}s ===")
    print(f"  Acometidas:      {totales['acometidas']}")
    print(f"  Transformadores: {totales['transformadores']}")
    print(f"  Cargas finales:  {totales['cargas']}")
    print(f"  Mediciones:      {totales['mediciones']}")


if __name__ == "__main__":
    main()
