-- Añade columna calc_version a modelado_chp para invalidar cache
-- cuando cambia el algoritmo de cálculo.
-- Los registros sin versión reciben '1' (algoritmo greedy original).
ALTER TABLE modelado_chp
  ADD COLUMN IF NOT EXISTS calc_version TEXT DEFAULT '1';
