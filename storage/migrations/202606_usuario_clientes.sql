-- storage/migrations/202606_usuario_clientes.sql
-- Tabla de relación N:N usuario ↔ cliente
CREATE TABLE IF NOT EXISTS usuario_clientes (
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, cliente_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_clientes_user
    ON usuario_clientes (user_id);

CREATE INDEX IF NOT EXISTS idx_usuario_clientes_cliente
    ON usuario_clientes (cliente_id);

-- empresa_id en user_profiles pasa a ser legacy.
-- No se borra para mantener compatibilidad con usuarios existentes.
-- La nueva lógica lee de usuario_clientes primero; empresa_id es fallback.
