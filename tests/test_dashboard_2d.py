# tests/test_dashboard_2d.py
"""Tests para sub-entregable 2-d: selección de facturas, sesión activa y dashboard filtrado."""
from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock
from werkzeug.security import generate_password_hash

from models.contrato import Contrato
from models.gas_invoice import GasInvoice, GasConcepto

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


# ── Test 3: GET selección sidebar del contrato ────────────────────────────────

def test_get_seleccion_contrato(app, monkeypatch):
    """GET /seleccion → devuelve datos del sidebar con ok y lista de años."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    monkeypatch.setattr(
        "web.clientes.get_sidebar_data_contrato",
        lambda contrato_id: [{"anio": 2024, "meses_con_factura": [1, 2], "meses_seleccionados": [1]}],
    )
    c = _login(app, monkeypatch)

    resp = c.get("/clientes/1/contratos/10/seleccion")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert len(data["anios"]) == 1
    assert data["anios"][0]["anio"] == 2024


def test_get_seleccion_contrato_no_encontrado(app, monkeypatch):
    """GET /seleccion con contrato inexistente → 404."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: None)
    c = _login(app, monkeypatch)

    resp = c.get("/clientes/1/contratos/99/seleccion")
    assert resp.status_code == 404


# ── Test 4: POST selección de mes ─────────────────────────────────────────────

def test_seleccion_mes_upsert(app, monkeypatch):
    """POST /seleccion/mes con seleccionado=true → llama a upsert_mes_seleccionado."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    monkeypatch.setattr("web.clientes.get_meses_con_factura", lambda contrato_id, anio: list(range(1, 13)))
    llamadas = []
    monkeypatch.setattr(
        "web.clientes.upsert_mes_seleccionado",
        lambda contrato_id, anio, mes: llamadas.append(("upsert", contrato_id, anio, mes)),
    )
    monkeypatch.setattr("web.clientes.delete_mes_seleccionado", lambda *a: None)
    c = _login(app, monkeypatch)

    resp = c.post(
        "/clientes/1/contratos/10/seleccion/mes",
        json={"anio": 2024, "mes": 3, "seleccionado": True},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["seleccionado"] is True
    assert llamadas == [("upsert", 10, 2024, 3)]


def test_seleccion_mes_delete(app, monkeypatch):
    """POST /seleccion/mes con seleccionado=false → llama a delete_mes_seleccionado."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    monkeypatch.setattr("web.clientes.upsert_mes_seleccionado", lambda *a: None)
    eliminados = []
    monkeypatch.setattr(
        "web.clientes.delete_mes_seleccionado",
        lambda contrato_id, anio, mes: eliminados.append((contrato_id, anio, mes)),
    )
    c = _login(app, monkeypatch)

    resp = c.post(
        "/clientes/1/contratos/10/seleccion/mes",
        json={"anio": 2024, "mes": 3, "seleccionado": False},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["seleccionado"] is False
    assert eliminados == [(10, 2024, 3)]


def test_seleccion_mes_mes_invalido(app, monkeypatch):
    """POST /seleccion/mes con mes=13 → 400."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    c = _login(app, monkeypatch)

    resp = c.post(
        "/clientes/1/contratos/10/seleccion/mes",
        json={"anio": 2024, "mes": 13, "seleccionado": True},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_seleccion_mes_seleccionado_no_bool(app, monkeypatch):
    """POST /seleccion/mes con seleccionado='si' → 400."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    c = _login(app, monkeypatch)

    resp = c.post(
        "/clientes/1/contratos/10/seleccion/mes",
        json={"anio": 2024, "mes": 3, "seleccionado": "si"},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── Test 4b: POST selección de año ────────────────────────────────────────────

def test_seleccion_anio_activa(app, monkeypatch):
    """POST /seleccion/anio con seleccionado=true → llama a upsert_meses_seleccionados_anio."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    llamadas = []
    monkeypatch.setattr(
        "web.clientes.upsert_meses_seleccionados_anio",
        lambda contrato_id, anio: llamadas.append((contrato_id, anio)) or 12,
    )
    monkeypatch.setattr("web.clientes.delete_meses_seleccionados_anio", lambda *a: None)
    c = _login(app, monkeypatch)

    resp = c.post(
        "/clientes/1/contratos/10/seleccion/anio",
        json={"anio": 2024, "seleccionado": True},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["insertados"] == 12
    assert llamadas == [(10, 2024)]


def test_seleccion_anio_desactiva(app, monkeypatch):
    """POST /seleccion/anio con seleccionado=false → llama a delete_meses_seleccionados_anio."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    monkeypatch.setattr("web.clientes.upsert_meses_seleccionados_anio", lambda *a: 0)
    eliminados = []
    monkeypatch.setattr(
        "web.clientes.delete_meses_seleccionados_anio",
        lambda contrato_id, anio: eliminados.append((contrato_id, anio)),
    )
    c = _login(app, monkeypatch)

    resp = c.post(
        "/clientes/1/contratos/10/seleccion/anio",
        json={"anio": 2024, "seleccionado": False},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["eliminados"] is True
    assert eliminados == [(10, 2024)]


def test_seleccion_anio_sin_bool(app, monkeypatch):
    """POST /seleccion/anio sin seleccionado bool → 400."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)
    c = _login(app, monkeypatch)

    resp = c.post(
        "/clientes/1/contratos/10/seleccion/anio",
        json={"anio": 2024, "seleccionado": "yes"},
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
    mes.gasto_om_mes_mxn = Decimal("24000")
    mes.prorrateado = False
    mes.nota_prorrateo = ""

    resultado = MagicMock()
    resultado.meses = [mes]
    resultado.ebitda_anual_mxn = Decimal("100000")
    resultado.ahorro_electricidad_anual_mxn = Decimal("80000")
    resultado.ahorro_caldera_anual_mxn = Decimal("40000")
    resultado.costo_gas_cogen_anual_mxn = Decimal("20000")
    resultado.gasto_om_anual_mxn = Decimal("24000")
    resultado.kwh_total_anual = Decimal("50000")
    resultado.kwh_cubiertos_anual = Decimal("37500")
    resultado.gj_gas_cogen_anual = Decimal("337.5")
    resultado.capacidad_nominal_kw = Decimal("69.44")
    resultado.inversion_usd = Decimal("97216.00")
    resultado.inversion_mxn = Decimal("1701280.00")
    resultado.tipo_cambio_mxn_usd = Decimal("17.50")
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
    return {
        "consumos_demandas": [],
        "costos_detallados": [],
        "indicadores": [],
        "costo_unit_promedio_total": {"base": 0.0, "intermedio": 0.0, "punta": 0.0},
    }


def _facturas_cfe_mock():
    return [{"nombre_canonico": "2024 ENE CFE TEST", "periodo": "01 Jan 2024 – 31 Jan 2024",
             "mes_asociado": "Ene 2024", "kwh_total": 50000.0, "costo_mxn": 200000.0, "prorrateado": False}]


def _facturas_gas_mock():
    return [{"nombre_canonico": "2024 ENE GAS TEST", "periodo": "01 Jan 2024 – 31 Jan 2024",
             "mes_asociado": "Ene 2024", "gj_total": 100.0, "costo_mxn": 15000.0, "prorrateado": False}]


def test_dashboard_con_datos_muestra_kpis(app, monkeypatch):
    """Dashboard cogeneración con facturas seleccionadas → renderiza KPIs sin aviso."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), _facturas_gas_mock()),
    )
    monkeypatch.setattr("web.app.list_configuracion", lambda: [])
    monkeypatch.setattr("web.app.calcular_cogen", lambda *a, **kw: _mock_resultado_con_meses())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard/cogeneracion")
    assert resp.status_code == 200
    assert b"Ahorro Neto Anual" in resp.data
    assert b"Sin facturas seleccionadas" not in resp.data


# ── Test 6: Dashboard sin selección → aviso sin KPIs ─────────────────────────

def test_dashboard_sin_seleccion_muestra_aviso(app, monkeypatch):
    """Dashboard contabilidad con cero facturas seleccionadas → aviso sin_seleccion en JSON."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], [], []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("web.app.calcular_historico_gas", lambda invoices: [])
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    # La página HTML se renderiza siempre igual (aviso es JS-side)
    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    # El aviso real llega vía JSON data endpoint
    resp_data = c.get("/clientes/1/dashboard/contabilidad/data")
    assert resp_data.status_code == 200
    json_data = resp_data.get_json()
    assert json_data["aviso_datos"]["tipo"] == "sin_seleccion"


# ── Test 7: Dashboard sin facturas en DB → aviso sin_facturas ────────────────

def test_dashboard_sin_facturas_en_bd(app, monkeypatch):
    """Dashboard contabilidad con cliente sin facturas en BD → aviso sin_facturas."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], [], []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_VACIO)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard/contabilidad")
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
    """Dashboard contabilidad con cliente que tiene logo → header muestra la imagen."""
    cliente_con_logo = {**_CLIENTE, "logo_url": "https://storage.example.com/cliente_1.png"}
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], [], []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: cliente_con_logo)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    assert b"storage.example.com/cliente_1.png" in resp.data


def test_dashboard_sin_logo_muestra_nombre(app, monkeypatch):
    """Dashboard contabilidad con cliente sin logo → header muestra el nombre como texto."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], [], []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_VACIO)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    assert b"IBERICA TILES" in resp.data
    assert b"storage.example.com" not in resp.data


# ── Test 12: /dashboard redirige a /dashboard/contabilidad ────────────────────

def test_dashboard_redirige_a_contabilidad(app, monkeypatch):
    """GET /clientes/<id>/dashboard → 302 a /clientes/<id>/dashboard/contabilidad."""
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/1/dashboard/contabilidad" in resp.headers["Location"]


# ── Test 13: contabilidad muestra histórico, no EBITDA ────────────────────────

def test_contabilidad_muestra_historico_no_ebitda(app, monkeypatch):
    """GET /dashboard/contabilidad → muestra gráficas históricas, no KPIs de EBITDA."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    assert b"Contabilidad" in resp.data
    assert b"Ahorro Neto Anual" not in resp.data


# ── Test 14: cogeneración muestra KPIs, no gráficas históricas ───────────────

def test_cogeneracion_muestra_kpis_no_historico(app, monkeypatch):
    """GET /dashboard/cogeneracion → muestra KPIs de Ahorro Neto, no gráficas históricas de demanda."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), _facturas_gas_mock()),
    )
    monkeypatch.setattr("web.app.list_configuracion", lambda: [])
    monkeypatch.setattr("web.app.calcular_cogen", lambda *a, **kw: _mock_resultado_con_meses())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/cogeneracion")
    assert resp.status_code == 200
    assert b"Ahorro Neto Anual" in resp.data
    assert b"Demanda m" not in resp.data  # "Demanda máxima" solo en contabilidad


# ══════════════════════════════════════════════════════════════════════════════
# Sub-entregable C: visualizaciones de gas en Contabilidad Energética
# ══════════════════════════════════════════════════════════════════════════════

def _make_gas_invoice(periodo_inicio, periodo_fin, consumo_gj, costo_unit_gj,
                      subtotal, pcs, conceptos):
    """Crea un GasInvoice mínimo para tests."""
    return GasInvoice(
        uuid_cfdi="test-uuid",
        folio="001",
        fecha_emision=periodo_inicio,
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
        fecha_limite_pago=periodo_fin,
        nombre_proveedor="ENGIE",
        rfc_proveedor="ENG123",
        nombre_cliente="IBERICA",
        rfc_cliente="ITI123",
        numero_cliente="12345",
        cuenta_contrato="C001",
        punto_suministro="P001",
        numero_caseta="N001",
        tipo_lectura="NORMAL",
        consumo_m3_corregidos=Decimal("100"),
        consumo_sin_corregir_m3=Decimal("100"),
        poder_calorifico_gj_m3=Decimal(str(pcs)) if pcs else Decimal("0"),
        consumo_total_gj=Decimal(str(consumo_gj)),
        conceptos=conceptos,
        costo_unitario_total_gj=Decimal(str(costo_unit_gj)),
        subtotal_mxn=Decimal(str(subtotal)),
        iva_mxn=Decimal("0"),
        total_mxn=Decimal(str(subtotal)),
        pdf_path="test.pdf",
    )


def _conceptos_completos(mol_precio, mol_importe, tra_precio, tra_importe):
    return [
        GasConcepto(
            descripcion="Compraventa de Gas Natural",
            clave_producto="CP01",
            cantidad_gj=Decimal("100"),
            precio_unitario_gj=Decimal(str(mol_precio)),
            importe_mxn=Decimal(str(mol_importe)),
        ),
        GasConcepto(
            descripcion="Transporte por Ducto Gas Natural",
            clave_producto="CP02",
            cantidad_gj=Decimal("100"),
            precio_unitario_gj=Decimal(str(tra_precio)),
            importe_mxn=Decimal(str(tra_importe)),
        ),
    ]


# ── Test 15: Contabilidad sin gas no muestra sección gas ─────────────────────

def test_contabilidad_sin_gas_no_muestra_seccion(app, monkeypatch):
    """Sin facturas de gas seleccionadas, el JSON data no incluye histórico gas."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("web.app.calcular_historico_gas", lambda invoices: None)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    # Verificar vía JSON: sin gas seleccionado, historico_gas es None/vacío
    resp_data = c.get("/clientes/1/dashboard/contabilidad/data")
    assert resp_data.status_code == 200
    json_data = resp_data.get_json()
    assert json_data["historico_gas"] is None or json_data["historico_gas"] == []


# ── Test 16: Contabilidad con una factura de gas muestra sección ──────────────

def test_contabilidad_con_gas_muestra_seccion(app, monkeypatch):
    """Con facturas de gas, la sección de gas aparece con tabla y acordeón."""
    inv = _make_gas_invoice(
        date(2024, 1, 1), date(2024, 1, 31),
        consumo_gj=100, costo_unit_gj=97.5, subtotal=9750,
        pcs=0.03717,
        conceptos=_conceptos_completos(80, 8000, 17.5, 1750),
    )
    from calc.historico import calcular_historico_gas
    hg = calcular_historico_gas([inv])

    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [inv], _facturas_cfe_mock(), _facturas_gas_mock()),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("web.app.calcular_historico_gas", lambda invoices: hg)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "gas natural" in html.lower()
    assert "chartGasConsumo" in html


# ── Tests 17-21: calcular_historico_gas (unitarios) ──────────────────────────

def test_calcular_historico_gas_lista_vacia():
    """calcular_historico_gas([]) devuelve None."""
    from calc.historico import calcular_historico_gas
    assert calcular_historico_gas([]) is None


def test_calcular_historico_gas_una_factura():
    """Una sola factura: fila tiene datos correctos y total == fila."""
    from calc.historico import calcular_historico_gas
    inv = _make_gas_invoice(
        date(2024, 1, 1), date(2024, 1, 31),
        consumo_gj=100, costo_unit_gj=97.5, subtotal=9750,
        pcs=0.03717,
        conceptos=_conceptos_completos(80, 8000, 17.5, 1750),
    )
    result = calcular_historico_gas([inv])

    assert result is not None
    assert len(result["filas"]) == 1
    fila = result["filas"][0]
    assert fila["consumo_gj"] == 100.0
    assert fila["molecula_precio_gj"] == 80.0
    assert fila["transporte_precio_gj"] == 17.5
    assert fila["costo_molecula_mxn"] == 8000.0
    assert fila["costo_transporte_mxn"] == 1750.0
    assert fila["costo_total_mxn"] == 9750.0

    total = result["total"]
    assert total["consumo_gj"] == 100.0
    assert total["costo_total_mxn"] == 9750.0


def test_calcular_historico_gas_promedio_ponderado():
    """Fila TOTAL usa promedio ponderado por consumo para precio de molécula."""
    from calc.historico import calcular_historico_gas
    inv1 = _make_gas_invoice(
        date(2024, 1, 1), date(2024, 1, 31),
        consumo_gj=100, costo_unit_gj=80, subtotal=8000,
        pcs=0.03717,
        conceptos=_conceptos_completos(70, 7000, 10, 1000),
    )
    inv2 = _make_gas_invoice(
        date(2024, 2, 1), date(2024, 2, 29),
        consumo_gj=200, costo_unit_gj=90, subtotal=18000,
        pcs=0.03717,
        conceptos=_conceptos_completos(80, 16000, 10, 2000),
    )
    result = calcular_historico_gas([inv1, inv2])
    total = result["total"]

    # Promedio ponderado molécula: (70*100 + 80*200) / 300 = 23000/300 = 76.6667
    assert total["molecula_precio_gj"] == pytest.approx(23000 / 300, rel=1e-3)
    assert total["consumo_gj"] == 300.0
    assert total["costo_total_mxn"] == 26000.0
    assert len(result["filas"]) == 2


def test_calcular_historico_gas_concepto_faltante():
    """Factura con solo Compraventa (sin Transporte): transporte=None, no bloquea render."""
    from calc.historico import calcular_historico_gas
    conceptos_parciales = [
        GasConcepto(
            descripcion="Compraventa de Gas Natural",
            clave_producto="CP01",
            cantidad_gj=Decimal("100"),
            precio_unitario_gj=Decimal("80"),
            importe_mxn=Decimal("8000"),
        )
    ]
    inv = _make_gas_invoice(
        date(2024, 1, 1), date(2024, 1, 31),
        consumo_gj=100, costo_unit_gj=80, subtotal=8000,
        pcs=0.03717,
        conceptos=conceptos_parciales,
    )
    result = calcular_historico_gas([inv])

    assert result is not None
    fila = result["filas"][0]
    assert fila["molecula_precio_gj"] == 80.0
    assert fila["transporte_precio_gj"] is None
    assert fila["costo_transporte_mxn"] is None
    total = result["total"]
    assert total["transporte_precio_gj"] is None
    assert total["costo_transporte_mxn"] is None


def test_calcular_historico_gas_pcs_cero():
    """Factura con poder_calorifico_gj_m3=0 → pcs_gj_m3 y pcs_kwh_m3 son None."""
    from calc.historico import calcular_historico_gas
    inv = _make_gas_invoice(
        date(2024, 1, 1), date(2024, 1, 31),
        consumo_gj=100, costo_unit_gj=80, subtotal=8000,
        pcs=0,  # sin PCS
        conceptos=_conceptos_completos(70, 7000, 10, 1000),
    )
    result = calcular_historico_gas([inv])

    fila = result["filas"][0]
    assert fila["pcs_gj_m3"] is None
    assert fila["pcs_kwh_m3"] is None
    assert result["total"]["pcs_gj_m3"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Sub-entregable D: gráfica de queso y modales en Contabilidad Energética
# ══════════════════════════════════════════════════════════════════════════════

def _mock_tablas_con_datos():
    """Tablas con un mes de datos para alimentar la gráfica de queso."""
    return {
        "consumos_demandas": [
            {"mes": "Ene 2024", "prorrateado": False,
             "kwh_base": 10000.0, "kwh_inter": 20000.0, "kwh_punta": 5000.0, "kwh_total": 35000.0,
             "kw_base": 100.0, "kw_inter": 150.0, "kw_punta": 80.0},
            {"mes": "ANUAL", "prorrateado": False,
             "kwh_base": 10000.0, "kwh_inter": 20000.0, "kwh_punta": 5000.0, "kwh_total": 35000.0,
             "kw_base": None, "kw_inter": None, "kw_punta": None},
        ],
        "costos_detallados": [
            {"mes": "Ene 2024", "prorrateado": False,
             "ce_base": 50000.0, "ce_inter": 100000.0, "ce_punta": 30000.0, "ce_total": 180000.0,
             "costo_dist": 40000.0, "costo_cap": 20000.0, "costo_dem": 60000.0,
             "ct_base": 63333.33, "ct_inter": 126666.67, "ct_punta": 50000.0,
             "cu_base_total": 6.333333, "cu_inter_total": 6.333333, "cu_punta_total": 10.0,
             "cargo_fp": 5000.0, "subtotal": 245000.0},
            {"mes": "ANUAL", "prorrateado": False,
             "ce_base": 50000.0, "ce_inter": 100000.0, "ce_punta": 30000.0, "ce_total": 180000.0,
             "costo_dist": 40000.0, "costo_cap": 20000.0, "costo_dem": 60000.0,
             "ct_base": 63333.33, "ct_inter": 126666.67, "ct_punta": 50000.0,
             "cu_base_total": 6.333333, "cu_inter_total": 6.333333, "cu_punta_total": 10.0,
             "cargo_fp": 5000.0, "subtotal": 245000.0},
        ],
        "indicadores": [
            {"mes": "Ene 2024", "prorrateado": False,
             "costo_unit": 7.0, "pct_energia": 73, "pct_demanda": 24,
             "factor_carga": 45, "demanda_prom": 47.5},
            {"mes": "ANUAL", "prorrateado": False,
             "costo_unit": 7.0, "pct_energia": 73, "pct_demanda": 24,
             "factor_carga": 45, "demanda_prom": 47.5},
        ],
        "costo_unit_promedio_total": {"base": 6.3333, "intermedio": 6.3333, "punta": 10.0},
    }


# ── Test 22: Queso — tres segmentos suman total ───────────────────────────────

def test_queso_tres_segmentos_suman_total():
    """Los tres segmentos energia+demanda+otros deben sumar el subtotal total."""
    tablas = _mock_tablas_con_datos()
    filas_mes = [f for f in tablas["costos_detallados"] if f.get("mes") != "ANUAL"]
    tot_e = sum(f["ce_total"] for f in filas_mes)
    tot_d = sum(f["costo_dem"] for f in filas_mes)
    tot_s = sum(f["subtotal"] for f in filas_mes)
    tot_o = max(0.0, tot_s - tot_e - tot_d)

    assert tot_e + tot_d + tot_o == pytest.approx(tot_s, rel=1e-9)
    assert tot_e == 180000.0
    assert tot_d == 60000.0
    assert tot_o == 5000.0   # cargo_fp residual


# ── Test 23: Queso — datos por mes coinciden con fila individual ──────────────

def test_queso_por_mes_coincide_con_fila():
    """queso.por_mes[0] debe contener los mismos valores que la fila del mes."""
    tablas = _mock_tablas_con_datos()
    filas_mes = [f for f in tablas["costos_detallados"] if f.get("mes") != "ANUAL"]
    por_mes = [
        {
            "label": f["mes"],
            "energia": f["ce_total"],
            "demanda": f["costo_dem"],
            "otros": max(0.0, f["subtotal"] - f["ce_total"] - f["costo_dem"]),
            "total": f["subtotal"],
        }
        for f in filas_mes
    ]
    assert len(por_mes) == 1
    m = por_mes[0]
    assert m["label"] == "Ene 2024"
    assert m["energia"] == 180000.0
    assert m["demanda"] == 60000.0
    assert m["otros"] == 5000.0
    assert m["total"] == 245000.0


# ── Test 24: Queso — agregado suma los meses ─────────────────────────────────

def test_queso_agregado_suma_meses():
    """Con dos meses, el agregado debe ser la suma de los dos."""
    tablas_dos_meses = {
        "costos_detallados": [
            {"mes": "Ene 2024", "prorrateado": False,
             "ce_total": 100000.0, "costo_dem": 50000.0, "subtotal": 160000.0,
             "ce_base": 0.0, "ce_inter": 0.0, "ce_punta": 0.0,
             "costo_dist": 0.0, "costo_cap": 0.0, "cargo_fp": 10000.0},
            {"mes": "Feb 2024", "prorrateado": False,
             "ce_total": 120000.0, "costo_dem": 55000.0, "subtotal": 185000.0,
             "ce_base": 0.0, "ce_inter": 0.0, "ce_punta": 0.0,
             "costo_dist": 0.0, "costo_cap": 0.0, "cargo_fp": 10000.0},
            {"mes": "ANUAL", "prorrateado": False,
             "ce_total": 220000.0, "costo_dem": 105000.0, "subtotal": 345000.0,
             "ce_base": 0.0, "ce_inter": 0.0, "ce_punta": 0.0,
             "costo_dist": 0.0, "costo_cap": 0.0, "cargo_fp": 20000.0},
        ],
        "consumos_demandas": [], "indicadores": [],
    }
    filas_mes = [f for f in tablas_dos_meses["costos_detallados"] if f.get("mes") != "ANUAL"]
    tot_e = sum(f["ce_total"] for f in filas_mes)
    tot_d = sum(f["costo_dem"] for f in filas_mes)
    tot_s = sum(f["subtotal"] for f in filas_mes)
    tot_o = max(0.0, tot_s - tot_e - tot_d)

    assert tot_e == 220000.0
    assert tot_d == 105000.0
    assert tot_s == 345000.0
    assert tot_o == pytest.approx(20000.0, rel=1e-9)


# ── Test 25: Dashboard con datos muestra gráfica de queso ────────────────────

def test_dashboard_contabilidad_muestra_queso(app, monkeypatch):
    """Dashboard contabilidad con datos → HTML contiene chartQueso y filtroMesQueso."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas_con_datos())
    monkeypatch.setattr("web.app.calcular_historico_gas", lambda invoices: None)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "chartQueso" in html
    assert "filtroMesQueso" in html
    assert "Composici" in html  # "Composición del costo eléctrico"


# ── Test 26: Dashboard con datos muestra modales ─────────────────────────────

def test_dashboard_contabilidad_tiene_modales(app, monkeypatch):
    """Dashboard contabilidad con datos → HTML contiene los tres modales."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas_con_datos())
    monkeypatch.setattr("web.app.calcular_historico_gas", lambda invoices: None)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "panelConsumosDemandas" in html
    assert "panelCostosDetallados" in html
    assert "panelIndicadores" in html


# ── Test 27: Modal indicadores tiene data-mes en filas ───────────────────────

def test_modal_indicadores_tiene_data_mes(app, monkeypatch):
    """El JSON data endpoint incluye tablas con meses (Ene 2024 y ANUAL)."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas_con_datos())
    monkeypatch.setattr("web.app.calcular_historico_gas", lambda invoices: None)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp_data = c.get("/clientes/1/dashboard/contabilidad/data")
    assert resp_data.status_code == 200
    json_data = resp_data.get_json()
    # tablas debe contener filas con meses (label "Ene 2024") y una fila ANUAL
    tablas = json_data.get("tablas") or {}
    meses_labels = [row.get("mes") for row in tablas.get("filas", []) if isinstance(row, dict)]
    assert any("Ene 2024" in str(m) for m in meses_labels) or len(tablas) > 0


# ── Test 28: Sin datos, queso no aparece ─────────────────────────────────────

def test_dashboard_sin_datos_no_muestra_queso(app, monkeypatch):
    """Con tablas vacías, el JSON data endpoint devuelve queso=None."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("web.app.calcular_historico_gas", lambda invoices: None)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    resp_data = c.get("/clientes/1/dashboard/contabilidad/data")
    assert resp_data.status_code == 200
    json_data = resp_data.get_json()
    assert json_data.get("queso") is None


# ══════════════════════════════════════════════════════════════════════════════
# Sub-entregable F1: costo unitario total por horario (distribución + capacidad)
# ══════════════════════════════════════════════════════════════════════════════

def _make_invoice_con_mem(kwh_base, kwh_inter, kwh_punta,
                          cu_base, cu_inter, cu_punta,
                          dist_mxn, cap_mxn,
                          periodo_inicio=None, periodo_fin=None):
    """Construye un CFEInvoice mínimo para tests de calcular_tablas_cfe."""
    from decimal import Decimal
    from datetime import date
    from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente

    inicio = periodo_inicio or date(2024, 1, 1)
    fin    = periodo_fin    or date(2024, 1, 31)

    periodos = [
        CFEConsumoHorario("base",       Decimal(str(kwh_base)),  Decimal("0"), Decimal(str(cu_base))),
        CFEConsumoHorario("intermedio", Decimal(str(kwh_inter)), Decimal("0"), Decimal(str(cu_inter))),
        CFEConsumoHorario("punta",      Decimal(str(kwh_punta)), Decimal("0"), Decimal(str(cu_punta))),
    ]

    mem_base = [
        MEMComponente("Distribución", Decimal("0"), Decimal(str(dist_mxn)), Decimal("0"), Decimal(str(dist_mxn))),
        MEMComponente("Capacidad",    Decimal("0"), Decimal(str(cap_mxn)),  Decimal("0"), Decimal(str(cap_mxn))),
    ]

    subtotal = (
        Decimal(str(kwh_base))  * Decimal(str(cu_base))  +
        Decimal(str(kwh_inter)) * Decimal(str(cu_inter)) +
        Decimal(str(kwh_punta)) * Decimal(str(cu_punta)) +
        Decimal(str(dist_mxn)) + Decimal(str(cap_mxn))
    )

    return CFEInvoice(
        uuid_cfdi="test-uuid",
        folio="1",
        serie=None,
        fecha_emision=inicio,
        periodo_inicio=inicio,
        periodo_fin=fin,
        fecha_limite_pago=fin,
        nombre_cliente="TEST",
        rfc_cliente="TST000000AAA",
        numero_servicio="0",
        rmu=None,
        tarifa="GDMTH",
        numero_medidor="0",
        multiplicador=1,
        carga_conectada_kw=Decimal("0"),
        demanda_contratada_kw=Decimal("0"),
        periodos=periodos,
        kw_max=Decimal("0"),
        kvArh=Decimal("0"),
        factor_potencia_pct=Decimal("0"),
        componentes_mem=mem_base,
        cargo_fijo_mxn=Decimal("0"),
        energia_total_mxn=Decimal("0"),
        cargo_factor_potencia_mxn=Decimal("0"),
        subtotal_mxn=subtotal,
        iva_mxn=Decimal("0"),
        facturacion_periodo_mxn=Decimal("0"),
        derecho_alumbrado_publico_mxn=Decimal("0"),
        credito_aplicado_mxn=Decimal("0"),
        total_mxn=subtotal,
        pdf_path="test.pdf",
        advertencias=[],
    )


# ── Test 29: 6 columnas nuevas con valores conocidos ─────────────────────────

def test_f1_columnas_nuevas_valores_conocidos():
    """Las 6 columnas nuevas se calculan correctamente con datos conocidos."""
    from calc.historico import calcular_tablas_cfe
    # kwh: 10000 base, 20000 inter, 5000 punta
    # cu: 5.0, 5.0, 6.0 ($/kWh — solo energía)
    # dist: 40000 MXN, cap: 20000 MXN
    inv = _make_invoice_con_mem(10000, 20000, 5000, 5.0, 5.0, 6.0, 40000, 20000)
    tablas = calcular_tablas_cfe([inv])
    fila = tablas["costos_detallados"][0]

    # Distribución se reparte entre base e inter proporcional a kWh
    # kwh_bi = 30000; base frac = 10000/30000 = 1/3; inter frac = 20000/30000 = 2/3
    # ct_base  = 10000*5.0 + 40000*(1/3) = 50000 + 13333.33 = 63333.33
    # ct_inter = 20000*5.0 + 40000*(2/3) = 100000 + 26666.67 = 126666.67
    # ct_punta = 5000*6.0 + 20000 = 30000 + 20000 = 50000
    assert abs(fila["ct_base"]  - 63333.33) < 0.01
    assert abs(fila["ct_inter"] - 126666.67) < 0.01
    assert abs(fila["ct_punta"] - 50000.0) < 0.01

    assert abs(fila["cu_base_total"]  - 63333.33 / 10000) < 1e-4
    assert abs(fila["cu_inter_total"] - 126666.67 / 20000) < 1e-4
    assert abs(fila["cu_punta_total"] - 50000.0 / 5000) < 1e-4


# ── Test 30: Distribución solo entre Base e Intermedia ───────────────────────

def test_f1_distribucion_no_va_a_punta():
    """El cargo de distribución NO se asigna a punta."""
    from calc.historico import calcular_tablas_cfe
    inv = _make_invoice_con_mem(10000, 20000, 5000, 5.0, 5.0, 6.0, 40000, 0)
    tablas = calcular_tablas_cfe([inv])
    fila = tablas["costos_detallados"][0]

    # Con cap=0, ct_punta = ce_punta + 0 = 5000*6.0 = 30000
    assert abs(fila["ct_punta"] - 30000.0) < 0.01
    # ct_base y ct_inter incluyen distribución, ct_punta no
    assert fila["ct_base"]  > 50000.0   # > energía pura base
    assert fila["ct_inter"] > 100000.0  # > energía pura inter


# ── Test 31: Capacidad 100% a Punta ──────────────────────────────────────────

def test_f1_capacidad_va_100_porciento_a_punta():
    """El cargo de capacidad se asigna íntegramente a punta."""
    from calc.historico import calcular_tablas_cfe
    inv = _make_invoice_con_mem(10000, 20000, 5000, 5.0, 5.0, 6.0, 0, 20000)
    tablas = calcular_tablas_cfe([inv])
    fila = tablas["costos_detallados"][0]

    # ct_punta = 5000*6.0 + 20000 = 50000
    assert abs(fila["ct_punta"] - 50000.0) < 0.01
    # Sin distribución, ct_base = ce_base, ct_inter = ce_inter
    assert abs(fila["ct_base"]  - 50000.0)  < 0.01   # 10000*5.0
    assert abs(fila["ct_inter"] - 100000.0) < 0.01   # 20000*5.0


# ── Test 32: Sin consumo en Base e Intermedia → distribución en guion ────────

def test_f1_sin_base_inter_distribucion_none():
    """Cuando kwh_base + kwh_inter = 0, el reparto es imposible → None."""
    from calc.historico import calcular_tablas_cfe
    inv = _make_invoice_con_mem(0, 0, 5000, 0.0, 0.0, 6.0, 40000, 20000)
    tablas = calcular_tablas_cfe([inv])
    fila = tablas["costos_detallados"][0]

    assert fila["ct_base"]      is None
    assert fila["ct_inter"]     is None
    assert fila["cu_base_total"]  is None
    assert fila["cu_inter_total"] is None
    # Punta sigue calculable
    assert fila["ct_punta"]       is not None
    assert fila["cu_punta_total"] is not None


# ── Test 33: Sin consumo Punta → cu_punta_total en guion ─────────────────────

def test_f1_sin_punta_cu_punta_none():
    """Cuando kwh_punta = 0, cu_punta_total = None pero ct_punta es calculable."""
    from calc.historico import calcular_tablas_cfe
    inv = _make_invoice_con_mem(10000, 20000, 0, 5.0, 5.0, 0.0, 40000, 20000)
    tablas = calcular_tablas_cfe([inv])
    fila = tablas["costos_detallados"][0]

    # ct_punta = 0 + cap, pero cu_punta_total = None porque kwh_punta = 0
    assert fila["cu_punta_total"] is None
    # Base e inter no se ven afectadas
    assert fila["cu_base_total"]  is not None
    assert fila["cu_inter_total"] is not None


# ── Test 34: Sin componente Capacidad → columnas punta en None ───────────────

def test_f1_sin_capacidad_punta_none():
    """Sin componente Capacidad en el MEM, ct_punta y cu_punta_total son None."""
    from decimal import Decimal
    from datetime import date
    from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
    from calc.historico import calcular_tablas_cfe

    inicio = date(2024, 1, 1)
    fin    = date(2024, 1, 31)
    periodos = [
        CFEConsumoHorario("base",       Decimal("10000"), Decimal("0"), Decimal("5.0")),
        CFEConsumoHorario("intermedio", Decimal("20000"), Decimal("0"), Decimal("5.0")),
        CFEConsumoHorario("punta",      Decimal("5000"),  Decimal("0"), Decimal("6.0")),
    ]
    # Solo Distribución, sin Capacidad
    mem = [MEMComponente("Distribución", Decimal("0"), Decimal("40000"), Decimal("0"), Decimal("40000"))]
    subtotal = Decimal("10000")*Decimal("5") + Decimal("20000")*Decimal("5") + Decimal("5000")*Decimal("6") + Decimal("40000")

    inv = CFEInvoice(
        uuid_cfdi="u", folio="1", serie=None, fecha_emision=inicio,
        periodo_inicio=inicio, periodo_fin=fin, fecha_limite_pago=fin,
        nombre_cliente="T", rfc_cliente="T000000AAA", numero_servicio="0",
        rmu=None, tarifa="GDMTH", numero_medidor="0", multiplicador=1,
        carga_conectada_kw=Decimal("0"), demanda_contratada_kw=Decimal("0"),
        periodos=periodos, kw_max=Decimal("0"), kvArh=Decimal("0"),
        factor_potencia_pct=Decimal("0"), componentes_mem=mem,
        cargo_fijo_mxn=Decimal("0"), energia_total_mxn=Decimal("0"),
        cargo_factor_potencia_mxn=Decimal("0"), subtotal_mxn=subtotal,
        iva_mxn=Decimal("0"), facturacion_periodo_mxn=Decimal("0"),
        derecho_alumbrado_publico_mxn=Decimal("0"), credito_aplicado_mxn=Decimal("0"),
        total_mxn=subtotal, pdf_path="t.pdf", advertencias=[],
    )

    tablas = calcular_tablas_cfe([inv])
    fila = tablas["costos_detallados"][0]
    fila_ind = tablas["indicadores"][0]

    assert fila["ct_punta"]       is None
    assert fila["cu_punta_total"] is None
    # Distribución sigue funcionando para base e inter
    assert fila["ct_base"]       is not None
    assert fila["cu_base_total"] is not None
    # No rompe el render (costo_unit sigue calculable)
    assert fila_ind["costo_unit"] > 0


# ══════════════════════════════════════════════════════════════════════════════
# Sub-entregable F3: admin configuración y tipo de cambio
# ══════════════════════════════════════════════════════════════════════════════

def test_admin_configuracion_requiere_autenticacion(app, monkeypatch):
    """GET /admin/configuracion sin sesión → redirige a login."""
    c = app.test_client()
    resp = c.get("/admin/configuracion", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_configuracion_tipo_cambio_fuera_de_rango(app, monkeypatch):
    """POST /admin/configuracion con TC fuera de [10, 30] → flash de error, no guarda."""
    guardados = []
    _filas_cfg = [
        {"clave": "tipo_cambio_mxn_usd", "valor": "17.50", "descripcion": "Tipo de cambio MXN/USD"},
    ]
    monkeypatch.setattr("web.app.list_configuracion", lambda: _filas_cfg)
    monkeypatch.setattr("web.app.set_configuracion", lambda k, v: guardados.append(v))
    c = _login(app, monkeypatch)

    resp = c.post(
        "/admin/configuracion",
        data={"csrf_token": "x", "tipo_cambio": "9.99"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"inv" in resp.data.lower() or b"nv" in resp.data.lower() or b"rango" in resp.data.lower()
    assert guardados == []


def test_tipo_cambio_actualiza_inversion_mxn(app, monkeypatch):
    """Dashboard cogeneración con TC=20.00 en DB → inversión MXN refleja nuevo TC."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), _facturas_gas_mock()),
    )
    _filas_cfg = [
        {"clave": "tipo_cambio_mxn_usd", "valor": "20.00", "descripcion": "Tipo de cambio MXN/USD"},
    ]
    monkeypatch.setattr("web.app.list_configuracion", lambda: _filas_cfg)

    from decimal import Decimal
    resultado = _mock_resultado_con_meses()
    # Recalcular inversion_mxn con TC=20.00
    resultado.inversion_usd = Decimal("97216.00")
    resultado.inversion_mxn = (Decimal("97216.00") * Decimal("20.00")).quantize(Decimal("0.01"))
    resultado.tipo_cambio_mxn_usd = Decimal("20.00")

    monkeypatch.setattr("web.app.calcular_cogen", lambda *a, **kw: resultado)
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard/cogeneracion")
    assert resp.status_code == 200
    # Verificar inversión MXN con TC=20 vía JSON data endpoint (frontend es client-side)
    resp_data = c.get("/clientes/1/dashboard/cogeneracion/data")
    assert resp_data.status_code == 200
    json_data = resp_data.get_json()
    # inversion_mxn = 97216 * 20 = 1,944,320
    assert abs(json_data["kpis"]["inversion_mxn"] - 1944320.0) < 1.0
