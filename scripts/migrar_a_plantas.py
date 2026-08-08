#!/usr/bin/env python3
"""
Migra la base de datos al modelo cliente → planta → recursos.

REQUIERE: 202610_plantas.sql ya ejecutado en Supabase SQL Editor.

Comportamiento general:
  Para cada cliente activo (excepto caso especial Iberica), crea una planta
  "Planta Principal" y asigna planta_id en todas las tablas operativas.

Caso especial IBERICA (cliente 44 → cliente 45):
  - Renombra cliente 45 de "IBÉRICA TILES Planta 2" a "IBÉRICA TILES".
  - Crea en cliente 45 dos plantas: "Planta 1" y "Planta 2".
  - Recursos de cliente 44 → cliente 45 + planta_id=Planta 1.
  - Recursos de cliente 45 → planta_id=Planta 2 (sin cambio de cliente_id).
  - Marca cliente 44 como inactivo.
  - usuario_clientes: elimina fila (iberica_user, 44), conserva (iberica_user, 45).

Uso:
  python3 scripts/migrar_a_plantas.py
  python3 scripts/migrar_a_plantas.py --forzar   # rehace desde cero
"""

import os
import sys
import argparse
from dotenv import load_dotenv

load_dotenv()

from supabase import create_client  # noqa: E402

CLIENTE_44 = 44  # IBÉRICA TILES Planta 1  → inactivar
CLIENTE_45 = 45  # IBÉRICA TILES Planta 2  → renombrar a "IBÉRICA TILES"
NOMBRE_CLIENTE_45_NUEVO = "IBÉRICA TILES"

# Tablas operativas con cliente_id directo que reciben planta_id
TABLAS_OPERATIVAS = [
    "contratos",
    "cfe_facturas",
    "gas_facturas",
    "facturas_electricidad_calificado",
    "ppa_bloques_mensuales",
    "medidores",
    "produccion_diaria",
]


def main():
    parser = argparse.ArgumentParser(description="Migra datos al modelo plantas")
    parser.add_argument("--forzar", action="store_true",
                        help="Elimina plantas existentes y rehace la migración")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    # ── Verificar que la migración SQL ya se ejecutó ──────────────────────────
    try:
        sb.table("plantas").select("id").limit(1).execute()
    except Exception as e:
        print("ERROR: La tabla 'plantas' no existe. Ejecuta primero 202610_plantas.sql"
              " en el SQL Editor de Supabase.")
        sys.exit(1)

    # ── --forzar: eliminar todas las plantas y limpiar planta_id ─────────────
    if args.forzar:
        print("--forzar: limpiando plantas existentes y planta_id en todas las tablas…")
        for tabla in TABLAS_OPERATIVAS:
            try:
                sb.table(tabla).update({"planta_id": None}).neq("id", 0).execute()
            except Exception:
                pass  # tabla vacía o planta_id aún no existe
        # Eliminar plantas vía delete (no DROP)
        try:
            sb.table("plantas").delete().neq("id", 0).execute()
        except Exception as e:
            print(f"  Aviso al limpiar plantas: {e}")
        print("  Limpieza completada.\n")

    # ── Cargar clientes ───────────────────────────────────────────────────────
    clientes_r = sb.table("clientes").select("id,nombre,activo").execute()
    clientes = {c["id"]: c for c in clientes_r.data}
    print(f"Clientes encontrados: {len(clientes)}")

    # ── CASO ESPECIAL: Iberica ────────────────────────────────────────────────
    _migrar_iberica(sb, clientes)

    # ── CASO GENERAL: todos los demás clientes activos ───────────────────────
    ids_especiales = {CLIENTE_44, CLIENTE_45}
    clientes_generales = [
        c for c in clientes_r.data
        if c["id"] not in ids_especiales and c.get("activo", True)
    ]
    print(f"\nMigrando {len(clientes_generales)} clientes generales…")
    for cliente in clientes_generales:
        _migrar_cliente_general(sb, cliente)

    # ── Verificación rápida ───────────────────────────────────────────────────
    _verificacion_rapida(sb)
    print("\nMigración completada. Ejecuta scripts/verificar_migracion_plantas.py para informe completo.")


def _obtener_o_crear_planta(sb, cliente_id: int, nombre: str) -> int:
    """Devuelve el id de la planta existente o la crea."""
    r = (sb.table("plantas")
         .select("id")
         .eq("cliente_id", cliente_id)
         .eq("nombre", nombre)
         .execute())
    if r.data:
        pid = r.data[0]["id"]
        print(f"  Planta existente: cliente={cliente_id}, nombre='{nombre}', id={pid}")
        return pid
    r2 = sb.table("plantas").insert({"cliente_id": cliente_id, "nombre": nombre}).execute()
    pid = r2.data[0]["id"]
    print(f"  Planta creada: cliente={cliente_id}, nombre='{nombre}', id={pid}")
    return pid


def _asignar_planta_id(sb, tabla: str, cliente_id: int, planta_id: int,
                       nuevo_cliente_id: int | None = None) -> int:
    """Asigna planta_id a todas las filas de la tabla para un cliente dado.

    Si nuevo_cliente_id se especifica, también actualiza cliente_id (migración 44→45).
    Retorna el número de filas actualizadas.
    """
    payload: dict = {"planta_id": planta_id}
    if nuevo_cliente_id is not None:
        payload["cliente_id"] = nuevo_cliente_id
    try:
        r = (sb.table(tabla)
             .update(payload)
             .eq("cliente_id", cliente_id)
             .execute())
        n = len(r.data)
        if n > 0 or nuevo_cliente_id:
            print(f"    {tabla}: {n} filas" +
                  (f" (cliente_id {cliente_id}→{nuevo_cliente_id})" if nuevo_cliente_id else ""))
        return n
    except Exception as e:
        # Tabla sin columna planta_id o vacía: ignorar graciosamente
        if "planta_id" in str(e) or "column" in str(e).lower():
            print(f"    {tabla}: columna planta_id no existe (¿ejecutaste el SQL?)")
        else:
            print(f"    {tabla}: {e}")
        return 0


def _migrar_iberica(sb, clientes: dict) -> None:
    """Maneja el caso especial clientes 44 (inactivar) y 45 (renombrar + 2 plantas)."""
    print("\n── Caso especial IBERICA ────────────────────────────────────────────")

    if CLIENTE_45 not in clientes:
        print(f"  AVISO: cliente {CLIENTE_45} no encontrado. Saltando caso especial.")
        return

    # 1. Renombrar cliente 45
    nombre_actual_45 = clientes[CLIENTE_45].get("nombre", "")
    if nombre_actual_45 != NOMBRE_CLIENTE_45_NUEVO:
        sb.table("clientes").update({"nombre": NOMBRE_CLIENTE_45_NUEVO}).eq("id", CLIENTE_45).execute()
        print(f"  Cliente 45: '{nombre_actual_45}' → '{NOMBRE_CLIENTE_45_NUEVO}'")
    else:
        print(f"  Cliente 45 ya se llama '{NOMBRE_CLIENTE_45_NUEVO}'")

    # 2. Crear plantas en cliente 45
    print("  Creando plantas en cliente 45:")
    id_planta1 = _obtener_o_crear_planta(sb, CLIENTE_45, "Planta 1")
    id_planta2 = _obtener_o_crear_planta(sb, CLIENTE_45, "Planta 2")

    # 3. Migrar recursos de cliente 44 → cliente 45, planta_id=Planta 1
    if CLIENTE_44 in clientes:
        print(f"\n  Migrando recursos de cliente {CLIENTE_44} → {CLIENTE_45} (Planta 1):")
        for tabla in TABLAS_OPERATIVAS:
            _asignar_planta_id(sb, tabla, CLIENTE_44, id_planta1, nuevo_cliente_id=CLIENTE_45)
    else:
        print(f"  Cliente {CLIENTE_44} no encontrado, nada que migrar.")

    # 4. Asignar planta_id=Planta 2 a recursos YA existentes de cliente 45
    #    (solo filas que aún tienen planta_id NULL, es decir los originales del 45)
    print(f"\n  Asignando planta_id=Planta 2 a recursos restantes de cliente {CLIENTE_45}:")
    for tabla in TABLAS_OPERATIVAS:
        try:
            r = (sb.table(tabla)
                 .update({"planta_id": id_planta2})
                 .eq("cliente_id", CLIENTE_45)
                 .is_("planta_id", "null")
                 .execute())
            n = len(r.data)
            if n > 0:
                print(f"    {tabla}: {n} filas → Planta 2")
        except Exception as e:
            print(f"    {tabla}: {e}")

    # 5. Marcar cliente 44 como inactivo
    if CLIENTE_44 in clientes:
        sb.table("clientes").update({"activo": False}).eq("id", CLIENTE_44).execute()
        print(f"\n  Cliente {CLIENTE_44} marcado como inactivo.")

    # 6. Limpiar usuario_clientes: eliminar entrada para cliente 44
    try:
        r = sb.table("usuario_clientes").delete().eq("cliente_id", CLIENTE_44).execute()
        if r.data:
            print(f"  usuario_clientes: eliminadas {len(r.data)} entradas para cliente {CLIENTE_44}.")
    except Exception as e:
        print(f"  usuario_clientes: {e}")

    print("── Fin caso especial IBERICA ─────────────────────────────────────────")


def _migrar_cliente_general(sb, cliente: dict) -> None:
    """Crea 'Planta Principal' y asigna planta_id para un cliente no-Iberica."""
    cid = cliente["id"]
    nombre = cliente.get("nombre", f"Cliente {cid}")
    print(f"\n  Cliente {cid} ({nombre}):")
    pid = _obtener_o_crear_planta(sb, cid, "Planta Principal")
    for tabla in TABLAS_OPERATIVAS:
        _asignar_planta_id(sb, tabla, cid, pid)


def _verificacion_rapida(sb) -> None:
    """Cuenta NULLs en planta_id por tabla y los reporta."""
    print("\n── Verificación rápida ──────────────────────────────────────────────")
    errores = 0
    for tabla in TABLAS_OPERATIVAS:
        try:
            todos = sb.table(tabla).select("id,planta_id").execute().data
            nulls = [r for r in todos if r.get("planta_id") is None]
            estado = "✓" if not nulls else "✗"
            print(f"  {estado} {tabla}: {len(todos)} filas, {len(nulls)} con planta_id NULL")
            if nulls:
                errores += 1
        except Exception as e:
            print(f"  ? {tabla}: {e}")
    if errores:
        print(f"\nATENCIÓN: {errores} tabla(s) con planta_id NULL. Revisar antes de continuar.")
    else:
        print("\nTodos los registros tienen planta_id asignado.")


if __name__ == "__main__":
    main()
