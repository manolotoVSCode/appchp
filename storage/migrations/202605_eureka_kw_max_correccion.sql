-- Corrección: kw_max = 0 en facturas de INDUSTRIAS EUREKA (cliente_id=39)
-- Causa: PDF layout antiguo usaba "kW Max" (con espacio) en lugar de "kWMax".
-- Parser v2.39.0 corrige el regex. Este script aplica el valor derivado a facturas históricas.
-- Fórmula: kw_max = MAX(kw_base, kw_intermedio, kw_punta) de cfe_periodos.
-- Ejecutar manualmente en la consola de Supabase SQL Editor.
-- Idempotente: solo actualiza filas donde kw_max IS NULL o kw_max = '0'.
-- Versión: v2.39.0 / 2026-05-21

DO $$
DECLARE
  v_cliente_id  INT := 39;
  v_updated     INT := 0;
  rec           RECORD;
  v_kw_max      NUMERIC;
BEGIN
  -- Iterar sobre facturas del cliente con kw_max nulo o cero
  FOR rec IN
    SELECT f.id, f.anio, f.mes
    FROM cfe_facturas f
    WHERE f.cliente_id = v_cliente_id
      AND (f.kw_max IS NULL OR f.kw_max = '0' OR f.kw_max = '')
    ORDER BY f.periodo_inicio
  LOOP
    -- Derivar kw_max como máximo de las demandas horarias registradas
    SELECT GREATEST(
             MAX(CASE WHEN p.periodo = 'base'       THEN p.demanda_kw::NUMERIC ELSE 0 END),
             MAX(CASE WHEN p.periodo = 'intermedio' THEN p.demanda_kw::NUMERIC ELSE 0 END),
             MAX(CASE WHEN p.periodo = 'punta'      THEN p.demanda_kw::NUMERIC ELSE 0 END)
           )
    INTO v_kw_max
    FROM cfe_periodos p
    WHERE p.factura_id = rec.id
      AND p.demanda_kw IS NOT NULL
      AND p.demanda_kw != ''
      AND p.demanda_kw != '0';

    IF v_kw_max IS NOT NULL AND v_kw_max > 0 THEN
      UPDATE cfe_facturas
      SET kw_max = v_kw_max::TEXT
      WHERE id = rec.id;
      v_updated := v_updated + 1;
      RAISE NOTICE 'Factura id=% (anio=%, mes=%) → kw_max corregido a %',
        rec.id, rec.anio, rec.mes, v_kw_max;
    ELSE
      RAISE NOTICE 'Factura id=% (anio=%, mes=%) → sin demandas horarias disponibles, omitida',
        rec.id, rec.anio, rec.mes;
    END IF;
  END LOOP;

  RAISE NOTICE 'Total facturas corregidas para cliente_id=%: %', v_cliente_id, v_updated;
END;
$$;

-- Verificación post-ejecución:
-- SELECT id, anio, mes, kw_max FROM cfe_facturas WHERE cliente_id = 39 ORDER BY periodo_inicio;

-- Diagnóstico: otros clientes con kw_max = '0' o nulo (posible mismo defecto de layout)
-- SELECT f.cliente_id, c.nombre, COUNT(*) AS n_facturas
-- FROM cfe_facturas f
-- JOIN clientes c ON c.id = f.cliente_id
-- WHERE f.kw_max IS NULL OR f.kw_max = '0' OR f.kw_max = ''
-- GROUP BY f.cliente_id, c.nombre
-- ORDER BY n_facturas DESC;
