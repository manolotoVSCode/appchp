-- Ampliar m2_producidos de NUMERIC(10,2) a NUMERIC(12,2)
-- Nuevo máximo: 9,999,999,999.99 m² por día (defensa en profundidad).
-- Ejecutar en Supabase SQL editor.

ALTER TABLE produccion_diaria
    ALTER COLUMN m2_producidos TYPE NUMERIC(12, 2);
