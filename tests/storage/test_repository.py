from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal
import pytest

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from storage.schema import init_db
from storage.repository import save_cfe_invoice, load_cfe_invoice, list_cfe_invoices


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    yield c
    c.close()


def _invoice_minima() -> CFEInvoice:
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
        rmu="36880 23-11-03",
        tarifa="GDMTH",
        numero_medidor="905CFJ",
        multiplicador=2800,
        carga_conectada_kw=Decimal("3200"),
        demanda_contratada_kw=Decimal("3200"),
        periodos=[
            CFEConsumoHorario("base",       Decimal("128800"), Decimal("1204"), Decimal("0.882900")),
            CFEConsumoHorario("intermedio", Decimal("204400"), Decimal("1232"), Decimal("1.722781")),
            CFEConsumoHorario("punta",      Decimal("47600"),  Decimal("1232"), Decimal("1.990648")),
        ],
        kw_max=Decimal("1232"),
        kvArh=Decimal("282800"),
        factor_potencia_pct=Decimal("80.28"),
        componentes_mem=[
            MEMComponente("Suministro",   Decimal("233.84"), Decimal("0"),        Decimal("0"),         Decimal("233.84")),
            MEMComponente("Distribución", Decimal("0"),      Decimal("94100.81"), Decimal("0"),         Decimal("94100.81")),
            MEMComponente("Generación B", Decimal("0"),      Decimal("0"),        Decimal("113704.64"), Decimal("113704.64")),
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
        advertencias=["advertencia de prueba"],
    )


def test_save_devuelve_id_entero(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    assert isinstance(factura_id, int)
    assert factura_id > 0


def test_load_recupera_campos_simples(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)
    assert cargada.folio == "000060832477"
    assert cargada.tarifa == "GDMTH"
    assert cargada.multiplicador == 2800
    assert cargada.rfc_cliente == "ITI170630377"
    assert cargada.credito_aplicado_mxn == Decimal("-242816.00")


def test_load_recupera_periodos(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)
    assert len(cargada.periodos) == 3
    base = next(p for p in cargada.periodos if p.periodo == "base")
    assert base.consumo_kwh == Decimal("128800")
    assert base.costo_unitario_kwh == Decimal("0.882900")


def test_load_recupera_mem_componentes(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)
    assert len(cargada.componentes_mem) == 3
    gen_b = next(c for c in cargada.componentes_mem if c.nombre == "Generación B")
    assert gen_b.importe_mxn == Decimal("113704.64")


def test_load_recupera_advertencias(conn):
    inv = _invoice_minima()
    factura_id = save_cfe_invoice(conn, inv)
    cargada = load_cfe_invoice(conn, factura_id)
    assert "advertencia de prueba" in cargada.advertencias


def test_load_factura_inexistente_lanza_error(conn):
    with pytest.raises(ValueError, match="no encontrada"):
        load_cfe_invoice(conn, 9999)


def test_list_devuelve_facturas_guardadas(conn):
    inv = _invoice_minima()
    save_cfe_invoice(conn, inv)
    save_cfe_invoice(conn, inv)
    facturas = list_cfe_invoices(conn)
    assert len(facturas) == 2


def test_mismo_cliente_no_duplica_en_clientes(conn):
    inv = _invoice_minima()
    save_cfe_invoice(conn, inv)
    save_cfe_invoice(conn, inv)
    count = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    assert count == 1
