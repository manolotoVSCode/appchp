# D7-A v3: Backend KPIs Telemetría — Resolución 5-min y Agregado Horario

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la resolución 15-min del backend de KPIs de telemetría con resolución 5-min para el rango 24h y agregado horario para 7d/30d, sembrando 207,360 muestras con checkpointing y retry, y añadir un endpoint POST para captura manual de producción mensual.

**Architecture:** Dos nuevas materialized views (`mediciones_agregadas_5min`, `mediciones_agregadas_horarias`) se crean en Supabase con pg_cron de refresco. El repositorio enruta `obtener_mediciones_para_rango` a la vista correcta según el rango. El seed escribe en `mediciones_tiempo_real` a 5-min y persiste progreso en `/tmp/seed_iberica_progress.json` con retry exponencial. El endpoint restructura `kpis_paneles` a 10 KPIs (4+3+3) y añade un endpoint POST para distribuir m² mensuales.

**Tech Stack:** Python 3.11, Flask 3.x, supabase-py, pytest, pg_cron (PostgreSQL extension en Supabase).

## Global Constraints

- Acceso a DB **exclusivamente** vía `supabase-py` SDK. No psycopg2, no SQL directo.
- Toda query debe incluir `.limit(20000)`.
- Feature flag FASE2_HABILITADA: `abort(404)` si `not app.config.get("FASE2_HABILITADA", False)`. No decorador.
- Autenticación: inyectar sesión en tests vía `client.session_transaction()`. No llamar a Supabase en tests.
- Constantes de tipo de contrato desde `models/contrato.py`.
- Versión a publicar: **v2.81.0** (v2.79.0 y v2.80.0 ya existen en CHANGELOG.md).
- Tests: 15 letras (a-o), 16 funciones de test (d tiene 2 funciones). Archivo: `tests/test_telemetria_kpis.py`.
- Seed: semilla determinista `random.Random(medidor_id)` por medidor.
- Responder en español — código y commits en inglés.

---

## Mapa de archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|-----------------|
| `storage/migrations/202609_mediciones_5min_horarias.sql` | Crear | DDL: vistas materializadas + índices únicos + pg_cron |
| `storage/repository.py` | Modificar | Añadir `obtener_agregados_5min`, `obtener_agregados_horarios`, actualizar `obtener_mediciones_para_rango`, añadir `upsert_produccion_mes`, `obtener_produccion_para_periodo` |
| `scripts/seed_iberica.py` | Modificar | Reescribir `_sembrar_historico_60_dias` a 5-min + checkpointing + retry + verificación de migraciones |
| `calc/telemetria_costos.py` | Modificar | Añadir `obtener_precio_unitario(cliente_id, anio, mes, historico_completo)` |
| `web/app.py` | Modificar | Restructurar `kpis_paneles` (10 KPIs, fuente_precio, solo_en_rango); añadir `POST /clientes/<id>/telemetria/produccion` |
| `tests/test_telemetria_kpis.py` | Modificar | Reemplazar tests e y f; actualizar g, h, k; añadir l, m, n, o |
| `CHANGELOG.md` | Modificar | Entrada v2.81.0 |
| `CLAUDE.md` | Modificar | Actualizar secciones "Nuevas funcionalidades" e "Integración Telemática" |

---

### Task 1: Migrations — vistas materializadas 5-min y horaria

**Files:**
- Create: `storage/migrations/202609_mediciones_5min_horarias.sql`

**Interfaces:**
- Consumes: tabla `mediciones_tiempo_real` (columnas: `medidor_id`, `timestamp`, `potencia_activa_kw`, `factor_potencia`, `energia_activa_importada_kwh`)
- Produces: vistas `mediciones_agregadas_5min` (campos: `medidor_id`, `bucket_5min`, `potencia_activa_kw`, `factor_potencia`, `energia_activa_importada_kwh`) y `mediciones_agregadas_horarias` (campos: `medidor_id`, `bucket_hora`, `potencia_activa_kw`, `factor_potencia`, `energia_activa_importada_kwh`)

- [ ] **Step 1: Crear el archivo de migración**

```sql
-- storage/migrations/202609_mediciones_5min_horarias.sql
-- Vista materializada: buckets de 5 minutos
-- Ejecutar en Supabase SQL Editor.

CREATE MATERIALIZED VIEW IF NOT EXISTS mediciones_agregadas_5min AS
SELECT
    medidor_id,
    date_trunc('minute', timestamp AT TIME ZONE 'UTC')
        - (EXTRACT(MINUTE FROM timestamp)::int % 5) * INTERVAL '1 minute' AS bucket_5min,
    AVG(potencia_activa_kw)              AS potencia_activa_kw,
    AVG(factor_potencia)                 AS factor_potencia,
    SUM(energia_activa_importada_kwh)    AS energia_activa_importada_kwh
FROM mediciones_tiempo_real
GROUP BY medidor_id, bucket_5min;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mag_5min_medidor_bucket
    ON mediciones_agregadas_5min (medidor_id, bucket_5min);

-- Vista materializada: buckets horarios
CREATE MATERIALIZED VIEW IF NOT EXISTS mediciones_agregadas_horarias AS
SELECT
    medidor_id,
    date_trunc('hour', timestamp AT TIME ZONE 'UTC') AS bucket_hora,
    AVG(potencia_activa_kw)              AS potencia_activa_kw,
    AVG(factor_potencia)                 AS factor_potencia,
    SUM(energia_activa_importada_kwh)    AS energia_activa_importada_kwh
FROM mediciones_tiempo_real
GROUP BY medidor_id, bucket_hora;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mag_horaria_medidor_bucket
    ON mediciones_agregadas_horarias (medidor_id, bucket_hora);

-- pg_cron: refrescar vistas automáticamente
-- Requiere extensión pg_cron habilitada en Supabase (Dashboard → Extensions).
SELECT cron.schedule(
    'refresh_5min',
    '*/5 * * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mediciones_agregadas_5min'
);
SELECT cron.schedule(
    'refresh_horario',
    '0 * * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mediciones_agregadas_horarias'
);
```

- [ ] **Step 2: Anotar instrucción para el usuario**

Este archivo **no se ejecuta automáticamente**. El usuario debe ejecutarlo en el SQL Editor de Supabase antes de correr el seed. Añadir al final del archivo un comentario con la instrucción:

```sql
-- INSTRUCCIÓN: Ejecutar manualmente en Supabase → SQL Editor.
-- Después de crear las vistas, refrescar una vez:
--   REFRESH MATERIALIZED VIEW mediciones_agregadas_5min;
--   REFRESH MATERIALIZED VIEW mediciones_agregadas_horarias;
```

- [ ] **Step 3: Commit**

```bash
git add storage/migrations/202609_mediciones_5min_horarias.sql
git commit -m "feat(fase2-D7-A): DDL vistas materializadas 5-min y horaria + pg_cron"
```

---

### Task 2: Capa repository — nuevas funciones de fetch, upsert y producción

**Files:**
- Modify: `storage/repository.py` (zona telemetría, tras `obtener_agregados_15min`)
- Modify: `tests/test_telemetria_kpis.py` (actualizar test_k, reemplazar test_e/test_f, añadir test_f nuevo)

**Interfaces:**
- Consumes: vistas `mediciones_agregadas_5min` y `mediciones_agregadas_horarias` (Task 1), tabla `produccion_diaria`
- Produces:
  - `obtener_agregados_5min(medidor_id: int, desde: str, hasta: str) -> list[dict]` — campo clave: `bucket_5min`
  - `obtener_agregados_horarios(medidor_id: int, desde: str, hasta: str) -> list[dict]` — campo clave: `bucket_hora`
  - `obtener_mediciones_para_rango(medidor_id, desde, hasta, rango)` ahora: `rango='24h'` → `obtener_agregados_5min`; `rango='7d'|'30d'` → `obtener_agregados_horarios`
  - `upsert_produccion_mes(cliente_id: int, anio: int, mes: int, m2_mes: float) -> int` — distribuye m² por día
  - `obtener_produccion_para_periodo(cliente_id: int, desde: datetime, hasta: datetime, usar_promedio_historico: bool = False) -> float` — suma m² del rango; si vacío y usar_promedio_historico=True, devuelve promedio histórico × días

- [ ] **Step 1: Escribir tests que fallarán**

En `tests/test_telemetria_kpis.py`:

1. **Eliminar** las funciones `test_e_baseline_vacio_retorna_none` y `test_f_sparkline_96_a_24_puntos`.

2. **Añadir** al final de la sección "Tests a-f":

```python
def test_f_produccion_para_periodo_usa_promedio():
    """Si no hay datos en el rango y usar_promedio_historico=True, usa el promedio histórico."""
    from datetime import datetime, timezone
    from unittest.mock import patch
    from storage.repository import obtener_produccion_para_periodo

    historico_data = [
        {"fecha": "2024-01-01", "m2_producidos": 5000.0},
        {"fecha": "2024-01-02", "m2_producidos": 5000.0},
        {"fecha": "2024-01-03", "m2_producidos": 0.0},  # domingo
    ]

    desde = datetime(2024, 2, 1, tzinfo=timezone.utc)
    hasta = datetime(2024, 2, 3, tzinfo=timezone.utc)

    with patch("storage.repository.obtener_produccion_diaria") as mock_opd:
        mock_opd.side_effect = [
            [],             # primera llamada: sin datos en el rango [2024-02-01, 2024-02-03]
            historico_data, # segunda llamada: datos históricos de hasta 90 días atrás
        ]
        result = obtener_produccion_para_periodo(44, desde, hasta, usar_promedio_historico=True)

    # Promedio de [5000, 5000, 0] = 10000/3 ≈ 3333.33; × 3 días = 10000
    assert abs(result - 10000.0) < 1.0


def test_f2_produccion_para_periodo_sin_historico_retorna_cero():
    """Si no hay datos y usar_promedio_historico=True pero tampoco hay histórico, retorna 0."""
    from datetime import datetime, timezone
    from unittest.mock import patch
    from storage.repository import obtener_produccion_para_periodo

    desde = datetime(2024, 2, 1, tzinfo=timezone.utc)
    hasta = datetime(2024, 2, 3, tzinfo=timezone.utc)

    with patch("storage.repository.obtener_produccion_diaria") as mock_opd:
        mock_opd.side_effect = [[], []]  # sin datos en ambas llamadas
        result = obtener_produccion_para_periodo(44, desde, hasta, usar_promedio_historico=True)

    assert result == 0.0
```

3. **Reemplazar** el cuerpo de `test_k_obtener_mediciones_para_rango_elige_tabla`:

```python
def test_k_obtener_mediciones_para_rango_elige_tabla():
    """rango='24h' llama a obtener_agregados_5min;
    '7d' y '30d' llaman a obtener_agregados_horarios."""
    from unittest.mock import patch, MagicMock
    from storage.repository import obtener_mediciones_para_rango

    fila_5min   = {"bucket_5min":  "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0,
                   "factor_potencia": 0.90, "energia_activa_importada_kwh": 8.33}
    fila_hora   = {"bucket_hora":  "2024-01-01T00:00:00Z", "potencia_activa_kw": 95.0,
                   "factor_potencia": 0.88, "energia_activa_importada_kwh": 95.0}

    with patch("storage.repository.obtener_agregados_5min", return_value=[fila_5min]) as mock_5m, \
         patch("storage.repository.obtener_agregados_horarios", return_value=[fila_hora]) as mock_ho:

        # 24h → 5min
        r24 = obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "24h")
        mock_5m.assert_called_once()
        mock_ho.assert_not_called()
        assert r24[0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert r24[0]["potencia_activa_kw"] == 100.0

        mock_5m.reset_mock()
        mock_ho.reset_mock()

        # 7d → horario
        r7 = obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-08T00:00:00Z", "7d")
        mock_ho.assert_called_once()
        mock_5m.assert_not_called()
        assert r7[0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert r7[0]["potencia_activa_kw"] == 95.0

        mock_5m.reset_mock()
        mock_ho.reset_mock()

        # 30d → horario
        obtener_mediciones_para_rango(1, "2024-01-01T00:00:00Z", "2024-01-31T00:00:00Z", "30d")
        mock_ho.assert_called_once()
        mock_5m.assert_not_called()
```

- [ ] **Step 2: Correr tests para verificar que fallan**

```bash
pytest tests/test_telemetria_kpis.py::test_f_produccion_para_periodo_usa_promedio \
       tests/test_telemetria_kpis.py::test_f2_produccion_para_periodo_sin_historico_retorna_cero \
       tests/test_telemetria_kpis.py::test_k_obtener_mediciones_para_rango_elige_tabla \
       -v
```

Esperado: FAIL con `ImportError` o `AttributeError` (funciones no existen aún).

- [ ] **Step 3: Implementar en `storage/repository.py`**

Localizar la función `obtener_agregados_15min` (aprox. línea 1532) e insertar inmediatamente después:

```python
def obtener_agregados_5min(
    medidor_id: int,
    desde: str,
    hasta: str,
) -> list[dict]:
    """Buckets de 5 minutos en mediciones_agregadas_5min para un medidor en [desde, hasta].

    Ordenados por bucket_5min ASC.
    """
    resp = (
        _supabase.table("mediciones_agregadas_5min")
        .select("*")
        .eq("medidor_id", medidor_id)
        .gte("bucket_5min", desde)
        .lte("bucket_5min", hasta)
        .order("bucket_5min", desc=False)
        .limit(20000)
        .execute()
    )
    return resp.data or []


def obtener_agregados_horarios(
    medidor_id: int,
    desde: str,
    hasta: str,
) -> list[dict]:
    """Buckets horarios en mediciones_agregadas_horarias para un medidor en [desde, hasta].

    Ordenados por bucket_hora ASC.
    """
    resp = (
        _supabase.table("mediciones_agregadas_horarias")
        .select("*")
        .eq("medidor_id", medidor_id)
        .gte("bucket_hora", desde)
        .lte("bucket_hora", hasta)
        .order("bucket_hora", desc=False)
        .limit(20000)
        .execute()
    )
    return resp.data or []
```

- [ ] **Step 4: Actualizar `obtener_mediciones_para_rango` (misma zona del archivo)**

Reemplazar el cuerpo completo de la función `obtener_mediciones_para_rango` (aprox. línea 1984):

```python
def obtener_mediciones_para_rango(
    medidor_id: int,
    desde: str,
    hasta: str,
    rango: str,
) -> list[dict]:
    """Selecciona la fuente correcta según el rango y devuelve dicts homogeneizados.

    rango='24h': mediciones_agregadas_5min (bucket_5min → timestamp).
    rango='7d' o '30d': mediciones_agregadas_horarias (bucket_hora → timestamp).

    Campos del dict retornado:
      timestamp, potencia_activa_kw, factor_potencia, energia_activa_importada_kwh.
    """
    if rango == "24h":
        rows = obtener_agregados_5min(medidor_id, desde, hasta)
        return [
            {
                "timestamp": r["bucket_5min"],
                "potencia_activa_kw": float(r.get("potencia_activa_kw") or 0),
                "factor_potencia": float(r.get("factor_potencia") or 0),
                "energia_activa_importada_kwh": float(
                    r.get("energia_activa_importada_kwh") or 0
                ),
            }
            for r in rows
        ]
    else:  # 7d, 30d
        rows = obtener_agregados_horarios(medidor_id, desde, hasta)
        return [
            {
                "timestamp": r["bucket_hora"],
                "potencia_activa_kw": float(r.get("potencia_activa_kw") or 0),
                "factor_potencia": float(r.get("factor_potencia") or 0),
                "energia_activa_importada_kwh": float(
                    r.get("energia_activa_importada_kwh") or 0
                ),
            }
            for r in rows
        ]
```

- [ ] **Step 5: Añadir `upsert_produccion_mes` en `storage/repository.py`**

Añadir inmediatamente después de `obtener_produccion_diaria`:

```python
def upsert_produccion_mes(
    cliente_id: int,
    anio: int,
    mes: int,
    m2_mes: float,
) -> int:
    """Distribuye m2_mes entre los días del mes ponderando por tipo de día.

    Ponderación: L-V = 1.0, Sáb = 0.6, Dom = 0.0.
    Días con peso 0 (domingo) reciben m2 = 0.
    Retorna número de registros upserted.
    """
    import calendar
    from datetime import date

    n_dias = calendar.monthrange(anio, mes)[1]
    dias = [date(anio, mes, d) for d in range(1, n_dias + 1)]

    PESOS = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 0.6, 6: 0.0}
    pesos = [PESOS[d.weekday()] for d in dias]
    total_peso = sum(pesos)

    if total_peso == 0:
        return 0

    registros = [
        {
            "cliente_id": cliente_id,
            "fecha": dia.isoformat(),
            "m2_producidos": round(m2_mes * peso / total_peso, 2),
        }
        for dia, peso in zip(dias, pesos)
    ]

    n = 0
    for inicio in range(0, len(registros), 100):
        lote = registros[inicio : inicio + 100]
        _supabase.table("produccion_diaria").upsert(
            lote, on_conflict="cliente_id,fecha"
        ).execute()
        n += len(lote)
    return n
```

- [ ] **Step 6: Añadir `obtener_produccion_para_periodo` en `storage/repository.py`**

Añadir inmediatamente después de `upsert_produccion_mes`:

```python
def obtener_produccion_para_periodo(
    cliente_id: int,
    desde: datetime,
    hasta: datetime,
    usar_promedio_historico: bool = False,
) -> float:
    """Retorna m² producidos atribuibles al periodo [desde, hasta].

    Si usar_promedio_historico=True y no hay datos en el rango,
    calcula el promedio diario histórico (90 días previos) × días del rango.
    """
    from datetime import timedelta

    desde_str = desde.strftime("%Y-%m-%d")
    hasta_str = hasta.strftime("%Y-%m-%d")

    registros = obtener_produccion_diaria(cliente_id, desde_str, hasta_str)
    total = sum(float(r.get("m2_producidos") or 0) for r in registros)

    if total > 0 or not usar_promedio_historico:
        return total

    dias_rango = max(1, (hasta.date() - desde.date()).days + 1)
    limite_historico = (desde - timedelta(days=90)).strftime("%Y-%m-%d")
    historico = obtener_produccion_diaria(
        cliente_id,
        limite_historico,
        (desde - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if not historico:
        return 0.0

    m2_dias = [float(r.get("m2_producidos") or 0) for r in historico]
    promedio_diario = sum(m2_dias) / len(m2_dias)
    return round(promedio_diario * dias_rango, 2)
```

Notar que `datetime` ya está importado en repository.py en las importaciones al tope del archivo — verificar que sea así antes del método; si no está, añadir `from datetime import datetime` al bloque de imports al inicio.

- [ ] **Step 7: Correr tests para verificar que pasan**

```bash
pytest tests/test_telemetria_kpis.py::test_f_produccion_para_periodo_usa_promedio \
       tests/test_telemetria_kpis.py::test_f2_produccion_para_periodo_sin_historico_retorna_cero \
       tests/test_telemetria_kpis.py::test_k_obtener_mediciones_para_rango_elige_tabla \
       -v
```

Esperado: PASS × 3.

- [ ] **Step 8: Correr suite completa para verificar sin regresiones**

```bash
pytest tests/test_telemetria_kpis.py -v
```

Esperado: todos los tests restantes siguen en PASS (a, b, c, d×2, g, h, i, j).

- [ ] **Step 9: Commit**

```bash
git add storage/repository.py tests/test_telemetria_kpis.py
git commit -m "feat(fase2-D7-A): repository 5min/horario fetch, upsert_produccion_mes, obtener_produccion_para_periodo"
```

---

### Task 3: Seed — 288 muestras/día, checkpointing y retry

**Files:**
- Modify: `scripts/seed_iberica.py`

**Interfaces:**
- Consumes: `telemetria.seed.generar_mediciones_por_carga(medidor, desde_utc, n, intervalo)`, `storage.repository.insertar_mediciones_batch`
- Produces: `_verificar_migraciones() -> bool`, `_sembrar_historico_60_dias` reescrita (288 muestras/día + checkpointing + retry)

- [ ] **Step 1: Añadir función `_verificar_migraciones` en `scripts/seed_iberica.py`**

Insertar después de los imports (antes de la definición de `PLANTA_1`):

```python
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
```

- [ ] **Step 2: Añadir helpers de checkpointing**

Insertar inmediatamente después de `_verificar_migraciones`:

```python
import json as _json_mod
import os as _os_mod

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
```

Nota: el script ya importa `json` y `os` de Python estándar en su bloque de imports al inicio. Verificar si ya están importados antes de añadir las importaciones privadas `_json_mod` / `_os_mod`; si ya están como `import json` / `import os`, usar `json` y `os` directamente en el cuerpo de los helpers, sin los alias con guión bajo.

- [ ] **Step 3: Reemplazar `_sembrar_historico_60_dias` por la versión 5-min**

Reemplazar la función completa `_sembrar_historico_60_dias` con:

```python
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
        import os
        os.remove(_CHECKPOINT_FILE)
    except FileNotFoundError:
        pass

    return total
```

El módulo `time` ya está importado como `import time` al inicio del archivo — verificar antes de añadir.

- [ ] **Step 4: Actualizar `_sembrar_mediciones` a resolución 5-min**

En la función `_sembrar_mediciones`, cambiar:

```python
n_intervalo = dias * 24 * 4   # 15-min → 4/h → 672 por día × días
```

por:

```python
n_intervalo = dias * 24 * 12   # 5-min → 12/h → 2016 por 7 días
```

Y cambiar la llamada a `generar_mediciones_por_carga`:

```python
meds = generar_mediciones_por_carga(carga, desde, n=n_intervalo, intervalo=15)
```

por:

```python
meds = generar_mediciones_por_carga(carga, desde, n=n_intervalo, intervalo=5)
```

- [ ] **Step 5: Verificar que el script parse sin errores**

```bash
python -c "import scripts.seed_iberica" 2>&1 || python scripts/seed_iberica.py --help
```

Esperado: sin ImportError; muestra el help.

- [ ] **Step 6: Commit**

```bash
git add scripts/seed_iberica.py
git commit -m "feat(fase2-D7-A): seed 5-min 288/día, checkpointing con retry exponencial, verificación de migraciones"
```

---

### Task 4: Restructurar KPIs, añadir `obtener_precio_unitario` y endpoint POST

**Files:**
- Modify: `calc/telemetria_costos.py`
- Modify: `web/app.py`
- Modify: `tests/test_telemetria_kpis.py`

**Interfaces:**
- Consumes:
  - `calcular_costo_periodo` existente en `calc/telemetria_costos.py`
  - `upsert_produccion_mes(cliente_id, anio, mes, m2_mes) -> int` (Task 2)
  - sesión Flask vía `get_current_user()` de `web/auth.py`
- Produces:
  - `obtener_precio_unitario(cliente_id: int, anio: int, mes: int, historico_completo: dict | None = None) -> dict` en `calc/telemetria_costos.py`
  - `kpis_paneles` con 10 KPIs: energeticos×4, economicos×3 (+ fuente_precio en costo_unitario), produccion×3 (+ solo_en_rango: ["30d"])
  - `POST /clientes/<int:cliente_id>/telemetria/produccion` → `{"ok": True, "registros": N}`

- [ ] **Step 1: Escribir tests que fallarán**

En `tests/test_telemetria_kpis.py`, añadir al final del archivo:

```python
# ── Tests e, l-o (nuevos) ─────────────────────────────────────────────────────


def test_e_precio_unitario_usa_historico_completo():
    """Si historico_completo tiene (anio, mes), retorna desde cache sin llamar a la BD."""
    from unittest.mock import patch
    from calc.telemetria_costos import obtener_precio_unitario

    historico = {
        (2024, 1): {
            "precio_mxn_kwh": 3.5,
            "fuente": "cache_test",
            "mes_referencia": "2024-01",
        }
    }

    with patch(
        "calc.telemetria_costos.obtener_precio_unitario_mxn_kwh"
    ) as mock_db:
        result = obtener_precio_unitario(44, 2024, 1, historico_completo=historico)
        mock_db.assert_not_called()

    assert result["precio_mxn_kwh"] == 3.5
    assert result["fuente"] == "cache_test"


def test_l_produccion_solo_en_rango(_client_fase2):
    """kpis_paneles.produccion incluye solo_en_rango: ['30d']."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [{"fecha": "2024-01-01", "m2_producidos": 100.0}])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    produccion = data["kpis_paneles"]["produccion"]
    assert produccion.get("solo_en_rango") == ["30d"]


def test_m_post_telemetria_produccion_distribuye(_client_fase2):
    """POST /telemetria/produccion llama a upsert_produccion_mes y retorna ok."""
    _inyectar_sesion(_client_fase2)
    with patch("storage.repository.upsert_produccion_mes", return_value=31) as mock_up, \
         patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente):
        resp = _client_fase2.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 1, "m2_mes": 120000.0},
        )
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["ok"] is True
    assert body["registros"] == 31
    mock_up.assert_called_once_with(44, 2024, 1, 120000.0)


def test_n_post_telemetria_produccion_valida_input(_client_fase2):
    """POST con valores inválidos retorna 400."""
    _inyectar_sesion(_client_fase2)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente):
        # mes fuera de rango
        r1 = _client_fase2.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 13, "m2_mes": 1000.0},
        )
        assert r1.status_code == 400

        # m2_mes negativo
        r2 = _client_fase2.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 1, "m2_mes": -1.0},
        )
        assert r2.status_code == 400


def test_o_post_telemetria_produccion_requiere_auth(_client_fase2):
    """POST sin sesión retorna 401 o redirige a login."""
    resp = _client_fase2.post(
        "/clientes/44/telemetria/produccion",
        json={"anio": 2024, "mes": 1, "m2_mes": 1000.0},
    )
    assert resp.status_code in (401, 302)
```

También **actualizar** `test_g_endpoint_devuelve_kpis_paneles`, `test_h_kpis_flags_aplica_y_oculto`, y la función `_mock_repo` para que usen `obtener_mediciones_para_rango` en lugar de `obtener_mediciones_recientes`:

```python
def _mock_repo(mock_arbol, mock_meds_act, mock_meds_ant, mock_prod):
    """Retorna dict de patches para el endpoint de telemetría."""
    return {
        "storage.repository.get_cliente_con_conteos": MagicMock(side_effect=_mock_get_cliente),
        "storage.repository.obtener_arbol_medidores": MagicMock(return_value=mock_arbol),
        "storage.repository.obtener_descendientes_ids": MagicMock(return_value=[3]),
        "storage.repository.obtener_mediciones_para_rango": MagicMock(side_effect=[
            mock_meds_act,   # periodo actual (hoja 3)
            mock_meds_ant,   # periodo anterior (hoja 3)
        ]),
        "storage.repository.obtener_produccion_diaria": MagicMock(return_value=mock_prod),
        "calc.telemetria_costos.calcular_costo_periodo": MagicMock(return_value={
            "costo_mxn": 5000.0, "precio_mxn_kwh": 2.5,
            "fuente": "factura_mes_exacto", "mes_referencia": "2024-01",
        }),
    }
```

El cambio en `_mock_repo` afecta automáticamente a los tests g, h, i que lo usan. Los `_MEDS` mock siguen siendo los mismos pero ahora deben ser dicts homogeneizados (con clave `timestamp`, no `potencia_activa_kw`):

```python
_MEDS = [
    {"timestamp": "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0,
     "factor_potencia": 0.90, "energia_activa_importada_kwh": 8.33},
    {"timestamp": "2024-01-01T01:00:00Z", "potencia_activa_kw": 120.0,
     "factor_potencia": 0.91, "energia_activa_importada_kwh": 10.0},
]
```

Y actualizar `test_h_kpis_flags_aplica_y_oculto` para verificar la nueva estructura (sin `indice_utilizacion_pct`, con `fuente_precio`):

```python
def test_h_kpis_flags_aplica_y_oculto(_client_fase2):
    """pct_sobre_factura tiene oculto_en_nodo; costo_unitario_mxn_kwh tiene fuente_precio."""
    _inyectar_sesion(_client_fase2)
    patches = _mock_repo(_ARBOL, _MEDS, _MEDS, [])
    with patch.multiple("storage.repository", **{
        k.split(".")[-1]: v for k, v in patches.items() if k.startswith("storage.repository")
    }), patch("calc.telemetria_costos.calcular_costo_periodo",
               patches["calc.telemetria_costos.calcular_costo_periodo"]):
        resp = _client_fase2.get("/clientes/44/dashboard/telemetria/data?rango=24h")
    data = json.loads(resp.data)
    energeticos = data["kpis_paneles"]["energeticos"]
    # indice_utilizacion_pct ya NO existe en la nueva estructura
    assert "indice_utilizacion_pct" not in energeticos
    pct = data["kpis_paneles"]["economicos"]["pct_sobre_factura"]
    assert pct["oculto_en_nodo"] == ["acometida_cfe"]
    costo_u = data["kpis_paneles"]["economicos"]["costo_unitario_mxn_kwh"]
    assert "fuente_precio" in costo_u
```

- [ ] **Step 2: Correr tests para verificar que fallan**

```bash
pytest tests/test_telemetria_kpis.py::test_e_precio_unitario_usa_historico_completo \
       tests/test_telemetria_kpis.py::test_h_kpis_flags_aplica_y_oculto \
       tests/test_telemetria_kpis.py::test_l_produccion_solo_en_rango \
       tests/test_telemetria_kpis.py::test_m_post_telemetria_produccion_distribuye \
       tests/test_telemetria_kpis.py::test_n_post_telemetria_produccion_valida_input \
       tests/test_telemetria_kpis.py::test_o_post_telemetria_produccion_requiere_auth \
       -v
```

Esperado: FAIL (funciones / rutas no existen aún).

- [ ] **Step 3: Añadir `obtener_precio_unitario` en `calc/telemetria_costos.py`**

Añadir al final del archivo:

```python
def obtener_precio_unitario(
    cliente_id: int,
    anio: int,
    mes: int,
    historico_completo: dict | None = None,
) -> dict:
    """Retorna {precio_mxn_kwh, fuente, mes_referencia} para (cliente, año, mes).

    Si historico_completo es un dict con clave (anio, mes), retorna desde el
    cache sin consultar la BD (útil para evitar N+1 queries en series de meses).
    Si no, delega a obtener_precio_unitario_mxn_kwh().

    Retorna:
        {
          "precio_mxn_kwh": float | None,
          "fuente": str,
          "mes_referencia": str | None,
        }
    """
    if historico_completo is not None and (anio, mes) in historico_completo:
        return historico_completo[(anio, mes)]
    return obtener_precio_unitario_mxn_kwh(cliente_id, anio, mes)
```

- [ ] **Step 4: Restructurar `kpis_paneles` en `web/app.py`**

Localizar el bloque `kpis_paneles = {` (aprox. línea 3034) y reemplazarlo completo:

```python
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
            },
            "economicos": {
                "costo_total_mxn": _kpi_bloque(
                    kec_act.get("costo_total_mxn"), kec_ant.get("costo_total_mxn"),
                    None, None,
                    es_favorable_menor=True,
                ),
                "costo_unitario_mxn_kwh": _kpi_bloque(
                    kec_act.get("costo_unitario_mxn_kwh"),
                    kec_ant.get("costo_unitario_mxn_kwh"),
                    None, None,
                    es_favorable_menor=True,
                    fuente_precio=costo_info.get("fuente"),
                ),
                "pct_sobre_factura": _kpi_bloque(
                    kec_act.get("pct_sobre_factura"), kec_ant.get("pct_sobre_factura"),
                    None, None,
                    es_favorable_menor=True,
                    oculto_en_nodo=["acometida_cfe"],
                ),
            },
            "produccion": {
                "solo_en_rango": ["30d"],
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
                "periodo_anterior_etiqueta": etiqueta_ant,
                "n_puntos_sparkline": _N_SPARK,
            },
        }
```

- [ ] **Step 5: Añadir el endpoint `POST /clientes/<id>/telemetria/produccion` en `web/app.py`**

Localizar la línea `return app` al final de `create_app()` e insertar inmediatamente antes:

```python
    @app.route("/clientes/<int:cliente_id>/telemetria/produccion", methods=["POST"])
    def telemetria_produccion_post(cliente_id: int):
        """Captura manual de producción mensual: distribuye m² entre días del mes.

        Body JSON requerido: {"anio": int, "mes": int, "m2_mes": float}
        Ponderación: L-V = 1.0, Sáb = 0.6, Dom = 0.0.
        Retorna: {"ok": True, "registros": N}
        """
        from flask import jsonify, request
        if not app.config.get("FASE2_HABILITADA", False):
            abort(404)
        from web.auth import is_authenticated
        if not is_authenticated():
            return jsonify({"error": "No autenticado"}), 401

        payload = request.get_json(silent=True) or {}
        anio = payload.get("anio")
        mes = payload.get("mes")
        m2_mes = payload.get("m2_mes")

        if not isinstance(anio, int) or anio < 2000 or anio > 2100:
            return jsonify({"error": "anio inválido"}), 400
        if not isinstance(mes, int) or mes < 1 or mes > 12:
            return jsonify({"error": "mes inválido (1-12)"}), 400
        if not isinstance(m2_mes, (int, float)) or m2_mes < 0:
            return jsonify({"error": "m2_mes debe ser >= 0"}), 400

        from storage.repository import upsert_produccion_mes
        n = upsert_produccion_mes(cliente_id, anio, mes, float(m2_mes))
        return jsonify({"ok": True, "registros": n})
```

- [ ] **Step 6: Correr tests nuevos**

```bash
pytest tests/test_telemetria_kpis.py::test_e_precio_unitario_usa_historico_completo \
       tests/test_telemetria_kpis.py::test_h_kpis_flags_aplica_y_oculto \
       tests/test_telemetria_kpis.py::test_l_produccion_solo_en_rango \
       tests/test_telemetria_kpis.py::test_m_post_telemetria_produccion_distribuye \
       tests/test_telemetria_kpis.py::test_n_post_telemetria_produccion_valida_input \
       tests/test_telemetria_kpis.py::test_o_post_telemetria_produccion_requiere_auth \
       -v
```

Esperado: PASS × 6.

- [ ] **Step 7: Correr suite completa**

```bash
pytest tests/test_telemetria_kpis.py -v
```

Esperado: PASS en todos los tests (a, b, c, d×2, e, f, f2, g, h, i, j, k, l, m, n, o).

- [ ] **Step 8: Correr tests de regresión general**

```bash
pytest tests/ -v --ignore=tests/integration
```

Esperado: sin regresiones.

- [ ] **Step 9: Commit**

```bash
git add calc/telemetria_costos.py web/app.py tests/test_telemetria_kpis.py
git commit -m "feat(fase2-D7-A): kpis_paneles 10 KPIs, fuente_precio, solo_en_rango, POST produccion"
```

---

### Task 5: Finalización — CHANGELOG, CLAUDE.md, commit y push

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: todo lo implementado en Tasks 1-4
- Produces: commit de versión v2.81.0, push a `origin/main`

- [ ] **Step 1: Añadir entrada v2.81.0 al inicio de `CHANGELOG.md`**

```markdown
## [2.81.0] — 2026-08-05

### Añadido — Fase 2 D7-A v3: resolución 5-min, agregado horario, seed 207k muestras, endpoint POST producción

- `storage/migrations/202609_mediciones_5min_horarias.sql` — nuevas vistas materializadas `mediciones_agregadas_5min` (bucket de 5 min) y `mediciones_agregadas_horarias` (bucket horario), con índices únicos por (medidor_id, bucket) y jobs pg_cron de refresco (cada 5 min / cada hora).
- `storage/repository.py` — nuevas funciones `obtener_agregados_5min` y `obtener_agregados_horarios` que leen las nuevas vistas. `obtener_mediciones_para_rango` actualizado: rango='24h' → vista 5-min; rango='7d'/'30d' → vista horaria (antes usaba mediciones_tiempo_real y mediciones_agregadas_15min). Nuevas funciones `upsert_produccion_mes(cliente_id, anio, mes, m2_mes)` (distribuye m² por día con ponderación L-V:1.0/Sáb:0.6/Dom:0.0) y `obtener_produccion_para_periodo(cliente_id, desde, hasta, usar_promedio_historico)`.
- `scripts/seed_iberica.py` — `_sembrar_historico_60_dias` reescrita a resolución 5-min (288 muestras/día × 60 días × 12 CBTs = 207,360 total). Añadido checkpointing en `/tmp/seed_iberica_progress.json` con retry exponencial (hasta 5 intentos, backoff 2^n segundos). Verificación de migraciones antes de sembrar. `_sembrar_mediciones` base actualizada a 5-min (intervalo=5, n=2016).
- `calc/telemetria_costos.py` — nueva función `obtener_precio_unitario(cliente_id, anio, mes, historico_completo)` con soporte de cache pre-cargado para evitar N+1 queries.
- `web/app.py` — `kpis_paneles` restructurado a 10 KPIs: energeticos×4 (sin indice_utilizacion_pct), economicos×3 (sin ahorro_potencial_mxn; fuente_precio añadido a costo_unitario_mxn_kwh), produccion×3 (sin pct_costo_especifico; solo_en_rango: ["30d"] en el bloque). Nuevo endpoint `POST /clientes/<id>/telemetria/produccion` con validación de input y distribución por día.
- `tests/test_telemetria_kpis.py` — tests a-o: reemplazados test_e (→ precio_unitario con cache) y test_f (→ produccion_para_periodo con promedio histórico); actualizados test_g/h/k; añadidos test_l (solo_en_rango), test_m (POST distribución), test_n (POST validación), test_o (POST auth).
```

- [ ] **Step 2: Actualizar `CLAUDE.md`**

En la sección `### Nuevas funcionalidades`, reemplazar el bloque completo con:

```
### Nuevas funcionalidades
Último tema resuelto: v2.81.0 — D7-A v3: backend KPIs telemetría con resolución
5-min (mediciones_agregadas_5min) para 24h y horaria (mediciones_agregadas_horarias)
para 7d/30d; seed 207,360 muestras con checkpointing + retry; kpis_paneles 10 KPIs
(4+3+3), fuente_precio en costo_unitario, solo_en_rango en produccion; POST endpoint
para captura manual de m²/mes.
Pendiente: ejecutar migration 202609_mediciones_5min_horarias.sql en Supabase,
luego correr seed: python3 scripts/seed_iberica.py --forzar
```

En la sección `### Integración Telemática`, actualizar:

```
### Integración Telemática
Último tema resuelto: v2.81.0 — D7-A v3 completo: vistas 5-min + horaria,
seed 288 muestras/día, endpoint POST producción, kpis_paneles restructurado a 10 KPIs.
Pendiente: integración MQTT/pipeline real.
```

- [ ] **Step 3: Verificar tests por última vez**

```bash
pytest tests/test_telemetria_kpis.py -v
```

Esperado: todos PASS.

- [ ] **Step 4: Commit y push**

```bash
git add CHANGELOG.md CLAUDE.md
git commit -m "feat(fase2-D7-A): backend KPIs telemetria con seed 5-min directo, agregado horario, tabla produccion y endpoint POST manual"
git push origin main
```

---

## Self-Review

**Spec coverage:**

| Requisito spec | Tarea que lo implementa |
|----------------|------------------------|
| `mediciones_agregadas_5min` (vista materializada) | Task 1 |
| `mediciones_agregadas_horarias` (vista materializada) | Task 1 |
| pg_cron refresh jobs | Task 1 |
| `obtener_mediciones_para_rango` → 5min para 24h | Task 2 |
| `obtener_mediciones_para_rango` → horario para 7d/30d | Task 2 |
| `upsert_produccion_mes` con ponderación L-V/Sáb/Dom | Task 2 |
| `obtener_produccion_para_periodo` con promedio histórico | Task 2 |
| Seed 288 muestras/día (5-min) | Task 3 |
| Checkpointing `/tmp/seed_iberica_progress.json` | Task 3 |
| Retry exponencial (5 intentos, backoff 2^n) | Task 3 |
| Verificación de migraciones antes de sembrar | Task 3 |
| `obtener_precio_unitario` con cache `historico_completo` | Task 4 |
| `kpis_paneles` 10 KPIs (4+3+3), sin `indice_utilizacion_pct` | Task 4 |
| `kpis_paneles` sin `ahorro_potencial_mxn` | Task 4 |
| `fuente_precio` en `costo_unitario_mxn_kwh` | Task 4 |
| `solo_en_rango: ["30d"]` en bloque produccion | Task 4 |
| `POST /clientes/<id>/telemetria/produccion` | Task 4 |
| Tests a-o (15 letras) | Tasks 2 y 4 |
| CHANGELOG v2.81.0 | Task 5 |

**Placeholder scan:** ningún placeholder encontrado. Todos los steps tienen código concreto.

**Type consistency:**
- `obtener_agregados_5min` → campo clave `bucket_5min`; `obtener_mediciones_para_rango` lo normaliza a `timestamp` → OK.
- `obtener_agregados_horarios` → campo clave `bucket_hora`; `obtener_mediciones_para_rango` lo normaliza a `timestamp` → OK.
- `upsert_produccion_mes(cliente_id, anio, mes, m2_mes)` → llamado desde el endpoint y desde test_m con exactamente esos parámetros → OK.
- `obtener_precio_unitario(cliente_id, anio, mes, historico_completo=None)` → test_e llama `obtener_precio_unitario(44, 2024, 1, historico_completo=historico)` → OK.
- `_MEDS` actualizados en tests usan `timestamp` (no `potencia_activa_kw` como campo de bucket), consistente con dicts homogeneizados que produce `obtener_mediciones_para_rango` → OK.
