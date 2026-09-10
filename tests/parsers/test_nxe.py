from __future__ import annotations

from decimal import Decimal
from datetime import date
from pathlib import Path

import pytest

from parsers.electricidad_calificado.nxe import NXEParser
from models.nxe_invoice import NXEInvoice
from parsers.registry import registry

FIXTURE = Path("tests/fixtures/calificado/NXE_2025_08_AGOSTO.pdf")

# El fixture se obtiene de: "08.- Factura Ibérica Tiles Planta 1 definitivo_Agosto25_NXE.pdf"
pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason=f"Fixture {FIXTURE} no encontrado. Copiar PDF de NX Energía Agosto 2025.",
)


@pytest.fixture
def invoice() -> NXEInvoice:
    return NXEParser().parse(FIXTURE)


# ---------------------------------------------------------------------------
# Tipo e identificación
# ---------------------------------------------------------------------------

def test_devuelve_nxe_invoice(invoice):
    assert isinstance(invoice, NXEInvoice)


def test_suministrador(invoice):
    assert invoice.suministrador == "NX ENERGIA S.A. DE C.V."


def test_rfc_suministrador(invoice):
    assert invoice.rfc_suministrador == "NEN230613SE2"


def test_documento_ref(invoice):
    # Valor esperado según la cabecera del PDF (ajustar si difiere)
    assert invoice.documento_ref is not None
    assert "NXE" in invoice.documento_ref.upper()


# ---------------------------------------------------------------------------
# Periodo
# ---------------------------------------------------------------------------

def test_periodo_inicio(invoice):
    assert invoice.periodo_inicio == date(2025, 8, 1)


def test_periodo_fin(invoice):
    assert invoice.periodo_fin == date(2025, 8, 31)


# ---------------------------------------------------------------------------
# Consumo
# ---------------------------------------------------------------------------

def test_energia_consumida_kwh(invoice):
    assert invoice.energia_consumida_kwh == Decimal("2413311")


def test_precio_monocomico(invoice):
    assert invoice.precio_monocomico_mxn_kwh == Decimal("2.1181")


# ---------------------------------------------------------------------------
# 5 categorías del resumen
# ---------------------------------------------------------------------------

def test_cargo_energia_mxn(invoice):
    assert invoice.cargo_energia_mxn == Decimal("2385418.75")


def test_cargo_potencia_mxn(invoice):
    assert invoice.cargo_potencia_mxn == Decimal("1053014.87")


def test_cargo_cel_mxn(invoice):
    assert invoice.cargo_cel_mxn == Decimal("94125.63")


def test_cobro_total_mxn(invoice):
    assert invoice.cobro_total_mxn == Decimal("5111624.74")


# ---------------------------------------------------------------------------
# Suma de 5 categorías vs total
# ---------------------------------------------------------------------------

def test_suma_5_categorias_vs_total(invoice):
    if any(v is None for v in [
        invoice.cargo_energia_mxn, invoice.cargo_potencia_mxn,
        invoice.cargo_cel_mxn, invoice.cargos_regulados_mxn,
        invoice.ajustes_penalizaciones_mxn,
    ]):
        pytest.skip("Alguna categoría no disponible")
    suma = (
        invoice.cargo_energia_mxn
        + invoice.cargo_potencia_mxn
        + invoice.cargo_cel_mxn
        + invoice.cargos_regulados_mxn
        + invoice.ajustes_penalizaciones_mxn
    )
    diff = abs(suma - invoice.cobro_total_mxn)
    assert diff <= Decimal("100"), f"Diferencia {diff} supera tolerancia 100 MXN"


# ---------------------------------------------------------------------------
# Detalle diario
# ---------------------------------------------------------------------------

def test_detalle_diario_no_vacio(invoice):
    assert len(invoice.detalle_diario) > 0


def test_detalle_diario_fechas_agosto(invoice):
    fechas = [d["fecha"] for d in invoice.detalle_diario]
    assert all(f.startswith("2025-08") for f in fechas)


# ---------------------------------------------------------------------------
# Sin advertencias críticas
# ---------------------------------------------------------------------------

def test_sin_advertencias(invoice):
    # Ninguna advertencia debe mencionar campos no encontrados en los críticos
    criticos = {"energia_consumida_kwh", "cobro_total_mxn"}
    advertencias_criticas = [a for a in invoice.advertencias if any(c in a for c in criticos)]
    assert advertencias_criticas == [], advertencias_criticas


# ---------------------------------------------------------------------------
# Registry: auto-detección
# ---------------------------------------------------------------------------

def test_registry_detecta_nxe():
    parser_class = registry.auto_detect(FIXTURE)
    assert parser_class is NXEParser


def test_registry_nxe_en_listado():
    claves = [e.clave for e in registry.todos()]
    assert "NXE" in claves


def test_registry_get_nxe():
    entrada = registry.get("NXE")
    assert entrada is not None
    assert entrada.rfc_emisor == "NEN230613SE2"
