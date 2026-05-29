-- Eliminar constraint UNIQUE existente y recrear incluyendo
-- capacidad_nominal_kw para que el upsert funcione correctamente

ALTER TABLE modelado_chp
  DROP CONSTRAINT IF EXISTS
    modelado_chp_medicion_id_num_motores_margen_kw_rendimiento__key;

ALTER TABLE modelado_chp
  ADD CONSTRAINT modelado_chp_unique_params
  UNIQUE (medicion_id, num_motores, margen_kw, rendimiento_electrico,
          costo_om_kwh, autoconsumo_pct, capacidad_nominal_kw);
