from __future__ import annotations

from decimal import Decimal
from datetime import date
from pathlib import Path
import pytest
from parsers.cfe.gdmth import GDMTHParser
from parsers.cfe import get_cfe_parser
from models.cfe_invoice import CFEInvoice

FIXTURE = Path("tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf")


@pytest.fixture
def invoice() -> CFEInvoice:
    parser = GDMTHParser()
    return parser.parse(FIXTURE)


def test_parser_devuelve_cfe_invoice(invoice):
    assert isinstance(invoice, CFEInvoice)

# --- Metadata ---
def test_tarifa(invoice):
    assert invoice.tarifa == "GDMTH"

def test_numero_servicio(invoice):
    assert invoice.numero_servicio == "052231189271"

def test_numero_medidor(invoice):
    assert invoice.numero_medidor == "905CFJ"

def test_multiplicador(invoice):
    assert invoice.multiplicador == 2800

def test_carga_conectada(invoice):
    assert invoice.carga_conectada_kw == Decimal("3200")

def test_demanda_contratada(invoice):
    assert invoice.demanda_contratada_kw == Decimal("3200")

def test_periodo_inicio(invoice):
    assert invoice.periodo_inicio == date(2023, 11, 7)

def test_periodo_fin(invoice):
    assert invoice.periodo_fin == date(2023, 11, 30)

def test_fecha_limite_pago(invoice):
    assert invoice.fecha_limite_pago == date(2023, 12, 14)

def test_nombre_cliente(invoice):
    assert "IBERICA TILES" in invoice.nombre_cliente

def test_rfc_cliente(invoice):
    assert invoice.rfc_cliente == "ITI170630377"

# --- Consumo horario ---
def test_consumo_base(invoice):
    base = next(p for p in invoice.periodos if p.periodo == "base")
    assert base.consumo_kwh == Decimal("128800")
    assert base.demanda_kw == Decimal("1204")

def test_consumo_intermedio(invoice):
    inter = next(p for p in invoice.periodos if p.periodo == "intermedio")
    assert inter.consumo_kwh == Decimal("204400")
    assert inter.demanda_kw == Decimal("1232")

def test_consumo_punta(invoice):
    punta = next(p for p in invoice.periodos if p.periodo == "punta")
    assert punta.consumo_kwh == Decimal("47600")
    assert punta.demanda_kw == Decimal("1232")

def test_tres_periodos(invoice):
    assert len(invoice.periodos) == 3

def test_costos_unitarios_positivos(invoice):
    for p in invoice.periodos:
        assert p.costo_unitario_kwh > Decimal("0")

def test_costo_punta_mayor_que_base(invoice):
    base = next(p for p in invoice.periodos if p.periodo == "base")
    punta = next(p for p in invoice.periodos if p.periodo == "punta")
    assert punta.costo_unitario_kwh > base.costo_unitario_kwh

# --- Medidor ---
def test_kw_max(invoice):
    assert invoice.kw_max == Decimal("1232")

def test_kvarh(invoice):
    assert invoice.kvArh == Decimal("282800")

def test_factor_potencia(invoice):
    assert invoice.factor_potencia_pct == Decimal("80.28")

# --- MEM ---
def test_nueve_componentes_mem(invoice):
    assert len(invoice.componentes_mem) == 9

def test_generacion_b_importe(invoice):
    gen_b = next(c for c in invoice.componentes_mem if c.nombre == "Generación B")
    assert gen_b.importe_mxn == Decimal("113704.64")

def test_generacion_i_importe(invoice):
    gen_i = next(c for c in invoice.componentes_mem if c.nombre == "Generación I")
    assert gen_i.importe_mxn == Decimal("352140.32")

def test_generacion_p_importe(invoice):
    gen_p = next(c for c in invoice.componentes_mem if c.nombre == "Generación P")
    assert gen_p.importe_mxn == Decimal("94752.56")

def test_distribucion_es_cargo_demanda(invoice):
    dist = next(c for c in invoice.componentes_mem if c.nombre == "Distribución")
    assert dist.cargo_demanda_mxn == Decimal("94100.81")
    assert dist.cargo_energia_mxn == Decimal("0")

# --- Financiero ---
def test_cargo_fijo(invoice):
    assert invoice.cargo_fijo_mxn == Decimal("233.84")

def test_energia_total(invoice):
    assert invoice.energia_total_mxn == Decimal("1099705.11")

def test_cargo_factor_potencia(invoice):
    assert invoice.cargo_factor_potencia_mxn == Decimal("80295.54")

def test_subtotal(invoice):
    assert invoice.subtotal_mxn == Decimal("1180234.49")

def test_iva(invoice):
    assert invoice.iva_mxn == Decimal("188837.52")

def test_facturacion_periodo(invoice):
    assert invoice.facturacion_periodo_mxn == Decimal("1369072.01")

def test_dap(invoice):
    assert invoice.derecho_alumbrado_publico_mxn == Decimal("515.84")

def test_credito_negativo(invoice):
    assert invoice.credito_aplicado_mxn == Decimal("-242816.00")

def test_total(invoice):
    assert invoice.total_mxn == Decimal("1126771.85")

# --- Validación ---
def test_sin_errores_de_validacion(invoice):
    parser = GDMTHParser()
    errores = parser.validate(invoice)
    assert errores == [], f"Errores encontrados: {errores}"

# --- kWMax: regex y fallback ---
def test_kw_max_regex_acepta_espacio():
    """RE_KW_MAX debe capturar tanto 'kWMax' como 'kW Max' (layout antiguo)."""
    from parsers.cfe.gdmth import RE_KW_MAX
    assert RE_KW_MAX.search("kWMax 1,232") is not None
    assert RE_KW_MAX.search("kW Max 1,232") is not None
    assert RE_KW_MAX.search("KW Max 1,232") is not None
    assert RE_KW_MAX.search("kwmax 1,232") is not None


def test_kw_max_fallback_desde_periodos(tmp_path):
    """Si el PDF no tiene kWMax, el parser lo deriva del máximo de las demandas horarias."""
    from unittest.mock import patch, MagicMock

    texto_sin_kwmax = (
        "NO. DE SERVICIO : 123456789\n"
        "TARIFA: GDMTH\n"
        "PERIODO FACTURADO: 01 ENE 2019 - 31 ENE 2019\n"
        "CARGA CONECTADA kW:1500 DEMANDA CONTRATADA kW: 1500\n"
        "MULTIPLICADOR: 100\n"
        "NO. MEDIDOR: ABC123\n"
        "kWh base 50,000\n"
        "kWh intermedia 80,000\n"
        "kWh punta 10,000\n"
        "kW base 900\n"
        "kW intermedia 1,100\n"
        "kW punta 950\n"
        # kWMax ausente deliberadamente
        "kVArh 5,000\n"
        "Factor de potencia % 92.50\n"
        "Suministro 100.00 0.00 0.00 100.00\n"
        "Distribución 0.00 8000.00 0.00 8000.00\n"
        "Transmisión 0.00 0.00 3000.00 3000.00\n"
        "CENACE 0.00 0.00 500.00 500.00\n"
        "Generación B 0.00 0.00 10000.00 10000.00\n"
        "Generación I 0.00 0.00 20000.00 20000.00\n"
        "Generación P 0.00 0.00 5000.00 5000.00\n"
        "Capacidad 0.00 15000.00 0.00 15000.00\n"
        "SCnMEM 0.00 0.00 200.00 200.00\n"
        "Cargo Fijo 100.00\n"
        "Energía 38200.00\n"
        "Cargo Factor de Potencia 0.00\n"
        "Subtotal 38300.00\n"
        "IVA 16 % 6128.00\n"
        "Facturación del Periodo 44428.00\n"
        "Derecho de Alumbrado Público 50.00\n"
        "Total 44478.00\n"
    )

    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = texto_sin_kwmax
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = ""
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page1, mock_page2]

    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.write_bytes(b"")

    with patch("pdfplumber.open", return_value=mock_pdf):
        inv = GDMTHParser().parse(dummy_pdf)

    # fallback: max(900, 1100, 950) = 1100
    assert inv.kw_max == Decimal("1100")
    assert any("derivado" in a for a in inv.advertencias)


# --- Factory ---
def test_factory_devuelve_gdmth_parser():
    parser = get_cfe_parser("GDMTH")
    assert isinstance(parser, GDMTHParser)

def test_factory_tarifa_no_soportada():
    with pytest.raises(ValueError, match="no soportada"):
        get_cfe_parser("TARIFA_INEXISTENTE")
