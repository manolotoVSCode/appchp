# tests/test_cogen_models.py
from __future__ import annotations
import pytest
from decimal import Decimal
from datetime import date
from models.cogen_result import CoGenParams, CoGenMes, CoGenResultado


def test_params_defaults():
    p = CoGenParams()
    assert p.cobertura_electrica == Decimal("0.75")
    assert p.rendimiento_electrico == Decimal("0.40")
    assert p.rendimiento_termico == Decimal("0.25")
    assert p.eficiencia_caldera == Decimal("0.85")


def test_mes_instancia():
    m = CoGenMes(
        periodo_inicio=date(2023, 11, 1),
        periodo_fin=date(2023, 11, 30),
        kwh_total=Decimal("1000000"),
        costo_cfe_mxn=Decimal("3000000"),
        costo_promedio_kwh=Decimal("3.00"),
        gj_consumido=Decimal("100000"),
        costo_unitario_gj=Decimal("80.00"),
        costo_gas_actual_mxn=Decimal("8000000"),
        kwh_cubiertos=Decimal("750000"),
        gj_gas_cogen=Decimal("6750"),
        costo_gas_cogen_mxn=Decimal("540000"),
        ahorro_electricidad_mxn=Decimal("2250000"),
        calor_recuperado_gj=Decimal("1687.50"),
        ahorro_caldera_mxn=Decimal("158823.53"),
        ebitda_mes_mxn=Decimal("1868823.53"),
    )
    assert m.periodo_inicio == date(2023, 11, 1)
    assert m.ebitda_mes_mxn == Decimal("1868823.53")


def test_resultado_totales():
    p = CoGenParams()
    m = CoGenMes(
        periodo_inicio=date(2023, 11, 1),
        periodo_fin=date(2023, 11, 30),
        kwh_total=Decimal("1000000"),
        costo_cfe_mxn=Decimal("3000000"),
        costo_promedio_kwh=Decimal("3.00"),
        gj_consumido=Decimal("100000"),
        costo_unitario_gj=Decimal("80.00"),
        costo_gas_actual_mxn=Decimal("8000000"),
        kwh_cubiertos=Decimal("750000"),
        gj_gas_cogen=Decimal("6750"),
        costo_gas_cogen_mxn=Decimal("540000"),
        ahorro_electricidad_mxn=Decimal("2250000"),
        calor_recuperado_gj=Decimal("1687.50"),
        ahorro_caldera_mxn=Decimal("158823.53"),
        ebitda_mes_mxn=Decimal("1868823.53"),
    )
    r = CoGenResultado(
        params=p,
        meses=[m],
        kwh_total_anual=Decimal("1000000"),
        kwh_cubiertos_anual=Decimal("750000"),
        gj_gas_cogen_anual=Decimal("6750"),
        costo_gas_cogen_anual_mxn=Decimal("540000"),
        ahorro_electricidad_anual_mxn=Decimal("2250000"),
        ahorro_caldera_anual_mxn=Decimal("158823.53"),
        ebitda_anual_mxn=Decimal("1868823.53"),
    )
    assert r.ebitda_anual_mxn == Decimal("1868823.53")
    assert len(r.meses) == 1
