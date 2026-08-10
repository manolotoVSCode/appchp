# Telemetría D7-A v2 — Histórico 60 días, selección de fuente por rango, sparkline dinámico

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extender el backend D7-A existente (v2.79.0) con histórico de 60 días por CBT, la función `determinar_periodo_anterior`, selección de fuente por rango en repositorio, sparkline dinámico por rango, parallel fetch y corrección de `pct_costo_especifico`.

**Architecture:** Cuatro cambios coordinados sobre código ya existente: (1) añadir dos funciones y corregir una en `calc/telemetria_kpis.py`; (2) añadir `obtener_mediciones_para_rango` en repositorio; (3) reemplazar seed de 1 día de histórico con seed de 60 días completos; (4) actualizar el endpoint para usar las nuevas funciones con fetch paralelo y sparkline dinámico.

**Tech Stack:** Python 3.11, Flask 3.x, supabase-py SDK, pytest + unittest.mock, concurrent.futures.ThreadPoolExecutor.

## Global Constraints

- Acceso a Supabase exclusivamente vía `_supabase` SDK. Sin psycopg2.
- `.limit(20000)` en toda lectura de Supabase.
- No modificar frontend (JS, HTML, CSS). Esta entrega es solo backend.
- No dependencias externas (solo stdlib + lo que ya está en requirements.txt).
- `concurrent.futures` es stdlib — permitido.
- No tocar Contabilidad, Cogeneración, parsers ni módulos fuera de telemetría.
- Sin decoradores de acceso — el `abort(404)` ya existe en el endpoint.
- Nombres de campos JSON exactamente snake_case como en el spec.
- La tabla `produccion_diaria` YA EXISTE (migration 202608_produccion_diaria.sql aplicada en v2.79.0). No crear nueva migración.

---

## Estado previo (v2.79.0) — qué ya existe

Los archivos siguientes ya existen con implementación parcial:

- `calc/telemetria_kpis.py` — 6 funciones: `calcular_kpis_energeticos`, `calcular_kpis_economicos`, `calcular_kpis_produccion` (pct_costo_especifico = None), `atribuir_produccion_a_nodo`, `calcular_baseline_movil`, `generar_sparkline` (sin param `tipo`).
- `tests/test_telemetria_kpis.py` — 9 tests: a–f unitarios, g–i integración con endpoint.
- `storage/repository.py` — tiene `obtener_mediciones_recientes`, `obtener_agregados_15min`, `obtener_produccion_diaria`. Falta `obtener_mediciones_para_rango`.
- `scripts/seed_iberica.py` — `_sembrar_produccion_diaria` (8 días), `_sembrar_historico_mes_anterior` (96 muestras × 1 día por CBT). Ambas necesitan extenderse.
- `web/app.py` — endpoint con `kpis_paneles`, `_N_SPARK = 24` hardcodeado, fetch serial, periodo anterior calculado inline.

---

## Archivos que cambian

| Archivo | Cambio |
|---------|--------|
| `calc/telemetria_kpis.py` | Añadir `determinar_periodo_anterior`; update `generar_sparkline` con `tipo`; fix `pct_costo_especifico` |
| `tests/test_telemetria_kpis.py` | Añadir tests `test_g_determinar_periodo_anterior` y `test_h_obtener_mediciones_para_rango` |
| `storage/repository.py` | Añadir `obtener_mediciones_para_rango` |
| `scripts/seed_iberica.py` | Reemplazar `_sembrar_historico_mes_anterior` → `_sembrar_historico_60_dias`; actualizar `_sembrar_produccion_diaria` a 60 días |
| `web/app.py` | Parallel fetch; `determinar_periodo_anterior` importada; sparkline dinámico; `n_puntos_sparkline` en meta |
| `CHANGELOG.md` | Entrada v2.80.0 |

---

### Task 1: Actualizar `calc/telemetria_kpis.py` + test_g

**Files:**
- Modify: `calc/telemetria_kpis.py`
- Modify: `tests/test_telemetria_kpis.py`

**Interfaces:**
- Produces (consumida por Task 4): `determinar_periodo_anterior(rango, ahora)` → `tuple[datetime, datetime, str]`
- Produces (consumida por Task 4): `generar_sparkline(mediciones, n_puntos, tipo='energia')` — interfaz ampliada retrocompatible

- [ ] **Step 1: Escribir test_g que falla (no existe `determinar_periodo_anterior` aún)**

Añade al final de `tests/test_telemetria_kpis.py`:

```python
def test_g_determinar_periodo_anterior():
    """Para cada rango, la ventana anterior termina 30 días antes de ahora
    y tiene la misma anchura que el rango."""
    from datetime import datetime, timezone, timedelta
    from calc.telemetria_kpis import determinar_periodo_anterior

    ahora = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 24h: anterior termina en ahora-30d, dura 24h
    d, h, etiq = determinar_periodo_anterior("24h", ahora)
    esperado_hasta = ahora - timedelta(days=30)
    esperado_desde = esperado_hasta - timedelta(hours=24)
    assert abs((h - esperado_hasta).total_seconds()) < 1
    assert abs((d - esperado_desde).total_seconds()) < 1
    assert "30" in etiq or "anterior" in etiq.lower()

    # 7d: dura 7 días
    d7, h7, _ = determinar_periodo_anterior("7d", ahora)
    assert abs((h7 - esperado_hasta).total_seconds()) < 1
    assert abs((d7 - (esperado_hasta - timedelta(days=7))).total_seconds()) < 1

    # 30d: dura 30 días
    d30, h30, _ = determinar_periodo_anterior("30d", ahora)
    assert abs((h30 - esperado_hasta).total_seconds()) < 1
    assert abs((d30 - (esperado_hasta - timedelta(days=30))).total_seconds()) < 1
```

- [ ] **Step 2: Verificar que falla (ImportError)**

```bash
python3 -m pytest tests/test_telemetria_kpis.py::test_g_determinar_periodo_anterior -v
```

Esperado: `ImportError: cannot import name 'determinar_periodo_anterior'`

- [ ] **Step 3: Implementar `determinar_periodo_anterior` en `calc/telemetria_kpis.py`**

Añade al final de `calc/telemetria_kpis.py`:

```python
def determinar_periodo_anterior(
    rango: str,
    ahora: datetime,
) -> tuple[datetime, datetime, str]:
    """Calcula el periodo anterior equivalente al rango, desplazado 30 días atrás.

    - 24h: hasta = ahora - 30d; desde = hasta - 24h
    - 7d:  hasta = ahora - 30d; desde = hasta - 7d
    - 30d: hasta = ahora - 30d; desde = hasta - 30d

    Retorna (desde_ant, hasta_ant, etiqueta).
    """
    from datetime import timedelta

    hasta_ant = ahora - timedelta(days=30)
    if rango == "7d":
        desde_ant = hasta_ant - timedelta(days=7)
        etiqueta = "misma semana 30 días antes"
    elif rango == "30d":
        desde_ant = hasta_ant - timedelta(days=30)
        etiqueta = "mismo mes 30 días antes"
    else:  # 24h (default)
        desde_ant = hasta_ant - timedelta(hours=24)
        etiqueta = "mismo momento 30 días antes"

    return desde_ant, hasta_ant, etiqueta
```

- [ ] **Step 4: Añadir `tipo` a `generar_sparkline`**

Reemplaza la función `generar_sparkline` existente con esta versión ampliada (retrocompatible — `tipo` tiene default `'energia'`):

```python
def generar_sparkline(
    mediciones: list[dict],
    n_puntos: int,
    tipo: str = "energia",
) -> list[float]:
    """Reduce mediciones a n_puntos agrupando por bucket temporal.

    mediciones: lista de dicts {"ts": str ISO, "kw": float, "fp": float (opcional)}
    tipo='energia':         kWh acumulados por bucket (integral trapezoidal).
    tipo='potencia':        promedio de kw por bucket.
    tipo='factor_potencia': promedio ponderado de fp por kw, por bucket.
    Retorna lista de n_puntos floats.
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

    if tipo == "energia":
        buckets = [0.0] * n_puntos
        for i in range(1, len(mediciones)):
            try:
                t0 = datetime.fromisoformat(mediciones[i - 1]["ts"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(mediciones[i]["ts"].replace("Z", "+00:00"))
                dt_h = (t1 - t0).total_seconds() / 3600.0
                kwh = (mediciones[i - 1]["kw"] + mediciones[i]["kw"]) / 2.0 * dt_h
                t_mid = t0 + (t1 - t0) / 2
                idx = min(int((t_mid - t_inicio).total_seconds() / bucket_size), n_puntos - 1)
                buckets[idx] += kwh
            except Exception:
                pass
        return [round(b, 3) for b in buckets]

    elif tipo == "potencia":
        # Promedio de kw por bucket
        sumas = [0.0] * n_puntos
        conteos = [0] * n_puntos
        for m in mediciones:
            try:
                t = datetime.fromisoformat(m["ts"].replace("Z", "+00:00"))
                idx = min(int((t - t_inicio).total_seconds() / bucket_size), n_puntos - 1)
                sumas[idx] += m["kw"]
                conteos[idx] += 1
            except Exception:
                pass
        return [round(sumas[i] / conteos[i], 3) if conteos[i] > 0 else 0.0 for i in range(n_puntos)]

    else:  # factor_potencia: promedio ponderado por kw
        fp_peso = [0.0] * n_puntos
        kw_peso = [0.0] * n_puntos
        for m in mediciones:
            try:
                t = datetime.fromisoformat(m["ts"].replace("Z", "+00:00"))
                idx = min(int((t - t_inicio).total_seconds() / bucket_size), n_puntos - 1)
                kw = m.get("kw", 0.0)
                fp = m.get("fp", 0.0)
                fp_peso[idx] += fp * kw
                kw_peso[idx] += kw
            except Exception:
                pass
        return [
            round(fp_peso[i] / kw_peso[i], 4) if kw_peso[i] > 0 else 0.0
            for i in range(n_puntos)
        ]
```

- [ ] **Step 5: Corregir `pct_costo_especifico` en `calcular_kpis_produccion`**

Reemplaza el bloque de return de `calcular_kpis_produccion` (las líneas donde `pct_costo_especifico` retornaba `None`):

```python
    consumo_esp = round(energia_kwh / m2_producidos_atribuidos, 4)
    costo_esp: float | None = None
    pct_costo_esp: float | None = None
    if costo_total_mxn is not None and costo_total_mxn > 0:
        costo_esp = round(costo_total_mxn / m2_producidos_atribuidos, 4)
        pct_costo_esp = round(costo_esp / costo_total_mxn * 100, 2)

    return {
        "consumo_especifico_kwh_m2": consumo_esp,
        "costo_especifico_mxn_m2": costo_esp,
        "pct_costo_especifico": pct_costo_esp,
        "m2_producidos": round(m2_producidos_atribuidos, 2),
    }
```

- [ ] **Step 6: Ejecutar todos los tests y verificar**

```bash
python3 -m pytest tests/test_telemetria_kpis.py -v
```

Esperado: 10 tests passing (los 9 anteriores + el nuevo test_g). El test_f aún pasa porque `generar_sparkline` sigue siendo retrocompatible (tipo='energia' por defecto).

- [ ] **Step 7: Commit**

```bash
git add calc/telemetria_kpis.py tests/test_telemetria_kpis.py
git commit -m "feat(telemetria-D7A): determinar_periodo_anterior, generar_sparkline con tipo, pct_costo_especifico corregido"
```

---

### Task 2: `obtener_mediciones_para_rango` en repositorio + test_h

**Files:**
- Modify: `storage/repository.py`
- Modify: `tests/test_telemetria_kpis.py`

**Interfaces:**
- Consumes de Task 1: nada (tarea independiente).
- Produces (consumida por Task 4):
  ```python
  obtener_mediciones_para_rango(medidor_id: int, desde: str, hasta: str, rango: str) -> list[dict]
  # cada dict: {"timestamp": str, "potencia_activa_kw": float, "factor_potencia": float, "energia_activa_importada_kwh": float}
  ```

- [ ] **Step 1: Escribir test_h que falla**

Añade al final de `tests/test_telemetria_kpis.py`:

```python
def test_h_obtener_mediciones_para_rango_elige_tabla():
    """rango='24h' llama a obtener_mediciones_recientes; '7d' llama a obtener_agregados_15min."""
    from unittest.mock import patch, MagicMock
    from storage.repository import obtener_mediciones_para_rango

    fila_real = {"timestamp": "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0,
                 "factor_potencia": 0.90, "energia_activa_importada_kwh": 25.0}
    fila_agg  = {"bucket_15min": "2024-01-01T00:00:00Z", "potencia_activa_kw": 90.0,
                 "factor_potencia": 0.88, "energia_activa_importada_kwh": 22.5}

    with patch("storage.repository.obtener_mediciones_recientes", return_value=[fila_real]) as mock_omr, \
         patch("storage.repository.obtener_agregados_15min", return_value=[fila_agg]) as mock_oa15:

        # 24h → mediciones_recientes
        r24 = obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "24h")
        mock_omr.assert_called_once()
        mock_oa15.assert_not_called()
        assert r24[0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert r24[0]["potencia_activa_kw"] == 100.0

        mock_omr.reset_mock()
        mock_oa15.reset_mock()

        # 7d → agregados_15min
        r7 = obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-08T00:00:00Z", "7d")
        mock_oa15.assert_called_once()
        mock_omr.assert_not_called()
        assert r7[0]["timestamp"] == "2024-01-01T00:00:00Z"   # campo normalizado
        assert r7[0]["potencia_activa_kw"] == 90.0

        mock_omr.reset_mock()
        mock_oa15.reset_mock()

        # 30d → también agregados_15min
        obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-31T00:00:00Z", "30d")
        mock_oa15.assert_called_once()
        mock_omr.assert_not_called()
```

- [ ] **Step 2: Verificar que falla (ImportError)**

```bash
python3 -m pytest tests/test_telemetria_kpis.py::test_h_obtener_mediciones_para_rango_elige_tabla -v
```

Esperado: `ImportError: cannot import name 'obtener_mediciones_para_rango'`

- [ ] **Step 3: Implementar `obtener_mediciones_para_rango` en `storage/repository.py`**

Lee el final de `storage/repository.py` para saber dónde insertar. Añade después de `obtener_produccion_diaria`:

```python
def obtener_mediciones_para_rango(
    medidor_id: int,
    desde: str,
    hasta: str,
    rango: str,
) -> list[dict]:
    """Selecciona la tabla correcta según el rango y devuelve dicts homogeneizados.

    rango='24h': mediciones_tiempo_real (resolución real, campo 'timestamp').
    rango='7d' o '30d': mediciones_agregadas_15min (campo 'bucket_15min').

    Campos del dict retornado:
      timestamp, potencia_activa_kw, factor_potencia, energia_activa_importada_kwh.
    """
    if rango == "24h":
        rows = obtener_mediciones_recientes(medidor_id, desde, hasta)
        return [
            {
                "timestamp": r["timestamp"],
                "potencia_activa_kw": float(r.get("potencia_activa_kw") or 0),
                "factor_potencia": float(r.get("factor_potencia") or 0),
                "energia_activa_importada_kwh": float(
                    r.get("energia_activa_importada_kwh") or 0
                ),
            }
            for r in rows
        ]
    else:  # 7d, 30d
        rows = obtener_agregados_15min(medidor_id, desde, hasta)
        return [
            {
                "timestamp": r["bucket_15min"],
                "potencia_activa_kw": float(r.get("potencia_activa_kw") or 0),
                "factor_potencia": float(r.get("factor_potencia") or 0),
                "energia_activa_importada_kwh": float(
                    r.get("energia_activa_importada_kwh") or 0
                ),
            }
            for r in rows
        ]
```

- [ ] **Step 4: Ejecutar todos los tests y verificar**

```bash
python3 -m pytest tests/test_telemetria_kpis.py tests/test_dashboard_telemetria.py -v
```

Esperado: 11 tests de `test_telemetria_kpis.py` + 8 de `test_dashboard_telemetria.py` = 19 passing.

- [ ] **Step 5: Commit**

```bash
git add storage/repository.py tests/test_telemetria_kpis.py
git commit -m "feat(telemetria-D7A): obtener_mediciones_para_rango con seleccion de tabla por rango"
```

---

### Task 3: Seed extendido a 60 días

**Files:**
- Modify: `scripts/seed_iberica.py`

**Interfaces:**
- Consumes: `generar_mediciones_por_carga` (ya importada de `telemetria/seed.py`), `insertar_mediciones_batch` (ya importada de `storage/repository.py`).
- Produces: nada para las otras tasks (infraestructura de datos).

**Nota de implementación:** No hay tests automáticos para este task — el script es una herramienta CLI. La verificación es ejecutar el script y consultar la BD. Los tests unitarios no simulan Supabase para el seed.

- [ ] **Step 1: Reemplazar `_sembrar_historico_mes_anterior` con `_sembrar_historico_60_dias`**

Lee `scripts/seed_iberica.py` (líneas 316–366) para ver la función que se reemplaza. Borra `_sembrar_historico_mes_anterior` completa y añade en su lugar:

```python
def _sembrar_historico_60_dias(planta: dict, forzar: bool) -> int:
    """Genera 60 días de mediciones históricas para cada CBT del cliente.

    60 días × 96 muestras/día = 5,760 muestras por CBT.
    12 CBTs × 5,760 = 69,120 muestras totales (para dos plantas combinadas).
    Usa semilla determinista por medidor.id para reproducibilidad.
    Chunks de 1,000 manejados por insertar_mediciones_batch (ya existente).
    """
    from storage.repository import _supabase

    cid = planta["cliente_id"]
    ahora_utc = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    desde_60d = ahora_utc - timedelta(days=60)
    desde_60d_iso = desde_60d.strftime("%Y-%m-%dT%H:%M:%SZ")

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

    total = 0
    for carga in cargas:
        mid = carga["id"]

        if forzar:
            # Borrar todo el rango de 60 días para este medidor
            _supabase.table("mediciones_tiempo_real").delete().eq(
                "medidor_id", mid
            ).gte("timestamp", desde_60d_iso).execute()
        else:
            # Saltar si ya hay más de 5000 muestras en el rango
            resp_cnt = (
                _supabase.table("mediciones_tiempo_real")
                .select("medidor_id", count="exact")
                .eq("medidor_id", mid)
                .gte("timestamp", desde_60d_iso)
                .limit(1)
                .execute()
            )
            if (resp_cnt.count or 0) > 5000:
                print(
                    f"    CBT {mid} ({carga.get('nombre', '')}): "
                    f"ya tiene {resp_cnt.count} muestras en los últimos 60d, saltando."
                )
                continue

        # Generar día a día: 96 muestras/día × 60 días
        for dia in range(60):
            dia_desde = desde_60d + timedelta(days=dia)
            meds = generar_mediciones_por_carga(carga, dia_desde, n=96, intervalo=15)
            total += insertar_mediciones_batch(meds)
            if (dia + 1) % 10 == 0:
                print(
                    f"    CBT {mid} ({carga.get('nombre', '')}): "
                    f"{dia + 1}/60 días procesados..."
                )

    return total
```

- [ ] **Step 2: Actualizar `_sembrar_produccion_diaria` — cambiar a 60 días en `main()`**

En `main()`, cambia la llamada a `_sembrar_produccion_diaria` de `dias=8` a `dias=60`:

```python
        np = _sembrar_produccion_diaria(planta, dias=60, forzar=args.forzar)
```

- [ ] **Step 3: Actualizar `main()` — reemplazar llamada a `_sembrar_historico_mes_anterior` con `_sembrar_historico_60_dias`**

En `main()`, dentro del `for planta in PLANTAS`, busca:
```python
        nh = _sembrar_historico_mes_anterior(planta, forzar=args.forzar)
```
Cámbiala por:
```python
        nh = _sembrar_historico_60_dias(planta, forzar=args.forzar)
```

También actualiza la línea de print del resumen. El resto de `main()` (totales, reportes) ya funciona porque usa `totales["historico"]` igual que antes.

- [ ] **Step 4: Verificar sintaxis sin ejecutar contra Supabase**

```bash
python3 -c "import scripts.seed_iberica; print('OK')" 2>&1 || python3 -m py_compile scripts/seed_iberica.py && echo "Sintaxis OK"
```

Esperado: `Sintaxis OK` (o `OK`).

- [ ] **Step 5: Verificar que los tests no se rompen**

```bash
python3 -m pytest tests/test_telemetria_kpis.py tests/test_dashboard_telemetria.py -q
```

Esperado: 19/19 passing (el seed no tiene tests automáticos — solo la verificación de sintaxis importa aquí).

- [ ] **Step 6: Commit**

```bash
git add scripts/seed_iberica.py
git commit -m "feat(telemetria-D7A): seed extendido a 60 dias de historico por CBT con idempotencia"
```

---

### Task 4: Actualizar endpoint — parallel fetch, sparkline dinámico, `determinar_periodo_anterior`

**Files:**
- Modify: `web/app.py` — función `cliente_dashboard_telemetria_data`

**Interfaces:**
- Consumes de Task 1: `determinar_periodo_anterior` de `calc.telemetria_kpis`
- Consumes de Task 2: `obtener_mediciones_para_rango` de `storage.repository`

**Contexto del endpoint actual (líneas relevantes en `web/app.py`):**

```python
# Línea ~2706: imports actuales del endpoint
from storage.repository import (
    obtener_arbol_medidores as _oam,
    obtener_descendientes_ids as _odi,
    obtener_mediciones_recientes as _omr,
    obtener_agregados_15min as _oa15,
)

# Línea ~2776: fetch actual (loop serial con if rango == "24h")
for hid in todas_hojas_ids:
    if rango == "24h":
        rows = _omr(hid, desde_iso, hasta_iso)
        mediciones_por_hoja[hid] = [...]
    else:
        rows = _oa15(hid, desde_iso, hasta_iso)
        mediciones_por_hoja[hid] = [...]

# Línea ~2882: periodo anterior calculado inline
desde_ant = desde - timedelta(days=30)
hasta_ant = ahora - timedelta(days=30)

# Línea ~2887: fetch anterior (loop serial)
for hid in hojas_ids_nodo:
    if rango == "24h":
        rows_ant = _omr(hid, desde_ant_iso, hasta_ant_iso)
    else:
        rows_ant = _oa15(hid, desde_ant_iso, hasta_ant_iso)

# Línea ~2971: sparkline hardcodeado
_N_SPARK = 24
```

- [ ] **Step 1: Actualizar imports en el endpoint**

Reemplaza el bloque de imports de repository dentro de `cliente_dashboard_telemetria_data`:

```python
        from storage.repository import (
            obtener_arbol_medidores as _oam,
            obtener_descendientes_ids as _odi,
            obtener_mediciones_para_rango as _omfr,
        )
        from calc.telemetria_kpis import determinar_periodo_anterior as _dpa
        from concurrent.futures import ThreadPoolExecutor
```

(elimina `_omr` y `_oa15` de los imports del endpoint — ya no los usará directamente.)

- [ ] **Step 2: Reemplazar cálculo inline del periodo anterior**

Busca el bloque:
```python
        desde_ant = desde - timedelta(days=30)
        hasta_ant = ahora - timedelta(days=30)
        desde_ant_iso = desde_ant.strftime("%Y-%m-%dT%H:%M:%SZ")
        hasta_ant_iso = hasta_ant.strftime("%Y-%m-%dT%H:%M:%SZ")
```

Reemplázalo con:
```python
        desde_ant, hasta_ant, etiqueta_ant = _dpa(rango, ahora)
        desde_ant_iso = desde_ant.strftime("%Y-%m-%dT%H:%M:%SZ")
        hasta_ant_iso = hasta_ant.strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 3: Reemplazar el fetch serial con fetch paralelo**

Reemplaza el bloque de fetch actual (loop `for hid in todas_hojas_ids`) y el bloque de fetch anterior (loop `for hid in hojas_ids_nodo`) con el siguiente bloque paralelo.

El código a reemplazar es aproximadamente:
```python
        # Fetch mediciones para TODAS las hojas del árbol ...
        mediciones_por_hoja = {}
        for hid in todas_hojas_ids:
            if rango == "24h":
                rows = _omr(hid, desde_iso, hasta_iso)
                mediciones_por_hoja[hid] = [...]
            else:
                rows = _oa15(hid, desde_iso, hasta_iso)
                mediciones_por_hoja[hid] = [...]
```

Y más adelante:
```python
        mediciones_ant = {}
        for hid in hojas_ids_nodo:
            if rango == "24h":
                rows_ant = _omr(hid, desde_ant_iso, hasta_ant_iso)
                mediciones_ant[hid] = [...]
            else:
                rows_ant = _oa15(hid, desde_ant_iso, hasta_ant_iso)
                mediciones_ant[hid] = [...]
```

Reemplaza ambos bloques con este único bloque de fetch paralelo (ponlo en el mismo punto donde estaba el primer `mediciones_por_hoja = {}`):

```python
        # Fetch paralelo: periodo actual (todas las hojas) + anterior (hojas del nodo)
        def _fetch_todas_hojas(hids, desde_s, hasta_s):
            resultado = {}
            for hid in hids:
                rows = _omfr(hid, desde_s, hasta_s, rango)
                resultado[hid] = [
                    {
                        "ts": r["timestamp"],
                        "kw": float(r.get("potencia_activa_kw") or 0),
                        "fp": float(r.get("factor_potencia") or 0),
                    }
                    for r in rows
                ]
            return resultado

        with ThreadPoolExecutor(max_workers=2) as _ex:
            _fut_act = _ex.submit(_fetch_todas_hojas, todas_hojas_ids, desde_iso, hasta_iso)
            _fut_ant = _ex.submit(_fetch_todas_hojas, hojas_ids_nodo, desde_ant_iso, hasta_ant_iso)
            mediciones_por_hoja = _fut_act.result()
            mediciones_ant = _fut_ant.result()
```

- [ ] **Step 4: Actualizar sparkline dinámico y añadir `n_puntos_sparkline` a meta**

Reemplaza:
```python
        _N_SPARK = 24
```

Con:
```python
        _N_SPARK = {"24h": 24, "7d": 7, "30d": 30}.get(rango, 24)
```

Luego en el dict de `kpis_paneles["meta"]`, añade:
```python
                "n_puntos_sparkline": _N_SPARK,
```

Y en la misma sección `"meta"`, actualiza `"periodo_anterior_etiqueta"` para usar la etiqueta calculada:
```python
                "periodo_anterior_etiqueta": etiqueta_ant,
```

(Antes era el string literal `"mismo día del mes anterior"` — ahora es la variable del resultado de `_dpa`.)

- [ ] **Step 5: Ejecutar todos los tests y verificar**

```bash
python3 -m pytest tests/test_telemetria_kpis.py tests/test_dashboard_telemetria.py -v
```

Esperado: 11 + 8 = 19 passing. Los tests de integración (g, h, i) seguirán pasando porque mockean las funciones del repositorio — pero ahora mockean `obtener_mediciones_para_rango` en lugar de `_omr`/`_oa15`. Si algún test de integración falla por el cambio de mock, ajusta el patch target en `tests/test_telemetria_kpis.py` de `obtener_mediciones_recientes` a `obtener_mediciones_para_rango` (los tests g-i ya mockean `obtener_mediciones_recientes` via `_patch_costo`, revisa que el mock cubra la nueva función).

- [ ] **Step 6: Commit**

```bash
git add web/app.py
git commit -m "feat(telemetria-D7A): fetch paralelo, sparkline dinamico por rango, determinar_periodo_anterior en endpoint"
```

---

### Task 5: CHANGELOG v2.80.0 + push

**Files:**
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: commits de Tasks 1-4.

- [ ] **Step 1: Añadir entrada v2.80.0 al inicio de CHANGELOG.md**

Inserta ANTES del bloque `## [2.79.0]`:

```markdown
## [2.80.0] — 2026-08-05

### Añadido — Fase 2 D7-A v2: histórico 60 días, selección de fuente por rango, sparkline dinámico

- `calc/telemetria_kpis.py` — nueva función `determinar_periodo_anterior(rango, ahora)`: calcula (desde_ant, hasta_ant, etiqueta) desplazando 30 días atrás con la misma anchura del rango. Función `generar_sparkline` extendida con param `tipo='energia'|'potencia'|'factor_potencia'` (retrocompatible). `calcular_kpis_produccion` ahora calcula `pct_costo_especifico = (costo_esp / costo_total) × 100` en lugar de retornar None.
- `storage/repository.py` — nueva función `obtener_mediciones_para_rango(medidor_id, desde, hasta, rango)`: enruta a `mediciones_tiempo_real` para rango='24h' y a `mediciones_agregadas_15min` para '7d'/'30d', devuelve dicts homogeneizados con campo `timestamp` normalizado.
- `scripts/seed_iberica.py` — `_sembrar_historico_mes_anterior` (1 día) reemplazada por `_sembrar_historico_60_dias` (60 días × 96 muestras = 5,760 por CBT; idempotente: salta si >5,000 muestras; --forzar borra el rango completo). `_sembrar_produccion_diaria` ahora cubre 60 días.
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data`: fetch paralelo con `ThreadPoolExecutor(max_workers=2)` (periodo actual + anterior simultáneos); usa `determinar_periodo_anterior` para calcular ventana anterior; sparkline dinámico (24h→24 pts, 7d→7 pts, 30d→30 pts); `n_puntos_sparkline` añadido a `kpis_paneles.meta`; `periodo_anterior_etiqueta` usa la etiqueta calculada según el rango.
- `tests/test_telemetria_kpis.py` — 2 nuevos tests: `test_g_determinar_periodo_anterior` (verifica las tres variantes de rango), `test_h_obtener_mediciones_para_rango_elige_tabla` (verifica routing a tabla correcta y normalización de campos).

```

- [ ] **Step 2: Commit y push**

```bash
git add CHANGELOG.md
git commit -m "chore: CHANGELOG v2.80.0 — D7-A v2 historico 60d, seleccion fuente por rango, sparkline dinamico"
git push
```

- [ ] **Step 3: Verificar push y log final**

```bash
git log --oneline -6
```

---

## Notas de implementación

**Por qué `pct_costo_especifico = costo_esp / costo_total_mxn × 100`:** En términos dimensionales esta fórmula da `(MXN/m²) / MXN × 100 = 100/m²`, que no es un porcentaje convencional. Es el valor que el spec especifica; el frontend definirá cómo presentarlo. Si la fórmula cambia en el futuro, solo cambia `calcular_kpis_produccion`.

**ThreadPoolExecutor con max_workers=2:** Supabase-py usa HTTPS/REST — stateless y thread-safe. Max workers = 2 porque solo hay 2 tareas independientes (actual y anterior). No hay ganancia en más threads.

**Verificación manual post-seed:**

Después de ejecutar `python3 scripts/seed_iberica.py --forzar`, verificar en Supabase:

```sql
-- Conteo de mediciones por CBT en los últimos 60 días
SELECT medidor_id, count(*)
FROM mediciones_tiempo_real
WHERE medidor_id IN (SELECT id FROM medidores WHERE cliente_id IN (44, 45))
  AND timestamp >= now() - interval '60 days'
GROUP BY medidor_id
ORDER BY medidor_id;
-- Esperado: ~5,760 por CBT, 12 CBTs = ~69,120 total

-- Producción diaria
SELECT cliente_id, count(*), min(fecha), max(fecha)
FROM produccion_diaria
GROUP BY cliente_id;
-- Esperado: 60 filas por cliente
```
