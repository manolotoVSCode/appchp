from __future__ import annotations
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from parsers.gas import get_gas_parser
from parsers.gas.engie import ENGIEParser
from models.gas_invoice import GasInvoice, GasConcepto

FIXTURE = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")


@pytest.fixture(scope="module")
def inv():
    return get_gas_parser().parse(FIXTURE)


def test_parse_devuelve_gas_invoice(inv):
    assert isinstance(inv, GasInvoice)


def test_uuid_cfdi(inv):
    assert inv.uuid_cfdi.lower() == "59030c00-01f5-4dc9-bda1-25d579b23095"


def test_folio(inv):
    assert inv.folio == "I00000547"


def test_fecha_emision(inv):
    assert inv.fecha_emision == date(2023, 12, 14)


def test_periodo_inicio(inv):
    assert inv.periodo_inicio == date(2023, 11, 1)


def test_periodo_fin(inv):
    assert inv.periodo_fin == date(2023, 11, 30)


def test_fecha_limite_pago(inv):
    assert inv.fecha_limite_pago == date(2023, 12, 25)


def test_rfc_proveedor(inv):
    assert inv.rfc_proveedor == "TRA0002119W1"


def test_rfc_cliente(inv):
    assert inv.rfc_cliente == "ITI170630377"


def test_numero_cliente(inv):
    assert inv.numero_cliente == "610002800"


def test_cuenta_contrato(inv):
    assert inv.cuenta_contrato == "5100096634"


def test_consumo_m3(inv):
    assert inv.consumo_m3_corregidos == Decimal("2960411.81")


def test_poder_calorifico(inv):
    assert inv.poder_calorifico_gj_m3 == Decimal("0.035958531")


def test_consumo_total_gj(inv):
    assert inv.consumo_total_gj == Decimal("106445.1830")


def test_dos_conceptos(inv):
    assert len(inv.conceptos) == 2


def test_concepto_compraventa(inv):
    c = next(x for x in inv.conceptos if x.clave_producto == "83101601")
    assert c.descripcion == "Compraventa de Gas Natural"
    assert c.cantidad_gj == Decimal("106445.1830")
    assert c.precio_unitario_gj == Decimal("54.8500")
    assert c.importe_mxn == Decimal("5838518.28")


def test_concepto_transporte(inv):
    c = next(x for x in inv.conceptos if x.clave_producto == "78102101")
    assert c.descripcion == "Transporte por Ducto Gas Natural"
    assert c.precio_unitario_gj == Decimal("24.6300")
    assert c.importe_mxn == Decimal("2621744.85")


def test_costo_unitario_total(inv):
    assert inv.costo_unitario_total_gj == Decimal("79.4800")


def test_subtotal(inv):
    assert inv.subtotal_mxn == Decimal("8460263.13")


def test_iva(inv):
    assert inv.iva_mxn == Decimal("1353642.10")


def test_total(inv):
    assert inv.total_mxn == Decimal("9813905.23")


def test_validacion_sin_errores(inv):
    parser = get_gas_parser()
    assert parser.validate(inv) == []


def test_factory_devuelve_engie_parser():
    assert isinstance(get_gas_parser(), ENGIEParser)
