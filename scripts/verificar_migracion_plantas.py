#!/usr/bin/env python3
"""
Verifica el estado de la migración a plantas.

Reporta:
  - Clientes activos vs inactivos.
  - Plantas por cliente.
  - Filas con planta_id NULL en cada tabla operativa (esperado: 0).
  - Filas con inconsistencia cliente_id ≠ plantas.cliente_id.
  - Usuarios en user_profiles y usuario_clientes.

Uso:
  python3 scripts/verificar_migracion_plantas.py
"""

import os
from dotenv import load_dotenv

load_dotenv()
from supabase import create_client  # noqa: E402

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
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    sep = "─" * 60

    # ── 1. Clientes activos vs inactivos ─────────────────────────────────────
    print(f"\n{sep}")
    print("1. CLIENTES")
    print(sep)
    clientes_r = sb.table("clientes").select("id,nombre,activo").execute().data
    activos   = [c for c in clientes_r if c.get("activo", True)]
    inactivos = [c for c in clientes_r if not c.get("activo", True)]
    print(f"  Activos  ({len(activos)}): {[f\"{c['id']}: {c['nombre']}\" for c in activos]}")
    print(f"  Inactivos({len(inactivos)}): {[f\"{c['id']}: {c['nombre']}\" for c in inactivos]}")

    # ── 2. Plantas por cliente ────────────────────────────────────────────────
    print(f"\n{sep}")
    print("2. PLANTAS POR CLIENTE")
    print(sep)
    try:
        plantas_r = sb.table("plantas").select("id,cliente_id,nombre,activo").execute().data
        by_client: dict[int, list] = {}
        for p in plantas_r:
            by_client.setdefault(p["cliente_id"], []).append(p)
        for cid, ps in sorted(by_client.items()):
            nombre_c = next((c["nombre"] for c in clientes_r if c["id"] == cid), f"?{cid}")
            print(f"  cliente {cid} ({nombre_c}): {[p['nombre'] for p in ps]}")
        if not plantas_r:
            print("  (sin plantas — ¿ejecutaste el script de migración?)")
    except Exception as e:
        print(f"  ERROR: {e}")
        plantas_r = []

    # ── 3. NULLs en planta_id por tabla ──────────────────────────────────────
    print(f"\n{sep}")
    print("3. planta_id NULL EN TABLAS OPERATIVAS (esperado: 0 en todas)")
    print(sep)
    total_errores = 0
    for tabla in TABLAS_OPERATIVAS:
        try:
            filas = sb.table(tabla).select("id,cliente_id,planta_id").execute().data
            nulls = [r for r in filas if r.get("planta_id") is None]
            estado = "✓" if not nulls else "✗"
            print(f"  {estado} {tabla}: {len(filas)} filas, {len(nulls)} con planta_id NULL")
            if nulls:
                total_errores += 1
                muestra = nulls[:3]
                for r in muestra:
                    print(f"      ↳ id={r.get('id')}, cliente_id={r.get('cliente_id')}")
        except Exception as e:
            print(f"  ? {tabla}: {e}")

    # ── 4. Consistencia cliente_id ↔ plantas.cliente_id ───────────────────────
    print(f"\n{sep}")
    print("4. CONSISTENCIA cliente_id ↔ plantas.cliente_id (esperado: 0 incongruencias)")
    print(sep)
    planta_by_id = {p["id"]: p["cliente_id"] for p in plantas_r}
    for tabla in TABLAS_OPERATIVAS:
        try:
            filas = sb.table(tabla).select("id,cliente_id,planta_id").execute().data
            inconsistentes = [
                r for r in filas
                if r.get("planta_id") and
                   planta_by_id.get(r["planta_id"]) != r["cliente_id"]
            ]
            estado = "✓" if not inconsistentes else "✗"
            print(f"  {estado} {tabla}: {len(inconsistentes)} incongruencias")
            for r in inconsistentes[:3]:
                pid = r.get("planta_id")
                print(f"      ↳ id={r.get('id')}, cliente_id={r.get('cliente_id')}, "
                      f"planta_id={pid} (planta.cliente_id={planta_by_id.get(pid)})")
        except Exception as e:
            print(f"  ? {tabla}: {e}")

    # ── 5. Usuarios ──────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("5. USUARIOS")
    print(sep)
    try:
        users = sb.table("user_profiles").select("email,rol,empresa_id,activo").execute().data
        for u in users:
            print(f"  {u['email']} / {u['rol']} / empresa_id={u['empresa_id']} / activo={u['activo']}")
    except Exception as e:
        print(f"  {e}")

    print(f"\n{sep}")
    print("5b. usuario_clientes")
    print(sep)
    try:
        uc = sb.table("usuario_clientes").select("user_id,cliente_id").execute().data
        for row in uc:
            print(f"  user_id={row['user_id'][:8]}…  cliente_id={row['cliente_id']}")
    except Exception as e:
        print(f"  {e}")

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    if total_errores == 0:
        print("RESULTADO: ✓ Migración consistente — sin planta_id NULL.")
    else:
        print(f"RESULTADO: ✗ {total_errores} tabla(s) con planta_id NULL. Revisar.")
    print(sep)


if __name__ == "__main__":
    main()
