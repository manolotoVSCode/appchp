-- ─────────────────────────────────────────────────────────────────────────────
-- Migración: 202608_medidor_rol_vigencia.sql
-- Tabla de rol temporal de medidor (cabecera vs carga).
-- Ya aplicada en producción. Esta migración versiona el DDL en el repositorio.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS medidor_rol_vigencia (
    id            bigserial PRIMARY KEY,
    medidor_id    bigint NOT NULL REFERENCES medidores(id),  -- SIN CASCADE
    rol           text NOT NULL CHECK (rol IN ('carga', 'interconexion', 'generacion_neta', 'centro_carga')),
    vigente_desde timestamptz NOT NULL,
    vigente_hasta timestamptz,
    motivo        text,
    created_at    timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mrv_medidor_desde
    ON medidor_rol_vigencia (medidor_id, vigente_desde);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mrv_medidor_abierto
    ON medidor_rol_vigencia (medidor_id)
    WHERE vigente_hasta IS NULL;

-- ── Configuración: umbral de residuo de balance ─────────────────────────────
-- Ya insertada en producción. Versionada aquí.

INSERT INTO configuracion (clave, valor, descripcion)
VALUES ('umbral_resto_cargas_pct', '', 'Umbral de residuo de balance (%) para alerta. Vacío = sin alerta.')
ON CONFLICT (clave) DO NOTHING;
