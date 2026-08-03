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


def test_get_clientes_de_usuario_fallback_user_profiles_vacio():
    """Sin filas en usuario_clientes y user_profiles devuelve vacío → lista vacía."""
    mock_sb = _mock_supabase()
    call_count = {"n": 0}
    results = [
        MagicMock(**{"select.return_value.eq.return_value.execute.return_value.data": []}),
        MagicMock(**{"select.return_value.eq.return_value.limit.return_value.execute.return_value.data": []}),
    ]
    def table_side_effect(name):
        idx = call_count["n"]
        call_count["n"] += 1
        return results[idx] if idx < len(results) else MagicMock()
    mock_sb.table.side_effect = table_side_effect
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-4")
    assert result == []


def test_get_clientes_de_usuario_retorna_lista_vacia_en_excepcion():
    """Si _supabase lanza excepción, retorna [] sin propagar."""
    mock_sb = _mock_supabase()
    mock_sb.table.side_effect = Exception("DB connection failed")
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-err")
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


# ── Permisos multi-cliente ─────────────────────────────────────────────────────

from web.auth_permissions import usuario_puede_ver_empresa, filtrar_empresas_para_usuario


def test_usuario_puede_ver_empresa_admin_ve_todo():
    user = {"rol": "admin", "clientes_ids": [], "empresa_id": None}
    assert usuario_puede_ver_empresa(99, user) is True


def test_usuario_puede_ver_empresa_master_admin_ve_todo():
    user = {"rol": "master_admin", "clientes_ids": [], "empresa_id": None}
    assert usuario_puede_ver_empresa(5, user) is True


def test_usuario_puede_ver_empresa_normal_con_lista():
    user = {"rol": "usuario_normal", "clientes_ids": [3, 7], "empresa_id": None}
    assert usuario_puede_ver_empresa(7, user) is True
    assert usuario_puede_ver_empresa(99, user) is False


def test_usuario_puede_ver_empresa_normal_fallback_empresa_id():
    """Sin clientes_ids, usa empresa_id legado."""
    user = {"rol": "usuario_normal", "clientes_ids": [], "empresa_id": 4}
    assert usuario_puede_ver_empresa(4, user) is True
    assert usuario_puede_ver_empresa(5, user) is False


def test_filtrar_empresas_admin_sin_filtro():
    clientes = [{"id": 1}, {"id": 2}, {"id": 3}]
    user = {"rol": "admin", "clientes_ids": [], "empresa_id": None}
    assert filtrar_empresas_para_usuario(clientes, user) == clientes


def test_filtrar_empresas_normal_multi():
    clientes = [{"id": 1}, {"id": 2}, {"id": 3}]
    user = {"rol": "usuario_normal", "clientes_ids": [1, 3], "empresa_id": None}
    result = filtrar_empresas_para_usuario(clientes, user)
    assert [c["id"] for c in result] == [1, 3]


def test_filtrar_empresas_normal_fallback():
    clientes = [{"id": 1}, {"id": 2}, {"id": 3}]
    user = {"rol": "usuario_normal", "clientes_ids": [], "empresa_id": 2}
    result = filtrar_empresas_para_usuario(clientes, user)
    assert [c["id"] for c in result] == [2]


def test_filtrar_empresas_normal_sin_asignacion():
    clientes = [{"id": 1}, {"id": 2}]
    user = {"rol": "usuario_normal", "clientes_ids": [], "empresa_id": None}
    assert filtrar_empresas_para_usuario(clientes, user) == []


# ── Tests de acceso web ────────────────────────────────────────────────────────

@pytest.fixture()
def app_fixture(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture()
def web_client(app_fixture):
    return app_fixture.test_client()


def _inject_usuario_normal(client, clientes_ids, empresa_id=None):
    with client.session_transaction() as sess:
        sess["_user_id"] = "test-user-uuid"
        sess["_user_email"] = "cliente@test.com"
        sess["_user_rol"] = "usuario_normal"
        sess["_empresa_id"] = empresa_id or (clientes_ids[0] if clientes_ids else None)
        sess["_empresa_nombre"] = "Test Empresa"
        sess["_clientes_ids"] = clientes_ids
        sess["_session_version"] = 1


def test_usuario_normal_puede_acceder_a_cliente_asignado(web_client):
    """usuario_normal con clientes_ids=[3] pasa el check de _require_login (no redirige a login)."""
    from unittest.mock import patch
    _inject_usuario_normal(web_client, clientes_ids=[3], empresa_id=3)
    with patch("web.auth._verificar_activo_con_cache", return_value=True), \
         patch("web.auth._verificar_session_version_con_cache", return_value=True):
        resp = web_client.get("/clientes/3/dashboard/contabilidad", follow_redirects=False)
    # El _require_login no debe redirigir a login ni a una ruta de acceso denegado
    location = resp.headers.get("Location", "")
    assert "/auth/login" not in location, f"Redirigido a login: {location}"


def test_usuario_normal_bloqueado_en_cliente_no_asignado(web_client):
    """usuario_normal con clientes_ids=[3] recibe redirect al intentar /clientes/99/..."""
    from unittest.mock import patch
    _inject_usuario_normal(web_client, clientes_ids=[3], empresa_id=3)
    with patch("web.auth._verificar_activo_con_cache", return_value=True), \
         patch("web.auth._verificar_session_version_con_cache", return_value=True):
        resp = web_client.get("/clientes/99/dashboard/contabilidad", follow_redirects=False)
    assert resp.status_code == 302


def test_editar_usuario_carga_correctamente(web_client):
    """GET /admin/usuarios/<id>/editar retorna 200 y contiene 'Clientes asignados'."""
    from unittest.mock import patch
    with web_client.session_transaction() as sess:
        sess["_user_id"] = "master-uuid"
        sess["_user_email"] = "master@test.com"
        sess["_user_rol"] = "master_admin"
        sess["_empresa_id"] = None
        sess["_clientes_ids"] = []
        sess["_session_version"] = 1

    target_data = {
        "id": "target-uuid", "email": "cli@test.com",
        "rol": "usuario_normal", "empresa_id": 5,
        "nombre": "Test", "apellido": "User", "activo": True,
    }
    with patch("web.auth._verificar_activo_con_cache", return_value=True), \
         patch("web.auth._verificar_session_version_con_cache", return_value=True), \
         patch("storage.repository._supabase") as mock_sb, \
         patch("storage.repository.get_all_clientes_con_conteos", return_value=[{"id": 5, "nombre": "Empresa A", "num_facturas_cfe": 0, "num_facturas_gas": 0}]), \
         patch("storage.repository.get_clientes_de_usuario", return_value=[{"id": 5, "nombre": "Empresa A"}]):
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [target_data]
        mock_sb.postgrest.auth.return_value = None
        resp = web_client.get("/admin/usuarios/target-uuid/editar", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Clientes asignados" in resp.data
