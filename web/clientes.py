# web/clientes.py
from __future__ import annotations

import logging
import re
import tempfile
import unicodedata
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
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
    rfc_existe,
    cliente_tiene_facturas,
    get_contratos_por_cliente,
    get_contrato,
    get_contrato_con_conteos,
    create_contrato,
    update_contrato,
    delete_contrato,
    ContratoIdentificadorDuplicado,
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
)

logger = logging.getLogger(__name__)

_RFC_RE = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

_SECTORES = ["Hotelero", "Manufactura", "Alimentos y bebidas", "Químico", "Textil", "Otro"]
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
            if not (1900 <= anio_int <= current_year + 1):
                return f"El año de inicio debe estar entre 1900 y {current_year + 1}."
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

def _validar_rfc(rfc: str) -> str | None:
    if not _RFC_RE.match(rfc):
        return "RFC inválido. Debe tener 12 o 13 caracteres con formato mexicano (3-4 letras, 6 dígitos de fecha, 3 de homoclave)."
    return None


def _validar_campos(nombre: str, rfc: str) -> str | None:
    if not nombre:
        return "El nombre del cliente es obligatorio."
    if not rfc:
        return "El RFC es obligatorio."
    return _validar_rfc(rfc)


# ── Rutas ─────────────────────────────────────────────────────────────────────

@clientes_bp.route("/")
def listado():
    clientes = get_all_clientes_con_conteos()
    return render_template("clientes/list.html", clientes=clientes)


@clientes_bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        rfc = _sanitizar(request.form.get("rfc", ""))
        notas = request.form.get("notas", "").strip() or None
        campos = _extraer_campos_extendidos(request.form)

        error = _validar_campos(nombre, rfc) or _validar_campos_extendidos(request.form)
        if error is None and rfc_existe(rfc):
            error = f"Ya existe un cliente con RFC {rfc}."

        if error:
            return render_template(
                "clientes/nuevo.html",
                error=error, nombre=nombre, rfc=rfc, notas=notas or "",
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
                nombre=nombre, rfc=rfc, notas=notas or "",
                **_FORM_SELECTS, **campos,
            )

    return render_template(
        "clientes/nuevo.html",
        error=None, nombre="", rfc="", notas="",
        **_FORM_SELECTS,
    )


@clientes_bp.route("/<int:cliente_id>")
def ficha(cliente_id: int):
    from storage.repository import get_ppa_bloques_mensuales
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))
    contratos = get_contratos_por_cliente(cliente_id)
    # PPA bloques para precarga: {anio: {mes: mwh_str}}
    ppa_bloques: dict[int, dict[int, str]] = {}
    try:
        for b in get_ppa_bloques_mensuales(cliente_id):
            ppa_bloques.setdefault(b["anio"], {})[b["mes"]] = b["bloque_contratado_mwh"]
    except Exception:
        pass
    return render_template("clientes/ficha.html", cliente=cliente, contratos=contratos, ppa_bloques=ppa_bloques)


@clientes_bp.route("/<int:cliente_id>/activar", methods=["POST"])
def cliente_activar(cliente_id: int):
    from flask import jsonify
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        return jsonify({"error": "Cliente no encontrado"}), 404
    session["cliente_activo_id"] = cliente_id
    session["cliente_activo_nombre"] = cliente["nombre"]
    session["cliente_activo_logo_url"] = cliente.get("logo_url")
    session.pop("_cp_cache", None)
    return jsonify({"ok": True})


@clientes_bp.route("/desactivar", methods=["POST"])
def cliente_desactivar():
    from flask import jsonify
    session.pop("cliente_activo_id", None)
    session.pop("cliente_activo_nombre", None)
    session.pop("cliente_activo_logo_url", None)
    return jsonify({"ok": True})


@clientes_bp.route("/<int:cliente_id>/editar", methods=["GET", "POST"])
def editar(cliente_id: int):
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    tiene_facturas = cliente_tiene_facturas(cliente_id)

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        rfc_form = request.form.get("rfc", "").strip().upper()
        notas = request.form.get("notas", "").strip() or None
        campos = _extraer_campos_extendidos(request.form)

        error = None
        if not nombre:
            error = "El nombre del cliente es obligatorio."
        elif not tiene_facturas:
            error = _validar_rfc(rfc_form)
            if error is None and rfc_form != cliente["rfc"] and rfc_existe(rfc_form, exclude_id=cliente_id):
                error = f"Ya existe un cliente con RFC {rfc_form}."
        if error is None:
            error = _validar_campos_extendidos(request.form)

        rfc_a_guardar = None if tiene_facturas else rfc_form

        if error:
            return render_template(
                "clientes/editar.html",
                cliente=cliente, tiene_facturas=tiene_facturas,
                error=error, nombre=nombre,
                rfc=cliente["rfc"] if tiene_facturas else rfc_form,
                notas=notas or "",
                **_FORM_SELECTS, **campos,
            )

        try:
            update_cliente(cliente_id, nombre=nombre, notas=notas, rfc=rfc_a_guardar, **campos)
            logger.info("Cliente actualizado: id=%d, nombre='%s'", cliente_id, nombre)
            if session.get("cliente_activo_id") == cliente_id:
                session["cliente_activo_nombre"] = nombre
            flash("Datos del cliente actualizados.", "success")
            return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
        except Exception as exc:
            logger.error("Error actualizando cliente id=%d: %s", cliente_id, exc)
            return render_template(
                "clientes/editar.html",
                cliente=cliente, tiene_facturas=tiene_facturas,
                error=f"Error al guardar: {exc}", nombre=nombre,
                rfc=cliente["rfc"] if tiene_facturas else rfc_form,
                notas=notas or "",
                **_FORM_SELECTS, **campos,
            )

    return render_template(
        "clientes/editar.html",
        cliente=cliente, tiene_facturas=tiene_facturas,
        error=None, nombre=cliente["nombre"],
        rfc=cliente["rfc"], notas=cliente.get("notas") or "",
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
        nivel_tension_kv=cliente.get("nivel_tension_kv"),
        altitud_msnm=cliente.get("altitud_msnm"),
        tipo_motor=cliente.get("tipo_motor"),
        **_FORM_SELECTS,
    )


@clientes_bp.route("/<int:cliente_id>/borrar", methods=["POST"])
def borrar(cliente_id: int):
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))

    nombre = cliente["nombre"]
    confirmacion = request.form.get("confirmacion", "").strip()

    if confirmacion != nombre:
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

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        tipo = request.form.get("tipo", "").strip()
        identificador_real = _sanitizar(request.form.get("identificador_real", ""))
        notas = request.form.get("notas", "").strip() or None

        error = None
        if not nombre:
            error = "El nombre del contrato es obligatorio."
        elif tipo not in TIPOS_VALIDOS:
            error = "Tipo inválido. Debe ser eléctrico básico (CFE), eléctrico calificado (PPA) o gas."
        elif not identificador_real:
            error = "El identificador real es obligatorio."

        if error is None:
            try:
                contrato_id = create_contrato(cliente_id, nombre, tipo, identificador_real, notas)
                logger.info(
                    "Contrato creado: id=%d, cliente_id=%d, nombre='%s'",
                    contrato_id, cliente_id, nombre,
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
            error=error,
            nombre=nombre,
            tipo=tipo,
            identificador_real=identificador_real,
            notas=notas or "",
        )

    return render_template(
        "clientes/contratos/nuevo.html",
        cliente=cliente,
        error=None,
        nombre="",
        tipo="electrico_basico",
        identificador_real="",
        notas="",
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

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        tipo = request.form.get("tipo", "").strip()
        identificador_real = _sanitizar(request.form.get("identificador_real", ""))
        notas = request.form.get("notas", "").strip() or None

        error = None
        if not nombre:
            error = "El nombre del contrato es obligatorio."
        elif tipo not in TIPOS_VALIDOS:
            error = "Tipo inválido. Debe ser eléctrico básico (CFE), eléctrico calificado (PPA) o gas."
        elif not identificador_real:
            error = "El identificador real es obligatorio."

        if error is None:
            try:
                update_contrato(contrato_id, nombre, tipo, identificador_real, notas)
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
        error=None,
        nombre=contrato.nombre,
        tipo=contrato.tipo,
        identificador_real=contrato.identificador_real,
        notas=contrato.notas or "",
    )


@clientes_bp.route("/<int:cliente_id>/contratos/<int:contrato_id>/borrar", methods=["POST"])
def contrato_borrar(cliente_id: int, contrato_id: int):
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
    confirmados = set(request.form.getlist("confirmado_pese_a_discrepancia"))

    if not files or all(not f.filename for f in files):
        return jsonify({"procesados": 0, "errores": [{"nombre": "", "error": "No se enviaron archivos"}]}), 400

    ok_count = 0
    exitosos = []
    errors = []
    pendientes_confirmacion = []

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
                identificador_factura = invoice.numero_servicio
            else:
                parser = get_gas_parser()
                invoice = parser.parse(tmp_path)
                identificador_factura = invoice.cuenta_contrato

            rfc_factura = (invoice.rfc_cliente or "").strip()
            rfc_cliente_real = (cliente.get("rfc") or "").strip()

            id_discrepante = identificador_factura != contrato.identificador_real
            if rfc_factura:
                rfc_discrepante = rfc_factura != rfc_cliente_real
            else:
                logger.warning(
                    "RFC vacío en factura '%s' (contrato_id=%d, cliente_id=%d) — "
                    "no se puede verificar RFC; se asocia al cliente del contrato.",
                    nombre, contrato_id, cliente_id,
                )
                rfc_discrepante = False

            if (id_discrepante or rfc_discrepante) and nombre not in confirmados:
                pendiente: dict = {"nombre": nombre}
                if id_discrepante:
                    pendiente["identificador_factura"] = identificador_factura
                    pendiente["identificador_contrato"] = contrato.identificador_real
                if rfc_discrepante:
                    pendiente["rfc_factura"] = rfc_factura
                    pendiente["rfc_cliente"] = rfc_cliente_real
                pendientes_confirmacion.append(pendiente)
                continue

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
            exitosos.append({"nombre_original": nombre, "nombre_canonico": nombre_canonico})
        except Exception as e:
            logger.error("Error procesando '%s': %s: %s", nombre, type(e).__name__, e, exc_info=True)
            errors.append({"nombre": nombre, "error": str(e)})
        finally:
            tmp_path.unlink(missing_ok=True)

    return jsonify({
        "procesados": ok_count,
        "exitosos": exitosos,
        "errores": errors,
        "pendientes_confirmacion": pendientes_confirmacion,
    })


@clientes_bp.route(
    "/<int:cliente_id>/contratos/<int:contrato_id>/facturas/<int:factura_id>/borrar",
    methods=["POST"],
)
def contrato_factura_borrar(cliente_id: int, contrato_id: int, factura_id: int):
    from flask import Response, jsonify

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

    data = request.get_json(silent=True) or {}
    anio = data.get("anio")
    seleccionado = data.get("seleccionado")
    if not isinstance(anio, int):
        return jsonify({"error": "'anio' debe ser un entero"}), 400
    if not isinstance(seleccionado, bool):
        return jsonify({"error": "'seleccionado' debe ser true o false"}), 400

    try:
        if seleccionado:
            n = upsert_meses_seleccionados_anio(contrato_id, anio)
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
            error=f"No se pudo leer el PDF: {exc}",
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
