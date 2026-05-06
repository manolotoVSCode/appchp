# tests/storage/test_repository_integration.py
"""Tests de integración contra Supabase de desarrollo.

Se saltan automáticamente si SUPABASE_DEV_URL o SUPABASE_DEV_KEY no están
definidas en el entorno. Para ejecutar:

    SUPABASE_DEV_URL=https://... SUPABASE_DEV_KEY=... pytest tests/storage/test_repository_integration.py -v
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

_SKIP = pytest.mark.skipif(
    not (os.environ.get("SUPABASE_DEV_URL") and os.environ.get("SUPABASE_DEV_KEY")),
    reason="SUPABASE_DEV_URL y SUPABASE_DEV_KEY requeridas para tests de integración",
)

# ── Fixtures de dominio ───────────────────────────────────────────────────────

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice, GasConcepto


def _make_cfe_invoice() -> CFEInvoice:
    return CFEInvoice(
        uuid_cfdi=None,
        folio="INTTEST-CFE-001",
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
        advertencias=["advertencia de integración"],
    )


def _make_gas_invoice() -> GasInvoice:
    return GasInvoice(
        uuid_cfdi="INTTEST-GAS-001",
        folio="INTTEST-GAS-001",
        fecha_emision=date(2023, 12, 1),
        periodo_inicio=date(2023, 11, 1),
        periodo_fin=date(2023, 11, 30),
        fecha_limite_pago=date(2023, 12, 15),
        nombre_proveedor="ENGIE MEXICO SA DE CV",
        rfc_proveedor="EME090928812",
        nombre_cliente="IBERICA TILES SAPI DE CV",
        rfc_cliente="ITI170630377",
        numero_cliente="TRA0002119W1",
        cuenta_contrato="12345",
        punto_suministro="PLANTA 2",
        numero_caseta="001",
        tipo_lectura="REAL",
        consumo_m3_corregidos=Decimal("9500.00"),
        consumo_sin_corregir_m3=Decimal("9400.00"),
        poder_calorifico_gj_m3=Decimal("0.0392"),
        consumo_total_gj=Decimal("106445.1830"),
        conceptos=[
            GasConcepto(
                descripcion="Gas Natural",
                clave_producto="83101601",
                cantidad_gj=Decimal("100000.00"),
                precio_unitario_gj=Decimal("79.50"),
                importe_mxn=Decimal("7950000.00"),
            ),
            GasConcepto(
                descripcion="Transporte",
                clave_producto="78102101",
                cantidad_gj=Decimal("6445.18"),
                precio_unitario_gj=Decimal("79.50"),
                importe_mxn=Decimal("512393.25"),
            ),
        ],
        costo_unitario_total_gj=Decimal("79.50"),
        subtotal_mxn=Decimal("8460263.13"),
        iva_mxn=Decimal("1353642.10"),
        total_mxn=Decimal("9813905.23"),
        pdf_path="invoices/Gas/test.pdf",
        advertencias=[],
    )


# ── Fixture: cliente Supabase de desarrollo ───────────────────────────────────

@pytest.fixture(scope="module")
def dev_client():
    """Cliente Supabase apuntando a la instancia de desarrollo."""
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_DEV_URL"],
        os.environ["SUPABASE_DEV_KEY"],
    )


# ── Tests de integración ──────────────────────────────────────────────────────

@_SKIP
def test_insertar_y_recuperar_cfe_invoice_completa(dev_client):
    """Inserta una CFEInvoice con periodos y componentes MEM y verifica que se recupera."""
    from unittest.mock import patch
    import storage.repository as repo

    invoice = _make_cfe_invoice()
    inserted_ids = {"factura": None, "cliente": None}

    with patch("storage.repository._supabase", dev_client):
        factura_id = repo.save_cfe_invoice(invoice)
        inserted_ids["factura"] = factura_id

        # Recuperar todas y buscar la insertada
        todas = repo.get_all_cfe_invoices()

    try:
        encontrada = next((f for f in todas if f.folio == "INTTEST-CFE-001"), None)
        assert encontrada is not None, "Factura CFE insertada no encontrada en get_all_cfe_invoices"
        assert encontrada.tarifa == "GDMTH"
        assert encontrada.multiplicador == 2800
        assert len(encontrada.periodos) == 3
        assert len(encontrada.componentes_mem) == 3
        assert encontrada.rfc_cliente == "ITI170630377"
        assert encontrada.credito_aplicado_mxn == Decimal("-242816.00")
    finally:
        # Cleanup
        with patch("storage.repository._supabase", dev_client):
            dev_client.table("cfe_facturas").delete().eq("id", factura_id).execute()
            dev_client.table("clientes").delete().eq("rfc", "ITI170630377").execute()


@_SKIP
def test_insertar_y_recuperar_gas_invoice_completa(dev_client):
    """Inserta una GasInvoice con conceptos y verifica que se recupera."""
    from unittest.mock import patch
    import storage.repository as repo

    invoice = _make_gas_invoice()

    with patch("storage.repository._supabase", dev_client):
        factura_id = repo.save_gas_invoice(invoice)
        todas = repo.get_all_gas_invoices()

    try:
        encontrada = next((f for f in todas if f.folio == "INTTEST-GAS-001"), None)
        assert encontrada is not None, "Factura Gas insertada no encontrada en get_all_gas_invoices"
        assert encontrada.nombre_proveedor == "ENGIE MEXICO SA DE CV"
        assert len(encontrada.conceptos) == 2
        assert encontrada.consumo_total_gj == Decimal("106445.1830")
    finally:
        # Cleanup
        dev_client.table("gas_facturas").delete().eq("id", factura_id).execute()
        dev_client.table("clientes").delete().eq("rfc", "ITI170630377").execute()


@_SKIP
def test_get_all_cfe_invoices_devuelve_decimals(dev_client):
    """Verifica que get_all_cfe_invoices devuelve CFEInvoice con todos los campos como Decimal."""
    from unittest.mock import patch
    import storage.repository as repo

    invoice = _make_cfe_invoice()

    with patch("storage.repository._supabase", dev_client):
        factura_id = repo.save_cfe_invoice(invoice)
        todas = repo.get_all_cfe_invoices()

    try:
        encontrada = next((f for f in todas if f.folio == "INTTEST-CFE-001"), None)
        assert encontrada is not None

        assert isinstance(encontrada.carga_conectada_kw, Decimal)
        assert isinstance(encontrada.demanda_contratada_kw, Decimal)
        assert isinstance(encontrada.kw_max, Decimal)
        assert isinstance(encontrada.kvArh, Decimal)
        assert isinstance(encontrada.factor_potencia_pct, Decimal)
        assert isinstance(encontrada.cargo_fijo_mxn, Decimal)
        assert isinstance(encontrada.energia_total_mxn, Decimal)
        assert isinstance(encontrada.subtotal_mxn, Decimal)
        assert isinstance(encontrada.iva_mxn, Decimal)
        assert isinstance(encontrada.total_mxn, Decimal)

        for p in encontrada.periodos:
            assert isinstance(p.consumo_kwh, Decimal)
            assert isinstance(p.demanda_kw, Decimal)
            assert isinstance(p.costo_unitario_kwh, Decimal)
    finally:
        dev_client.table("cfe_facturas").delete().eq("id", factura_id).execute()
        dev_client.table("clientes").delete().eq("rfc", "ITI170630377").execute()


@_SKIP
def test_get_all_gas_invoices_devuelve_decimals(dev_client):
    """Verifica que get_all_gas_invoices devuelve GasInvoice con todos los campos como Decimal."""
    from unittest.mock import patch
    import storage.repository as repo

    invoice = _make_gas_invoice()

    with patch("storage.repository._supabase", dev_client):
        factura_id = repo.save_gas_invoice(invoice)
        todas = repo.get_all_gas_invoices()

    try:
        encontrada = next((f for f in todas if f.folio == "INTTEST-GAS-001"), None)
        assert encontrada is not None

        assert isinstance(encontrada.consumo_m3_corregidos, Decimal)
        assert isinstance(encontrada.consumo_sin_corregir_m3, Decimal)
        assert isinstance(encontrada.poder_calorifico_gj_m3, Decimal)
        assert isinstance(encontrada.consumo_total_gj, Decimal)
        assert isinstance(encontrada.costo_unitario_total_gj, Decimal)
        assert isinstance(encontrada.subtotal_mxn, Decimal)
        assert isinstance(encontrada.iva_mxn, Decimal)
        assert isinstance(encontrada.total_mxn, Decimal)

        for c in encontrada.conceptos:
            assert isinstance(c.cantidad_gj, Decimal)
            assert isinstance(c.precio_unitario_gj, Decimal)
            assert isinstance(c.importe_mxn, Decimal)
    finally:
        dev_client.table("gas_facturas").delete().eq("id", factura_id).execute()
        dev_client.table("clientes").delete().eq("rfc", "ITI170630377").execute()
