-- Migración: cambio de tipo TEXT → tipos nativos en tablas CFE y Gas
-- Objetivo: mejorar integridad de datos y habilitar ordenamiento/filtrado numérico en Supabase.
-- IMPORTANTE: la app usa supabase-py que convierte automáticamente; el cambio es transparente
--             para el código Python siempre que los valores almacenados sean válidos.
-- Ejecutar manualmente en la consola de Supabase SQL Editor.
-- Ejecutar el rollback ANTES de aplicar si desea poder revertir.
-- Versión: v2.39.0 / 2026-05-21

-- ===========================================================================
-- PRE-VALIDACIÓN: verificar que no haya valores no convertibles
-- Ejecutar y revisar antes de aplicar ALTER TABLE.
-- ===========================================================================
/*
SELECT id, kw_max FROM cfe_facturas
WHERE kw_max IS NOT NULL AND kw_max !~ '^\d+(\.\d+)?$';

SELECT id, kvarh FROM cfe_facturas
WHERE kvarh IS NOT NULL AND kvarh !~ '^\d+(\.\d+)?$';

SELECT id, factor_potencia_pct FROM cfe_facturas
WHERE factor_potencia_pct IS NOT NULL AND factor_potencia_pct !~ '^\d+(\.\d+)?$';

SELECT id, consumo_kwh FROM cfe_periodos
WHERE consumo_kwh IS NOT NULL AND consumo_kwh !~ '^\d+(\.\d+)?$';

SELECT id, costo_unitario_kwh FROM cfe_periodos
WHERE costo_unitario_kwh IS NOT NULL AND costo_unitario_kwh !~ '^\d+(\.\d+)?$';
*/

-- ===========================================================================
-- cfe_facturas — campos numéricos y de fecha
-- ===========================================================================

-- Campos NUMERIC (montos MXN — preservan exactitud decimal)
ALTER TABLE cfe_facturas
  ALTER COLUMN cargo_fijo_mxn             TYPE NUMERIC USING cargo_fijo_mxn::NUMERIC,
  ALTER COLUMN energia_total_mxn          TYPE NUMERIC USING energia_total_mxn::NUMERIC,
  ALTER COLUMN cargo_factor_potencia_mxn  TYPE NUMERIC USING cargo_factor_potencia_mxn::NUMERIC,
  ALTER COLUMN subtotal_mxn               TYPE NUMERIC USING subtotal_mxn::NUMERIC,
  ALTER COLUMN iva_mxn                    TYPE NUMERIC USING iva_mxn::NUMERIC,
  ALTER COLUMN facturacion_periodo_mxn    TYPE NUMERIC USING facturacion_periodo_mxn::NUMERIC,
  ALTER COLUMN derecho_alumbrado_publico_mxn TYPE NUMERIC USING derecho_alumbrado_publico_mxn::NUMERIC,
  ALTER COLUMN credito_aplicado_mxn       TYPE NUMERIC USING credito_aplicado_mxn::NUMERIC,
  ALTER COLUMN total_mxn                  TYPE NUMERIC USING total_mxn::NUMERIC;

-- Campos INTEGER/NUMERIC para mediciones
ALTER TABLE cfe_facturas
  ALTER COLUMN kw_max                TYPE NUMERIC USING NULLIF(kw_max, '')::NUMERIC,
  ALTER COLUMN kvarh                 TYPE NUMERIC USING NULLIF(kvarh, '')::NUMERIC,
  ALTER COLUMN factor_potencia_pct   TYPE NUMERIC USING NULLIF(factor_potencia_pct, '')::NUMERIC,
  ALTER COLUMN multiplicador         TYPE INTEGER  USING NULLIF(multiplicador, '')::INTEGER,
  ALTER COLUMN carga_conectada_kw    TYPE NUMERIC USING NULLIF(carga_conectada_kw, '')::NUMERIC,
  ALTER COLUMN demanda_contratada_kw TYPE NUMERIC USING NULLIF(demanda_contratada_kw, '')::NUMERIC;

-- Campos DATE
ALTER TABLE cfe_facturas
  ALTER COLUMN fecha_emision       TYPE DATE USING NULLIF(fecha_emision, '')::DATE,
  ALTER COLUMN periodo_inicio      TYPE DATE USING NULLIF(periodo_inicio, '')::DATE,
  ALTER COLUMN periodo_fin         TYPE DATE USING NULLIF(periodo_fin, '')::DATE,
  ALTER COLUMN fecha_limite_pago   TYPE DATE USING NULLIF(fecha_limite_pago, '')::DATE;

-- ===========================================================================
-- cfe_periodos — consumos y costos
-- ===========================================================================

ALTER TABLE cfe_periodos
  ALTER COLUMN consumo_kwh        TYPE NUMERIC USING NULLIF(consumo_kwh, '')::NUMERIC,
  ALTER COLUMN demanda_kw         TYPE NUMERIC USING NULLIF(demanda_kw, '')::NUMERIC,
  ALTER COLUMN costo_unitario_kwh TYPE NUMERIC USING NULLIF(costo_unitario_kwh, '')::NUMERIC;

-- ===========================================================================
-- cfe_mem_componentes — importes MXN
-- ===========================================================================

ALTER TABLE cfe_mem_componentes
  ALTER COLUMN cargo_fijo_mxn    TYPE NUMERIC USING NULLIF(cargo_fijo_mxn, '')::NUMERIC,
  ALTER COLUMN cargo_demanda_mxn TYPE NUMERIC USING NULLIF(cargo_demanda_mxn, '')::NUMERIC,
  ALTER COLUMN cargo_energia_mxn TYPE NUMERIC USING NULLIF(cargo_energia_mxn, '')::NUMERIC,
  ALTER COLUMN importe_mxn       TYPE NUMERIC USING NULLIF(importe_mxn, '')::NUMERIC;

-- ===========================================================================
-- gas_facturas — campos numéricos y de fecha
-- ===========================================================================

ALTER TABLE gas_facturas
  ALTER COLUMN consumo_m3_corregidos     TYPE NUMERIC USING NULLIF(consumo_m3_corregidos, '')::NUMERIC,
  ALTER COLUMN consumo_sin_corregir_m3   TYPE NUMERIC USING NULLIF(consumo_sin_corregir_m3, '')::NUMERIC,
  ALTER COLUMN poder_calorifico_gj_m3    TYPE NUMERIC USING NULLIF(poder_calorifico_gj_m3, '')::NUMERIC,
  ALTER COLUMN consumo_total_gj          TYPE NUMERIC USING NULLIF(consumo_total_gj, '')::NUMERIC,
  ALTER COLUMN costo_unitario_total_gj   TYPE NUMERIC USING NULLIF(costo_unitario_total_gj, '')::NUMERIC,
  ALTER COLUMN subtotal_mxn              TYPE NUMERIC USING NULLIF(subtotal_mxn, '')::NUMERIC,
  ALTER COLUMN iva_mxn                   TYPE NUMERIC USING NULLIF(iva_mxn, '')::NUMERIC,
  ALTER COLUMN total_mxn                 TYPE NUMERIC USING NULLIF(total_mxn, '')::NUMERIC;

ALTER TABLE gas_facturas
  ALTER COLUMN fecha_emision     TYPE DATE USING NULLIF(fecha_emision, '')::DATE,
  ALTER COLUMN periodo_inicio    TYPE DATE USING NULLIF(periodo_inicio, '')::DATE,
  ALTER COLUMN periodo_fin       TYPE DATE USING NULLIF(periodo_fin, '')::DATE,
  ALTER COLUMN fecha_limite_pago TYPE DATE USING NULLIF(fecha_limite_pago, '')::DATE;

-- ===========================================================================
-- gas_conceptos — campos numéricos
-- ===========================================================================

ALTER TABLE gas_conceptos
  ALTER COLUMN cantidad_gj       TYPE NUMERIC USING NULLIF(cantidad_gj, '')::NUMERIC,
  ALTER COLUMN precio_unitario_gj TYPE NUMERIC USING NULLIF(precio_unitario_gj, '')::NUMERIC,
  ALTER COLUMN importe_mxn       TYPE NUMERIC USING NULLIF(importe_mxn, '')::NUMERIC;

-- ===========================================================================
-- facturas_electricidad_calificado — campos numéricos y de fecha
-- ===========================================================================

ALTER TABLE facturas_electricidad_calificado
  ALTER COLUMN consumo_kwh             TYPE NUMERIC USING NULLIF(consumo_kwh, '')::NUMERIC,
  ALTER COLUMN precio_unitario_mxn_kwh TYPE NUMERIC USING NULLIF(precio_unitario_mxn_kwh, '')::NUMERIC,
  ALTER COLUMN subtotal_mxn            TYPE NUMERIC USING NULLIF(subtotal_mxn, '')::NUMERIC,
  ALTER COLUMN iva_mxn                 TYPE NUMERIC USING NULLIF(iva_mxn, '')::NUMERIC,
  ALTER COLUMN total_mxn               TYPE NUMERIC USING NULLIF(total_mxn, '')::NUMERIC;

ALTER TABLE facturas_electricidad_calificado
  ALTER COLUMN periodo_inicio TYPE DATE USING NULLIF(periodo_inicio, '')::DATE,
  ALTER COLUMN periodo_fin    TYPE DATE USING NULLIF(periodo_fin, '')::DATE;
