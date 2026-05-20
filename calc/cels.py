# calc/cels.py
"""
Cálculo de Certificados de Energías Limpias (CELs) según metodología CRE Caso I.
Referencia: RES/1838/2016 de la Comisión Reguladora de Energía.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

_CUATRO = Decimal("0.0001")
_DOS = Decimal("0.01")
_CERO = Decimal("0")

# Conversión GJ → MWh
_GJ_A_MWH = Decimal("277.778")

# Tablas de RefE (eficiencia eléctrica de referencia)
# Cada entrada: (límite_inferior_MW_inclusive, RefE_decimal)
# La tabla termina con el último tramo (sin límite superior).
_REFE_TABLA_PRINCIPAL = [
    (Decimal("0"),    Decimal("0.40")),   # < 0.5 MW
    (Decimal("0.5"),  Decimal("0.44")),   # 0.5 ≤ cap < 6
    (Decimal("6"),    Decimal("0.47")),   # 6 ≤ cap < 15
    (Decimal("15"),   Decimal("0.48")),   # 15 ≤ cap < 30
    (Decimal("30"),   Decimal("0.51")),   # 30 ≤ cap < 150
    (Decimal("150"),  Decimal("0.52")),   # 150 ≤ cap < 300
    (Decimal("300"),  Decimal("0.53")),   # cap ≥ 300
]

_REFE_TABLA_ALTITUD = [
    (Decimal("0"),    Decimal("0.40")),   # < 0.5 MW
    (Decimal("0.5"),  Decimal("0.44")),   # 0.5 ≤ cap < 6
    (Decimal("6"),    Decimal("0.45")),   # 6 ≤ cap < 15
    (Decimal("15"),   Decimal("0.45")),   # 15 ≤ cap < 30 (table ends at 30)
]

_REFE_ALTITUD_MOTORES = {"combustion_interna", "turbina_gas"}

REFH_VAPOR = Decimal("0.90")
REFH_GASES = Decimal("0.82")


def _calcular_ref_h(medio_termico_vapor_pct: int) -> Decimal:
    """RefH ponderado según porcentaje de vapor (0-100) vs gases de combustión."""
    pct = Decimal(medio_termico_vapor_pct) / Decimal("100")
    return pct * REFH_VAPOR + (Decimal("1") - pct) * REFH_GASES

_FP = {
    "lt_1":    Decimal("0.91"),
    "1_34":    Decimal("0.94"),
    "69_85":   Decimal("0.96"),
    "115_230": Decimal("0.98"),
    "gt_400":  Decimal("1.00"),
}


def _refe(capacidad_kw: Decimal, altitud_msnm: int, tipo_motor: str) -> Decimal:
    """Selecciona RefE según tabla principal o alternativa."""
    capacidad_mw = capacidad_kw / Decimal("1000")
    usar_altitud = (
        altitud_msnm > 1500
        and capacidad_kw < Decimal("30000")
        and tipo_motor in _REFE_ALTITUD_MOTORES
    )
    tabla = _REFE_TABLA_ALTITUD if usar_altitud else _REFE_TABLA_PRINCIPAL
    ref = tabla[0][1]
    for limite, valor in tabla:
        if capacidad_mw >= limite:
            ref = valor
    return ref


@dataclass
class CELsResultado:
    """Resultado del cálculo de CELs según CRE Caso I."""
    # Capacidad y origen
    capacidad_kw: Decimal
    capacidad_es_estimada: bool  # Siempre True: la capacidad usada es la calculada de facturas
    # Datos del cliente usados
    medio_termico: str | None
    nivel_tension_kv: str
    altitud_msnm: int
    tipo_motor: str
    # Variables de operación (anuales, en MWh)
    E_mwh: Decimal   # electricidad neta generada
    F_mwh: Decimal   # combustibles fósiles en PCI
    H_mwh: Decimal   # calor útil
    # Variables de referencia
    RefE: Decimal
    RefH: Decimal
    fp: Decimal
    RefE_prima: Decimal
    # Resultados intermedios
    Fh: Decimal
    Fe: Decimal
    EE: Decimal | None       # eficiencia eléctrica (None si Fe ≤ 0)
    EP: Decimal
    AEP: Decimal
    APEP: Decimal | None     # None si EP ≤ 0
    AREL: Decimal | None     # None si Fe ≤ 0
    ELC: Decimal
    porcentaje_ELC: Decimal | None  # None si E ≤ 0
    es_eficiente: bool
    cels_mwh_anual: Decimal  # ELC si eficiente, 0 si no


def calcular_cels(
    kwh_cubiertos_anual: Decimal,
    gj_gas_cogen_pci_anual: Decimal,
    calor_recuperado_gj_anual: Decimal,
    capacidad_nominal_kw: Decimal | None,
    medio_termico: str | None,
    nivel_tension_kv: str | None,
    altitud_msnm: int | None,
    tipo_motor: str | None,
    medio_termico_vapor_pct: int | None = None,
) -> CELsResultado | None:
    """Calcula CELs según CRE Caso I. Devuelve None si faltan datos del cliente.

    La capacidad usada es capacidad_nominal_kw (calculada con ceil desde facturas históricas).
    medio_termico_vapor_pct (0-100) define el mix de medios: RefH ponderado entre vapor (0.90)
    y gases de combustión (0.82). None → sin especificar → devuelve None.
    """
    # Validar que todos los campos del cliente estén presentes
    if any(v is None for v in [nivel_tension_kv, altitud_msnm, tipo_motor]):
        return None
    if medio_termico_vapor_pct is None:
        return None

    # Determinar capacidad a usar
    if capacidad_nominal_kw is None or capacidad_nominal_kw <= 0:
        return None
    capacidad_kw = capacidad_nominal_kw
    capacidad_es_estimada = True

    refh = _calcular_ref_h(medio_termico_vapor_pct)
    fp = _FP.get(nivel_tension_kv)
    if fp is None:
        return None

    ref_e = _refe(capacidad_kw, altitud_msnm, tipo_motor)
    ref_e_prima = (ref_e * fp).quantize(_CUATRO, ROUND_HALF_UP)

    # Variables de operación en MWh
    E = (kwh_cubiertos_anual / Decimal("1000")).quantize(_DOS, ROUND_HALF_UP)
    F = (gj_gas_cogen_pci_anual * _GJ_A_MWH / Decimal("1000")).quantize(_DOS, ROUND_HALF_UP)
    H = (calor_recuperado_gj_anual * _GJ_A_MWH / Decimal("1000")).quantize(_DOS, ROUND_HALF_UP)

    Fh = (H / refh).quantize(_DOS, ROUND_HALF_UP)
    Fe = (F - Fh).quantize(_DOS, ROUND_HALF_UP)
    EE = (E / Fe).quantize(_CUATRO, ROUND_HALF_UP) if Fe > _CERO else None

    EP_raw = _CERO
    if ref_e_prima > _CERO:
        EP_raw += E / ref_e_prima
    EP_raw += H / refh
    EP = EP_raw.quantize(_DOS, ROUND_HALF_UP)

    AEP = (EP - F).quantize(_DOS, ROUND_HALF_UP)
    APEP = (AEP / EP).quantize(_CUATRO, ROUND_HALF_UP) if EP > _CERO else None
    AREL = (AEP / Fe).quantize(_CUATRO, ROUND_HALF_UP) if Fe > _CERO else None
    ELC = (AEP * ref_e).quantize(_DOS, ROUND_HALF_UP)
    porcentaje_ELC = (ELC / E).quantize(_CUATRO, ROUND_HALF_UP) if E > _CERO else None

    es_eficiente = ELC > _CERO
    cels_mwh = ELC if es_eficiente else _CERO

    return CELsResultado(
        capacidad_kw=capacidad_kw,
        capacidad_es_estimada=capacidad_es_estimada,
        medio_termico=medio_termico,
        nivel_tension_kv=nivel_tension_kv,
        altitud_msnm=altitud_msnm,
        tipo_motor=tipo_motor,
        E_mwh=E,
        F_mwh=F,
        H_mwh=H,
        RefE=ref_e,
        RefH=refh,
        fp=fp,
        RefE_prima=ref_e_prima,
        Fh=Fh,
        Fe=Fe,
        EE=EE,
        EP=EP,
        AEP=AEP,
        APEP=APEP,
        AREL=AREL,
        ELC=ELC,
        porcentaje_ELC=porcentaje_ELC,
        es_eficiente=es_eficiente,
        cels_mwh_anual=cels_mwh,
    )
