-- Migración: eliminar constraint UNIQUE de RFC en tabla clientes
-- Ejecutar manualmente en Supabase SQL Editor.
--
-- Verificar nombre exacto del constraint antes de ejecutar:
--   SELECT conname, contype
--   FROM pg_constraint
--   WHERE conrelid = 'clientes'::regclass AND contype = 'u';

ALTER TABLE clientes DROP CONSTRAINT IF EXISTS clientes_rfc_key;
ALTER TABLE clientes DROP CONSTRAINT IF EXISTS clientes_rfc_unique;

DROP INDEX IF EXISTS idx_clientes_rfc_unique;
DROP INDEX IF EXISTS clientes_rfc_unique;

-- Permitir NULL en RFC (campo ya era TEXT; solo se elimina NOT NULL si existe)
ALTER TABLE clientes ALTER COLUMN rfc DROP NOT NULL;
