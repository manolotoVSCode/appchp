# tests/calc/test_nombre_canonico.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest

from calc.nombre_canonico import (
    generar_nombre_canonico,
    generar_nombre_canonico_raw,
    _normalizar_proveedor,
)
from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.gas_invoice import GasInvoice


# ── Helpers para construir facturas mínimas ────────────────────────────────────

def _cfe(periodo_inicio: date, periodo_fin: date, numero_servicio: str = "812990300016") -> CFEInvoice:
    return CFEInvoice(
        uuid_cfdi=None, folio="1", serie=None,
        fecha_emision=periodo_inicio, periodo_inicio=periodo_inicio, periodo_fin=periodo_fin,
        fecha_limite_pago=periodo_fin, nombre_cliente="CLIENTE", rfc_cliente="RFC",
        numero_servicio=numero_servicio, rmu=None, tarifa="GDMTH", numero_medidor="M",
        multiplicador=1, carga_conectada_kw=Decimal("0"), demanda_contratada_kw=Decimal("0"),
        periodos=[], kw_max=Decimal("0"), kvArh=Decimal("0"), factor_potencia_pct=Decimal("0"),
        componentes_mem=[], cargo_fijo_mxn=Decimal("0"), energia_total_mxn=Decimal("0"),
        cargo_factor_potencia_mxn=Decimal("0"), subtotal_mxn=Decimal("0"), iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=Decimal("0"), derecho_alumbrado_publico_mxn=Decimal("0"),
        credito_aplicado_mxn=Decimal("0"), total_mxn=Decimal("0"), pdf_path="f.pdf",
    )


def _gas(periodo_inicio: date, periodo_fin: date, nombre_proveedor: str = "ENGIE") -> GasInvoice:
    return GasInvoice(
        uuid_cfdi="", folio="1", fecha_emision=periodo_inicio,
        periodo_inicio=periodo_inicio, periodo_fin=periodo_fin, fecha_limite_pago=periodo_fin,
        nombre_proveedor=nombre_proveedor, rfc_proveedor="RFC", nombre_cliente="CLIENTE",
        rfc_cliente="RFC", numero_cliente="0", cuenta_contrato="0", punto_suministro="0",
        numero_caseta="0", tipo_lectura="0", consumo_m3_corregidos=Decimal("0"),
        consumo_sin_corregir_m3=Decimal("0"), poder_calorifico_gj_m3=Decimal("0"),
        consumo_total_gj=Decimal("0"), conceptos=[], costo_unitario_total_gj=Decimal("0"),
        subtotal_mxn=Decimal("0"), iva_mxn=Decimal("0"), total_mxn=Decimal("0"), pdf_path="f.pdf",
    )


# ── Tests de generar_nombre_canonico ──────────────────────────────────────────

def test_cfe_tipica():
    """Factura CFE con periodo enero: nombre incluye ENERO y numero_servicio."""
    factura = _cfe(date(2024, 1, 1), date(2024, 1, 31))
    assert generar_nombre_canonico(factura) == "2024 ENERO CFE 812990300016"


def test_gas_engie():
    """Factura gas ENGIE: nombre incluye ENGIE sin número de servicio."""
    factura = _gas(date(2024, 1, 1), date(2024, 1, 31))
    assert generar_nombre_canonico(factura) == "2024 ENERO ENGIE"


def test_mes_asociado_distinto_al_periodo_inicio():
    """Factura cuyo periodo va del 29 feb al 31 mar: mes asociado es MARZO."""
    # 29 feb (1 día en feb) + 31 días en mar → mes asociado = marzo
    factura = _cfe(date(2024, 2, 29), date(2024, 3, 31), numero_servicio="052231189271")
    nombre = generar_nombre_canonico(factura)
    assert nombre == "2024 MARZO CFE 052231189271"
    assert "FEBRERO" not in nombre


def test_gas_proveedor_con_acentos():
    """Proveedor con acento: se normaliza sin acento, mayúsculas, espacios conservados."""
    factura = _gas(date(2024, 1, 1), date(2024, 1, 31), nombre_proveedor="Naturgy México")
    assert generar_nombre_canonico(factura) == "2024 ENERO NATURGY MEXICO"


def test_cfe_numero_servicio_vacio_usa_fallback():
    """numero_servicio vacío → fallback 'CFE SIN_SERVICIO'."""
    factura = _cfe(date(2024, 1, 1), date(2024, 1, 31), numero_servicio="")
    assert generar_nombre_canonico(factura) == "2024 ENERO CFE SIN_SERVICIO"


def test_cfe_numero_servicio_none_usa_fallback():
    """numero_servicio None → fallback 'CFE SIN_SERVICIO'."""
    factura = _cfe(date(2024, 1, 1), date(2024, 1, 31), numero_servicio=None)
    assert generar_nombre_canonico(factura) == "2024 ENERO CFE SIN_SERVICIO"


def test_gas_proveedor_vacio_usa_gas():
    """nombre_proveedor vacío → proveedor genérico 'GAS'."""
    factura = _gas(date(2024, 1, 1), date(2024, 1, 31), nombre_proveedor="")
    assert generar_nombre_canonico(factura) == "2024 ENERO GAS"


def test_gas_proveedor_con_espacios_conserva_espacios():
    """Proveedor multi-palabra conserva espacios internos."""
    factura = _gas(date(2024, 1, 1), date(2024, 1, 31), nombre_proveedor="GAS NATURAL DEL CENTRO")
    assert generar_nombre_canonico(factura) == "2024 ENERO GAS NATURAL DEL CENTRO"


def test_normalizar_proveedor_elimina_acentos():
    assert _normalizar_proveedor("Energía Limpia") == "ENERGIA LIMPIA"
    assert _normalizar_proveedor("Naturgy México") == "NATURGY MEXICO"
    assert _normalizar_proveedor("ENGIE") == "ENGIE"


def test_noviembre_2023():
    """Verifica otro mes y año."""
    factura = _cfe(date(2023, 11, 1), date(2023, 11, 30), numero_servicio="052231189271")
    assert generar_nombre_canonico(factura) == "2023 NOVIEMBRE CFE 052231189271"


# ── Tests de generar_nombre_canonico_raw ──────────────────────────────────────

def test_raw_cfe():
    nombre = generar_nombre_canonico_raw(
        date(2024, 1, 1), date(2024, 1, 31),
        tipo="cfe", numero_servicio="812990300016",
    )
    assert nombre == "2024 ENERO CFE 812990300016"


def test_raw_gas():
    nombre = generar_nombre_canonico_raw(
        date(2024, 1, 1), date(2024, 1, 31),
        tipo="gas", nombre_proveedor="ENGIE",
    )
    assert nombre == "2024 ENERO ENGIE"


def test_raw_cfe_sin_servicio():
    nombre = generar_nombre_canonico_raw(
        date(2024, 1, 1), date(2024, 1, 31),
        tipo="cfe", numero_servicio=None,
    )
    assert nombre == "2024 ENERO CFE SIN_SERVICIO"


# ── Tests de migración ────────────────────────────────────────────────────────

def _make_mock_client(cfe_rows: list[dict], gas_rows: list[dict]) -> MagicMock:
    """Construye mock de cliente Supabase para pruebas de migración.

    El mismo mock de tabla se devuelve en cada llamada con el mismo nombre,
    para que los call_args_list sean accesibles tras la ejecución.
    """
    mock = MagicMock()
    _tables: dict[str, MagicMock] = {}

    def _table_side_effect(name):
        if name not in _tables:
            t = MagicMock()
            if name == "cfe_facturas":
                t.select.return_value.execute.return_value.data = cfe_rows
            elif name == "gas_facturas":
                t.select.return_value.execute.return_value.data = gas_rows
            _tables[name] = t
        return _tables[name]

    mock.table.side_effect = _table_side_effect
    mock._tables = _tables  # acceso desde los tests
    return mock


def _cfe_row(id_: int, periodo_inicio: str, periodo_fin: str, numero_servicio: str = "123") -> dict:
    return {
        "id": id_,
        "periodo_inicio": periodo_inicio,
        "periodo_fin": periodo_fin,
        "numero_servicio": numero_servicio,
    }


def _gas_row(id_: int, periodo_inicio: str, periodo_fin: str, nombre_proveedor: str = "ENGIE") -> dict:
    return {
        "id": id_,
        "periodo_inicio": periodo_inicio,
        "periodo_fin": periodo_fin,
        "nombre_proveedor": nombre_proveedor,
    }


def test_migracion_calcula_y_actualiza_cfe(monkeypatch):
    """La migración actualiza nombre_canonico en todas las facturas CFE."""
    from scripts.migrar_nombre_canonico import migrar

    cfe_rows = [_cfe_row(1, "2024-01-01", "2024-01-31", "812990300016")]
    gas_rows = []
    client = _make_mock_client(cfe_rows, gas_rows)

    resultado = migrar(client)

    assert resultado["cfe_ok"] == 1
    assert resultado["gas_ok"] == 0
    assert resultado["errores"] == 0

    # Verificar que se llamó update con el nombre correcto
    update_calls = client._tables["cfe_facturas"].update.call_args_list
    assert len(update_calls) == 1
    assert update_calls[0] == call({"nombre_canonico": "2024 ENERO CFE 812990300016"})


def test_migracion_calcula_y_actualiza_gas(monkeypatch):
    """La migración actualiza nombre_canonico en todas las facturas gas."""
    from scripts.migrar_nombre_canonico import migrar

    cfe_rows = []
    gas_rows = [_gas_row(10, "2024-01-01", "2024-01-31", "ENGIE")]
    client = _make_mock_client(cfe_rows, gas_rows)

    resultado = migrar(client)

    assert resultado["cfe_ok"] == 0
    assert resultado["gas_ok"] == 1
    assert resultado["errores"] == 0

    update_calls = client._tables["gas_facturas"].update.call_args_list
    assert len(update_calls) == 1
    assert update_calls[0] == call({"nombre_canonico": "2024 ENERO ENGIE"})


def test_migracion_idempotente():
    """Ejecutar la migración dos veces produce el mismo resultado."""
    from scripts.migrar_nombre_canonico import migrar

    cfe_rows = [_cfe_row(1, "2024-01-01", "2024-01-31", "812990300016")]
    gas_rows = [_gas_row(10, "2024-02-01", "2024-02-29", "ENGIE")]

    # Primera corrida
    client1 = _make_mock_client(cfe_rows, gas_rows)
    r1 = migrar(client1)

    # Segunda corrida (mismo cliente con mismo estado)
    client2 = _make_mock_client(cfe_rows, gas_rows)
    r2 = migrar(client2)

    assert r1 == r2
    assert r1["errores"] == 0


def test_migracion_contabiliza_errores(monkeypatch):
    """Filas con datos corruptos se cuentan como errores, no abortan la corrida."""
    from scripts.migrar_nombre_canonico import migrar

    # Fila con periodo_inicio inválido
    cfe_rows = [
        _cfe_row(1, "2024-01-01", "2024-01-31", "812990300016"),
        {"id": 2, "periodo_inicio": "invalido", "periodo_fin": "2024-01-31", "numero_servicio": "X"},
    ]
    gas_rows = []
    client = _make_mock_client(cfe_rows, gas_rows)

    resultado = migrar(client)

    assert resultado["cfe_ok"] == 1
    assert resultado["errores"] == 1
