-- Auditoría de intentos de login (exitosos y fallidos)
-- Ejecutar en: Supabase SQL Editor

CREATE TABLE IF NOT EXISTS login_audit (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID,
    email       TEXT,
    success     BOOLEAN NOT NULL,
    ip_address  TEXT,
    user_agent  TEXT,
    failure_reason TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_audit_user_id    ON login_audit(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_login_audit_email      ON login_audit(email);
CREATE INDEX IF NOT EXISTS idx_login_audit_created_at ON login_audit(created_at DESC);

-- Verificar:
-- SELECT * FROM login_audit LIMIT 1;
