-- storage/migrations/202609_mediciones_5min_horarias.sql
-- Vistas materializadas: agregación 5-min y horaria de mediciones en tiempo real
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

-- INSTRUCCIÓN: Ejecutar manualmente en Supabase → SQL Editor.
-- Después de crear las vistas, refrescar una vez:
--   REFRESH MATERIALIZED VIEW mediciones_agregadas_5min;
--   REFRESH MATERIALIZED VIEW mediciones_agregadas_horarias;
