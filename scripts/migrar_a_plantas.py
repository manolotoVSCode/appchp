#!/usr/bin/env python3
"""
Migra la base de datos al modelo cliente → planta → recursos.

REQUIERE: 202610_plantas.sql ya ejecutado en Supabase SQL Editor.

ENFOQUE: UPDATE en lugar de copy-delete.
Los IDs originales de todas las filas se conservan. No hay ruptura de FKs.

Comportamiento:
  IBERICA (clientes 44 y 45):
    1. Crear "Planta 1" y "Planta 2" en cliente 45 (idempotente).
    2. Recursos del cliente 44:
         UPDATE tabla SET cliente_id=45, planta_id=Planta 1
         WHERE cliente_id=44
       Aplica a TABLAS_OPERATIVAS + mediciones_cincominutal.
    3. Recursos del cliente 45 con planta_id NULL:
         UPDATE tabla SET planta_id=Planta 2
         WHERE cliente_id=45 AND planta_id IS NULL
    4. Renombrar cliente 45 → "IBÉRICA TILES".
    5. Marcar cliente 44 como inactivo.
    6. Migrar user_profiles.empresa_id de 44 → 45.
       Eliminar entrada usuario_clientes para cliente 44.

  Demás clientes activos:
    7. Crear "Planta Principal" (idempotente).
       UPDATE tabla SET planta_id=Planta Principal
       WHERE cliente_id=X AND planta_id IS NULL

Idempotencia:
  - Plantas existentes no se recrean (UNIQUE cliente_id+nombre protege).
  - Pasos 3 y 7 usan WHERE planta_id IS NULL: no sobrescriben migraciones previas.
  - Paso 2 no filtra por planta_id IS NULL porque también cambia cliente_id.

Con --forzar:
  - SET planta_id = NULL en todas las tablas operativas.
  - DELETE FROM plantas (el ON DELETE SET NULL del FK lo haría igual,
    pero se hace explícitamente para garantía).
  - Reejecutar pasos 1-7 desde cero.

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

CLIENTE_44 = 44  # IBÉRICA TILES Planta 1 → inactivar
CLIENTE_45 = 45  # IBÉRICA TILES Planta 2 → renombrar a "IBÉRICA TILES"
NOMBRE_CLIENTE_45_NUEVO = "IBÉRICA TILES"

# Tablas que reciben planta_id (DDL 202610_plantas.sql)
TABLAS_PLANTA_ID = [
    "contratos",
    "cfe_facturas",
    "gas_facturas",
    "facturas_electricidad_calificado",
    "ppa_bloques_mensuales",
    "medidores",
    "produccion_diaria",
]

# Tablas adicionales que necesitan migración de cliente_id 44→45 pero pueden no
# tener columna planta_id todavía (el error se captura y se reporta sin abortar).
TABLAS_SOLO_CLIENTE_ID = [
    "mediciones_cincominutal",
]

# Lista unificada para migración IBERICA (client_id 44→45)
TABLAS_MIGRACION_IBERICA = TABLAS_PLANTA_ID + TABLAS_SOLO_CLIENTE_ID


def main():
    parser = argparse.ArgumentParser(description="Migra datos al modelo plantas (UPDATE en su lugar)")
    parser.add_argument("--forzar", action="store_true",
                        help="Resetea planta_id, elimina plantas y rehace la migración completa")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    # ── Verificar que la migración SQL ya se ejecutó ──────────────────────────
    try:
        sb.table("plantas").select("id").limit(1).execute()
    except Exception:
        print("ERROR: La tabla 'plantas' no existe.")
        print("       Ejecuta primero 202610_plantas.sql en el SQL Editor de Supabase.")
        sys.exit(1)

    # ── Cargar clientes (se necesita antes de --forzar para acotar por cliente_id) ──
    clientes_r = sb.table("clientes").select("id,nombre,activo").execute()
    clientes = {c["id"]: c for c in clientes_r.data}
    print(f"Clientes encontrados: {len(clientes)}")

    # ── --forzar: limpiar planta_id acotado por cliente y eliminar plantas ────
    if args.forzar:
        ids_a_limpiar = list(clientes.keys())
        print("─" * 60)
        print(f"--forzar: reseteando planta_id para {len(ids_a_limpiar)} clientes…")
        for tabla in TABLAS_PLANTA_ID:
            try:
                r = (sb.table(tabla)
                     .update({"planta_id": None})
                     .in_("cliente_id", ids_a_limpiar)
                     .execute())
                n = len(r.data) if r.data else 0
                print(f"  {tabla}: {n} filas → planta_id = NULL")
            except Exception as e:
                print(f"  {tabla}: {e} (omitida)")
        try:
            r = (sb.table("plantas")
                 .delete()
                 .in_("cliente_id", ids_a_limpiar)
                 .execute())
            n = len(r.data) if r.data else "?"
            print(f"  plantas: {n} eliminadas")
        except Exception as e:
            print(f"  plantas: {e}")
        print("  Limpieza completada.\n")

    # ── CASO ESPECIAL: IBERICA ────────────────────────────────────────────────
    _migrar_iberica(sb, clientes)

    # ── CASO GENERAL: demás clientes activos ──────────────────────────────────
    ids_especiales = {CLIENTE_44, CLIENTE_45}
    clientes_generales = [
        c for c in clientes_r.data
        if c["id"] not in ids_especiales and c.get("activo", True)
    ]
    print(f"\nMigrando {len(clientes_generales)} clientes generales…")
    for cliente in clientes_generales:
        _migrar_cliente_general(sb, cliente)

    # ── Verificación final ────────────────────────────────────────────────────
    _verificacion_final(sb)
    print("\nMigración completada.")
    print("Ejecuta scripts/verificar_migracion_plantas.py para informe completo.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _obtener_o_crear_planta(sb, cliente_id: int, nombre: str) -> int:
    """Devuelve el id de la planta existente o la crea. Idempotente."""
    r = (sb.table("plantas")
         .select("id")
         .eq("cliente_id", cliente_id)
         .eq("nombre", nombre)
         .execute())
    if r.data:
        pid = r.data[0]["id"]
        print(f"    Planta existente: cliente={cliente_id}, nombre='{nombre}', id={pid}")
        return pid
    r2 = sb.table("plantas").insert({"cliente_id": cliente_id, "nombre": nombre}).execute()
    pid = r2.data[0]["id"]
    print(f"    Planta creada:    cliente={cliente_id}, nombre='{nombre}', id={pid}")
    return pid


def _update_planta_id(sb, tabla: str, cliente_id: int, planta_id: int,
                      nuevo_cliente_id: int | None = None,
                      solo_null: bool = True) -> int:
    """UPDATE planta_id (y opcionalmente cliente_id) en la tabla.

    Args:
        tabla: nombre de la tabla.
        cliente_id: filtro WHERE cliente_id = X.
        planta_id: valor a asignar en planta_id.
        nuevo_cliente_id: si se especifica, también actualiza cliente_id.
        solo_null: si True, añade filtro AND planta_id IS NULL (idempotente).
                   Se fuerza a False cuando se cambia cliente_id.
    Retorna el número de filas actualizadas.
    """
    payload: dict = {"planta_id": planta_id}
    if nuevo_cliente_id is not None:
        payload["cliente_id"] = nuevo_cliente_id
        solo_null = False  # Al cambiar cliente_id no filtramos por planta_id NULL

    try:
        q = sb.table(tabla).update(payload).eq("cliente_id", cliente_id)
        if solo_null:
            q = q.is_("planta_id", "null")
        r = q.execute()
        n = len(r.data)
        if n > 0 or nuevo_cliente_id is not None:
            sufijo = f" (cliente_id {cliente_id}→{nuevo_cliente_id})" if nuevo_cliente_id else ""
            print(f"    {tabla}: {n} filas actualizadas{sufijo}")
        return n
    except Exception as e:
        msg = str(e)
        if "planta_id" in msg or "column" in msg.lower() or "does not exist" in msg:
            print(f"    {tabla}: columna planta_id no existe (¿ejecutaste el DDL?)")
        elif "cliente_id" in msg:
            print(f"    {tabla}: columna cliente_id no existe, omitida")
        else:
            print(f"    {tabla}: {e}")
        return 0


def _update_cliente_id(sb, tabla: str, cliente_id_origen: int,
                       cliente_id_destino: int) -> int:
    """UPDATE cliente_id sin tocar planta_id. Para tablas sin columna planta_id."""
    try:
        r = (sb.table(tabla)
             .update({"cliente_id": cliente_id_destino})
             .eq("cliente_id", cliente_id_origen)
             .execute())
        n = len(r.data)
        if n > 0:
            print(f"    {tabla}: {n} filas → cliente_id {cliente_id_origen}→{cliente_id_destino}")
        return n
    except Exception as e:
        print(f"    {tabla}: {e}")
        return 0


# ── Caso especial IBERICA ─────────────────────────────────────────────────────

def _migrar_iberica(sb, clientes: dict) -> None:
    """Migra clientes 44 y 45 al modelo planta usando UPDATE en su lugar."""
    sep = "─" * 60
    print(f"\n{sep}")
    print("CASO ESPECIAL — IBERICA")
    print(sep)

    if CLIENTE_45 not in clientes:
        print(f"  AVISO: cliente {CLIENTE_45} no encontrado. Saltando caso especial.")
        return

    # [1] Crear plantas en cliente 45 ─────────────────────────────────────────
    print("\n  [1] Plantas objetivo en cliente 45:")
    id_planta1 = _obtener_o_crear_planta(sb, CLIENTE_45, "Planta 1")
    id_planta2 = _obtener_o_crear_planta(sb, CLIENTE_45, "Planta 2")

    # [2] Recursos cliente 44 → cliente 45 + planta_id = Planta 1 ─────────────
    if CLIENTE_44 in clientes:
        print(f"\n  [2] Recursos cliente {CLIENTE_44} → cliente {CLIENTE_45} + planta_id=Planta 1:")
        # Tablas con planta_id: actualizar cliente_id Y planta_id de una sola pasada
        for tabla in TABLAS_PLANTA_ID:
            _update_planta_id(sb, tabla, CLIENTE_44, id_planta1, nuevo_cliente_id=CLIENTE_45)
        # Tablas sin planta_id: actualizar solo cliente_id
        for tabla in TABLAS_SOLO_CLIENTE_ID:
            _update_cliente_id(sb, tabla, CLIENTE_44, CLIENTE_45)
    else:
        print(f"\n  [2] Cliente {CLIENTE_44} no encontrado, nada que migrar.")

    # [3] Recursos cliente 45 con planta_id NULL → planta_id = Planta 2 ───────
    print(f"\n  [3] Recursos de cliente {CLIENTE_45} (planta_id NULL) → planta_id=Planta 2:")
    for tabla in TABLAS_PLANTA_ID:
        _update_planta_id(sb, tabla, CLIENTE_45, id_planta2, solo_null=True)

    # [4] Renombrar cliente 45 ─────────────────────────────────────────────────
    nombre_actual_45 = clientes[CLIENTE_45].get("nombre", "")
    if nombre_actual_45 != NOMBRE_CLIENTE_45_NUEVO:
        sb.table("clientes").update({"nombre": NOMBRE_CLIENTE_45_NUEVO}).eq("id", CLIENTE_45).execute()
        print(f"\n  [4] Cliente 45: '{nombre_actual_45}' → '{NOMBRE_CLIENTE_45_NUEVO}'")
    else:
        print(f"\n  [4] Cliente 45 ya tiene nombre '{NOMBRE_CLIENTE_45_NUEVO}'")

    # [5] Marcar cliente 44 como inactivo ─────────────────────────────────────
    if CLIENTE_44 in clientes:
        sb.table("clientes").update({"activo": False}).eq("id", CLIENTE_44).execute()
        print(f"  [5] Cliente {CLIENTE_44} marcado como inactivo.")

    # [6] Migrar user_profiles.empresa_id 44 → 45 ─────────────────────────────
    print(f"\n  [6] Migrando usuario iberica:")
    try:
        r_up = (sb.table("user_profiles")
                .update({"empresa_id": CLIENTE_45})
                .eq("empresa_id", CLIENTE_44)
                .execute())
        if r_up.data:
            emails = [u.get("email", "?") for u in r_up.data]
            print(f"    user_profiles: empresa_id {CLIENTE_44}→{CLIENTE_45} para: {emails}")
        else:
            print(f"    user_profiles: ningún usuario tenía empresa_id={CLIENTE_44}")
    except Exception as e:
        print(f"    user_profiles: {e}")

    # [6b] Limpiar usuario_clientes: eliminar entrada para cliente 44 ──────────
    try:
        r_uc = sb.table("usuario_clientes").delete().eq("cliente_id", CLIENTE_44).execute()
        n_uc = len(r_uc.data) if r_uc.data else 0
        if n_uc:
            print(f"    usuario_clientes: {n_uc} entrada(s) para cliente {CLIENTE_44} eliminadas.")
        else:
            print(f"    usuario_clientes: ninguna entrada para cliente {CLIENTE_44}")
    except Exception as e:
        print(f"    usuario_clientes: {e}")

    print(f"\n{sep}")
    print("FIN — IBERICA")
    print(sep)


# ── Caso general ──────────────────────────────────────────────────────────────

def _migrar_cliente_general(sb, cliente: dict) -> None:
    """Crea 'Planta Principal' y asigna planta_id donde sea NULL."""
    cid = cliente["id"]
    nombre = cliente.get("nombre", f"Cliente {cid}")
    print(f"\n  Cliente {cid} ({nombre}):")
    pid = _obtener_o_crear_planta(sb, cid, "Planta Principal")
    for tabla in TABLAS_PLANTA_ID:
        _update_planta_id(sb, tabla, cid, pid, solo_null=True)


# ── Verificación ──────────────────────────────────────────────────────────────

def _verificacion_final(sb) -> None:
    """Reporte de conteos por tabla: NULLs en planta_id y filas aún en cliente 44."""
    sep = "─" * 60
    print(f"\n{sep}")
    print("VERIFICACIÓN FINAL")
    print(sep)

    errores = 0
    for tabla in TABLAS_PLANTA_ID:
        try:
            filas = (sb.table(tabla)
                     .select("id,cliente_id,planta_id")
                     .limit(20000)
                     .execute().data)
            nulls = sum(1 for r in filas if r.get("planta_id") is None)
            c44 = sum(1 for r in filas if r.get("cliente_id") == CLIENTE_44)
            ok = nulls == 0 and c44 == 0
            estado = "✓" if ok else "✗"
            extras = []
            if nulls:
                extras.append(f"{nulls} planta_id NULL")
            if c44:
                extras.append(f"{c44} aún en cliente 44")
            detalle = f" [{', '.join(extras)}]" if extras else ""
            print(f"  {estado} {tabla}: {len(filas)} filas{detalle}")
            if not ok:
                errores += 1
        except Exception as e:
            print(f"  ? {tabla}: {e}")

    # Verificación mediciones_cincominutal (sin planta_id)
    for tabla in TABLAS_SOLO_CLIENTE_ID:
        try:
            filas = (sb.table(tabla)
                     .select("id,cliente_id")
                     .limit(20000)
                     .execute().data)
            c44 = sum(1 for r in filas if r.get("cliente_id") == CLIENTE_44)
            ok = c44 == 0
            estado = "✓" if ok else "✗"
            detalle = f" [{c44} aún en cliente 44]" if c44 else ""
            print(f"  {estado} {tabla}: {len(filas)} filas{detalle} (sin planta_id)")
            if not ok:
                errores += 1
        except Exception as e:
            print(f"  ? {tabla}: {e}")

    # Estado clientes 44 y 45
    print(f"\n  Clientes 44 y 45:")
    try:
        cl = (sb.table("clientes")
              .select("id,nombre,activo")
              .in_("id", [CLIENTE_44, CLIENTE_45])
              .execute().data)
        for c in sorted(cl, key=lambda x: x["id"]):
            print(f"    {c['id']}: nombre='{c['nombre']}', activo={c['activo']}")
    except Exception as e:
        print(f"    {e}")

    # Plantas de cliente 45
    print(f"\n  Plantas de cliente 45:")
    try:
        ps = (sb.table("plantas")
              .select("id,nombre,activo")
              .eq("cliente_id", CLIENTE_45)
              .execute().data)
        for p in sorted(ps, key=lambda x: x["nombre"]):
            print(f"    planta {p['id']}: '{p['nombre']}', activo={p['activo']}")
        if not ps:
            print("    (ninguna)")
    except Exception as e:
        print(f"    {e}")

    # Contratos por cliente para verificar distribución
    print(f"\n  Contratos por cliente (44 y 45):")
    try:
        cts = (sb.table("contratos")
               .select("id,cliente_id,planta_id")
               .in_("cliente_id", [CLIENTE_44, CLIENTE_45])
               .limit(200)
               .execute().data)
        conteo: dict[int, int] = {}
        for r in cts:
            conteo[r["cliente_id"]] = conteo.get(r["cliente_id"], 0) + 1
        for cid in sorted(conteo):
            print(f"    cliente {cid}: {conteo[cid]} contratos")
        if CLIENTE_44 not in conteo:
            print(f"    cliente 44: 0 contratos ✓")
    except Exception as e:
        print(f"    {e}")

    print(f"\n{sep}")
    if errores == 0:
        print("RESULTADO: ✓ Migración consistente — sin NULLs ni filas en cliente 44.")
    else:
        print(f"RESULTADO: ✗ {errores} tabla(s) con inconsistencias. Revisar.")
    print(sep)

    # Queries SQL de verificación (para ejecutar en Supabase SQL Editor)
    print("\n── Queries SQL de verificación (Supabase SQL Editor) ───────────────")
    print("SELECT id, nombre, activo FROM clientes WHERE id IN (44, 45);")
    print("SELECT cliente_id, nombre FROM plantas WHERE cliente_id = 45;")
    print("SELECT cliente_id, count(*) FROM contratos")
    print("  WHERE cliente_id IN (44, 45) GROUP BY cliente_id;")
    print("SELECT planta_id, count(*) FROM medidores")
    print("  WHERE cliente_id = 45 GROUP BY planta_id;")


if __name__ == "__main__":
    main()
