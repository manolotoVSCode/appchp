# web/clientes.py
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for
from parsers.cfe import get_cfe_parser
from parsers.gas import get_gas_parser
from storage.repository import (
    get_all_clientes_con_conteos,
    get_cliente_con_conteos,
    create_cliente,
    update_cliente,
    delete_cliente,
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
)

logger = logging.getLogger(__name__)

_RFC_RE = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')


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
        rfc = request.form.get("rfc", "").strip().upper()
        notas = request.form.get("notas", "").strip() or None

        error = _validar_campos(nombre, rfc)
        if error is None and rfc_existe(rfc):
            error = f"Ya existe un cliente con RFC {rfc}."

        if error:
            return render_template(
                "clientes/nuevo.html",
                error=error, nombre=nombre, rfc=rfc, notas=notas or "",
            )

        try:
            cliente_id = create_cliente(nombre, rfc, notas)
            logger.info("Cliente creado: id=%d, nombre='%s', rfc=%s", cliente_id, nombre, rfc)
            flash(f"Cliente '{nombre}' creado correctamente.", "success")
            return redirect(url_for("clientes.ficha", cliente_id=cliente_id))
        except Exception as exc:
            logger.error("Error creando cliente nombre='%s', rfc=%s: %s", nombre, rfc, exc)
            return render_template(
                "clientes/nuevo.html",
                error=f"Error al crear el cliente: {exc}",
                nombre=nombre, rfc=rfc, notas=notas or "",
            )

    return render_template("clientes/nuevo.html", error=None, nombre="", rfc="", notas="")


@clientes_bp.route("/<int:cliente_id>")
def ficha(cliente_id: int):
    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        flash("El cliente solicitado no existe.", "warning")
        return redirect(url_for("clientes.listado"))
    contratos = get_contratos_por_cliente(cliente_id)
    return render_template("clientes/ficha.html", cliente=cliente, contratos=contratos)


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

        error = None
        if not nombre:
            error = "El nombre del cliente es obligatorio."
        elif not tiene_facturas:
            error = _validar_rfc(rfc_form)
            if error is None and rfc_form != cliente["rfc"] and rfc_existe(rfc_form, exclude_id=cliente_id):
                error = f"Ya existe un cliente con RFC {rfc_form}."

        rfc_a_guardar = None if tiene_facturas else rfc_form

        if error:
            return render_template(
                "clientes/editar.html",
                cliente=cliente, tiene_facturas=tiene_facturas,
                error=error, nombre=nombre,
                rfc=cliente["rfc"] if tiene_facturas else rfc_form,
                notas=notas or "",
            )

        try:
            update_cliente(cliente_id, nombre=nombre, notas=notas, rfc=rfc_a_guardar)
            logger.info("Cliente actualizado: id=%d, nombre='%s'", cliente_id, nombre)
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
            )

    return render_template(
        "clientes/editar.html",
        cliente=cliente, tiene_facturas=tiene_facturas,
        error=None, nombre=cliente["nombre"],
        rfc=cliente["rfc"], notas=cliente.get("notas") or "",
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
        flash(f"Cliente '{nombre}' y todas sus facturas han sido borrados.", "success")
    except Exception as exc:
        logger.error("Error borrando cliente id=%d: %s", cliente_id, exc)
        flash(f"Error al borrar el cliente: {exc}", "danger")
        return redirect(url_for("clientes.ficha", cliente_id=cliente_id))

    return redirect(url_for("clientes.listado"))


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
        identificador_real = request.form.get("identificador_real", "").strip()
        notas = request.form.get("notas", "").strip() or None

        error = None
        if not nombre:
            error = "El nombre del contrato es obligatorio."
        elif tipo not in ("electrico", "gas"):
            error = "El tipo debe ser 'electrico' o 'gas'."
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
        tipo="electrico",
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

    return render_template(
        "clientes/contratos/ficha.html",
        cliente=cliente,
        contrato=contrato,
        facturas_cfe=facturas_cfe,
        facturas_gas=facturas_gas,
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
        identificador_real = request.form.get("identificador_real", "").strip()
        notas = request.form.get("notas", "").strip() or None

        error = None
        if not nombre:
            error = "El nombre del contrato es obligatorio."
        elif tipo not in ("electrico", "gas"):
            error = "El tipo debe ser 'electrico' o 'gas'."
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
    from flask import Response, current_app, jsonify

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
            tipo_contrato = "electrico" if tipo == "cfe" else "gas"
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

            if identificador_factura != contrato.identificador_real and nombre not in confirmados:
                pendientes_confirmacion.append({
                    "nombre": nombre,
                    "identificador_factura": identificador_factura,
                    "identificador_contrato": contrato.identificador_real,
                })
                continue

            if tipo == "cfe":
                factura_id, nombre_canonico = save_cfe_invoice(invoice, contrato_id=contrato_id)
            else:
                factura_id, nombre_canonico = save_gas_invoice(invoice, contrato_id=contrato_id)

            logger.info("Factura guardada: '%s' → id=%d (tipo=%s, contrato=%d)", nombre, factura_id, tipo, contrato_id)
            ok_count += 1
            exitosos.append({"nombre_original": nombre, "nombre_canonico": nombre_canonico})
        except Exception as e:
            logger.error("Error procesando '%s': %s: %s", nombre, type(e).__name__, e, exc_info=True)
            errors.append({"nombre": nombre, "error": str(e)})
        finally:
            tmp_path.unlink(missing_ok=True)

    if ok_count > 0:
        current_app.config["RESULTADO"] = None

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
    from flask import Response, current_app, jsonify

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
        current_app.config["RESULTADO"] = None
        logger.info("Factura borrada: id=%d, tipo=%s, contrato_id=%d", factura_id, tipo, contrato_id)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error("Error borrando factura id=%d, tipo=%s: %s", factura_id, tipo, exc)
        return jsonify({"error": str(exc)}), 500
