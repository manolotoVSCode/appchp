# tests/storage/test_repository_unit.py
"""Unit tests para storage/repository.py usando mocks del cliente Supabase."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice, GasConcepto


# ── Fixtures de dominio ───────────────────────────────────────────────────────

def _make_cfe_invoice() -> CFEInvoice:
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


def _make_gas_invoice() -> GasInvoice:
    return GasInvoice(
        uuid_cfdi="59030c00-01f5-4dc9-bda1-25d579b23095",
        folio="I00000547",
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


# ── Helper para construir mock de tabla Supabase ──────────────────────────────

def _make_table_mock(insert_return_data=None, upsert_return_data=None, select_return_data=None):
    """Construye un mock que responde a la cadena table(...).insert/upsert/select().execute()."""
    mock = MagicMock()

    insert_result = MagicMock()
    insert_result.data = insert_return_data or []
    mock.insert.return_value.execute.return_value = insert_result

    upsert_result = MagicMock()
    upsert_result.data = upsert_return_data or []
    mock.upsert.return_value.execute.return_value = upsert_result

    select_result = MagicMock()
    select_result.data = select_return_data or []
    mock.select.return_value.order.return_value.execute.return_value = select_result

    return mock


# ── Tests: save_cfe_invoice ───────────────────────────────────────────────────

class TestSaveCfeInvoice:
    def test_llama_insert_en_cfe_facturas_con_campos_correctos(self):
        invoice = _make_cfe_invoice()

        clientes_mock = _make_table_mock(upsert_return_data=[{"id": 1}])
        cfe_facturas_mock = _make_table_mock(insert_return_data=[{"id": 42}])
        cfe_periodos_mock = _make_table_mock(insert_return_data=[])
        cfe_mem_mock = _make_table_mock(insert_return_data=[])

        def table_router(name):
            return {
                "clientes": clientes_mock,
                "cfe_facturas": cfe_facturas_mock,
                "cfe_periodos": cfe_periodos_mock,
                "cfe_mem_componentes": cfe_mem_mock,
            }[name]

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.side_effect = table_router
            import storage.repository as repo
            factura_id = repo.save_cfe_invoice(invoice)

        assert factura_id == 42

        # Verificar que insert fue llamado con los campos obligatorios
        insert_call_args = cfe_facturas_mock.insert.call_args[0][0]
        assert insert_call_args["folio"] == "000060832477"
        assert insert_call_args["tarifa"] == "GDMTH"
        assert insert_call_args["cliente_id"] == 1
        assert insert_call_args["multiplicador"] == 2800
        assert insert_call_args["kvarh"] == "282800"
        assert insert_call_args["credito_aplicado_mxn"] == "-242816.00"
        assert insert_call_args["periodo_inicio"] == "2023-11-07"
        assert insert_call_args["advertencias"] == '["advertencia de prueba"]'

    def test_llama_insert_en_cfe_periodos(self):
        invoice = _make_cfe_invoice()

        clientes_mock = _make_table_mock(upsert_return_data=[{"id": 1}])
        cfe_facturas_mock = _make_table_mock(insert_return_data=[{"id": 10}])
        cfe_periodos_mock = _make_table_mock(insert_return_data=[])
        cfe_mem_mock = _make_table_mock(insert_return_data=[])

        def table_router(name):
            return {
                "clientes": clientes_mock,
                "cfe_facturas": cfe_facturas_mock,
                "cfe_periodos": cfe_periodos_mock,
                "cfe_mem_componentes": cfe_mem_mock,
            }[name]

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.side_effect = table_router
            import storage.repository as repo
            repo.save_cfe_invoice(invoice)

        periodos_data = cfe_periodos_mock.insert.call_args[0][0]
        assert len(periodos_data) == 3
        periodos_nombres = {p["periodo"] for p in periodos_data}
        assert periodos_nombres == {"base", "intermedio", "punta"}

    def test_llama_insert_en_cfe_mem_componentes(self):
        invoice = _make_cfe_invoice()

        clientes_mock = _make_table_mock(upsert_return_data=[{"id": 1}])
        cfe_facturas_mock = _make_table_mock(insert_return_data=[{"id": 10}])
        cfe_periodos_mock = _make_table_mock(insert_return_data=[])
        cfe_mem_mock = _make_table_mock(insert_return_data=[])

        def table_router(name):
            return {
                "clientes": clientes_mock,
                "cfe_facturas": cfe_facturas_mock,
                "cfe_periodos": cfe_periodos_mock,
                "cfe_mem_componentes": cfe_mem_mock,
            }[name]

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.side_effect = table_router
            import storage.repository as repo
            repo.save_cfe_invoice(invoice)

        mem_data = cfe_mem_mock.insert.call_args[0][0]
        assert len(mem_data) == 3
        nombres = {c["nombre"] for c in mem_data}
        assert "Generación B" in nombres


# ── Tests: save_gas_invoice ───────────────────────────────────────────────────

class TestSaveGasInvoice:
    def test_llama_insert_en_gas_facturas_con_campos_correctos(self):
        invoice = _make_gas_invoice()

        clientes_mock = _make_table_mock(upsert_return_data=[{"id": 2}])
        gas_facturas_mock = _make_table_mock(insert_return_data=[{"id": 99}])
        gas_conceptos_mock = _make_table_mock(insert_return_data=[])

        def table_router(name):
            return {
                "clientes": clientes_mock,
                "gas_facturas": gas_facturas_mock,
                "gas_conceptos": gas_conceptos_mock,
            }[name]

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.side_effect = table_router
            import storage.repository as repo
            factura_id = repo.save_gas_invoice(invoice)

        assert factura_id == 99

        insert_args = gas_facturas_mock.insert.call_args[0][0]
        assert insert_args["folio"] == "I00000547"
        assert insert_args["cliente_id"] == 2
        assert insert_args["nombre_proveedor"] == "ENGIE MEXICO SA DE CV"
        assert insert_args["consumo_total_gj"] == "106445.1830"
        assert insert_args["subtotal_mxn"] == "8460263.13"
        assert insert_args["periodo_inicio"] == "2023-11-01"

    def test_llama_insert_en_gas_conceptos(self):
        invoice = _make_gas_invoice()

        clientes_mock = _make_table_mock(upsert_return_data=[{"id": 2}])
        gas_facturas_mock = _make_table_mock(insert_return_data=[{"id": 55}])
        gas_conceptos_mock = _make_table_mock(insert_return_data=[])

        def table_router(name):
            return {
                "clientes": clientes_mock,
                "gas_facturas": gas_facturas_mock,
                "gas_conceptos": gas_conceptos_mock,
            }[name]

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.side_effect = table_router
            import storage.repository as repo
            repo.save_gas_invoice(invoice)

        conceptos_data = gas_conceptos_mock.insert.call_args[0][0]
        assert len(conceptos_data) == 2
        claves = {c["clave_producto"] for c in conceptos_data}
        assert claves == {"83101601", "78102101"}


# ── Tests: get_all_cfe_invoices ───────────────────────────────────────────────

class TestGetAllCfeInvoices:
    def _make_row(self) -> dict:
        return {
            "id": 1,
            "uuid_cfdi": None,
            "folio": "000060832477",
            "serie": "PB",
            "fecha_emision": "2023-12-04",
            "periodo_inicio": "2023-11-07",
            "periodo_fin": "2023-11-30",
            "fecha_limite_pago": "2023-12-14",
            "numero_servicio": "052231189271",
            "rmu": "36880 23-11-03",
            "tarifa": "GDMTH",
            "numero_medidor": "905CFJ",
            "multiplicador": 2800,
            "carga_conectada_kw": "3200",
            "demanda_contratada_kw": "3200",
            "kw_max": "1232",
            "kvarh": "282800",
            "factor_potencia_pct": "80.28",
            "cargo_fijo_mxn": "233.84",
            "energia_total_mxn": "1099705.11",
            "cargo_factor_potencia_mxn": "80295.54",
            "subtotal_mxn": "1180234.49",
            "iva_mxn": "188837.52",
            "facturacion_periodo_mxn": "1369072.01",
            "derecho_alumbrado_publico_mxn": "515.84",
            "credito_aplicado_mxn": "-242816.00",
            "total_mxn": "1126771.85",
            "pdf_path": "tests/fixtures/cfe/P2_2023_11_NOVIEMBRE.pdf",
            "advertencias": '["advertencia de prueba"]',
            "clientes": {"nombre": "IBERICA TILES SAPI DE CV", "rfc": "ITI170630377"},
            "cfe_periodos": [
                {"id": 1, "factura_id": 1, "periodo": "base",       "consumo_kwh": "128800", "demanda_kw": "1204", "costo_unitario_kwh": "0.882900"},
                {"id": 2, "factura_id": 1, "periodo": "intermedio", "consumo_kwh": "204400", "demanda_kw": "1232", "costo_unitario_kwh": "1.722781"},
                {"id": 3, "factura_id": 1, "periodo": "punta",      "consumo_kwh": "47600",  "demanda_kw": "1232", "costo_unitario_kwh": "1.990648"},
            ],
            "cfe_mem_componentes": [
                {"id": 1, "factura_id": 1, "nombre": "Suministro",   "cargo_fijo_mxn": "233.84", "cargo_demanda_mxn": "0",         "cargo_energia_mxn": "0",          "importe_mxn": "233.84"},
                {"id": 2, "factura_id": 1, "nombre": "Distribución", "cargo_fijo_mxn": "0",      "cargo_demanda_mxn": "94100.81",  "cargo_energia_mxn": "0",          "importe_mxn": "94100.81"},
                {"id": 3, "factura_id": 1, "nombre": "Generación B", "cargo_fijo_mxn": "0",      "cargo_demanda_mxn": "0",         "cargo_energia_mxn": "113704.64",  "importe_mxn": "113704.64"},
            ],
        }

    def test_devuelve_lista_de_cfe_invoices(self):
        row = self._make_row()
        cfe_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = cfe_facturas_mock
            import storage.repository as repo
            result = repo.get_all_cfe_invoices()

        assert len(result) == 1
        assert isinstance(result[0], CFEInvoice)

    def test_campos_son_decimal_no_string_ni_float(self):
        row = self._make_row()
        cfe_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = cfe_facturas_mock
            import storage.repository as repo
            result = repo.get_all_cfe_invoices()

        inv = result[0]
        assert isinstance(inv.carga_conectada_kw, Decimal)
        assert isinstance(inv.demanda_contratada_kw, Decimal)
        assert isinstance(inv.kw_max, Decimal)
        assert isinstance(inv.kvArh, Decimal)
        assert isinstance(inv.factor_potencia_pct, Decimal)
        assert isinstance(inv.cargo_fijo_mxn, Decimal)
        assert isinstance(inv.energia_total_mxn, Decimal)
        assert isinstance(inv.cargo_factor_potencia_mxn, Decimal)
        assert isinstance(inv.subtotal_mxn, Decimal)
        assert isinstance(inv.iva_mxn, Decimal)
        assert isinstance(inv.facturacion_periodo_mxn, Decimal)
        assert isinstance(inv.derecho_alumbrado_publico_mxn, Decimal)
        assert isinstance(inv.credito_aplicado_mxn, Decimal)
        assert isinstance(inv.total_mxn, Decimal)

    def test_periodos_tienen_campos_decimal(self):
        row = self._make_row()
        cfe_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = cfe_facturas_mock
            import storage.repository as repo
            result = repo.get_all_cfe_invoices()

        inv = result[0]
        assert len(inv.periodos) == 3
        for p in inv.periodos:
            assert isinstance(p.consumo_kwh, Decimal)
            assert isinstance(p.demanda_kw, Decimal)
            assert isinstance(p.costo_unitario_kwh, Decimal)

    def test_valores_numericos_correctos(self):
        row = self._make_row()
        cfe_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = cfe_facturas_mock
            import storage.repository as repo
            result = repo.get_all_cfe_invoices()

        inv = result[0]
        assert inv.credito_aplicado_mxn == Decimal("-242816.00")
        assert inv.facturacion_periodo_mxn == Decimal("1369072.01")
        base = next(p for p in inv.periodos if p.periodo == "base")
        assert base.consumo_kwh == Decimal("128800")
        assert base.costo_unitario_kwh == Decimal("0.882900")

    def test_advertencias_se_deserializan_como_lista(self):
        row = self._make_row()
        cfe_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = cfe_facturas_mock
            import storage.repository as repo
            result = repo.get_all_cfe_invoices()

        inv = result[0]
        assert isinstance(inv.advertencias, list)
        assert "advertencia de prueba" in inv.advertencias


# ── Tests: get_all_gas_invoices ───────────────────────────────────────────────

class TestGetAllGasInvoices:
    def _make_row(self) -> dict:
        return {
            "id": 1,
            "uuid_cfdi": "59030c00-01f5-4dc9-bda1-25d579b23095",
            "folio": "I00000547",
            "fecha_emision": "2023-12-01",
            "periodo_inicio": "2023-11-01",
            "periodo_fin": "2023-11-30",
            "fecha_limite_pago": "2023-12-15",
            "nombre_proveedor": "ENGIE MEXICO SA DE CV",
            "rfc_proveedor": "EME090928812",
            "numero_cliente": "TRA0002119W1",
            "cuenta_contrato": "12345",
            "punto_suministro": "PLANTA 2",
            "numero_caseta": "001",
            "tipo_lectura": "REAL",
            "consumo_m3_corregidos": "9500.00",
            "consumo_sin_corregir_m3": "9400.00",
            "poder_calorifico_gj_m3": "0.0392",
            "consumo_total_gj": "106445.1830",
            "costo_unitario_total_gj": "79.50",
            "subtotal_mxn": "8460263.13",
            "iva_mxn": "1353642.10",
            "total_mxn": "9813905.23",
            "pdf_path": "invoices/Gas/test.pdf",
            "advertencias": "[]",
            "clientes": {"nombre": "IBERICA TILES SAPI DE CV", "rfc": "ITI170630377"},
            "gas_conceptos": [
                {"id": 1, "factura_id": 1, "descripcion": "Gas Natural", "clave_producto": "83101601", "cantidad_gj": "100000.00", "precio_unitario_gj": "79.50", "importe_mxn": "7950000.00"},
                {"id": 2, "factura_id": 1, "descripcion": "Transporte",  "clave_producto": "78102101", "cantidad_gj": "6445.18",   "precio_unitario_gj": "79.50", "importe_mxn": "512393.25"},
            ],
        }

    def test_devuelve_lista_de_gas_invoices(self):
        row = self._make_row()
        gas_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = gas_facturas_mock
            import storage.repository as repo
            result = repo.get_all_gas_invoices()

        assert len(result) == 1
        assert isinstance(result[0], GasInvoice)

    def test_campos_son_decimal_no_string_ni_float(self):
        row = self._make_row()
        gas_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = gas_facturas_mock
            import storage.repository as repo
            result = repo.get_all_gas_invoices()

        inv = result[0]
        assert isinstance(inv.consumo_m3_corregidos, Decimal)
        assert isinstance(inv.consumo_sin_corregir_m3, Decimal)
        assert isinstance(inv.poder_calorifico_gj_m3, Decimal)
        assert isinstance(inv.consumo_total_gj, Decimal)
        assert isinstance(inv.costo_unitario_total_gj, Decimal)
        assert isinstance(inv.subtotal_mxn, Decimal)
        assert isinstance(inv.iva_mxn, Decimal)
        assert isinstance(inv.total_mxn, Decimal)

    def test_conceptos_tienen_campos_decimal(self):
        row = self._make_row()
        gas_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = gas_facturas_mock
            import storage.repository as repo
            result = repo.get_all_gas_invoices()

        inv = result[0]
        assert len(inv.conceptos) == 2
        for c in inv.conceptos:
            assert isinstance(c.cantidad_gj, Decimal)
            assert isinstance(c.precio_unitario_gj, Decimal)
            assert isinstance(c.importe_mxn, Decimal)

    def test_valores_numericos_correctos(self):
        row = self._make_row()
        gas_facturas_mock = _make_table_mock(select_return_data=[row])

        with patch("storage.repository._supabase") as mock_client:
            mock_client.table.return_value = gas_facturas_mock
            import storage.repository as repo
            result = repo.get_all_gas_invoices()

        inv = result[0]
        assert inv.consumo_total_gj == Decimal("106445.1830")
        assert inv.subtotal_mxn == Decimal("8460263.13")
        assert inv.total_mxn == Decimal("9813905.23")
