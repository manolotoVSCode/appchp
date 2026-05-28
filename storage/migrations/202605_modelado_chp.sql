-- storage/migrations/202605_modelado_chp.sql
-- Modelado CHP: campos en clientes + tablas de cache de resultados.
-- Ejecutar manualmente desde el panel SQL de Supabase.

-- Campos nuevos en tabla clientes
ALTER TABLE clientes
  ADD COLUMN IF NOT EXISTS chp_num_motores     SMALLINT DEFAULT 1,
  ADD COLUMN IF NOT EXISTS chp_margen_kw       NUMERIC(10,2) DEFAULT 0;

-- Tabla de resultados del modelado (cache por medicion + parámetros)
CREATE TABLE IF NOT EXISTS modelado_chp (
    id                      BIGSERIAL PRIMARY KEY,
    medicion_id             BIGINT NOT NULL REFERENCES mediciones_cincominutal(id) ON DELETE CASCADE,
    cliente_id              INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    num_motores             SMALLINT NOT NULL,
    margen_kw               NUMERIC(10,2) NOT NULL,
    rendimiento_electrico   NUMERIC(5,4) NOT NULL,
    costo_om_kwh            NUMERIC(10,6) NOT NULL,
    autoconsumo_pct         NUMERIC(5,4) NOT NULL DEFAULT 0.03,
    -- Resultados anualizados
    gen_neta_anual_kwh      NUMERIC(16,2),
    gen_bruta_anual_kwh     NUMERIC(16,2),
    cobertura_pct           NUMERIC(7,4),
    consumo_gas_anual_gj    NUMERIC(16,4),
    costo_om_anual_mxn      NUMERIC(16,2),
    horas_anuales_motor     NUMERIC(10,2),
    capacidad_promedio_kw   NUMERIC(10,2),
    -- Metadata
    calculado_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    capacidad_nominal_kw    NUMERIC(10,2),
    UNIQUE(medicion_id, num_motores, margen_kw, rendimiento_electrico, costo_om_kwh, autoconsumo_pct, capacidad_nominal_kw)
);

-- Tabla de curva modelada (generación neta por intervalo de 5 min)
CREATE TABLE IF NOT EXISTS modelado_chp_curva (
    id              BIGSERIAL PRIMARY KEY,
    modelado_id     BIGINT NOT NULL REFERENCES modelado_chp(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL,
    demanda_kw      NUMERIC(10,3) NOT NULL,
    gen_neta_kw     NUMERIC(10,3) NOT NULL,
    motores_activos SMALLINT NOT NULL
);

-- Añadir columna capacidad_nominal_kw si la tabla ya existe
ALTER TABLE modelado_chp ADD COLUMN IF NOT EXISTS capacidad_nominal_kw NUMERIC(10,2);

CREATE INDEX IF NOT EXISTS idx_modelado_chp_medicion  ON modelado_chp(medicion_id);
CREATE INDEX IF NOT EXISTS idx_modelado_chp_cliente   ON modelado_chp(cliente_id);
CREATE INDEX IF NOT EXISTS idx_modelado_chp_curva     ON modelado_chp_curva(modelado_id);
CREATE INDEX IF NOT EXISTS idx_modelado_chp_curva_ts  ON modelado_chp_curva(ts);
