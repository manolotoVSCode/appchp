-- Tabla append-only: contrato eléctrico vigente por acometida en cada intervalo.
-- Misma semántica que activo_alimentacion_vigencia.
-- FK activo_id sin CASCADE: no borrar registro si se elimina el activo.

CREATE TABLE IF NOT EXISTS acometida_contrato_vigencia (
    id            bigserial PRIMARY KEY,
    activo_id     bigint NOT NULL REFERENCES activos_electricos(id),
    contrato_id   bigint REFERENCES contratos(id) ON DELETE SET NULL,
    vigente_desde timestamptz NOT NULL,
    vigente_hasta timestamptz,
    motivo        text,
    created_at    timestamptz DEFAULT now()
);

-- Índice de consulta por activo y fecha
CREATE INDEX IF NOT EXISTS idx_acv_activo_desde
    ON acometida_contrato_vigencia (activo_id, vigente_desde);

-- Solo una fila abierta (vigente_hasta IS NULL) por acometida
CREATE UNIQUE INDEX IF NOT EXISTS idx_acv_activo_abierta
    ON acometida_contrato_vigencia (activo_id)
    WHERE vigente_hasta IS NULL;
