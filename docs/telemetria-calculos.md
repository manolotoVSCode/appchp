# Inventario de funciones de cálculo de telemetría

Todas las funciones son puras (no acceden a Supabase). Las consultas a BD se hacen en `storage/repository.py` y el resultado se pasa como argumento.

---

## `calc/telemetria_kpis.py`

### `calcular_kpis_energeticos(mediciones, potencia_nominal_kw) → dict`

```python
def calcular_kpis_energeticos(
    mediciones: list[dict],          # [{"ts": str ISO, "kw": float, "fp": float}]
    potencia_nominal_kw: float | None,
) -> dict:
```

Retorna `{energia_kwh, demanda_pico_kw, demanda_promedio_kw, factor_potencia_promedio, indice_utilizacion_pct}`.

Energía calculada por integración trapezoidal sobre la serie. Factor de potencia ponderado por potencia activa. Índice de utilización = demanda_pico / potencia_nominal × 100; None si no hay potencia nominal.

---

### `calcular_kpis_economicos(energia_kwh, precio_mxn_kwh, costo_cliente_factura_total, baseline_kwh) → dict`

```python
def calcular_kpis_economicos(
    energia_kwh: float,
    precio_mxn_kwh: float | None,
    costo_cliente_factura_total: float | None,
    baseline_kwh: float | None,
) -> dict:
```

Retorna `{costo_total_mxn, costo_unitario_mxn_kwh, pct_sobre_factura, ahorro_potencial_mxn}`.

Si `precio_mxn_kwh` es None, todos los campos retornan None. El ahorro potencial es `(baseline_kwh - energia_kwh) × precio`.

---

### `calcular_kpis_produccion(energia_kwh, costo_total_mxn, m2_producidos_atribuidos) → dict`

```python
def calcular_kpis_produccion(
    energia_kwh: float,
    costo_total_mxn: float | None,
    m2_producidos_atribuidos: float,
) -> dict:
```

Retorna `{consumo_especifico_kwh_m2, costo_especifico_mxn_m2, pct_costo_especifico, m2_producidos}`.

Si `m2_producidos_atribuidos <= 0`, todos los campos numéricos retornan None.

---

### `atribuir_produccion_a_nodo(m2_totales_planta, energia_nodo_kwh, energia_total_planta_kwh) → float`

```python
def atribuir_produccion_a_nodo(
    m2_totales_planta: float,
    energia_nodo_kwh: float,
    energia_total_planta_kwh: float,
) -> float:
```

Atribuye m² al nodo proporcionalmente a su fracción del consumo total de la planta. Retorna 0.0 si la energía total de planta es cero.

---

### `calcular_baseline_movil(mediciones_historicas) → float | None`

```python
def calcular_baseline_movil(
    mediciones_historicas: list[dict],   # [{"ts": str ISO, "kw": float}]
) -> float | None:
```

Integra la energía del periodo histórico como baseline provisional. Retorna kWh o None si no hay datos.

**Nota:** la fórmula exacta (promedio diario, percentil 90, etc.) está pendiente de definición por el usuario. Ver `docs/deuda-tecnica.md`.

---

### `generar_sparkline(mediciones, n_puntos, tipo) → list[float]`

```python
def generar_sparkline(
    mediciones: list[dict],    # [{"ts": str ISO, "kw": float, "fp": float (opcional)}]
    n_puntos: int,
    tipo: str = "energia",     # "energia" | "potencia" | "factor_potencia"
) -> list[float]:
```

Reduce las mediciones a `n_puntos` agrupando por bucket temporal de igual duración.

- `"energia"`: kWh acumulados por bucket (integral trapezoidal).
- `"potencia"`: promedio de kW por bucket.
- `"factor_potencia"`: promedio ponderado de fp por kW, por bucket.

---

### `determinar_periodo_anterior(rango, ahora) → tuple[datetime, datetime, str]`

```python
def determinar_periodo_anterior(
    rango: str,          # "24h" | "7d" | "30d"
    ahora: datetime,
) -> tuple[datetime, datetime, str]:
```

Calcula el periodo anterior equivalente desplazado 30 días hacia atrás. Retorna `(desde_ant, hasta_ant, etiqueta)`. Usado para la comparativa de periodo anterior en el dashboard.

---

## `calc/telemetria_costos.py`

### `obtener_precio_unitario_mxn_kwh(cliente_id, anio, mes) → dict`

```python
def obtener_precio_unitario_mxn_kwh(
    cliente_id: int,
    anio: int,
    mes: int,
) -> dict:
```

Retorna `{precio_mxn_kwh: float | None, fuente: str, mes_referencia: str | None}`.

Cascada de búsqueda: (1) factura CFE mes exacto → (2) factura CFE más reciente (≤12 meses) → (3) factura PPA mes exacto → (4) factura PPA más reciente → (5) `fuente="sin_datos"`.

Accede a Supabase internamente vía `storage.repository`. No es una función pura.

---

### `calcular_costo_periodo(cliente_id, energia_kwh, desde_utc, hasta_utc) → dict`

```python
def calcular_costo_periodo(
    cliente_id: int,
    energia_kwh: float,
    desde_utc: datetime,
    hasta_utc: datetime,
) -> dict:
```

Retorna `{costo_mxn: float | None, precio_mxn_kwh: float | None, fuente: str, mes_referencia: str | None}`.

Determina el mes principal del rango (el que abarca más horas) y delega en `obtener_precio_unitario_mxn_kwh`. Wrapper de conveniencia para el endpoint `/telemetria/data`.

---

### `obtener_precio_unitario(cliente_id, anio, mes, historico_completo) → dict`

```python
def obtener_precio_unitario(
    cliente_id: int,
    anio: int,
    mes: int,
    historico_completo: dict | None = None,
) -> dict:
```

Versión con caché opcional. Si `historico_completo` es un dict indexado por `(anio, mes)`, retorna desde el cache sin consultar BD. Útil para evitar N+1 al calcular costos sobre series de meses.

---

### Funciones internas (no llamar desde fuera del módulo)

`_precio_de_factura_cfe(fac) → tuple[float | None, str | None]`: extrae precio unitario de una fila de `cfe_facturas` con `cfe_periodos` embebidos (subtotal / kwh_total).

`_precio_de_factura_ppa(fac) → float | None`: extrae `precio_unitario_mxn_kwh` de una fila de `facturas_electricidad_calificado`.

`_mes_principal(desde, hasta) → tuple[int, int]`: itera hora a hora y retorna el mes con mayor presencia en el rango.

---

## Funciones de repositorio relevantes para telemetría (`storage/repository.py`)

| Función | Descripción |
|---|---|
| `obtener_arbol_activos_telemetria(cliente_id, planta_id)` | Lista plana de activos con `medidor_id` vigente y `punto_medicion`. |
| `obtener_mediciones_para_rango(medidor_id, desde, hasta, rango)` | Selecciona vista 5min u horaria según rango; retorna `[{ts, kw, fp}]`. |
| `obtener_agregados_5min(medidor_id, desde, hasta)` | Buckets 5 min de `mediciones_agregadas_5min`. |
| `obtener_agregados_horarios(medidor_id, desde, hasta)` | Buckets horarios de `mediciones_agregadas_horarias`. |
| `obtener_factura_cfe_cliente_mes(cliente_id, anio, mes)` | Fila de `cfe_facturas` con `cfe_periodos` embebidos. |
| `obtener_ultimas_facturas_cfe(cliente_id, n)` | Últimas n facturas CFE del cliente. |
| `obtener_factura_ppa_cliente_mes(cliente_id, anio, mes)` | Fila de `facturas_electricidad_calificado` para el mes exacto. |
| `obtener_ultimas_facturas_ppa(cliente_id, n)` | Últimas n facturas PPA del cliente. |
