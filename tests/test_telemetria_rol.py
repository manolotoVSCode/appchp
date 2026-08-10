"""Tests para la funcionalidad de rol temporal de medidor.

Cubre resolver_intervalos_rol (puro, con mock de Supabase) y
declarar_rol_medidor (validación de conflictos).
"""
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")


# ── Instantes de prueba ──────────────────────────────────────────────────────
_D = "2024-01-01T00:00:00Z"
_M = "2024-01-15T12:00:00Z"
_H = "2024-01-31T23:59:59Z"


# ── test_a: medidor sin filas → retorna un solo intervalo rol carga ─────────
def test_resolver_sin_filas_retorna_carga():
    """Medidor sin filas en medidor_rol_vigencia → intervalo unico de carga."""
    # Mock: tabla vacía para ese medidor
    mock_execute = MagicMock()
    mock_execute.data = []

    with patch("storage.repository._supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.lt.return_value.or_.return_value.order.return_value.execute.return_value = mock_execute

        from storage.repository import resolver_intervalos_rol
        result = resolver_intervalos_rol(999, _D, _H)

    assert len(result) == 1
    assert result[0]["rol"] == "carga"
    assert result[0]["intervalo_desde"] == _D
    assert result[0]["intervalo_hasta"] == _H


# ── test_b: medidor con rol cabecera en todo el rango ────────────────────────
def test_resolver_rol_cabecera_completo():
    """Medidor con rol interconexion cubriendo todo el rango."""
    mock_execute = MagicMock()
    mock_execute.data = [
        {"rol": "interconexion", "vigente_desde": "2024-01-01T00:00:00+00:00",
         "vigente_hasta": None, "motivo": "instalacion"},
    ]

    with patch("storage.repository._supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.lt.return_value.or_.return_value.order.return_value.execute.return_value = mock_execute

        from storage.repository import resolver_intervalos_rol
        result = resolver_intervalos_rol(10, _D, _H)

    assert len(result) == 1
    assert result[0]["rol"] == "interconexion"


# ── test_c: medidor con hueco al inicio → el hueco es carga ─────────────────
def test_resolver_hueco_inicio_es_carga():
    """Medidor con vigencia que empieza a mitad del rango → hueco inicial es carga."""
    mock_execute = MagicMock()
    mock_execute.data = [
        {"rol": "generacion_neta", "vigente_desde": _M,
         "vigente_hasta": None, "motivo": "cambio"},
    ]

    with patch("storage.repository._supabase") as sb:
        sb.table.return_value.select.return_value.eq.return_value.lt.return_value.or_.return_value.order.return_value.execute.return_value = mock_execute

        from storage.repository import resolver_intervalos_rol
        result = resolver_intervalos_rol(10, _D, _H)

    assert len(result) == 2
    assert result[0]["rol"] == "carga"
    assert result[0]["intervalo_desde"] == _D
    assert result[0]["intervalo_hasta"] == _M
    assert result[1]["rol"] == "generacion_neta"


# ── test_d: declarar_rol_medidor levanta ValueError con conflicto ────────────
def test_declarar_rol_duplicado():
    """declarar_rol_medidor levanta ValueError si ya existe otro medidor
    de la misma planta con rol interconexion vigente."""
    from storage.repository import declarar_rol_medidor

    # Mock chain para las 3 queries: medidor.planta_id, otros medidores, conflicto
    with patch("storage.repository._supabase") as sb:
        table = sb.table.return_value

        # Primera llamada: obtener planta_id del medidor
        chain_planta = MagicMock()
        chain_planta.data = [{"planta_id": 1}]

        # Segunda llamada: otros medidores de la misma planta
        chain_otros = MagicMock()
        chain_otros.data = [{"id": 20}]

        # Tercera llamada: conflicto encontrado
        chain_conflict = MagicMock()
        chain_conflict.data = [{"id": 99, "medidor_id": 20}]

        call_count = [0]
        original_select = table.select

        def select_se(*args, **kwargs):
            call_count[0] += 1
            mock_chain = MagicMock()
            if call_count[0] == 1:
                # planta_id lookup
                mock_chain.eq.return_value.limit.return_value.execute.return_value = chain_planta
            elif call_count[0] == 2:
                # otros medidores
                mock_chain.eq.return_value.neq.return_value.execute.return_value = chain_otros
            elif call_count[0] == 3:
                # conflicto
                mock_chain.eq.return_value.eq.return_value.lte.return_value.or_.return_value.limit.return_value.execute.return_value = chain_conflict
            return mock_chain

        table.select = select_se

        desde = datetime(2024, 6, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="Ya existe otro medidor"):
            declarar_rol_medidor(10, "interconexion", desde, "test")
