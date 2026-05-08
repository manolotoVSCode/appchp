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
    """Dashboard cogeneración con facturas seleccionadas → renderiza KPIs sin aviso."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), _facturas_gas_mock()),
    )
    monkeypatch.setattr("web.app.calcular_cogen", lambda *a, **kw: _mock_resultado_con_meses())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard/cogeneracion")
    assert resp.status_code == 200
    assert b"EBITDA Anual" in resp.data
    assert b"Sin facturas seleccionadas" not in resp.data


# ── Test 6: Dashboard sin selección → aviso sin KPIs ─────────────────────────

def test_dashboard_sin_seleccion_muestra_aviso(app, monkeypatch):
    """Dashboard contabilidad con cero facturas seleccionadas → aviso sin_seleccion, sin gráficas."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], [], []),
    )
    monkeypatch.setattr("web.app.calcular_historico_cfe", lambda invoices: _mock_historico())
    monkeypatch.setattr("web.app.calcular_tablas_cfe", lambda invoices: _mock_tablas())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/1/dashboard/contabilidad")
    assert resp.status_code == 200
    assert "Sin facturas seleccionadas".encode() in resp.data
    assert b"EBITDA Anual" not in resp.data


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
    assert b"EBITDA Anual" not in resp.data


# ── Test 14: cogeneración muestra KPIs, no gráficas históricas ───────────────

def test_cogeneracion_muestra_kpis_no_historico(app, monkeypatch):
    """GET /dashboard/cogeneracion → muestra KPIs de EBITDA, no gráficas históricas de demanda."""
    monkeypatch.setattr(
        "web.app._cargar_facturas_seleccionadas",
        lambda cliente_id: ([], [], _facturas_cfe_mock(), _facturas_gas_mock()),
    )
    monkeypatch.setattr("web.app.calcular_cogen", lambda *a, **kw: _mock_resultado_con_meses())
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE)
    c = _login(app, monkeypatch)

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard/cogeneracion")
    assert resp.status_code == 200
    assert b"EBITDA Anual" in resp.data
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
    """Sin facturas de gas seleccionadas, la sección de gas no aparece."""
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
    assert b"gas natural" not in resp.data.lower() or b"Hist\xc3\xb3rico de consumos y costos de gas" not in resp.data


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
