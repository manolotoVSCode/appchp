-- ─────────────────────────────────────────────────────────────────────────────
-- Migración: 202606_telemetria_fase2.sql
-- Capa de datos de telemetría — Fase 2
-- Medidores Accuenergy Acuvim II, set completo de variables.
-- PostgreSQL nativo (sin TimescaleDB).
-- Diseño migrable a hypertable: PK de mediciones_tiempo_real incluye timestamp.
-- REFERENCES usa tabla "clientes" (PK: id INTEGER) que es la tabla de empresas.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Tabla de medidores ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medidores (
    id              BIGSERIAL   PRIMARY KEY,
    empresa_id      INTEGER     NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    nombre          TEXT        NOT NULL,
    punto_medicion  TEXT,
    ubicacion       TEXT,
    numero_serie    TEXT,
    relacion_tc     NUMERIC(10,4),  -- relación de transformadores de corriente (ej. 200:5 → 40)
    marca           TEXT        NOT NULL DEFAULT 'Accuenergy',
    modelo          TEXT        NOT NULL DEFAULT 'Acuvim II',
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_medidores_empresa ON medidores(empresa_id);

-- ── Tabla de mediciones en tiempo real ───────────────────────────────────────
-- Una fila por lectura del medidor (intervalo configurable, típico 1-5 min).
-- PK compuesta (id, timestamp) permite conversión futura a hypertable TimescaleDB
-- con: SELECT create_hypertable('mediciones_tiempo_real', 'timestamp');
CREATE TABLE IF NOT EXISTS mediciones_tiempo_real (
    id                  BIGSERIAL,
    medidor_id          BIGINT      NOT NULL REFERENCES medidores(id) ON DELETE CASCADE,
    timestamp           TIMESTAMPTZ NOT NULL,

    -- ── Voltajes fase-neutro (V) ─────────────────────────────────────────────
    v_an                NUMERIC(10,3),   -- Fase A – neutro
    v_bn                NUMERIC(10,3),   -- Fase B – neutro
    v_cn                NUMERIC(10,3),   -- Fase C – neutro
    v_avg_ln            NUMERIC(10,3),   -- Promedio LN

    -- ── Voltajes fase-fase (V) ───────────────────────────────────────────────
    v_ab                NUMERIC(10,3),
    v_bc                NUMERIC(10,3),
    v_ca                NUMERIC(10,3),
    v_avg_ll            NUMERIC(10,3),   -- Promedio LL

    -- ── Corrientes (A) ───────────────────────────────────────────────────────
    i_a                 NUMERIC(10,3),
    i_b                 NUMERIC(10,3),
    i_c                 NUMERIC(10,3),
    i_n                 NUMERIC(10,3),   -- Corriente de neutro
    i_avg               NUMERIC(10,3),

    -- ── Potencia activa (kW) ─────────────────────────────────────────────────
    kw_a                NUMERIC(12,4),
    kw_b                NUMERIC(12,4),
    kw_c                NUMERIC(12,4),
    kw_total            NUMERIC(12,4),

    -- ── Potencia reactiva (kVAR) ─────────────────────────────────────────────
    kvar_a              NUMERIC(12,4),
    kvar_b              NUMERIC(12,4),
    kvar_c              NUMERIC(12,4),
    kvar_total          NUMERIC(12,4),

    -- ── Potencia aparente (kVA) ──────────────────────────────────────────────
    kva_a               NUMERIC(12,4),
    kva_b               NUMERIC(12,4),
    kva_c               NUMERIC(12,4),
    kva_total           NUMERIC(12,4),

    -- ── Factor de potencia ───────────────────────────────────────────────────
    pf_a                NUMERIC(6,4),
    pf_b                NUMERIC(6,4),
    pf_c                NUMERIC(6,4),
    pf_total            NUMERIC(6,4),

    -- ── Frecuencia (Hz) ──────────────────────────────────────────────────────
    frecuencia_hz       NUMERIC(7,3),

    -- ── Energía activa (kWh) — contadores acumulados del medidor ─────────────
    kwh_importado       NUMERIC(14,3),
    kwh_exportado       NUMERIC(14,3),

    -- ── Energía reactiva (kVARh) — contadores acumulados ─────────────────────
    kvarh_importado     NUMERIC(14,3),
    kvarh_exportado     NUMERIC(14,3),

    -- ── THD voltaje (%) ──────────────────────────────────────────────────────
    thd_v_a             NUMERIC(7,3),
    thd_v_b             NUMERIC(7,3),
    thd_v_c             NUMERIC(7,3),

    -- ── THD corriente (%) ────────────────────────────────────────────────────
    thd_i_a             NUMERIC(7,3),
    thd_i_b             NUMERIC(7,3),
    thd_i_c             NUMERIC(7,3),

    -- ── Demanda (kW, kVA) ────────────────────────────────────────────────────
    demanda_kw          NUMERIC(12,4),
    demanda_kva         NUMERIC(12,4),
    demanda_max_kw      NUMERIC(12,4),   -- máxima registrada en el medidor
    demanda_max_kva     NUMERIC(12,4),

    PRIMARY KEY (id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_mtr_medidor_ts
    ON mediciones_tiempo_real(medidor_id, timestamp DESC);

-- ── Tabla de agregados de 15 minutos ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mediciones_agregadas_15min (
    medidor_id          BIGINT      NOT NULL REFERENCES medidores(id) ON DELETE CASCADE,
    bucket_15min        TIMESTAMPTZ NOT NULL,

    -- Potencia activa (kW)
    kw_total_avg        NUMERIC(12,4),
    kw_total_max        NUMERIC(12,4),
    kw_total_min        NUMERIC(12,4),

    -- Potencia reactiva (kVAR)
    kvar_total_avg      NUMERIC(12,4),

    -- Potencia aparente (kVA)
    kva_total_avg       NUMERIC(12,4),

    -- Factor de potencia
    pf_total_avg        NUMERIC(6,4),

    -- Voltaje promedio LN
    v_avg_ln_avg        NUMERIC(10,3),

    -- Corriente media
    i_avg_avg           NUMERIC(10,3),

    -- Frecuencia media
    frecuencia_hz_avg   NUMERIC(7,3),

    -- Número de lecturas en el bucket
    n_lecturas          INTEGER,

    -- Energía en el período (diferencia de contadores acumulados)
    kwh_periodo         NUMERIC(14,3),
    kvarh_periodo       NUMERIC(14,3),

    PRIMARY KEY (medidor_id, bucket_15min)
);

CREATE INDEX IF NOT EXISTS idx_mag_medidor_bucket
    ON mediciones_agregadas_15min(medidor_id, bucket_15min DESC);

-- ── Función de agregación a 15 minutos ───────────────────────────────────────
-- Calcula buckets del rango [p_desde, p_hasta) para un medidor dado.
-- Se invoca manualmente o desde el job de pg_cron.
CREATE OR REPLACE FUNCTION agregar_mediciones_15min(
    p_medidor_id BIGINT,
    p_desde      TIMESTAMPTZ,
    p_hasta      TIMESTAMPTZ
) RETURNS void LANGUAGE plpgsql AS $func$
BEGIN
    INSERT INTO mediciones_agregadas_15min (
        medidor_id,   bucket_15min,
        kw_total_avg, kw_total_max, kw_total_min,
        kvar_total_avg, kva_total_avg, pf_total_avg,
        v_avg_ln_avg, i_avg_avg, frecuencia_hz_avg,
        n_lecturas, kwh_periodo, kvarh_periodo
    )
    SELECT
        medidor_id,
        date_trunc('hour', timestamp)
            + INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 15),
        AVG(kw_total),
        MAX(kw_total),
        MIN(kw_total),
        AVG(kvar_total),
        AVG(kva_total),
        AVG(pf_total),
        AVG(v_avg_ln),
        AVG(i_avg),
        AVG(frecuencia_hz),
        COUNT(*),
        MAX(kwh_importado)  - MIN(kwh_importado),
        MAX(kvarh_importado) - MIN(kvarh_importado)
    FROM  mediciones_tiempo_real
    WHERE medidor_id = p_medidor_id
      AND timestamp >= p_desde
      AND timestamp <  p_hasta
    GROUP BY
        medidor_id,
        date_trunc('hour', timestamp)
            + INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 15)
    ON CONFLICT (medidor_id, bucket_15min) DO UPDATE SET
        kw_total_avg      = EXCLUDED.kw_total_avg,
        kw_total_max      = EXCLUDED.kw_total_max,
        kw_total_min      = EXCLUDED.kw_total_min,
        kvar_total_avg    = EXCLUDED.kvar_total_avg,
        kva_total_avg     = EXCLUDED.kva_total_avg,
        pf_total_avg      = EXCLUDED.pf_total_avg,
        v_avg_ln_avg      = EXCLUDED.v_avg_ln_avg,
        i_avg_avg         = EXCLUDED.i_avg_avg,
        frecuencia_hz_avg = EXCLUDED.frecuencia_hz_avg,
        n_lecturas        = EXCLUDED.n_lecturas,
        kwh_periodo       = EXCLUDED.kwh_periodo,
        kvarh_periodo     = EXCLUDED.kvarh_periodo;
END;
$func$;

-- ── Job pg_cron: agrega el período de 15 min anterior, cada 15 min ───────────
-- Requiere extensión pg_cron (disponible en Supabase Pro/Enterprise).
-- El DO $$ guarda con IF EXISTS para no fallar si pg_cron no está habilitado.
DO $cron_setup$
DECLARE
    v_job_name TEXT := 'agregar_mediciones_15min_job';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        RAISE NOTICE 'pg_cron no está disponible; job no registrado.';
        RETURN;
    END IF;

    -- Desregistrar si ya existía (idempotente)
    BEGIN
        PERFORM cron.unschedule(v_job_name);
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    -- Registrar el job: cada 15 min, agrega el período anterior para todos los medidores activos
    PERFORM cron.schedule(
        v_job_name,
        '*/15 * * * *',
        $job$
        DO $inner$
        DECLARE
            r       RECORD;
            v_hasta TIMESTAMPTZ;
            v_desde TIMESTAMPTZ;
        BEGIN
            v_hasta := date_trunc('hour', NOW())
                       + INTERVAL '15 min'
                         * FLOOR(EXTRACT(MINUTE FROM NOW()) / 15);
            v_desde := v_hasta - INTERVAL '15 minutes';
            FOR r IN SELECT id FROM medidores WHERE activo = TRUE LOOP
                PERFORM agregar_mediciones_15min(r.id, v_desde, v_hasta);
            END LOOP;
        END;
        $inner$
        $job$
    );

    RAISE NOTICE 'Job % registrado correctamente.', v_job_name;
END;
$cron_setup$;
