-- storage/schema.sql
-- DDL de referencia. Las tablas existen en Supabase como infraestructura preestablecida.
-- Ejecutar manualmente en el SQL Editor de Supabase si se necesita recrear el schema.
-- Última actualización: 2026-05-11 (v2.21.0)

-- ── Clientes ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clientes (
    id                          SERIAL PRIMARY KEY,
    nombre                      TEXT    NOT NULL,
    rfc                         TEXT    NOT NULL UNIQUE,
    notas                       TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Campos extendidos (todos nullable)
    sector_industrial           TEXT,
    contacto_nombre             TEXT,
    contacto_cargo              TEXT,
    contacto_email              TEXT,
    contacto_telefono           TEXT,
    direccion                   TEXT,
    estado                      TEXT,
    codigo_postal               TEXT,
    tarifa_cfe                  TEXT,
    capacidad_instalada_kw      NUMERIC,
    demanda_contratada_kw       NUMERIC,
    anio_inicio_operacion       INTEGER,
    regimen_operacion           TEXT,
    consumo_anual_estimado_mwh  NUMERIC,
    logo_url                    TEXT,
    -- Campos regulatorios para cálculo CELs (CRE Caso I)
    medio_termico               TEXT,   -- 'vapor_agua' | 'gases_combustion'
    nivel_tension_kv            TEXT,   -- 'lt_1' | '1_34' | '69_85' | '115_230' | 'gt_400'
    altitud_msnm                NUMERIC,
    tipo_motor                  TEXT    -- 'combustion_interna' | 'turbina_gas' | otro
);

-- ── Contratos ─────────────────────────────────────────────────────────────────
-- Un cliente puede tener múltiples contratos eléctricos y/o de gas.

CREATE TABLE IF NOT EXISTS contratos (
    id                  SERIAL PRIMARY KEY,
    cliente_id          INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    nombre              TEXT    NOT NULL,
    tipo                TEXT    NOT NULL CHECK (tipo IN ('electrico', 'gas')),
    identificador_real  TEXT    NOT NULL,
    notas               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS contratos_cliente_id_idx ON contratos(cliente_id);

-- ── Facturas CFE ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cfe_facturas (
    id                            SERIAL PRIMARY KEY,
    cliente_id                    INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    contrato_id                   INTEGER REFERENCES contratos(id) ON DELETE SET NULL,
    uuid_cfdi                     TEXT,
    folio                         TEXT    NOT NULL,
    serie                         TEXT,
    fecha_emision                 TEXT    NOT NULL,
    periodo_inicio                TEXT    NOT NULL,
    periodo_fin                   TEXT    NOT NULL,
    fecha_limite_pago             TEXT    NOT NULL,
    numero_servicio               TEXT    NOT NULL,
    rmu                           TEXT,
    tarifa                        TEXT    NOT NULL,
    numero_medidor                TEXT    NOT NULL,
    multiplicador                 INTEGER NOT NULL,
    carga_conectada_kw            TEXT    NOT NULL,
    demanda_contratada_kw         TEXT    NOT NULL,
    kw_max                        TEXT    NOT NULL,
    kvarh                         TEXT    NOT NULL,
    factor_potencia_pct           TEXT    NOT NULL,
    cargo_fijo_mxn                TEXT    NOT NULL,
    energia_total_mxn             TEXT    NOT NULL,
    cargo_factor_potencia_mxn     TEXT    NOT NULL,
    subtotal_mxn                  TEXT    NOT NULL,
    iva_mxn                       TEXT    NOT NULL,
    facturacion_periodo_mxn       TEXT    NOT NULL,
    derecho_alumbrado_publico_mxn TEXT    NOT NULL,
    credito_aplicado_mxn          TEXT    NOT NULL,
    total_mxn                     TEXT    NOT NULL,
    pdf_path                      TEXT    NOT NULL,
    advertencias                  TEXT    NOT NULL DEFAULT '[]',
    nombre_canonico               TEXT,
    anio                          INTEGER,
    mes                           INTEGER,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS cfe_facturas_cliente_id_idx   ON cfe_facturas(cliente_id);
CREATE INDEX IF NOT EXISTS cfe_facturas_contrato_id_idx  ON cfe_facturas(contrato_id);
CREATE INDEX IF NOT EXISTS cfe_facturas_anio_mes_idx     ON cfe_facturas(contrato_id, anio, mes);

-- ── Periodos y componentes MEM de factura CFE ─────────────────────────────────

CREATE TABLE IF NOT EXISTS cfe_periodos (
    id                  SERIAL PRIMARY KEY,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    periodo             TEXT    NOT NULL,
    consumo_kwh         TEXT    NOT NULL,
    demanda_kw          TEXT    NOT NULL,
    costo_unitario_kwh  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cfe_mem_componentes (
    id                  SERIAL PRIMARY KEY,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    nombre              TEXT    NOT NULL,
    cargo_fijo_mxn      TEXT    NOT NULL,
    cargo_demanda_mxn   TEXT    NOT NULL,
    cargo_energia_mxn   TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);

-- ── Facturas de gas ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gas_facturas (
    id                       SERIAL PRIMARY KEY,
    cliente_id               INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    contrato_id              INTEGER REFERENCES contratos(id) ON DELETE SET NULL,
    uuid_cfdi                TEXT,
    folio                    TEXT    NOT NULL,
    fecha_emision            TEXT    NOT NULL,
    periodo_inicio           TEXT    NOT NULL,
    periodo_fin              TEXT    NOT NULL,
    fecha_limite_pago        TEXT    NOT NULL,
    nombre_proveedor         TEXT    NOT NULL,
    rfc_proveedor            TEXT    NOT NULL,
    numero_cliente           TEXT    NOT NULL,
    cuenta_contrato          TEXT    NOT NULL,
    punto_suministro         TEXT    NOT NULL,
    numero_caseta            TEXT    NOT NULL,
    tipo_lectura             TEXT    NOT NULL,
    consumo_m3_corregidos    TEXT    NOT NULL,
    consumo_sin_corregir_m3  TEXT    NOT NULL,
    poder_calorifico_gj_m3   TEXT    NOT NULL,
    consumo_total_gj         TEXT    NOT NULL,
    costo_unitario_total_gj  TEXT    NOT NULL,
    subtotal_mxn             TEXT    NOT NULL,
    iva_mxn                  TEXT    NOT NULL,
    total_mxn                TEXT    NOT NULL,
    pdf_path                 TEXT    NOT NULL,
    advertencias             TEXT    NOT NULL DEFAULT '[]',
    nombre_canonico          TEXT,
    anio                     INTEGER,
    mes                      INTEGER,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS gas_facturas_cliente_id_idx   ON gas_facturas(cliente_id);
CREATE INDEX IF NOT EXISTS gas_facturas_contrato_id_idx  ON gas_facturas(contrato_id);
CREATE INDEX IF NOT EXISTS gas_facturas_anio_mes_idx     ON gas_facturas(contrato_id, anio, mes);

-- ── Conceptos de factura de gas ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gas_conceptos (
    id                  SERIAL PRIMARY KEY,
    factura_id          INTEGER NOT NULL REFERENCES gas_facturas(id) ON DELETE CASCADE,
    descripcion         TEXT    NOT NULL,
    clave_producto      TEXT    NOT NULL,
    cantidad_gj         TEXT    NOT NULL,
    precio_unitario_gj  TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);

-- ── Selección de meses por contrato ───────────────────────────────────────────
-- Tabla de cruce que registra qué meses están seleccionados para análisis.

CREATE TABLE IF NOT EXISTS contrato_meses_seleccionados (
    contrato_id  INTEGER NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    anio         INTEGER NOT NULL,
    mes          INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    PRIMARY KEY (contrato_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS cms_contrato_id_idx ON contrato_meses_seleccionados(contrato_id);

-- ── Configuración del sistema ─────────────────────────────────────────────────
-- Tabla clave-valor para parámetros globales editables desde /admin/configuracion.

CREATE TABLE IF NOT EXISTS configuracion (
    clave        TEXT PRIMARY KEY,
    valor        TEXT NOT NULL,
    descripcion  TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Valores por defecto (insertar solo si la clave no existe):
INSERT INTO configuracion (clave, valor, descripcion) VALUES
    ('tipo_cambio_mxn_usd',                 '17.50', 'Tipo de cambio MXN/USD para conversión de inversión estimada')
ON CONFLICT (clave) DO NOTHING;

INSERT INTO configuracion (clave, valor, descripcion) VALUES
    ('factor_emision_electricidad_kg_co2_kwh', '0.435', 'Factor de emisión de electricidad de la red (kg CO₂/kWh)')
ON CONFLICT (clave) DO NOTHING;

INSERT INTO configuracion (clave, valor, descripcion) VALUES
    ('factor_emision_gas_kg_co2_gj', '56.1', 'Factor de emisión de gas natural (kg CO₂/GJ)')
ON CONFLICT (clave) DO NOTHING;
