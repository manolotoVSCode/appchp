-- v2.33.4 — Precio de gas manual para proyección de cogeneración sin facturas de gas
-- Permite calcular el dashboard de cogeneración cuando hay 12+ facturas CFE pero
-- menos de 12 facturas de gas, usando un precio de referencia configurado manualmente.

ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS precio_gas_manual_mxn_gj_pcs NUMERIC(10,4);

COMMENT ON COLUMN clientes.precio_gas_manual_mxn_gj_pcs
    IS 'Precio de gas manual en MXN/GJ PCS (equivalente a costo_unitario_total_gj de facturas reales). '
       'Usado como fallback en proyección de cogeneración cuando hay < 12 facturas de gas seleccionadas.';
