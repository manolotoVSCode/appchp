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
    return render_template("clientes/ficha.html", cliente=cliente)


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
