-- Diagnóstico: facturas con validacion_manual = TRUE y campos críticos vacíos
-- Ejecutar en Supabase SQL Editor para identificar facturas que requieren recaptura.

SELECT
  f.id,
  c.nombre                AS cliente,
  ct.nombre               AS contrato,
  f.nombre_canonico,
  f.anio,
  f.mes,
  f.folio,
  -- Periodos: contar cuántos tienen consumo real
  (SELECT COUNT(*) FROM cfe_periodos p
   WHERE p.factura_id = f.id AND p.consumo_kwh IS NOT NULL AND p.consumo_kwh != '0')
                          AS periodos_con_consumo,
  -- Componentes MEM: contar cuántos existen
  (SELECT COUNT(*) FROM cfe_mem_componentes m WHERE m.factura_id = f.id)
                          AS num_componentes_mem,
  COALESCE(f.kw_max, '0') AS kw_max,
  COALESCE(f.factor_potencia_pct, '0') AS factor_potencia_pct,
  CASE
    WHEN (
      (SELECT COUNT(*) FROM cfe_periodos p
       WHERE p.factura_id = f.id AND p.consumo_kwh IS NOT NULL AND p.consumo_kwh != '0') < 3
      OR (SELECT COUNT(*) FROM cfe_mem_componentes m WHERE m.factura_id = f.id) < 9
      OR COALESCE(f.kw_max, '0') = '0'
      OR COALESCE(f.factor_potencia_pct, '0') = '0'
    )
    THEN 'REQUIERE RECAPTURA'
    ELSE 'OK'
  END                     AS estado
FROM cfe_facturas f
LEFT JOIN clientes c  ON c.id  = f.cliente_id
LEFT JOIN contratos ct ON ct.id = f.contrato_id
WHERE f.validacion_manual = TRUE
ORDER BY f.cliente_id, f.anio, f.mes;
