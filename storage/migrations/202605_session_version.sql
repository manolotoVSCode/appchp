-- Mecanismo session_version para invalidación de sesiones al cambiar contraseña
-- Ejecutar en: Supabase SQL Editor

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1;

-- Verificar:
-- SELECT id, email, session_version FROM user_profiles LIMIT 5;
