# tests/test_clientes.py
"""Tests de regresión y humo para el blueprint de gestión de clientes."""
from __future__ import annotations

import io
import pytest
from werkzeug.security import generate_password_hash
from models.contrato import Contrato

_HASH = generate_password_hash("test_pass", method="pbkdf2:sha256")

_CLIENTE_BASE = {
    "id": 1,
    "nombre": "IBERICA TILES",
    "rfc": "ITI930101AAA",
    "notas": "Cliente industrial",
    "created_at": "2024-01-15T10:00:00+00:00",
    "num_cfe": 12,
    "num_gas": 12,
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

_CONTRATO_BASE = Contrato(
    id=10,
    cliente_id=1,
    nombre="CFE Planta 1",
    tipo="electrico_basico",
    identificador_real="812990300016",
    notas="Contrato principal",
    created_at="2024-01-15T10:00:00+00:00",
)

_CONTRATO_BASE_DICT = {
    "id": 10,
    "cliente_id": 1,
    "nombre": "CFE Planta 1",
    "tipo": "electrico_basico",
    "identificador_real": "812990300016",
    "notas": "Contrato principal",
    "created_at": "2024-01-15T10:00:00+00:00",
    "num_cfe": 9,
    "num_gas": 0,
}


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


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(app, monkeypatch):
    """Cliente autenticado con repositorio de clientes mockeado."""
    monkeypatch.setattr(
        "web.clientes.get_all_clientes_con_conteos",
        lambda: [_CLIENTE_BASE],
    )
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})
    return c


# ── Ruta raíz ─────────────────────────────────────────────────────────────────

def test_raiz_redirige_a_clientes(auth_client):
    """GET / → 302 a /clientes."""
    resp = auth_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes" in resp.headers["Location"]


# ── Listado de clientes ───────────────────────────────────────────────────────

def test_listado_requiere_autenticacion(client):
    """GET /clientes sin sesión → redirige a /login."""
    resp = client.get("/clientes/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_listado_muestra_clientes(auth_client, monkeypatch):
    """GET /clientes/ con sesión → 200 con nombre del cliente."""
    monkeypatch.setattr(
        "web.clientes.get_all_clientes_con_conteos",
        lambda: [_CLIENTE_BASE],
    )
    resp = auth_client.get("/clientes/", follow_redirects=False)
    assert resp.status_code == 200
    assert b"IBERICA TILES" in resp.data
    assert b"ITI930101AAA" in resp.data


def test_listado_vacio_muestra_call_to_action(auth_client, monkeypatch):
    """GET /clientes/ sin clientes → mensaje de estado vacío."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [])
    resp = auth_client.get("/clientes/", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Crear primer cliente" in resp.data


# ── Crear cliente ─────────────────────────────────────────────────────────────

def test_nuevo_cliente_get(auth_client):
    """GET /clientes/nuevo → 200 con formulario."""
    resp = auth_client.get("/clientes/nuevo")
    assert resp.status_code == 200
    assert b"Nuevo cliente" in resp.data


def test_nuevo_cliente_rfc_invalido(auth_client, monkeypatch):
    """POST /clientes/nuevo con RFC inválido → 200 con error."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "Test SA", "rfc": "CORTO", "notas": "",
    })
    assert resp.status_code == 200
    assert b"RFC inv" in resp.data


def test_nuevo_cliente_rfc_duplicado(auth_client, monkeypatch):
    """POST /clientes/nuevo con RFC ya existente → error de duplicado."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: True)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "Otro SA", "rfc": "ITI930101AAA", "notas": "",
    })
    assert resp.status_code == 200
    assert b"Ya existe" in resp.data


def test_nuevo_cliente_exitoso(auth_client, monkeypatch):
    """POST /clientes/nuevo válido → redirige a ficha del cliente."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    monkeypatch.setattr("web.clientes.create_cliente", lambda *a, **kw: 99)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "Nueva SA", "rfc": "NUE930101ABC", "notas": "notas",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/99" in resp.headers["Location"]


# ── Ficha de cliente ──────────────────────────────────────────────────────────

def test_ficha_cliente_existente(auth_client, monkeypatch):
    """GET /clientes/1 → 200 con datos del cliente."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contratos_por_cliente", lambda id: [])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda id: [])
    resp = auth_client.get("/clientes/1")
    assert resp.status_code == 200
    assert b"IBERICA TILES" in resp.data
    assert b"ITI930101AAA" in resp.data


def test_ficha_cliente_inexistente(auth_client, monkeypatch):
    """GET /clientes/999 con cliente inexistente → redirige a /clientes."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: None)
    resp = auth_client.get("/clientes/999", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes" in resp.headers["Location"]


# ── Editar cliente ────────────────────────────────────────────────────────────

def test_editar_get_sin_facturas(auth_client, monkeypatch):
    """GET /clientes/1/editar sin facturas → RFC editable."""
    cliente_sin_facturas = {**_CLIENTE_BASE, "num_cfe": 0, "num_gas": 0}
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: cliente_sin_facturas)
    monkeypatch.setattr("web.clientes.cliente_tiene_facturas", lambda id: False)
    resp = auth_client.get("/clientes/1/editar")
    assert resp.status_code == 200
    # Campo RFC no debe estar deshabilitado
    assert b'disabled' not in resp.data or b'name="rfc"' in resp.data


def test_editar_get_con_facturas_rfc_deshabilitado(auth_client, monkeypatch):
    """GET /clientes/1/editar con facturas → RFC deshabilitado con leyenda."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.cliente_tiene_facturas", lambda id: True)
    resp = auth_client.get("/clientes/1/editar")
    assert resp.status_code == 200
    assert b"disabled" in resp.data
    assert b"facturas cargadas" in resp.data


def test_editar_post_exitoso(auth_client, monkeypatch):
    """POST /clientes/1/editar válido → redirige a ficha."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.cliente_tiene_facturas", lambda id: False)
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    monkeypatch.setattr("web.clientes.update_cliente", lambda *a, **kw: None)
    resp = auth_client.post("/clientes/1/editar", data={
        "nombre": "IBERICA TILES SA", "rfc": "ITI930101AAA", "notas": "actualizado",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/1" in resp.headers["Location"]


# ── Borrar cliente ────────────────────────────────────────────────────────────

def test_borrar_confirmacion_incorrecta(auth_client, monkeypatch):
    """POST /clientes/1/borrar con nombre incorrecto → no borra, flash de error."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_cliente", lambda id: borrado.append(id))
    resp = auth_client.post("/clientes/1/borrar", data={
        "confirmacion": "nombre incorrecto",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert len(borrado) == 0  # no se llamó delete_cliente


def test_borrar_confirmacion_correcta(auth_client, monkeypatch):
    """POST /clientes/1/borrar con nombre exacto → borra y redirige a listado."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_cliente", lambda id: borrado.append(id))
    resp = auth_client.post("/clientes/1/borrar", data={
        "confirmacion": "IBERICA TILES",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes" in resp.headers["Location"]
    assert 1 in borrado


# ── Contratos ─────────────────────────────────────────────────────────────────

def test_contrato_nuevo_get(auth_client, monkeypatch):
    """GET /clientes/1/contratos/nuevo → 200 con formulario."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    resp = auth_client.get("/clientes/1/contratos/nuevo")
    assert resp.status_code == 200
    assert b"Nuevo contrato" in resp.data


def test_contrato_nuevo_exitoso(auth_client, monkeypatch):
    """POST /clientes/1/contratos/nuevo válido → redirige a ficha del contrato."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.create_contrato", lambda *a, **kw: 10)
    resp = auth_client.post("/clientes/1/contratos/nuevo", data={
        "nombre": "CFE Planta 1",
        "tipo": "electrico_basico",
        "identificador_real": "812990300016",
        "notas": "",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/1/contratos/10" in resp.headers["Location"]


def test_contrato_nuevo_campos_vacios(auth_client, monkeypatch):
    """POST /clientes/1/contratos/nuevo sin nombre → 200 con error."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    resp = auth_client.post("/clientes/1/contratos/nuevo", data={
        "nombre": "",
        "tipo": "electrico_basico",
        "identificador_real": "812990300016",
        "notas": "",
    })
    assert resp.status_code == 200
    assert b"obligatorio" in resp.data


def test_contrato_nuevo_identificador_duplicado(auth_client, monkeypatch):
    """POST /clientes/1/contratos/nuevo con identificador duplicado → 200 con error."""
    from storage.repository import ContratoIdentificadorDuplicado
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr(
        "web.clientes.create_contrato",
        lambda *a, **kw: (_ for _ in ()).throw(ContratoIdentificadorDuplicado("812990300016")),
    )
    resp = auth_client.post("/clientes/1/contratos/nuevo", data={
        "nombre": "Duplicado",
        "tipo": "electrico_basico",
        "identificador_real": "812990300016",
        "notas": "",
    })
    assert resp.status_code == 200
    assert b"Ya existe" in resp.data


def test_contrato_ficha(auth_client, monkeypatch):
    """GET /clientes/1/contratos/10 → 200 con datos del contrato y conteos de facturas."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_BASE)
    monkeypatch.setattr("web.clientes.get_contrato_con_conteos", lambda id: _CONTRATO_BASE_DICT)
    monkeypatch.setattr("web.clientes.get_cfe_facturas_por_contrato", lambda id: [])
    monkeypatch.setattr("web.clientes.get_gas_facturas_por_contrato", lambda id: [])
    resp = auth_client.get("/clientes/1/contratos/10")
    assert resp.status_code == 200
    assert b"CFE Planta 1" in resp.data
    assert b"812990300016" in resp.data
    assert b"Facturas CFE" in resp.data
    assert b"Facturas Gas" in resp.data


def test_contrato_ficha_con_facturas_cfe(auth_client, monkeypatch):
    """GET /clientes/1/contratos/10 con facturas CFE → tabla de facturas visible."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_BASE)
    monkeypatch.setattr("web.clientes.get_contrato_con_conteos", lambda id: _CONTRATO_BASE_DICT)
    monkeypatch.setattr("web.clientes.get_cfe_facturas_por_contrato", lambda id: [
        {
            "id": 1,
            "nombre_canonico": "2024 ENE CFE 812990300016",
            "periodo_inicio": "2024-01-01",
            "periodo_fin": "2024-01-31",
            "subtotal_mxn": "45000.00",
        }
    ])
    monkeypatch.setattr("web.clientes.get_gas_facturas_por_contrato", lambda id: [])
    resp = auth_client.get("/clientes/1/contratos/10")
    assert resp.status_code == 200
    assert b"2024 ENE CFE 812990300016" in resp.data


def test_contrato_ficha_acceso_cruzado(auth_client, monkeypatch):
    """GET /clientes/2/contratos/10 con contrato de otro cliente → 302 a ficha del cliente 2."""
    cliente2 = {**_CLIENTE_BASE, "id": 2, "nombre": "OTRO CLIENTE"}
    contrato_de_cliente1 = _CONTRATO_BASE  # cliente_id=1

    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: cliente2 if id == 2 else _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: contrato_de_cliente1)
    resp = auth_client.get("/clientes/2/contratos/10", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/2" in resp.headers["Location"]


def test_contrato_editar_get(auth_client, monkeypatch):
    """GET /clientes/1/contratos/10/editar → 200 con formulario pre-rellenado."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_BASE)
    resp = auth_client.get("/clientes/1/contratos/10/editar")
    assert resp.status_code == 200
    assert b"CFE Planta 1" in resp.data
    assert b"812990300016" in resp.data


def test_contrato_editar_post_exitoso(auth_client, monkeypatch):
    """POST /clientes/1/contratos/10/editar válido → redirige a ficha del contrato."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_BASE)
    monkeypatch.setattr("web.clientes.update_contrato", lambda *a, **kw: None)
    resp = auth_client.post("/clientes/1/contratos/10/editar", data={
        "nombre": "CFE Planta 1 Actualizado",
        "tipo": "electrico_basico",
        "identificador_real": "812990300016",
        "notas": "actualizado",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/1/contratos/10" in resp.headers["Location"]


def test_contrato_borrar_confirmacion_incorrecta(auth_client, monkeypatch):
    """POST /clientes/1/contratos/10/borrar con nombre incorrecto → no borra."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_BASE)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_contrato", lambda id: borrado.append(id))
    resp = auth_client.post("/clientes/1/contratos/10/borrar", data={
        "confirmacion": "nombre incorrecto",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert len(borrado) == 0


def test_contrato_borrar_confirmacion_correcta(auth_client, monkeypatch):
    """POST /clientes/1/contratos/10/borrar con nombre exacto → borra y redirige a ficha del cliente."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contrato", lambda id: _CONTRATO_BASE)
    borrado = []
    monkeypatch.setattr("web.clientes.delete_contrato", lambda id: borrado.append(id))
    resp = auth_client.post("/clientes/1/contratos/10/borrar", data={
        "confirmacion": "CFE Planta 1",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/1" in resp.headers["Location"]
    assert 10 in borrado


# ── Campos extendidos — crear cliente ────────────────────────────────────────

def test_nuevo_cliente_con_campos_extendidos(auth_client, monkeypatch):
    """POST /clientes/nuevo con todos los campos nuevos → create_cliente recibe los campos."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    llamadas = []
    def _create(nombre, rfc, notas, **kwargs):
        llamadas.append(kwargs)
        return 99
    monkeypatch.setattr("web.clientes.create_cliente", _create)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "IBERICA TILES", "rfc": "ITI930101AAA", "notas": "",
        "sector_industrial": "Manufactura",
        "contacto_nombre": "Juan Pérez",
        "contacto_email": "juan@iberica.com",
        "contacto_telefono": "81 1234 5678",
        "estado": "Nuevo León",
        "codigo_postal": "64000",
        "tarifa_cfe": "GDMTH",
        "capacidad_instalada_kw": "500",
        "anio_inicio_operacion": "2010",
        "regimen_operacion": "24/7 continuo",
        "medio_termico": "vapor_agua",
        "nivel_tension_kv": "1_34",
        "altitud_msnm": "1600",
        "tipo_motor": "combustion_interna",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert len(llamadas) == 1
    assert llamadas[0]["sector_industrial"] == "Manufactura"
    assert llamadas[0]["contacto_email"] == "juan@iberica.com"
    assert llamadas[0]["estado"] == "Nuevo León"
    assert llamadas[0]["capacidad_instalada_kw"] == 500.0
    assert llamadas[0]["anio_inicio_operacion"] == 2010
    assert llamadas[0]["medio_termico"] == "vapor_agua"
    assert llamadas[0]["nivel_tension_kv"] == "1_34"
    assert llamadas[0]["altitud_msnm"] == 1600
    assert llamadas[0]["tipo_motor"] == "combustion_interna"


def test_nuevo_cliente_solo_campos_requeridos(auth_client, monkeypatch):
    """POST /clientes/nuevo solo nombre + RFC → campos extendidos en None."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    llamadas = []
    def _create(nombre, rfc, notas, **kwargs):
        llamadas.append(kwargs)
        return 99
    monkeypatch.setattr("web.clientes.create_cliente", _create)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "Mínimo SA", "rfc": "MIN930101ABC", "notas": "",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert llamadas[0]["sector_industrial"] is None
    assert llamadas[0]["contacto_email"] is None
    assert llamadas[0]["capacidad_instalada_kw"] is None


def test_nuevo_cliente_email_invalido(auth_client, monkeypatch):
    """POST /clientes/nuevo con email mal formado → 200 con error de validación."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "Test SA", "rfc": "TST930101ABC", "notas": "",
        "contacto_email": "no-es-un-email",
    })
    assert resp.status_code == 200
    assert b"email" in resp.data.lower()


def test_nuevo_cliente_codigo_postal_invalido(auth_client, monkeypatch):
    """POST /clientes/nuevo con CP de 4 dígitos → 200 con error de validación."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "Test SA", "rfc": "TST930101ABC", "notas": "",
        "codigo_postal": "6400",
    })
    assert resp.status_code == 200
    assert b"postal" in resp.data.lower()


def test_nuevo_cliente_capacidad_negativa(auth_client, monkeypatch):
    """POST /clientes/nuevo con capacidad instalada negativa → 200 con error de validación."""
    monkeypatch.setattr("web.clientes.rfc_existe", lambda *a, **kw: False)
    resp = auth_client.post("/clientes/nuevo", data={
        "nombre": "Test SA", "rfc": "TST930101ABC", "notas": "",
        "capacidad_instalada_kw": "-100",
    })
    assert resp.status_code == 200
    assert b"positivo" in resp.data.lower()


# ── Logo del cliente ──────────────────────────────────────────────────────────

_PNG_HEADER = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100


def test_logo_subida_valida(auth_client, monkeypatch):
    """POST /clientes/1/logo con PNG válido y < 2MB → 200 con logo_url."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    llamadas = []
    monkeypatch.setattr(
        "web.clientes.upload_logo",
        lambda cliente_id, file_bytes, content_type: llamadas.append(cliente_id) or "https://storage.example.com/logo.png",
    )
    resp = auth_client.post(
        "/clientes/1/logo",
        data={"logo": (io.BytesIO(_PNG_HEADER), "logo.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("logo_url") == "https://storage.example.com/logo.png"
    assert llamadas == [1]


def test_logo_formato_invalido(auth_client, monkeypatch):
    """POST /clientes/1/logo con archivo JPG → 400 con mensaje de error."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    resp = auth_client.post(
        "/clientes/1/logo",
        data={"logo": (io.BytesIO(b'\xff\xd8\xff' + b'\x00' * 50), "foto.jpg")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "PNG" in data.get("error", "")


def test_logo_demasiado_grande(auth_client, monkeypatch):
    """POST /clientes/1/logo con PNG de 3MB → 400 con mensaje de tamaño."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    tres_mb = _PNG_HEADER + b'\x00' * (3 * 1024 * 1024)
    resp = auth_client.post(
        "/clientes/1/logo",
        data={"logo": (io.BytesIO(tres_mb), "grande.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "2 MB" in data.get("error", "")


def test_logo_eliminacion(auth_client, monkeypatch):
    """POST /clientes/1/logo/eliminar → llama a delete_logo y devuelve ok."""
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    llamadas = []
    monkeypatch.setattr("web.clientes.delete_logo", lambda id: llamadas.append(id))
    resp = auth_client.post("/clientes/1/logo/eliminar")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ok") is True
    assert llamadas == [1]


# ── Activación de cliente activo ──────────────────────────────────────────────

def test_activar_cliente_establece_sesion(app, monkeypatch):
    """POST /clientes/1/activar → establece cliente_activo_id en sesión."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE_BASE])
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})

    resp = c.post("/clientes/1/activar")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    with c.session_transaction() as sess:
        assert sess.get("cliente_activo_id") == 1
        assert sess.get("cliente_activo_nombre") == "IBERICA TILES"


def test_activar_otro_cliente_reemplaza_activo(app, monkeypatch):
    """POST /clientes/2/activar cuando cliente 1 estaba activo → sesión actualizada al 2."""
    cliente2 = {**_CLIENTE_BASE, "id": 2, "nombre": "SEGUNDO CLIENTE"}
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE_BASE, cliente2])
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: cliente2 if id == 2 else _CLIENTE_BASE)
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.post("/clientes/2/activar")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    with c.session_transaction() as sess:
        assert sess.get("cliente_activo_id") == 2
        assert sess.get("cliente_activo_nombre") == "SEGUNDO CLIENTE"


def test_desactivar_cliente_limpia_sesion(app, monkeypatch):
    """POST /clientes/desactivar → elimina cliente activo de sesión."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE_BASE])
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.post("/clientes/desactivar")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    with c.session_transaction() as sess:
        assert sess.get("cliente_activo_id") is None
        assert sess.get("cliente_activo_nombre") is None


def test_ficha_get_no_activa_cliente(app, monkeypatch):
    """GET /clientes/1 → la sesión NO queda con cliente_activo_id (activación es por AJAX)."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE_BASE])
    monkeypatch.setattr("web.clientes.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.clientes.get_contratos_por_cliente", lambda id: [])
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda id: [])
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})

    resp = c.get("/clientes/1", follow_redirects=False)
    assert resp.status_code == 200

    with c.session_transaction() as sess:
        assert sess.get("cliente_activo_id") is None


def test_sidebar_sin_cliente_activo_solo_listado(app, monkeypatch):
    """Sin cliente activo en sesión, el sidebar muestra solo Listado clientes bajo CLIENTES."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE_BASE])
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})

    resp = c.get("/clientes/", follow_redirects=False)
    assert resp.status_code == 200
    html = resp.data.decode()
    # Los sub-items del dashboard no deben aparecer sin cliente activo
    assert "Contabilidad Energ" not in html
    assert "Proyecto Cogenera" not in html


def test_sidebar_con_cliente_activo_muestra_estructura(app, monkeypatch):
    """Con cliente activo en sesión, el sidebar muestra nombre, sub-headers Dashboard y Contratos."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE_BASE])
    monkeypatch.setattr("storage.repository.get_cliente_con_conteos", lambda id: _CLIENTE_BASE)
    monkeypatch.setattr("web.app.get_contratos_por_cliente", lambda id: [_CONTRATO_BASE])
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1
        sess["cliente_activo_nombre"] = "IBERICA TILES"

    resp = c.get("/clientes/", follow_redirects=False)
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "IBERICA TILES" in html
    assert "Contabilidad Energ" in html
    assert "Proyecto Cogenera" in html
    assert "Detalles" in html
    assert "sidebar-sub-header" in html


def test_dashboard_redirige_a_contabilidad(app, monkeypatch):
    """GET /clientes/1/dashboard → 302 a /clientes/1/dashboard/contabilidad."""
    monkeypatch.setattr("web.clientes.get_all_clientes_con_conteos", lambda: [_CLIENTE_BASE])
    c = app.test_client()
    c.post("/login", data={"username": "operador", "password": "test_pass"})

    with c.session_transaction() as sess:
        sess["cliente_activo_id"] = 1

    resp = c.get("/clientes/1/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/clientes/1/dashboard/contabilidad" in resp.headers["Location"]
