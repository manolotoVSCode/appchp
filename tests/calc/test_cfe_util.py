# tests/calc/test_cfe_util.py
"""Tests para calc/cfe_util.py — calcular_costos_unitarios_kwh."""
from decimal import Decimal

import pytest

from calc.cfe_util import calcular_costos_unitarios_kwh


class TestCalcularCostosUnitariosKwh:
    """Verifica que la fórmula replica exactamente la del parser gdmth.py."""

    def test_formula_maspesca_julio2024(self):
        """Valores conocidos del PDF de MASPESCA julio 2024."""
        cu_base, cu_inter, cu_punta = calcular_costos_unitarios_kwh(
            kwh_base=Decimal("11530"),
            kwh_inter=Decimal("25106"),
            kwh_punta=Decimal("2281"),
            gen_b_mxn=Decimal("12846.73"),
            gen_i_mxn=Decimal("50668.93"),
            gen_p_mxn=Decimal("5191.78"),
            transmision_mxn=Decimal("6884.42"),
            cenace_mxn=Decimal("252.97"),
            scnmem_mxn=Decimal("241.29"),
        )
        # shared = (6884.42 + 252.97 + 241.29) / (11530 + 25106 + 2281)
        # shared = 7378.68 / 38917
        kwh_total = Decimal("38917")
        shared = (Decimal("6884.42") + Decimal("252.97") + Decimal("241.29")) / kwh_total
        expected_base  = (Decimal("12846.73") / Decimal("11530") + shared).quantize(Decimal("0.000001"))
        expected_inter = (Decimal("50668.93") / Decimal("25106") + shared).quantize(Decimal("0.000001"))
        expected_punta = (Decimal("5191.78")  / Decimal("2281")  + shared).quantize(Decimal("0.000001"))
        assert cu_base  == expected_base
        assert cu_inter == expected_inter
        assert cu_punta == expected_punta

    def test_kwh_total_cero_devuelve_ceros(self):
        cu_base, cu_inter, cu_punta = calcular_costos_unitarios_kwh(
            kwh_base=Decimal("0"),
            kwh_inter=Decimal("0"),
            kwh_punta=Decimal("0"),
            gen_b_mxn=Decimal("1000"),
            gen_i_mxn=Decimal("1000"),
            gen_p_mxn=Decimal("1000"),
            transmision_mxn=Decimal("500"),
            cenace_mxn=Decimal("100"),
            scnmem_mxn=Decimal("50"),
        )
        assert cu_base == Decimal("0")
        assert cu_inter == Decimal("0")
        assert cu_punta == Decimal("0")

    def test_resultado_tiene_6_decimales(self):
        cu_base, cu_inter, cu_punta = calcular_costos_unitarios_kwh(
            kwh_base=Decimal("10000"),
            kwh_inter=Decimal("20000"),
            kwh_punta=Decimal("5000"),
            gen_b_mxn=Decimal("15000"),
            gen_i_mxn=Decimal("40000"),
            gen_p_mxn=Decimal("10000"),
            transmision_mxn=Decimal("5000"),
            cenace_mxn=Decimal("200"),
            scnmem_mxn=Decimal("100"),
        )
        # Verificar que tiene exactamente 6 lugares decimales de precisión
        assert cu_base  == cu_base.quantize(Decimal("0.000001"))
        assert cu_inter == cu_inter.quantize(Decimal("0.000001"))
        assert cu_punta == cu_punta.quantize(Decimal("0.000001"))

    def test_punta_cero_kwh_devuelve_cero_para_punta(self):
        """Si no hay consumo punta, costo_punta es 0."""
        cu_base, cu_inter, cu_punta = calcular_costos_unitarios_kwh(
            kwh_base=Decimal("10000"),
            kwh_inter=Decimal("20000"),
            kwh_punta=Decimal("0"),
            gen_b_mxn=Decimal("15000"),
            gen_i_mxn=Decimal("40000"),
            gen_p_mxn=Decimal("0"),
            transmision_mxn=Decimal("5000"),
            cenace_mxn=Decimal("200"),
            scnmem_mxn=Decimal("100"),
        )
        assert cu_punta == Decimal("0")
        assert cu_base  > Decimal("0")
        assert cu_inter > Decimal("0")
