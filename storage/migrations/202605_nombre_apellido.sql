-- Migración: agregar nombre y apellido a user_profiles
-- Ejecutar manualmente en el SQL Editor de Supabase.

ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS nombre TEXT,
    ADD COLUMN IF NOT EXISTS apellido TEXT;
