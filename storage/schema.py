from __future__ import annotations

import sqlite3
from typing import Any


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clientes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT    NOT NULL,
    rfc        TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cfe_facturas (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id                    INTEGER NOT NULL REFERENCES clientes(id),
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
    kvArh                         TEXT    NOT NULL,
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
    created_at                    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cfe_periodos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    periodo             TEXT    NOT NULL,
    consumo_kwh         TEXT    NOT NULL,
    demanda_kw          TEXT    NOT NULL,
    costo_unitario_kwh  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cfe_mem_componentes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    nombre              TEXT    NOT NULL,
    cargo_fijo_mxn      TEXT    NOT NULL,
    cargo_demanda_mxn   TEXT    NOT NULL,
    cargo_energia_mxn   TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gas_facturas (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id               INTEGER NOT NULL REFERENCES clientes(id),
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
    created_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gas_conceptos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES gas_facturas(id) ON DELETE CASCADE,
    descripcion         TEXT    NOT NULL,
    clave_producto      TEXT    NOT NULL,
    cantidad_gj         TEXT    NOT NULL,
    precio_unitario_gj  TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);
"""

_DDL_SQLITE = DDL

_DDL_PG = """
CREATE TABLE IF NOT EXISTS clientes (
    id         SERIAL PRIMARY KEY,
    nombre     TEXT    NOT NULL,
    rfc        TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS cfe_facturas (
    id                            SERIAL PRIMARY KEY,
    cliente_id                    INTEGER NOT NULL REFERENCES clientes(id),
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
    kvArh                         TEXT    NOT NULL,
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
    created_at                    TEXT    NOT NULL DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

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

CREATE TABLE IF NOT EXISTS gas_facturas (
    id                       SERIAL PRIMARY KEY,
    cliente_id               INTEGER NOT NULL REFERENCES clientes(id),
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
    created_at               TEXT    NOT NULL DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS gas_conceptos (
    id                  SERIAL PRIMARY KEY,
    factura_id          INTEGER NOT NULL REFERENCES gas_facturas(id) ON DELETE CASCADE,
    descripcion         TEXT    NOT NULL,
    clave_producto      TEXT    NOT NULL,
    cantidad_gj         TEXT    NOT NULL,
    precio_unitario_gj  TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);
"""


def init_db(conn: Any) -> None:
    """Crea las tablas si no existen. Seguro de llamar múltiples veces."""
    if isinstance(conn, sqlite3.Connection):
        # Legacy path: raw sqlite3 connection (old tests)
        conn.executescript(DDL)
        conn.commit()
    else:
        # Conn adapter path: detect dialect and use appropriate DDL
        dialect = getattr(conn, "dialect", "sqlite")
        ddl = _DDL_PG if dialect == "postgres" else _DDL_SQLITE
        conn.executescript(ddl)
        conn.commit()
