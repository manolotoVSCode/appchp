-- Migración: columnas de trazabilidad para captura manual de facturas CFE
-- Ejecutar en Supabase SQL Editor (una sola vez)

ALTER TABLE cfe_facturas
  ADD COLUMN IF NOT EXISTS validacion_manual     BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS validado_por          UUID    NULL     REFERENCES auth.users(id),
  ADD COLUMN IF NOT EXISTS motivo_captura_manual TEXT    NULL;

COMMENT ON COLUMN cfe_facturas.validacion_manual     IS 'True si los datos de la factura fueron capturados manualmente por el operador.';
COMMENT ON COLUMN cfe_facturas.validado_por          IS 'UUID del usuario que realizó la captura manual.';
COMMENT ON COLUMN cfe_facturas.motivo_captura_manual IS 'Razón por la que se requirió captura manual (texto_cifrado, campos_ilegibles, pdf_escaneado, otro).';
