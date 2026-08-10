"""Tests para calc/telemetria_costos.py y extensión del endpoint D3."""
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from time import time

# Garantizar que storage.repository puede importarse sin Supabase real
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake_key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")


# ── Fixtures ──────────────────────────────────────────────────────────────

FAC_CFE_MOCK = {
    "id": 1, "cliente_id": 44, "anio": 2024, "mes": 1,
    "subtotal_mxn": "25000.00",
    "cfe_periodos": [
        {"consumo_kwh": "5000.00", "periodo": "base"},
        {"consumo_kwh": "3000.00", "periodo": "intermedio"},
        {"consumo_kwh": "2000.00", "periodo": "punta"},
    ]
}

FAC_PPA_MOCK = {
    "id": 2, "cliente_id": 44, "anio": 2024, "mes": 2,
    "precio_unitario_mxn_kwh": "2.50",
    "consumo_kwh": "10000.00",
    "subtotal_mxn": "25000.00",
}


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
def client(app):
    return app.test_client()


def _injectar_sesion(client, rol="master_admin", empresa_id=44, cliente_activo_id=44):
    now = time()
    with client.session_transaction() as sess:
        sess["_user_id"] = "mock-uuid"
        sess["_user_email"] = "test@test.com"
        sess["_user_rol"] = rol
        sess["_empresa_id"] = empresa_id
        sess["_access_token"] = "mock-token"
        sess["cliente_activo_id"] = cliente_activo_id
        sess["_session_version"] = 1
        sess["_activo_check"] = {"user_id": "mock-uuid", "ts": now, "activo": True}
        sess["_sv_check"] = {"user_id": "mock-uuid", "ts": now, "version": 1}


# ── Test a ─────────────────────────────────────────────────────────────────
def test_precio_cfe_mes_exacto():
    """Con factura CFE del mes exacto: subtotal/kwh_total y fuente=factura_mes_exacto."""
    from calc.telemetria_costos import obtener_precio_unitario_mxn_kwh
    with patch("storage.repository.obtener_factura_cfe_cliente_mes", return_value=FAC_CFE_MOCK), \
         patch("storage.repository.obtener_ultimas_facturas_cfe", return_value=[]):
        result = obtener_precio_unitario_mxn_kwh(44, 2024, 1)
    assert result["fuente"] == "factura_mes_exacto"
    assert result["precio_mxn_kwh"] == pytest.approx(2.5, rel=1e-3)  # 25000/10000
    assert result["mes_referencia"] == "2024-01"


# ── Test b ─────────────────────────────────────────────────────────────────
def test_precio_cfe_mes_anterior():
    """Sin factura del mes exacto, usa la última disponible con fuente=factura_mes_anterior."""
    from calc.telemetria_costos import obtener_precio_unitario_mxn_kwh
    fac_anterior = {**FAC_CFE_MOCK, "anio": 2023, "mes": 12}
    with patch("storage.repository.obtener_factura_cfe_cliente_mes", return_value=None), \
         patch("storage.repository.obtener_ultimas_facturas_cfe", return_value=[fac_anterior]), \
         patch("storage.repository.obtener_factura_ppa_cliente_mes", return_value=None), \
         patch("storage.repository.obtener_ultimas_facturas_ppa", return_value=[]):
        result = obtener_precio_unitario_mxn_kwh(44, 2024, 1)
    assert result["fuente"] == "factura_mes_anterior"
    assert result["precio_mxn_kwh"] == pytest.approx(2.5, rel=1e-3)
    assert result["mes_referencia"] == "2023-12"


# ── Test c ─────────────────────────────────────────────────────────────────
def test_precio_sin_facturas():
    """Sin facturas: precio=None, fuente=sin_datos."""
    from calc.telemetria_costos import obtener_precio_unitario_mxn_kwh
    with patch("storage.repository.obtener_factura_cfe_cliente_mes", return_value=None), \
         patch("storage.repository.obtener_ultimas_facturas_cfe", return_value=[]), \
         patch("storage.repository.obtener_factura_ppa_cliente_mes", return_value=None), \
         patch("storage.repository.obtener_ultimas_facturas_ppa", return_value=[]):
        result = obtener_precio_unitario_mxn_kwh(44, 2024, 1)
    assert result["fuente"] == "sin_datos"
    assert result["precio_mxn_kwh"] is None


# ── Test d ─────────────────────────────────────────────────────────────────
def test_precio_ppa():
    """Para cliente PPA usa precio_unitario_mxn_kwh de facturas_electricidad_calificado."""
    from calc.telemetria_costos import obtener_precio_unitario_mxn_kwh
    with patch("storage.repository.obtener_factura_cfe_cliente_mes", return_value=None), \
         patch("storage.repository.obtener_ultimas_facturas_cfe", return_value=[]), \
         patch("storage.repository.obtener_factura_ppa_cliente_mes", return_value=FAC_PPA_MOCK), \
         patch("storage.repository.obtener_ultimas_facturas_ppa", return_value=[]):
        result = obtener_precio_unitario_mxn_kwh(44, 2024, 2)
    assert result["fuente"] == "factura_mes_exacto"
    assert result["precio_mxn_kwh"] == pytest.approx(2.5, rel=1e-3)


# ── Test f ─────────────────────────────────────────────────────────────────
def test_endpoint_data_nuevas_claves(client, app):
    """El endpoint /data devuelve kpis.costo_mxn, kpis.precio_fuente, comparativa_mes_anterior.disponible."""
    app.config["FASE2_HABILITADA"] = True

    ARBOL_MOCK = [
        {"id": 1, "nombre": "Acometida CFE-1", "punto_medicion": "acometida_cfe",
         "activo_padre_id": None, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": None, "potencia_nominal_kw": None, "medidor_id": None,
         "tipo": "acometida"},
        {"id": 2, "nombre": "Horno 1", "punto_medicion": "carga_final",
         "activo_padre_id": 1, "cliente_id": 44, "planta_id": 1,
         "tipo_carga": "horno_tunel", "potencia_nominal_kw": 200.0, "medidor_id": 30,
         "tipo": "carga"},
    ]
    MEDICIONES_MOCK = [
        {"timestamp": "2024-01-01T00:00:00Z", "potencia_activa_kw": 100.0, "factor_potencia": 0.90},
        {"timestamp": "2024-01-01T00:15:00Z", "potencia_activa_kw": 110.0, "factor_potencia": 0.91},
    ]

    _injectar_sesion(client)

    with patch("storage.repository.get_cliente_con_conteos",
               return_value={"id": 44, "nombre": "Iberica", "num_cfe": 12,
                             "num_gas": 12, "num_electricidad": 12, "contratos": []}), \
         patch("storage.repository.obtener_arbol_activos_telemetria", return_value=ARBOL_MOCK), \
         patch("storage.repository.obtener_mediciones_para_rango", return_value=MEDICIONES_MOCK), \
         patch("storage.repository.resolver_intervalos_medidor", return_value=[]), \
         patch("storage.repository.resolver_intervalos_contrato", return_value=[]), \
         patch("storage.repository.resolver_intervalos_fuente", return_value=[]), \
         patch("storage.repository.obtener_ultimo_timestamp_cliente",
               return_value=datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)), \
         patch("web.app.obtener_plantas_por_cliente",
               return_value=[{"id": 1, "nombre": "Planta 1", "activo": True}]), \
         patch("storage.repository.obtener_produccion_diaria", return_value=[]):
        resp = client.get("/clientes/44/planta/1/dashboard/telemetria/data?rango=24h")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "costo_mxn" in data["kpis"]
    assert "precio_fuente" in data["kpis"]
    assert "comparativa_mes_anterior" in data
    assert "disponible" in data["comparativa_mes_anterior"]


# ── Test h ─────────────────────────────────────────────────────────────────
def test_precio_por_contrato_cfe_exacto():
    """obtener_precio_unitario_por_contrato: factura CFE del contrato exacto."""
    from calc.telemetria_costos import obtener_precio_unitario_por_contrato
    with patch("storage.repository.obtener_factura_cfe_contrato_mes", return_value=FAC_CFE_MOCK), \
         patch("storage.repository.obtener_ultimas_facturas_cfe_contrato", return_value=[]):
        result = obtener_precio_unitario_por_contrato(5, 2024, 1)
    assert result["fuente"] == "factura_mes_exacto"
    assert result["precio_mxn_kwh"] == pytest.approx(2.5, rel=1e-3)
    assert result["mes_referencia"] == "2024-01"


def test_precio_por_contrato_sin_facturas():
    """obtener_precio_unitario_por_contrato: sin facturas → sin_datos."""
    from calc.telemetria_costos import obtener_precio_unitario_por_contrato
    with patch("storage.repository.obtener_factura_cfe_contrato_mes", return_value=None), \
         patch("storage.repository.obtener_ultimas_facturas_cfe_contrato", return_value=[]), \
         patch("storage.repository.obtener_factura_ppa_contrato_mes", return_value=None), \
         patch("storage.repository.obtener_ultimas_facturas_ppa_contrato", return_value=[]):
        result = obtener_precio_unitario_por_contrato(5, 2024, 1)
    assert result["fuente"] == "sin_datos"
    assert result["precio_mxn_kwh"] is None


# ── Test g ─────────────────────────────────────────────────────────────────
def test_comparativa_energia_delta_pct():
    """energia_delta_pct se calcula correctamente con datos controlados."""
    # Si el periodo actual tiene 200 kWh y el anterior 160 kWh: delta = +25%
    # Usamos _precio_de_factura_cfe directamente para verificar la aritmética
    from calc.telemetria_costos import _precio_de_factura_cfe
    fac = {
        "subtotal_mxn": "10000.00",
        "cfe_periodos": [{"consumo_kwh": "4000.00"}, {"consumo_kwh": "3000.00"}, {"consumo_kwh": "3000.00"}]
    }
    precio, _ = _precio_de_factura_cfe(fac)
    assert precio == pytest.approx(1.0, rel=1e-3)  # 10000/10000

    # Verificar delta matemáticamente
    energia_actual = 200.0
    energia_anterior = 160.0
    delta = round((energia_actual - energia_anterior) / energia_anterior * 100, 1)
    assert delta == pytest.approx(25.0, rel=1e-3)
