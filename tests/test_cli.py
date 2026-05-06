from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from cli.main import procesar_factura_cfe

FIXTURE = Path("tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf")


def _make_supabase_mock(factura_id=1, cliente_id=1):
    """Construye un mock del cliente Supabase que responde a las operaciones del repository."""
    mock = MagicMock()

    def table_router(name):
        t = MagicMock()
        if name == "clientes":
            t.upsert.return_value.execute.return_value.data = [{"id": cliente_id}]
        elif name == "cfe_facturas":
            t.insert.return_value.execute.return_value.data = [{"id": factura_id}]
        else:
            t.insert.return_value.execute.return_value.data = []
        return t

    mock.table.side_effect = table_router
    return mock


def test_procesar_factura_cfe_devuelve_id():
    with patch("storage.repository._supabase", _make_supabase_mock(factura_id=7)):
        factura_id = procesar_factura_cfe(FIXTURE, tarifa="GDMTH")
    assert isinstance(factura_id, int)
    assert factura_id == 7


def test_procesar_tarifa_no_soportada_lanza_error():
    with pytest.raises(ValueError, match="no soportada"):
        procesar_factura_cfe(FIXTURE, tarifa="GDMTO")


def test_procesar_pdf_inexistente_lanza_error():
    with pytest.raises(FileNotFoundError):
        procesar_factura_cfe(Path("no_existe.pdf"))
