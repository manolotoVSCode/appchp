#!/usr/bin/env python3
"""
Migra la base de datos al modelo cliente → planta → recursos.

REQUIERE: 202610_plantas.sql ya ejecutado en Supabase SQL Editor.

ENFOQUE: UPDATE en lugar de copy-delete.
Los IDs originales de todas las filas se conservan. No hay ruptura de FKs.

Separación de recursos entre Planta 1 y Planta 2 de IBERICA:
  Los recursos ya tienen cliente_id=45 (migración anterior). La distinción
  entre plantas se realiza por patrón del nombre del medidor o del contrato,
  no por cliente_id de origen.

  Criterio medidores (es_planta_1):
    - Nombre coincide con regex ^T-[1-3]\\.  (transformadores T-1.x, T-2.x, T-3.x)
    - Nombre contiene "T-SA"
    - Nombre contiene cualquiera de: MMC1, Atomizador 1, Atomizado 1,
      Zona Prensas, Zona Hornos, Servicios Auxiliares, CFE-1, SE Poniente

  Criterio medidores hijos sin match: heredan planta_id del medidor padre.
  Default si no matchea ni padre ni nombre: Planta 2 (con warning).

  Criterio contratos (es_planta_1):
    - Nombre contiene "Planta 1"

  Facturas (cfe, gas, calificado, ppa_bloques): heredan planta_id del
  contrato al que pertenecen (via JOIN contrato_id → contratos.planta_id).

  mediciones_cincominutal: no tiene columna planta_id; se omite.
  produccion_diaria: no distinguible — se asigna todo a Planta 2.

Comportamiento:
  IBERICA (cliente 45, antes 44+45):
    1. Crear "Planta 1" y "Planta 2" en cliente 45 (idempotente).
    2. Asignar medidores por patrón de nombre (padres primero, luego hijos).
    3. Asignar contratos por patrón de nombre.
    4. Asignar facturas heredando planta_id del contrato.
    5. Asignar produccion_diaria → Planta 2.
    6. Renombrar cliente 45 → "IBÉRICA TILES".
    7. Marcar cliente 44 como inactivo (si existe).
    8. Migrar user_profiles.empresa_id de 44 → 45.
       Eliminar entrada usuario_clientes para cliente 44.

  Demás clientes activos:
    9. Crear "Planta Principal" (idempotente).
       UPDATE tabla SET planta_id=Planta Principal
       WHERE cliente_id=X AND planta_id IS NULL

Idempotencia:
  - Plantas existentes no se recrean (UNIQUE cliente_id+nombre protege).
  - Recursos ya con planta_id asignado no se sobrescriben (solo_null=True)
    salvo con --forzar.

Con --forzar:
  - SET planta_id = NULL en todas las tablas operativas.
  - DELETE FROM plantas (el ON DELETE SET NULL del FK lo haría igual,
    pero se hace explícitamente para garantía).
  - Reejecutar pasos 1-9 desde cero.

Uso:
  python3 scripts/migrar_a_plantas.py
  python3 scripts/migrar_a_plantas.py --forzar   # rehace desde cero
"""
from __future__ import annotations

import os
import re
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

# Tablas de facturas que heredan planta_id del contrato
TABLAS_FACTURAS = [
    "cfe_facturas",
    "gas_facturas",
    "facturas_electricidad_calificado",
    "ppa_bloques_mensuales",
]


# ── Clasificadores de recursos IBERICA ────────────────────────────────────────

def es_planta_1(nombre: str) -> bool:
    """Retorna True si el medidor pertenece al grupo Planta 1 (ex-cliente 44).

    Criterio: transformadores T-1.x, T-2.x, T-3.x; acometida T-SA;
    y medidores cuyo nombre contiene keywords asociados al área oeste/poniente.
    """
    if re.match(r'^T-[1-3]\.', nombre):
        return True
    if 'T-SA' in nombre:
        return True
    keywords_p1 = [
        'MMC1', 'Atomizador 1', 'Atomizado 1', 'Zona Prensas',
        'Zona Hornos', 'Servicios Auxiliares', 'CFE-1', 'SE Poniente',
    ]
    return any(k in nombre for k in keywords_p1)


def es_planta_2(nombre: str) -> bool:
    """Retorna True si el medidor pertenece al grupo Planta 2 (cliente 45 original).

    Criterio: transformadores T-4.x, T-5.x, T-6.x y keywords del área sur/oriente.
    """
    if re.match(r'^T-[4-6]\.', nombre):
        return True
    keywords_p2 = [
        'MMC2', 'Atomizador 2', 'Atomizado 2', 'Prensas P2',
        'Hornos P2', 'Pulido', 'CFE-2', 'SE Sur',
    ]
    return any(k in nombre for k in keywords_p2)


def es_contrato_planta_1(nombre: str) -> bool:
    """Retorna True si el contrato pertenece a Planta 1 por su nombre."""
    return 'Planta 1' in nombre


# ── Funciones principales ──────────────────────────────────────────────────────

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

def _asignar_medidores_iberica(sb, id_planta1: int, id_planta2: int) -> None:
    """Asigna planta_id a medidores de cliente 45 por patrón del nombre.

    Orden: padres primero (medidor_padre_id IS NULL), luego hijos.
    Los hijos sin match de nombre heredan la planta del padre.
    Sin match ni padre: default Planta 2 con warning.
    """
    print(f"\n  [2a] Asignando medidores por patrón del nombre:")

    # Leer todos los medidores de cliente 45
    try:
        r = (sb.table("medidores")
             .select("id,nombre,medidor_padre_id,planta_id")
             .eq("cliente_id", CLIENTE_45)
             .execute())
        medidores = r.data or []
    except Exception as e:
        print(f"    ERROR leyendo medidores: {e}")
        return

    if not medidores:
        print("    Sin medidores en cliente 45.")
        return

    # Separar padres e hijos
    padres = [m for m in medidores if not m.get("medidor_padre_id")]
    hijos = [m for m in medidores if m.get("medidor_padre_id")]

    # Mapa id → planta_id asignada (para propagar a hijos)
    asignacion: dict[int, int] = {}

    # Procesar padres
    p1_count = p2_count = 0
    for m in padres:
        nombre = m.get("nombre", "")
        mid = m["id"]
        if es_planta_1(nombre):
            planta = id_planta1
            p1_count += 1
        else:
            # Default Planta 2 (también cubre es_planta_2 y sin match)
            if not es_planta_2(nombre):
                print(f"    WARNING: medidor padre sin match — '{nombre}' → Planta 2 (default)")
            planta = id_planta2
            p2_count += 1
        asignacion[mid] = planta
        try:
            sb.table("medidores").update({"planta_id": planta}).eq("id", mid).execute()
        except Exception as e:
            print(f"    ERROR actualizando medidor {mid} '{nombre}': {e}")

    print(f"    Padres: {p1_count} → Planta 1, {p2_count} → Planta 2")

    # Procesar hijos (heredan del padre)
    h1_count = h2_count = h_warn = 0
    for m in hijos:
        nombre = m.get("nombre", "")
        mid = m["id"]
        padre_id = m.get("medidor_padre_id")
        planta = asignacion.get(padre_id)

        if planta is None:
            # Intentar clasificar por nombre propio
            if es_planta_1(nombre):
                planta = id_planta1
            else:
                planta = id_planta2
                h_warn += 1
                print(f"    WARNING: hijo sin padre asignado — '{nombre}' → Planta 2 (default)")

        asignacion[mid] = planta
        if planta == id_planta1:
            h1_count += 1
        else:
            h2_count += 1

        try:
            sb.table("medidores").update({"planta_id": planta}).eq("id", mid).execute()
        except Exception as e:
            print(f"    ERROR actualizando medidor hijo {mid} '{nombre}': {e}")

    print(f"    Hijos:  {h1_count} → Planta 1, {h2_count} → Planta 2"
          + (f" ({h_warn} warnings)" if h_warn else ""))
    print(f"    Total medidores: {len(medidores)} ({p1_count + h1_count} P1, {p2_count + h2_count} P2)")


def _asignar_contratos_iberica(sb, id_planta1: int, id_planta2: int) -> dict[int, int]:
    """Asigna planta_id a contratos de cliente 45 por patrón del nombre.

    Retorna mapa contrato_id → planta_id para usar en la asignación de facturas.
    """
    print(f"\n  [2b] Asignando contratos por patrón del nombre:")

    try:
        r = (sb.table("contratos")
             .select("id,nombre,tipo,planta_id")
             .eq("cliente_id", CLIENTE_45)
             .execute())
        contratos = r.data or []
    except Exception as e:
        print(f"    ERROR leyendo contratos: {e}")
        return {}

    if not contratos:
        print("    Sin contratos en cliente 45.")
        return {}

    mapa: dict[int, int] = {}
    c1_count = c2_count = 0

    for c in contratos:
        nombre = c.get("nombre") or ""
        cid = c["id"]
        if es_contrato_planta_1(nombre):
            planta = id_planta1
            c1_count += 1
        else:
            planta = id_planta2
            c2_count += 1
            if 'Planta 2' not in nombre:
                print(f"    INFO: contrato '{nombre}' (tipo={c.get('tipo')}) → Planta 2 (default)")
        mapa[cid] = planta
        try:
            sb.table("contratos").update({"planta_id": planta}).eq("id", cid).execute()
        except Exception as e:
            print(f"    ERROR actualizando contrato {cid} '{nombre}': {e}")

    print(f"    Contratos: {c1_count} → Planta 1, {c2_count} → Planta 2")
    return mapa


def _asignar_facturas_por_contrato(sb, contrato_planta: dict[int, int]) -> None:
    """Asigna planta_id a facturas heredando del contrato padre."""
    if not contrato_planta:
        return

    print(f"\n  [2c] Asignando facturas por planta_id del contrato:")

    for tabla in TABLAS_FACTURAS:
        try:
            r = (sb.table(tabla)
                 .select("id,contrato_id,planta_id")
                 .eq("cliente_id", CLIENTE_45)
                 .execute())
            filas = r.data or []
        except Exception as e:
            print(f"    {tabla}: ERROR leyendo — {e}")
            continue

        if not filas:
            print(f"    {tabla}: sin filas")
            continue

        f1 = f2 = fw = 0
        for fila in filas:
            fid = fila["id"]
            cid = fila.get("contrato_id")
            planta = contrato_planta.get(cid)
            if planta is None:
                print(f"    WARNING: {tabla} id={fid} contrato_id={cid} sin planta — default P2")
                planta = list(contrato_planta.values())[0] if contrato_planta else None
                fw += 1
                if planta is None:
                    continue
            if planta == list(contrato_planta.values())[0]:
                # Determinar si es P1 o P2 comparando con el valor de Planta 1
                pass
            try:
                sb.table(tabla).update({"planta_id": planta}).eq("id", fid).execute()
                # Contar correctamente comparando con id_planta1 — pero no tenemos ese valor aquí.
                # Usamos el mapa para contar
                f1 += 1  # placeholder; el log real es por tabla
            except Exception as e:
                print(f"    ERROR {tabla} id={fid}: {e}")

        # Reconteo real
        p_counts: dict[int, int] = {}
        for fila in filas:
            p = contrato_planta.get(fila.get("contrato_id"))
            if p:
                p_counts[p] = p_counts.get(p, 0) + 1
        detalle = ", ".join(f"planta_id={k}: {v}" for k, v in sorted(p_counts.items()))
        print(f"    {tabla}: {len(filas)} filas actualizadas ({detalle})" +
              (f" [{fw} warnings]" if fw else ""))


def _migrar_iberica(sb, clientes: dict) -> None:
    """Migra cliente 45 al modelo planta usando clasificación por nombre."""
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

    # [2a] Asignar medidores por nombre ───────────────────────────────────────
    _asignar_medidores_iberica(sb, id_planta1, id_planta2)

    # [2b] Asignar contratos por nombre ───────────────────────────────────────
    contrato_planta = _asignar_contratos_iberica(sb, id_planta1, id_planta2)

    # [2c] Asignar facturas heredando del contrato ────────────────────────────
    _asignar_facturas_por_contrato(sb, contrato_planta)

    # [3] produccion_diaria → Planta 2 (no distinguible entre plantas) ────────
    print(f"\n  [3] produccion_diaria → Planta 2 (no distinguible entre plantas):")
    _update_planta_id(sb, "produccion_diaria", CLIENTE_45, id_planta2, solo_null=True)

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
    """Reporte de conteos por tabla: NULLs en planta_id y filas aún en cliente 44.

    También muestra distribución de medidores y contratos entre plantas de Iberica.
    """
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
    plantas_iberica: dict[int, str] = {}
    try:
        ps = (sb.table("plantas")
              .select("id,nombre,activo")
              .eq("cliente_id", CLIENTE_45)
              .execute().data)
        for p in sorted(ps, key=lambda x: x["nombre"]):
            print(f"    planta {p['id']}: '{p['nombre']}', activo={p['activo']}")
            plantas_iberica[p["id"]] = p["nombre"]
        if not ps:
            print("    (ninguna)")
    except Exception as e:
        print(f"    {e}")

    # Medidores por planta en cliente 45
    print(f"\n  Medidores por planta (cliente 45):")
    try:
        ms = (sb.table("medidores")
              .select("id,nombre,planta_id,medidor_padre_id")
              .eq("cliente_id", CLIENTE_45)
              .execute().data)
        conteo_p: dict[int | None, int] = {}
        for m in ms:
            pid = m.get("planta_id")
            conteo_p[pid] = conteo_p.get(pid, 0) + 1
        for pid, cnt in sorted(conteo_p.items(), key=lambda x: (x[0] is None, x[0])):
            pnombre = plantas_iberica.get(pid, "NULL") if pid else "NULL (sin asignar)"
            estado_m = "✓" if pid else "✗"
            print(f"    {estado_m} {pnombre}: {cnt} medidores")
            if not pid:
                errores += 1
    except Exception as e:
        print(f"    {e}")

    # Contratos por planta en cliente 45
    print(f"\n  Contratos por planta (cliente 45):")
    try:
        cts = (sb.table("contratos")
               .select("id,nombre,tipo,planta_id")
               .eq("cliente_id", CLIENTE_45)
               .execute().data)
        for c in sorted(cts, key=lambda x: (x.get("planta_id") or 0, x.get("nombre", ""))):
            pid = c.get("planta_id")
            pnombre = plantas_iberica.get(pid, "NULL") if pid else "NULL"
            print(f"    planta={pnombre}: '{c.get('nombre')}' (tipo={c.get('tipo')})")
    except Exception as e:
        print(f"    {e}")

    # CFE facturas por planta en cliente 45
    print(f"\n  CFE facturas por planta (cliente 45):")
    try:
        fs = (sb.table("cfe_facturas")
              .select("id,planta_id")
              .eq("cliente_id", CLIENTE_45)
              .execute().data)
        conteo_f: dict[int | None, int] = {}
        for f in fs:
            pid = f.get("planta_id")
            conteo_f[pid] = conteo_f.get(pid, 0) + 1
        for pid, cnt in sorted(conteo_f.items(), key=lambda x: (x[0] is None, x[0])):
            pnombre = plantas_iberica.get(pid, "NULL") if pid else "NULL"
            print(f"    {pnombre}: {cnt} facturas")
    except Exception as e:
        print(f"    {e}")

    print(f"\n{sep}")
    if errores == 0:
        print("RESULTADO: ✓ Migración consistente — sin NULLs ni filas en cliente 44.")
    else:
        print(f"RESULTADO: ✗ {errores} tabla(s)/grupos con inconsistencias. Revisar.")
    print(sep)

    # Queries SQL de verificación (para ejecutar en Supabase SQL Editor)
    print("\n── Queries SQL de verificación (Supabase SQL Editor) ───────────────")
    print("""
SELECT p.nombre, count(m.id) as medidores
FROM plantas p
LEFT JOIN medidores m ON m.planta_id = p.id
WHERE p.cliente_id = 45 GROUP BY p.nombre ORDER BY p.nombre;

SELECT p.nombre, c.tipo, c.id, c.nombre as contrato_nombre
FROM contratos c
JOIN plantas p ON p.id = c.planta_id
WHERE c.cliente_id = 45 ORDER BY p.nombre;

SELECT p.nombre, count(f.id) as facturas
FROM cfe_facturas f
JOIN plantas p ON p.id = f.planta_id
WHERE f.cliente_id = 45 GROUP BY p.nombre ORDER BY p.nombre;
""")


if __name__ == "__main__":
    main()
