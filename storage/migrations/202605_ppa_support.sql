-- storage/migrations/202605_ppa_support.sql
-- Ejecutar manualmente en Supabase SQL Editor. Creado: 2026-05-14 (v2.25.0)
-- Propósito: añadir soporte para clientes con suministro eléctrico calificado (PPA).

-- ── Paso 1: Migrar contratos existentes 'electrico' → 'electrico_basico' ─────
-- Hacer ANTES de alterar el constraint para no violar el nuevo CHECK.
ALTER TABLE contratos DROP CONSTRAINT IF EXISTS contratos_tipo_check;
UPDATE contratos SET tipo = 'electrico_basico' WHERE tipo = 'electrico';
ALTER TABLE contratos ADD CONSTRAINT contratos_tipo_check
  CHECK (tipo IN ('electrico_basico', 'electrico_calificado', 'gas'));

-- ── Paso 2: Campos PPA en tabla clientes ──────────────────────────────────────
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_suministrador TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_rfc_suministrador TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_precio_fijo_usd_mwh DECIMAL(10,4);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_fecha_inicio_suministro DATE;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_energia_contratada_mwh_anual DECIMAL(15,4);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_capacidad_maxima_kw DECIMAL(12,2);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_margen_reserva_cenace_pct DECIMAL(6,4);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_zona_carga TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_rpu TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_division TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_pdf_contrato_url TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS ppa_notas TEXT;

-- ── Paso 3: Tabla ppa_bloques_mensuales ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS ppa_bloques_mensuales (
  id SERIAL PRIMARY KEY,
  cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
  anio INTEGER NOT NULL,
  mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
  bloque_contratado_mwh DECIMAL(12,3) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(cliente_id, anio, mes)
);
CREATE INDEX IF NOT EXISTS idx_ppa_bloques_cliente ON ppa_bloques_mensuales(cliente_id);

-- ── Paso 4: Tabla facturas_electricidad_calificado ────────────────────────────
CREATE TABLE IF NOT EXISTS facturas_electricidad_calificado (
  id SERIAL PRIMARY KEY,
  contrato_id INTEGER NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
  cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
  suministrador TEXT,
  rpu TEXT,
  serie_folio TEXT,
  periodo_inicio DATE NOT NULL,
  periodo_fin DATE NOT NULL,
  dias_facturados INTEGER,
  anio INTEGER,
  mes INTEGER,
  nombre_canonico TEXT,
  consumo_kwh DECIMAL(15,3) NOT NULL,
  precio_unitario_mxn_kwh DECIMAL(10,6) NOT NULL,
  subtotal_mxn DECIMAL(15,2) NOT NULL,
  iva_mxn DECIMAL(15,2),
  total_mxn DECIMAL(15,2),
  excedente_detectado BOOLEAN DEFAULT FALSE,
  advertencias JSONB DEFAULT '[]'::jsonb,
  pdf_url TEXT,
  parser_version TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(contrato_id, anio, mes)
);
CREATE INDEX IF NOT EXISTS idx_fac_calif_cliente ON facturas_electricidad_calificado(cliente_id);
CREATE INDEX IF NOT EXISTS idx_fac_calif_contrato ON facturas_electricidad_calificado(contrato_id);
CREATE INDEX IF NOT EXISTS idx_fac_calif_anio_mes ON facturas_electricidad_calificado(anio, mes);
