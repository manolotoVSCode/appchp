from __future__ import annotations

import sqlite3
import pytest
from storage.schema import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


def test_init_db_crea_tablas(conn):
    init_db(conn)
    tablas = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "clientes" in tablas
    assert "cfe_facturas" in tablas
    assert "cfe_periodos" in tablas
    assert "cfe_mem_componentes" in tablas


def test_init_db_es_idempotente(conn):
    init_db(conn)
    init_db(conn)  # segunda llamada no debe lanzar error


def test_clientes_tiene_columnas_esperadas(conn):
    init_db(conn)
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(clientes)").fetchall()
    }
    assert {"id", "nombre", "rfc", "created_at"}.issubset(cols)


def test_cfe_facturas_referencia_clientes(conn):
    init_db(conn)
    info = conn.execute("PRAGMA foreign_key_list(cfe_facturas)").fetchall()
    tablas_ref = {row[2] for row in info}
    assert "clientes" in tablas_ref
