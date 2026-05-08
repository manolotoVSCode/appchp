#!/usr/bin/env python3
# scripts/migrar_facturas_a_contratos.py
"""
Migración: asocia facturas CFE y gas existentes a contratos.

Para cada cliente, agrupa las facturas sin contrato_id por su identificador
(numero_servicio para CFE, cuenta_contrato para gas), crea los contratos
necesarios y actualiza la columna contrato_id en cada factura.

Idempotente: se puede re-ejecutar sin crear duplicados ni cambiar asociaciones
existentes.

Uso:
    python scripts/migrar_facturas_a_contratos.py

Variables de entorno requeridas:
    SUPABASE_URL
    SUPABASE_KEY
"""
from __future__ import annotations

import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)


# ── Utilidades puras ──────────────────────────────────────────────────────────

def _letra_para_n(n: int) -> str:
    """Convierte índice base-0 en letra(s) al estilo Excel: 0→A, 25→Z, 26→AA…"""
    result = ""
    while True:
        result = chr(ord("A") + n % 26) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def _agrupar_por_identificador(
    facturas: list[dict], campo: str
) -> dict[str, list[dict]]:
    """Agrupa facturas por el valor del campo.
    Valores None o cadena vacía se mapean a 'SIN_IDENTIFICADOR'."""
    grupos: dict[str, list[dict]] = {}
    for f in facturas:
        id_real = (f.get(campo) or "").strip() or "SIN_IDENTIFICADOR"
        grupos.setdefault(id_real, []).append(f)
    return grupos


def _inicializar_contadores(contratos: list[dict]) -> dict[str, int]:
    """Cuenta contratos existentes por tipo, excluyendo explícitamente los de
    identificador_real == 'SIN_IDENTIFICADOR'. El resultado es el punto de
    partida para asignar letras consecutivas a contratos nuevos."""
    contadores: dict[str, int] = {"electrico": 0, "gas": 0}
    for c in contratos:
        if c["identificador_real"] != "SIN_IDENTIFICADOR":
            tipo = c.get("tipo", "")
            if tipo in contadores:
                contadores[tipo] += 1
    return contadores


# ── Lógica de migración ───────────────────────────────────────────────────────

def _obtener_o_crear_contrato(
    client,
    cliente_id: int,
    tipo: str,
    identificador_real: str,
    contadores: dict[str, int],
    cache: dict[tuple, int],
) -> tuple[int, bool]:
    """Devuelve (contrato_id, fue_creado).

    Busca primero en el cache local (contratos ya vistos en esta corrida o
    cargados al inicio del cliente). Si está en cache, reutiliza sin tocar DB.
    Si no está, crea el contrato y actualiza cache y contadores."""
    key = (tipo, identificador_real)
    if key in cache:
        return cache[key], False

    if identificador_real == "SIN_IDENTIFICADOR":
        nombre = "Sin identificador"
    else:
        nombre = f"Contrato {_letra_para_n(contadores[tipo])}"

    result = client.table("contratos").insert({
        "cliente_id": cliente_id,
        "nombre": nombre,
        "tipo": tipo,
        "identificador_real": identificador_real,
        "notas": None,
    }).execute()

    contrato_id: int = result.data[0]["id"]
    cache[key] = contrato_id

    if identificador_real != "SIN_IDENTIFICADOR":
        contadores[tipo] += 1

    return contrato_id, True


def _migrar_cliente(
    client, cliente_id: int, cliente_nombre: str, stats: dict
) -> None:
    """Procesa un cliente: crea los contratos necesarios y asocia sus facturas."""
    contratos = client.table("contratos").select(
        "id, tipo, identificador_real"
    ).eq("cliente_id", cliente_id).execute().data

    cache: dict[tuple, int] = {
        (c["tipo"], c["identificador_real"]): c["id"] for c in contratos
    }
    contadores = _inicializar_contadores(contratos)

    # ── CFE ───────────────────────────────────────────────────────────────────
    cfe_all = client.table("cfe_facturas").select(
        "id, numero_servicio, contrato_id"
    ).eq("cliente_id", cliente_id).execute().data

    cfe_sin = [f for f in cfe_all if f.get("contrato_id") is None]
    stats["facturas_saltadas"] += len(cfe_all) - len(cfe_sin)

    for id_real, grupo in _agrupar_por_identificador(cfe_sin, "numero_servicio").items():
        contrato_id, creado = _obtener_o_crear_contrato(
            client, cliente_id, "electrico", id_real, contadores, cache
        )
        if creado:
            stats["contratos_creados"]["electrico"] += 1
            logger.info(
                "Contrato creado: cliente_id=%d tipo=electrico id_real='%s'",
                cliente_id, id_real,
            )

        for f in grupo:
            try:
                client.table("cfe_facturas").update(
                    {"contrato_id": contrato_id}
                ).eq("id", f["id"]).execute()
                stats["facturas_asociadas"]["electrico"] += 1
                if id_real == "SIN_IDENTIFICADOR":
                    stats["facturas_sin_identificador"]["electrico"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["errores"].append(
                    f"[cliente {cliente_id} '{cliente_nombre}'] "
                    f"cfe_factura id={f['id']}: {exc}"
                )

    # ── Gas ───────────────────────────────────────────────────────────────────
    gas_all = client.table("gas_facturas").select(
        "id, cuenta_contrato, contrato_id"
    ).eq("cliente_id", cliente_id).execute().data

    gas_sin = [f for f in gas_all if f.get("contrato_id") is None]
    stats["facturas_saltadas"] += len(gas_all) - len(gas_sin)

    for id_real, grupo in _agrupar_por_identificador(gas_sin, "cuenta_contrato").items():
        contrato_id, creado = _obtener_o_crear_contrato(
            client, cliente_id, "gas", id_real, contadores, cache
        )
        if creado:
            stats["contratos_creados"]["gas"] += 1
            logger.info(
                "Contrato creado: cliente_id=%d tipo=gas id_real='%s'",
                cliente_id, id_real,
            )

        for f in grupo:
            try:
                client.table("gas_facturas").update(
                    {"contrato_id": contrato_id}
                ).eq("id", f["id"]).execute()
                stats["facturas_asociadas"]["gas"] += 1
                if id_real == "SIN_IDENTIFICADOR":
                    stats["facturas_sin_identificador"]["gas"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["errores"].append(
                    f"[cliente {cliente_id} '{cliente_nombre}'] "
                    f"gas_factura id={f['id']}: {exc}"
                )


def migrar(client) -> dict:
    """Punto de entrada de la migración. Acepta un cliente Supabase inyectado.

    Itera sobre todos los clientes en orden de id, procesa sus facturas sin
    contrato_id y devuelve un dict de estadísticas."""
    stats: dict = {
        "clientes_procesados": 0,
        "contratos_creados": {"electrico": 0, "gas": 0},
        "facturas_asociadas": {"electrico": 0, "gas": 0},
        "facturas_saltadas": 0,
        "facturas_sin_identificador": {"electrico": 0, "gas": 0},
        "errores": [],
    }

    clientes = (
        client.table("clientes").select("id, nombre").order("id").execute().data
    )
    for cliente in clientes:
        _migrar_cliente(client, cliente["id"], cliente["nombre"], stats)
        stats["clientes_procesados"] += 1

    return stats


# ── Salida por consola ────────────────────────────────────────────────────────

def _imprimir_resumen(stats: dict) -> None:
    linea = "═" * 49
    print(f"\n{linea}")
    print("  MIGRACIÓN FACTURAS → CONTRATOS — RESUMEN")
    print(linea)
    print(f"  Clientes procesados               : {stats['clientes_procesados']}")
    print(f"  Contratos creados (eléctrico)     : {stats['contratos_creados']['electrico']}")
    print(f"  Contratos creados (gas)           : {stats['contratos_creados']['gas']}")
    print(f"  Facturas asociadas (CFE)          : {stats['facturas_asociadas']['electrico']}")
    print(f"  Facturas asociadas (gas)          : {stats['facturas_asociadas']['gas']}")
    print(f"  Facturas ya asociadas (saltadas)  : {stats['facturas_saltadas']}")
    print(f"  Facturas → Sin identificador CFE  : {stats['facturas_sin_identificador']['electrico']}")
    print(f"  Facturas → Sin identificador gas  : {stats['facturas_sin_identificador']['gas']}")
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
