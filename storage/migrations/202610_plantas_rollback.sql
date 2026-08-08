-- ─────────────────────────────────────────────────────────────────────────────
-- Rollback: 202610_plantas_rollback.sql
-- Revierte la migración 202610_plantas.sql.
-- PRECAUCIÓN: elimina la tabla plantas y todas las columnas planta_id.
-- Ejecutar SOLO si se decide abortar la migración a plantas.
-- ─────────────────────────────────────────────────────────────────────────────

-- Eliminar columnas planta_id (antes de DROP TABLE plantas por la FK)
ALTER TABLE produccion_diaria              DROP COLUMN IF EXISTS planta_id;
ALTER TABLE medidores                      DROP COLUMN IF EXISTS planta_id;
ALTER TABLE ppa_bloques_mensuales          DROP COLUMN IF EXISTS planta_id;
ALTER TABLE facturas_electricidad_calificado DROP COLUMN IF EXISTS planta_id;
ALTER TABLE gas_facturas                   DROP COLUMN IF EXISTS planta_id;
ALTER TABLE cfe_facturas                   DROP COLUMN IF EXISTS planta_id;
ALTER TABLE contratos                      DROP COLUMN IF EXISTS planta_id;

-- Eliminar tabla plantas (CASCADE elimina índices y constraints dependientes)
DROP TABLE IF EXISTS plantas CASCADE;

-- Eliminar columna activo de clientes
ALTER TABLE clientes DROP COLUMN IF EXISTS activo;
