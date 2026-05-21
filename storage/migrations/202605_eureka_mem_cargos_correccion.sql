-- Corrección: asignación incorrecta de tipo de cargo en componentes MEM
-- Contexto: el parser asigna cargo_fijo/demanda/energía por posición de columna en el PDF.
-- En facturas 2019-era de INDUSTRIAS EUREKA (cliente_id=39), la tabla MEM podía tener
-- un layout distinto que resulta en valores asignados a la columna equivocada.
-- Regla: cada componente tiene exactamente un cargo activo; importe_mxn es siempre correcto.
-- Corrección: rederiva cargo_fijo/demanda/energía desde importe_mxn según el tipo de componente.
-- Ejecutar manualmente en Supabase SQL Editor.
-- Idempotente: usa CASE para que aplicar dos veces no cambie el resultado.
-- Versión: v2.39.0 / 2026-05-21

DO $$
DECLARE
  v_cliente_id  INT := 39;
  v_fixed       INT := 0;
  v_nombre      TEXT;
  v_factura_id  INT;
  rec           RECORD;
BEGIN
  -- Diagnóstico previo: mostrar componentes con asignación aparentemente incorrecta
  RAISE NOTICE '=== Diagnóstico: componentes MEM con asignación inconsistente ===';
  FOR rec IN
    SELECT
      m.id,
      m.factura_id,
      m.nombre,
      m.cargo_fijo_mxn,
      m.cargo_demanda_mxn,
      m.cargo_energia_mxn,
      m.importe_mxn,
      f.anio,
      f.mes
    FROM cfe_mem_componentes m
    JOIN cfe_facturas f ON f.id = m.factura_id
    WHERE f.cliente_id = v_cliente_id
      AND (
        -- Suministro debe tener cargo_fijo > 0
        (m.nombre = 'Suministro'   AND m.importe_mxn::NUMERIC > 0 AND m.cargo_fijo_mxn::NUMERIC = 0)
        -- Distribución y Capacidad deben tener cargo_demanda > 0
     OR (m.nombre IN ('Distribución','Capacidad') AND m.importe_mxn::NUMERIC > 0 AND m.cargo_demanda_mxn::NUMERIC = 0)
        -- Los demás deben tener cargo_energia > 0
     OR (m.nombre IN ('Transmisión','CENACE','Generación B','Generación I','Generación P','SCnMEM')
           AND m.importe_mxn::NUMERIC > 0 AND m.cargo_energia_mxn::NUMERIC = 0)
      )
    ORDER BY f.anio, f.mes, m.nombre
  LOOP
    RAISE NOTICE 'Inconsistente: factura_id=%, anio=%, mes=%, componente=%, fijo=%, demanda=%, energia=%, importe=%',
      rec.factura_id, rec.anio, rec.mes, rec.nombre,
      rec.cargo_fijo_mxn, rec.cargo_demanda_mxn, rec.cargo_energia_mxn, rec.importe_mxn;
  END LOOP;

  -- Corrección: rederivación por tipo de componente en todas las facturas del cliente
  UPDATE cfe_mem_componentes m
  SET
    cargo_fijo_mxn = CASE
      WHEN m.nombre = 'Suministro'   THEN m.importe_mxn
      ELSE '0'
    END,
    cargo_demanda_mxn = CASE
      WHEN m.nombre IN ('Distribución', 'Capacidad') THEN m.importe_mxn
      ELSE '0'
    END,
    cargo_energia_mxn = CASE
      WHEN m.nombre IN ('Transmisión', 'CENACE', 'Generación B', 'Generación I', 'Generación P', 'SCnMEM') THEN m.importe_mxn
      ELSE '0'
    END
  FROM cfe_facturas f
  WHERE m.factura_id = f.id
    AND f.cliente_id = v_cliente_id
    AND m.nombre IN (
      'Suministro', 'Distribución', 'Transmisión', 'CENACE',
      'Generación B', 'Generación I', 'Generación P', 'Capacidad', 'SCnMEM'
    );

  GET DIAGNOSTICS v_fixed = ROW_COUNT;
  RAISE NOTICE 'Componentes MEM corregidos para cliente_id=%: %', v_cliente_id, v_fixed;
END;
$$;

-- Verificación post-ejecución para factura 25 (ajustar id si difiere):
-- SELECT nombre, cargo_fijo_mxn, cargo_demanda_mxn, cargo_energia_mxn, importe_mxn
-- FROM cfe_mem_componentes WHERE factura_id = 25 ORDER BY nombre;
