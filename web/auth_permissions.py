# web/auth_permissions.py
from __future__ import annotations

from functools import wraps

from flask import abort, current_app, flash, redirect, request, url_for

from web.auth import (
    ROL_MASTER_ADMIN,
    ROL_ADMIN,
    ROL_USUARIO_NORMAL,
    get_current_user,
    is_authenticated,
)


# ── Decoradores ───────────────────────────────────────────────────────────────

def login_required(f):
    """Redirige a login si el usuario no está autenticado."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def require_role(*roles: str):
    """Exige que el usuario tenga uno de los roles indicados."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user or user["rol"] not in roles:
                flash("No tienes permisos para realizar esta acción.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_master_admin(f):
    return require_role(ROL_MASTER_ADMIN)(f)


def require_admin_or_master(f):
    return require_role(ROL_MASTER_ADMIN, ROL_ADMIN)(f)


def require_master_admin_y_fase2(f):
    """404 si FASE2_HABILITADA está apagada; 403 si el rol no es master_admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_app.config.get("FASE2_HABILITADA", False):
            abort(404)
        current = get_current_user()
        if not current or current.get("rol") != ROL_MASTER_ADMIN:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Checks de permisos ────────────────────────────────────────────────────────

def usuario_puede_borrar(user: dict) -> bool:
    """master_admin y admin pueden borrar clientes, facturas y contratos."""
    return user.get("rol") in (ROL_MASTER_ADMIN, ROL_ADMIN)


def usuario_puede_crear(user: dict) -> bool:
    """master_admin y admin pueden crear clientes."""
    return user.get("rol") in (ROL_MASTER_ADMIN, ROL_ADMIN)


def usuario_puede_ver_empresa(empresa_id: int, user: dict) -> bool:
    """
    master_admin y admin ven todas las empresas.
    usuario_normal: verifica en clientes_ids (multi) o empresa_id (fallback legacy).
    """
    if user.get("rol") in (ROL_MASTER_ADMIN, ROL_ADMIN):
        return True
    clientes_ids = user.get("clientes_ids", [])
    if clientes_ids:
        return empresa_id in clientes_ids
    return user.get("empresa_id") == empresa_id


def filtrar_empresas_para_usuario(clientes: list[dict], user: dict) -> list[dict]:
    """
    Filtra la lista de clientes según el rol del usuario.
    master_admin/admin: sin filtro.
    usuario_normal: filtra por clientes_ids (multi) o empresa_id (fallback legacy).
    """
    if user.get("rol") in (ROL_MASTER_ADMIN, ROL_ADMIN):
        return clientes
    clientes_ids = user.get("clientes_ids", [])
    if clientes_ids:
        return [c for c in clientes if c.get("id") in clientes_ids]
    empresa_id = user.get("empresa_id")
    if empresa_id is None:
        return []
    return [c for c in clientes if c.get("id") == empresa_id]


def validar_borrar_usuario(actor: dict, target: dict) -> str | None:
    """
    Valida si actor puede borrar a target.
    Retorna mensaje de error o None si la operación es válida.
    """
    actor_rol = actor.get("rol")
    target_rol = target.get("rol")
    if actor_rol not in (ROL_MASTER_ADMIN, ROL_ADMIN):
        return "No tienes permiso para borrar usuarios."
    if actor.get("user_id") == target.get("id"):
        return "No puedes borrar tu propia cuenta."
    if target_rol == ROL_MASTER_ADMIN:
        return "No se puede borrar al Master Admin."
    if actor_rol == ROL_ADMIN and target_rol == ROL_ADMIN:
        return "No puedes borrar a otro Administrador."
    return None
