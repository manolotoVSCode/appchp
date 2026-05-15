# tests/test_seleccion_mezcla.py
"""Tests para el bloqueo de mezcla CFE/PPA en selección de meses."""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

# Asegurar que el módulo pueda importarse en tests aislados
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")


def _make_supabase_mock(contratos_data, meses_por_contrato):
    """
    Construye un mock de _supabase para get_tipos_electricos_con_meses_seleccionados.

    contratos_data: lista de dicts {"id": int, "tipo": str}
    meses_por_contrato: dict {contrato_id: list[dict]} con meses seleccionados
    """
    mock_client = MagicMock()

    def table_side_effect(table_name):
        t = MagicMock()
        if table_name == "contratos":
            # .select("id, tipo").eq(...).in_(...).execute()
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=contratos_data)
        elif table_name == "contrato_meses_seleccionados":
            # .select(...).eq(contrato_id=value).limit(1).execute()
            def select_side(*args, **kwargs):
                s = MagicMock()

                def eq_side(field, value):
                    e = MagicMock()
                    data = meses_por_contrato.get(value, [])
                    e.limit.return_value.execute.return_value = MagicMock(data=data)
                    return e

                s.eq.side_effect = eq_side
                return s

            t.select.side_effect = select_side
        return t

    mock_client.table.side_effect = table_side_effect
    return mock_client


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_get_tipos_electricos_sin_meses():
    """Cliente sin meses seleccionados devuelve lista vacía."""
    contratos_data = [
        {"id": 1, "tipo": "electrico_basico"},
        {"id": 2, "tipo": "electrico_calificado"},
    ]
    meses_por_contrato = {1: [], 2: []}

    import storage.repository as repo
    with patch("storage.repository._supabase", _make_supabase_mock(contratos_data, meses_por_contrato)):
        result = repo.get_tipos_electricos_con_meses_seleccionados(cliente_id=99)

    assert result == []


def test_get_tipos_electricos_solo_basico():
    """Solo contratos basico seleccionados."""
    contratos_data = [
        {"id": 1, "tipo": "electrico_basico"},
        {"id": 2, "tipo": "electrico_calificado"},
    ]
    meses_por_contrato = {1: [{"contrato_id": 1}], 2: []}

    import storage.repository as repo
    with patch("storage.repository._supabase", _make_supabase_mock(contratos_data, meses_por_contrato)):
        result = repo.get_tipos_electricos_con_meses_seleccionados(cliente_id=99)

    assert result == ["electrico_basico"]


def test_get_tipos_electricos_solo_calificado():
    """Solo contratos calificado seleccionados."""
    contratos_data = [
        {"id": 1, "tipo": "electrico_basico"},
        {"id": 2, "tipo": "electrico_calificado"},
    ]
    meses_por_contrato = {1: [], 2: [{"contrato_id": 2}]}

    import storage.repository as repo
    with patch("storage.repository._supabase", _make_supabase_mock(contratos_data, meses_por_contrato)):
        result = repo.get_tipos_electricos_con_meses_seleccionados(cliente_id=99)

    assert result == ["electrico_calificado"]


def test_get_tipos_electricos_ambos():
    """Retorna ambos tipos si ambos tienen meses seleccionados (estado de error en UI)."""
    contratos_data = [
        {"id": 1, "tipo": "electrico_basico"},
        {"id": 2, "tipo": "electrico_calificado"},
    ]
    meses_por_contrato = {
        1: [{"contrato_id": 1}],
        2: [{"contrato_id": 2}],
    }

    import storage.repository as repo
    with patch("storage.repository._supabase", _make_supabase_mock(contratos_data, meses_por_contrato)):
        result = repo.get_tipos_electricos_con_meses_seleccionados(cliente_id=99)

    assert result == ["electrico_basico", "electrico_calificado"]


def test_get_tipos_electricos_sin_contratos_electricos():
    """Cliente solo con contrato de gas devuelve lista vacía."""
    contratos_data = []  # ningún contrato eléctrico
    meses_por_contrato = {}

    import storage.repository as repo
    with patch("storage.repository._supabase", _make_supabase_mock(contratos_data, meses_por_contrato)):
        result = repo.get_tipos_electricos_con_meses_seleccionados(cliente_id=99)

    assert result == []
