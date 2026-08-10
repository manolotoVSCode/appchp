-- Corrección: columna motivo ausente en medidor_activo_vigencia
--
-- La tabla medidor_activo_vigencia fue creada sin la columna motivo.
-- Su ausencia provocaba APIError 42703 (columna inexistente) en
-- resolver_intervalos_medidor al intentar SELECT motivo.
--
-- La corrección se aplicó directamente en producción (Supabase Studio).
-- Esta migración versiona el cambio en el repositorio.
-- No es necesario volver a ejecutarla si la columna ya fue añadida.

ALTER TABLE medidor_activo_vigencia
    ADD COLUMN IF NOT EXISTS motivo TEXT;
