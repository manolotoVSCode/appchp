-- Soporte para configuración de motores heterogéneos en Modelado CHP.
-- Sustituye num_motores + capacidad_nominal_kw por motores_config JSONB,
-- permitiendo mezcla de motores con distinta potencia nominal.

ALTER TABLE modelado_chp
  ADD COLUMN IF NOT EXISTS motores_config JSONB;

ALTER TABLE modelado_chp_curva
  ADD COLUMN IF NOT EXISTS gen_por_motor JSONB;

ALTER TABLE clientes
  ADD COLUMN IF NOT EXISTS chp_motores_config JSONB;

ALTER TABLE modelado_chp
  DROP CONSTRAINT IF EXISTS modelado_chp_unique_params;

CREATE UNIQUE INDEX IF NOT EXISTS idx_modelado_chp_unique
  ON modelado_chp (
    medicion_id, margen_kw, rendimiento_electrico,
    costo_om_kwh, autoconsumo_pct,
    (motores_config::text)
  );
