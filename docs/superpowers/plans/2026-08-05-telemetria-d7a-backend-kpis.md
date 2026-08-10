# Telemetría D7-A — Backend de KPIs de Paneles

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el backend de KPIs del dashboard de telemetría: tabla `produccion_diaria`, módulo de cálculo, seed extendido y bloque `kpis_paneles` en el endpoint existente.

**Architecture:** Nuevo módulo `calc/telemetria_kpis.py` con funciones puras (sin DB); el endpoint en `web/app.py` las invoca con los datos ya fetcheados. La tabla `produccion_diaria` se accede vía una nueva función de repositorio. Todo el cálculo del periodo anterior usa el mismo patrón de fetch existente (−30 días). El seed extiende el script existente con dos bloques nuevos (producción + histórico de mediciones).

**Tech Stack:** Python 3.11, Flask 3.x, supabase-py SDK, pytest + unittest.mock.

## Global Constraints

- Acceso a Supabase exclusivamente vía `storage.repository` (o `_supabase` dentro de scripts CLI). Sin psycopg2.
- `.limit(20000)` en toda lectura de Supabase.
- No modificar frontend (JS, HTML, CSS) en esta entrega.
- No tocar Contabilidad, Cogeneración, parsers, mediciones_cincominutal, ni módulos ajenos a telemetría.
- No introducir dependencias externas (solo stdlib + dependencias ya en requirements.txt).
- Sin decoradores de acceso: la verificación `abort(404)` en el endpoint ya existe.
- Nombres de campos JSON del endpoint deben coincidir exactamente con los del spec (snake_case).

---

## Archivos que cambian

| Archivo | Cambio |
|---------|--------|
| `storage/migrations/202608_produccion_diaria.sql` | Nuevo — DDL de la tabla |
| `calc/telemetria_kpis.py` | Nuevo — 6 funciones de cálculo |
| `tests/test_telemetria_kpis.py` | Nuevo — 9 tests (a-i) |
| `storage/repository.py` | Añadir `obtener_produccion_diaria` |
| `scripts/seed_iberica.py` | Extender con producción y mediciones históricas |
| `web/app.py` | Añadir bloque `kpis_paneles` al endpoint existente |
| `CHANGELOG.md` | Entrada v2.79.0 |

---

### Task 1: Módulo de cálculo + tests unitarios (a-f)

**Files:**
- Create: `calc/telemetria_kpis.py`
- Create: `tests/test_telemetria_kpis.py` (solo tests a-f en este task)

**Interfaces:**
- Produces (consumidas por Task 3):
  - `calcular_kpis_energeticos(mediciones, potencia_nominal_kw)` → `dict`
  - `calcular_kpis_economicos(energia_kwh, precio_mxn_kwh, costo_cliente_factura_total, baseline_kwh)` → `dict`
  - `calcular_kpis_produccion(energia_kwh, costo_total_mxn, m2_producidos_atribuidos)` → `dict`
  - `atribuir_produccion_a_nodo(m2_totales_planta, energia_nodo_kwh, energia_total_planta_kwh)` → `float`
  - `calcular_baseline_movil(mediciones_historicas)` → `float | None`
  - `generar_sparkline(mediciones, n_puntos)` → `list[float]`

- [ ] **Step 1: Escribir los tests (a-f) que fallan**

Crea `tests/test_telemetria_kpis.py`:

```python
"""Tests para calc/telemetria_kpis.py (Task 1 — D7-A)."""
from datetime import datetime, timedelta, timezone

import pytest

from calc.telemetria_kpis import (
    atribuir_produccion_a_nodo,
    calcular_baseline_movil,
    calcular_kpis_economicos,
    calcular_kpis_energeticos,
    calcular_kpis_produccion,
    generar_sparkline,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _meds(pares_ts_kw_fp):
    """[(ts_str, kw, fp), ...] → lista de dicts."""
    return [{"ts": ts, "kw": kw, "fp": fp} for ts, kw, fp in pares_ts_kw_fp]


# ── Tests a-f ─────────────────────────────────────────────────────────────────

def test_a_kpis_energeticos_basicos():
    """energia, demanda_pico y demanda_promedio con valores esperados."""
    meds = _meds([
        ("2024-01-01T00:00:00Z", 100.0, 0.90),
        ("2024-01-01T01:00:00Z", 120.0, 0.91),
        ("2024-01-01T02:00:00Z", 110.0, 0.89),
    ])
    r = calcular_kpis_energeticos(meds, 200.0)
    # Trapezoidal: (100+120)/2*1h + (120+110)/2*1h = 110 + 115 = 225 kWh
    assert abs(r["energia_kwh"] - 225.0) < 0.01
    assert r["demanda_pico_kw"] == 120.0
    assert abs(r["demanda_promedio_kw"] - 110.0) < 0.01   # (100+120+110)/3


def test_b_fp_ponderado_por_kw_no_promedio_simple():
    """FP se pondera por potencia_activa_kw, no por conteo de muestras."""
    meds = _meds([
        ("2024-01-01T00:00:00Z", 100.0, 0.90),
        ("2024-01-01T00:15:00Z", 1000.0, 0.80),
    ])
    r = calcular_kpis_energeticos(meds, None)
    esperado = (100.0 * 0.90 + 1000.0 * 0.80) / (100.0 + 1000.0)   # ≈ 0.8091
    assert abs(r["factor_potencia_promedio"] - esperado) < 0.001
    assert r["factor_potencia_promedio"] < 0.85   # promedio simple sería 0.85


def test_c_costo_total_con_precio_y_energia():
    """costo_total_mxn = energia_kwh * precio_mxn_kwh."""
    r = calcular_kpis_economicos(
        energia_kwh=1000.0,
        precio_mxn_kwh=2.5,
        costo_cliente_factura_total=None,
        baseline_kwh=None,
    )
    assert r["costo_total_mxn"] == 2500.0
    assert r["costo_unitario_mxn_kwh"] == 2.5
    assert r["pct_sobre_factura"] is None
    assert r["ahorro_potencial_mxn"] is None


def test_d_atribuir_produccion_proporcional():
    """Nodo con 40 % de energía recibe 40 % de los m²."""
    m2 = atribuir_produccion_a_nodo(
        m2_totales_planta=10_000.0,
        energia_nodo_kwh=400.0,
        energia_total_planta_kwh=1_000.0,
    )
    assert abs(m2 - 4_000.0) < 0.01


def test_d_atribuir_produccion_energia_cero():
    """Si energia_total_planta_kwh <= 0, retorna 0.0."""
    assert atribuir_produccion_a_nodo(10_000.0, 400.0, 0.0) == 0.0


def test_e_baseline_vacio_retorna_none():
    assert calcular_baseline_movil([]) is None


def test_f_sparkline_96_a_24_puntos():
    """generar_sparkline con 96 muestras (15 min) y n_puntos=24 retorna 24 floats."""
    inicio = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meds = [
        {
            "ts": (inicio + timedelta(minutes=i * 15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kw": 100.0,
            "fp": 0.90,
        }
        for i in range(96)
    ]
    r = generar_sparkline(meds, 24)
    assert len(r) == 24
    assert all(isinstance(v, float) for v in r)
```

- [ ] **Step 2: Verificar que fallan (no existe el módulo aún)**

```bash
python3 -m pytest tests/test_telemetria_kpis.py -v 2>&1 | head -20
```

Esperado: errores `ModuleNotFoundError` — confirma que los tests detectan ausencia.

- [ ] **Step 3: Implementar `calc/telemetria_kpis.py`**

```python
"""Cálculo de KPIs de paneles para telemetría (Fase 2 D7-A).

Funciones puras: reciben datos ya fetcheados, no acceden a Supabase.
"""
from __future__ import annotations

from datetime import datetime


def calcular_kpis_energeticos(
    mediciones: list[dict],
    potencia_nominal_kw: float | None,
) -> dict:
    """Calcula KPIs energéticos sobre la serie temporal del nodo.

    mediciones: lista de dicts {"ts": str ISO, "kw": float, "fp": float}
    Retorna dict con: energia_kwh, demanda_pico_kw, demanda_promedio_kw,
                      factor_potencia_promedio, indice_utilizacion_pct
    """
    if not mediciones:
        return {
            "energia_kwh": 0.0,
            "demanda_pico_kw": 0.0,
            "demanda_promedio_kw": 0.0,
            "factor_potencia_promedio": None,
            "indice_utilizacion_pct": None,
        }

    kw_vals = [m["kw"] for m in mediciones]
    fp_vals = [m.get("fp", 0.0) for m in mediciones]

    # Energía: integración trapezoidal
    energia = 0.0
    for i in range(1, len(mediciones)):
        try:
            t0 = datetime.fromisoformat(mediciones[i - 1]["ts"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(mediciones[i]["ts"].replace("Z", "+00:00"))
            dt_h = (t1 - t0).total_seconds() / 3600.0
            energia += (kw_vals[i - 1] + kw_vals[i]) / 2.0 * dt_h
        except Exception:
            pass

    demanda_pico = max(kw_vals)
    demanda_prom = sum(kw_vals) / len(kw_vals)

    # FP ponderado por potencia activa
    total_kw = sum(kw_vals)
    fp_pond: float | None = None
    if total_kw > 0:
        fp_pond = sum(fp_vals[i] * kw_vals[i] for i in range(len(mediciones))) / total_kw

    # Índice de utilización: pico / nominal
    idx_util: float | None = None
    if potencia_nominal_kw and potencia_nominal_kw > 0:
        idx_util = round(demanda_pico / potencia_nominal_kw * 100, 2)

    return {
        "energia_kwh": round(energia, 3),
        "demanda_pico_kw": round(demanda_pico, 3),
        "demanda_promedio_kw": round(demanda_prom, 3),
        "factor_potencia_promedio": round(fp_pond, 4) if fp_pond is not None else None,
        "indice_utilizacion_pct": idx_util,
    }


def calcular_kpis_economicos(
    energia_kwh: float,
    precio_mxn_kwh: float | None,
    costo_cliente_factura_total: float | None,
    baseline_kwh: float | None,
) -> dict:
    """Calcula KPIs económicos del nodo.

    Retorna dict con: costo_total_mxn, costo_unitario_mxn_kwh,
                      pct_sobre_factura, ahorro_potencial_mxn
    """
    if precio_mxn_kwh is None:
        return {
            "costo_total_mxn": None,
            "costo_unitario_mxn_kwh": None,
            "pct_sobre_factura": None,
            "ahorro_potencial_mxn": None,
        }

    costo_total = round(energia_kwh * precio_mxn_kwh, 2)

    pct_factura: float | None = None
    if costo_cliente_factura_total and costo_cliente_factura_total > 0:
        pct_factura = round(costo_total / costo_cliente_factura_total * 100, 2)

    ahorro: float | None = None
    if baseline_kwh is not None:
        ahorro = round((baseline_kwh - energia_kwh) * precio_mxn_kwh, 2)

    return {
        "costo_total_mxn": costo_total,
        "costo_unitario_mxn_kwh": precio_mxn_kwh,
        "pct_sobre_factura": pct_factura,
        "ahorro_potencial_mxn": ahorro,
    }


def calcular_kpis_produccion(
    energia_kwh: float,
    costo_total_mxn: float | None,
    m2_producidos_atribuidos: float,
) -> dict:
    """Calcula KPIs de producción del nodo.

    Retorna dict con: consumo_especifico_kwh_m2, costo_especifico_mxn_m2,
                      pct_costo_especifico, m2_producidos
    """
    if m2_producidos_atribuidos <= 0:
        return {
            "consumo_especifico_kwh_m2": None,
            "costo_especifico_mxn_m2": None,
            "pct_costo_especifico": None,
            "m2_producidos": 0.0,
        }

    consumo_esp = round(energia_kwh / m2_producidos_atribuidos, 4)
    costo_esp: float | None = None
    if costo_total_mxn is not None:
        costo_esp = round(costo_total_mxn / m2_producidos_atribuidos, 4)

    return {
        "consumo_especifico_kwh_m2": consumo_esp,
        "costo_especifico_mxn_m2": costo_esp,
        "pct_costo_especifico": None,   # fórmula final por definir por el usuario
        "m2_producidos": round(m2_producidos_atribuidos, 2),
    }


def atribuir_produccion_a_nodo(
    m2_totales_planta: float,
    energia_nodo_kwh: float,
    energia_total_planta_kwh: float,
) -> float:
    """Atribuye m² de producción al nodo proporcionalmente a su consumo eléctrico."""
    if energia_total_planta_kwh <= 0:
        return 0.0
    return m2_totales_planta * (energia_nodo_kwh / energia_total_planta_kwh)


def calcular_baseline_movil(mediciones_historicas: list[dict]) -> float | None:
    """Calcula la energía total del periodo histórico como baseline provisional.

    mediciones_historicas: lista de dicts {"ts": str ISO, "kw": float}
    Retorna kWh integrados, o None si no hay datos.
    NOTA: fórmula final (promedio diario, p90, etc.) por definir por el usuario.
    """
    if not mediciones_historicas:
        return None

    kw_vals = [m.get("kw", 0.0) for m in mediciones_historicas]
    energia = 0.0
    for i in range(1, len(mediciones_historicas)):
        try:
            t0 = datetime.fromisoformat(
                mediciones_historicas[i - 1]["ts"].replace("Z", "+00:00")
            )
            t1 = datetime.fromisoformat(
                mediciones_historicas[i]["ts"].replace("Z", "+00:00")
            )
            dt_h = (t1 - t0).total_seconds() / 3600.0
            energia += (kw_vals[i - 1] + kw_vals[i]) / 2.0 * dt_h
        except Exception:
            pass

    return round(energia, 3) if energia > 0 else None


def generar_sparkline(mediciones: list[dict], n_puntos: int) -> list[float]:
    """Reduce mediciones a n_puntos agrupando por bucket temporal.

    mediciones: lista de dicts {"ts": str ISO, "kw": float}
    Retorna lista de n_puntos floats con kWh acumulados por bucket.
    Para 24h y n_puntos=24: cada bucket es una hora.
    """
    if not mediciones or n_puntos <= 0:
        return [0.0] * max(n_puntos, 0)

    try:
        t_inicio = datetime.fromisoformat(mediciones[0]["ts"].replace("Z", "+00:00"))
        t_fin = datetime.fromisoformat(mediciones[-1]["ts"].replace("Z", "+00:00"))
    except Exception:
        return [0.0] * n_puntos

    duracion = (t_fin - t_inicio).total_seconds()
    if duracion <= 0:
        return [0.0] * n_puntos

    bucket_size = duracion / n_puntos
    buckets = [0.0] * n_puntos

    for i in range(1, len(mediciones)):
        try:
            t0 = datetime.fromisoformat(mediciones[i - 1]["ts"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(mediciones[i]["ts"].replace("Z", "+00:00"))
            dt_h = (t1 - t0).total_seconds() / 3600.0
            kwh = (mediciones[i - 1]["kw"] + mediciones[i]["kw"]) / 2.0 * dt_h
            # Midpoint del intervalo determina el bucket
            t_mid = t0 + (t1 - t0) / 2
            offset = (t_mid - t_inicio).total_seconds()
            idx = min(int(offset / bucket_size), n_puntos - 1)
            buckets[idx] += kwh
        except Exception:
            pass

    return [round(b, 3) for b in buckets]
```

- [ ] **Step 4: Ejecutar tests a-f y verificar que pasan**

```bash
python3 -m pytest tests/test_telemetria_kpis.py -v -k "test_a or test_b or test_c or test_d or test_e or test_f"
```

Esperado: 7/7 passing (test_d tiene dos funciones).

- [ ] **Step 5: Ejecutar la suite completa para verificar no-regresión**

```bash
python3 -m pytest tests/test_dashboard_telemetria.py tests/test_telemetria_kpis.py -v
```

Esperado: 8 + 7 = 15 passing (los tests g-i aún no existen).

- [ ] **Step 6: Commit**

```bash
git add calc/telemetria_kpis.py tests/test_telemetria_kpis.py
git commit -m "feat(telemetria-D7A): modulo de calculo de KPIs de paneles con tests unitarios"
```

---

### Task 2: Migración SQL + seed extendido + función de repositorio

**Files:**
- Create: `storage/migrations/202608_produccion_diaria.sql`
- Modify: `storage/repository.py` (añadir `obtener_produccion_diaria`)
- Modify: `scripts/seed_iberica.py` (añadir producción + histórico)

**Interfaces:**
- Consumes: nada de Task 1 (no necesita las funciones de cálculo).
- Produces (consumida por Task 3):
  - `obtener_produccion_diaria(cliente_id, desde_fecha, hasta_fecha)` → `list[dict]`
    - `desde_fecha`, `hasta_fecha`: strings `"YYYY-MM-DD"`
    - cada dict tiene al menos `{"fecha": str, "m2_producidos": float}`

- [ ] **Step 1: Crear la migración SQL**

Crea `storage/migrations/202608_produccion_diaria.sql`:

```sql
-- Producción diaria de planta para KPIs de telemetría (D7-A)
-- Ejecutar en Supabase SQL editor.

CREATE TABLE IF NOT EXISTS produccion_diaria (
    id          BIGSERIAL PRIMARY KEY,
    cliente_id  INT NOT NULL,
    fecha       DATE NOT NULL,
    m2_producidos NUMERIC(10, 2) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT produccion_diaria_cliente_fecha_uq UNIQUE (cliente_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_produccion_diaria_cliente_fecha
    ON produccion_diaria (cliente_id, fecha);
```

- [ ] **Step 2: Añadir `obtener_produccion_diaria` a `storage/repository.py`**

Lee el final de `storage/repository.py` para saber dónde insertar. Añade al final del archivo (antes de cualquier bloque `if __name__ == "__main__"` si existe):

```python
def obtener_produccion_diaria(
    cliente_id: int,
    desde_fecha: str,
    hasta_fecha: str,
) -> list[dict]:
    """Retorna registros de produccion_diaria para el cliente en el rango de fechas.

    desde_fecha, hasta_fecha: "YYYY-MM-DD" (ambos inclusivos).
    """
    resp = (
        _supabase.table("produccion_diaria")
        .select("fecha, m2_producidos")
        .eq("cliente_id", cliente_id)
        .gte("fecha", desde_fecha)
        .lte("fecha", hasta_fecha)
        .order("fecha")
        .limit(20000)
        .execute()
    )
    return resp.data or []
```

- [ ] **Step 3: Extender `scripts/seed_iberica.py` — producción diaria**

Añade la siguiente función ANTES de `main()`:

```python
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
```

- [ ] **Step 4: Extender `scripts/seed_iberica.py` — histórico del mes anterior**

Añade la siguiente función ANTES de `main()`:

```python
def _sembrar_historico_mes_anterior(planta: dict, forzar: bool) -> int:
    """Genera 96 muestras por CBT correspondientes al mismo día del mes anterior.

    Retorna total de muestras insertadas.
    """
    from storage.repository import _supabase

    cid = planta["cliente_id"]
    hoy = datetime.now(timezone.utc)
    # Mismo día del mes anterior: restar 30 días, truncar a inicio de día UTC
    hoy_date = hoy.date()
    desde_ant = datetime(
        hoy_date.year if hoy_date.month > 1 else hoy_date.year - 1,
        (hoy_date.month - 1) if hoy_date.month > 1 else 12,
        min(hoy_date.day, 28),
        0, 0, 0,
        tzinfo=timezone.utc,
    )

    # Obtener cargas finales
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

    if forzar:
        # Borrar mediciones del rango del mes anterior para este cliente
        ids_medidores = [c["id"] for c in cargas]
        hasta_ant_iso = (desde_ant + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        desde_ant_iso = desde_ant.strftime("%Y-%m-%dT%H:%M:%SZ")
        (
            _supabase.table("mediciones_tiempo_real")
            .delete()
            .in_("medidor_id", ids_medidores)
            .gte("timestamp", desde_ant_iso)
            .lt("timestamp", hasta_ant_iso)
            .execute()
        )

    total = 0
    for carga in cargas:
        meds = generar_mediciones_por_carga(carga, desde_ant, n=96, intervalo=15)
        total += insertar_mediciones_batch(meds)
    return total
```

- [ ] **Step 5: Actualizar `main()` en `scripts/seed_iberica.py` para llamar los nuevos bloques**

En la función `main()`, dentro del loop `for planta in PLANTAS`, añade después de la línea `totales["mediciones"] += nm`:

```python
        np = _sembrar_produccion_diaria(planta, dias=8, forzar=args.forzar)
        nh = _sembrar_historico_mes_anterior(planta, forzar=args.forzar)
        totales["produccion"] = totales.get("produccion", 0) + np
        totales["historico"]  = totales.get("historico", 0)  + nh
        print(f"    Producción diaria: {np} registros  |  Histórico mes anterior: {nh} muestras")
```

Y al final, añade las líneas de reporte de los nuevos totales:

```python
    print(f"  Producción diaria: {totales.get('produccion', 0)} registros")
    print(f"  Histórico mes ant: {totales.get('historico', 0)} muestras")
```

- [ ] **Step 6: Verificar que los tests existentes pasan (no se tocan tests)**

```bash
python3 -m pytest tests/test_dashboard_telemetria.py tests/test_telemetria_kpis.py -q
```

Esperado: 15/15 passing.

- [ ] **Step 7: Commit**

```bash
git add storage/migrations/202608_produccion_diaria.sql storage/repository.py scripts/seed_iberica.py
git commit -m "feat(telemetria-D7A): tabla produccion_diaria, seed extendido y obtener_produccion_diaria"
```

---

### Task 3: Endpoint extendido + tests de integración (g-i)

**Files:**
- Modify: `web/app.py` — función `cliente_dashboard_telemetria_data`
- Modify: `tests/test_telemetria_kpis.py` — añadir tests g, h, i

**Interfaces:**
- Consumes de Task 1:
  - `from calc.telemetria_kpis import calcular_kpis_energeticos, calcular_kpis_economicos, calcular_kpis_produccion, atribuir_produccion_a_nodo, calcular_baseline_movil, generar_sparkline`
- Consumes de Task 2:
  - `from storage.repository import obtener_produccion_diaria as _opd`

**Notas de implementación:**

El endpoint ya tiene disponible:
- `energia_kwh` — energía del nodo seleccionado (periodo actual)
- `mediciones_por_hoja`, `hojas_ids_nodo` — series de cada hoja
- `bucket_kw`, `bucket_fp_peso`, `bucket_kw_peso`, `ts_sorted` — serie agregada del nodo
- `mediciones_ant`, `ts_ant`, `energia_ant` — datos del periodo −30 días
- `costo_info` — dict con `precio_mxn_kwh`, `costo_mxn`
- `desde`, `ahora`, `desde_ant`, `hasta_ant` — ventanas temporales
- `nodo`, `acometida`, `por_id` — datos del árbol

La lista de mediciones para `calcular_kpis_energeticos` se construye desde `bucket_kw` y `bucket_fp_peso`:
```python
meds_actuales = [
    {
        "ts": ts,
        "kw": bucket_kw[ts],
        "fp": bucket_fp_peso[ts] / bucket_kw_peso[ts] if bucket_kw_peso[ts] > 0 else 0.0,
    }
    for ts in ts_sorted
]
```

La lista para el periodo anterior desde `bucket_ant`:
```python
ts_ant_sorted = sorted(bucket_ant.keys())
meds_anteriores = [{"ts": ts, "kw": bucket_ant[ts], "fp": 0.0} for ts in ts_ant_sorted]
```

La energía total de la planta (acometida) para atribuir producción:
```python
energia_total_planta = _energia_nodo(acometida["id"])
```

- [ ] **Step 1: Leer `web/app.py` desde la línea 2877 hasta el final de la función**

Lee `web/app.py` líneas 2877-2990 para entender el punto de inserción exacto. La función devuelve el JSON en `return jsonify({...})` en la línea ~2961. Añadir el bloque `kpis_paneles` dentro de ese dict.

- [ ] **Step 2: Añadir imports y bloque kpis_paneles al endpoint**

Localiza el bloque de imports dentro de la función `cliente_dashboard_telemetria_data` (las líneas `from storage.repository import ...`). Añade:

```python
        from calc.telemetria_kpis import (
            atribuir_produccion_a_nodo as _apn,
            calcular_baseline_movil as _cbm,
            calcular_kpis_economicos as _cke,
            calcular_kpis_energeticos as _cken,
            calcular_kpis_produccion as _ckp,
            generar_sparkline as _gs,
        )
        from storage.repository import obtener_produccion_diaria as _opd
```

Luego, ANTES de `return jsonify({...})`, añade el bloque de cálculo de `kpis_paneles`:

```python
        # ── KPIs de paneles ────────────────────────────────────────────────
        _N_SPARK = 24

        # Serie agregada actual (ya disponible como bucket_kw + bucket_fp_peso)
        meds_actuales = [
            {
                "ts": ts,
                "kw": bucket_kw[ts],
                "fp": (bucket_fp_peso[ts] / bucket_kw_peso[ts]
                       if bucket_kw_peso[ts] > 0 else 0.0),
            }
            for ts in ts_sorted
        ]
        meds_anteriores = [
            {"ts": ts, "kw": bucket_ant[ts], "fp": 0.0}
            for ts in sorted(bucket_ant.keys())
        ]

        # Potencia nominal del nodo seleccionado (solo carga_final la tiene)
        pot_nom = nodo.get("potencia_nominal_kw")
        pot_nom = float(pot_nom) if pot_nom else None

        # Calcular KPIs energéticos
        ken_act = _cken(meds_actuales, pot_nom)
        ken_ant = _cken(meds_anteriores, None) if disponible_ant else {}

        def _delta(act, ant):
            if act is None or not ant or ant.get(list(ant.keys())[0] if ant else "") is None:
                return None
            # extraer el primer valor numérico comparable no es trivial; usar función genérica
            return None

        def _delta_pct(act_val, ant_val):
            if act_val is None or ant_val is None or ant_val == 0:
                return None
            return round((act_val - ant_val) / abs(ant_val) * 100, 1)

        # Producción diaria
        desde_str = desde.strftime("%Y-%m-%d")
        hasta_str = ahora.strftime("%Y-%m-%d")
        desde_ant_str = desde_ant.strftime("%Y-%m-%d")
        hasta_ant_str = hasta_ant.strftime("%Y-%m-%d")

        prod_act = _opd(cliente_id, desde_str, hasta_str)
        prod_ant = _opd(cliente_id, desde_ant_str, hasta_ant_str)

        m2_planta_act = sum(float(r.get("m2_producidos") or 0) for r in prod_act)
        m2_planta_ant = sum(float(r.get("m2_producidos") or 0) for r in prod_ant)

        # Energía total de la acometida (para atribuir producción proporcionalmente)
        energia_total_planta = _energia_nodo(acometida["id"])

        m2_nodo_act = _apn(m2_planta_act, energia_kwh, energia_total_planta)
        m2_nodo_ant = _apn(m2_planta_ant, energia_ant, energia_total_planta)

        # Baseline = energía del mismo periodo del mes anterior
        baseline_kwh = _cbm(meds_anteriores) if disponible_ant else None

        # KPIs económicos
        precio = costo_info.get("precio_mxn_kwh")
        costo_total_act = costo_info.get("costo_mxn")
        costo_total_ant = costo_ant_info.get("costo_mxn") if costo_ant_info else None
        costo_planta_act = (
            round(energia_total_planta * precio, 2) if precio else None
        )
        kec_act = _cke(energia_kwh, precio, costo_planta_act, baseline_kwh)
        kec_ant = _cke(energia_ant, precio, None, None) if disponible_ant else {}

        # KPIs producción
        kp_act = _ckp(energia_kwh, costo_total_act, m2_nodo_act)
        kp_ant = _ckp(energia_ant, costo_total_ant, m2_nodo_ant) if disponible_ant else {}

        # Sparklines (24 puntos)
        sp_energia_act = _gs(meds_actuales, _N_SPARK)
        sp_energia_ant = _gs(meds_anteriores, _N_SPARK) if disponible_ant else None

        def _kpi_bloque(act_val, ant_val, spark_act, spark_ant, **extra):
            return {
                "actual": act_val,
                "anterior": ant_val if disponible_ant else None,
                "delta_pct": _delta_pct(act_val, ant_val) if disponible_ant else None,
                "sparkline_actual": spark_act,
                "sparkline_anterior": spark_ant,
                **extra,
            }

        kpis_paneles = {
            "energeticos": {
                "energia_kwh": _kpi_bloque(
                    ken_act.get("energia_kwh"), ken_ant.get("energia_kwh"),
                    sp_energia_act, sp_energia_ant,
                    es_favorable_menor=True,
                ),
                "demanda_pico_kw": _kpi_bloque(
                    ken_act.get("demanda_pico_kw"), ken_ant.get("demanda_pico_kw"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "demanda_promedio_kw": _kpi_bloque(
                    ken_act.get("demanda_promedio_kw"), ken_ant.get("demanda_promedio_kw"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "factor_potencia": _kpi_bloque(
                    ken_act.get("factor_potencia_promedio"),
                    ken_ant.get("factor_potencia_promedio"),
                    None, None,
                    es_favorable_menor=False,
                    es_gauge=True,
                    rango_min=0.0,
                    rango_max=1.0,
                ),
                "indice_utilizacion_pct": _kpi_bloque(
                    ken_act.get("indice_utilizacion_pct"),
                    ken_ant.get("indice_utilizacion_pct"),
                    None, None,
                    es_favorable_menor=True,
                    aplica_a_nodo=["carga_final"],
                ),
            },
            "economicos": {
                "costo_total_mxn": _kpi_bloque(
                    kec_act.get("costo_total_mxn"), kec_ant.get("costo_total_mxn"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "costo_unitario_mxn_kwh": _kpi_bloque(
                    kec_act.get("costo_unitario_mxn_kwh"), kec_ant.get("costo_unitario_mxn_kwh"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "pct_sobre_factura": _kpi_bloque(
                    kec_act.get("pct_sobre_factura"), kec_ant.get("pct_sobre_factura"),
                    None, None,
                    es_favorable_menor=True,
                    oculto_en_nodo=["acometida_cfe"],
                ),
                "ahorro_potencial_mxn": _kpi_bloque(
                    kec_act.get("ahorro_potencial_mxn"), kec_ant.get("ahorro_potencial_mxn"),
                    None, None,
                    es_favorable_menor=False,
                    baseline_nota="baseline provisional, criterio final por definir",
                ),
            },
            "produccion": {
                "consumo_especifico_kwh_m2": _kpi_bloque(
                    kp_act.get("consumo_especifico_kwh_m2"),
                    kp_ant.get("consumo_especifico_kwh_m2"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "costo_especifico_mxn_m2": _kpi_bloque(
                    kp_act.get("costo_especifico_mxn_m2"),
                    kp_ant.get("costo_especifico_mxn_m2"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "pct_costo_especifico": _kpi_bloque(
                    kp_act.get("pct_costo_especifico"),
                    kp_ant.get("pct_costo_especifico"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "produccion_m2": _kpi_bloque(
                    kp_act.get("m2_producidos"), kp_ant.get("m2_producidos"),
                    None, None,
                    es_favorable_menor=False,
                ),
            },
            "meta": {
                "periodo_actual_desde": desde_iso,
                "periodo_actual_hasta": hasta_iso,
                "periodo_anterior_desde": desde_ant_iso,
                "periodo_anterior_hasta": hasta_ant_iso,
                "periodo_anterior_etiqueta": "mismo día del mes anterior",
            },
        }
```

Finalmente, añade `"kpis_paneles": kpis_paneles,` al dict del `return jsonify({...})`.

- [ ] **Step 3: Añadir tests g, h, i a `tests/test_telemetria_kpis.py`**

Añade al final del archivo los imports necesarios y los tres tests:

```python
# ── Tests g-i (integración con endpoint) ─────────────────────────────────────
# Reutiliza fixtures y mocks del patrón de test_dashboard_telemetria.py

import json
from unittest.mock import MagicMock, patch


@pytest.fixture()
def _app_fase2(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FASE2_HABILITADA", "true")
    from web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def _client_fase2(_app_fase2):
    return _app_fase2.test_client()


def _inyectar_sesion(client):
    from time import time
    with client.session_transaction() as sess:
        sess["_user_id"] = "test-uid"
        sess["_user_email"] = "test@test.com"
        sess["_user_rol"] = "master_admin"
        sess["_empresa_id"] = 44
        sess["_access_token"] = "fake-token"
        sess["_token_exp"] = time() + 3600


_ARBOL = [
    {"id": 1, "nombre": "Acometida", "punto_medicion": "acometida_cfe",
     "medidor_padre_id": None, "cliente_id": 44, "tipo_carga": None, "potencia_nominal_kw": None},
    {"id": 2, "nombre": "T-1.1", "punto_medicion": "transformador",
     "medidor_padre_id": 1, "cliente_id": 44, "tipo_carga": None, "potencia_nominal_kw": 500.0},
    {"id": 3, "nombre": "CBT-Horno", "punto_medicion": "carga_final",
     "medidor_padre_id": 2, "cliente_id": 44, "tipo_carga": "horno_tunel", "potencia_nominal_kw": 200.0},
]

_MEDS = [
    {"timestamp": "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0, "factor_potencia": 0.90},
    {"timestamp": "2024-01-01T01:00:00Z", "potencia_activa_kw": 120.0, "factor_potencia": 0.91},
]


def _mock_repo(mock_arbol, mock_meds_act, mock_meds_ant, mock_prod):
    """Retorna dict de patches para el endpoint de telemetría."""
    return {
        "storage.repository.obtener_arbol_medidores": MagicMock(return_value=mock_arbol),
        "storage.repository.obtener_descendientes_ids": MagicMock(return_value=[3]),
        "storage.repository.obtener_mediciones_recientes": MagicMock(side_effect=[
            mock_meds_act,   # periodo actual (hoja 3)
            mock_meds_ant,   # periodo anterior (hoja 3)
        ]),
        "storage.repository.obtener_produccion_diaria": MagicMock(return_value=mock_prod),
        "calc.telemetria_costos.calcular_costo_periodo": MagicMock(return_value={
            "costo_mxn": 5000.0, "precio_mxn_kwh": 2.5,
            "fuente": "factura_mes_exacto", "mes_referencia": "2024-01",
        }),
    }


def test_g_endpoint_devuelve_kpis_paneles(_client_fase2):
    """Endpoint /telemetria/data incluye kpis_paneles con las tres subclaves y meta."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [{"fecha": "2024-01-01", "m2_producidos": 5000.0}])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get(
            "/clientes/44/dashboard/telemetria/data?rango=24h",
            headers={"Accept": "application/json"},
        )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "kpis_paneles" in data
    kp = data["kpis_paneles"]
    assert "energeticos" in kp
    assert "economicos" in kp
    assert "produccion" in kp
    assert "meta" in kp


def test_h_kpis_flags_aplica_y_oculto(_client_fase2):
    """indice_utilizacion_pct tiene aplica_a_nodo; pct_sobre_factura tiene oculto_en_nodo."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    idx = data["kpis_paneles"]["energeticos"]["indice_utilizacion_pct"]
    assert idx["aplica_a_nodo"] == ["carga_final"]
    pct = data["kpis_paneles"]["economicos"]["pct_sobre_factura"]
    assert pct["oculto_en_nodo"] == ["acometida_cfe"]


def test_i_anterior_null_sin_datos_historicos(_client_fase2):
    """Si no hay mediciones históricas, los valores 'anterior' y 'delta_pct' son null."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, [], [])   # anterior vacío
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    kpi = data["kpis_paneles"]["energeticos"]["energia_kwh"]
    assert kpi["anterior"] is None
    assert kpi["delta_pct"] is None
```

- [ ] **Step 4: Ejecutar todos los tests y verificar 17/17 passing**

```bash
python3 -m pytest tests/test_dashboard_telemetria.py tests/test_telemetria_kpis.py -v
```

Esperado: 8 (existentes) + 7 (a-f) + 3 (g-i) = 18 passing total (incluyendo `test_d` que tiene dos asserts en dos funciones).

Si algún test de integración falla por la firma del mock, ajustar el mock según el traceback. Los tests g-i pueden requerir ajustar la forma en que `patch.multiple` ve los nombres de las funciones — seguir el patrón exacto de `tests/test_dashboard_telemetria.py` para el setup de mocks.

- [ ] **Step 5: Commit**

```bash
git add web/app.py tests/test_telemetria_kpis.py
git commit -m "feat(telemetria-D7A): endpoint extendido con kpis_paneles y tests de integracion"
```

---

### Task 4: CHANGELOG y push

**Files:**
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: commits de Tasks 1-3.
- Produces: entrada v2.79.0 en CHANGELOG, push a origin/main.

- [ ] **Step 1: Agregar entrada v2.79.0 al inicio de CHANGELOG.md**

Inserta antes del bloque `## [2.78.3]`:

```markdown
## [2.79.0] — 2026-08-05

### Añadido — Fase 2 D7-A: backend de KPIs de paneles de telemetría

- `storage/migrations/202608_produccion_diaria.sql` — nueva tabla `produccion_diaria (id, cliente_id, fecha, m2_producidos, created_at)` con UNIQUE(cliente_id, fecha) e índice por fecha. Requiere ejecución manual en Supabase.
- `calc/telemetria_kpis.py` — nuevo módulo con 6 funciones puras de cálculo: `calcular_kpis_energeticos` (energía trapezoidal, demanda pico/prom, FP ponderado por kW, índice utilización), `calcular_kpis_economicos` (costo total, unitario, % factura, ahorro potencial), `calcular_kpis_produccion` (consumo y costo específicos por m²), `atribuir_produccion_a_nodo` (m² proporcional al consumo), `calcular_baseline_movil` (energía del periodo histórico, fórmula provisional), `generar_sparkline` (reduce mediciones a N puntos por bucket temporal).
- `storage/repository.py` — nueva función `obtener_produccion_diaria(cliente_id, desde_fecha, hasta_fecha)`.
- `scripts/seed_iberica.py` — extendido con `_sembrar_produccion_diaria` (registros diarios con perfil L-V/Sáb/Dom, semilla determinista) y `_sembrar_historico_mes_anterior` (96 muestras por CBT del mismo día del mes anterior). Ambos bloques son idempotentes y respetan `--forzar`.
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data` extendido: nuevo bloque `kpis_paneles` con subclaves `energeticos` (5 KPIs), `economicos` (4 KPIs), `produccion` (4 KPIs) y `meta`. Cada KPI incluye `actual`, `anterior`, `delta_pct`, `sparkline_actual`, `sparkline_anterior` y flags de renderizado (`es_favorable_menor`, `aplica_a_nodo`, `oculto_en_nodo`, `es_gauge`).
- `tests/test_telemetria_kpis.py` — 9 nuevos tests: a-f unitarios (sin DB), g-i de integración contra el endpoint mockeado.

```

- [ ] **Step 2: Commit y push**

```bash
git add CHANGELOG.md
git commit -m "chore: CHANGELOG v2.79.0 — backend KPIs telemetria D7-A"
git push
```

- [ ] **Step 3: Verificar push y log final**

```bash
git log --oneline -5
```

---

## Notas de implementación

**Por qué `pct_costo_especifico` es `None`:** La fórmula dimensional no está definida en el spec; se retorna `None` como placeholder explícito. El frontend puede ocultarlo hasta que el usuario decida el criterio.

**Por qué `baseline_kwh` = energía del mes anterior:** La spec dice "fórmula final por definir". La implementación provisional usa `calcular_baseline_movil` con las mediciones del periodo −30 días — que ya se fetchean en el endpoint. Sin fetch adicional.

**SQL no llegó en el mensaje del spec:** La tabla `produccion_diaria` se infirió del contexto. Si el usuario tiene un DDL diferente, ajustar el archivo de migración.

**Tiempo esperado del endpoint:** El fetch adicional de `obtener_produccion_diaria` (x2: actual + anterior) añade ~200–500 ms; el total debería mantenerse < 8 s.
