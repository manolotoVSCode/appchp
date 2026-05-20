-- Migración: medio térmico con mezcla configurable
-- Ejecutar manualmente en Supabase SQL Editor.
-- Fecha: 2026-05

-- 1. Agregar columna de porcentaje de vapor (0-100).
ALTER TABLE clientes
  ADD COLUMN IF NOT EXISTS medio_termico_vapor_pct INTEGER
  CHECK (medio_termico_vapor_pct BETWEEN 0 AND 100);

-- 2. Poblar el campo para clientes existentes.
UPDATE clientes SET medio_termico_vapor_pct = 100 WHERE medio_termico = 'vapor_agua';
UPDATE clientes SET medio_termico_vapor_pct = 0   WHERE medio_termico = 'gases_combustion';

-- 3. Normalizar el valor del campo medio_termico al nuevo valor del dropdown
--    (vapor_agua → vapor_o_agua). Sin este paso, el dropdown no pre-selecciona
--    la opción correcta en el formulario de edición.
UPDATE clientes SET medio_termico = 'vapor_o_agua' WHERE medio_termico = 'vapor_agua';

-- Verificación sugerida tras ejecutar:
-- SELECT id, nombre, medio_termico, medio_termico_vapor_pct FROM clientes ORDER BY nombre;
