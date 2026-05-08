# tests/test_dashboard_2d.py
"""Tests para sub-entregable 2-d: selección de facturas, sesión activa y dashboard filtrado."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from werkzeug.security import generate_password_hash

from models.contrato import Contrato

_HASH = generate_password_hash("test_pass", method="pbkdf2:sha256")

_CLIENTE = {
    "id": 1,
    "nombre": "IBERICA TILES",
    "rfc": "ITI930101AAA",
    "notas": None,
    "created_at": "2024-01-15T10:00:00+00:00",
    "num_cfe": 3,
    "num_gas": 2,
    "logo_url": None,
    "sector_industrial": None,
    "contacto_nombre": None,
    "contacto_cargo": None,
    "contacto_email": None,
    "contacto_telefono": None,
    "direccion": None,
    "estado": None,
    "codigo_postal": None,
    "tarifa_cfe": None,
    "capacidad_instalada_kw": None,
    "demanda_contratada_kw": None,
    "anio_inicio_operacion": None,
    "regimen_operacion": None,
    "consumo_anual_estimado_mwh": None,
}

_CLIENTE_VACIO = {**_CLIENTE, "num_cfe": 0, "num_gas": 0}

_CONTRATO_ELECTRICO = Contrato(
    id=10,
    cliente_id=1,
    nombre="CFE Planta 1",
    tipo="electrico",
    identificador_real="812990300016",
    notas=None,
    created_at="2024-01-15T10:00:00+00:00",
)


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("APP_USER", "operador")
    monkeypatch.setenv("APP_PASSWORD_HASH", _HASH)
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


def _login(app, monkeypatch):
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda id: [_CONTRATO_ELECTRICO])
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})
    return c


# ── Test 1: GET ficha NO activa cliente en sesión ─────────────────────────────

def test_ficha_activa_cliente_en_sesion(app, monkeypatch):
    """GET /clientes/1 → ya NO activa cliente en sesión (activación es por checkbox AJAX)."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contratos_por_cliente", lambda id: [])
    c = _login(app, monkeypatch)

    resp = c.get("/clientes/1", follow_redirects=False)
    assert resp.status_code == 200

    with c.session_transaction() as sess:
        assert sess.get("cliente_activo_id") is None


# ── Test 2: Borrar cliente limpia la sesión ───────────────────────────────────

def test_borrar_cliente_activo_limpia_sesion(app, monkeypatch):
    """POST /clientes/1/borrar con cliente activo en sesión → sesión limpiada."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contratos_por_cliente", lambda id: [])
    monkeypatch.setattr("web.clientes.delete_cliente", lambda id: None)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    # Establecer cliente activo directamente en sesión
    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    # Borrar cliente
    resp = c.post("/clientes/1/borrar",
                  data={"confirmacion": "IBERICA TILES"},
                  follow_redirects=False)
    assert resp.status_code == 302

    with c.session_transaction() as sess:
        assert sess.get("cliente_activo_id") is None
        assert sess.get("cliente_activo_nombre") is None


# ── Test 3: Toggle selección individual ──────────────────────────────────────

def test_toggle_seleccion_individual(app, monkeypatch):
    """PATCH /seleccion → llama a update_factura_seleccionada con los parámetros correctos."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    llamadas = []
    monkeypatch.setattr(
        "web.clientes.update_factura_seleccionada",
        lambda factura_id, tipo, seleccionada: llamadas.append((factura_id, tipo, seleccionada)),
    )
    c = _login(app, monkeypatch)

    resp = c.patch(
        "/clientes/1/contratos/10/facturas/42/seleccion",
        json={"seleccionada": False, "tipo": "cfe"},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["seleccionada"] is False
    assert llamadas == [(42, "cfe", False)]


def test_toggle_seleccion_tipo_invalido(app, monkeypatch):
    """PATCH /seleccion con tipo inválido → 400."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    c = _login(app, monkeypatch)

    resp = c.patch(
        "/clientes/1/contratos/10/facturas/42/seleccion",
        json={"seleccionada": True, "tipo": "invalido"},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── Test 4: Selección masiva ──────────────────────────────────────────────────

def test_seleccion_masiva(app, monkeypatch):
    """PATCH /seleccion-masiva → llama a update_facturas_seleccion_masiva y devuelve actualizadas."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    monkeypatch.setattr(
        "web.clientes.update_facturas_seleccion_masiva",
        lambda contrato_id, seleccionada: 3,
    )
    c = _login(app, monkeypatch)

    resp = c.patch(
        "/clientes/1/contratos/10/facturas/seleccion-masiva",
        json={"seleccionada": False},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["actualizadas"] == 3
    assert data["seleccionada"] is False


def test_seleccion_masiva_sin_bool(app, monkeypatch):
    """PATCH /seleccion-masiva con seleccionada=null → 400."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    c = _login(app, monkeypatch)

    resp = c.patch(
        "/clientes/1/contratos/10/facturas/seleccion-masiva",
        json={"seleccionada": "si"},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── Test 5: Dashboard con facturas seleccionadas → muestra KPIs ───────────────

def _mock_resultado_con_meses():
    from decimal import Decimal
    mes = MagicMock()
    mes.periodo_inicio.strftime.return_value = "Ene 2024"
    mes.ebitda_mes_mxn = Decimal("100000")
    mes.ahorro_electricidad_mxn = Decimal("80000")
    mes.ahorro_caldera_mxn = Decimal("40000")
    mes.costo_gas_cogen_mxn = Decimal("20000")
    mes.kwh_total = Decimal("50000")
    mes.costo_cfe_mxn = Decimal("200000")
    mes.costo_promedio_kwh = Decimal("4.0")
    mes.gj_consumido = Decimal("100")
    mes.costo_unitario_gj = Decimal("150")
    mes.costo_gas_actual_mxn = Decimal("15000")
    mes.kwh_cubiertos = Decimal("37500")
    mes.gj_gas_cogen = Decimal("337.5")
    mes.calor_recuperado_gj = Decimal("84.375")
    mes.prorrateado = False
    mes.nota_prorrateo = ""

    resultado = MagicMock()
    resultado.meses = [mes]
    resultado.ebitda_anual_mxn = Decimal("100000")
    resultado.ahorro_electricidad_anual_mxn = Decimal("80000")
    resultado.ahorro_caldera_anual_mxn = Decimal("40000")
    resultado.costo_gas_cogen_anual_mxn = Decimal("20000")
    resultado.kwh_total_anual = Decimal("50000")
    resultado.kwh_cubiertos_anual = Decimal("37500")
    resultado.gj_gas_cogen_anual = Decimal("337.5")
    resultado.params.cobertura_electrica = 0.75
    resultado.params.rendimiento_electrico = 0.40
    resultado.params.rendimiento_termico = 0.25
    resultado.params.eficiencia_caldera = 0.85
    return resultado


def _mock_historico():
    """Objeto historico serializable para el template (usa tojson en JS)."""
    class Historico:
        tabla_punta = []
        labels = []
        demanda_punta = []
        demanda_intermedio = []
        demanda_base = []
        costo_unit_mes = []
        consumo_base = []
        consumo_intermedio = []
        consumo_punta = []
        costo_unit_promedio = {"base": 0.0, "intermedio": 0.0, "punta": 0.0}

        def __iter__(self):
            return iter(self.__dict__.items())

    # Devolver un dict plano que Jinja tojson pueda serializar
    return {
        "tabla_punta": [],
        "labels": [],
        "demanda_punta": [],
        "demanda_intermedio": [],
        "demanda_base": [],
        "costo_unit_mes": [],
        "consumo_base": [],
        "consumo_intermedio": [],
        "consumo_punta": [],
        "costo_unit_promedio": {"base": 0.0, "intermedio": 0.0, "punta": 0.0},
    }


def _mock_tablas():
    class _Tablas:
        consumos_demandas = []
        costos_detallados = []
        indicadores = []
    return _Tablas()


def _facturas_cfe_mock():
    return [{"nombre_canonico": "2024 ENE CFE TEST", "periodo": "01 Jan 2024 – 31 Jan 2024",
             "mes_asociado": "Ene 2024", "kwh_total": 50000.0, "costo_mxn": 200000.0, "prorrateado": False}]


def _facturas_gas_mock():
    return [{"nombre_canonico": "2024 ENE GAS TEST", "periodo": "01 Jan 2024 – 31 Jan 2024",
             "mes_asociado": "Ene 2024", "gj_total": 100.0, "costo_mxn": 15000.0, "prorrateado": False}]


def test_dashboard_con_datos_muestra_kpis(app, monkeypatch):
    """Dashboard con facturas seleccionadas → renderiza KPIs sin aviso."""
    monkeypatch.setattr(
        "web.app._cargar_datos_cliente",
        lambda cliente_id: (_mock_resultado_con_meses(), _facturas_cfe_mock(), _facturas_gas_mock(),
                            _mock_historico(), _mock_tablas()),
    )
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard")
    assert resp.status_code == 200
    assert b"EBITDA Anual" in resp.data
    assert b"Sin facturas seleccionadas" not in resp.data


# ── Test 6: Dashboard sin selección → aviso sin KPIs ─────────────────────────

def test_dashboard_sin_seleccion_muestra_aviso(app, monkeypatch):
    """Dashboard con cero facturas seleccionadas → aviso sin_seleccion, sin KPIs."""
    monkeypatch.setattr(
        "web.app._cargar_datos_cliente",
        lambda cliente_id: (MagicMock(meses=[]), [], [], _mock_historico(), _mock_tablas()),
    )
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard")
    assert resp.status_code == 200
    assert "Sin facturas seleccionadas".encode() in resp.data
    assert b"EBITDA Anual" not in resp.data


# ── Test 7: Dashboard sin facturas en DB → aviso sin_facturas ────────────────

def test_dashboard_sin_facturas_en_bd(app, monkeypatch):
    """Dashboard con cliente sin facturas en BD → aviso sin_facturas."""
    monkeypatch.setattr(
        "web.app._cargar_datos_cliente",
        lambda cliente_id: (MagicMock(meses=[]), [], [], _mock_historico(), _mock_tablas()),
    )
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_VACIO)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard")
    assert resp.status_code == 200
    assert "Sin facturas cargadas".encode() in resp.data


# ── Test 8: Dashboard con cliente_id incorrecto → redirect ───────────────────

def test_dashboard_cliente_id_no_coincide_con_sesion(app, monkeypatch):
    """GET /clientes/2/dashboard cuando sesión tiene cliente_activo_id=1 → redirect con flash."""
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/2/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes" in resp.headers["Location"]


# ── Test 9: Sidebar muestra sección contextual cuando hay cliente activo ──────

def test_sidebar_muestra_seccion_cliente_activo(app, monkeypatch):
    """Cualquier página renderizada con cliente_activo en sesión muestra nombre en sidebar."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE])
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/")
    assert resp.status_code == 200
    assert b"IBERICA TILES" in resp.data


def test_sidebar_no_muestra_seccion_sin_cliente_activo(app, monkeypatch):
    """Sin cliente activo en sesión, el sidebar no muestra la sección contextual."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE])
    c = _login(app, monkeypatch)

    # Sin cliente activo en sesión
    resp = c.get("/clientes/")
    assert resp.status_code == 200
    # "Ficha" y "Dashboard" como links del sidebar contextual no deben aparecer
    # (el listado sí muestra "IBERICA TILES" como nombre de cliente, pero no el enlace de sidebar)
    html = resp.data.decode()
    assert 'sidebar-section' not in html or 'IBERICA TILES' not in html.split('sidebar-section')[1].split('sidebar-bottom')[0] if 'sidebar-section' in html and 'sidebar-bottom' in html else True


# ── Test 10-11: Dashboard header con/sin logo ─────────────────────────────────

def test_dashboard_con_logo_muestra_imagen(app, monkeypatch):
    """Dashboard con cliente que tiene logo → header muestra la imagen."""
    cliente_con_logo = {**_CLIENTE, "logo_url": "https://storage.example.com/cliente_1.png"}
    monkeypatch.setattr(
        "web.app._cargar_datos_cliente",
        lambda cliente_id: (MagicMock(meses=[]), [], [], _mock_historico(), _mock_tablas()),
    )
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: cliente_con_logo)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard")
    assert resp.status_code == 200
    assert b"storage.example.com/cliente_1.png" in resp.data


def test_dashboard_sin_logo_muestra_nombre(app, monkeypatch):
    """Dashboard con cliente sin logo → header muestra el nombre como texto."""
    monkeypatch.setattr(
        "web.app._cargar_datos_cliente",
        lambda cliente_id: (MagicMock(meses=[]), [], [], _mock_historico(), _mock_tablas()),
    )
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_VACIO)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard")
    assert resp.status_code == 200
    assert b"IBERICA TILES" in resp.data
    # sin logo no debe aparecer un <img> de Storage
    assert b"storage.example.com" not in resp.data
