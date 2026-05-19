# tests/calc/test_cogen_ppa.py
from decimal import Decimal
from datetime import date

import pytest

from calc.cogen import calcular_cogen_ppa, CoGenParams
from models.factura_calificado import FacturaCalificado
from models.gas_invoice import GasInvoice, GasConcepto


def make_ppa(consumo_kwh="2000000", precio="2.0", subtotal="4000000.00"):
    return FacturaCalificado(
        id=1, contrato_id=1, cliente_id=1,
        suministrador="GIN", rpu="52200951158", serie_folio="GI01 00001",
        periodo_inicio=date(2024, 9, 1), periodo_fin=date(2024, 9, 30),
        dias_facturados=30, anio=2024, mes=9, nombre_canonico="2024-09",
        consumo_kwh=Decimal(consumo_kwh),
        precio_unitario_mxn_kwh=Decimal(precio),
        subtotal_mxn=Decimal(subtotal),
        iva_mxn=None, total_mxn=None,
        excedente_detectado=False, advertencias=[], pdf_url=None,
        parser_version="1.0.0", created_at=None,
    )


def make_gas():
    return GasInvoice(
        uuid_cfdi=None, folio="1", fecha_emision=date(2024, 9, 1),
        periodo_inicio=date(2024, 9, 1), periodo_fin=date(2024, 9, 30),
        fecha_limite_pago=date(2024, 10, 15),
        nombre_proveedor="ENGIE", rfc_proveedor="TRA0002119W1",
        nombre_cliente="CLIENTE TEST", rfc_cliente="CLI000101AAA",
        numero_cliente="123", cuenta_contrato="456",
        punto_suministro="P1", numero_caseta="C1", tipo_lectura="M",
        consumo_m3_corregidos=Decimal("10000"),
        consumo_sin_corregir_m3=Decimal("9800"),
        poder_calorifico_gj_m3=Decimal("0.0372"),
        consumo_total_gj=Decimal("372"),
        conceptos=[],
        costo_unitario_total_gj=Decimal("150"),
        subtotal_mxn=Decimal("55800"),
        iva_mxn=Decimal("8928"), total_mxn=Decimal("64728"),
        pdf_path="",
    )


def test_calcular_cogen_ppa_basico():
    r = calcular_cogen_ppa([make_ppa()], [make_gas()], CoGenParams())
    assert len(r.meses) == 1
    m = r.meses[0]
    assert m.kwh_total == Decimal("2000000")
    assert m.ahorro_electricidad_mxn > 0
    # Campos GDMTH deben ser 0
    assert m.ahorro_capacidad_mes_mxn == Decimal("0")
    assert m.ahorro_distribucion_mes_mxn == Decimal("0")
    assert m.kwh_punta_total == Decimal("0")
    assert m.kwh_intermedia_total == Decimal("0")
    assert m.kwh_base_total == Decimal("0")
    assert m.kw_max == Decimal("0")
    assert m.precio_capacidad_kw == Decimal("0")
    assert m.precio_distribucion_kw == Decimal("0")


def test_calcular_cogen_ppa_sin_gas():
    """Sin factura de gas para ese mes → sin meses resultado."""
    r = calcular_cogen_ppa([make_ppa()], [], CoGenParams())
    assert r.meses == []
    assert r.kwh_total_anual == Decimal("0")
    assert r.ebitda_anual_mxn == Decimal("0")


def test_calcular_cogen_ppa_ahorro_correcto():
    """Verificar fórmula: ahorro = kwh_cubiertos * costo_promedio."""
    ppa = make_ppa(consumo_kwh="1000000", subtotal="3000000.00")
    r = calcular_cogen_ppa([ppa], [make_gas()], CoGenParams())
    m = r.meses[0]
    kwh_cub = (Decimal("1000000") * Decimal("0.75")).quantize(Decimal("0.01"))
    costo_prom = (Decimal("3000000.00") / Decimal("1000000")).quantize(Decimal("0.01"))
    expected = (kwh_cub * costo_prom).quantize(Decimal("0.01"))
    assert m.ahorro_electricidad_mxn == expected


def test_calcular_cogen_ppa_capacidad_nominal():
    """Capacidad nominal = ceil(consumo_kwh / (días_facturados × 24 h)).
    make_ppa usa dias_facturados=30 → 720 h.
    ceil(2_000_000 / 720) = ceil(2777.77…) = 2778 kW.
    """
    import math
    r = calcular_cogen_ppa([make_ppa(consumo_kwh="2000000")], [make_gas()], CoGenParams())
    # dias_facturados del fixture = 30
    horas = Decimal(30 * 24)
    expected = Decimal(math.ceil(Decimal("2000000") / horas))
    assert r.capacidad_nominal_kw == expected


def test_calcular_cogen_ppa_inversion_calculada():
    """Con capacidad nominal válida, inversión USD y MXN se calculan."""
    r = calcular_cogen_ppa([make_ppa()], [make_gas()], CoGenParams(), tipo_cambio=Decimal("17.50"))
    assert r.inversion_usd is not None
    assert r.inversion_mxn is not None
    assert r.inversion_mxn > 0


def test_calcular_cogen_ppa_ebitda_componentes():
    """EBITDA = ahorro_elec + ahorro_caldera - costo_gas_cogen - gasto_om."""
    r = calcular_cogen_ppa([make_ppa()], [make_gas()], CoGenParams())
    m = r.meses[0]
    expected = m.ahorro_electricidad_mxn + m.ahorro_caldera_mxn - m.costo_gas_cogen_mxn - m.gasto_om_mes_mxn
    assert m.ebitda_mes_mxn == expected


def test_calcular_cogen_ppa_totales_anuales():
    """Totales anuales = suma de meses (con 1 mes = igual al mes)."""
    r = calcular_cogen_ppa([make_ppa()], [make_gas()], CoGenParams())
    m = r.meses[0]
    assert r.ebitda_anual_mxn == m.ebitda_mes_mxn
    assert r.kwh_total_anual == m.kwh_total
    assert r.kwh_cubiertos_anual == m.kwh_cubiertos
