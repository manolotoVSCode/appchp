# tests/calc/test_periodo.py
from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from calc.periodo import mes_asociado, prorratear_cfe, prorratear_gas, UMBRAL_PRORRATEO_DIAS
from models.cfe_invoice import CFEInvoice, CFEConsumoHorario
from models.gas_invoice import GasInvoice, GasConcepto


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfe_con_periodo(inicio: date, fin: date, dias: int | None = None) -> CFEInvoice:
    """CFEInvoice mínima para tests de prorrateo."""
    kwh = Decimal("1000")
    return CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"),
        periodos=[CFEConsumoHorario("base", kwh, Decimal("100"), Decimal("2.00"))],
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[],
        cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=Decimal("3000"),
        cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=Decimal("3000"),
        iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=Decimal("3000"),
        derecho_alumbrado_publico_mxn=Decimal("0"),
        credito_aplicado_mxn=Decimal("0"),
        total_mxn=Decimal("3000"),
        pdf_path="test.pdf",
    )


def _gas_con_periodo(inicio: date, fin: date) -> GasInvoice:
    """GasInvoice mínima para tests de prorrateo."""
    gj = Decimal("100")
    precio = Decimal("80.00")
    return GasInvoice(
        uuid_cfdi="uuid", folio="G1",
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_proveedor="ENGIE",
        rfc_proveedor="TRA0002119W1", nombre_cliente="TEST",
        rfc_cliente="TST010101AAA", numero_cliente="610002800",
        cuenta_contrato="5100096634", punto_suministro="TEST",
        numero_caseta="C1", tipo_lectura="REAL",
        consumo_m3_corregidos=Decimal("100000"),
        consumo_sin_corregir_m3=Decimal("0"),
        poder_calorifico_gj_m3=Decimal("0.036"),
        consumo_total_gj=gj,
        conceptos=[GasConcepto("Gas Natural", "83101601", gj, precio, gj * precio)],
        costo_unitario_total_gj=precio,
        subtotal_mxn=gj * precio,
        iva_mxn=Decimal("1280.00"),
        total_mxn=gj * precio + Decimal("1280.00"),
        pdf_path="test.pdf",
    )


# ── Tests: mes_asociado ───────────────────────────────────────────────────────

def test_mes_asociado_mes_completo():
    """Ene 1 a Ene 31 → enero trivial."""
    assert mes_asociado(date(2024, 1, 1), date(2024, 1, 31)) == (2024, 1)


def test_mes_asociado_noviembre_parcial():
    """Nov 7 a Nov 30 → noviembre (todos los días en nov)."""
    assert mes_asociado(date(2023, 11, 7), date(2023, 11, 30)) == (2023, 11)


def test_mes_asociado_cruce_dic_ene():
    """Dic 31 a Ene 31 → enero (diciembre 1 día, enero 31 días)."""
    assert mes_asociado(date(2023, 12, 31), date(2024, 1, 31)) == (2024, 1)


def test_mes_asociado_cruce_feb_mar():
    """Feb 29 a Mar 31 → marzo (febrero 1 día en año bisiesto, marzo 31 días)."""
    assert mes_asociado(date(2024, 2, 29), date(2024, 3, 31)) == (2024, 3)


def test_mes_asociado_empate_asigna_posterior():
    """Feb 15 a Mar 15 (2024): periodo_fin excluido (< fix).
    Feb 15 a Mar 14 (inclusive): Feb 15..29 = 15 días; Mar 1..14 = 14 días → febrero gana.
    Nota: con periodo_fin excluido ya no hay empate; Feb tiene un día más."""
    # Con el fix (< periodo_fin), Mar 15 queda excluido:
    # Feb: días 15..29 = 15 días; Mar: días 1..14 = 14 días → Feb gana
    result = mes_asociado(date(2024, 2, 15), date(2024, 3, 15))
    assert result == (2024, 2)


def test_mes_asociado_empate_real_asigna_posterior():
    """Empate real con periodo_fin excluido: Feb 16 a Mar 16 (2024).
    Feb 16..29 = 14 días; Mar 1..15 = 15 días → marzo gana por días."""
    result = mes_asociado(date(2024, 2, 16), date(2024, 3, 16))
    assert result == (2024, 3)


def test_mes_asociado_patron_cfe_tipico():
    """Oct 31 a Nov 30 (patrón típico CFE): Oct 1 día, Nov 30 días → noviembre."""
    assert mes_asociado(date(2023, 10, 31), date(2023, 11, 30)) == (2023, 11)


# ── Tests: prorratear_cfe ─────────────────────────────────────────────────────

def test_prorratear_cfe_30_dias_no_prorratea():
    """Factura con (fin - inicio).days = 30 no se prorratea."""
    inv = _cfe_con_periodo(date(2023, 11, 1), date(2023, 12, 1))  # 30 días
    result, factor = prorratear_cfe(inv)
    assert factor is None
    assert result is inv  # misma instancia, sin copia


def test_prorratear_cfe_25_dias_no_prorratea():
    """Umbral inclusivo: 25 días no se prorratea."""
    inv = _cfe_con_periodo(date(2023, 11, 6), date(2023, 12, 1))  # 25 días
    result, factor = prorratear_cfe(inv)
    assert factor is None


def test_prorratear_cfe_23_dias_aplica_factor():
    """Factura de 23 días se multiplica por 30/23."""
    inv = _cfe_con_periodo(date(2023, 11, 8), date(2023, 12, 1))  # 23 días
    result, factor = prorratear_cfe(inv)
    assert factor is not None
    esperado = (Decimal("30") / Decimal("23")).quantize(Decimal("0.0001"))
    assert factor == esperado


def test_prorratear_cfe_23_dias_escala_facturacion():
    """facturacion_periodo_mxn se escala por el factor."""
    inv = _cfe_con_periodo(date(2023, 11, 8), date(2023, 12, 1))  # 23 días
    result, factor = prorratear_cfe(inv)
    esperado = (Decimal("3000") * factor).quantize(Decimal("0.01"))
    assert result.facturacion_periodo_mxn == esperado


def test_prorratear_cfe_23_dias_escala_consumo_kwh():
    """consumo_kwh en periodos se escala por el factor."""
    inv = _cfe_con_periodo(date(2023, 11, 8), date(2023, 12, 1))  # 23 días
    result, factor = prorratear_cfe(inv)
    esperado = (Decimal("1000") * factor).quantize(Decimal("0.01"))
    assert result.periodos[0].consumo_kwh == esperado


def test_prorratear_cfe_no_muta_original():
    """La factura original no se modifica."""
    inv = _cfe_con_periodo(date(2023, 11, 8), date(2023, 12, 1))
    original_facturacion = inv.facturacion_periodo_mxn
    prorratear_cfe(inv)
    assert inv.facturacion_periodo_mxn == original_facturacion


# ── Tests: prorratear_gas ─────────────────────────────────────────────────────

def test_prorratear_gas_30_dias_no_prorratea():
    """Factura gas de 30 días no se prorratea."""
    inv = _gas_con_periodo(date(2023, 11, 1), date(2023, 12, 1))  # 30 días
    result, factor = prorratear_gas(inv)
    assert factor is None
    assert result is inv


def test_prorratear_gas_25_dias_no_prorratea():
    """Umbral inclusivo: 25 días no se prorratea."""
    inv = _gas_con_periodo(date(2023, 11, 6), date(2023, 12, 1))  # 25 días
    result, factor = prorratear_gas(inv)
    assert factor is None


def test_prorratear_gas_23_dias_aplica_factor():
    """Factura gas de 23 días se multiplica por 30/23."""
    inv = _gas_con_periodo(date(2023, 11, 8), date(2023, 12, 1))  # 23 días
    result, factor = prorratear_gas(inv)
    assert factor is not None
    esperado = (Decimal("30") / Decimal("23")).quantize(Decimal("0.0001"))
    assert factor == esperado


def test_prorratear_gas_23_dias_escala_consumo_gj():
    """consumo_total_gj se escala por el factor."""
    inv = _gas_con_periodo(date(2023, 11, 8), date(2023, 12, 1))  # 23 días
    result, factor = prorratear_gas(inv)
    esperado = (Decimal("100") * factor).quantize(Decimal("0.0001"))
    assert result.consumo_total_gj == esperado


def test_prorratear_gas_no_escala_precio_unitario():
    """costo_unitario_total_gj NO se escala (es precio por unidad)."""
    inv = _gas_con_periodo(date(2023, 11, 8), date(2023, 12, 1))  # 23 días
    result, _ = prorratear_gas(inv)
    assert result.costo_unitario_total_gj == inv.costo_unitario_total_gj


# ── Test de integración: motor produce 12 meses ───────────────────────────────

def test_calcular_cogen_12_meses_con_periodos_reales():
    """Con 12 CFE (patrón fin_mes_anterior a fin_mes) y 12 Gas (mes calendario completo),
    el motor debe producir exactamente 12 meses pareados."""
    from models.cogen_result import CoGenParams
    from calc.cogen import calcular_cogen

    # Meses: nov 2023 a oct 2024
    meses = [
        (2023, 11), (2023, 12),
        (2024, 1), (2024, 2), (2024, 3), (2024, 4),
        (2024, 5), (2024, 6), (2024, 7), (2024, 8), (2024, 9), (2024, 10),
    ]

    cfe_invoices = []
    gas_invoices = []

    for anio, mes in meses:
        # CFE: patrón "último día mes anterior → último día mes"
        if mes == 1:
            inicio_cfe = date(anio - 1, 12, 31)
        else:
            ultimo_mes_ant = calendar.monthrange(anio, mes - 1)[1]
            inicio_cfe = date(anio, mes - 1, ultimo_mes_ant)
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        fin_cfe = date(anio, mes, ultimo_dia)
        cfe_invoices.append(_cfe_con_periodo(inicio_cfe, fin_cfe))

        # Gas: mes calendario completo (1 al último)
        gas_invoices.append(_gas_con_periodo(date(anio, mes, 1), date(anio, mes, ultimo_dia)))

    resultado = calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())
    assert len(resultado.meses) == 12


def test_calcular_cogen_mes_prorrateado_produce_resultado():
    """Un mes con gas de periodo corto (23 días) se prorratea y produce resultado."""
    from models.cogen_result import CoGenParams
    from calc.cogen import calcular_cogen

    # CFE: Oct 31 a Nov 30 (patrón normal)
    cfe = [_cfe_con_periodo(date(2023, 10, 31), date(2023, 11, 30))]
    # Gas: Nov 8 a Nov 30 (23 días — inicio de contrato)
    gas = [_gas_con_periodo(date(2023, 11, 8), date(2023, 11, 30))]

    resultado = calcular_cogen(cfe, gas, CoGenParams())
    assert len(resultado.meses) == 1
    assert resultado.meses[0].prorrateado is True
    assert "Gas" in resultado.meses[0].nota_prorrateo
