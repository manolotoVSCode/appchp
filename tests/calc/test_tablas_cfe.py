# tests/calc/test_tablas_cfe.py
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

import pytest

from calc.historico import calcular_tablas_cfe
from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mem(nombre: str, cargo_dem: Decimal = Decimal("0")) -> MEMComponente:
    return MEMComponente(
        nombre=nombre,
        cargo_fijo_mxn=Decimal("0"),
        cargo_demanda_mxn=cargo_dem,
        cargo_energia_mxn=Decimal("0"),
        importe_mxn=cargo_dem,
    )


def _cfe(
    year: int,
    month: int,
    kwh_base: Decimal,
    kwh_inter: Decimal,
    kwh_punta: Decimal,
    kw_base: Decimal,
    kw_inter: Decimal,
    kw_punta: Decimal,
    cu_base: Decimal,
    cu_inter: Decimal,
    cu_punta: Decimal,
    subtotal: Decimal,
    cargo_fp: Decimal = Decimal("0"),
    costo_dist: Decimal = Decimal("0"),
    costo_cap: Decimal = Decimal("0"),
    dias_override: int | None = None,
) -> CFEInvoice:
    """Factura CFE sintética con periodo completo del mes (o dias_override días)."""
    ultimo = dias_override if dias_override else calendar.monthrange(year, month)[1]
    inicio = date(year, month, 1)
    fin = date(year, month, ultimo)
    periodos = [
        CFEConsumoHorario("base",       kwh_base,  kw_base,  cu_base),
        CFEConsumoHorario("intermedio", kwh_inter, kw_inter, cu_inter),
        CFEConsumoHorario("punta",      kwh_punta, kw_punta, cu_punta),
    ]
    componentes = [
        _mem("Suministro"),
        _mem("Distribución",  costo_dist),
        _mem("Transmisión"),
        _mem("CENACE"),
        _mem("Generación B"),
        _mem("Generación I"),
        _mem("Generación P"),
        _mem("Capacidad",     costo_cap),
        _mem("SCnMEM"),
    ]
    return CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("500"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=componentes,
        cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=subtotal,
        cargo_factor_potencia_mxn=cargo_fp,
        subtotal_mxn=subtotal,
        iva_mxn=(subtotal * Decimal("0.16")).quantize(Decimal("0.01")),
        facturacion_periodo_mxn=(subtotal * Decimal("1.16")).quantize(Decimal("0.01")),
        derecho_alumbrado_publico_mxn=Decimal("0"),
        credito_aplicado_mxn=Decimal("0"),
        total_mxn=(subtotal * Decimal("1.16")).quantize(Decimal("0.01")),
        pdf_path="test.pdf",
    )


# Factura base reutilizable en varios tests
INV_ENE = _cfe(
    2024, 1,
    kwh_base=Decimal("600000"), kwh_inter=Decimal("300000"), kwh_punta=Decimal("100000"),
    kw_base=Decimal("900"),     kw_inter=Decimal("600"),     kw_punta=Decimal("500"),
    cu_base=Decimal("1.00"),    cu_inter=Decimal("2.00"),    cu_punta=Decimal("5.00"),
    subtotal=Decimal("2500000"),
    cargo_fp=Decimal("50000"),
    costo_dist=Decimal("400000"), costo_cap=Decimal("300000"),
)

INV_FEB = _cfe(
    2024, 2,
    kwh_base=Decimal("500000"), kwh_inter=Decimal("250000"), kwh_punta=Decimal("80000"),
    kw_base=Decimal("850"),     kw_inter=Decimal("580"),     kw_punta=Decimal("470"),
    cu_base=Decimal("1.10"),    cu_inter=Decimal("2.10"),    cu_punta=Decimal("5.20"),
    subtotal=Decimal("2200000"),
    cargo_fp=Decimal("40000"),
    costo_dist=Decimal("350000"), costo_cap=Decimal("280000"),
)


# ── Estructura y longitud ─────────────────────────────────────────────────────

def test_estructura_keys():
    h = calcular_tablas_cfe([INV_ENE])
    assert set(h.keys()) == {"consumos_demandas", "costos_detallados", "indicadores"}


def test_longitud_con_anual():
    """Con N facturas, cada tabla tiene N+1 filas (N meses + ANUAL)."""
    h = calcular_tablas_cfe([INV_ENE, INV_FEB])
    assert len(h["consumos_demandas"]) == 3
    assert len(h["costos_detallados"]) == 3
    assert len(h["indicadores"]) == 3


def test_ultima_fila_es_anual():
    h = calcular_tablas_cfe([INV_ENE, INV_FEB])
    assert h["consumos_demandas"][-1]["mes"] == "ANUAL"
    assert h["costos_detallados"][-1]["mes"] == "ANUAL"
    assert h["indicadores"][-1]["mes"] == "ANUAL"


def test_lista_vacia_solo_anual():
    h = calcular_tablas_cfe([])
    assert len(h["consumos_demandas"]) == 1
    assert h["consumos_demandas"][0]["mes"] == "ANUAL"


# ── Tabla 1: Consumos y Demandas ─────────────────────────────────────────────

def test_consumos_kwh_correctos():
    h = calcular_tablas_cfe([INV_ENE])
    f = h["consumos_demandas"][0]
    assert f["kwh_base"]  == 600000.0
    assert f["kwh_inter"] == 300000.0
    assert f["kwh_punta"] == 100000.0
    assert f["kwh_total"] == 1000000.0


def test_demandas_kw_correctas():
    h = calcular_tablas_cfe([INV_ENE])
    f = h["consumos_demandas"][0]
    assert f["kw_base"]  == 900.0
    assert f["kw_inter"] == 600.0
    assert f["kw_punta"] == 500.0


def test_anual_kw_son_none():
    """Las demandas máximas no se suman en la fila ANUAL."""
    h = calcular_tablas_cfe([INV_ENE])
    anual = h["consumos_demandas"][-1]
    assert anual["kw_base"]  is None
    assert anual["kw_inter"] is None
    assert anual["kw_punta"] is None


def test_anual_kwh_suma_dos_meses():
    h = calcular_tablas_cfe([INV_ENE, INV_FEB])
    anual = h["consumos_demandas"][-1]
    assert anual["kwh_base"]  == 600000.0 + 500000.0
    assert anual["kwh_inter"] == 300000.0 + 250000.0
    assert anual["kwh_punta"] == 100000.0 +  80000.0
    assert anual["kwh_total"] == 1000000.0 + 830000.0


# ── Tabla 2: Costos Detallados ────────────────────────────────────────────────

def test_costo_energia_por_horario():
    h = calcular_tablas_cfe([INV_ENE])
    f = h["costos_detallados"][0]
    assert abs(f["ce_base"]  - 600000 * 1.00) < 0.01
    assert abs(f["ce_inter"] - 300000 * 2.00) < 0.01
    assert abs(f["ce_punta"] - 100000 * 5.00) < 0.01
    assert abs(f["ce_total"] - (600000 + 600000 + 500000)) < 0.01


def test_costos_distribucion_capacidad():
    h = calcular_tablas_cfe([INV_ENE])
    f = h["costos_detallados"][0]
    assert f["costo_dist"] == 400000.0
    assert f["costo_cap"]  == 300000.0
    assert f["costo_dem"]  == 700000.0


def test_cargo_factor_potencia_y_subtotal():
    h = calcular_tablas_cfe([INV_ENE])
    f = h["costos_detallados"][0]
    assert f["cargo_fp"] == 50000.0
    assert f["subtotal"] == 2500000.0


def test_anual_costos_suma():
    h = calcular_tablas_cfe([INV_ENE, INV_FEB])
    anual = h["costos_detallados"][-1]
    assert abs(anual["subtotal"]  - (2500000 + 2200000)) < 0.01
    assert abs(anual["cargo_fp"]  - (50000 + 40000)) < 0.01
    assert abs(anual["costo_dist"]- (400000 + 350000)) < 0.01


# ── Tabla 3: Indicadores ──────────────────────────────────────────────────────

def test_costo_unit_total():
    """$/kWh = subtotal / kwh_total."""
    h = calcular_tablas_cfe([INV_ENE])
    f = h["indicadores"][0]
    esperado = round(2500000 / 1000000, 2)  # 2.50
    assert f["costo_unit"] == esperado


def test_pct_energia():
    """pct_energia = round(ce_total / subtotal * 100)."""
    h = calcular_tablas_cfe([INV_ENE])
    f = h["indicadores"][0]
    ce_total = 600000 * 1.00 + 300000 * 2.00 + 100000 * 5.00
    esperado = round(ce_total / 2500000 * 100)
    assert f["pct_energia"] == esperado


def test_pct_demanda():
    """pct_demanda = round(costo_dem / subtotal * 100)."""
    h = calcular_tablas_cfe([INV_ENE])
    f = h["indicadores"][0]
    esperado = round(700000 / 2500000 * 100)
    assert f["pct_demanda"] == esperado


def test_demanda_maxima_es_max_de_tres():
    """La demanda máxima usada para factor de carga es el máximo de base/inter/punta.

    Aquí kw_base (900) > kw_punta (500), así que debe usarse 900, no 500.
    INV_ENE: periodo 2024-01-01 → 2024-01-31 = 30 días (fin-inicio) = 720 h.
    """
    h = calcular_tablas_cfe([INV_ENE])
    f = h["indicadores"][0]
    horas = 30 * 24  # (Jan 31 - Jan 1).days = 30
    dem_prom = round(1000000 / horas, 1)
    esperado_fc = round(dem_prom / 900 * 100)  # usa kw_base=900, no kw_punta=500
    assert f["factor_carga"] == esperado_fc
    # Verificar que sería distinto si usáramos kw_punta
    factor_incorrecto = round(dem_prom / 500 * 100)
    assert f["factor_carga"] != factor_incorrecto


def test_demanda_promedio_usa_horas_reales():
    """demanda_prom = kwh_total / (dias × 24).

    INV_ENE: periodo 2024-01-01 → 2024-01-31.
    (Jan 31 - Jan 1).days = 30 días = 720 horas.
    """
    h = calcular_tablas_cfe([INV_ENE])
    f = h["indicadores"][0]
    esperado = round(1000000 / (30 * 24), 1)  # 30 días, no 31
    assert f["demanda_prom"] == esperado


def test_demanda_promedio_febrero_28_dias():
    """Febrero 2024 bisiesto: periodo 2024-02-01 → 2024-02-29.

    (Feb 29 - Feb 1).days = 28 días = 672 horas.
    """
    h = calcular_tablas_cfe([INV_FEB])
    f = h["indicadores"][0]
    esperado = round(830000 / (28 * 24), 1)  # 28 días, no 29
    assert f["demanda_prom"] == esperado


def test_manejo_periodo_faltante():
    """Factura sin periodo punta devuelve 0.0 sin excepción."""
    inicio = date(2024, 3, 1)
    fin = date(2024, 3, 31)
    periodos_sin_punta = [
        CFEConsumoHorario("base",       Decimal("600000"), Decimal("900"), Decimal("1.00")),
        CFEConsumoHorario("intermedio", Decimal("300000"), Decimal("600"), Decimal("2.00")),
    ]
    inv = CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos_sin_punta,
        kw_max=Decimal("500"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=Decimal("1500000"), cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=Decimal("1500000"), iva_mxn=Decimal("240000"),
        facturacion_periodo_mxn=Decimal("1740000"),
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=Decimal("1740000"), pdf_path="test.pdf",
    )
    h = calcular_tablas_cfe([inv])
    f_cd = h["consumos_demandas"][0]
    assert f_cd["kwh_punta"] == 0.0
    assert f_cd["kw_punta"]  == 0.0
    f_cd_tab2 = h["costos_detallados"][0]
    assert f_cd_tab2["ce_punta"] == 0.0


def test_mes_prorrateado_usa_720_horas():
    """Factura de 15 días se proratea y debe usar 720 h para demanda_prom."""
    inv_corto = _cfe(
        2024, 4,
        kwh_base=Decimal("200000"), kwh_inter=Decimal("100000"), kwh_punta=Decimal("50000"),
        kw_base=Decimal("800"),     kw_inter=Decimal("500"),     kw_punta=Decimal("400"),
        cu_base=Decimal("1.00"),    cu_inter=Decimal("2.00"),    cu_punta=Decimal("5.00"),
        subtotal=Decimal("1000000"),
        dias_override=15,  # periodo corto → prorrateo
    )
    h = calcular_tablas_cfe([inv_corto])
    f = h["indicadores"][0]
    # Los kWh ya vienen prorrateados (×2), así kwh_total = 700000 × (30/15) = 700000
    # La demanda_prom debe dividir entre 720, no entre 15×24=360
    assert f["demanda_prom"] == round(h["consumos_demandas"][0]["kwh_total"] / 720, 1)


def test_anual_demanda_promedio():
    """ANUAL demanda_prom = kwh_total_anual / horas_totales_acumuladas.

    INV_ENE: (Jan31-Jan1).days=30 → 720 h.
    INV_FEB: (Feb29-Feb1).days=28 → 672 h. Total = 1392 h.
    """
    h = calcular_tablas_cfe([INV_ENE, INV_FEB])
    anual_ind = h["indicadores"][-1]
    anual_cd  = h["consumos_demandas"][-1]
    horas_ene = 30 * 24   # (Jan31 - Jan1).days = 30
    horas_feb = 28 * 24   # (Feb29 - Feb1).days = 28
    esperado = round(anual_cd["kwh_total"] / (horas_ene + horas_feb), 1)
    assert anual_ind["demanda_prom"] == esperado


def test_anual_factor_carga_usa_max_historico():
    """ANUAL factor_carga usa el mayor demanda_max mensual del periodo.

    INV_ENE: max=900 (kw_base). INV_FEB: max=850 (kw_base). Histórico max = 900.
    """
    h = calcular_tablas_cfe([INV_ENE, INV_FEB])
    anual_ind = h["indicadores"][-1]
    anual_cd  = h["consumos_demandas"][-1]
    horas_totales = 30 * 24 + 28 * 24  # 720 + 672 = 1392
    dem_prom_anual = round(anual_cd["kwh_total"] / horas_totales, 1)
    esperado = round(dem_prom_anual / 900 * 100)  # max histórico = 900 (enero, kw_base)
    assert anual_ind["factor_carga"] == esperado
