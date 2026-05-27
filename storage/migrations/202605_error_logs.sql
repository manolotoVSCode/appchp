-- Tabla de registro de errores de aplicación
CREATE TABLE IF NOT EXISTS error_logs (
    id          BIGSERIAL PRIMARY KEY,
    nivel       TEXT        NOT NULL,   -- error_500 | error_403 | error_404 | validacion | negocio
    ruta        TEXT,
    metodo      TEXT,
    codigo_http INTEGER,
    usuario_id  UUID,
    usuario_email TEXT,
    usuario_rol TEXT,
    empresa_id  INTEGER,
    mensaje     TEXT,
    traceback   TEXT,
    user_agent  TEXT,
    ip          TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_error_logs_nivel      ON error_logs(nivel);
CREATE INDEX IF NOT EXISTS idx_error_logs_usuario_id ON error_logs(usuario_id) WHERE usuario_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON error_logs(created_at DESC);

ALTER TABLE error_logs ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON error_logs TO service_role;
GRANT USAGE, SELECT ON SEQUENCE error_logs_id_seq TO service_role;
