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
