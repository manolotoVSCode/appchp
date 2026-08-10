# Deuda técnica conocida

Inventario de decisiones intencionalmente diferidas con justificación y condición de cierre.

---

## 1. Ancla temporal del dashboard de telemetría

**Archivo:** `web/app.py`, función `cliente_dashboard_telemetria_data`.

**Estado:** activo.

El endpoint `/clientes/<id>/dashboard/telemetria/data` usa `max(timestamp)` de `mediciones_tiempo_real` como referencia de "ahora" en lugar de `datetime.now(timezone.utc)`. El campo `meta.modo_temporal` del JSON devuelve `"sintetico"` mientras aplique esta deuda.

**Por qué existe:** los datos de telemetría son sintéticos y estáticos. Usar `now()` haría que el dashboard mostrara siempre "sin datos en las últimas 24h" porque las mediciones llevan meses sin actualizarse. El ancla permite que la demo sea funcional sin re-seeds periódicos.

**Condición de cierre:** cuando entren medidores físicos con envío continuo vía MQTT (entrega D7-C / IoT). En ese punto la diferencia entre `max(timestamp)` y `now()` será de segundos, no de meses. Revertir la línea:

```python
ahora = _ts_max if _ts_max is not None else datetime.now(timezone.utc)
```

a:

```python
ahora = datetime.now(timezone.utc)
```

Y cambiar el valor de `meta.modo_temporal` a `"tiempo_real"`.

---

## 2. Clave service_role en lugar de anon + RLS

**Archivo:** `storage/repository.py` — inicialización del cliente Supabase.

**Estado:** activo.

La aplicación usa la clave `service_role` de Supabase, que bypasea Row Level Security. Toda la autorización de datos se hace en la capa de aplicación (Flask), no en la base de datos.

**Por qué existe:** en fase 1 la app es de uso interno con un único operador. Implementar RLS por tenant requiere rediseñar cómo fluye el JWT de Supabase Auth desde el frontend hasta las queries, lo que es trabajo de fase 3 (multi-tenant SaaS).

**Riesgos:** si la clave `SUPABASE_KEY` se filtra, un atacante tiene acceso completo a todas las tablas sin restricción. La clave debe vivir exclusivamente en variables de entorno del servidor backend y nunca exponerse al cliente.

**Condición de cierre:** migración a clave `anon` con políticas RLS por `empresa_id` / `cliente_id`, sincronizadas con el JWT del usuario autenticado. Trabajo planificado para fase 3.

---

## 3. Divergencia potencial entre `activo_padre_id` y `activo_alimentacion_vigencia`

**Archivos:** `storage/repository.py` — `activo_alimentacion_vigencia`, `activos_electricos`.

**Estado:** mitigado, no eliminado.

`activo_padre_id` en `activos_electricos` es el estado materializado de la alimentación vigente: se actualiza en cada llamada a `declarar_cambio_alimentacion` y se crea atómicamente junto con la fila de vigencia en `crear_activo_con_vigencia`. Los endpoints de edición excluyen `activo_padre_id` del payload.

Sin embargo, una modificación directa de `activo_padre_id` via SQL (Supabase Studio o scripts de migración) actualiza el estado materializado sin crear la fila correspondiente en `activo_alimentacion_vigencia`, generando divergencia entre la topología visible y la verdad temporal.

**Detección:** la función `verificar_consistencia_alimentacion(cliente_id)` en `storage/repository.py` compara ambas fuentes y retorna una lista de discrepancias. No está expuesta como ruta HTTP; se llama manualmente o desde scripts de mantenimiento.

**Condición de cierre:** implementar un trigger PostgreSQL en Supabase que sincronice `activo_alimentacion_vigencia` al detectar un UPDATE de `activo_padre_id` directo en BD. Hasta entonces, cualquier migración SQL que toque `activo_padre_id` debe también insertar la fila de vigencia correspondiente.

---

## 4. Baseline de producción no está definido formalmente

**Archivo:** `calc/telemetria_kpis.py`, función `calcular_baseline_movil`.

**Estado:** activo.

La función `calcular_baseline_movil(mediciones_historicas)` devuelve la energía integrada del periodo histórico completo como baseline provisional. El docstring de la función indica explícitamente "fórmula final (promedio diario, p90, etc.) por definir por el usuario".

**Por qué existe:** el KPI de ahorro potencial (`(baseline - energia_actual) × precio`) requiere una definición de qué es el consumo "normal" del activo. Opciones posibles: promedio de los últimos N días, percentil 90 de la distribución histórica, valor contractual, o promedio del mismo periodo en el año anterior. La elección tiene implicaciones metodológicas que dependen del caso de uso del cliente y no estaban especificadas al construir el módulo.

**Consecuencia actual:** `calcular_kpis_economicos` recibe `baseline_kwh` como parámetro; si el llamante pasa la energía histórica total (que es lo que hace `calcular_baseline_movil`), el resultado de `ahorro_potencial_mxn` puede no ser representativo del ahorro real.

**Condición de cierre:** el usuario define la metodología de baseline. Una vez definida, actualizar `calcular_baseline_movil` y documentarla aquí. Si la metodología requiere datos adicionales (p. ej., producción del año anterior), revisar también el contrato de datos del endpoint `/telemetria/data`.

---

## 5. Schema documentado en el repositorio no es fuente de verdad verificada

**Archivos:** `storage/schema.sql`, `CLAUDE.md`, `storage/migrations/`.

**Estado:** activo.

El repositorio tiene tres fuentes de verdad parciales para el schema de Supabase y ninguna de ellas es completa ni verificada contra producción. `storage/schema.sql` fue actualizado por última vez en v2.25.0 (2026-05-14) y no incluye ninguna tabla añadida desde entonces: `plantas`, `medidores`, `activos_electricos`, `medidor_activo_vigencia`, `activo_alimentacion_vigencia`, `acometida_contrato_vigencia`, `produccion_diaria`, `login_audit`, ni las columnas `planta_id` añadidas a tablas existentes. `CLAUDE.md` documenta el schema en prosa pero tampoco está verificado: el bug de `medidor_activo_vigencia.motivo` (columna ausente en producción que no estaba en ningún DDL del repositorio) se detectó en ejecución, no desde el repositorio. Las migraciones en `storage/migrations/` son la fuente más fiel pero solo cubren cambios incrementales; las tablas `activos_electricos`, `medidor_activo_vigencia` y `activo_alimentacion_vigencia` no tienen DDL de creación en ningún archivo del repositorio.

**Por qué existe:** las primeras tablas de telemetría y activos se crearon directamente en Supabase Studio sin generar una migración versionada.

**Consecuencia:** los tests que usan mocks de Supabase (`unittest.mock.patch`) no ejecutan queries reales y por tanto no detectan divergencias de columnas. Un SELECT de una columna inexistente solo falla en ejecución contra producción o una base de desarrollo real.

**Condición de cierre:** regenerar `storage/schema.sql` desde producción ejecutando `pg_dump --schema-only` (o la introspección equivalente desde Supabase), compararlo con el estado actual del repositorio, y saldar las diferencias. Toda nueva tabla o columna añadida directamente en Supabase debe acompañarse de un archivo de migración en `storage/migrations/` antes del siguiente commit.
