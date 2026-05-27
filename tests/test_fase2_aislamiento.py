# tests/test_fase2_aislamiento.py
"""Tests de aislamiento de fase 2 (telemetría).

Cubre:
a) Decorador devuelve 404 con flag=false (cualquier rol).
b) Decorador permite 200 con flag=true y master_admin.
c) Decorador devuelve 403 con flag=true y admin.
d) Decorador devuelve 403 con flag=true y usuario_normal.
e) before_request redirige (302) con flag=true y sin usuario logueado (login_required precede al decorador).
f) Context processor inyecta 'fase2_habilitada' con el valor correcto.
g) Sidebar NO muestra "Telemetría (Beta)" con flag=false y master_admin.
h) Sidebar NO muestra "Telemetría (Beta)" con flag=true y admin.
i) Sidebar SÍ muestra "Telemetría (Beta)" con flag=true y master_admin.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_app(fase2: bool):
    import os
    os.environ["SUPABASE_URL"] = "https://fake.supabase.co"
    os.environ["SUPABASE_KEY"] = "fake_key"
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["FASE2_HABILITADA"] = "true" if fase2 else "false"

    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


def _inject_session(client, rol: str | None = None):
    from time import time
    with client.session_transaction() as sess:
        if rol is None:
            sess.clear()
            return
        uid = "test-user-uuid"
        now = time()
        sess["_user_id"] = uid
        sess["_user_email"] = f"{rol}@test.com"
        sess["_user_rol"] = rol
        sess["_empresa_id"] = None
        sess["_session_version"] = 1
        # Evitar que before_request consulte BD (cache TTL = 5 min)
        sess["_activo_check"] = {"user_id": uid, "ts": now, "activo": True}
        sess["_sv_check"] = {"user_id": uid, "ts": now, "version": 1}


def _add_dummy_route(app):
    """Añade /admin/__fase2_test protegida con el decorador al app de test."""
    from web.auth_permissions import require_master_admin_y_fase2

    @app.route("/admin/__fase2_test")
    @require_master_admin_y_fase2
    def _fase2_test_view():
        return "ok", 200


def _mock_supabase_empty():
    """MagicMock de supabase que devuelve listas vacías para cualquier query."""
    mock = MagicMock()
    result = MagicMock()
    result.data = []
    result.count = 0
    # Encadenamientos comunes: .table().select().xxx.execute()
    chain = mock.table.return_value.select.return_value
    for attr in ("order", "eq", "limit", "range", "ilike", "gte", "lte",
                 "neq", "contains", "execute"):
        getattr(chain, attr).return_value = chain
    chain.execute.return_value = result
    mock.postgrest = MagicMock()
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def app_flag_off():
    return _make_app(fase2=False)


@pytest.fixture()
def app_flag_on():
    return _make_app(fase2=True)


@pytest.fixture()
def client_off(app_flag_off):
    _add_dummy_route(app_flag_off)
    return app_flag_off.test_client()


@pytest.fixture()
def client_on(app_flag_on):
    _add_dummy_route(app_flag_on)
    return app_flag_on.test_client()


# ── Tests a-e: decorador ──────────────────────────────────────────────────────

def test_a_decorador_404_cuando_flag_off(client_off):
    """a) flag=false → 404 para master_admin."""
    _inject_session(client_off, "master_admin")
    resp = client_off.get("/admin/__fase2_test")
    assert resp.status_code == 404


def test_b_decorador_permite_master_admin_con_flag_on(client_on):
    """b) flag=true + master_admin → 200."""
    _inject_session(client_on, "master_admin")
    resp = client_on.get("/admin/__fase2_test")
    assert resp.status_code == 200
    assert resp.data == b"ok"


def test_c_decorador_403_admin_con_flag_on(client_on):
    """c) flag=true + admin → 403."""
    _inject_session(client_on, "admin")
    resp = client_on.get("/admin/__fase2_test")
    assert resp.status_code == 403


def test_d_decorador_403_usuario_normal_con_flag_on(client_on):
    """d) flag=true + usuario_normal → 403."""
    _inject_session(client_on, "usuario_normal")
    resp = client_on.get("/admin/__fase2_test")
    assert resp.status_code == 403


def test_e_decorador_redirige_sin_usuario_con_flag_on(client_on):
    """e) flag=true + sin usuario logueado → 302 (before_request redirige a login)."""
    _inject_session(client_on, None)
    resp = client_on.get("/admin/__fase2_test")
    assert resp.status_code == 302


# ── Test f: context processor ─────────────────────────────────────────────────

def test_f_context_processor_inyecta_flag(app_flag_off, app_flag_on):
    """f) Context processor inyecta 'fase2_habilitada' con el valor correcto."""
    with app_flag_off.test_request_context("/"):
        with app_flag_off.app_context():
            ctx = {}
            for func in app_flag_off.template_context_processors[None]:
                ctx.update(func())
            assert ctx.get("fase2_habilitada") is False

    with app_flag_on.test_request_context("/"):
        with app_flag_on.app_context():
            ctx = {}
            for func in app_flag_on.template_context_processors[None]:
                ctx.update(func())
            assert ctx.get("fase2_habilitada") is True


# ── Tests g-i: sidebar ────────────────────────────────────────────────────────

def _get_clientes_page(client, rol: str, mock_sub):
    """Hace GET /clientes/ autenticado, con supabase mockeado."""
    _inject_session(client, rol)
    with patch("storage.repository._supabase", mock_sub):
        resp = client.get("/clientes/", follow_redirects=False)
    return resp


def test_g_sidebar_no_muestra_fase2_con_flag_off(app_flag_off):
    """g) flag=false, master_admin → 'Telemetría (Beta)' NO aparece en sidebar."""
    mock_sub = _mock_supabase_empty()
    client = app_flag_off.test_client()
    resp = _get_clientes_page(client, "master_admin", mock_sub)
    assert b"Telemetr" not in resp.data


def test_h_sidebar_no_muestra_fase2_con_flag_on_y_admin(app_flag_on):
    """h) flag=true, admin → 'Telemetría (Beta)' NO aparece."""
    mock_sub = _mock_supabase_empty()
    client = app_flag_on.test_client()
    resp = _get_clientes_page(client, "admin", mock_sub)
    assert b"Telemetr" not in resp.data


def test_i_sidebar_muestra_fase2_con_flag_on_y_master_admin(app_flag_on):
    """i) flag=true, master_admin → 'Telemetría (Beta)' SÍ aparece."""
    mock_sub = _mock_supabase_empty()
    client = app_flag_on.test_client()
    resp = _get_clientes_page(client, "master_admin", mock_sub)
    assert b"Telemetr" in resp.data
