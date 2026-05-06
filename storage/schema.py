from __future__ import annotations

import sqlite3


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
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Crea las tablas si no existen. Seguro de llamar múltiples veces."""
    conn.executescript(DDL)
    conn.commit()
