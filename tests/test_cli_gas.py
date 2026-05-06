from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from cli.main import procesar_factura_gas

FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


def _make_supabase_mock(factura_id=1, cliente_id=1):
    """Construye un mock del cliente Supabase para operaciones de gas."""
    mock = MagicMock()

    def table_router(name):
        t = MagicMock()
        if name == "clientes":
            t.upsert.return_value.execute.return_value.data = [{"id": cliente_id}]
        elif name == "gas_facturas":
            t.insert.return_value.execute.return_value.data = [{"id": factura_id}]
        else:
            t.insert.return_value.execute.return_value.data = []
        return t

    mock.table.side_effect = table_router
    return mock


def test_procesar_factura_gas_devuelve_id():
    with patch("storage.repository._supabase", _make_supabase_mock(factura_id=5)):
        fid = procesar_factura_gas(FIXTURE)
    assert isinstance(fid, int) and fid == 5


def test_pdf_gas_inexistente_lanza_error():
    with pytest.raises(FileNotFoundError):
        procesar_factura_gas(Path("invoices/Gas/no_existe.pdf"))
