# tests/calc/test_cogen.py
from __future__ import annotations
import math
import pytest
from decimal import Decimal
from datetime import date

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice, GasConcepto
from models.cogen_result import CoGenParams, CoGenMes, CoGenResultado
from calc.cogen import calcular_cogen, calcular_payback_decimal, calcular_flujo_acumulado


# ── Helpers para construir fixtures sintéticos ────────────────────────────────

def _cfe(year: int, month: int, kwh: Decimal, facturacion: Decimal) -> CFEInvoice:
    tercio = kwh / 3
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    inicio = date(year, month, 1)
    fin_month = 30 if month in (4,6,9,11) else (28 if month == 2 else 31)
    fin = date(year, month, fin_month)
    return CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=facturacion, cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=facturacion, iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=facturacion,
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=facturacion, pdf_path="test.pdf",
    )


def _gas(year: int, month: int, gj: Decimal, precio_gj: Decimal) -> GasInvoice:
    subtotal = gj * precio_gj
    inicio = date(year, month, 1)
    fin_month = 30 if month in (4,6,9,11) else (28 if month == 2 else 31)
    fin = date(year, month, fin_month)
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
        conceptos=[
            GasConcepto("Compraventa de Gas Natural", "83101601",
                        gj, precio_gj * Decimal("0.69"), gj * precio_gj * Decimal("0.69")),
            GasConcepto("Transporte por Ducto Gas Natural", "78102101",
                        gj, precio_gj * Decimal("0.31"), gj * precio_gj * Decimal("0.31")),
        ],
        costo_unitario_total_gj=precio_gj,
        subtotal_mxn=subtotal,
        iva_mxn=(subtotal * Decimal("0.16")).quantize(Decimal("0.01")),
        total_mxn=(subtotal * Decimal("1.16")).quantize(Decimal("0.01")),
        pdf_path="test.pdf",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

KWH = Decimal("1000000")
FACTURACION = Decimal("3000000")
GJ = Decimal("100000")
PRECIO_GJ = Decimal("80.00")


@pytest.fixture
def resultado_un_mes():
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    return calcular_cogen(cfe, gas, CoGenParams())


def test_devuelve_cogen_resultado(resultado_un_mes):
    assert isinstance(resultado_un_mes, CoGenResultado)


def test_un_mes_en_resultado(resultado_un_mes):
    assert len(resultado_un_mes.meses) == 1


def test_kwh_cubiertos(resultado_un_mes):
    # 1_000_000 × 0.75 = 750_000
    assert resultado_un_mes.meses[0].kwh_cubiertos == Decimal("750000.00")


def test_costo_promedio_kwh(resultado_un_mes):
    # 3_000_000 / 1_000_000 = 3.00
    assert resultado_un_mes.meses[0].costo_promedio_kwh == Decimal("3.00")


def test_gj_gas_cogen(resultado_un_mes):
    # 750_000 × 0.0036 × 1.11 / 0.40 = 7_492.50
    assert resultado_un_mes.meses[0].gj_gas_cogen == Decimal("7492.5000")


def test_costo_gas_cogen(resultado_un_mes):
    # 7_492.5 × 80 = 599_400.00
    assert resultado_un_mes.meses[0].costo_gas_cogen_mxn == Decimal("599400.00")


def test_ahorro_electricidad_es_suma_componentes(resultado_un_mes):
    """ahorro_electricidad = ahorro_energia + ahorro_capacidad + ahorro_distribucion + ahorro_otros."""
    m = resultado_un_mes.meses[0]
    assert m.ahorro_electricidad_mxn == (
        m.ahorro_energia_mes_mxn + m.ahorro_capacidad_mes_mxn
        + m.ahorro_distribucion_mes_mxn + m.ahorro_otros_servicios_mes_mxn
    )


def test_calor_recuperado(resultado_un_mes):
    # 7_492.5 × 0.25 = 1_873.1250
    assert resultado_un_mes.meses[0].calor_recuperado_gj == Decimal("1873.1250")


def test_ahorro_caldera(resultado_un_mes):
    # (1_873.125 / 0.85) × 80 = 176_247.06 (redondeado a centavos)
    esperado = (Decimal("1873.1250") / Decimal("0.85") * Decimal("80.00")).quantize(Decimal("0.01"))
    assert resultado_un_mes.meses[0].ahorro_caldera_mxn == esperado


def test_ebitda_mes(resultado_un_mes):
    m = resultado_un_mes.meses[0]
    esperado = m.ahorro_electricidad_mxn + m.ahorro_caldera_mxn - m.costo_gas_cogen_mxn - m.gasto_om_mes_mxn
    assert m.ebitda_mes_mxn == esperado


def test_meses_sin_par_se_omiten():
    """Si CFE tiene un mes que Gas no tiene, ese mes no aparece en resultado."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION), _cfe(2023, 12, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]  # solo noviembre
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert len(r.meses) == 1
    assert r.meses[0].periodo_inicio == date(2023, 11, 1)


def test_totales_anuales_son_suma_mensual():
    cfe = [_cfe(2023, 11, KWH, FACTURACION), _cfe(2023, 12, KWH * 2, FACTURACION * 2)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ), _gas(2023, 12, GJ * 2, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert r.ebitda_anual_mxn == sum(m.ebitda_mes_mxn for m in r.meses)
    assert r.kwh_total_anual == sum(m.kwh_total for m in r.meses)


def test_factor_pci_pcs_incrementa_gj(resultado_un_mes):
    """gj_gas_cogen con factor 1.11 debe ser mayor que sin corrección PCI→PCS."""
    m = resultado_un_mes.meses[0]
    gj_sin_factor = m.kwh_cubiertos * Decimal("0.0036") / Decimal("0.40")
    assert m.gj_gas_cogen > gj_sin_factor


def test_gasto_om_es_0_3_mxn_por_kwh_cubierto(resultado_un_mes):
    """O&M = 0.3 MXN/kWh × kWh_cubiertos (costo fijo por kWh, no porcentaje del costo)."""
    m = resultado_un_mes.meses[0]
    # 750_000 kWh × 0.3 MXN/kWh = 225_000.00 MXN
    esperado = (m.kwh_cubiertos * Decimal("0.3")).quantize(Decimal("0.01"))
    assert m.gasto_om_mes_mxn == esperado


def test_ahorro_neto_incluye_om(resultado_un_mes):
    """ebitda_mes_mxn (Ahorro Neto) = ingresos − costo gas − O&M."""
    m = resultado_un_mes.meses[0]
    esperado = (m.ahorro_electricidad_mxn + m.ahorro_caldera_mxn
                - m.costo_gas_cogen_mxn - m.gasto_om_mes_mxn)
    assert m.ebitda_mes_mxn == esperado


def test_gasto_om_anual_es_suma_mensual():
    cfe = [_cfe(2023, 11, KWH, FACTURACION), _cfe(2023, 12, KWH * 2, FACTURACION * 2)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ), _gas(2023, 12, GJ * 2, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert r.gasto_om_anual_mxn == sum(m.gasto_om_mes_mxn for m in r.meses)


# ── Tests metodología GDMTH 3 componentes ────────────────────────────────────

def test_greedy_cubre_punta_primero(resultado_un_mes):
    """Con cobertura 75%, los kWh más caros (punta) se cubren primero."""
    m = resultado_un_mes.meses[0]
    punta_total = KWH / 3  # fixture usa tercio igual por horario
    # punta se cubre completa porque el greedy la prioriza y 750k > 333k
    assert m.kwh_punta_cubierto <= punta_total
    assert m.kwh_punta_cubierto == punta_total


def test_ahorro_energia_mayor_que_promedio():
    """Greedy da ahorro mayor que promedio cuando punta concentra poco consumo pero precio alto."""
    kwh_base  = Decimal("800000")
    kwh_inter = Decimal("150000")
    kwh_punta = Decimal("50000")
    total = kwh_base + kwh_inter + kwh_punta
    cu_base  = Decimal("1.00")
    cu_inter = Decimal("1.50")
    cu_punta = Decimal("2.50")
    costo_total = kwh_base * cu_base + kwh_inter * cu_inter + kwh_punta * cu_punta
    costo_prom = costo_total / total

    # Con cobertura 75%: 750_000 kWh cubiertos
    # Greedy: 50k punta + 150k inter + 550k base
    kwh_cub = total * Decimal("0.75")
    ahorro_greedy = (
        Decimal("50000") * cu_punta
        + Decimal("150000") * cu_inter
        + (kwh_cub - Decimal("200000")) * cu_base
    )
    ahorro_promedio = kwh_cub * costo_prom
    assert ahorro_greedy > ahorro_promedio


def test_ahorro_capacidad_cero():
    """Ahorro capacidad es 0 (supuesto conservador: kw_max no cambia)."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert r.meses[0].ahorro_capacidad_mes_mxn == Decimal("0")


def test_ahorro_distribucion_cero():
    """Ahorro distribución es 0 (supuesto conservador: kw_max no cambia)."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert r.meses[0].ahorro_distribucion_mes_mxn == Decimal("0")


def test_ahorro_electricidad_igual_suma_componentes():
    """ahorro_electricidad = suma de los 4 componentes (energía, capacidad, distribución, otros)."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    m = r.meses[0]
    assert m.ahorro_electricidad_mxn == (
        m.ahorro_energia_mes_mxn + m.ahorro_capacidad_mes_mxn
        + m.ahorro_distribucion_mes_mxn + m.ahorro_otros_servicios_mes_mxn
    )


def test_ahorro_capacidad_con_componentes_mem():
    """Con componentes MEM presentes, ahorro_capacidad > 0."""
    # kw_max=1000, punta demanda_kw=1000 → kw_punta=1000
    # MEM: Capacidad $100,000 y Distribución $30,000
    # precio_capacidad  = 100,000 / kw_punta(1000) = 100 MXN/kW  (Capacidad usa kw_punta)
    # precio_distribucion = 30,000 / kw_max(1000)  =  30 MXN/kW  (Distribución usa kw_max)
    # kwh_total_orig = 1,000,000; cobertura=75% → kwh_post=250,000
    # dias_orig = (date(2023,11,30) - date(2023,11,1)).days = 29
    # demanda_promedio_post = 250,000 / (24 × 29) = 359.1954...
    # demanda_efectiva_post = 359.1954... / 0.57 = 630.1675...
    # reduccion_cap  = max(kw_punta(1000) - 630.17, 0) = 369.83 kW
    # reduccion_dist = max(kw_max(1000)   - 630.17, 0) = 369.83 kW
    # ahorro_capacidad    = 100 × 369.83 ≈ 36,983 MXN
    # ahorro_distribucion =  30 × 369.83 ≈ 11,095 MXN
    from models.cfe_invoice import MEMComponente

    tercio = KWH / 3
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"),  Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"),  Decimal("1.20")),
        # demanda_kw=1000 en punta → kw_punta=1000 → precio_cap = 100,000/1000 = 100 MXN/kW
        # reduccion_cap = max(1000 - 630.17, 0) ≈ 369.83 kW → ahorro_cap ≈ 36,983 MXN
        CFEConsumoHorario("punta",      tercio, Decimal("1000"), Decimal("1.50")),
    ]
    inicio = date(2023, 11, 1)
    fin = date(2023, 11, 30)
    cfe_mem = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("1000"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[
            MEMComponente(
                nombre="Capacidad",
                cargo_fijo_mxn=Decimal("0"),
                cargo_demanda_mxn=Decimal("100000"),
                cargo_energia_mxn=Decimal("0"),
                importe_mxn=Decimal("100000"),
            ),
            MEMComponente(
                nombre="Distribución",
                cargo_fijo_mxn=Decimal("0"),
                cargo_demanda_mxn=Decimal("30000"),
                cargo_energia_mxn=Decimal("0"),
                importe_mxn=Decimal("30000"),
            ),
        ],
        cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=FACTURACION, cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=FACTURACION, iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=FACTURACION,
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=FACTURACION, pdf_path="test.pdf",
    )
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen([cfe_mem], gas, CoGenParams())
    m = r.meses[0]

    # Verificar que ahorro_capacidad y ahorro_distribucion > 0
    assert m.ahorro_capacidad_mes_mxn > Decimal("0"), (
        f"ahorro_capacidad esperado > 0, obtenido {m.ahorro_capacidad_mes_mxn}"
    )
    assert m.ahorro_distribucion_mes_mxn > Decimal("0"), (
        f"ahorro_distribucion esperado > 0, obtenido {m.ahorro_distribucion_mes_mxn}"
    )

    # El invariante estructural se mantiene (4 componentes; ahorro_otros=0 sin Transmisión/CENACE/SCnMEM)
    assert m.ahorro_electricidad_mxn == (
        m.ahorro_energia_mes_mxn + m.ahorro_capacidad_mes_mxn
        + m.ahorro_distribucion_mes_mxn + m.ahorro_otros_servicios_mes_mxn
    )

    # Verificar rangos razonables:
    # dias_orig = 29, kwh_post = 250,000, demanda_efectiva_post ≈ 630.17 kW
    # reduccion_cap  = max(kw_punta(1000) - 630.17, 0) ≈ 369.83 kW
    # reduccion_dist = max(kw_max(1000)   - 630.17, 0) ≈ 369.83 kW
    # precio_cap = 100 MXN/kW → ahorro_cap ≈ 36,983 MXN
    # precio_dist = 30 MXN/kW → ahorro_dist ≈ 11,095 MXN
    assert Decimal("36000") < m.ahorro_capacidad_mes_mxn < Decimal("38000")
    assert Decimal("10000") < m.ahorro_distribucion_mes_mxn < Decimal("12000")


def test_totales_anuales_componentes_son_suma_mensual():
    """Los totales anuales de los 4 componentes son la suma de los mensuales."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION), _cfe(2023, 12, KWH * 2, FACTURACION * 2)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ), _gas(2023, 12, GJ * 2, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    assert r.ahorro_energia_anual_mxn == sum(m.ahorro_energia_mes_mxn for m in r.meses)
    assert r.ahorro_capacidad_anual_mxn == sum(m.ahorro_capacidad_mes_mxn for m in r.meses)
    assert r.ahorro_distribucion_anual_mxn == sum(m.ahorro_distribucion_mes_mxn for m in r.meses)
    assert r.ahorro_otros_servicios_anual_mxn == sum(m.ahorro_otros_servicios_mes_mxn for m in r.meses)


# ── Tests de capacidad nominal, inversión, payback y flujo ───────────────────

def test_capacidad_nominal_kw(resultado_un_mes):
    """capacidad = ceil(kWh_mes / (días × 24 h)).
    Fixture nov-2023: inicio=11/01, fin=11/30 → (11/30−11/01).days+1=30 días → 720 h.
    ceil(1_000_000 / 720) = ceil(1388.88…) = 1389 kW.
    """
    # dias = (date(2023,11,30) - date(2023,11,1)).days + 1 = 30 días → 720 horas
    dias = (date(2023, 11, 30) - date(2023, 11, 1)).days + 1
    horas = Decimal(dias * 24)
    esperado = Decimal(math.ceil(KWH / horas))
    assert resultado_un_mes.capacidad_nominal_kw == esperado


def test_capacidad_nominal_sin_facturas():
    """Sin facturas CFE → capacidad es None."""
    r = calcular_cogen([], [], CoGenParams())
    assert r.capacidad_nominal_kw is None


def test_inversion_usd(resultado_un_mes):
    """inversión USD = capacidad × 1400 USD/kW."""
    capacidad = resultado_un_mes.capacidad_nominal_kw
    esperado = (capacidad * Decimal("1400")).quantize(Decimal("0.01"))
    assert resultado_un_mes.inversion_usd == esperado


def test_inversion_mxn(resultado_un_mes):
    """inversión MXN = inversión USD × tipo de cambio (17.50 por defecto)."""
    esperado = (resultado_un_mes.inversion_usd * Decimal("17.50")).quantize(Decimal("0.01"))
    assert resultado_un_mes.inversion_mxn == esperado


def test_inversion_mxn_tipo_cambio_custom():
    """Con tipo_cambio=20.00, inversión MXN refleja el nuevo TC."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams(), tipo_cambio=Decimal("20.00"))
    esperado = (r.inversion_usd * Decimal("20.00")).quantize(Decimal("0.01"))
    assert r.inversion_mxn == esperado


def test_payback_decimal_basico():
    """Payback decimal: inversión=100 000, ahorro=30 000/año.
    Año 1: -100k+30k=-70k. Año 2: -70k+30k=-40k. Año 3: -40k+30k=-10k.
    Año 4: -10k+30k=+20k → payback = 3 + 10000/30000 = 3.33 años.
    """
    p = calcular_payback_decimal(Decimal("100000"), Decimal("30000"), Decimal("30000"))
    assert p == Decimal("3.33")


def test_payback_decimal_mayor_horizonte():
    """Con ahorro muy bajo, payback supera los 15 años → retorna None."""
    assert calcular_payback_decimal(Decimal("1000000"), Decimal("50000"), Decimal("50000")) is None


def test_payback_decimal_ahorro_cero():
    """Ahorro Neto = 0 → no aplica (None)."""
    assert calcular_payback_decimal(Decimal("100000"), Decimal("0"), Decimal("0")) is None


def test_payback_decimal_ahorro_negativo():
    """Ahorro Neto negativo → no aplica (None)."""
    assert calcular_payback_decimal(Decimal("100000"), Decimal("-5000"), Decimal("-5000")) is None


def test_payback_decimal_con_beneficio_fiscal():
    """Payback con flujo_anio_1 distinto al ahorro anual (beneficio fiscal).
    Inversión=70 000 000, flujo_año1=45 000 000, ahorro_anual=24 000 000.
    Año 1: -70M+45M=-25M. Año 2: -25M+24M=-1M. Año 3: -1M+24M=+23M.
    Payback = 2 + 1M/24M ≈ 2.04 años.
    """
    p = calcular_payback_decimal(
        Decimal("70000000"), Decimal("45000000"), Decimal("24000000")
    )
    assert p is not None
    assert Decimal("2.00") < p < Decimal("2.10")


def test_payback_decimal_inversion_cero():
    """Inversión = 0 → payback = 0.00."""
    assert calcular_payback_decimal(Decimal("0"), Decimal("30000"), Decimal("30000")) == Decimal("0")


def test_flujo_acumulado_anio_0():
    """Año 0 del flujo acumulado = -inversión."""
    flujo = calcular_flujo_acumulado(Decimal("100000"), Decimal("30000"))
    assert flujo[0] == Decimal("-100000")


def test_flujo_acumulado_progresion():
    """Cada año suma el ahorro neto al acumulado anterior."""
    flujo = calcular_flujo_acumulado(Decimal("100000"), Decimal("30000"))
    for i in range(1, len(flujo)):
        assert flujo[i] == flujo[i - 1] + Decimal("30000")


def test_flujo_acumulado_longitud():
    """Lista con horizonte=15 tiene 16 elementos (año 0 a año 15)."""
    flujo = calcular_flujo_acumulado(Decimal("100000"), Decimal("30000"))
    assert len(flujo) == 16


# ── Tests de huella de carbono ────────────────────────────────────────────────

FE_ELEC = Decimal("0.435")   # kg CO2 / kWh
FE_GAS  = Decimal("56.1")    # kg CO2 / GJ


def test_co2_actual_huella_con_factores_conocidos():
    """CO2 actual = kWh_anual × fe_elec + GJ_gas_anual × fe_gas."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams(), factor_emision_elec=FE_ELEC, factor_emision_gas=FE_GAS)

    esperado_elec = (KWH * FE_ELEC).quantize(Decimal("0.01"))
    esperado_gas  = (GJ  * FE_GAS ).quantize(Decimal("0.01"))
    assert r.co2_actual_electricidad_kg_anual == esperado_elec
    assert r.co2_actual_gas_kg_anual          == esperado_gas
    assert r.co2_actual_total_kg_anual        == esperado_elec + esperado_gas


def test_co2_proyectado_cobertura_75():
    """Con cobertura 75% la electricidad de red se reduce a 25%; el gas cogen se suma."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    params = CoGenParams(cobertura_electrica=Decimal("0.75"))
    r = calcular_cogen(cfe, gas, params, factor_emision_elec=FE_ELEC, factor_emision_gas=FE_GAS)

    assert r.co2_proyectado_electricidad_kg_anual is not None
    assert r.co2_proyectado_gas_kg_anual          is not None
    assert r.co2_proyectado_total_kg_anual        is not None
    # Electricidad de red = 25% del total
    esperado_elec_proy = (KWH * Decimal("0.25") * FE_ELEC).quantize(Decimal("0.01"))
    assert r.co2_proyectado_electricidad_kg_anual == esperado_elec_proy


def test_co2_reduccion_positiva():
    """La reducción de CO2 debe ser positiva con parámetros estándar."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams(), factor_emision_elec=FE_ELEC, factor_emision_gas=FE_GAS)

    assert r.co2_reduccion_kg_anual      is not None
    assert r.co2_reduccion_kg_anual      > 0
    assert r.co2_reduccion_porcentaje    > 0


def test_co2_reduccion_cero_con_cobertura_cero():
    """Cobertura 0% → sin cogen → reducción ≈ 0 (misma huella proyectada)."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    params = CoGenParams(cobertura_electrica=Decimal("0"))
    r = calcular_cogen(cfe, gas, params, factor_emision_elec=FE_ELEC, factor_emision_gas=FE_GAS)

    assert r.co2_reduccion_kg_anual == Decimal("0.00") or r.co2_reduccion_kg_anual < Decimal("0.01")
    assert r.co2_proyectado_total_kg_anual == r.co2_actual_total_kg_anual


def test_co2_calor_recuperado_supera_caldera():
    """Si calor recuperado > GJ caldera actual, gj_caldera_con_cogen → 0 (no negativo)."""
    # Gas muy bajo (10 GJ), calor recuperado con cobertura 100% será mayor
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, Decimal("10"), PRECIO_GJ)]
    params = CoGenParams(cobertura_electrica=Decimal("1.0"))
    r = calcular_cogen(cfe, gas, params, factor_emision_elec=FE_ELEC, factor_emision_gas=FE_GAS)

    # El total proyectado debe ser no negativo
    assert r.co2_proyectado_gas_kg_anual          >= 0
    assert r.co2_proyectado_electricidad_kg_anual == Decimal("0.00")


def test_co2_sin_facturas_cfe_es_none():
    """Sin facturas CFE no hay meses → campos CO2 son None."""
    r = calcular_cogen([], [], CoGenParams(), factor_emision_elec=FE_ELEC, factor_emision_gas=FE_GAS)

    assert r.co2_actual_total_kg_anual     is None
    assert r.co2_proyectado_total_kg_anual is None
    assert r.co2_reduccion_kg_anual        is None


def test_co2_none_sin_factores_emision():
    """Sin factores de emisión los campos CO2 quedan None (backward-compat)."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())

    assert r.co2_actual_total_kg_anual     is None
    assert r.co2_proyectado_total_kg_anual is None
    assert r.co2_reduccion_kg_anual        is None


# ── Tests: horas del mes dinámicas ────────────────────────────────────────────

def test_capacidad_nominal_31_dias():
    """Enero: inicio=1/1, fin=1/31 → (fin−inicio).days+1=31 días → 744 h. capacidad = ceil(kWh / 744)."""
    from models.cfe_invoice import CFEConsumoHorario

    kwh_jan = Decimal("744000")  # 1000 kWh/h × 744 h
    tercio = kwh_jan / 3
    inicio = date(2024, 1, 1)
    fin    = date(2024, 1, 31)   # 30 días de diferencia (fin-inicio)
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    cfe_jan = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=Decimal("3000000"), cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=Decimal("3000000"), iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=Decimal("3000000"),
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=Decimal("3000000"), pdf_path="test.pdf",
    )
    gas = [_gas(2024, 1, Decimal("100000"), PRECIO_GJ)]
    r = calcular_cogen([cfe_jan], gas, CoGenParams())
    # dias = (1/31 - 1/1).days + 1 = 31 días → 744 h; ceil(744000/744) = 1000
    dias = (fin - inicio).days + 1
    horas = Decimal(dias * 24)
    esperado = Decimal(math.ceil(kwh_jan / horas))
    assert r.capacidad_nominal_kw == esperado


def test_capacidad_nominal_28_dias():
    """Febrero no bisiesto: inicio=2/1, fin=2/28 → (fin−inicio).days+1=28 días → 672 h. Menor capacidad que con 720h."""
    from models.cfe_invoice import CFEConsumoHorario

    kwh_feb = Decimal("648000")  # 1000 kWh/h × 648 h
    tercio = kwh_feb / 3
    inicio = date(2023, 2, 1)
    fin    = date(2023, 2, 28)   # 27 días de diferencia
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    cfe_feb = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=Decimal("2000000"), cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=Decimal("2000000"), iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=Decimal("2000000"),
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=Decimal("2000000"), pdf_path="test.pdf",
    )
    gas = [_gas(2023, 2, Decimal("50000"), PRECIO_GJ)]
    r = calcular_cogen([cfe_feb], gas, CoGenParams())
    dias = (fin - inicio).days + 1  # 28 días
    horas = Decimal(dias * 24)
    esperado = Decimal(math.ceil(kwh_feb / horas))
    assert r.capacidad_nominal_kw == esperado


# ── Tests: Ahorro Otros Servicios (4to componente GDMTH) ─────────────────────

def test_ahorro_otros_servicios_con_componentes_mem():
    """Con Transmisión + CENACE + SCnMEM en la factura, ahorro_otros_servicios > 0."""
    from models.cfe_invoice import MEMComponente

    # Transmisión=50000, CENACE=20000, SCnMEM=10000 → cargo_otros=80000
    # kwh_total_orig = KWH = 1_000_000
    # precio_otros = 80000 / 1000000 = 0.08 MXN/kWh
    # kwh_cubiertos = 750000 (cobertura 75%)
    # ahorro_otros = 750000 × 0.08 = 60000 MXN
    tercio = KWH / 3
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    inicio = date(2023, 11, 1)
    fin    = date(2023, 11, 30)
    cfe_con_otros = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[
            MEMComponente("Transmisión", Decimal("0"), Decimal("0"), Decimal("50000"), Decimal("50000")),
            MEMComponente("CENACE",      Decimal("0"), Decimal("0"), Decimal("20000"), Decimal("20000")),
            MEMComponente("SCnMEM",      Decimal("0"), Decimal("0"), Decimal("10000"), Decimal("10000")),
        ],
        cargo_fijo_mxn=Decimal("0"), energia_total_mxn=FACTURACION,
        cargo_factor_potencia_mxn=Decimal("0"), subtotal_mxn=FACTURACION,
        iva_mxn=Decimal("0"), facturacion_periodo_mxn=FACTURACION,
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=FACTURACION, pdf_path="test.pdf",
    )
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen([cfe_con_otros], gas, CoGenParams())
    m = r.meses[0]

    assert m.cargo_otros_total_mxn == Decimal("80000")
    assert m.precio_otros_mxn_kwh  == Decimal("0.0800")  # 80000/1000000
    assert m.ahorro_otros_servicios_mes_mxn == Decimal("60000.00")  # 750000 × 0.08
    assert r.ahorro_otros_servicios_anual_mxn == m.ahorro_otros_servicios_mes_mxn


def test_ahorro_otros_servicios_cero_sin_componentes():
    """Sin Transmisión/CENACE/SCnMEM en la factura, ahorro_otros_servicios = 0."""
    cfe = [_cfe(2023, 11, KWH, FACTURACION)]
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen(cfe, gas, CoGenParams())
    m = r.meses[0]

    assert m.cargo_otros_total_mxn == Decimal("0")
    assert m.precio_otros_mxn_kwh  == Decimal("0")
    assert m.ahorro_otros_servicios_mes_mxn == Decimal("0")


def test_capacidad_nominal_dias_calendario():
    """Factura cross-mes (2018-09-30 → 2018-10-31, 32 días facturados).
    mes_asociado → octubre 2018 → calendar.monthrange = 31 días.
    Incorrecto (días facturación): ceil(536196 / (32×24)) = ceil(698.17) = 699.
    Correcto  (días calendario):  ceil(536196 / (31×24)) = ceil(720.69) = 721.
    """
    kwh_total = Decimal("536196")
    tercio = kwh_total / 3
    inicio = date(2018, 9, 30)
    fin    = date(2018, 10, 31)
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    cfe_cross = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=Decimal("1000000"), cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=Decimal("1000000"), iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=Decimal("1000000"),
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=Decimal("1000000"), pdf_path="test.pdf",
    )
    r = calcular_cogen([cfe_cross], [], CoGenParams())
    assert r.capacidad_nominal_kw == Decimal("721"), (
        f"Esperado 721 kW (días calendario oct-2018=31), obtenido {r.capacidad_nominal_kw}"
    )


def test_capacidad_nominal_periodo_exacto_mes():
    """Enero 2024 (1/1→1/31): periodo alineado con el mes.
    calendar.monthrange(2024,1)[1] = 31 días → 744 h.
    ceil(744000 / 744) = ceil(1000.0) = 1000 kW.
    """
    kwh_jan = Decimal("744000")
    tercio = kwh_jan / 3
    inicio = date(2024, 1, 1)
    fin    = date(2024, 1, 31)
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    cfe_jan = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=Decimal("2000000"), cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=Decimal("2000000"), iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=Decimal("2000000"),
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=Decimal("2000000"), pdf_path="test.pdf",
    )
    r = calcular_cogen([cfe_jan], [], CoGenParams())
    assert r.capacidad_nominal_kw == Decimal("1000")


def test_capacidad_nominal_multiples_facturas():
    """Con 3 facturas, capacidad_nominal_kw es el MAX de las tres.
    - Ene-2024 (31 días):  744000 kWh → ceil(744000/744) = 1000 kW  ← máximo
    - Feb-2023 (28 días):  504000 kWh → ceil(504000/672) = 750 kW
    - Nov-2023 (30 días):  540000 kWh → ceil(540000/720) = 750 kW
    """
    def _cfe_directo(kwh: Decimal, inicio: date, fin: date) -> CFEInvoice:
        tercio = kwh / 3
        periodos = [
            CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
            CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
            CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
        ]
        return CFEInvoice(
            uuid_cfdi=None, folio="F1", serie=None,
            fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
            fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
            numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
            multiplicador=1, carga_conectada_kw=Decimal("1000"),
            demanda_contratada_kw=Decimal("1000"), periodos=periodos,
            kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
            componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
            energia_total_mxn=Decimal("1000000"), cargo_factor_potencia_mxn=Decimal("0"),
            subtotal_mxn=Decimal("1000000"), iva_mxn=Decimal("0"),
            facturacion_periodo_mxn=Decimal("1000000"),
            derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
            total_mxn=Decimal("1000000"), pdf_path="test.pdf",
        )

    facturas = [
        _cfe_directo(Decimal("744000"), date(2024, 1, 1),  date(2024, 1, 31)),   # 1000 kW
        _cfe_directo(Decimal("504000"), date(2023, 2, 1),  date(2023, 2, 28)),   # 750 kW
        _cfe_directo(Decimal("540000"), date(2023, 11, 1), date(2023, 11, 30)),  # 750 kW
    ]
    r = calcular_cogen(facturas, [], CoGenParams())
    assert r.capacidad_nominal_kw == Decimal("1000")


def test_ahorro_otros_servicios_incluido_en_total():
    """Ahorro eléctrico total incluye Ahorro Otros Servicios."""
    from models.cfe_invoice import MEMComponente

    tercio = KWH / 3
    periodos = [
        CFEConsumoHorario("base",       tercio, Decimal("100"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", tercio, Decimal("100"), Decimal("1.20")),
        CFEConsumoHorario("punta",      tercio, Decimal("100"), Decimal("1.50")),
    ]
    inicio = date(2023, 11, 1)
    fin    = date(2023, 11, 30)
    cfe_con_otros = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("100"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[
            MEMComponente("Transmisión", Decimal("0"), Decimal("0"), Decimal("40000"), Decimal("40000")),
            MEMComponente("CENACE",      Decimal("0"), Decimal("0"), Decimal("15000"), Decimal("15000")),
        ],
        cargo_fijo_mxn=Decimal("0"), energia_total_mxn=FACTURACION,
        cargo_factor_potencia_mxn=Decimal("0"), subtotal_mxn=FACTURACION,
        iva_mxn=Decimal("0"), facturacion_periodo_mxn=FACTURACION,
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=FACTURACION, pdf_path="test.pdf",
    )
    gas = [_gas(2023, 11, GJ, PRECIO_GJ)]
    r = calcular_cogen([cfe_con_otros], gas, CoGenParams())
    m = r.meses[0]

    # Invariante: ahorro_electricidad = suma de los 4 componentes
    assert m.ahorro_electricidad_mxn == (
        m.ahorro_energia_mes_mxn + m.ahorro_capacidad_mes_mxn
        + m.ahorro_distribucion_mes_mxn + m.ahorro_otros_servicios_mes_mxn
    )
    # Ahorro otros > 0 porque hay Transmisión y CENACE
    assert m.ahorro_otros_servicios_mes_mxn > Decimal("0")
