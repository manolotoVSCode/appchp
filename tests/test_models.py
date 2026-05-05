from dataclasses import asdict
from datetime import date
from decimal import Decimal
from models.cfe_invoice import MEMComponente, CFEConsumoHorario, CFEInvoice
from models.gas_invoice import GasConcepto, GasInvoice


def _cfe_invoice_noviembre() -> CFEInvoice:
    return CFEInvoice(
        uuid_cfdi=None,
        folio="000060832477",
        serie="PB",
        fecha_emision=date(2023, 12, 4),
        periodo_inicio=date(2023, 11, 7),
        periodo_fin=date(2023, 11, 30),
        fecha_limite_pago=date(2023, 12, 14),
        nombre_cliente="IBERICA TILES SAPI DE CV",
        rfc_cliente="ITI170630377",
        numero_servicio="052231189271",
        rmu="36880 23-11-03 XAXX-010101 010 CFE",
        tarifa="GDMTH",
        numero_medidor="905CFJ",
        multiplicador=2800,
        carga_conectada_kw=Decimal("3200"),
        demanda_contratada_kw=Decimal("3200"),
        periodos=[
            CFEConsumoHorario("base", Decimal("128800"), Decimal("1204"), Decimal("0.9")),
            CFEConsumoHorario("intermedio", Decimal("204400"), Decimal("1232"), Decimal("1.8")),
            CFEConsumoHorario("punta", Decimal("47600"), Decimal("1232"), Decimal("2.1")),
        ],
        kw_max=Decimal("1232"),
        kvArh=Decimal("282800"),
        factor_potencia_pct=Decimal("80.28"),
        componentes_mem=[
            MEMComponente("Suministro", Decimal("233.84"), Decimal("0"), Decimal("0"), Decimal("233.84")),
        ],
        cargo_fijo_mxn=Decimal("233.84"),
        energia_total_mxn=Decimal("1099705.11"),
        cargo_factor_potencia_mxn=Decimal("80295.54"),
        subtotal_mxn=Decimal("1180234.49"),
        iva_mxn=Decimal("188837.52"),
        facturacion_periodo_mxn=Decimal("1369072.01"),
        derecho_alumbrado_publico_mxn=Decimal("515.84"),
        credito_aplicado_mxn=Decimal("-242816.00"),
        total_mxn=Decimal("1126771.85"),
        pdf_path="tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf",
    )


def test_cfe_invoice_instancia_correctamente():
    inv = _cfe_invoice_noviembre()
    assert inv.tarifa == "GDMTH"
    assert inv.multiplicador == 2800
    assert len(inv.periodos) == 3
    assert inv.periodos[0].periodo == "base"


def test_cfe_invoice_serializa_a_dict():
    inv = _cfe_invoice_noviembre()
    d = asdict(inv)
    assert d["tarifa"] == "GDMTH"
    assert d["periodos"][0]["consumo_kwh"] == Decimal("128800")
    assert d["componentes_mem"][0]["nombre"] == "Suministro"


def test_cfe_invoice_advertencias_vacia_por_defecto():
    inv = _cfe_invoice_noviembre()
    assert inv.advertencias == []


def test_gas_invoice_instancia_correctamente():
    inv = GasInvoice(
        uuid_cfdi="59030c00-01f5-4dc9-bda1-25d579b23095",
        folio="I00000547",
        fecha_emision=date(2023, 12, 14),
        periodo_inicio=date(2023, 11, 1),
        periodo_fin=date(2023, 11, 30),
        fecha_limite_pago=date(2023, 12, 25),
        nombre_proveedor="GDF SUEZ MEXICO COMERCIALIZADORA",
        rfc_proveedor="TRA0002119W1",
        nombre_cliente="IBERICA TILES SAPI DE CV",
        rfc_cliente="ITI170630377",
        numero_cliente="610002800",
        cuenta_contrato="5100096634",
        punto_suministro="IBERICA TILES SAPI DE CV",
        numero_caseta="11067-01",
        tipo_lectura="REAL CONSUMO",
        consumo_m3_corregidos=Decimal("2960411.81"),
        consumo_sin_corregir_m3=Decimal("0"),
        poder_calorifico_gj_m3=Decimal("0.035958531"),
        consumo_total_gj=Decimal("106445.1830"),
        conceptos=[
            GasConcepto("Compraventa de Gas Natural", "83101601",
                        Decimal("106445.1830"), Decimal("54.85"), Decimal("5838518.28")),
            GasConcepto("Transporte por Ducto Gas Natural", "78102101",
                        Decimal("106445.1830"), Decimal("24.63"), Decimal("2621744.85")),
        ],
        costo_unitario_total_gj=Decimal("79.48"),
        subtotal_mxn=Decimal("8460263.13"),
        iva_mxn=Decimal("1353642.10"),
        total_mxn=Decimal("9813905.23"),
        pdf_path="tests/fixtures/gas/sample.pdf",
    )
    assert inv.costo_unitario_total_gj == Decimal("79.48")
    assert len(inv.conceptos) == 2
