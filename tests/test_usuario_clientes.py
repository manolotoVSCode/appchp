# tests/test_usuario_clientes.py
"""Tests para funciones N:N usuario_clientes en repository."""
from __future__ import annotations
import os
from unittest.mock import MagicMock, patch, call
import pytest

# Asegurar que el módulo pueda importarse en tests aislados
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")


def _mock_supabase():
    return MagicMock()


# ── get_clientes_de_usuario ────────────────────────────────────────────────────

def test_get_clientes_de_usuario_retorna_lista_de_usuario_clientes():
    """Cuando hay filas en usuario_clientes, retorna clientes ordenados."""
    mock_sb = _mock_supabase()
    # usuario_clientes devuelve dos cliente_ids
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"cliente_id": 2},
        {"cliente_id": 5},
    ]
    # clientes devuelve los clientes correspondientes
    mock_sb.table.return_value.select.return_value.in_.return_value.order.return_value.execute.return_value.data = [
        {"id": 2, "nombre": "Alfa"},
        {"id": 5, "nombre": "Beta"},
    ]
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-1")
    assert len(result) == 2
    assert result[0]["id"] == 2
    assert result[1]["id"] == 5


def test_get_clientes_de_usuario_fallback_empresa_id():
    """Sin filas en usuario_clientes, hace fallback a empresa_id de user_profiles."""
    mock_sb = _mock_supabase()

    # Dos llamadas a table():
    # 1a: usuario_clientes → vacío
    # 2a: user_profiles → empresa_id=7
    # 3a: clientes por id 7
    call_count = {"n": 0}
    results = [
        # usuario_clientes
        MagicMock(**{"select.return_value.eq.return_value.execute.return_value.data": []}),
        # user_profiles
        MagicMock(**{"select.return_value.eq.return_value.limit.return_value.execute.return_value.data": [{"empresa_id": 7}]}),
        # clientes
        MagicMock(**{"select.return_value.eq.return_value.execute.return_value.data": [{"id": 7, "nombre": "Gamma"}]}),
    ]

    def table_side_effect(name):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(results):
            return results[idx]
        return MagicMock()

    mock_sb.table.side_effect = table_side_effect
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-2")
    assert len(result) == 1
    assert result[0]["id"] == 7


def test_get_clientes_de_usuario_retorna_lista_vacia_sin_asignaciones():
    """Sin filas en usuario_clientes y sin empresa_id, retorna lista vacía."""
    mock_sb = _mock_supabase()
    call_count = {"n": 0}
    results = [
        MagicMock(**{"select.return_value.eq.return_value.execute.return_value.data": []}),
        MagicMock(**{"select.return_value.eq.return_value.limit.return_value.execute.return_value.data": [{"empresa_id": None}]}),
    ]

    def table_side_effect(name):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(results):
            return results[idx]
        return MagicMock()

    mock_sb.table.side_effect = table_side_effect
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-3")
    assert result == []


# ── set_clientes_de_usuario ────────────────────────────────────────────────────

def test_set_clientes_de_usuario_borra_e_inserta():
    """Debe borrar filas previas e insertar las nuevas."""
    mock_sb = _mock_supabase()
    delete_mock = MagicMock()
    insert_mock = MagicMock()
    mock_sb.table.return_value.delete.return_value.eq.return_value.execute = delete_mock
    mock_sb.table.return_value.insert.return_value.execute = insert_mock

    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import set_clientes_de_usuario
        set_clientes_de_usuario("user-uuid-1", [3, 7, 12])

    delete_mock.assert_called_once()
    insert_mock.assert_called_once()


def test_set_clientes_de_usuario_lista_vacia_solo_borra():
    """Con lista vacía: borra pero no inserta."""
    mock_sb = _mock_supabase()
    delete_mock = MagicMock()
    insert_mock = MagicMock()
    mock_sb.table.return_value.delete.return_value.eq.return_value.execute = delete_mock
    mock_sb.table.return_value.insert.return_value.execute = insert_mock

    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import set_clientes_de_usuario
        set_clientes_de_usuario("user-uuid-1", [])

    delete_mock.assert_called_once()
    insert_mock.assert_not_called()


# ── get_usuarios_de_cliente ────────────────────────────────────────────────────

def test_get_usuarios_de_cliente_retorna_lista():
    """Retorna lista de usuarios asignados al cliente."""
    mock_sb = _mock_supabase()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": "uuid-a", "user_profiles": {"email": "a@b.com", "nombre": "Ana", "apellido": "L"}},
        {"user_id": "uuid-b", "user_profiles": {"email": "x@y.com", "nombre": None, "apellido": None}},
    ]
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_usuarios_de_cliente
        result = get_usuarios_de_cliente(42)
    assert len(result) == 2
    assert result[0]["user_id"] == "uuid-a"
    assert result[0]["email"] == "a@b.com"


def test_get_usuarios_de_cliente_retorna_lista_vacia():
    """Sin asignaciones retorna lista vacía."""
    mock_sb = _mock_supabase()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_usuarios_de_cliente
        result = get_usuarios_de_cliente(99)
    assert result == []
