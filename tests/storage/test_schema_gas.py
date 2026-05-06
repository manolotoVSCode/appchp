from __future__ import annotations
import sqlite3
import pytest
from storage.schema import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


def test_gas_facturas_existe(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gas_facturas'")
    assert cur.fetchone() is not None


def test_gas_conceptos_existe(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gas_conceptos'")
    assert cur.fetchone() is not None


def test_gas_facturas_columnas(conn):
    cur = conn.execute("PRAGMA table_info(gas_facturas)")
    cols = {row[1] for row in cur.fetchall()}
    for expected in ("id", "cliente_id", "uuid_cfdi", "folio", "periodo_inicio",
                     "consumo_total_gj", "costo_unitario_total_gj", "subtotal_mxn",
                     "iva_mxn", "total_mxn", "advertencias"):
        assert expected in cols, f"Columna faltante: {expected}"


def test_gas_conceptos_fk_cascade(conn):
    """Borrar gas_factura elimina sus conceptos (ON DELETE CASCADE)."""
    conn.execute("INSERT INTO clientes (nombre, rfc) VALUES ('Test', 'TST010101AAA')")
    conn.execute(
        "INSERT INTO gas_facturas (cliente_id, uuid_cfdi, folio, fecha_emision, "
        "periodo_inicio, periodo_fin, fecha_limite_pago, nombre_proveedor, rfc_proveedor, "
        "numero_cliente, cuenta_contrato, punto_suministro, numero_caseta, tipo_lectura, "
        "consumo_m3_corregidos, consumo_sin_corregir_m3, poder_calorifico_gj_m3, "
        "consumo_total_gj, costo_unitario_total_gj, subtotal_mxn, iva_mxn, total_mxn, "
        "pdf_path, advertencias) "
        "VALUES (1,'uuid','F1','2023-01-01','2023-01-01','2023-01-31','2023-02-01',"
        "'PROV','TRA0002119W1','100','200','PUNTO','C1','REAL',"
        "'100','0','0.036','3.6','79.48','100','16','116','x.pdf','[]')"
    )
    conn.execute(
        "INSERT INTO gas_conceptos (factura_id, descripcion, clave_producto, "
        "cantidad_gj, precio_unitario_gj, importe_mxn) VALUES (1,'Compraventa','83101601','3.6','54.85','197.46')"
    )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM gas_facturas WHERE id = 1")
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) FROM gas_conceptos WHERE factura_id = 1")
    assert cur.fetchone()[0] == 0
