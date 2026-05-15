from __future__ import annotations

from decimal import Decimal
from datetime import date
from pathlib import Path

import pytest

from parsers.electricidad_calificado.gin import GINParser, GINInvoice

FIXTURE = Path("Invoices/Calificado/24. 2409F - ENERGIA ELECTRICA sep 24.pdf")


@pytest.fixture
def invoice() -> GINInvoice:
    parser = GINParser()
    return parser.parse(FIXTURE)


def test_parser_devuelve_gin_invoice(invoice):
    assert isinstance(invoice, GINInvoice)


def test_suministrador(invoice):
    assert invoice.suministrador == "GENERACION INDUSTRIAL"


def test_rfc_suministrador(invoice):
    assert invoice.rfc_suministrador == "GIN040707G89"


def test_rfc_receptor(invoice):
    assert invoice.rfc_receptor == "ITI170630377"


def test_serie_folio(invoice):
    assert invoice.serie_folio == "GI01 01312"


def test_folio_fiscal(invoice):
    assert invoice.folio_fiscal == "2C10B666-477A-4443-899C-A1C1B23C869E"


def test_fecha_factura(invoice):
    assert invoice.fecha_factura == date(2024, 10, 9)


def test_periodo_inicio(invoice):
    assert invoice.periodo_inicio == date(2024, 9, 1)


def test_periodo_fin(invoice):
    assert invoice.periodo_fin == date(2024, 9, 30)


def test_rpu(invoice):
    assert invoice.rpu == "52200951158"


def test_consumo_kwh(invoice):
    assert invoice.consumo_kwh == Decimal("2060135")


def test_precio_unitario(invoice):
    assert invoice.precio_unitario_mxn_kwh == Decimal("2.030600")


def test_subtotal_mxn(invoice):
    assert invoice.subtotal_mxn == Decimal("4183310.13")


def test_iva_mxn(invoice):
    assert invoice.iva_mxn == Decimal("669329.62")


def test_total_mxn(invoice):
    assert invoice.total_mxn == Decimal("4852639.75")


def test_sin_advertencias(invoice):
    assert invoice.advertencias == []
