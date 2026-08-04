-- Ampliación de medidores para jerarquía Acometida → Transformador → Carga
-- Ejecutar en Supabase SQL editor.

ALTER TABLE medidores
  ADD COLUMN IF NOT EXISTS medidor_padre_id BIGINT NULL
    REFERENCES medidores(id) ON DELETE SET NULL;

ALTER TABLE medidores
  ADD COLUMN IF NOT EXISTS tipo_carga TEXT NULL;

ALTER TABLE medidores
  ADD COLUMN IF NOT EXISTS potencia_nominal_kw NUMERIC(10,2) NULL;

CREATE INDEX IF NOT EXISTS idx_medidores_padre
  ON medidores (medidor_padre_id);
