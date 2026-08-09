# web/clientes.py
from __future__ import annotations

import json as _json
import logging
import re
import tempfile
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, session, url_for
from web.auth import get_current_user as _get_current_user
from web.auth_permissions import usuario_puede_borrar, usuario_puede_crear, filtrar_empresas_para_usuario
from web.error_logger import log_error
from calc.excepciones import PeriodoIncompletoError
from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente
from models.contrato import TIPOS_VALIDOS, TIPOS_ELECTRICOS, TIPO_ELECTRICO_BASICO, TIPO_ELECTRICO_CALIFICADO
from parsers.cfe import get_cfe_parser
from parsers.gas import get_gas_parser
from parsers.electricidad_calificado.gin import GINParser
from storage.repository import (
    get_all_clientes_con_conteos,
    get_cliente_con_conteos,
    create_cliente,
    update_cliente,
    delete_cliente,
    upload_logo,
    delete_logo,
    get_contratos_por_cliente,
    get_contrato,
    get_contrato_con_conteos,
    create_contrato,
    update_contrato,
    delete_contrato,
    ContratoIdentificadorDuplicado,
    obtener_plantas_por_cliente,
    obtener_planta,
    crear_planta,
    actualizar_planta,
    planta_tiene_recursos,
    save_cfe_invoice,
    save_gas_invoice,
    get_cfe_facturas_por_contrato,
    get_gas_facturas_por_contrato,
    delete_cfe_factura,
    delete_gas_factura,
    get_sidebar_data_contrato,
    get_sidebar_data_cliente,
    get_meses_seleccionados_por_contrato,
    get_meses_con_factura,
    upsert_mes_seleccionado,
    delete_mes_seleccionado,
    upsert_meses_seleccionados_anio,
    delete_meses_seleccionados_anio,
    get_facturas_calificado_por_contrato,
    create_factura_calificado,
    get_factura_calificado,
    update_factura_calificado,
    delete_factura_calificado,
    get_tipos_electricos_con_meses_seleccionados,
    update_precio_gas_manual,
    get_ultimas_cfe_invoices,
    get_ultimas_gas_invoices,
    get_ultimas_ppa_invoices,
    get_mediciones_por_cliente,
    get_medicion,
    create_medicion,
    save_medicion_datos,
    get_medicion_datos,
    update_medicion,
    delete_medicion,
    get_cliente_chp_params,
    update_cliente_chp_params,
    get_chp_session_params,
    save_chp_session_params,
    get_modelado_chp,
    get_modelado_chp_by_id,
    save_modelado_chp,
    save_modelado_chp_curva,
    get_modelado_chp_curva,
)

logger = logging.getLogger(__name__)

_RFC_RE = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

_SECTORES = [
    "Hotelero", "Manufactura", "Alimentos y bebidas", "Químico", "Textil",
    "Pesquero", "Forestal", "Cerámico", "Plásticos", "Metalúrgico", "Otro",
]
_ESTADOS = [
    "Aguascalientes", "Baja California", "Baja California Sur", "Campeche",
    "Chiapas", "Chihuahua", "Ciudad de México", "Coahuila", "Colima",
    "Durango", "Estado de México", "Guanajuato", "Guerrero", "Hidalgo",
    "Jalisco", "Michoacán", "Morelos", "Nayarit", "Nuevo León", "Oaxaca",
    "Puebla", "Querétaro", "Quintana Roo", "San Luis Potosí", "Sinaloa",
    "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatán",
    "Zacatecas",
]
_TARIFAS_CFE = ["GDMTH", "GDMTO", "PDBT", "DAC", "DIST", "DIT"]
_REGIMENES = ["24/7 continuo", "Dos turnos", "Un turno", "Estacional"]

_MOTIVOS_CAPTURA_MANUAL = [
    "texto_cifrado",
    "campos_ilegibles",
    "pdf_escaneado",
    "otro",
]


def _invoice_to_campos_extraidos(invoice: CFEInvoice) -> dict:
    """Serializa los campos de un CFEInvoice a un dict JSON-serializable.

    Usa comprobaciones de tipo estrictas para que sea seguro con MagicMock en tests.
    """
    from datetime import date as _date_cls
    from decimal import Decimal as _Decimal_cls

    def _date(d):
        return d.isoformat() if isinstance(d, _date_cls) else None

    def _dec(d):
        return str(d) if isinstance(d, _Decimal_cls) else None

    def _str(s):
        return s if isinstance(s, str) else None

    def _int_safe(i):
        return i if isinstance(i, int) and not isinstance(i, bool) else None

    periodos_raw = getattr(invoice, "periodos", [])
    periodos = (
        [
            {
                "periodo": _str(p.periodo),
                "consumo_kwh": _dec(p.consumo_kwh),
                "demanda_kw": _dec(p.demanda_kw),
                "costo_unitario_kwh": _dec(p.costo_unitario_kwh),
            }
            for p in periodos_raw
        ]
        if isinstance(periodos_raw, list)
        else []
    )

    componentes_raw = getattr(invoice, "componentes_mem", [])
    componentes_mem = (
        [
            {
                "nombre": _str(c.nombre),
                "cargo_fijo_mxn": _dec(c.cargo_fijo_mxn),
                "cargo_demanda_mxn": _dec(c.cargo_demanda_mxn),
                "cargo_energia_mxn": _dec(c.cargo_energia_mxn),
                "importe_mxn": _dec(c.importe_mxn),
            }
            for c in componentes_raw
        ]
        if isinstance(componentes_raw, list)
        else []
    )

    advertencias_raw = getattr(invoice, "advertencias", [])

    return {
        "uuid_cfdi": _str(getattr(invoice, "uuid_cfdi", None)),
        "folio": _str(getattr(invoice, "folio", None)),
        "serie": _str(getattr(invoice, "serie", None)),
        "fecha_emision": _date(getattr(invoice, "fecha_emision", None)),
        "periodo_inicio": _date(getattr(invoice, "periodo_inicio", None)),
        "periodo_fin": _date(getattr(invoice, "periodo_fin", None)),
        "fecha_limite_pago": _date(getattr(invoice, "fecha_limite_pago", None)),
        "nombre_cliente": _str(getattr(invoice, "nombre_cliente", None)),
        "rfc_cliente": _str(getattr(invoice, "rfc_cliente", None)),
        "numero_servicio": _str(getattr(invoice, "numero_servicio", None)),
        "rmu": _str(getattr(invoice, "rmu", None)),
        "tarifa": _str(getattr(invoice, "tarifa", None)),
        "numero_medidor": _str(getattr(invoice, "numero_medidor", None)),
        "multiplicador": _int_safe(getattr(invoice, "multiplicador", None)),
        "carga_conectada_kw": _dec(getattr(invoice, "carga_conectada_kw", None)),
        "demanda_contratada_kw": _dec(getattr(invoice, "demanda_contratada_kw", None)),
        "kw_max": _dec(getattr(invoice, "kw_max", None)),
        "kvarh": _dec(getattr(invoice, "kvArh", None)),
        "factor_potencia_pct": _dec(getattr(invoice, "factor_potencia_pct", None)),
        "cargo_fijo_mxn": _dec(getattr(invoice, "cargo_fijo_mxn", None)),
        "energia_total_mxn": _dec(getattr(invoice, "energia_total_mxn", None)),
        "cargo_factor_potencia_mxn": _dec(getattr(invoice, "cargo_factor_potencia_mxn", None)),
        "subtotal_mxn": _dec(getattr(invoice, "subtotal_mxn", None)),
        "iva_mxn": _dec(getattr(invoice, "iva_mxn", None)),
        "facturacion_periodo_mxn": _dec(getattr(invoice, "facturacion_periodo_mxn", None)),
        "derecho_alumbrado_publico_mxn": _dec(getattr(invoice, "derecho_alumbrado_publico_mxn", None)),
        "credito_aplicado_mxn": _dec(getattr(invoice, "credito_aplicado_mxn", None)),
        "total_mxn": _dec(getattr(invoice, "total_mxn", None)),
        "advertencias": advertencias_raw if isinstance(advertencias_raw, list) else [],
        "periodos": periodos,
        "componentes_mem": componentes_mem,
    }


def _parse_date_field(s: str | None):
    """Convierte 'YYYY-MM-DD' a date o None si el string está vacío/inválido."""
    if not s or not s.strip():
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal_field(s: str | None, default: Decimal = Decimal("0")) -> Decimal:
    """Convierte string a Decimal, devuelve default si vacío/inválido."""
    if not s or not s.strip():
        return default
    try:
        return Decimal(s.strip())
    except InvalidOperation:
        return default


def _sanitizar(valor: str) -> str:
    """Normaliza Unicode y elimina caracteres de control/formato (Cc/Cf, p.ej. U+202D, U+202C)."""
    normalizado = unicodedata.normalize("NFKC", valor)
    limpio = "".join(c for c in normalizado if unicodedata.category(c) not in ("Cc", "Cf"))
    return limpio.strip().upper()


def _sanitizar_texto(valor: str) -> str | None:
    """Normaliza Unicode y elimina caracteres de control/formato. Preserva mayúsculas/minúsculas."""
    if not valor:
        return None
    normalizado = unicodedata.normalize("NFKC", valor)
    limpio = "".join(c for c in normalizado if unicodedata.category(c) not in ("Cc", "Cf"))
    resultado = limpio.strip()
    return resultado or None


def _extraer_vapor_pct(form) -> int | None:
    """Deriva medio_termico_vapor_pct a partir del tipo de medio térmico seleccionado."""
    tipo = form.get("medio_termico", "").strip()
    if tipo == "vapor_o_agua":
        return 100
    if tipo == "gases_combustion":
        return 0
    if tipo == "mezcla":
        v = form.get("medio_termico_vapor_pct", "").strip()
        try:
            pct = int(v)
            if 0 <= pct <= 100:
                return pct
        except (ValueError, TypeError):
            pass
        return 50
    return None


def _validar_campos_extendidos(form) -> str | None:
    """Valida los campos opcionales del formulario de cliente. Devuelve mensaje de error o None."""
    from datetime import date as _date
    email = form.get("contacto_email", "").strip()
    if email and not _EMAIL_RE.match(email):
        return "El email de contacto no tiene un formato válido."
    cp = form.get("codigo_postal", "").strip()
    if cp and not re.fullmatch(r'\d{5}', cp):
        return "El código postal debe tener exactamente 5 dígitos."
    for campo in ("capacidad_instalada_kw", "demanda_contratada_kw", "consumo_anual_estimado_mwh"):
        val = form.get(campo, "").strip()
        if val:
            try:
                if float(val) <= 0:
                    return f"El valor de '{campo.replace('_', ' ')}' debe ser un número positivo."
            except ValueError:
                return f"El valor de '{campo.replace('_', ' ')}' debe ser un número."
    anio = form.get("anio_inicio_operacion", "").strip()
    if anio:
        try:
            anio_int = int(anio)
            current_year = _date.today().year
            if not (1900 <= anio_int <= current_year + 5):
                return f"El año de inicio debe estar entre 1900 y {current_year + 5}."
        except ValueError:
            return "El año de inicio de operación debe ser un número entero."
    altitud = form.get("altitud_msnm", "").strip()
    if altitud:
        try:
            alt_int = int(altitud)
            if not (0 <= alt_int <= 5000):
                return "La altitud debe estar entre 0 y 5000 msnm."
        except ValueError:
            return "La altitud debe ser un número entero."
    if form.get("medio_termico", "").strip() == "mezcla":
        v = form.get("medio_termico_vapor_pct", "").strip()
        if v:
            try:
                pct = int(v)
                if not (0 <= pct <= 100):
                    return "El % Vapor debe estar entre 0 y 100."
            except ValueError:
                return "El % Vapor debe ser un número entero."
    return None


def _extraer_campos_extendidos(form) -> dict:
    """Extrae y sanitiza los campos opcionales del formulario. Devuelve dict listo para repository."""
    def _opt_float(key: str) -> float | None:
        v = form.get(key, "").strip()
        try:
            return float(v) if v else None
        except ValueError:
            return None

    def _opt_int(key: str) -> int | None:
        v = form.get(key, "").strip()
        try:
            return int(v) if v else None
        except ValueError:
            return None

    return {
        "sector_industrial": form.get("sector_industrial", "").strip() or None,
        "contacto_nombre": _sanitizar_texto(form.get("contacto_nombre", "")),
        "contacto_cargo": _sanitizar_texto(form.get("contacto_cargo", "")),
        "contacto_email": form.get("contacto_email", "").strip() or None,
        "contacto_telefono": form.get("contacto_telefono", "").strip() or None,
        "direccion": _sanitizar_texto(form.get("direccion", "")),
        "estado": form.get("estado", "").strip() or None,
        "codigo_postal": form.get("codigo_postal", "").strip() or None,
        "tarifa_cfe": form.get("tarifa_cfe", "").strip() or None,
        "capacidad_instalada_kw": _opt_float("capacidad_instalada_kw"),
        "demanda_contratada_kw": _opt_float("demanda_contratada_kw"),
        "anio_inicio_operacion": _opt_int("anio_inicio_operacion"),
        "regimen_operacion": form.get("regimen_operacion", "").strip() or None,
        "consumo_anual_estimado_mwh": _opt_float("consumo_anual_estimado_mwh"),
        "medio_termico": form.get("medio_termico", "").strip() or None,
        "medio_termico_vapor_pct": _extraer_vapor_pct(form),
        "nivel_tension_kv": form.get("nivel_tension_kv", "").strip() or None,
        "altitud_msnm": _opt_int("altitud_msnm"),
        "tipo_motor": form.get("tipo_motor", "").strip() or None,
    }


_FORM_SELECTS = {
    "sectores": _SECTORES,
    "estados": _ESTADOS,
    "tarifas_cfe": _TARIFAS_CFE,
    "regimenes": _REGIMENES,
}


def _detect_tipo(pdf_path: Path) -> str:
    """Devuelve 'cfe' o 'gas' inspeccionando el texto de la primera página del PDF."""
    import pdfplumber
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = (pdf.pages[0].extract_text() or "").upper()
    except Exception as e:
        raise ValueError(f"No se pudo leer el PDF: {e}") from e
    if "COMISIÓN FEDERAL" in text or "C.F.E." in text or "CFE" in text:
        return "cfe"
    if "ENGIE" in text or "GAS NATURAL" in text:
        return "gas"
    raise ValueError("No se pudo determinar el tipo de factura (CFE o Gas)")

clientes_bp = Blueprint("clientes", __name__, url_prefix="/clientes")


# ── Helpers de validación ─────────────────────────────────────────────────────

def _validar_rfc_formato(rfc: str) -> str | None:
    """Valida longitud del RFC SOLO si está lleno. Vacío es válido."""
    if not rfc:
        return None
    if len(rfc) not in (12, 13):
        return "RFC debe tener 12 o 13 caracteres."
    return None


# ── Rutas ─────────────────────────────────────────────────────────────────────

@clientes_bp.route("/")
def listado():
    user = _get_current_user()
    if user and user.get("rol") == "usuario_normal":
        if user.get("empresa_id"):
            return redirect(url_for("clientes.ficha", cliente_id=user["empresa_id"]))
        return render_template("error_sin_empresa.html"), 403
    clientes = get_all_clientes_con_conteos()
    if user:
        clientes = filtrar_empresas_para_usuario(clientes, user)
    return render_template("clientes/list.html", clientes=clientes)


@clientes_bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    user = _get_current_user()
    if not usuario_puede_crear(user or {}):
        log_error("negocio", "No tienes permisos para crear clientes.")
        flash("No tienes permisos para crear clientes.", "danger")
        return redirect(url_for("clientes.listado"))
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        rfc_raw = _sanitizar(request.form.get("rfc", ""))
        rfc = rfc_raw or None  # vacío → NULL en BD
        notas = request.form.get("notas", "").strip() or None
        campos = _extraer_campos_extendidos(request.form)

        if not nombre:
            error = "El nombre del cliente es obligatorio."
        else:
            error = _validar_rfc_formato(rfc_raw) or _validar_campos_extendidos(request.form)

        if error:
            return render_template(
                "clientes/nuevo.html",
                error=error, nombre=nombre, rfc=rfc_raw, notas=notas or "",
                **_FORM_SELECTS, **campos,
            )

        try:
            cliente_id = create_cliente(nombre, rfc, notas, **campos)
            logger.info("Cliente creado: id=%d, nombre='%s', rfc=%s", cliente_id, nombre, rfc)
            flash(f"Cliente '{nombre}' creado correctamente.", "success")
            return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
        except Exception as exc:
            logger.error("Error creando cliente nombre='%s', rfc=%s: %s", nombre, rfc, exc)
            return render_template(
                "clientes/nuevo.html",
                error=f"Error al crear el cliente: {exc}",
                nombre=nombre, rfc=rfc_raw, notas=notas or "",
                **_FORM_SELECTS, **campos,
            )

    return render_template(
        "clientes/nuevo.html",
        error=None, nombre="", rfc="", notas="",
        **_FORM_SELECTS,
    )


def _calcular_cre_params(cliente: dict) -> dict | None:
    """Calcula parámetros estáticos CRE para mostrar en la ficha.
    Requiere datos completos del cliente (nivel_tension_kv, altitud_msnm, tipo_motor,
    medio_termico_vapor_pct). Devuelve None si faltan datos.
    Carga las últimas 12 facturas para derivar la capacidad nominal.
    """
    from calc.cels import _calcular_ref_h, _FP, _refe
    from calc.cogen import _capacidad_nominal_kw, _capacidad_nominal_kw_ppa

    nivel = cliente.get("nivel_tension_kv")
    altitud = cliente.get("altitud_msnm")
    tipo_motor = cliente.get("tipo_motor")
    vapor_pct = cliente.get("medio_termico_vapor_pct")

    if any(v is None for v in [nivel, altitud, tipo_motor, vapor_pct]):
        return None

    fp = _FP.get(nivel)
    if fp is None:
        return None

    refh = _calcular_ref_h(int(vapor_pct))

    # Capacidad nominal: intentar CFE básico, luego PPA
    cap_kw = None
    try:
        cfe_inv = get_ultimas_cfe_invoices(cliente["id"], n=12)
        if cfe_inv:
            cap_kw = _capacidad_nominal_kw(cfe_inv)
    except Exception:
        pass
    if cap_kw is None:
        try:
            ppa_inv = get_ultimas_ppa_invoices(cliente["id"], n=12)
            if ppa_inv:
                cap_kw = _capacidad_nominal_kw_ppa(ppa_inv)
        except Exception:
            pass

    ref_e = _refe(cap_kw, int(altitud), tipo_motor) if cap_kw else None
    ref_e_prima = (ref_e * fp).quantize(Decimal("0.0001")) if ref_e else None

    return {
        "ref_h": refh,
        "fp": fp,
        "ref_e": ref_e,
        "ref_e_prima": ref_e_prima,
        "capacidad_nominal_kw": cap_kw,
        "nivel_tension_kv": nivel,
        "altitud_msnm": altitud,
        "tipo_motor": tipo_motor,
        "medio_termico_vapor_pct": int(vapor_pct),
    }


@clientes_bp.route("/<int:cliente_id>")
def ficha(cliente_id: int):
    from storage.repository import get_ppa_bloques_mensuales
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))
    # Activar cliente en sesión: sin esto el sidebar no muestra dashboard ni contratos
    session["cliente_activo_id"] = cliente_id
    session["cliente_activo_nombre"] = cliente["nombre"]
    session["cliente_activo_logo_url"] = cliente.get("logo_url")
    session.pop("_cp_cache", None)
    contratos = get_contratos_por_cliente(cliente_id)
    # PPA bloques para precarga: {anio: {mes: mwh_str}}
    ppa_bloques: dict[int, dict[int, str]] = {}
    try:
        for b in get_ppa_bloques_mensuales(cliente_id):
            ppa_bloques.setdefault(b["anio"], {})[b["mes"]] = b["bloque_contratado_mwh"]
    except Exception:
        pass
    user = _get_current_user()
    # Parámetros CRE: solo para admin/master_admin
    cre_params = None
    if user and user.get("rol") in ("master_admin", "admin"):
        try:
            cre_params = _calcular_cre_params(cliente)
        except Exception:
            pass
    mediciones_ficha = get_mediciones_por_cliente(cliente_id)
    plantas = obtener_plantas_por_cliente(cliente_id, solo_activas=False)
    resp = make_response(render_template(
        "clientes/ficha.html",
        cliente=cliente,
        contratos=contratos,
        ppa_bloques=ppa_bloques,
        cre_params=cre_params,
        mediciones_ficha=mediciones_ficha,
        plantas=plantas,
    ))
    if user and user.get("rol") in ("master_admin", "admin"):
        resp.set_cookie("last_cliente_id", str(cliente_id),
                        max_age=30 * 24 * 3600, samesite="Lax",
                        httponly=True, secure=not current_app.debug)
    return resp


@clientes_bp.route("/<int:cliente_id>/activar", methods=["POST"])
def cliente_activar(cliente_id: int):
    from flask import jsonify, make_response
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        return jsonify({"error": "Cliente no encontrado"}), 404
    session["cliente_activo_id"] = cliente_id
    session["cliente_activo_nombre"] = cliente["nombre"]
    session["cliente_activo_logo_url"] = cliente.get("logo_url")
    session.pop("_cp_cache", None)
    resp = make_response(jsonify({"ok": True}))
    user = _get_current_user()
    if user and user.get("rol") in ("master_admin", "admin"):
        resp.set_cookie(
            "last_cliente_id", str(cliente_id),
            max_age=30 * 24 * 3600, samesite="Lax",
            httponly=True, secure=not current_app.debug,
        )
    return resp


@clientes_bp.route("/desactivar", methods=["POST"])
def cliente_desactivar():
    from flask import jsonify, make_response
    session.pop("cliente_activo_id", None)
    session.pop("cliente_activo_nombre", None)
    session.pop("cliente_activo_logo_url", None)
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie("last_cliente_id")
    return resp


@clientes_bp.route("/<int:cliente_id>/editar", methods=["GET", "POST"])
def editar(cliente_id: int):
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        rfc_raw = request.form.get("rfc", "").strip().upper()
        rfc = rfc_raw or None  # vacío → NULL en BD
        notas = request.form.get("notas", "").strip() or None
        campos = _extraer_campos_extendidos(request.form)

        if not nombre:
            error = "El nombre del cliente es obligatorio."
        else:
            error = _validar_rfc_formato(rfc_raw) or _validar_campos_extendidos(request.form)

        if error:
            return render_template(
                "clientes/editar.html",
                cliente=cliente,
                error=error, nombre=nombre, rfc=rfc_raw, notas=notas or "",
                **_FORM_SELECTS, **campos,
            )

        try:
            update_cliente(cliente_id, nombre=nombre, notas=notas, rfc=rfc, **campos)
            chp_num_motores = int(request.form.get("chp_num_motores") or 1)
            chp_margen_kw = float(request.form.get("chp_margen_kw") or 0)
            update_cliente_chp_params(cliente_id, chp_num_motores, chp_margen_kw)
            logger.info("Cliente actualizado: id=%d, nombre='%s'", cliente_id, nombre)
            if session.get("cliente_activo_id") == cliente_id:
                session["cliente_activo_nombre"] = nombre
            flash("Datos del cliente actualizados.", "success")
            return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
        except Exception as exc:
            logger.error("Error actualizando cliente id=%d: %s", cliente_id, exc)
            return render_template(
                "clientes/editar.html",
                cliente=cliente,
                error=f"Error al guardar: {exc}", nombre=nombre, rfc=rfc_raw, notas=notas or "",
                **_FORM_SELECTS, **campos,
            )

    return render_template(
        "clientes/editar.html",
        cliente=cliente,
        error=None, nombre=cliente["nombre"],
        rfc=cliente.get("rfc") or "", notas=cliente.get("notas") or "",
        sector_industrial=cliente.get("sector_industrial"),
        contacto_nombre=cliente.get("contacto_nombre") or "",
        contacto_cargo=cliente.get("contacto_cargo") or "",
        contacto_email=cliente.get("contacto_email") or "",
        contacto_telefono=cliente.get("contacto_telefono") or "",
        direccion=cliente.get("direccion") or "",
        estado=cliente.get("estado"),
        codigo_postal=cliente.get("codigo_postal") or "",
        tarifa_cfe=cliente.get("tarifa_cfe"),
        capacidad_instalada_kw=cliente.get("capacidad_instalada_kw"),
        demanda_contratada_kw=cliente.get("demanda_contratada_kw"),
        anio_inicio_operacion=cliente.get("anio_inicio_operacion"),
        regimen_operacion=cliente.get("regimen_operacion"),
        consumo_anual_estimado_mwh=cliente.get("consumo_anual_estimado_mwh"),
        medio_termico=cliente.get("medio_termico"),
        medio_termico_vapor_pct=cliente.get("medio_termico_vapor_pct"),
        nivel_tension_kv=cliente.get("nivel_tension_kv"),
        altitud_msnm=cliente.get("altitud_msnm"),
        tipo_motor=cliente.get("tipo_motor"),
        **_FORM_SELECTS,
    )


@clientes_bp.route("/<int:cliente_id>/borrar", methods=["POST"])
def borrar(cliente_id: int):
    user = _get_current_user()
    if not usuario_puede_borrar(user or {}):
        log_error("negocio", "No tienes permisos para borrar clientes.")
        flash("No tienes permisos para borrar clientes.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    nombre = cliente["nombre"]
    confirmacion = request.form.get("confirmacion", "").strip()

    if confirmacion != nombre:
        log_error("validacion", "La confirmación no coincide con el nombre del cliente. No se realizó ningún cambio.")
        flash(
            "La confirmación no coincide con el nombre del cliente. No se realizó ningún cambio.",
            "danger",
        )
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    try:
        delete_cliente(cliente_id)
        logger.info(
            "Cliente borrado: id=%d, nombre='%s' (%d CFE, %d gas)",
            cliente_id, nombre, cliente["num_cfe"], cliente["num_gas"],
        )
        if session.get("cliente_activo_id") == cliente_id:
            session.pop("cliente_activo_id", None)
            session.pop("cliente_activo_nombre", None)
            session.pop("cliente_activo_logo_url", None)
        flash(f"Cliente '{nombre}' y todas sus facturas han sido borrados.", "success")
    except Exception as exc:
        logger.error("Error borrando cliente id=%d: %s", cliente_id, exc)
        log_error("negocio", f"Error al borrar el cliente: {exc}")
        flash(f"Error al borrar el cliente: {exc}", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    return redirect(url_for("clientes.listado"))


@clientes_bp.route("/<int:cliente_id>/logo", methods=["POST"])
def cliente_logo_subir(cliente_id: int):
    from flask import jsonify

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    f = request.files.get("logo")
    if not f or not f.filename:
        return jsonify({"error": "No se envió ningún archivo"}), 400

    if not f.filename.lower().endswith(".png"):
        return jsonify({"error": "Solo se aceptan archivos PNG con fondo transparente."}), 400

    file_bytes = f.read()
    if len(file_bytes) > 2 * 1024 * 1024:
        return jsonify({"error": "El logo no puede superar 2 MB."}), 400

    if not file_bytes.startswith(b'\x89PNG'):
        return jsonify({"error": "El archivo no es un PNG válido."}), 400

    try:
        logo_url = upload_logo(cliente_id, file_bytes, "image/png")
        if session.get("cliente_activo_id") == cliente_id:
            session["cliente_activo_logo_url"] = logo_url
        return jsonify({"logo_url": logo_url})
    except Exception as exc:
        logger.error("Error subiendo logo cliente_id=%d: %s", cliente_id, exc)
        return jsonify({"error": "No se pudo subir el logo. Los demás datos fueron guardados."}), 502


@clientes_bp.route("/<int:cliente_id>/logo/eliminar", methods=["POST"])
def cliente_logo_eliminar(cliente_id: int):
    from flask import jsonify

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    try:
        delete_logo(cliente_id)
        if session.get("cliente_activo_id") == cliente_id:
            session["cliente_activo_logo_url"] = None
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("Error eliminando logo cliente_id=%d: %s", cliente_id, exc)
        return jsonify({"error": str(exc)}), 500


# ── Contratos ─────────────────────────────────────────────────────────────────

def _verificar_acceso_contrato(contrato_id: int, cliente_id: int):
    """Carga el contrato y verifica que pertenezca al cliente dado.

    Devuelve el objeto Contrato si el acceso es válido.
    Si el contrato no existe, devuelve None.
    Si pertenece a otro cliente, hace flash + redirect y devuelve una Response.
    """
    contrato = get_contrato(contrato_id)
    if contrato is None:
        return None
    if contrato.cliente_id != cliente_id:
        otro_cliente = get_cliente_con_conteos(contrato.cliente_id)
        nombre_otro = otro_cliente["nombre"] if otro_cliente else f"id={contrato.cliente_id}"
        flash(
            f"El contrato '{contrato.nombre}' pertenece al cliente '{nombre_otro}', "
            f"no a este cliente. Has sido redirigido a la ficha del cliente actual.",
            "warning",
        )
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    return contrato


@clientes_bp.route("/<int:cliente_id>/contratos/nuevo", methods=["GET", "POST"])
def contrato_nuevo(cliente_id: int):
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    plantas = obtener_plantas_por_cliente(cliente_id)

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        tipo = request.form.get("tipo", "").strip()
        identificador_real = _sanitizar(request.form.get("identificador_real", ""))
        notas = request.form.get("notas", "").strip() or None
        planta_id_str = request.form.get("planta_id", "").strip()
        planta_id = int(planta_id_str) if planta_id_str.isdigit() else None

        error = None
        if not nombre:
            error = "El nombre del contrato es obligatorio."
        elif tipo not in TIPOS_VALIDOS:
            error = "Tipo inválido. Debe ser eléctrico básico (CFE), eléctrico calificado (PPA) o gas."
        elif not identificador_real:
            error = "El identificador real es obligatorio."
        elif plantas and planta_id is None:
            error = "Debes seleccionar una planta para el contrato."

        if error is None:
            try:
                contrato_id = create_contrato(cliente_id, nombre, tipo, identificador_real, notas, planta_id=planta_id)
                logger.info(
                    "Contrato creado: id=%d, cliente_id=%d, nombre='%s', planta_id=%s",
                    contrato_id, cliente_id, nombre, planta_id,
                )
                flash(f"Contrato '{nombre}' creado correctamente.", "success")
                return redirect(url_for(
                    "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
                ))
            except ContratoIdentificadorDuplicado:
                error = f"Ya existe un contrato con el identificador '{identificador_real}' para este cliente."
            except Exception as exc:
                logger.error("Error creando contrato cliente_id=%d: %s", cliente_id, exc)
                error = f"Error al crear el contrato: {exc}"

        return render_template(
            "clientes/contratos/nuevo.html",
            cliente=cliente,
            plantas=plantas,
            error=error,
            nombre=nombre,
            tipo=tipo,
            identificador_real=identificador_real,
            notas=notas or "",
            planta_id_sel=planta_id,
        )

    # GET — preseleccionar la planta activa de la sesión si existe
    from flask import session as _sess
    planta_id_default = _sess.get("planta_activa_id")
    return render_template(
        "clientes/contratos/nuevo.html",
        cliente=cliente,
        plantas=plantas,
        error=None,
        nombre="",
        tipo="electrico_basico",
        identificador_real="",
        notas="",
        planta_id_sel=planta_id_default,
    )


@clientes_bp.route("/<int:cliente_id>/contratos/<int:contrato_id>")
def contrato_ficha(cliente_id: int, contrato_id: int):
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    from flask import Response
    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        flash("El contrato solicitado no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    if isinstance(resultado, Response):
        return resultado

    contrato = get_contrato_con_conteos(contrato_id)
    facturas_cfe = get_cfe_facturas_por_contrato(contrato_id)
    facturas_gas = get_gas_facturas_por_contrato(contrato_id)
    try:
        facturas_calificado = get_facturas_calificado_por_contrato(contrato_id)
    except Exception:
        facturas_calificado = []

    return render_template(
        "clientes/contratos/ficha.html",
        cliente=cliente,
        contrato=contrato,
        facturas_cfe=facturas_cfe,
        facturas_gas=facturas_gas,
        facturas_calificado=facturas_calificado,
    )


@clientes_bp.route("/<int:cliente_id>/contratos/<int:contrato_id>/editar", methods=["GET", "POST"])
def contrato_editar(cliente_id: int, contrato_id: int):
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    from flask import Response
    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        flash("El contrato solicitado no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    if isinstance(resultado, Response):
        return resultado
    contrato = resultado

    plantas = obtener_plantas_por_cliente(cliente_id)

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        tipo = request.form.get("tipo", "").strip()
        identificador_real = _sanitizar(request.form.get("identificador_real", ""))
        notas = request.form.get("notas", "").strip() or None
        planta_id_str = request.form.get("planta_id", "").strip()
        planta_id = int(planta_id_str) if planta_id_str.isdigit() else None

        error = None
        if not nombre:
            error = "El nombre del contrato es obligatorio."
        elif tipo not in TIPOS_VALIDOS:
            error = "Tipo inválido. Debe ser eléctrico básico (CFE), eléctrico calificado (PPA) o gas."
        elif not identificador_real:
            error = "El identificador real es obligatorio."
        elif plantas and planta_id is None:
            error = "Debes seleccionar una planta para el contrato."

        if error is None:
            try:
                update_contrato(contrato_id, nombre, tipo, identificador_real, notas, planta_id=planta_id)
                logger.info("Contrato actualizado: id=%d, nombre='%s'", contrato_id, nombre)
                flash("Contrato actualizado correctamente.", "success")
                return redirect(url_for(
                    "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
                ))
            except ContratoIdentificadorDuplicado:
                error = f"Ya existe un contrato con el identificador '{identificador_real}' para este cliente."
            except Exception as exc:
                logger.error("Error actualizando contrato id=%d: %s", contrato_id, exc)
                error = f"Error al guardar: {exc}"

        return render_template(
            "clientes/contratos/editar.html",
            cliente=cliente,
            contrato=contrato,
            plantas=plantas,
            planta_id_sel=planta_id,
            error=error,
            nombre=nombre,
            tipo=tipo,
            identificador_real=identificador_real,
            notas=notas or "",
        )

    return render_template(
        "clientes/contratos/editar.html",
        cliente=cliente,
        contrato=contrato,
        plantas=plantas,
        planta_id_sel=contrato.planta_id,
        error=None,
        nombre=contrato.nombre,
        tipo=contrato.tipo,
        identificador_real=contrato.identificador_real,
        notas=contrato.notas or "",
    )


@clientes_bp.route("/<int:cliente_id>/contratos/<int:contrato_id>/borrar", methods=["POST"])
def contrato_borrar(cliente_id: int, contrato_id: int):
    user = _get_current_user()
    if not usuario_puede_borrar(user or {}):
        log_error("negocio", "No tienes permisos para borrar contratos.")
        flash("No tienes permisos para borrar contratos.", "danger")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    from flask import Response
    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        flash("El contrato solicitado no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    if isinstance(resultado, Response):
        return resultado
    contrato = resultado

    nombre = contrato.nombre
    confirmacion = request.form.get("confirmacion", "").strip()
    if confirmacion != nombre:
        log_error("validacion", "La confirmación no coincide con el nombre del contrato. No se realizó ningún cambio.")
        flash(
            "La confirmación no coincide con el nombre del contrato. No se realizó ningún cambio.",
            "danger",
        )
        return redirect(url_for(
            "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
        ))

    try:
        delete_contrato(contrato_id)
        logger.info(
            "Contrato borrado: id=%d, nombre='%s', cliente_id=%d", contrato_id, nombre, cliente_id
        )
        flash(f"Contrato '{nombre}' borrado correctamente.", "success")
    except Exception as exc:
        logger.error("Error borrando contrato id=%d: %s", contrato_id, exc)
        log_error("negocio", f"Error al borrar el contrato: {exc}")
        flash(f"Error al borrar el contrato: {exc}", "danger")
        return redirect(url_for(
            "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
        ))

    return redirect(url_for("clientes.ficha", cliente_id=cliente_id))


@clientes_bp.route("/<int:cliente_id>/contratos/<int:contrato_id>/upload", methods=["POST"])
def contrato_upload(cliente_id: int, contrato_id: int):
    from flask import Response, jsonify

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        return jsonify({"error": "Contrato no encontrado"}), 404
    if isinstance(resultado, Response):
        return jsonify({"error": "Acceso denegado"}), 403
    contrato = resultado

    files = request.files.getlist("facturas")

    if not files or all(not f.filename for f in files):
        return jsonify({"procesados": 0, "errores": [{"nombre": "", "error": "No se enviaron archivos"}]}), 400

    ok_count = 0
    exitosos = []
    errors = []
    requieren_captura_manual = []

    for f in files:
        nombre = f.filename or "<sin nombre>"
        suffix = Path(f.filename).suffix.lower() if (f.filename and Path(f.filename).suffix) else ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = Path(tmp.name)
        try:
            tipo = _detect_tipo(tmp_path)
            tipo_contrato = TIPO_ELECTRICO_BASICO if tipo == "cfe" else "gas"
            if tipo_contrato != contrato.tipo:
                errors.append({
                    "nombre": nombre,
                    "error": (
                        f"Tipo de factura ({tipo.upper()}) no coincide con el tipo del contrato "
                        f"({contrato.tipo}). Verifica que estás subiendo al contrato correcto."
                    ),
                })
                continue

            if tipo == "cfe":
                parser = get_cfe_parser("GDMTH")
                invoice = parser.parse(tmp_path)

                # Tarea 3: numero_servicio obligatorio antes de guardar
                if not invoice.numero_servicio:
                    requieren_captura_manual.append({
                        "archivo": nombre,
                        "campos_faltantes": ["numero_servicio"],
                        "campos_extraidos": _invoice_to_campos_extraidos(invoice),
                        "motivo": "numero_servicio_nulo",
                    })
                    continue

                # Tarea 2: fechas de período obligatorias antes de guardar
                campos_faltantes_periodo = [
                    campo for campo in ("periodo_inicio", "periodo_fin")
                    if getattr(invoice, campo, None) is None
                ]
                if campos_faltantes_periodo:
                    requieren_captura_manual.append({
                        "archivo": nombre,
                        "campos_faltantes": campos_faltantes_periodo,
                        "campos_extraidos": _invoice_to_campos_extraidos(invoice),
                        "motivo": "fechas_periodo_nulas",
                    })
                    continue

                identificador_factura = invoice.numero_servicio
            else:
                parser = get_gas_parser()
                invoice = parser.parse(tmp_path)
                identificador_factura = invoice.cuenta_contrato

            id_discrepante = identificador_factura != contrato.identificador_real

            if tipo == "cfe":
                factura_id, nombre_canonico = save_cfe_invoice(
                    invoice, cliente_id=cliente_id, contrato_id=contrato_id
                )
            else:
                factura_id, nombre_canonico = save_gas_invoice(
                    invoice, cliente_id=cliente_id, contrato_id=contrato_id
                )

            logger.info("Factura guardada: '%s' → id=%d (tipo=%s, contrato=%d)", nombre, factura_id, tipo, contrato_id)
            ok_count += 1
            entrada = {"nombre_original": nombre, "nombre_canonico": nombre_canonico}
            if id_discrepante:
                entrada["advertencia"] = (
                    f"Identificador de la factura ({identificador_factura}) "
                    f"no coincide con el del contrato ({contrato.identificador_real})."
                )
            exitosos.append(entrada)
        except Exception as e:
            logger.error("Error procesando '%s': %s: %s", nombre, type(e).__name__, e, exc_info=True)
            errors.append({"nombre": nombre, "error": str(e)})
        finally:
            tmp_path.unlink(missing_ok=True)

    return jsonify({
        "procesados": ok_count,
        "exitosos": exitosos,
        "errores": errors,
        "requieren_captura_manual": requieren_captura_manual,
    })


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/upload/manual",
    methods=["POST"],
)
def contrato_upload_manual(cliente_id: int, contrato_id: int):
    """Guarda una factura CFE con datos capturados manualmente por el operador.

    Recibe multipart/form-data con el PDF y todos los campos CFE. Se usa cuando
    el parser no puede extraer campos críticos (período, número de servicio).
    """
    from flask import Response, jsonify
    from models.cfe_invoice import CFEInvoice, CFEConsumoHorario, MEMComponente

    user = _get_current_user()
    if not user:
        return jsonify({"error": "No autenticado"}), 401

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        return jsonify({"error": "Contrato no encontrado"}), 404
    if isinstance(resultado, Response):
        return jsonify({"error": "Acceso denegado"}), 403

    # Campos obligatorios
    numero_servicio = (request.form.get("numero_servicio") or "").strip()
    periodo_inicio = _parse_date_field(request.form.get("periodo_inicio"))
    periodo_fin = _parse_date_field(request.form.get("periodo_fin"))

    errores_validacion = []
    if not numero_servicio:
        errores_validacion.append("numero_servicio es obligatorio.")
    if periodo_inicio is None:
        errores_validacion.append("periodo_inicio es obligatorio (formato YYYY-MM-DD).")
    if periodo_fin is None:
        errores_validacion.append("periodo_fin es obligatorio (formato YYYY-MM-DD).")
    if periodo_inicio and periodo_fin and periodo_fin <= periodo_inicio:
        errores_validacion.append("periodo_fin debe ser posterior a periodo_inicio.")
    if errores_validacion:
        return jsonify({"error": "; ".join(errores_validacion)}), 400

    # Campos opcionales con valores por defecto
    folio = (request.form.get("folio") or "").strip() or "SIN_FOLIO"
    uuid_cfdi = (request.form.get("uuid_cfdi") or "").strip() or None
    serie = (request.form.get("serie") or "").strip() or None
    rmu = (request.form.get("rmu") or "").strip() or None
    nombre_cliente = (request.form.get("nombre_cliente") or "").strip()
    rfc_cliente = (request.form.get("rfc_cliente") or "").strip()
    tarifa = (request.form.get("tarifa") or "GDMTH").strip()
    numero_medidor = (request.form.get("numero_medidor") or "").strip()
    motivo_captura_manual = (request.form.get("motivo_captura_manual") or "otro").strip()

    fecha_emision = _parse_date_field(request.form.get("fecha_emision")) or periodo_inicio
    fecha_limite_pago = _parse_date_field(request.form.get("fecha_limite_pago")) or periodo_fin

    multiplicador = int(request.form.get("multiplicador") or 1)
    carga_conectada_kw = _parse_decimal_field(request.form.get("carga_conectada_kw"))
    demanda_contratada_kw = _parse_decimal_field(request.form.get("demanda_contratada_kw"))
    kw_max = _parse_decimal_field(request.form.get("kw_max"))
    kvarh = _parse_decimal_field(request.form.get("kvarh"))
    factor_potencia_pct = _parse_decimal_field(request.form.get("factor_potencia_pct"))
    cargo_fijo_mxn = _parse_decimal_field(request.form.get("cargo_fijo_mxn"))
    energia_total_mxn = _parse_decimal_field(request.form.get("energia_total_mxn"))
    cargo_factor_potencia_mxn = _parse_decimal_field(request.form.get("cargo_factor_potencia_mxn"))
    subtotal_mxn = _parse_decimal_field(request.form.get("subtotal_mxn"))
    iva_mxn = _parse_decimal_field(request.form.get("iva_mxn"))
    facturacion_periodo_mxn = _parse_decimal_field(request.form.get("facturacion_periodo_mxn"))
    derecho_alumbrado_publico_mxn = _parse_decimal_field(request.form.get("derecho_alumbrado_publico_mxn"))
    credito_aplicado_mxn = _parse_decimal_field(request.form.get("credito_aplicado_mxn"))
    total_mxn = _parse_decimal_field(request.form.get("total_mxn"))

    # Periodos y componentes MEM desde campos JSON
    try:
        periodos_raw = _json.loads(request.form.get("periodos_json") or "[]")
        periodos = [
            CFEConsumoHorario(
                periodo=p["periodo"],
                consumo_kwh=_parse_decimal_field(p.get("consumo_kwh")),
                demanda_kw=_parse_decimal_field(p.get("demanda_kw")),
                costo_unitario_kwh=_parse_decimal_field(p.get("costo_unitario_kwh")),
            )
            for p in periodos_raw
        ]
    except Exception:
        periodos = []

    try:
        componentes_raw = _json.loads(request.form.get("componentes_mem_json") or "[]")
        componentes_mem = [
            MEMComponente(
                nombre=c["nombre"],
                cargo_fijo_mxn=_parse_decimal_field(c.get("cargo_fijo_mxn")),
                cargo_demanda_mxn=_parse_decimal_field(c.get("cargo_demanda_mxn")),
                cargo_energia_mxn=_parse_decimal_field(c.get("cargo_energia_mxn")),
                importe_mxn=_parse_decimal_field(c.get("importe_mxn")),
            )
            for c in componentes_raw
        ]
    except Exception:
        componentes_mem = []

    # Validar campos críticos de consumo: deben existir los 3 periodos con kWh > 0
    periodos_con_consumo = [p for p in periodos if p.consumo_kwh is not None and p.consumo_kwh > 0]
    if len(periodos_con_consumo) < 3:
        return jsonify({
            "error": "Faltan datos de consumo. Se requieren los kWh de los tres horarios (base, intermedio, punta). Completa la sección Consumos del formulario."
        }), 400

    # Validar componentes MEM: deben existir los 9 componentes estándar GDMTH
    if len(componentes_mem) < 9:
        return jsonify({
            "error": f"Faltan componentes MEM. Se requieren 9 (Suministro, Distribución, Transmisión, CENACE, Generación B/I/P, Capacidad, SCnMEM). Se recibieron {len(componentes_mem)}. Completa la sección MEM del formulario."
        }), 400

    # Calcular costo_unitario_kwh automáticamente (campo derivado, no viene del operador)
    try:
        from calc.cfe_util import calcular_costos_unitarios_kwh as _calc_cu
        _mem = {c.nombre: c for c in componentes_mem}
        _D0 = Decimal("0")
        _kwh_base  = next((p.consumo_kwh for p in periodos if p.periodo == "base"),       _D0)
        _kwh_inter = next((p.consumo_kwh for p in periodos if p.periodo == "intermedio"), _D0)
        _kwh_punta = next((p.consumo_kwh for p in periodos if p.periodo == "punta"),      _D0)
        _cu_base, _cu_inter, _cu_punta = _calc_cu(
            kwh_base=_kwh_base, kwh_inter=_kwh_inter, kwh_punta=_kwh_punta,
            gen_b_mxn=_mem.get("Generación B", MEMComponente("", _D0, _D0, _D0, _D0)).importe_mxn or _D0,
            gen_i_mxn=_mem.get("Generación I", MEMComponente("", _D0, _D0, _D0, _D0)).importe_mxn or _D0,
            gen_p_mxn=_mem.get("Generación P", MEMComponente("", _D0, _D0, _D0, _D0)).importe_mxn or _D0,
            transmision_mxn=_mem.get("Transmisión", MEMComponente("", _D0, _D0, _D0, _D0)).importe_mxn or _D0,
            cenace_mxn=_mem.get("CENACE",       MEMComponente("", _D0, _D0, _D0, _D0)).importe_mxn or _D0,
            scnmem_mxn=_mem.get("SCnMEM",       MEMComponente("", _D0, _D0, _D0, _D0)).importe_mxn or _D0,
        )
        from dataclasses import replace as _replace
        periodos = [
            _replace(p, costo_unitario_kwh=_cu_base)  if p.periodo == "base"       else
            _replace(p, costo_unitario_kwh=_cu_inter) if p.periodo == "intermedio" else
            _replace(p, costo_unitario_kwh=_cu_punta) if p.periodo == "punta"      else p
            for p in periodos
        ]
    except Exception as _e_cu:
        logger.warning("No se pudo calcular costo_unitario_kwh en captura manual: %s", _e_cu)

    # PDF: guardar en temp para pdf_path
    pdf_file = request.files.get("pdf")
    tmp_path = None
    try:
        if pdf_file and pdf_file.filename:
            suffix = Path(pdf_file.filename).suffix.lower() or ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                pdf_file.save(tmp.name)
                tmp_path = Path(tmp.name)
            pdf_path = str(tmp_path)
        else:
            pdf_path = "captura_manual"

        invoice = CFEInvoice(
            uuid_cfdi=uuid_cfdi,
            folio=folio,
            serie=serie,
            fecha_emision=fecha_emision,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            fecha_limite_pago=fecha_limite_pago,
            nombre_cliente=nombre_cliente,
            rfc_cliente=rfc_cliente,
            numero_servicio=numero_servicio,
            rmu=rmu,
            tarifa=tarifa,
            numero_medidor=numero_medidor,
            multiplicador=multiplicador,
            carga_conectada_kw=carga_conectada_kw,
            demanda_contratada_kw=demanda_contratada_kw,
            periodos=periodos,
            kw_max=kw_max,
            kvArh=kvarh,
            factor_potencia_pct=factor_potencia_pct,
            componentes_mem=componentes_mem,
            cargo_fijo_mxn=cargo_fijo_mxn,
            energia_total_mxn=energia_total_mxn,
            cargo_factor_potencia_mxn=cargo_factor_potencia_mxn,
            subtotal_mxn=subtotal_mxn,
            iva_mxn=iva_mxn,
            facturacion_periodo_mxn=facturacion_periodo_mxn,
            derecho_alumbrado_publico_mxn=derecho_alumbrado_publico_mxn,
            credito_aplicado_mxn=credito_aplicado_mxn,
            total_mxn=total_mxn,
            pdf_path=pdf_path,
        )

        factura_id, nombre_canonico = save_cfe_invoice(
            invoice,
            cliente_id=cliente_id,
            contrato_id=contrato_id,
            validacion_manual=True,
            validado_por=user.get("user_id"),
            motivo_captura_manual=motivo_captura_manual,
        )
        logger.info(
            "Factura CFE guardada manualmente: id=%d, nombre='%s', operador=%s",
            factura_id, nombre_canonico, user.get("email"),
        )
        return jsonify({
            "procesados": 1,
            "exitosos": [{"nombre_original": pdf_file.filename if pdf_file else "", "nombre_canonico": nombre_canonico}],
            "errores": [],
        })
    except Exception as exc:
        logger.error("Error en captura manual: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/facturas/<int:factura_id>/borrar",
    methods=["POST"],
)
def contrato_factura_borrar(cliente_id: int, contrato_id: int, factura_id: int):
    from flask import Response, jsonify

    user = _get_current_user()
    if not usuario_puede_borrar(user or {}):
        log_error("negocio", "No tienes permisos para borrar facturas.")
        flash("No tienes permisos para borrar facturas.", "danger")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        return jsonify({"error": "Cliente no encontrado"}), 404

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        return jsonify({"error": "Contrato no encontrado"}), 404
    if isinstance(resultado, Response):
        return jsonify({"error": "Acceso denegado"}), 403

    tipo = request.form.get("tipo", "").strip()
    if tipo not in ("cfe", "gas"):
        return jsonify({"error": "Tipo inválido. Debe ser 'cfe' o 'gas'."}), 400

    try:
        if tipo == "cfe":
            delete_cfe_factura(factura_id)
        else:
            delete_gas_factura(factura_id)
        logger.info("Factura borrada: id=%d, tipo=%s, contrato_id=%d", factura_id, tipo, contrato_id)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("Error borrando factura id=%d, tipo=%s: %s", factura_id, tipo, exc)
        return jsonify({"error": str(exc)}), 500


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/seleccion",
    methods=["GET"],
)
def contrato_get_seleccion(cliente_id: int, contrato_id: int):
    """Devuelve los datos del sidebar para el contrato: años con facturas y meses seleccionados."""
    from flask import Response, jsonify

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        return jsonify({"error": "Contrato no encontrado"}), 404
    if isinstance(resultado, Response):
        return jsonify({"error": "Acceso denegado"}), 403
    contrato = resultado

    try:
        data = get_sidebar_data_contrato(contrato_id, contrato_tipo=contrato.tipo)
        return jsonify({"ok": True, "anios": data})
    except Exception as exc:
        logger.error("Error cargando sidebar data contrato_id=%d: %s", contrato_id, exc)
        return jsonify({"error": str(exc)}), 500


@clientes_bp.route("/<int:cliente_id>/contratos/seleccion", methods=["GET"])
def cliente_contratos_seleccion_batch(cliente_id: int):
    """Retorna datos de sidebar para TODOS los contratos del cliente en 3 queries."""
    from flask import jsonify
    activo_id = session.get("cliente_activo_id")
    if activo_id != cliente_id:
        return jsonify({"error": "Acceso denegado"}), 403
    try:
        data = get_sidebar_data_cliente(cliente_id)
        # Convertir claves int a str para JSON
        return jsonify({"ok": True, "contratos": {str(k): v for k, v in data.items()}})
    except Exception as exc:
        logger.error("Error cargando sidebar batch cliente_id=%d: %s", cliente_id, exc)
        return jsonify({"error": "Error interno"}), 500


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/seleccion/mes",
    methods=["POST"],
)
def contrato_seleccion_mes(cliente_id: int, contrato_id: int):
    """Toggle de selección de un mes para el contrato."""
    from flask import Response, jsonify

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        return jsonify({"error": "Contrato no encontrado"}), 404
    if isinstance(resultado, Response):
        return jsonify({"error": "Acceso denegado"}), 403
    contrato = resultado

    data = request.get_json(silent=True) or {}
    anio = data.get("anio")
    mes = data.get("mes")
    seleccionado = data.get("seleccionado")
    if not isinstance(anio, int) or not isinstance(mes, int) or mes < 1 or mes > 12:
        return jsonify({"error": "anio y mes deben ser enteros válidos"}), 400
    if not isinstance(seleccionado, bool):
        return jsonify({"error": "'seleccionado' debe ser true o false"}), 400

    try:
        if seleccionado:
            meses_con_factura = get_meses_con_factura(contrato_id, anio, contrato_tipo=contrato.tipo)
            if mes not in meses_con_factura:
                return jsonify({"error": f"No existe factura para {anio}-{mes:02d} en este contrato"}), 400

            # Bloqueo de mezcla: no mezclar basico y calificado
            if contrato.tipo in TIPOS_ELECTRICOS:
                tipos_existentes = get_tipos_electricos_con_meses_seleccionados(cliente_id)
                tipo_opuesto = TIPO_ELECTRICO_CALIFICADO if contrato.tipo == TIPO_ELECTRICO_BASICO else TIPO_ELECTRICO_BASICO
                if tipo_opuesto in tipos_existentes:
                    if tipo_opuesto == TIPO_ELECTRICO_BASICO:
                        msg = ("Hay meses de facturas CFE GDMTH seleccionados. "
                               "Deselecciona primero todos los meses de los contratos CFE antes de activar suministro calificado (PPA).")
                    else:
                        msg = ("Hay meses de facturas calificadas (PPA) seleccionados. "
                               "Deselecciona primero todos los meses de los contratos PPA antes de activar suministro CFE GDMTH.")
                    return jsonify({"error": msg}), 409

            upsert_mes_seleccionado(contrato_id, anio, mes)
        else:
            delete_mes_seleccionado(contrato_id, anio, mes)
        return jsonify({"ok": True, "seleccionado": seleccionado})
    except Exception as exc:
        logger.error("Error en selección mes contrato_id=%d %d-%d: %s", contrato_id, anio, mes, exc)
        return jsonify({"error": str(exc)}), 500


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/seleccion/anio",
    methods=["POST"],
)
def contrato_seleccion_anio(cliente_id: int, contrato_id: int):
    """Selección masiva de todos los meses con factura de un año."""
    from flask import Response, jsonify

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        return jsonify({"error": "Contrato no encontrado"}), 404
    if isinstance(resultado, Response):
        return jsonify({"error": "Acceso denegado"}), 403
    contrato = resultado

    data = request.get_json(silent=True) or {}
    anio = data.get("anio")
    seleccionado = data.get("seleccionado")
    if not isinstance(anio, int):
        return jsonify({"error": "'anio' debe ser un entero"}), 400
    if not isinstance(seleccionado, bool):
        return jsonify({"error": "'seleccionado' debe ser true o false"}), 400

    try:
        if seleccionado:
            if contrato.tipo in TIPOS_ELECTRICOS:
                tipos_existentes = get_tipos_electricos_con_meses_seleccionados(cliente_id)
                tipo_opuesto = TIPO_ELECTRICO_CALIFICADO if contrato.tipo == TIPO_ELECTRICO_BASICO else TIPO_ELECTRICO_BASICO
                if tipo_opuesto in tipos_existentes:
                    if tipo_opuesto == TIPO_ELECTRICO_BASICO:
                        msg = ("Hay meses de facturas CFE GDMTH seleccionados. "
                               "Deselecciona primero todos los meses de los contratos CFE antes de activar suministro calificado (PPA).")
                    else:
                        msg = ("Hay meses de facturas calificadas (PPA) seleccionados. "
                               "Deselecciona primero todos los meses de los contratos PPA antes de activar suministro CFE GDMTH.")
                    return jsonify({"error": msg}), 409
            n = upsert_meses_seleccionados_anio(contrato_id, anio, contrato_tipo=contrato.tipo)
            return jsonify({"ok": True, "insertados": n})
        else:
            delete_meses_seleccionados_anio(contrato_id, anio)
            return jsonify({"ok": True, "eliminados": True})
    except Exception as exc:
        logger.error("Error en selección anio contrato_id=%d %d: %s", contrato_id, anio, exc)
        return jsonify({"error": str(exc)}), 500


# ── Facturas calificadas (suministro eléctrico PPA) ───────────────────────────

def _validar_y_parsear_factura_calificado(form, contrato_id, cliente_id, excluir_factura_id=None):
    """Valida y parsea los campos del formulario de factura calificada.

    Devuelve (datos_dict, error_str). Si hay error, datos_dict es None.
    Si excluir_factura_id es None, verifica duplicados; si es un int, los omite (modo editar).
    """
    from datetime import date as date_type
    from decimal import Decimal, InvalidOperation
    from storage.repository import get_ppa_bloques_mensuales

    rpu = form.get("rpu", "").strip()
    suministrador = form.get("suministrador", "").strip() or None
    serie_folio = form.get("serie_folio", "").strip() or None
    periodo_inicio_str = form.get("periodo_inicio", "").strip()
    periodo_fin_str = form.get("periodo_fin", "").strip()
    consumo_kwh_str = form.get("consumo_kwh", "").strip()
    precio_unitario_str = form.get("precio_unitario_mxn_kwh", "").strip()
    subtotal_str = form.get("subtotal_mxn", "").strip()
    iva_str = form.get("iva_mxn", "").strip()
    total_str = form.get("total_mxn", "").strip()

    error = None
    if not rpu:
        error = "El RPU es obligatorio."
    elif not periodo_inicio_str:
        error = "El periodo de inicio es obligatorio."
    elif not periodo_fin_str:
        error = "El periodo de fin es obligatorio."
    elif not consumo_kwh_str:
        error = "El consumo en kWh es obligatorio."
    elif not precio_unitario_str:
        error = "El precio unitario MXN/kWh es obligatorio."
    elif not subtotal_str:
        error = "El subtotal MXN es obligatorio."

    if error:
        return None, error

    try:
        periodo_inicio = date_type.fromisoformat(periodo_inicio_str)
        periodo_fin = date_type.fromisoformat(periodo_fin_str)
    except ValueError:
        return None, "Fechas inválidas."

    if periodo_fin <= periodo_inicio:
        return None, "El periodo de fin debe ser posterior al de inicio."

    try:
        consumo_kwh = Decimal(consumo_kwh_str)
        if consumo_kwh <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        return None, "El consumo kWh debe ser un número positivo."

    try:
        precio_unitario = Decimal(precio_unitario_str)
        if precio_unitario <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        return None, "El precio unitario debe ser un número positivo."

    try:
        subtotal_mxn = Decimal(subtotal_str)
        if subtotal_mxn <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        return None, "El subtotal debe ser un número positivo."

    iva_mxn = None
    if iva_str:
        try:
            iva_mxn = Decimal(iva_str)
        except InvalidOperation:
            return None, "El IVA debe ser un número válido."

    total_mxn = None
    if total_str:
        try:
            total_mxn = Decimal(total_str)
        except InvalidOperation:
            return None, "El total debe ser un número válido."

    if iva_mxn is not None and total_mxn is not None:
        expected_total = subtotal_mxn + iva_mxn
        if abs(expected_total - total_mxn) > Decimal("1"):
            return None, "El total no es coherente con subtotal + IVA (tolerancia ±1 peso)."

    dias_facturados = (periodo_fin - periodo_inicio).days + 1
    anio = periodo_fin.year
    mes = periodo_fin.month
    consumo_mwh = consumo_kwh / Decimal("1000")
    nombre_canonico = f"{anio:04d}-{mes:02d}"

    # Verificar duplicado solo en modo crear
    if excluir_factura_id is None:
        existing = get_facturas_calificado_por_contrato(contrato_id)
        if any(f.get("anio") == anio and f.get("mes") == mes for f in existing):
            return None, (
                f"Ya existe una factura para {nombre_canonico} en este contrato. "
                "¿Deseas editar la existente?"
            )

    # Detección de excedente
    try:
        bloques = get_ppa_bloques_mensuales(cliente_id, anio)
        bloque_mes = next((b for b in bloques if b["mes"] == mes), None)
        excedente_detectado = False
        if bloque_mes:
            bloque_mwh = Decimal(str(bloque_mes["bloque_contratado_mwh"]))
            excedente_detectado = consumo_mwh > bloque_mwh * Decimal("1.10")
    except Exception:
        excedente_detectado = False

    datos = {
        "suministrador": suministrador,
        "rpu": rpu,
        "serie_folio": serie_folio,
        "periodo_inicio": periodo_inicio.isoformat(),
        "periodo_fin": periodo_fin.isoformat(),
        "dias_facturados": dias_facturados,
        "anio": anio,
        "mes": mes,
        "nombre_canonico": nombre_canonico,
        "consumo_kwh": consumo_kwh,
        "precio_unitario_mxn_kwh": precio_unitario,
        "subtotal_mxn": subtotal_mxn,
        "iva_mxn": iva_mxn,
        "total_mxn": total_mxn,
        "excedente_detectado": excedente_detectado,
    }
    return datos, None


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/factura_calificado/crear",
    methods=["GET", "POST"],
)
def factura_calificado_crear(cliente_id: int, contrato_id: int):
    from flask import Response

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        flash("El contrato solicitado no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    if isinstance(resultado, Response):
        return resultado
    contrato = resultado

    if contrato.tipo != TIPO_ELECTRICO_CALIFICADO:
        log_error("negocio", "Este contrato no es de tipo eléctrico calificado.")
        flash("Este contrato no es de tipo eléctrico calificado.", "danger")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    if request.method == "POST":
        datos, error = _validar_y_parsear_factura_calificado(
            request.form, contrato_id, cliente_id, excluir_factura_id=None
        )
        if not error:
            try:
                factura_id = create_factura_calificado(contrato_id, cliente_id, datos)
                nombre_canonico = datos["nombre_canonico"]
                logger.info(
                    "Factura calificada creada: id=%d, contrato_id=%d", factura_id, contrato_id
                )
                flash(f"Factura {nombre_canonico} cargada correctamente.", "success")
                return redirect(url_for(
                    "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
                ))
            except Exception as exc:
                logger.error("Error creando factura calificada: %s", exc)
                error = f"Error al guardar: {exc}"

        return render_template(
            "clientes/contratos/factura_calificado_form.html",
            cliente=cliente,
            contrato=contrato,
            modo="crear",
            factura=None,
            error=error,
            form_data=request.form,
        )

    return render_template(
        "clientes/contratos/factura_calificado_form.html",
        cliente=cliente,
        contrato=contrato,
        modo="crear",
        factura=None,
        error=None,
        form_data={
            "rpu": cliente.get("ppa_rpu") or "",
            "suministrador": cliente.get("ppa_suministrador") or "",
        },
    )


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/factura_calificado/<int:factura_id>/editar",
    methods=["GET", "POST"],
)
def factura_calificado_editar(cliente_id: int, contrato_id: int, factura_id: int):
    from flask import Response

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        flash("El contrato solicitado no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    if isinstance(resultado, Response):
        return resultado
    contrato = resultado

    if contrato.tipo != TIPO_ELECTRICO_CALIFICADO:
        flash("Este contrato no es de tipo eléctrico calificado.", "warning")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    factura = get_factura_calificado(factura_id)
    if factura is None:
        flash("La factura solicitada no existe.", "warning")
        return redirect(url_for(
            "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
        ))

    if factura.contrato_id != contrato_id:
        flash("La factura no pertenece a este contrato.", "warning")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    if request.method == "POST":
        datos, error = _validar_y_parsear_factura_calificado(
            request.form, contrato_id, cliente_id, excluir_factura_id=factura_id
        )
        if not error:
            try:
                update_factura_calificado(factura_id, datos)
                nombre_canonico = datos["nombre_canonico"]
                logger.info(
                    "Factura calificada actualizada: id=%d, contrato_id=%d", factura_id, contrato_id
                )
                flash(f"Factura {nombre_canonico} actualizada.", "success")
                return redirect(url_for(
                    "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
                ))
            except Exception as exc:
                logger.error("Error actualizando factura calificada id=%d: %s", factura_id, exc)
                error = f"Error al guardar: {exc}"

        return render_template(
            "clientes/contratos/factura_calificado_form.html",
            cliente=cliente,
            contrato=contrato,
            modo="editar",
            factura=factura,
            error=error,
            form_data=request.form,
        )

    return render_template(
        "clientes/contratos/factura_calificado_form.html",
        cliente=cliente,
        contrato=contrato,
        modo="editar",
        factura=factura,
        error=None,
        form_data=vars(factura),
    )


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/factura_calificado/<int:factura_id>/borrar",
    methods=["POST"],
)
def factura_calificado_borrar(cliente_id: int, contrato_id: int, factura_id: int):
    from flask import Response

    user = _get_current_user()
    if not usuario_puede_borrar(user or {}):
        log_error("negocio", "No tienes permisos para borrar facturas.")
        flash("No tienes permisos para borrar facturas.", "danger")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        flash("El contrato solicitado no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
    if isinstance(resultado, Response):
        return resultado
    contrato = resultado

    if contrato.tipo != TIPO_ELECTRICO_CALIFICADO:
        flash("Este contrato no es de tipo eléctrico calificado.", "warning")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    factura = get_factura_calificado(factura_id)
    if factura is None:
        flash("La factura solicitada no existe.", "warning")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    if factura.contrato_id != contrato_id:
        flash("La factura no pertenece a este contrato.", "warning")
        return redirect(url_for("clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id))

    try:
        delete_factura_calificado(factura_id)
        logger.info(
            "Factura calificada borrada: id=%d, contrato_id=%d", factura_id, contrato_id
        )
        flash("Factura borrada.", "success")
    except Exception as exc:
        logger.error("Error borrando factura calificada id=%d: %s", factura_id, exc)
        log_error("negocio", f"Error al borrar: {exc}")
        flash(f"Error al borrar: {exc}", "danger")
    return redirect(url_for(
        "clientes.contrato_ficha", cliente_id=cliente_id, contrato_id=contrato_id
    ))


# ── Upload PDF factura calificada (GIN) ────────────────────────────────────────

@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/factura_calificado/upload",
    methods=["GET", "POST"],
)
def factura_calificado_upload(cliente_id: int, contrato_id: int):
    from flask import Response

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado")), 404

    resultado = _verificar_acceso_contrato(contrato_id, cliente_id)
    if resultado is None:
        flash("El contrato solicitado no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id)), 404
    if isinstance(resultado, Response):
        return resultado
    contrato = resultado

    nav_active = "contrato"
    contrato_activo_id = contrato_id

    if request.method == "GET":
        return render_template(
            "clientes/contratos/factura_calificado_upload.html",
            cliente=cliente,
            contrato=contrato,
            nav_active=nav_active,
            contrato_activo_id=contrato_activo_id,
        )

    # POST — procesar archivo
    file = request.files.get("factura")
    if not file or not file.filename:
        return render_template(
            "clientes/contratos/factura_calificado_upload.html",
            cliente=cliente,
            contrato=contrato,
            nav_active=nav_active,
            contrato_activo_id=contrato_activo_id,
            error="No se seleccionó ningún archivo.",
        )

    if not file.filename.lower().endswith(".pdf"):
        return render_template(
            "clientes/contratos/factura_calificado_upload.html",
            cliente=cliente,
            contrato=contrato,
            nav_active=nav_active,
            contrato_activo_id=contrato_activo_id,
            error="El archivo debe ser un PDF (.pdf).",
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = Path(tmp.name)

        invoice = GINParser().parse(tmp_path)

        form_data = {
            "suministrador": invoice.suministrador or "",
            "rpu": invoice.rpu or "",
            "serie_folio": invoice.serie_folio or "",
            "periodo_inicio": invoice.periodo_inicio.isoformat(),
            "periodo_fin": invoice.periodo_fin.isoformat(),
            "consumo_kwh": str(invoice.consumo_kwh),
            "precio_unitario_mxn_kwh": str(invoice.precio_unitario_mxn_kwh),
            "subtotal_mxn": str(invoice.subtotal_mxn),
            "iva_mxn": str(invoice.iva_mxn) if invoice.iva_mxn is not None else "",
            "total_mxn": str(invoice.total_mxn) if invoice.total_mxn is not None else "",
        }

        return render_template(
            "clientes/contratos/factura_calificado_preview.html",
            cliente=cliente,
            contrato=contrato,
            nav_active=nav_active,
            contrato_activo_id=contrato_activo_id,
            invoice=invoice,
            form_data=form_data,
        )

    except Exception as exc:
        logger.error(
            "Error parseando factura calificada GIN para contrato %d: %s: %s",
            contrato_id, type(exc).__name__, exc, exc_info=True,
        )
        return render_template(
            "clientes/contratos/factura_calificado_upload.html",
            cliente=cliente,
            contrato=contrato,
            nav_active=nav_active,
            contrato_activo_id=contrato_activo_id,
            error="No se pudo extraer los datos del PDF. Verifique que el archivo corresponde a una factura GIN válida.",
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


# ── Datos PPA del cliente ──────────────────────────────────────────────────────

@clientes_bp.route("/<int:cliente_id>/ppa/datos", methods=["POST"])
def cliente_ppa_datos_actualizar(cliente_id: int):
    from flask import Response
    from storage.repository import update_cliente_ppa_datos

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    def _opt_decimal(key: str):
        v = request.form.get(key, "").strip()
        if not v:
            return None
        try:
            from decimal import Decimal
            return str(Decimal(v))
        except Exception:
            return None

    datos = {
        "ppa_suministrador":                _sanitizar_texto(request.form.get("ppa_suministrador", "")),
        "ppa_rfc_suministrador":            _sanitizar_texto(request.form.get("ppa_rfc_suministrador", "")),
        "ppa_precio_fijo_usd_mwh":          _opt_decimal("ppa_precio_fijo_usd_mwh"),
        "ppa_fecha_inicio_suministro":      request.form.get("ppa_fecha_inicio_suministro", "").strip() or None,
        "ppa_energia_contratada_mwh_anual": _opt_decimal("ppa_energia_contratada_mwh_anual"),
        "ppa_capacidad_maxima_kw":          _opt_decimal("ppa_capacidad_maxima_kw"),
        "ppa_margen_reserva_cenace_pct":    _opt_decimal("ppa_margen_reserva_cenace_pct"),
        "ppa_zona_carga":                   _sanitizar_texto(request.form.get("ppa_zona_carga", "")),
        "ppa_rpu":                          _sanitizar_texto(request.form.get("ppa_rpu", "")),
        "ppa_division":                     _sanitizar_texto(request.form.get("ppa_division", "")),
        "ppa_pdf_contrato_url":             request.form.get("ppa_pdf_contrato_url", "").strip() or None,
        "ppa_notas":                        request.form.get("ppa_notas", "").strip() or None,
    }
    try:
        update_cliente_ppa_datos(cliente_id, datos)
        flash("Datos PPA actualizados.", "success")
    except Exception as exc:
        logger.error("Error actualizando PPA datos cliente_id=%d: %s", cliente_id, exc)
        log_error("negocio", f"Error al guardar datos PPA: {exc}")
        flash(f"Error al guardar datos PPA: {exc}", "danger")
    return redirect(url_for("clientes.ficha", cliente_id=cliente_id))


@clientes_bp.route("/<int:cliente_id>/ppa/bloques", methods=["POST"])
def cliente_ppa_bloques_actualizar(cliente_id: int):
    from storage.repository import upsert_ppa_bloque_mensual, delete_ppa_bloque_mensual
    from decimal import Decimal

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    anio_str = request.form.get("anio_bloques", "").strip()
    try:
        anio = int(anio_str)
    except ValueError:
        log_error("validacion", "Año inválido.")
        flash("Año inválido.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    _MESES_NOMBRES = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]

    errores = 0
    for mes in range(1, 13):
        campo = f"bloque_{mes}"
        val = request.form.get(campo, "").strip()
        if not val:
            try:
                delete_ppa_bloque_mensual(cliente_id, anio, mes)
            except Exception:
                pass
        else:
            try:
                bloque = Decimal(val)
                if bloque < 0:
                    raise ValueError("Negativo")
                upsert_ppa_bloque_mensual(cliente_id, anio, mes, bloque)
            except Exception as exc:
                logger.warning(
                    "Error en bloque mes=%d cliente_id=%d: %s", mes, cliente_id, exc
                )
                errores += 1

    if errores:
        flash(f"Se guardaron los bloques con {errores} error(es). Verifica los valores numéricos.", "warning")
    else:
        flash(f"Bloques mensuales {anio} actualizados.", "success")
    return redirect(url_for("clientes.ficha", cliente_id=cliente_id))


@clientes_bp.route("/<int:cliente_id>/gas-manual", methods=["POST"])
def cliente_gas_manual_actualizar(cliente_id: int):
    """Guarda o borra el precio de gas manual (MXN/GJ PCS) del cliente."""
    from decimal import Decimal, InvalidOperation

    user = _get_current_user()
    if not user or user.get("rol") not in ("master_admin", "admin"):
        log_error("negocio", "No tienes permiso para esta acción.")
        flash("No tienes permiso para esta acción.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    val = request.form.get("precio_gas_manual_mxn_gj_pcs", "").strip()
    if not val:
        update_precio_gas_manual(cliente_id, None)
        flash("Precio de gas manual eliminado.", "success")
    else:
        try:
            precio = Decimal(val)
            if precio <= 0:
                raise ValueError("El precio debe ser positivo.")
            update_precio_gas_manual(cliente_id, precio)
            flash(f"Precio de gas manual actualizado: {precio} MXN/GJ.", "success")
        except (InvalidOperation, ValueError) as exc:
            log_error("validacion", f"Valor inválido para precio de gas: {exc}")
            flash(f"Valor inválido para precio de gas: {exc}", "danger")
    return redirect(url_for("clientes.ficha", cliente_id=cliente_id))


# ══════════════════════════════════════════════════════════════════════════════
# Mediciones cincominutal
# ══════════════════════════════════════════════════════════════════════════════

_MESES_NOMBRES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


@clientes_bp.route("/<int:cliente_id>/mediciones/cincominutal/subir", methods=["GET", "POST"])
def medicion_subir(cliente_id: int):
    from datetime import datetime as _dt
    user = _get_current_user()
    if not user or user.get("rol") not in ("master_admin", "admin"):
        flash("No tienes permiso para subir mediciones.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    anio_actual = _dt.now().year

    if request.method == "GET":
        return render_template(
            "clientes/mediciones/cincominutal_subir.html",
            cliente=cliente,
            anio_actual=anio_actual,
        )

    # POST — procesar upload
    file = request.files.get("archivo")
    if not file or not file.filename:
        flash("Debes seleccionar un archivo.", "danger")
        return render_template(
            "clientes/mediciones/cincominutal_subir.html",
            cliente=cliente,
            anio_actual=anio_actual,
        )

    if not file.filename.lower().endswith(".xlsx"):
        flash("El archivo debe ser un Excel (.xlsx).", "danger")
        return render_template(
            "clientes/mediciones/cincominutal_subir.html",
            cliente=cliente,
            anio_actual=anio_actual,
        )

    try:
        anio = int(request.form.get("anio", 0))
        mes  = int(request.form.get("mes", 0))
    except (ValueError, TypeError):
        flash("Año o mes inválido.", "danger")
        return render_template(
            "clientes/mediciones/cincominutal_subir.html",
            cliente=cliente,
            anio_actual=anio_actual,
        )

    if not (1 <= mes <= 12) or anio < 2000:
        flash("Año o mes fuera de rango.", "danger")
        return render_template(
            "clientes/mediciones/cincominutal_subir.html",
            cliente=cliente,
            anio_actual=anio_actual,
        )

    tmp_path = None
    medicion_id = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = Path(tmp.name)

        from web.mediciones_parser import parse_cincominutal
        datos = parse_cincominutal(tmp_path)

        medicion_id = create_medicion(
            cliente_id=cliente_id,
            anio=anio,
            mes=mes,
            nombre=file.filename,
            uploaded_by=user.get("email", ""),
        )

        save_medicion_datos(medicion_id, datos)

        flash(
            f"Medición de {_MESES_NOMBRES[mes]} {anio} cargada correctamente ({len(datos):,} registros).",
            "success",
        )
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    except ValueError as exc:
        if medicion_id is not None:
            try:
                delete_medicion(medicion_id)
            except Exception:
                pass
        flash(str(exc), "danger")
        return render_template(
            "clientes/mediciones/cincominutal_subir.html",
            cliente=cliente,
            anio_actual=anio_actual,
        )
    except Exception as exc:
        if medicion_id is not None:
            try:
                delete_medicion(medicion_id)
            except Exception:
                pass
        log_error("negocio", f"Error al subir medición cincominutal: {exc}")
        flash("Error inesperado al procesar el archivo.", "danger")
        return render_template(
            "clientes/mediciones/cincominutal_subir.html",
            cliente=cliente,
            anio_actual=anio_actual,
        )
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


@clientes_bp.route("/<int:cliente_id>/mediciones/<int:medicion_id>/borrar", methods=["POST"])
def medicion_borrar(cliente_id: int, medicion_id: int):
    user = _get_current_user()
    if not user or user.get("rol") not in ("master_admin", "admin"):
        flash("No tienes permiso para borrar mediciones.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    medicion = get_medicion(medicion_id)
    if not medicion or medicion["cliente_id"] != cliente_id:
        flash("Medición no encontrada.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    delete_medicion(medicion_id)
    if session.get("medicion_activa_id") == medicion_id:
        session.pop("medicion_activa_id", None)

    mes_nombre = _MESES_NOMBRES[medicion["mes"]] if 1 <= medicion["mes"] <= 12 else str(medicion["mes"])
    flash(f"Medición de {mes_nombre} {medicion['anio']} eliminada.", "success")
    return redirect(url_for("clientes.ficha", cliente_id=cliente_id))


@clientes_bp.route("/<int:cliente_id>/mediciones/<int:medicion_id>/datos")
def medicion_datos(cliente_id: int, medicion_id: int):
    from flask import jsonify
    user = _get_current_user()
    if not user:
        return jsonify({"error": "No autenticado"}), 401

    medicion = get_medicion(medicion_id)
    if not medicion or medicion["cliente_id"] != cliente_id:
        return jsonify({"error": "Medición no encontrada"}), 404

    puntos = get_medicion_datos(medicion_id)
    ts_list = []
    for p in puntos:
        raw = p.get("ts") or ""
        # Normalizar a "YYYY-MM-DDTHH:MM" — Supabase puede devolver " " o "T"
        ts_list.append(raw[:16].replace(" ", "T"))
    kw_list = [float(p["potencia_kw"]) for p in puntos]
    return jsonify({"ts": ts_list, "potencia_kw": kw_list})


@clientes_bp.route("/<int:cliente_id>/mediciones/seleccionar", methods=["POST"])
def medicion_seleccionar(cliente_id: int):
    from flask import jsonify
    user = _get_current_user()
    if not user:
        return jsonify({"error": "No autenticado"}), 401

    data = request.get_json() or {}
    medicion_id = data.get("medicion_id")
    if medicion_id is None:
        return jsonify({"error": "medicion_id requerido"}), 400

    medicion = get_medicion(int(medicion_id))
    if not medicion or medicion["cliente_id"] != cliente_id:
        return jsonify({"error": "Medición no encontrada"}), 404

    session["medicion_activa_id"] = int(medicion_id)
    return jsonify({"ok": True})


@clientes_bp.route("/<int:cliente_id>/mediciones/<int:medicion_id>", methods=["PATCH", "DELETE"])
def medicion_api(cliente_id: int, medicion_id: int):
    """PATCH: actualiza campos editables. DELETE: borra la medición. Devuelve JSON."""
    from flask import jsonify
    user = _get_current_user()
    if not user or user.get("rol") not in ("master_admin", "admin"):
        return jsonify({"error": "No autorizado"}), 403

    medicion = get_medicion(medicion_id)
    if not medicion or medicion["cliente_id"] != cliente_id:
        return jsonify({"error": "No encontrada"}), 404

    if request.method == "DELETE":
        delete_medicion(medicion_id)
        return jsonify({"ok": True})

    # PATCH
    data = request.get_json(silent=True) or {}
    campos: dict = {}

    if "nombre" in data:
        v = str(data["nombre"]).strip() if data["nombre"] is not None else ""
        campos["nombre"] = v or None

    if "anio" in data:
        try:
            anio = int(data["anio"])
            if not (2000 <= anio <= 2100):
                return jsonify({"error": "Año fuera de rango (2000-2100)"}), 422
            campos["anio"] = anio
        except (ValueError, TypeError):
            return jsonify({"error": "Año inválido"}), 422

    if "mes" in data:
        try:
            mes = int(data["mes"])
            if not (1 <= mes <= 12):
                return jsonify({"error": "Mes fuera de rango (1-12)"}), 422
            campos["mes"] = mes
        except (ValueError, TypeError):
            return jsonify({"error": "Mes inválido"}), 422

    if not campos:
        return jsonify({"error": "Sin campos válidos a actualizar"}), 422

    updated = update_medicion(medicion_id, campos)
    if updated is None:
        return jsonify({"error": "No se pudo actualizar"}), 500
    return jsonify({"ok": True, "medicion": updated})


@clientes_bp.route("/<int:cliente_id>/mediciones/borrar-lote", methods=["POST"])
def medicion_borrar_lote(cliente_id: int):
    """Borra varias mediciones por lista de ids. Devuelve JSON."""
    from flask import jsonify
    user = _get_current_user()
    if not user or user.get("rol") not in ("master_admin", "admin"):
        return jsonify({"error": "No autorizado"}), 403

    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"error": "Lista de ids vacía"}), 422

    eliminadas = 0
    errores = 0
    for mid in ids:
        try:
            m = get_medicion(int(mid))
            if m and m["cliente_id"] == cliente_id:
                delete_medicion(int(mid))
                eliminadas += 1
            else:
                errores += 1
        except Exception:
            errores += 1
    return jsonify({"ok": True, "eliminadas": eliminadas, "errores": errores})


# ── Modelado CHP ─────────────────────────────────────────────────────────────

@clientes_bp.route("/<int:cliente_id>/dashboard/modelado-chp/data")
def modelado_chp_data(cliente_id: int):
    """Calcula o sirve desde cache los KPIs del modelado CHP para una medición."""
    import math as _math
    from flask import jsonify
    from calc.modelado_chp import modelar_chp

    user = _get_current_user()
    if not user:
        return jsonify({"error": "No autenticado"}), 401

    medicion_id = request.args.get("medicion_id", type=int)
    if not medicion_id:
        return jsonify({"error": "medicion_id es obligatorio"}), 422

    # Verificar que la medición pertenece al cliente
    medicion = get_medicion(medicion_id)
    if not medicion or medicion.get("cliente_id") != cliente_id:
        return jsonify({"error": "Medición no encontrada"}), 404

    # Parámetros CHP del cliente (defaults guardados)
    import json as _json
    chp_params = get_cliente_chp_params(cliente_id)

    margen_kw             = request.args.get("margen_kw",             type=float, default=chp_params["margen_kw"])
    rendimiento_electrico = request.args.get("rendimiento_electrico", type=float, default=0.40)
    costo_om_kwh          = request.args.get("costo_om_kwh",          type=float, default=0.30)
    autoconsumo_pct       = request.args.get("autoconsumo_pct",       type=float, default=0.03)

    # consumo_anual_kwh: suma de kWh de las últimas 12 facturas eléctricas
    from decimal import Decimal as _Decimal
    cfe_inv = get_ultimas_cfe_invoices(cliente_id, n=12)
    if cfe_inv:
        consumo_anual_kwh = float(
            sum(sum(p.consumo_kwh for p in inv.periodos) for inv in cfe_inv)
        )
    else:
        ppa_inv = get_ultimas_ppa_invoices(cliente_id, n=12)
        consumo_anual_kwh = float(sum(inv.consumo_kwh for inv in ppa_inv))

    # capacidad sugerida desde facturas (usada cuando motores_config no tiene kW válidos)
    from calc.cogen import _capacidad_nominal_kw as _cap_fn
    cap_dec = _cap_fn(cfe_inv) if cfe_inv else None
    if cap_dec:
        _cap_sugerida = float(cap_dec)
    else:
        _peak = max((float(d["potencia_kw"]) for d in get_medicion_datos(medicion_id) or []), default=0.0)
        _cap_sugerida = float(_math.ceil(_peak)) if _peak > 0 else 100.0

    # motores_config: del QS, o del cliente, o default con cap sugerida
    _motores_str = request.args.get("motores_config", "")
    if _motores_str:
        try:
            motores_config = _json.loads(_motores_str)
        except Exception:
            return jsonify({"error": "motores_config JSON inválido"}), 422
    else:
        motores_config = chp_params.get("motores_config") or []

    # Si no hay capacidades válidas, usar sugerida en motor único
    if not any(float(m.get("capacidad_kw", 0)) > 0 for m in motores_config):
        motores_config = [{"id": 1, "nombre": "Motor 1", "capacidad_kw": _cap_sugerida}]

    capacidad_nominal_kw = sum(float(m.get("capacidad_kw", 0)) for m in motores_config)
    num_motores = len(motores_config)

    # precio_gas_gj para cogen_defaults — promedio ponderado desde facturas, fallback manual
    gas_inv_def = get_ultimas_gas_invoices(cliente_id, n=12)
    _total_gj_def = sum(float(inv.consumo_total_gj) for inv in gas_inv_def if float(inv.consumo_total_gj) > 0)
    if _total_gj_def > 0:
        _precio_gas_gj = sum(
            float(inv.costo_unitario_total_gj) * float(inv.consumo_total_gj)
            for inv in gas_inv_def if float(inv.consumo_total_gj) > 0
        ) / _total_gj_def
    else:
        _cliente_rec = get_cliente_con_conteos(cliente_id)
        _precio_manual_str = _cliente_rec.get("precio_gas_manual_mxn_gj_pcs") if _cliente_rec else None
        _precio_gas_gj = float(_precio_manual_str) if _precio_manual_str else 0.0

    # Buscar en cache
    from storage.repository import _supabase as _sb
    cached = get_modelado_chp(
        medicion_id, motores_config, margen_kw,
        rendimiento_electrico, costo_om_kwh, autoconsumo_pct,
    )

    if cached:
        modelado_id = cached["id"]
        curva_check = _sb.table("modelado_chp_curva") \
            .select("id").eq("modelado_id", modelado_id).limit(1).execute()
        tiene_curva = bool(curva_check.data)
        if not tiene_curva:
            datos = get_medicion_datos(medicion_id)
            if not datos:
                return jsonify({"error": "Sin datos en la medición"}), 422
            resultado = modelar_chp(
                datos=datos,
                motores_config=motores_config,
                margen_kw=margen_kw,
                rendimiento_electrico=rendimiento_electrico,
                costo_om_kwh=costo_om_kwh,
                autoconsumo_pct=autoconsumo_pct,
                consumo_anual_kwh=consumo_anual_kwh,
            )
            _sb.table("modelado_chp_curva").delete().eq("modelado_id", modelado_id).execute()
            save_modelado_chp_curva(modelado_id, resultado["curva"])
        kpis = {k: float(cached.get(k) or 0) for k in [
            "gen_neta_anual_kwh", "gen_bruta_anual_kwh",
            "cobertura_pct", "consumo_gas_anual_gj",
            "costo_om_anual_mxn", "horas_anuales_motor",
            "capacidad_promedio_kw",
        ]}
        kpis["consumo_cliente_mes_kwh"] = 0.0
    else:
        datos = get_medicion_datos(medicion_id)
        if not datos:
            return jsonify({"error": "Sin datos en la medición"}), 422

        resultado = modelar_chp(
            datos=datos,
            motores_config=motores_config,
            margen_kw=margen_kw,
            rendimiento_electrico=rendimiento_electrico,
            costo_om_kwh=costo_om_kwh,
            autoconsumo_pct=autoconsumo_pct,
            consumo_anual_kwh=consumo_anual_kwh,
        )
        kpis = resultado["kpis"]
        params_save = {
            "motores_config":        motores_config,
            "margen_kw":             margen_kw,
            "rendimiento_electrico": rendimiento_electrico,
            "costo_om_kwh":          costo_om_kwh,
            "autoconsumo_pct":       autoconsumo_pct,
        }
        modelado_id = save_modelado_chp(cliente_id, medicion_id, params_save, kpis)
        _sb.table("modelado_chp_curva").delete().eq("modelado_id", modelado_id).execute()
        save_modelado_chp_curva(modelado_id, resultado["curva"])

    return jsonify({
        "ok": True,
        "modelado_id": modelado_id,
        "medicion_id": medicion_id,
        "mes": medicion.get("mes"),
        "anio": medicion.get("anio"),
        "params": {
            "motores_config":        motores_config,
            "capacidad_nominal_kw":  capacidad_nominal_kw,
            "num_motores":           num_motores,
            "margen_kw":             margen_kw,
            "rendimiento_electrico": rendimiento_electrico,
            "costo_om_kwh":          costo_om_kwh,
            "autoconsumo_pct":       autoconsumo_pct,
            "consumo_anual_kwh":     consumo_anual_kwh,
        },
        "kpis": kpis,
        "cogen_defaults": {
            "rendimiento_termico": 0.25,
            "eficiencia_caldera":  0.85,
            "precio_gas_gj":       round(_precio_gas_gj, 2),
        },
    })


@clientes_bp.route("/<int:cliente_id>/dashboard/modelado-chp/curva/<int:modelado_id>")
def modelado_chp_curva(cliente_id: int, modelado_id: int):
    """Retorna la curva modelada (ts, demanda_kw, gen_neta_kw) de un modelado."""
    from flask import jsonify

    user = _get_current_user()
    if not user:
        return jsonify({"error": "No autenticado"}), 401

    # Obtener motores_config del modelado para etiquetas y construcción de arrays por motor
    modelado_hdr = get_modelado_chp_by_id(modelado_id)
    motores_cfg  = (modelado_hdr.get("motores_config") or []) if modelado_hdr else []

    puntos = get_modelado_chp_curva(modelado_id)

    # Construir arrays por motor a partir de gen_por_motor JSONB
    motores_out = []
    for m in motores_cfg:
        mid_str = str(m["id"])
        gen_kw = [
            float((p.get("gen_por_motor") or {}).get(mid_str, 0.0))
            for p in puntos
        ]
        motores_out.append({
            "id":     m["id"],
            "nombre": m.get("nombre") or f"Motor {m['id']}",
            "gen_kw": gen_kw,
        })

    return jsonify({
        "ts":          [p["ts"] for p in puntos],
        "demanda_kw":  [float(p["demanda_kw"]) for p in puntos],
        "gen_neta_kw": [float(p["gen_neta_kw"]) for p in puntos],
        "motores":     motores_out,
    })


@clientes_bp.route("/<int:cliente_id>/dashboard/modelado-chp/params", methods=["POST"])
def modelado_chp_params(cliente_id: int):
    """Guarda los parámetros de cabecera de la sesión del Modelado CHP."""
    from flask import jsonify

    actor = _get_current_user()
    if not actor:
        return jsonify({"ok": False}), 401

    data = request.get_json(silent=True) or {}

    params = {
        "motores":               data.get("motores", []),
        "margen_kw":             data.get("margen_kw", 100),
        "rendimiento_electrico": data.get("rendimiento_electrico", 40),
        "rendimiento_termico":   data.get("rendimiento_termico", 45),
        "precio_gas_gj":         data.get("precio_gas_gj", 0),
        "costo_om_kwh":          data.get("costo_om_kwh", 0.30),
        "precio_motor_usd_kw":   data.get("precio_motor_usd_kw", 1400),
        "autoconsumo_pct":       data.get("autoconsumo_pct", 3),
        "deduccion_fiscal":      data.get("deduccion_fiscal", False),
        "anios_deduccion":       data.get("anios_deduccion", 1),
    }
    save_chp_session_params(cliente_id, params)
    return jsonify({"ok": True})


@clientes_bp.route("/<int:cliente_id>/dashboard/modelado-chp/cogen-data")
def modelado_chp_cogen_data(cliente_id: int):
    """KPIs de cogeneración calculados desde un modelado CHP previo.

    Usa la cobertura derivada de la simulación CHP (kpis_modelado["cobertura_pct"])
    como entrada al motor calcular_cogen(), con las facturas CFE y gas reales.
    Retorna una estructura JSON compatible con /dashboard/cogeneracion/data.
    """
    from flask import jsonify
    from decimal import Decimal as _D
    from calc.modelado_chp import calcular_cogen_desde_modelado
    from calc.cogen import calcular_flujo_acumulado, calcular_payback_decimal
    from storage.repository import list_configuracion

    user = _get_current_user()
    if not user:
        return jsonify({"error": "No autenticado"}), 401

    modelado_id = request.args.get("modelado_id", type=int)
    if not modelado_id:
        return jsonify({"error": "modelado_id es obligatorio"}), 422

    # 1. Obtener cabecera del modelado
    modelado = get_modelado_chp_by_id(modelado_id)
    if not modelado or modelado.get("cliente_id") != cliente_id:
        return jsonify({"error": "Modelado no encontrado"}), 404

    # 2. Parámetros técnicos — del QS o defaults
    rendimiento_termico = request.args.get("rendimiento_termico", type=float, default=0.25)
    eficiencia_caldera  = request.args.get("eficiencia_caldera",  type=float, default=0.85)
    inversion_usd_qs    = request.args.get("inversion_usd",       type=float, default=None)
    deduccion_fiscal    = request.args.get("deduccion_fiscal", "0") == "1"
    anios_deduccion     = max(1, min(5, request.args.get("anios_deduccion", type=int, default=1)))

    # Del modelado: rendimiento_electrico ya está guardado en la cabecera
    rendimiento_electrico = float(modelado.get("rendimiento_electrico") or 0.40)

    # KPIs del modelado (campos guardados en la cabecera)
    kpis_modelado = {
        "cobertura_pct":         float(modelado.get("cobertura_pct") or 0),
        "gen_neta_anual_kwh":    float(modelado.get("gen_neta_anual_kwh") or 0),
        "gen_bruta_anual_kwh":   float(modelado.get("gen_bruta_anual_kwh") or 0),
        "horas_anuales_motor":   float(modelado.get("horas_anuales_motor") or 0),
        "capacidad_promedio_kw": float(modelado.get("capacidad_promedio_kw") or 0),
    }

    # 3. Cargar facturas CFE y gas (últimas 12, igual que cogeneracion/data)
    cfe_invoices = sorted(get_ultimas_cfe_invoices(cliente_id, n=12), key=lambda x: x.periodo_inicio)
    gas_invoices = sorted(get_ultimas_gas_invoices(cliente_id, n=12), key=lambda x: x.periodo_inicio)

    if not cfe_invoices:
        return jsonify({"error": "Sin facturas CFE disponibles para calcular cogeneración"}), 422

    # 4. Config global
    cfg = {row["clave"]: row["valor"] for row in list_configuracion()}
    tc_str     = cfg.get("tipo_cambio_mxn_usd")
    fe_elec_str = cfg.get("factor_emision_electricidad_kg_co2_kwh")
    fe_gas_str  = cfg.get("factor_emision_gas_kg_co2_gj")
    tipo_cambio      = _D(tc_str)      if tc_str      else _D("17.50")
    factor_emision_elec = _D(fe_elec_str) if fe_elec_str else None
    factor_emision_gas  = _D(fe_gas_str)  if fe_gas_str  else None

    # 5. Calcular cogeneración con cobertura del modelado
    try:
        r = calcular_cogen_desde_modelado(
            kpis_modelado=kpis_modelado,
            rendimiento_electrico=rendimiento_electrico,
            rendimiento_termico=rendimiento_termico,
            eficiencia_caldera=eficiencia_caldera,
            cfe_invoices=cfe_invoices,
            gas_invoices=gas_invoices,
            tipo_cambio=tipo_cambio,
            factor_emision_elec=factor_emision_elec,
            factor_emision_gas=factor_emision_gas,
            inversion_usd_override=inversion_usd_qs,
            deduccion_fiscal=deduccion_fiscal,
            anios_deduccion=anios_deduccion,
        )
    except Exception as _e:
        logger.exception("Error en modelado-chp/cogen-data: %s", _e)
        return jsonify({"error": "error_calculo", "mensaje": str(_e)}), 500

    # 6. CELs
    cels_resultado = None
    try:
        from calc.cels import calcular_cels as _calcular_cels
        from storage.repository import get_cliente_con_conteos as _gcc
        cliente = _gcc(cliente_id)
        calor_recuperado_anual = sum(m.calor_recuperado_gj for m in r.meses)
        cels_resultado = _calcular_cels(
            kwh_cubiertos_anual=r.kwh_cubiertos_anual,
            gj_gas_cogen_pci_anual=r.gj_gas_cogen_pci_anual,
            calor_recuperado_gj_anual=calor_recuperado_anual,
            capacidad_nominal_kw=r.capacidad_nominal_kw,
            medio_termico=cliente.get("medio_termico") if cliente else None,
            nivel_tension_kv=cliente.get("nivel_tension_kv") if cliente else None,
            altitud_msnm=cliente.get("altitud_msnm") if cliente else None,
            tipo_motor=cliente.get("tipo_motor") if cliente else None,
            medio_termico_vapor_pct=cliente.get("medio_termico_vapor_pct") if cliente else None,
        )
    except Exception as _e_cels:
        logger.error("Error calculando CELs en cogen-data: %s", _e_cels)

    # 6b. Energía limpia — se calcula aquí donde tenemos cels_resultado y r
    if cels_resultado is not None and cels_resultado.cels_mwh_anual is not None and r.energia_limpia_pct is None:
        kwh_total = float(r.kwh_total_anual) if r.kwh_total_anual else 0.0
        if kwh_total <= 0:
            # Fallback: consumo del modelado cuando las facturas no tienen kWh total
            kwh_total = float(kpis_modelado.get("consumo_cliente_mes_kwh", 0)) * 12
        if kwh_total > 0:
            from decimal import ROUND_HALF_UP as _RHU
            r.energia_limpia_pct = (
                _D(str(cels_resultado.cels_mwh_anual)) * _D("1000")
                / _D(str(kwh_total)) * _D("100")
            ).quantize(_D("0.01"), rounding=_RHU)

    # 7. Flujo 15 años y payback
    if r.inversion_mxn is not None and r.inversion_mxn > 0:
        payback_inicial   = calcular_payback_decimal(r.inversion_mxn, r.ebitda_anual_mxn, r.ebitda_anual_mxn)
        flujo_acum_15     = [float(v) for v in calcular_flujo_acumulado(r.inversion_mxn, r.ebitda_anual_mxn)]
        flujo_anual_15    = [-float(r.inversion_mxn)] + [float(r.ebitda_anual_mxn)] * 15
        if r.flujo_anio_1_con_beneficio_mxn is not None:
            flujo_anual_15_fiscal = (
                [-float(r.inversion_mxn), float(r.flujo_anio_1_con_beneficio_mxn)]
                + [float(r.ebitda_anual_mxn)] * 14
            )
            _acum = 0.0
            flujo_acum_15_fiscal = []
            for v in flujo_anual_15_fiscal:
                _acum += v
                flujo_acum_15_fiscal.append(_acum)
            payback_con_beneficio = calcular_payback_decimal(
                r.inversion_mxn, r.flujo_anio_1_con_beneficio_mxn, r.ebitda_anual_mxn
            )
            payback_con_beneficio = float(payback_con_beneficio) if payback_con_beneficio is not None else None
        else:
            flujo_anual_15_fiscal = flujo_anual_15
            flujo_acum_15_fiscal  = flujo_acum_15
            payback_con_beneficio = float(payback_inicial) if payback_inicial is not None else None
        payback_inicial = float(payback_inicial) if payback_inicial is not None else None
    else:
        payback_inicial = payback_con_beneficio = None
        flujo_acum_15 = flujo_anual_15 = flujo_anual_15_fiscal = flujo_acum_15_fiscal = []

    # 8. CO2
    co2 = None
    if r.co2_reduccion_kg_anual is not None:
        reduccion_t = float(r.co2_reduccion_kg_anual) / 1000
        co2 = {
            "actual_total_t": float(r.co2_actual_total_kg_anual) / 1000 if r.co2_actual_total_kg_anual else None,
            "reduccion_t": reduccion_t,
            "reduccion_pct": float(r.co2_reduccion_porcentaje) if r.co2_reduccion_porcentaje else 0.0,
            "arboles": int(reduccion_t * 50),
            "factor_emision_elec": float(factor_emision_elec) if factor_emision_elec else None,
            "factor_emision_gas":  float(factor_emision_gas)  if factor_emision_gas  else None,
        }

    # 9. CELs dict
    def _cels_dict(cels):
        if cels is None:
            return None
        def _f(v):
            return float(v) if v is not None else None
        return {
            "es_eficiente": cels.es_eficiente,
            "cels_mwh_anual": _f(cels.cels_mwh_anual),
            "capacidad_kw": _f(cels.capacidad_kw),
            "capacidad_es_estimada": cels.capacidad_es_estimada,
            "RefE": _f(cels.RefE),
            "RefH": _f(cels.RefH),
            "fp": _f(cels.fp),
            "EE": _f(cels.EE),
            "EP": _f(cels.EP),
            "AEP": _f(cels.AEP),
            "APEP": _f(cels.APEP),
            "AREL": _f(cels.AREL),
            "ELC": _f(cels.ELC),
            "porcentaje_ELC": _f(cels.porcentaje_ELC),
        }

    chart_labels          = [m.periodo_inicio.strftime("%b %Y") for m in r.meses]
    chart_ebitda          = [float(m.ebitda_mes_mxn) for m in r.meses]
    chart_ahorro_elec     = [float(m.ahorro_electricidad_mxn) for m in r.meses]
    chart_ahorro_caldera  = [float(m.ahorro_caldera_mxn) for m in r.meses]
    chart_costo_gas       = [float(m.costo_gas_cogen_mxn) for m in r.meses]
    chart_om              = [float(m.gasto_om_mes_mxn) for m in r.meses]

    tabla_mensual = [
        {
            "periodo":                     m.periodo_inicio.strftime("%b %Y"),
            "kwh_total":                   float(m.kwh_total),
            "kwh_cubiertos":               float(m.kwh_cubiertos),
            "ahorro_energia_mes_mxn":      float(m.ahorro_energia_mes_mxn),
            "ahorro_capacidad_mes_mxn":    float(m.ahorro_capacidad_mes_mxn),
            "ahorro_distribucion_mes_mxn": float(m.ahorro_distribucion_mes_mxn),
            "ahorro_otros_servicios_mes_mxn": float(m.ahorro_otros_servicios_mes_mxn),
            "gj_gas_cogen":                float(m.gj_gas_cogen),
            "costo_gas_cogen_mxn":         float(m.costo_gas_cogen_mxn),
            "ahorro_electricidad_mxn":     float(m.ahorro_electricidad_mxn),
            "calor_recuperado_gj":         float(m.calor_recuperado_gj),
            "ahorro_caldera_mxn":          float(m.ahorro_caldera_mxn),
            "gasto_om_mes_mxn":            float(m.gasto_om_mes_mxn),
            "ebitda_mes_mxn":              float(m.ebitda_mes_mxn),
        }
        for m in r.meses
    ]

    return jsonify({
        "ok": True,
        "modelado_id": modelado_id,
        "kpis_modelado": kpis_modelado,
        "kpis": {
            "cobertura_pct":                  float(kpis_modelado["cobertura_pct"]),
            "ahorro_electricidad_anual":       float(r.ahorro_electricidad_anual_mxn),
            "ahorro_caldera_anual":            float(r.ahorro_caldera_anual_mxn),
            "costo_gas_cogen_anual":           float(r.costo_gas_cogen_anual_mxn),
            "gasto_om_anual":                  float(r.gasto_om_anual_mxn),
            "ebitda_anual":                    float(r.ebitda_anual_mxn),
            "kwh_total_anual":                 float(r.kwh_total_anual),
            "kwh_cubiertos_anual":             float(r.kwh_cubiertos_anual),
            "gj_gas_cogen_anual":              float(r.gj_gas_cogen_anual),
            "capacidad_nominal_kw":            sum(float(m.get("capacidad_kw", 0)) for m in (modelado.get("motores_config") or [])) or (float(r.capacidad_nominal_kw) if r.capacidad_nominal_kw else None),
            "inversion_usd":                   float(r.inversion_usd) if r.inversion_usd else None,
            "inversion_mxn":                   float(r.inversion_mxn) if r.inversion_mxn else None,
            "tipo_cambio":                     float(r.tipo_cambio_mxn_usd) if r.tipo_cambio_mxn_usd else None,
            "ahorro_energia_anual":            float(r.ahorro_energia_anual_mxn),
            "ahorro_capacidad_anual":          float(r.ahorro_capacidad_anual_mxn),
            "ahorro_distribucion_anual":       float(r.ahorro_distribucion_anual_mxn),
            "ahorro_otros_servicios_anual":    float(r.ahorro_otros_servicios_anual_mxn),
            "beneficio_fiscal_anio_1_mxn":     float(r.beneficio_fiscal_anio_1_mxn) if r.beneficio_fiscal_anio_1_mxn else None,
            "gen_neta_anual_kwh":              kpis_modelado["gen_neta_anual_kwh"],
            "gen_bruta_anual_kwh":             kpis_modelado["gen_bruta_anual_kwh"],
            "horas_anuales_motor":             kpis_modelado["horas_anuales_motor"],
            "energia_limpia_pct":              float(r.energia_limpia_pct) if r.energia_limpia_pct is not None else None,
        },
        "params": {
            "cobertura_electrica":    float(kpis_modelado["cobertura_pct"]),
            "rendimiento_electrico":  rendimiento_electrico,
            "rendimiento_termico":    rendimiento_termico,
            "eficiencia_caldera":     eficiencia_caldera,
        },
        "co2": co2,
        "cels": _cels_dict(cels_resultado),
        "chart_labels": chart_labels,
        "chart_ebitda": chart_ebitda,
        "chart_ahorro_elec": chart_ahorro_elec,
        "chart_ahorro_caldera": chart_ahorro_caldera,
        "chart_costo_gas": chart_costo_gas,
        "chart_om": chart_om,
        "tabla_mensual": tabla_mensual,
        "payback_inicial": payback_inicial,
        "payback_con_beneficio": payback_con_beneficio,
        "flujo_acum_15": flujo_acum_15,
        "flujo_anual_15": flujo_anual_15,
        "flujo_anual_15_fiscal": flujo_anual_15_fiscal,
        "flujo_acum_15_fiscal": flujo_acum_15_fiscal,
    })


@clientes_bp.route("/<int:cliente_id>/dashboard/modelado-chp/excel")
def modelado_chp_excel(cliente_id: int):
    """Genera y descarga el Excel maestro con fórmulas nativas del Modelado CHP.

    Reutiliza exactamente la misma lógica de cálculo de /cogen-data.
    Solo accesible para admin y master_admin.
    """
    from flask import make_response
    from io import BytesIO
    from decimal import Decimal as _D
    from calc.modelado_chp import calcular_cogen_desde_modelado
    from calc.cogen import calcular_payback_decimal
    from storage.repository import list_configuracion, get_modelado_chp_curva
    from reports.excel_modelado_chp import generar_excel_modelado_chp

    user = _get_current_user()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    if user.get("rol") not in ("master_admin", "admin"):
        return jsonify({"error": "No autorizado"}), 403

    modelado_id = request.args.get("modelado_id", type=int)
    if not modelado_id:
        return jsonify({"error": "modelado_id es obligatorio"}), 422

    modelado = get_modelado_chp_by_id(modelado_id)
    if not modelado or modelado.get("cliente_id") != cliente_id:
        return jsonify({"error": "Modelado no encontrado"}), 404

    # Parámetros técnicos (mismos defaults que cogen-data)
    rendimiento_termico   = request.args.get("rendimiento_termico",  type=float, default=0.25)
    eficiencia_caldera    = request.args.get("eficiencia_caldera",   type=float, default=0.85)
    inversion_usd_qs      = request.args.get("inversion_usd",        type=float, default=None)
    deduccion_fiscal      = request.args.get("deduccion_fiscal", "0") == "1"
    anios_deduccion       = max(1, min(5, request.args.get("anios_deduccion", type=int, default=1)))
    rendimiento_electrico = float(modelado.get("rendimiento_electrico") or 0.40)

    kpis_modelado = {
        "cobertura_pct":         float(modelado.get("cobertura_pct") or 0),
        "gen_neta_anual_kwh":    float(modelado.get("gen_neta_anual_kwh") or 0),
        "gen_bruta_anual_kwh":   float(modelado.get("gen_bruta_anual_kwh") or 0),
        "horas_anuales_motor":   float(modelado.get("horas_anuales_motor") or 0),
        "capacidad_promedio_kw": float(modelado.get("capacidad_promedio_kw") or 0),
    }

    cfe_invoices = sorted(get_ultimas_cfe_invoices(cliente_id, n=12), key=lambda x: x.periodo_inicio)
    gas_invoices = sorted(get_ultimas_gas_invoices(cliente_id, n=12), key=lambda x: x.periodo_inicio)

    if not cfe_invoices:
        return jsonify({"error": "Sin facturas CFE disponibles"}), 422

    cfg = {row["clave"]: row["valor"] for row in list_configuracion()}
    tc_str       = cfg.get("tipo_cambio_mxn_usd")
    fe_elec_str  = cfg.get("factor_emision_electricidad_kg_co2_kwh")
    tipo_cambio  = _D(tc_str) if tc_str else _D("17.50")
    factor_emision_elec = float(fe_elec_str) if fe_elec_str else None

    try:
        r = calcular_cogen_desde_modelado(
            kpis_modelado=kpis_modelado,
            rendimiento_electrico=rendimiento_electrico,
            rendimiento_termico=rendimiento_termico,
            eficiencia_caldera=eficiencia_caldera,
            cfe_invoices=cfe_invoices,
            gas_invoices=gas_invoices,
            tipo_cambio=tipo_cambio,
            factor_emision_elec=_D(str(factor_emision_elec)) if factor_emision_elec else None,
            inversion_usd_override=inversion_usd_qs,
            deduccion_fiscal=deduccion_fiscal,
            anios_deduccion=anios_deduccion,
        )
    except Exception as _e:
        logger.exception("Error generando Excel modelado-chp: %s", _e)
        return jsonify({"error": str(_e)}), 500

    # CELs (opcional, para CELs fijo en hoja KPIs)
    cels_mwh_anual = None
    try:
        from calc.cels import calcular_cels as _calcular_cels
        from storage.repository import get_cliente_con_conteos as _gcc
        cliente = _gcc(cliente_id)
        calor_recuperado_anual = sum(m.calor_recuperado_gj for m in r.meses)
        cels_resultado = _calcular_cels(
            kwh_cubiertos_anual=r.kwh_cubiertos_anual,
            gj_gas_cogen_pci_anual=r.gj_gas_cogen_pci_anual,
            calor_recuperado_gj_anual=calor_recuperado_anual,
            capacidad_nominal_kw=r.capacidad_nominal_kw,
            medio_termico=cliente.get("medio_termico") if cliente else None,
            nivel_tension_kv=cliente.get("nivel_tension_kv") if cliente else None,
            altitud_msnm=cliente.get("altitud_msnm") if cliente else None,
            tipo_motor=cliente.get("tipo_motor") if cliente else None,
            medio_termico_vapor_pct=cliente.get("medio_termico_vapor_pct") if cliente else None,
        )
        if cels_resultado and cels_resultado.cels_mwh_anual is not None:
            cels_mwh_anual = float(cels_resultado.cels_mwh_anual)
    except Exception:
        pass

    # Precio gas promedio ponderado de los meses calculados
    total_gj   = sum(float(m.gj_gas_cogen)      for m in r.meses)
    total_cost = sum(float(m.costo_gas_cogen_mxn) for m in r.meses)
    precio_gas_gj = (total_cost / total_gj) if total_gj > 0 else 0.0

    # Precio USD/kW (calculado desde inversión total si se pasó override)
    motores_config_raw = modelado.get("motores_config") or []
    capacidad_total_kw = sum(float(m.get("capacidad_kw", 0)) for m in motores_config_raw)
    if inversion_usd_qs and inversion_usd_qs > 0 and capacidad_total_kw > 0:
        precio_kw_usd = inversion_usd_qs / capacidad_total_kw
    else:
        precio_kw_usd = 1400.0  # default _USD_POR_KW

    # Costo promedio CFE ponderado sobre r.meses
    sum_ah = sum(float(m.ahorro_electricidad_mxn) for m in r.meses)
    sum_cub = sum(float(m.kwh_cubiertos) for m in r.meses)
    kwh_costo_promedio = sum_ah / sum_cub if sum_cub > 0 else 0.0

    # Parámetros para hoja "Parámetros"
    params_excel = {
        "cobertura_pct":              kpis_modelado["cobertura_pct"],
        "rendimiento_electrico":      rendimiento_electrico,
        "rendimiento_termico":        rendimiento_termico,
        "eficiencia_caldera":         eficiencia_caldera,
        "precio_gas_gj":              precio_gas_gj,
        "costo_om_kwh":               0.30,
        "tipo_cambio":                float(tipo_cambio),
        "precio_kw_usd":              precio_kw_usd,
        "deduccion_fiscal":           1 if deduccion_fiscal else 0,
        "anios_deduccion":            anios_deduccion,
        "consumo_cliente_anual_kwh":  float(r.kwh_total_anual) if r.kwh_total_anual else 0.0,
        "kwh_cubiertos_anual":        float(r.kwh_cubiertos_anual),
        "gen_bruta_anual_kwh":        kpis_modelado["gen_bruta_anual_kwh"],
        "consumo_gas_anual_gj":       float(r.gj_gas_cogen_anual),
        "horas_anuales_motor":        kpis_modelado["horas_anuales_motor"],
        "kwh_costo_promedio_cfe":     kwh_costo_promedio,
    }

    # Motores config enriquecido con horas del modelado
    horas_por_motor = modelado.get("horas_por_motor") or {}
    motores_enrich = []
    for m in motores_config_raw:
        mid = str(m.get("id", ""))
        horas = float(horas_por_motor.get(mid, kpis_modelado["horas_anuales_motor"]))
        motores_enrich.append({
            "nombre":       m.get("nombre", f"Motor {mid}"),
            "capacidad_kw": float(m.get("capacidad_kw", 0)),
            "horas_anuales": horas,
        })

    # Curva horaria (opcional — puede ser lenta para archivos grandes)
    curva_raw = None
    try:
        curva_raw = get_modelado_chp_curva(modelado_id)
    except Exception:
        pass

    # Generar Excel
    excel_bytes = generar_excel_modelado_chp(
        params=params_excel,
        r=r,
        motores_config=motores_enrich,
        cliente_nombre=modelado.get("cliente_nombre") or str(cliente_id),
        curva=curva_raw,
        cels_mwh_anual=cels_mwh_anual,
        factor_emision_elec=factor_emision_elec,
    )

    # Nombre de archivo descriptivo
    from storage.repository import get_cliente_con_conteos as _gcc2
    try:
        cliente_info = _gcc2(cliente_id)
        nombre_cliente = (cliente_info.get("nombre") or str(cliente_id)).replace(" ", "_")
    except Exception:
        nombre_cliente = str(cliente_id)

    mes_label = modelado.get("mes_label") or ""
    anio_label = str(modelado.get("anio") or "")
    filename = f"ModeladoCHP_{nombre_cliente}_{mes_label}_{anio_label}.xlsx".strip("_")

    resp = make_response(excel_bytes)
    resp.headers["Content-Type"] = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@clientes_bp.route("/<int:cliente_id>/activar", methods=["POST"])
def activar_cliente(cliente_id: int):
    """Actualiza cliente_activo_id en sesión para usuario_normal multi-cliente."""
    from flask import jsonify
    actor = _get_current_user()
    if not actor:
        return jsonify({"ok": False}), 401
    clientes_ids = session.get("_clientes_ids", [])
    if actor["rol"] == "usuario_normal" and cliente_id not in clientes_ids:
        return jsonify({"ok": False}), 403
    session["cliente_activo_id"] = cliente_id
    session["_empresa_id"] = cliente_id
    return jsonify({"ok": True})


# ── Gestión de plantas ────────────────────────────────────────────────────────

@clientes_bp.route("/<int:cliente_id>/planta/nueva", methods=["GET", "POST"])
def planta_nueva(cliente_id: int):
    user = _get_current_user()
    if not usuario_puede_crear(user or {}):
        flash("No tienes permisos para crear plantas.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        direccion_planta = request.form.get("direccion_planta", "").strip() or None
        notas = request.form.get("notas", "").strip() or None
        if not nombre:
            return render_template(
                "clientes/planta/nueva.html",
                cliente=cliente,
                error="El nombre de la planta es obligatorio.",
                nombre="",
                direccion_planta=direccion_planta or "",
                notas=notas or "",
            )
        try:
            crear_planta(cliente_id, nombre, direccion_planta=direccion_planta, notas=notas)
            session.pop("_plantas_cache", None)
            flash(f"Planta '{nombre}' creada correctamente.", "success")
        except Exception as exc:
            logger.error("Error creando planta cliente_id=%d: %s", cliente_id, exc)
            return render_template(
                "clientes/planta/nueva.html",
                cliente=cliente,
                error=f"Error al crear la planta: {exc}",
                nombre=nombre,
                direccion_planta=direccion_planta or "",
                notas=notas or "",
            )
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    return render_template(
        "clientes/planta/nueva.html",
        cliente=cliente,
        error=None,
        nombre="",
        direccion_planta="",
        notas="",
    )


@clientes_bp.route("/<int:cliente_id>/planta/<int:planta_id>/editar", methods=["GET", "POST"])
def planta_editar(cliente_id: int, planta_id: int):
    user = _get_current_user()
    if not usuario_puede_crear(user or {}):
        flash("No tienes permisos para editar plantas.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    planta = obtener_planta(planta_id)
    if planta is None or planta.get("cliente_id") != cliente_id:
        flash("La planta solicitada no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        direccion_planta = request.form.get("direccion_planta", "").strip() or None
        notas = request.form.get("notas", "").strip() or None

        if not nombre:
            return render_template(
                "clientes/planta/editar.html",
                cliente=cliente,
                planta=planta,
                error="El nombre de la planta es obligatorio.",
                nombre="",
                direccion_planta=direccion_planta or "",
                notas=notas or "",
            )
        try:
            actualizar_planta(planta_id, nombre=nombre, direccion_planta=direccion_planta, notas=notas)
            session.pop("_plantas_cache", None)
            flash("Planta actualizada correctamente.", "success")
        except Exception as exc:
            logger.error("Error actualizando planta id=%d: %s", planta_id, exc)
            return render_template(
                "clientes/planta/editar.html",
                cliente=cliente,
                planta=planta,
                error=f"Error al guardar: {exc}",
                nombre=nombre,
                direccion_planta=direccion_planta or "",
                notas=notas or "",
            )
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    return render_template(
        "clientes/planta/editar.html",
        cliente=cliente,
        planta=planta,
        error=None,
        nombre=planta.get("nombre", ""),
        direccion_planta=planta.get("direccion_planta") or "",
        notas=planta.get("notas") or "",
    )


@clientes_bp.route("/<int:cliente_id>/planta/<int:planta_id>/desactivar", methods=["POST"])
def planta_desactivar(cliente_id: int, planta_id: int):
    user = _get_current_user()
    if not usuario_puede_borrar(user or {}):
        flash("No tienes permisos para desactivar plantas.", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    planta = obtener_planta(planta_id)
    if planta is None or planta.get("cliente_id") != cliente_id:
        flash("La planta solicitada no existe.", "warning")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    try:
        actualizar_planta(planta_id, activo=False)
        session.pop("_plantas_cache", None)
        # Si era la planta activa, limpiar sesión
        if session.get("planta_activa_id") == planta_id:
            session.pop("planta_activa_id", None)
        flash(f"Planta '{planta.get('nombre')}' desactivada.", "success")
    except Exception as exc:
        logger.error("Error desactivando planta id=%d: %s", planta_id, exc)
        flash(f"Error al desactivar: {exc}", "danger")

    return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
