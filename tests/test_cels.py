# tests/test_cels.py
from decimal import Decimal
import pytest
from calc.cels import calcular_cels, CELsResultado


# ── Helper ───────────────────────────────────────────────────────────────────

def _base_args(**overrides):
    """Argumentos base para un cliente tipo IBERICA TILES con datos completos."""
    args = {
        "kwh_cubiertos_anual": Decimal("3_600_000"),   # 3600 MWh/año
        "gj_gas_cogen_pci_anual": Decimal("32_400"),   # GJ PCI
        "calor_recuperado_gj_anual": Decimal("9_000"), # GJ calor recuperado
        "capacidad_nominal_kw": Decimal("5000"),       # 5 MW
        "medio_termico": "vapor_agua",
        "nivel_tension_kv": "1_34",
        "altitud_msnm": 340,
        "tipo_motor": "combustion_interna",
    }
    args.update(overrides)
    return args


# ── Test: cliente con campos incompletos ─────────────────────────────────────

def test_campos_vacios_devuelve_none():
    """Si cualquier campo del cliente es None, devuelve None."""
    result = calcular_cels(
        kwh_cubiertos_anual=Decimal("1000000"),
        gj_gas_cogen_pci_anual=Decimal("10000"),
        calor_recuperado_gj_anual=Decimal("2000"),
        capacidad_nominal_kw=Decimal("5000"),
        medio_termico=None,
        nivel_tension_kv="1_34",
        altitud_msnm=500,
        tipo_motor="combustion_interna",
    )
    assert result is None


def test_nivel_tension_none_devuelve_none():
    result = calcular_cels(**_base_args(nivel_tension_kv=None))
    assert result is None


def test_sin_capacidad_devuelve_none():
    """Sin capacidad instalada ni nominal, devuelve None."""
    result = calcular_cels(**_base_args(capacidad_nominal_kw=None))
    assert result is None


# ── Test: selección de tabla RefE ─────────────────────────────────────────────

def test_refe_tabla_principal_30mw():
    """30 MW a 340 msnm → tabla principal → RefE = 51%."""
    result = calcular_cels(**_base_args(
        capacidad_nominal_kw=Decimal("30000"),  # exactamente 30 MW
        altitud_msnm=2000,                      # > 1500 pero cap = 30000 (no < 30000)
        tipo_motor="combustion_interna",
    ))
    assert result is not None
    assert result.RefE == Decimal("0.51")


def test_refe_tabla_altitud_6mw():
    """6 MW, altitud 2000m, motor combustion_interna → tabla altitud → RefE = 45%."""
    result = calcular_cels(**_base_args(
        capacidad_nominal_kw=Decimal("6000"),
        altitud_msnm=2000,
        tipo_motor="combustion_interna",
    ))
    assert result is not None
    assert result.RefE == Decimal("0.45")


def test_refe_tabla_principal_turbina_baja_altitud():
    """Turbina a 500 msnm → tabla principal (altitud ≤ 1500)."""
    result = calcular_cels(**_base_args(
        capacidad_nominal_kw=Decimal("6000"),
        altitud_msnm=500,
        tipo_motor="turbina_gas",
    ))
    assert result is not None
    assert result.RefE == Decimal("0.47")


# ── Test: RefH según medio_termico ───────────────────────────────────────────

def test_refh_vapor_agua():
    result = calcular_cels(**_base_args(medio_termico="vapor_agua"))
    assert result is not None
    assert result.RefH == Decimal("0.90")


def test_refh_gases_combustion():
    result = calcular_cels(**_base_args(medio_termico="gases_combustion"))
    assert result is not None
    assert result.RefH == Decimal("0.82")


# ── Test: fp según nivel_tension_kv ─────────────────────────────────────────

def test_fp_lt1():
    result = calcular_cels(**_base_args(nivel_tension_kv="lt_1"))
    assert result is not None
    assert result.fp == Decimal("0.91")


def test_fp_gt400():
    result = calcular_cels(**_base_args(nivel_tension_kv="gt_400"))
    assert result is not None
    assert result.fp == Decimal("1.00")


# ── Test: H=0 → no eficiente ────────────────────────────────────────────────

def test_h_cero_no_eficiente():
    """Sin calor recuperado, AEP probablemente negativo, ELC ≤ 0, no eficiente."""
    result = calcular_cels(**_base_args(calor_recuperado_gj_anual=Decimal("0")))
    assert result is not None
    assert not result.es_eficiente
    assert result.cels_mwh_anual == Decimal("0")


# ── Test: bug PCI/PCS ────────────────────────────────────────────────────────

def test_f_usa_pci_sin_factor_1_11():
    """F debe calcularse con gj_gas_cogen_pci_anual (sin factor 1.11).

    Verificamos que F_mwh = gj_gas_cogen_pci_anual * 0.277778.
    Si el módulo aplicara internamente 1.11, F sería 11% mayor.
    """
    gj_pci = Decimal("10000")
    result = calcular_cels(**_base_args(
        gj_gas_cogen_pci_anual=gj_pci,
    ))
    assert result is not None
    # F_mwh = 10000 * 277.778 / 1000 = 2777.78 MWh
    expected_F = (gj_pci * Decimal("277.778") / Decimal("1000")).quantize(Decimal("0.01"))
    assert result.F_mwh == expected_F


# ── Test: lógica híbrida de capacidad ────────────────────────────────────────

def test_capacidad_instalada_tiene_prioridad():
    """Si capacidad_instalada_kw está llena, se usa sobre capacidad_nominal_kw."""
    result = calcular_cels(**_base_args(
        capacidad_nominal_kw=Decimal("5000"),   # 5 MW → RefE 44%
        capacidad_instalada_kw=200.0,            # 0.2 MW → RefE 40%
    ))
    assert result is not None
    assert not result.capacidad_es_estimada
    assert result.RefE == Decimal("0.40")


def test_capacidad_nominal_como_fallback():
    """Si capacidad_instalada_kw es None, se usa capacidad_nominal_kw."""
    result = calcular_cels(**_base_args(
        capacidad_nominal_kw=Decimal("5000"),
        capacidad_instalada_kw=None,
    ))
    assert result is not None
    assert result.capacidad_es_estimada


# ── Test: resultado es_eficiente con datos realistas ─────────────────────────

def test_cogen_eficiente_con_datos_iberica():
    """Con datos tipo IBERICA TILES, se espera cogeneración eficiente."""
    result = calcular_cels(**_base_args())
    assert result is not None
    assert isinstance(result, CELsResultado)
    # ELC debe ser positivo para que sea eficiente
    assert result.ELC > Decimal("0")
    assert result.es_eficiente
    assert result.cels_mwh_anual > Decimal("0")
