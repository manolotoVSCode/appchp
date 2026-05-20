-- Migración: sistema multi-usuario con Supabase Auth
-- Ejecutar manualmente en Supabase SQL Editor.
-- Fecha: 2026-06

-- 1. Tabla de perfiles de usuario vinculada a auth.users
CREATE TABLE IF NOT EXISTS user_profiles (
  id          UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email       TEXT        NOT NULL,
  rol         TEXT        NOT NULL CHECK (rol IN ('master_admin', 'admin', 'usuario_normal')),
  empresa_id  INTEGER     REFERENCES clientes(id) ON DELETE SET NULL,
  activo      BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para búsqueda por empresa
CREATE INDEX IF NOT EXISTS user_profiles_empresa_id_idx ON user_profiles(empresa_id);

-- 2. RLS: la tabla solo es accesible desde el backend con service_role
--    (No se habilita RLS; el backend usa service_role que bypasea RLS por diseño — deuda técnica fase 1)

-- Verificación sugerida tras ejecutar:
-- SELECT id, email, rol, empresa_id, activo FROM user_profiles ORDER BY email;
