-- storage/migrations/202610_facturas_nxe.sql
-- Crea la tabla facturas_nxe para estados de cuenta de NX Energía S.A. de C.V.
-- No es un CFDI. Contiene parámetros contratados, 5 categorías de resumen y detalle diario JSONB.

SET search_path = public;

CREATE TABLE IF NOT EXISTS public.facturas_nxe (
    id                              SERIAL PRIMARY KEY,
    contrato_id                     INTEGER NOT NULL REFERENCES public.contratos(id) ON DELETE CASCADE,
    cliente_id                      INTEGER NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
    -- Identificación
    documento_ref                   TEXT,
    suministrador                   TEXT NOT NULL DEFAULT 'NX ENERGIA S.A. DE C.V.',
    rfc_suministrador               TEXT,
    -- Periodo
    periodo_inicio                  DATE NOT NULL,
    periodo_fin                     DATE NOT NULL,
    anio                            INTEGER,
    mes                             INTEGER,
    nombre_canonico                 TEXT,
    -- Parámetros contratados (TEXT para preservar exactitud del PDF)
    precio_energia_usd_mwh          TEXT,
    tipo_cambio_mxn_usd             TEXT,
    precio_cels_usd                 TEXT,
    precio_potencia_usd_kwmes       TEXT,
    factor_potencia_pct             TEXT,
    energia_contratada_kwh          TEXT,
    potencia_contratada_kwmes       TEXT,
    -- Consumo
    energia_consumida_kwh           TEXT NOT NULL,
    desviacion_pct                  TEXT,
    precio_monocomico_mxn_kwh       TEXT,
    -- 5 categorías del resumen (MXN)
    cargo_energia_mxn               TEXT,
    cargo_potencia_mxn              TEXT,
    cargo_cel_mxn                   TEXT,
    cargos_regulados_mxn            TEXT,
    ajustes_penalizaciones_mxn      TEXT,
    cobro_total_mxn                 TEXT NOT NULL,
    -- Detalle dentro de ajustes
    cobro_energia_no_consumida_usd  TEXT,
    cobro_exceso_consumo_usd        TEXT,
    costo_desvios_pdp_mxn           TEXT,
    costo_reliquidaciones_mxn       TEXT,
    -- Subtotales regulados
    tarifas_reguladas_mxn           TEXT,
    cargo_servicios_mem_mxn         TEXT,
    -- Detalle diario (Tablas 1.1 + 1.2 + 1.3 fusionadas, ≤31 días)
    detalle_diario                  JSONB DEFAULT '[]'::jsonb,
    -- Metadatos
    advertencias                    JSONB DEFAULT '[]'::jsonb,
    pdf_url                         TEXT,
    parser_version                  TEXT,
    created_at                      TIMESTAMP DEFAULT NOW(),
    UNIQUE(contrato_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS idx_facturas_nxe_cliente  ON public.facturas_nxe(cliente_id);
CREATE INDEX IF NOT EXISTS idx_facturas_nxe_contrato ON public.facturas_nxe(contrato_id);
CREATE INDEX IF NOT EXISTS idx_facturas_nxe_anio_mes ON public.facturas_nxe(anio, mes);
