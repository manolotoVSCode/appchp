#!/usr/bin/env python3
"""Seed masivo de telemetría jerárquica — Ibérica Tiles Planta 1 (c44) y Planta 2 (c45).

Uso:
    python scripts/seed_iberica.py              # seed completo (si no existe)
    python scripts/seed_iberica.py --forzar     # borrar y resembrar desde cero
    python scripts/seed_iberica.py --gap        # rellenar gap temporal sin borrar nada
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


def _verificar_migraciones() -> bool:
    """Verifica que las vistas materializadas 5-min y horaria existen en Supabase.

    Intenta hacer un SELECT de 1 fila en cada vista. Si la tabla no existe,
    Supabase lanza una excepción con "relation ... does not exist".
    Retorna True si ambas vistas están accesibles, False en caso contrario.
    """
    from storage.repository import _supabase

    vistas = ["mediciones_agregadas_5min", "mediciones_agregadas_horarias"]
    for vista in vistas:
        try:
            _supabase.table(vista).select("medidor_id").limit(1).execute()
        except Exception as e:
            msg = str(e).lower()
            if "does not exist" in msg or "relation" in msg or "42p01" in msg:
                print(f"⛔  Vista materializada faltante: {vista}")
                print("    Ejecutar primero: storage/migrations/202609_mediciones_5min_horarias.sql")
                return False
    return True


import json as _json_mod

_CHECKPOINT_FILE = "/tmp/seed_iberica_progress.json"


def _leer_checkpoint() -> dict:
    """Retorna checkpoint guardado o estructura vacía."""
    try:
        with open(_CHECKPOINT_FILE) as _f:
            return _json_mod.load(_f)
    except (FileNotFoundError, _json_mod.JSONDecodeError):
        return {"medidor_ids_completados": [], "ultimo_dia_por_medidor": {}}


def _guardar_checkpoint(completados: list[int], ultimo_dia: dict) -> None:
    """Escribe checkpoint en disco."""
    with open(_CHECKPOINT_FILE, "w") as _f:
        _json_mod.dump(
            {
                "medidor_ids_completados": completados,
                "ultimo_dia_por_medidor": {str(k): v for k, v in ultimo_dia.items()},
            },
            _f,
        )


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

    n_intervalo = dias * 24 * 12   # 5-min → 12/h → 2016 por 7 días
    total = 0
    for carga in cargas:
        meds = generar_mediciones_por_carga(carga, desde, n=n_intervalo, intervalo=5)
        total += insertar_mediciones_batch(meds)
    return total


def _sembrar_produccion_diaria(planta: dict, dias: int, forzar: bool) -> int:
    """Genera registros de produccion_diaria para el cliente. Retorna n insertados."""
    import random as _rnd
    from storage.repository import _supabase

    cid   = planta["cliente_id"]
    hoy   = datetime.now(timezone.utc).date()
    fechas = [hoy - timedelta(days=i) for i in range(dias)]
    # También incluir el mismo día del mes anterior (para comparativa)
    from datetime import date as _date
    mes_anterior_dia = _date(hoy.year if hoy.month > 1 else hoy.year - 1,
                             (hoy.month - 1) if hoy.month > 1 else 12,
                             min(hoy.day, 28))
    if mes_anterior_dia not in fechas:
        fechas.append(mes_anterior_dia)

    # Verificar registros existentes si no --forzar
    if forzar:
        fechas_str = [f.isoformat() for f in fechas]
        _supabase.table("produccion_diaria").delete().eq("cliente_id", cid).in_(
            "fecha", fechas_str
        ).execute()
    else:
        # Obtener las fechas ya sembradas
        resp = (
            _supabase.table("produccion_diaria")
            .select("fecha")
            .eq("cliente_id", cid)
            .limit(20000)
            .execute()
        )
        ya_sembradas = {r["fecha"] for r in (resp.data or [])}
        fechas = [f for f in fechas if f.isoformat() not in ya_sembradas]

    if not fechas:
        return 0

    registros = []
    for fecha in fechas:
        rng = _rnd.Random(cid * 10_000 + fecha.toordinal())
        dia_semana = fecha.weekday()   # 0=lunes, 6=domingo
        if dia_semana == 6:            # domingo
            m2 = 0.0
        elif dia_semana == 5:          # sábado
            m2 = rng.uniform(2_500, 3_500)
        else:                          # lunes-viernes
            m2 = rng.uniform(4_200, 5_500) * rng.uniform(0.9, 1.1)
        registros.append({
            "cliente_id": cid,
            "fecha": fecha.isoformat(),
            "m2_producidos": round(m2, 2),
        })

    # Insertar por lotes de 100
    n = 0
    for inicio in range(0, len(registros), 100):
        lote = registros[inicio:inicio + 100]
        _supabase.table("produccion_diaria").upsert(lote, on_conflict="cliente_id,fecha").execute()
        n += len(lote)
    return n


def _sembrar_historico_60_dias(planta: dict, forzar: bool) -> int:
    """Genera 60 días de mediciones a resolución 5-min (288 muestras/día) por CBT.

    12 CBTs × 60 días × 288 = 207,360 muestras totales (ambas plantas).
    Checkpointing en /tmp/seed_iberica_progress.json.
    Retry con backoff exponencial (hasta 5 intentos) en errores de red.
    Si forzar=False y el medidor ya aparece en el checkpoint, salta.
    """
    from storage.repository import _supabase

    if not _verificar_migraciones():
        print("  ⚠  Migraciones pendientes: seed histórico abortado.")
        return 0

    cid = planta["cliente_id"]
    ahora_utc = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    desde_60d = ahora_utc - timedelta(days=60)
    desde_60d_iso = desde_60d.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Cargas finales
    resp = (
        _supabase.table("medidores")
        .select("*")
        .eq("cliente_id", cid)
        .eq("punto_medicion", "carga_final")
        .limit(20000)
        .execute()
    )
    cargas = resp.data or []
    if not cargas:
        return 0

    checkpoint = (
        {"medidor_ids_completados": [], "ultimo_dia_por_medidor": {}}
        if forzar
        else _leer_checkpoint()
    )
    completados: set[int] = set(checkpoint["medidor_ids_completados"])
    ultimo_dia: dict[int, int] = {
        int(k): v
        for k, v in checkpoint.get("ultimo_dia_por_medidor", {}).items()
    }

    total = 0

    for carga in cargas:
        mid = carga["id"]
        nombre = carga.get("nombre", str(mid))

        if mid in completados and not forzar:
            print(f"    CBT {mid} ({nombre}): ya completado, saltando.")
            continue

        if forzar:
            _supabase.table("mediciones_tiempo_real").delete().eq(
                "medidor_id", mid
            ).gte("timestamp", desde_60d_iso).execute()
            ultimo_dia.pop(mid, None)

        dia_inicio = 0 if forzar else ultimo_dia.get(mid, 0)

        for dia in range(dia_inicio, 60):
            dia_desde = desde_60d + timedelta(days=dia)
            meds = generar_mediciones_por_carga(carga, dia_desde, n=288, intervalo=5)

            for intento in range(5):
                try:
                    n_ins = insertar_mediciones_batch(meds)
                    total += n_ins
                    break
                except Exception as exc:
                    espera = 2 ** intento
                    print(
                        f"    CBT {mid}: error intento {intento + 1}/5, "
                        f"reintentando en {espera}s — {exc}"
                    )
                    time.sleep(espera)
                    if intento == 4:
                        raise

            if (dia + 1) % 10 == 0:
                ultimo_dia[mid] = dia + 1
                _guardar_checkpoint(list(completados), ultimo_dia)
                print(
                    f"    CBT {mid} ({nombre}): {dia + 1}/60 días procesados "
                    f"({(dia + 1) * 288} muestras este medidor)…"
                )

        completados.add(mid)
        ultimo_dia[mid] = 60
        _guardar_checkpoint(list(completados), ultimo_dia)
        print(f"    CBT {mid} ({nombre}): ✓ completado (17,280 muestras).")

    # Limpiar checkpoint
    try:
        os.remove(_CHECKPOINT_FILE)
    except FileNotFoundError:
        pass

    return total


def _rellenar_gap(planta: dict) -> list[dict]:
    """Rellena el gap temporal desde max(timestamp)+5min hasta ahora para cada CBT.

    Retorna lista de dicts por CBT: {nombre, medidor_id, desde, hasta, insertadas}.
    No borra datos existentes. Idempotente: arranca desde max(timestamp) actual.
    """
    from storage.repository import _supabase

    cid = planta["cliente_id"]
    ahora = datetime.now(timezone.utc).replace(microsecond=0)

    resp = (
        _supabase.table("medidores")
        .select("*")
        .eq("cliente_id", cid)
        .eq("punto_medicion", "carga_final")
        .limit(20000)
        .execute()
    )
    cargas = resp.data or []

    resultados = []
    for carga in cargas:
        mid = carga["id"]
        nombre = carga.get("nombre", str(mid))

        # Timestamp máximo existente para este medidor
        resp_max = (
            _supabase.table("mediciones_tiempo_real")
            .select("timestamp")
            .eq("medidor_id", mid)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if not resp_max.data:
            resultados.append({"nombre": nombre, "medidor_id": mid,
                                "desde": None, "hasta": None, "insertadas": 0,
                                "nota": "sin datos previos"})
            continue

        ts_max_str = resp_max.data[0]["timestamp"]
        # Supabase devuelve UTC con variantes "+00", "+00:00" o "Z".
        # Stripeamos cualquier offset y forzamos UTC para compatibilidad Python 3.9+.
        ts_naive_str = ts_max_str.replace("Z", "").split("+")[0].strip()
        ts_max = datetime.fromisoformat(ts_naive_str).replace(tzinfo=timezone.utc)

        # Primer punto del gap = max + 5 min
        gap_desde = ts_max + timedelta(minutes=5)

        if gap_desde >= ahora:
            resultados.append({"nombre": nombre, "medidor_id": mid,
                                "desde": gap_desde.isoformat(),
                                "hasta": ahora.isoformat(), "insertadas": 0,
                                "nota": "sin gap"})
            continue

        # Calcular n a intervalos de 5 minutos
        diff_min = int((ahora - gap_desde).total_seconds() / 60)
        n = diff_min // 5
        if n <= 0:
            resultados.append({"nombre": nombre, "medidor_id": mid,
                                "desde": gap_desde.isoformat(),
                                "hasta": ahora.isoformat(), "insertadas": 0,
                                "nota": "gap < 5min"})
            continue

        meds = generar_mediciones_por_carga(carga, gap_desde, n=n, intervalo=5)

        # Insertar en chunks de 1000
        total_ins = 0
        for i in range(0, len(meds), 1000):
            total_ins += insertar_mediciones_batch(meds[i:i + 1000])

        resultados.append({
            "nombre": nombre,
            "medidor_id": mid,
            "desde": gap_desde.isoformat(),
            "hasta": ahora.isoformat(),
            "insertadas": total_ins,
        })
        print(f"    CBT {mid} ({nombre}): {total_ins} muestras "
              f"[{gap_desde.strftime('%H:%M')} → {ahora.strftime('%H:%M')} UTC]")

    return resultados


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed masivo de telemetría jerárquica Ibérica Tiles."
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Borrar datos existentes y resembrar desde cero.",
    )
    parser.add_argument(
        "--gap",
        action="store_true",
        help="Rellenar el gap temporal desde max(timestamp)+5min hasta ahora. "
             "No borra datos existentes.",
    )
    args = parser.parse_args()

    t0 = time.time()

    # ── Modo --gap ────────────────────────────────────────────────────────────
    if args.gap:
        print("=== Seed Ibérica Tiles — Rellenar gap temporal ===")
        if not _verificar_existencia():
            print("⛔  Árbol no sembrado. Ejecutar seed completo primero.")
            sys.exit(1)

        total_gap = 0
        for planta in PLANTAS:
            cid = planta["cliente_id"]
            print(f"\n→ Planta cliente_id={cid}…")
            filas = _rellenar_gap(planta)
            total_gap += sum(r["insertadas"] for r in filas)

        # Refrescar vistas materializadas
        from storage.repository import _supabase
        print("\n→ Refrescando vistas materializadas…")
        try:
            _supabase.rpc("refresh_mediciones_5min", {}).execute()
            print("    mediciones_agregadas_5min: OK")
        except Exception:
            pass
        try:
            _supabase.rpc("refresh_mediciones_horarias", {}).execute()
            print("    mediciones_agregadas_horarias: OK")
        except Exception:
            pass
        print("    (Si las RPCs no existen, ejecutar manualmente:")
        print("     REFRESH MATERIALIZED VIEW CONCURRENTLY mediciones_agregadas_5min;")
        print("     REFRESH MATERIALIZED VIEW CONCURRENTLY mediciones_agregadas_horarias;)")

        elapsed = time.time() - t0
        print(f"\n=== Gap rellenado en {elapsed:.1f}s — {total_gap} muestras totales ===")
        sys.exit(0)

    # ── Modo normal / --forzar ────────────────────────────────────────────────
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
        np = _sembrar_produccion_diaria(planta, dias=60, forzar=args.forzar)
        nh = _sembrar_historico_60_dias(planta, forzar=args.forzar)
        totales["produccion"] = totales.get("produccion", 0) + np
        totales["historico"]  = totales.get("historico", 0)  + nh
        print(f"    Producción diaria: {np} registros  |  Histórico 60 días: {nh} muestras")

    elapsed = time.time() - t0
    print(f"\n=== Completado en {elapsed:.1f}s ===")
    print(f"  Acometidas:      {totales['acometidas']}")
    print(f"  Transformadores: {totales['transformadores']}")
    print(f"  Cargas finales:  {totales['cargas']}")
    print(f"  Mediciones:      {totales['mediciones']}")
    print(f"  Producción diaria: {totales.get('produccion', 0)} registros")
    print(f"  Histórico 60 días: {totales.get('historico', 0)} muestras")


if __name__ == "__main__":
    main()
