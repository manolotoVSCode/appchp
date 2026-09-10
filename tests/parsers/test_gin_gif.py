from __future__ import annotations

from decimal import Decimal
from datetime import date
from pathlib import Path

import pytest

from parsers.electricidad_calificado.gin_gif import GINGIFParser, GINInvoice
from parsers.registry import registry

FIXTURE = Path("tests/fixtures/calificado/GIN_GIF_2025_02_FEBRERO.pdf")
FIXTURE_ABR2025 = Path("tests/fixtures/calificado/GIN_GIF_2025_04_ABRIL.pdf")


@pytest.fixture
def invoice() -> GINInvoice:
    return GINGIFParser().parse(FIXTURE)


@pytest.fixture
def invoice_abr() -> GINInvoice:
    return GINGIFParser().parse(FIXTURE_ABR2025)


# ---------------------------------------------------------------------------
# Metadatos CFDI
# ---------------------------------------------------------------------------

def test_devuelve_gin_invoice(invoice):
    assert isinstance(invoice, GINInvoice)


def test_suministrador(invoice):
    assert invoice.suministrador == "GENERACION INDUSTRIAL"


def test_rfc_suministrador(invoice):
    assert invoice.rfc_suministrador == "GIN040707G89"


def test_rfc_receptor(invoice):
    assert invoice.rfc_receptor == "ITI170630377"


def test_serie_folio(invoice):
    # Formato GIF: serie + guión + folio
    assert invoice.serie_folio == "GIF-0129"


def test_folio_fiscal(invoice):
    assert invoice.folio_fiscal == "22584568-2805-4167-9C85-92FECDFA01C7"


def test_fecha_factura(invoice):
    assert invoice.fecha_factura == date(2025, 3, 11)


# ---------------------------------------------------------------------------
# Periodo
# ---------------------------------------------------------------------------

def test_periodo_inicio(invoice):
    assert invoice.periodo_inicio == date(2025, 2, 1)


def test_periodo_fin(invoice):
    assert invoice.periodo_fin == date(2025, 2, 28)


def test_rpu_es_none(invoice):
    # El formato GIF no incluye RPU
    assert invoice.rpu is None


# ---------------------------------------------------------------------------
# Energía y precios
# ---------------------------------------------------------------------------

def test_consumo_kwh(invoice):
    assert invoice.consumo_kwh == Decimal("1839201")


def test_precio_unitario(invoice):
    assert invoice.precio_unitario_mxn_kwh == Decimal("2.1239")


def test_subtotal_mxn(invoice):
    assert invoice.subtotal_mxn == Decimal("3906276.39")


def test_iva_mxn(invoice):
    assert invoice.iva_mxn == Decimal("625004.22")


def test_total_mxn(invoice):
    assert invoice.total_mxn == Decimal("4531280.61")


def test_sin_advertencias(invoice):
    assert invoice.advertencias == []


# ---------------------------------------------------------------------------
# Registry: auto-detección
# ---------------------------------------------------------------------------

def test_registry_detecta_gin_gif():
    parser_class = registry.auto_detect(FIXTURE)
    assert parser_class is GINGIFParser


def test_registry_no_detecta_gin_a_en_gif():
    from parsers.electricidad_calificado.gin import GINParser
    parser_class = registry.auto_detect(FIXTURE)
    assert parser_class is not GINParser


def test_registry_gin_gif_en_listado():
    claves = [e.clave for e in registry.todos()]
    assert "GIN_GIF" in claves


def test_registry_get_gin_gif():
    entrada = registry.get("GIN_GIF")
    assert entrada is not None
    assert entrada.rfc_emisor == "GIN040707G89"


# ---------------------------------------------------------------------------
# Variante Abril 2025 (RAZÓN SOCIAL: / RFC: prefijos, PERIODO uppercase, RPU)
# ---------------------------------------------------------------------------

def test_abr_devuelve_gin_invoice(invoice_abr):
    assert isinstance(invoice_abr, GINInvoice)


def test_abr_suministrador(invoice_abr):
    assert invoice_abr.suministrador == "GENERACION INDUSTRIAL"


def test_abr_rfc_suministrador(invoice_abr):
    assert invoice_abr.rfc_suministrador == "GIN040707G89"


def test_abr_rfc_receptor(invoice_abr):
    assert invoice_abr.rfc_receptor == "ITI170630377"


def test_abr_serie_folio(invoice_abr):
    assert invoice_abr.serie_folio == "GIF-0522"


def test_abr_fecha_factura(invoice_abr):
    assert invoice_abr.fecha_factura == date(2025, 5, 9)


def test_abr_periodo_inicio(invoice_abr):
    assert invoice_abr.periodo_inicio == date(2025, 4, 1)


def test_abr_periodo_fin(invoice_abr):
    assert invoice_abr.periodo_fin == date(2025, 4, 30)


def test_abr_rpu(invoice_abr):
    assert invoice_abr.rpu == "052200951158"


def test_abr_consumo_kwh(invoice_abr):
    assert invoice_abr.consumo_kwh == Decimal("2792802")


def test_abr_precio_unitario(invoice_abr):
    assert invoice_abr.precio_unitario_mxn_kwh == Decimal("2.0103")


def test_abr_subtotal_mxn(invoice_abr):
    assert invoice_abr.subtotal_mxn == Decimal("5614344.10")


def test_abr_iva_mxn(invoice_abr):
    assert invoice_abr.iva_mxn == Decimal("898295.06")


def test_abr_total_mxn(invoice_abr):
    assert invoice_abr.total_mxn == Decimal("6512639.16")


def test_abr_sin_advertencias(invoice_abr):
    assert invoice_abr.advertencias == []
