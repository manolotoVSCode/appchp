# tests/test_contrato_upload.py
"""Tests para el endpoint de upload de facturas por contrato y borrado de facturas."""
from __future__ import annotations

import io
import logging

import pytest
from unittest.mock import MagicMock
from models.contrato import Contrato

_CLIENTE = {
    "id": 1,
    "nombre": "IBERICA TILES",
    "rfc": "ITI930101AAA",
    "notas": None,
    "created_at": "2024-01-15T10:00:00+00:00",
    "num_cfe": 9,
    "num_gas": 0,
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

_CONTRATO_ELECTRICO = Contrato(
    id=10,
    cliente_id=1,
    nombre="CFE Planta 1",
    tipo="electrico_basico",
    identificador_real="812990300016",
    notas=None,
    created_at="2024-01-15T10:00:00+00:00",
)

_CONTRATO_GAS = Contrato(
    id=20,
    cliente_id=1,
    nombre="Gas Planta 1",
    tipo="gas",
    identificador_real="CUENTA-001",
    notas=None,
    created_at="2024-01-15T10:00:00+00:00",
)


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture()
def auth_client(app, monkeypatch):
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE])
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = "test-user-uuid"
        sess["_user_email"] = "operador@test.com"
        sess["_user_rol"] = "admin"
        sess["_empresa_id"] = None
    return c


def _fake_pdf(nombre="factura.pdf"):
    return (io.BytesIO(b"%PDF-1.4 fake"), nombre)


def _mock_cfe_invoice(numero_servicio="812990300016", rfc_cliente="ITI930101AAA"):
    inv = MagicMock()
    inv.numero_servicio = numero_servicio
    inv.rfc_cliente = rfc_cliente
    inv.advertencias = []
    return inv


def _mock_gas_invoice(cuenta_contrato="CUENTA-001", rfc_cliente="ITI930101AAA"):
    inv = MagicMock()
    inv.cuenta_contrato = cuenta_contrato
    inv.rfc_cliente = rfc_cliente
    inv.advertencias = []
    return inv


def _setup_electrico(monkeypatch):
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_ELECTRICO)


def _setup_gas(monkeypatch):
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_GAS)


# ── Test 1: Upload CFE exitoso ────────────────────────────────────────────────

def test_upload_cfe_exitoso(auth_client, monkeypatch):
    """Upload válido de factura CFE → procesados=1, exitosos con nombre_canonico."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice()
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, cliente_id=None, contrato_id=None: (1, "2024 ENE CFE 812990300016"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert data["exitosos"][0]["nombre_canonico"] == "2024 ENE CFE 812990300016"
    assert data["errores"] == []
    assert data["pendientes_confirmacion"] == []


# ── Test 2: Upload Gas exitoso ────────────────────────────────────────────────

def test_upload_gas_exitoso(auth_client, monkeypatch):
    """Upload válido de factura Gas → procesados=1."""
    _setup_gas(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "gas")
    parser = MagicMock()
    parser.parse.return_value = _mock_gas_invoice()
    monkeypatch.setattr("web.clientes.get_gas_parser", lambda: parser)
    monkeypatch.setattr(
        "web.clientes.save_gas_invoice",
        lambda inv, cliente_id=None, contrato_id=None: (2, "2024 ENE GAS CUENTA-001"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/20/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert data["errores"] == []


# ── Test 3: Error de parseo queda en log ──────────────────────────────────────

def test_upload_error_queda_en_log(auth_client, monkeypatch, caplog):
    """Error de parseo → registro ERROR con exc_info y JSON con errores."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.side_effect = ValueError("Campo no encontrado: PERIODO FACTURADO")
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)

    with caplog.at_level(logging.ERROR, logger="web.clientes"):
        resp = auth_client.post(
            "/clientes/1/contratos/10/upload",
            data={"facturas": _fake_pdf()},
            content_type="multipart/form-data",
        )

    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["errores"]) == 1
    assert "PERIODO FACTURADO" in data["errores"][0]["error"]
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "Se esperaba al menos un registro ERROR en el log"
    assert error_records[0].exc_info is not None


# ── Test 4: CFE a contrato Gas → error bloqueante ────────────────────────────

def test_upload_tipo_cfe_a_contrato_gas_es_error(auth_client, monkeypatch):
    """Factura CFE subida a contrato de gas → error bloqueante, no se intenta parsear."""
    _setup_gas(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")

    resp = auth_client.post(
        "/clientes/1/contratos/20/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["errores"]) == 1
    assert "no coincide" in data["errores"][0]["error"]


# ── Test 5: Identificador discrepante → pendiente_confirmacion ───────────────

def test_upload_identificador_discrepante_queda_pendiente(auth_client, monkeypatch):
    """Factura con numero_servicio diferente al del contrato → pendientes_confirmacion, no se guarda."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice(numero_servicio="OTRO-NUMERO")
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado = []
    monkeypatch.setattr("web.clientes.save_cfe_invoice", lambda inv, cliente_id=None, contrato_id=None: guardado.append(1) or (1, "x"))

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["pendientes_confirmacion"]) == 1
    assert data["pendientes_confirmacion"][0]["identificador_factura"] == "OTRO-NUMERO"
    assert data["pendientes_confirmacion"][0]["identificador_contrato"] == "812990300016"
    assert len(guardado) == 0


# ── Test 6: Confirmación de discrepancia → guarda con contrato_id correcto ───

def test_upload_confirmado_pese_a_discrepancia_guarda(auth_client, monkeypatch):
    """Con confirmado_pese_a_discrepancia → guarda la factura con el contrato_id del contrato."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice(numero_servicio="OTRO-NUMERO")
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado_con = []
    guardado_con_contrato = []
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, cliente_id=None, contrato_id=None: guardado_con_contrato.append(contrato_id) or (1, "nombre"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf(), "confirmado_pese_a_discrepancia": "factura.pdf"},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert len(guardado_con_contrato) == 1
    assert guardado_con_contrato[0] == 10  # contrato_id correcto


# ── Test 7: Gas a contrato eléctrico → error bloqueante ──────────────────────

def test_upload_tipo_gas_a_contrato_electrico_es_error(auth_client, monkeypatch):
    """Factura Gas subida a contrato eléctrico → error bloqueante."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "gas")

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["errores"]) == 1
    assert "no coincide" in data["errores"][0]["error"]


# ── Test 8: Borrar factura CFE ────────────────────────────────────────────────

def test_contrato_factura_borrar_exitoso(auth_client, monkeypatch, app):
    """POST a /facturas/42/borrar con tipo=cfe → ok=True, factura eliminada."""
    _setup_electrico(monkeypatch)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_cfe_factura", lambda id: borrado.append(id))

    resp = auth_client.post(
        "/clientes/1/contratos/10/facturas/42/borrar",
        data={"tipo": "cfe"},
    )
    data = resp.get_json()
    assert data["ok"] is True
    assert 42 in borrado


# ── Test 9: Upload sin archivos → 400 ────────────────────────────────────────

def test_upload_sin_archivos(auth_client, monkeypatch):
    """POST sin archivos → 400 con mensaje de error."""
    _setup_electrico(monkeypatch)

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["procesados"] == 0
    assert data["errores"][0]["error"] == "No se enviaron archivos"


# ── Test 10: RFC coincide → sin alerta, guarda con cliente_id del contrato ────

def test_upload_rfc_coincidente_guarda_sin_pendiente(auth_client, monkeypatch):
    """RFC del PDF coincide con el del cliente → guarda directamente, sin pendientes."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice(
        numero_servicio="812990300016", rfc_cliente="ITI930101AAA"
    )
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado_cliente_id = []
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, cliente_id=None, contrato_id=None: guardado_cliente_id.append(cliente_id) or (1, "nombre"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert data["pendientes_confirmacion"] == []
    assert guardado_cliente_id == [1]  # cliente_id del contrato, no del RFC


# ── Tests 11-13: RFC discrepante → se guarda directamente (sin modal, sin pendiente) ──

def test_upload_rfc_distinto_guarda_directamente(auth_client, monkeypatch):
    """RFC del PDF distinto al del cliente → se guarda sin pendiente (v2.36.0: RFC no se valida)."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice(
        numero_servicio="812990300016",  # identificador coincide
        rfc_cliente="OTR930101XYZ",      # RFC distinto al del cliente
    )
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado_cliente_id = []
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, cliente_id=None, contrato_id=None: guardado_cliente_id.append(cliente_id) or (1, "nombre"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    # Se guarda directamente: sin modal, sin pendiente
    assert data["procesados"] == 1
    assert data["pendientes_confirmacion"] == []
    assert guardado_cliente_id == [1]  # cliente_id del contrato


def test_upload_rfc_vacio_en_pdf_guarda_directamente(auth_client, monkeypatch):
    """RFC vacío en el PDF → se guarda directamente (identificador coincide, no hay pendiente)."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice(
        numero_servicio="812990300016",
        rfc_cliente="",  # vacío
    )
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, cliente_id=None, contrato_id=None: (1, "nombre"),
    )

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 1
    assert data["pendientes_confirmacion"] == []


# ── Test 14: Upload nunca crea cliente nuevo ───────────────────────────────────

def test_upload_nunca_crea_cliente(auth_client, monkeypatch):
    """El endpoint de upload no llama a create_cliente ni a _upsert_cliente."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    parser = MagicMock()
    parser.parse.return_value = _mock_cfe_invoice()
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    monkeypatch.setattr(
        "web.clientes.save_cfe_invoice",
        lambda inv, cliente_id=None, contrato_id=None: (1, "nombre"),
    )

    clientes_creados = []
    monkeypatch.setattr("web.clientes.create_cliente", lambda *a, **kw: clientes_creados.append(1) or 999)

    auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    assert clientes_creados == [], "El upload no debe crear clientes"


# ── Test 16: Crear cliente RFC con espacios/invisibles → sanitizar y aceptar ──

def test_nuevo_cliente_rfc_con_espacios_sanitiza(auth_client, monkeypatch):
    """RFC con espacios y caracteres invisibles → sanitizado y aceptado si formato válido."""
    monkeypatch.setattr("web.clientes.create_cliente", lambda nombre, rfc, notas, **kw: 42)

    # U+202D (left-to-right override) antes del RFC, espacio al final
    rfc_con_invisible = "\u202Diti930101aaa "
    resp = auth_client.post(
        "/clientes/nuevo",
        data={"nombre": "Test SA", "rfc": rfc_con_invisible, "notas": ""},
    )
    # Debe redirigir (éxito), no mostrar error de RFC
    assert resp.status_code == 302


# ── Test 17: Crear cliente RFC en minúsculas → sanitizar a mayúsculas y aceptar

def test_nuevo_cliente_rfc_minusculas_sanitiza(auth_client, monkeypatch):
    """RFC en minúsculas → sanitizado a mayúsculas y aceptado."""
    monkeypatch.setattr("web.clientes.create_cliente", lambda nombre, rfc, notas, **kw: 42)

    resp = auth_client.post(
        "/clientes/nuevo",
        data={"nombre": "Test SA", "rfc": "iti930101aaa", "notas": ""},
    )
    assert resp.status_code == 302


# ── Tests captura manual (v2.37.0) ────────────────────────────────────────────

def test_upload_numero_servicio_nulo_requiere_captura_manual(auth_client, monkeypatch):
    """Factura CFE con numero_servicio vacío → requiere_captura_manual, no se guarda."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    inv = _mock_cfe_invoice(numero_servicio="")  # vacío
    inv.periodo_inicio = __import__("datetime").date(2024, 1, 1)
    inv.periodo_fin = __import__("datetime").date(2024, 1, 31)
    parser = MagicMock()
    parser.parse.return_value = inv
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado = []
    monkeypatch.setattr("web.clientes.save_cfe_invoice", lambda *a, **kw: guardado.append(1) or (1, "x"))

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["requieren_captura_manual"]) == 1
    assert data["requieren_captura_manual"][0]["campos_faltantes"] == ["numero_servicio"]
    assert data["requieren_captura_manual"][0]["motivo"] == "numero_servicio_nulo"
    assert guardado == []


def test_upload_periodo_inicio_nulo_requiere_captura_manual(auth_client, monkeypatch):
    """Factura CFE con periodo_inicio=None → requiere_captura_manual."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    inv = _mock_cfe_invoice(numero_servicio="812990300016")
    inv.periodo_inicio = None
    inv.periodo_fin = __import__("datetime").date(2024, 1, 31)
    parser = MagicMock()
    parser.parse.return_value = inv
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    guardado = []
    monkeypatch.setattr("web.clientes.save_cfe_invoice", lambda *a, **kw: guardado.append(1) or (1, "x"))

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    assert len(data["requieren_captura_manual"]) == 1
    assert "periodo_inicio" in data["requieren_captura_manual"][0]["campos_faltantes"]
    assert data["requieren_captura_manual"][0]["motivo"] == "fechas_periodo_nulas"
    assert guardado == []


def test_upload_ambas_fechas_nulas_requiere_captura_manual(auth_client, monkeypatch):
    """Factura CFE con periodo_inicio y periodo_fin None → requiere_captura_manual con ambos en campos_faltantes."""
    _setup_electrico(monkeypatch)
    monkeypatch.setattr("web.clientes._detect_tipo", lambda _: "cfe")
    inv = _mock_cfe_invoice(numero_servicio="812990300016")
    inv.periodo_inicio = None
    inv.periodo_fin = None
    parser = MagicMock()
    parser.parse.return_value = inv
    monkeypatch.setattr("web.clientes.get_cfe_parser", lambda tarifa: parser)
    monkeypatch.setattr("web.clientes.save_cfe_invoice", lambda *a, **kw: (1, "x"))

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload",
        data={"facturas": _fake_pdf()},
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert data["procesados"] == 0
    faltantes = data["requieren_captura_manual"][0]["campos_faltantes"]
    assert "periodo_inicio" in faltantes
    assert "periodo_fin" in faltantes


def test_upload_manual_exitoso(auth_client, monkeypatch):
    """POST a /upload/manual con datos completos → guarda con validacion_manual=True."""
    import datetime
    _setup_electrico(monkeypatch)
    guardado_kwargs = {}
    def _fake_save(inv, cliente_id=None, contrato_id=None, **kwargs):
        guardado_kwargs.update(kwargs)
        return (99, "2024 ENE CFE 812990300016")
    monkeypatch.setattr("web.clientes.save_cfe_invoice", _fake_save)

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload/manual",
        data={
            "numero_servicio": "812990300016",
            "periodo_inicio": "2024-01-01",
            "periodo_fin": "2024-01-31",
            "folio": "F001",
            "fecha_emision": "2024-01-15",
            "fecha_limite_pago": "2024-02-10",
            "total_mxn": "50000.00",
            "motivo_captura_manual": "texto_cifrado",
            "tarifa": "GDMTH",
            "periodos_json": "[]",
            "componentes_mem_json": "[]",
        },
        content_type="multipart/form-data",
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["procesados"] == 1
    assert guardado_kwargs.get("validacion_manual") is True
    assert guardado_kwargs.get("motivo_captura_manual") == "texto_cifrado"


def test_upload_manual_sin_numero_servicio_falla(auth_client, monkeypatch):
    """POST a /upload/manual sin numero_servicio → 400 con mensaje de error."""
    _setup_electrico(monkeypatch)

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload/manual",
        data={
            "numero_servicio": "",
            "periodo_inicio": "2024-01-01",
            "periodo_fin": "2024-01-31",
            "motivo_captura_manual": "texto_cifrado",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "numero_servicio" in data["error"]


def test_upload_manual_sin_periodo_falla(auth_client, monkeypatch):
    """POST a /upload/manual sin periodo_inicio → 400."""
    _setup_electrico(monkeypatch)

    resp = auth_client.post(
        "/clientes/1/contratos/10/upload/manual",
        data={
            "numero_servicio": "812990300016",
            "periodo_inicio": "",
            "periodo_fin": "2024-01-31",
            "motivo_captura_manual": "texto_cifrado",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "periodo_inicio" in data["error"]
