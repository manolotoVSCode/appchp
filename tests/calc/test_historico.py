# tests/calc/test_historico.py
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from calc.historico import calcular_historico_cfe
from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente


# ── Helper ────────────────────────────────────────────────────────────────────

def _cfe(
    year: int,
    month: int,
    kwh_punta: Decimal,
    kwh_inter: Decimal,
    kwh_base: Decimal,
    kw_punta: Decimal,
    kw_inter: Decimal,
    kw_base: Decimal,
    cu_punta: Decimal,
    cu_inter: Decimal,
    cu_base: Decimal,
    facturacion: Decimal,
) -> CFEInvoice:
    """CFEInvoice sintética con periodo completo del mes."""
    import calendar
    ultimo = calendar.monthrange(year, month)[1]
    inicio = date(year, month, 1)
    fin = date(year, month, ultimo)
    periodos = [
        CFEConsumoHorario("punta",      kwh_punta, kw_punta, cu_punta),
        CFEConsumoHorario("intermedio", kwh_inter, kw_inter, cu_inter),
        CFEConsumoHorario("base",       kwh_base,  kw_base,  cu_base),
    ]
    return CFEInvoice(
        uuid_cfdi=None, folio="F1", serie=None,
        fecha_emision=inicio, periodo_inicio=inicio, periodo_fin=fin,
        fecha_limite_pago=fin, nombre_cliente="TEST", rfc_cliente="TST010101AAA",
        numero_servicio="12345", rmu=None, tarifa="GDMTH", numero_medidor="M1",
        multiplicador=1, carga_conectada_kw=Decimal("1000"),
        demanda_contratada_kw=Decimal("1000"), periodos=periodos,
        kw_max=Decimal("500"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("90"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=facturacion, cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=facturacion, iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=facturacion,
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=facturacion, pdf_path="test.pdf",
    )


# Fixture base: dos meses con valores conocidos
@pytest.fixture
def dos_meses():
    return [
        _cfe(
            2024, 1,
            kwh_punta=Decimal("100"), kwh_inter=Decimal("300"), kwh_base=Decimal("600"),
            kw_punta=Decimal("200"),  kw_inter=Decimal("400"),  kw_base=Decimal("600"),
            cu_punta=Decimal("5.00"), cu_inter=Decimal("3.00"), cu_base=Decimal("1.50"),
            facturacion=Decimal("2500"),   # 100×5 + 300×3 + 600×1.5 = 500+900+900 = 2300; no cuadra exacto, usamos 2500
        ),
        _cfe(
            2024, 2,
            kwh_punta=Decimal("80"),  kwh_inter=Decimal("250"), kwh_base=Decimal("500"),
            kw_punta=Decimal("180"),  kw_inter=Decimal("380"),  kw_base=Decimal("580"),
            cu_punta=Decimal("5.20"), cu_inter=Decimal("3.10"), cu_base=Decimal("1.55"),
            facturacion=Decimal("2200"),
        ),
    ]


# ── Tests de estructura ───────────────────────────────────────────────────────

def test_estructura_keys(dos_meses):
    h = calcular_historico_cfe(dos_meses)
    expected_keys = {
        "labels", "demanda_punta", "demanda_intermedio", "demanda_base",
        "consumo_punta", "consumo_intermedio", "consumo_base",
        "costo_unit_mes", "tabla_punta", "costo_unit_promedio",
    }
    assert expected_keys == set(h.keys())


def test_longitud_arrays(dos_meses):
    h = calcular_historico_cfe(dos_meses)
    n = len(dos_meses)
    for key in ["labels", "demanda_punta", "demanda_intermedio", "demanda_base",
                "consumo_punta", "consumo_intermedio", "consumo_base", "costo_unit_mes"]:
        assert len(h[key]) == n, f"Array '{key}' tiene longitud incorrecta"


def test_tabla_punta_tiene_fila_total(dos_meses):
    h = calcular_historico_cfe(dos_meses)
    assert h["tabla_punta"][-1]["mes"] == "TOTAL ANUAL"
    assert len(h["tabla_punta"]) == len(dos_meses) + 1


# ── Tests de orden cronológico ────────────────────────────────────────────────

def test_orden_cronologico():
    """Los meses salen en orden ascendente independientemente del orden de entrada."""
    inv_mar = _cfe(2024, 3, Decimal("100"), Decimal("300"), Decimal("600"),
                   Decimal("200"), Decimal("400"), Decimal("600"),
                   Decimal("5"), Decimal("3"), Decimal("1.5"), Decimal("2300"))
    inv_ene = _cfe(2024, 1, Decimal("100"), Decimal("300"), Decimal("600"),
                   Decimal("200"), Decimal("400"), Decimal("600"),
                   Decimal("5"), Decimal("3"), Decimal("1.5"), Decimal("2300"))
    h = calcular_historico_cfe([inv_mar, inv_ene])
    # Usar strftime para el label esperado — el formato depende del locale del sistema
    label_ene = date(2024, 1, 1).strftime("%b %Y")
    label_mar = date(2024, 3, 1).strftime("%b %Y")
    assert h["labels"][0] == label_ene
    assert h["labels"][1] == label_mar


# ── Tests de demanda ──────────────────────────────────────────────────────────

def test_demanda_por_horario(dos_meses):
    h = calcular_historico_cfe(dos_meses)
    assert h["demanda_punta"][0] == 200.0
    assert h["demanda_intermedio"][0] == 400.0
    assert h["demanda_base"][0] == 600.0
    assert h["demanda_punta"][1] == 180.0


# ── Tests de consumo ──────────────────────────────────────────────────────────

def test_consumo_por_horario(dos_meses):
    h = calcular_historico_cfe(dos_meses)
    assert h["consumo_punta"][0] == 100.0
    assert h["consumo_intermedio"][0] == 300.0
    assert h["consumo_base"][0] == 600.0


# ── Tests de costo unitario mensual ──────────────────────────────────────────

def test_costo_unitario_mes(dos_meses):
    """costo_unit_mes = subtotal_mxn (pre-IVA) / kwh_total."""
    h = calcular_historico_cfe(dos_meses)
    kwh_total_ene = 100 + 300 + 600  # 1000
    esperado = round(2500 / kwh_total_ene, 4)
    assert h["costo_unit_mes"][0] == esperado


# ── Tests de tabla punta ──────────────────────────────────────────────────────

def test_tabla_punta_costo(dos_meses):
    """costo_punta = kwh_punta × cu_punta."""
    h = calcular_historico_cfe(dos_meses)
    esperado = round(100 * 5.00, 2)  # 500.00
    assert h["tabla_punta"][0]["costo_punta"] == esperado


def test_tabla_punta_porcentaje(dos_meses):
    """pct = costo_punta / facturacion_total × 100."""
    h = calcular_historico_cfe(dos_meses)
    costo_punta = round(100 * 5.00, 2)
    esperado = round(costo_punta / 2500 * 100, 1)
    assert h["tabla_punta"][0]["pct"] == esperado


def test_tabla_punta_fila_total_suma_costos(dos_meses):
    """TOTAL ANUAL costo_punta = suma de costos punta mensuales."""
    h = calcular_historico_cfe(dos_meses)
    total_row = h["tabla_punta"][-1]
    suma = sum(r["costo_punta"] for r in h["tabla_punta"][:-1])
    assert abs(total_row["costo_punta"] - suma) < 0.01


def test_tabla_punta_fila_total_promedio_ponderado(dos_meses):
    """TOTAL ANUAL costo_unit_punta = suma(costo_punta) / suma(kwh_punta)."""
    h = calcular_historico_cfe(dos_meses)
    total_row = h["tabla_punta"][-1]
    suma_cp = 100 * 5.00 + 80 * 5.20  # 500 + 416 = 916
    suma_kwh_p = 100 + 80             # 180
    esperado = round(suma_cp / suma_kwh_p, 4)
    assert total_row["costo_unit_punta"] == esperado


# ── Tests de costo unitario promedio ponderado ────────────────────────────────

def test_costo_unit_promedio_keys(dos_meses):
    h = calcular_historico_cfe(dos_meses)
    assert set(h["costo_unit_promedio"].keys()) == {"base", "intermedio", "punta"}


def test_costo_unit_promedio_ponderado_punta(dos_meses):
    """Promedio ponderado por consumo, no promedio simple de tasas mensuales."""
    h = calcular_historico_cfe(dos_meses)
    # punta: mes1 = 100kWh × $5, mes2 = 80kWh × $5.20
    suma_costo = 100 * 5.00 + 80 * 5.20   # 916
    suma_kwh = 100 + 80                    # 180
    esperado = round(suma_costo / suma_kwh, 4)
    assert h["costo_unit_promedio"]["punta"] == esperado


def test_costo_unit_promedio_no_es_promedio_simple(dos_meses):
    """El promedio ponderado difiere del promedio aritmético de las tasas cuando los volúmenes difieren."""
    h = calcular_historico_cfe(dos_meses)
    promedio_simple = round((5.00 + 5.20) / 2, 4)  # 5.10
    promedio_ponderado = h["costo_unit_promedio"]["punta"]
    # Con 100kWh a $5 y 80kWh a $5.20, el ponderado es < 5.10 (más peso al mes más barato)
    assert promedio_ponderado != promedio_simple


def test_lista_vacia_devuelve_estructura_valida():
    """Con lista vacía, devuelve el dict con arrays vacíos y dict de promedios en cero."""
    h = calcular_historico_cfe([])
    assert h["labels"] == []
    assert h["tabla_punta"] == [{"mes": "TOTAL ANUAL", "costo_punta": 0.0, "pct": 0.0, "costo_unit_punta": 0.0}]
    assert h["costo_unit_promedio"] == {"base": 0.0, "intermedio": 0.0, "punta": 0.0}
