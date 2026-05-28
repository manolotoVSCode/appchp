# tests/test_telemetria_vista.py
"""Tests para las rutas de Telemetría (Fase 2) — solo lectura + sembrado sintético."""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")

_MEDIDOR_FIXTURE = {
    "id": 1,
    "cliente_id": 10,
    "nombre": "Medidor Planta Norte",
    "punto_medicion": "MPN-01",
    "ubicacion": "Cuarto eléctrico N",
    "numero_serie": "ACC2024001",
    "relacion_tc": 200.0,
    "marca": "Accuenergy",
    "modelo": "Acuvim II",
    "activo": True,
    "creado_en": "2026-06-01T00:00:00+00:00",
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FASE2_HABILITADA", "true")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture()
def app_fase2_off(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FASE2_HABILITADA", "false")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


def _client_master_admin(flask_app):
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "master-uuid"
        sess["_user_email"] = "master@test.com"
        sess["_user_rol"] = "master_admin"
        sess["_empresa_id"] = None
    return c


def _client_admin(flask_app):
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "admin-uuid"
        sess["_user_email"] = "admin@test.com"
        sess["_user_rol"] = "admin"
        sess["_empresa_id"] = None
    return c


def _client_usuario_normal(flask_app):
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "user-uuid"
        sess["_user_email"] = "user@test.com"
        sess["_user_rol"] = "usuario_normal"
        sess["_empresa_id"] = 1
    return c


# ── Test a: FASE2_HABILITADA=false → 404 ─────────────────────────────────────

def test_a_telemetria_index_sin_flag_devuelve_404(app_fase2_off):
    client = _client_master_admin(app_fase2_off)
    with patch("storage.repository.get_all_clientes_con_conteos", return_value=[]):
        resp = client.get("/admin/telemetria")
    assert resp.status_code == 404


# ── Test b: flag activa, rol no master_admin → redirect ──────────────────────

def test_b_telemetria_index_admin_redirige(app):
    client = _client_admin(app)
    with patch("storage.repository.get_all_clientes_con_conteos", return_value=[]):
        resp = client.get("/admin/telemetria")
    assert resp.status_code == 302


def test_b_telemetria_index_usuario_normal_redirige(app):
    client = _client_usuario_normal(app)
    with patch("storage.repository.get_all_clientes_con_conteos", return_value=[]):
        resp = client.get("/admin/telemetria")
    assert resp.status_code == 302


# ── Test c: flag activa, master_admin → 200 ──────────────────────────────────

def test_c_telemetria_index_master_admin_ok(app):
    client = _client_master_admin(app)
    with patch("storage.repository.get_all_clientes_con_conteos", return_value=[]):
        resp = client.get("/admin/telemetria")
    assert resp.status_code == 200
    assert b"Telemetr" in resp.data


# ── Test d: medidor inexistente → redirect a index con flash ─────────────────

def test_d_telemetria_medidor_inexistente_redirige(app):
    client = _client_master_admin(app)
    with patch("storage.repository.obtener_medidor", return_value=None):
        resp = client.get("/admin/telemetria/medidor/999")
    assert resp.status_code == 302
    assert "/admin/telemetria" in resp.headers["Location"]


# ── Test e: sembrado inserta 96 mediciones con claves exactas y rangos válidos ─

_COLUMNAS_ESPERADAS = frozenset({
    "medidor_id", "timestamp",
    "potencia_activa_kw", "potencia_reactiva_kvar", "potencia_aparente_kva",
    "factor_potencia",
    "energia_activa_importada_kwh", "energia_activa_exportada_kwh",
    "energia_reactiva_importada_kvarh", "energia_reactiva_exportada_kvarh",
    "voltaje_l1_v", "voltaje_l2_v", "voltaje_l3_v",
    "corriente_l1_a", "corriente_l2_a", "corriente_l3_a",
    "frecuencia_hz", "secuencia_fases",
})


def test_e_sembrar_inserta_96_mediciones(app):
    captured: list[list] = []

    def _fake_batch(lista):
        captured.append(lista)
        return len(lista)

    client = _client_master_admin(app)
    with patch("storage.repository.obtener_medidor", return_value=_MEDIDOR_FIXTURE), \
         patch("storage.repository.insertar_mediciones_batch", side_effect=_fake_batch):
        resp = client.post("/admin/telemetria/medidor/1/sembrar")

    assert resp.status_code == 302
    assert len(captured) == 1
    mediciones = captured[0]
    assert len(mediciones) == 96

    for m in mediciones:
        # Claves exactas del esquema real — ni de más ni de menos
        assert set(m.keys()) == _COLUMNAS_ESPERADAS, (
            f"Claves incorrectas: extras={set(m.keys()) - _COLUMNAS_ESPERADAS}, "
            f"faltan={_COLUMNAS_ESPERADAS - set(m.keys())}"
        )
        fp = m["factor_potencia"]
        assert 0.88 <= fp <= 0.97, f"fp fuera de rango: {fp}"
        freq = m["frecuencia_hz"]
        assert 59.95 <= freq <= 60.05, f"frecuencia fuera de rango: {freq}"
        for col in ("voltaje_l1_v", "voltaje_l2_v", "voltaje_l3_v"):
            v = m[col]
            assert 13_662 <= v <= 13_938, f"{col} fuera de rango: {v}"
        assert m["energia_activa_exportada_kwh"] == 0.0
        assert m["energia_reactiva_exportada_kvarh"] == 0.0

    # Energía importada debe ser monótonamente creciente
    kwh_vals = [m["energia_activa_importada_kwh"] for m in mediciones]
    for i in range(1, len(kwh_vals)):
        assert kwh_vals[i] > kwh_vals[i - 1], f"kwh no monótono en índice {i}"


# ── Test f: sembrar sin master_admin → redirect ───────────────────────────────

def test_f_sembrar_sin_master_admin_redirige(app):
    client = _client_admin(app)
    with patch("storage.repository.obtener_medidor", return_value=_MEDIDOR_FIXTURE), \
         patch("storage.repository.insertar_mediciones_batch", return_value=0):
        resp = client.post("/admin/telemetria/medidor/1/sembrar")
    assert resp.status_code == 302
    assert "/admin/telemetria" not in resp.headers.get("Location", "")
