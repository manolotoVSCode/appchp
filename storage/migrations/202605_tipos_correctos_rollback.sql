-- ROLLBACK: revierte tipos nativos → TEXT en todas las tablas
-- Ejecutar ANTES de aplicar la migración 202605_tipos_correctos.sql si necesita revertir.
-- Versión: v2.39.0 / 2026-05-21

ALTER TABLE cfe_facturas
  ALTER COLUMN cargo_fijo_mxn             TYPE TEXT USING cargo_fijo_mxn::TEXT,
  ALTER COLUMN energia_total_mxn          TYPE TEXT USING energia_total_mxn::TEXT,
  ALTER COLUMN cargo_factor_potencia_mxn  TYPE TEXT USING cargo_factor_potencia_mxn::TEXT,
  ALTER COLUMN subtotal_mxn               TYPE TEXT USING subtotal_mxn::TEXT,
  ALTER COLUMN iva_mxn                    TYPE TEXT USING iva_mxn::TEXT,
  ALTER COLUMN facturacion_periodo_mxn    TYPE TEXT USING facturacion_periodo_mxn::TEXT,
  ALTER COLUMN derecho_alumbrado_publico_mxn TYPE TEXT USING derecho_alumbrado_publico_mxn::TEXT,
  ALTER COLUMN credito_aplicado_mxn       TYPE TEXT USING credito_aplicado_mxn::TEXT,
  ALTER COLUMN total_mxn                  TYPE TEXT USING total_mxn::TEXT,
  ALTER COLUMN kw_max                     TYPE TEXT USING kw_max::TEXT,
  ALTER COLUMN kvarh                      TYPE TEXT USING kvarh::TEXT,
  ALTER COLUMN factor_potencia_pct        TYPE TEXT USING factor_potencia_pct::TEXT,
  ALTER COLUMN multiplicador              TYPE TEXT USING multiplicador::TEXT,
  ALTER COLUMN carga_conectada_kw         TYPE TEXT USING carga_conectada_kw::TEXT,
  ALTER COLUMN demanda_contratada_kw      TYPE TEXT USING demanda_contratada_kw::TEXT,
  ALTER COLUMN fecha_emision              TYPE TEXT USING fecha_emision::TEXT,
  ALTER COLUMN periodo_inicio             TYPE TEXT USING periodo_inicio::TEXT,
  ALTER COLUMN periodo_fin                TYPE TEXT USING periodo_fin::TEXT,
  ALTER COLUMN fecha_limite_pago          TYPE TEXT USING fecha_limite_pago::TEXT;

ALTER TABLE cfe_periodos
  ALTER COLUMN consumo_kwh        TYPE TEXT USING consumo_kwh::TEXT,
  ALTER COLUMN demanda_kw         TYPE TEXT USING demanda_kw::TEXT,
  ALTER COLUMN costo_unitario_kwh TYPE TEXT USING costo_unitario_kwh::TEXT;

ALTER TABLE cfe_mem_componentes
  ALTER COLUMN cargo_fijo_mxn    TYPE TEXT USING cargo_fijo_mxn::TEXT,
  ALTER COLUMN cargo_demanda_mxn TYPE TEXT USING cargo_demanda_mxn::TEXT,
  ALTER COLUMN cargo_energia_mxn TYPE TEXT USING cargo_energia_mxn::TEXT,
  ALTER COLUMN importe_mxn       TYPE TEXT USING importe_mxn::TEXT;

ALTER TABLE gas_facturas
  ALTER COLUMN consumo_m3_corregidos     TYPE TEXT USING consumo_m3_corregidos::TEXT,
  ALTER COLUMN consumo_sin_corregir_m3   TYPE TEXT USING consumo_sin_corregir_m3::TEXT,
  ALTER COLUMN poder_calorifico_gj_m3    TYPE TEXT USING poder_calorifico_gj_m3::TEXT,
  ALTER COLUMN consumo_total_gj          TYPE TEXT USING consumo_total_gj::TEXT,
  ALTER COLUMN costo_unitario_total_gj   TYPE TEXT USING costo_unitario_total_gj::TEXT,
  ALTER COLUMN subtotal_mxn              TYPE TEXT USING subtotal_mxn::TEXT,
  ALTER COLUMN iva_mxn                   TYPE TEXT USING iva_mxn::TEXT,
  ALTER COLUMN total_mxn                 TYPE TEXT USING total_mxn::TEXT,
  ALTER COLUMN fecha_emision             TYPE TEXT USING fecha_emision::TEXT,
  ALTER COLUMN periodo_inicio            TYPE TEXT USING periodo_inicio::TEXT,
  ALTER COLUMN periodo_fin               TYPE TEXT USING periodo_fin::TEXT,
  ALTER COLUMN fecha_limite_pago         TYPE TEXT USING fecha_limite_pago::TEXT;

ALTER TABLE gas_conceptos
  ALTER COLUMN cantidad_gj        TYPE TEXT USING cantidad_gj::TEXT,
  ALTER COLUMN precio_unitario_gj TYPE TEXT USING precio_unitario_gj::TEXT,
  ALTER COLUMN importe_mxn        TYPE TEXT USING importe_mxn::TEXT;

ALTER TABLE facturas_electricidad_calificado
  ALTER COLUMN consumo_kwh             TYPE TEXT USING consumo_kwh::TEXT,
  ALTER COLUMN precio_unitario_mxn_kwh TYPE TEXT USING precio_unitario_mxn_kwh::TEXT,
  ALTER COLUMN subtotal_mxn            TYPE TEXT USING subtotal_mxn::TEXT,
  ALTER COLUMN iva_mxn                 TYPE TEXT USING iva_mxn::TEXT,
  ALTER COLUMN total_mxn               TYPE TEXT USING total_mxn::TEXT,
  ALTER COLUMN periodo_inicio          TYPE TEXT USING periodo_inicio::TEXT,
  ALTER COLUMN periodo_fin             TYPE TEXT USING periodo_fin::TEXT;
