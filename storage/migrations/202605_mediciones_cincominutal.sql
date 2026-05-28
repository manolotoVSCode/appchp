-- storage/migrations/202605_mediciones_cincominutal.sql
-- Ejecutar manualmente en Supabase (Dashboard > SQL Editor).

CREATE TABLE IF NOT EXISTS mediciones_cincominutal (
    id          BIGSERIAL PRIMARY KEY,
    cliente_id  INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    anio        SMALLINT NOT NULL,
    mes         SMALLINT NOT NULL,
    nombre      TEXT,           -- nombre libre del archivo subido
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    uploaded_by TEXT,           -- email del usuario que subió
    UNIQUE(cliente_id, anio, mes)
);

CREATE TABLE IF NOT EXISTS mediciones_cincominutal_datos (
    id              BIGSERIAL PRIMARY KEY,
    medicion_id     BIGINT NOT NULL REFERENCES mediciones_cincominutal(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL,   -- timestamp UTC del intervalo
    potencia_kw     NUMERIC(10,3) NOT NULL  -- kWh_E × 12
);

CREATE INDEX IF NOT EXISTS idx_mediciones_datos_medicion ON mediciones_cincominutal_datos(medicion_id);
CREATE INDEX IF NOT EXISTS idx_mediciones_datos_ts       ON mediciones_cincominutal_datos(ts);
