-- Fix: constraint UNIQUE necesario para upsert en save_modelado_chp.
-- repository.py usa on_conflict="medicion_id,margen_kw,rendimiento_electrico,costo_om_kwh,autoconsumo_pct"
-- y PostgREST requiere un UNIQUE constraint (no solo un índice) sobre esas columnas exactas.
--
-- Ejecutar en orden en el SQL Editor de Supabase:

-- Paso 1: verificar duplicados (debe devolver 0 filas; si hay, ejecutar paso 2 antes)
SELECT medicion_id, margen_kw, rendimiento_electrico, costo_om_kwh, autoconsumo_pct,
       COUNT(*) AS n
FROM modelado_chp
GROUP BY medicion_id, margen_kw, rendimiento_electrico, costo_om_kwh, autoconsumo_pct
HAVING COUNT(*) > 1
ORDER BY n DESC;

-- Paso 2 (solo si hay duplicados): conservar el registro más reciente por grupo
DELETE FROM modelado_chp
WHERE id NOT IN (
    SELECT MAX(id)
    FROM modelado_chp
    GROUP BY medicion_id, margen_kw, rendimiento_electrico, costo_om_kwh, autoconsumo_pct
);

-- Paso 3: crear el constraint
ALTER TABLE modelado_chp
  ADD CONSTRAINT modelado_chp_upsert_key
  UNIQUE (medicion_id, margen_kw, rendimiento_electrico, costo_om_kwh, autoconsumo_pct);
