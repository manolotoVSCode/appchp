# web/clientes.py
from __future__ import annotations

import logging
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
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
)

logger = logging.getLogger(__name__)

_RFC_RE = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')

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

    return render_template(
        "clientes/contratos/ficha.html",
        cliente=cliente,
        contrato=contrato,
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
