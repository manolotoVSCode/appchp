-- ─────────────────────────────────────────────────────────────────────────────
-- Migración: 202610_plantas.sql
-- Introduce la entidad PLANTA como nivel intermedio: cliente → planta → recursos.
-- Esta migración es SOLO infraestructura (DDL).  Los datos se migran con
-- scripts/migrar_a_plantas.py.  El backend sigue operando por cliente_id.
-- Ejecutar en Supabase SQL Editor antes de correr el script Python.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── 1. Tabla plantas ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS plantas (
    id               BIGSERIAL    PRIMARY KEY,
    cliente_id       INTEGER      NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    nombre           TEXT         NOT NULL,
    activo           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    direccion_planta TEXT,
    notas            TEXT,
    UNIQUE (cliente_id, nombre)
);

CREATE INDEX IF NOT EXISTS idx_plantas_cliente_id ON plantas(cliente_id);

-- ── 2. Campo activo en clientes ───────────────────────────────────────────────

ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE;

-- ── 3. planta_id en tablas operativas (nullable, sin FK rota si planta se elimina) ──

ALTER TABLE contratos
    ADD COLUMN IF NOT EXISTS planta_id BIGINT REFERENCES plantas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_contratos_planta_id ON contratos(planta_id);

ALTER TABLE cfe_facturas
    ADD COLUMN IF NOT EXISTS planta_id BIGINT REFERENCES plantas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_cfe_facturas_planta_id ON cfe_facturas(planta_id);

ALTER TABLE gas_facturas
    ADD COLUMN IF NOT EXISTS planta_id BIGINT REFERENCES plantas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_gas_facturas_planta_id ON gas_facturas(planta_id);

ALTER TABLE facturas_electricidad_calificado
    ADD COLUMN IF NOT EXISTS planta_id BIGINT REFERENCES plantas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_fac_calif_planta_id ON facturas_electricidad_calificado(planta_id);

ALTER TABLE ppa_bloques_mensuales
    ADD COLUMN IF NOT EXISTS planta_id BIGINT REFERENCES plantas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_ppa_bloques_planta_id ON ppa_bloques_mensuales(planta_id);

ALTER TABLE medidores
    ADD COLUMN IF NOT EXISTS planta_id BIGINT REFERENCES plantas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_medidores_planta_id ON medidores(planta_id);

ALTER TABLE produccion_diaria
    ADD COLUMN IF NOT EXISTS planta_id BIGINT REFERENCES plantas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_produccion_diaria_planta_id ON produccion_diaria(planta_id);

-- ── Nota sobre tablas NO modificadas ──────────────────────────────────────────
-- Las siguientes tablas NO reciben planta_id porque su relación con la planta
-- es transitiva (via FK):
--   cfe_periodos          → via factura_id  → cfe_facturas.planta_id
--   cfe_mem_componentes   → via factura_id  → cfe_facturas.planta_id
--   gas_conceptos         → via factura_id  → gas_facturas.planta_id
--   contrato_meses_seleccionados → via contrato_id → contratos.planta_id
--   mediciones_tiempo_real / agregadas → via medidor_id → medidores.planta_id
