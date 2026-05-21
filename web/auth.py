# web/auth.py
from __future__ import annotations

import base64
import json
import logging
import urllib.parse
from datetime import timedelta
from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ── Roles válidos ─────────────────────────────────────────────────────────────

ROL_MASTER_ADMIN = "master_admin"
ROL_ADMIN = "admin"
ROL_USUARIO_NORMAL = "usuario_normal"
ROLES_VALIDOS = {ROL_MASTER_ADMIN, ROL_ADMIN, ROL_USUARIO_NORMAL}


# ── Helpers de sesión ─────────────────────────────────────────────────────────

def set_user_session(user_id: str, email: str, rol: str, empresa_id: int | None,
                     access_token: str, remember: bool = False,
                     empresa_nombre: str | None = None) -> None:
    session.permanent = remember
    session["_user_id"] = user_id
    session["_user_email"] = email
    session["_user_rol"] = rol
    session["_empresa_id"] = empresa_id
    session["_empresa_nombre"] = empresa_nombre
    session["_access_token"] = access_token


def clear_user_session() -> None:
    for key in ("_user_id", "_user_email", "_user_rol", "_empresa_id", "_empresa_nombre",
                "_access_token", "_cp_cache", "cliente_activo_id",
                "cliente_activo_nombre", "cliente_activo_logo_url"):
        session.pop(key, None)


def get_current_user() -> dict | None:
    """Retorna dict con user_id, email, rol, empresa_id, empresa_nombre o None si no autenticado."""
    user_id = session.get("_user_id")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "email": session.get("_user_email", ""),
        "rol": session.get("_user_rol", ""),
        "empresa_id": session.get("_empresa_id"),
        "empresa_nombre": session.get("_empresa_nombre"),
    }


def is_authenticated() -> bool:
    return bool(session.get("_user_id"))


# ── JWT decode (sin PyJWT) ────────────────────────────────────────────────────

def _decode_jwt_payload(token: str) -> dict:
    """Decodifica el payload de un JWT sin verificar firma."""
    try:
        segment = token.split(".")[1]
        # Añadir padding para base64
        segment += "=" * (4 - len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(segment))
    except Exception:
        return {}


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _get_supabase():
    from storage.repository import _supabase
    return _supabase


def _get_user_profile(user_id: str) -> dict | None:
    """Obtiene perfil desde user_profiles."""
    try:
        sb = _get_supabase()
        res = sb.table("user_profiles").select("*").eq("id", user_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.error("Error leyendo user_profiles id=%s: %s", user_id, exc)
        return None


# ── URL segura ────────────────────────────────────────────────────────────────

def _es_url_segura(url: str) -> bool:
    if not url or not url.startswith("/") or url.startswith("//"):
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "" and parsed.netloc == ""


# ── Rutas de autenticación ────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if is_authenticated():
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not email or not password:
            error = "Ingresa tu correo y contraseña."
        else:
            error = _handle_login(email, password, remember)
            if error is None:
                user = get_current_user()
                if user and user["rol"] == ROL_USUARIO_NORMAL:
                    empresa_id = user.get("empresa_id")
                    if empresa_id:
                        return redirect(url_for("clientes.ficha", cliente_id=empresa_id))
                    return render_template(
                        "auth/login.html",
                        error="Sin empresa asignada. Contacta al administrador.",
                    )
                raw_next = request.args.get("next", "")
                next_url = raw_next if _es_url_segura(raw_next) else url_for("clientes.listado")
                return redirect(next_url)

    return render_template("auth/login.html", error=error)


def _handle_login(email: str, password: str, remember: bool) -> str | None:
    """Intenta autenticar con Supabase. Retorna mensaje de error o None si OK."""
    sb = _get_supabase()
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        msg = str(exc).lower()
        if "invalid" in msg or "credentials" in msg or "email" in msg:
            return "Correo o contraseña incorrectos."
        logger.error("Error en sign_in_with_password para %s: %s", email, exc)
        return f"Error sign_in: {exc}"

    if not res or not res.session:
        return "Correo o contraseña incorrectos."

    user_id = res.user.id
    access_token = res.session.access_token

    # sign_in_with_password cambia el Authorization del cliente compartido al JWT del
    # usuario (authenticated). Resetear a service_role para que _get_user_profile
    # pueda leer user_profiles sin depender de GRANTs a authenticated.
    import os
    try:
        sb.postgrest.auth(os.environ["SUPABASE_KEY"])
    except Exception:
        pass

    profile = _get_user_profile(user_id)
    if profile is None:
        logger.warning("Perfil no encontrado: user_id=%s", user_id)
        return "Tu cuenta no tiene perfil de acceso. Contacta al administrador."

    if not profile.get("activo", True):
        return "Tu cuenta está desactivada. Contacta al administrador."

    empresa_nombre = None
    if profile["rol"] == ROL_USUARIO_NORMAL and profile.get("empresa_id"):
        try:
            from storage.repository import get_cliente_con_conteos as _gcc
            empresa = _gcc(profile["empresa_id"])
            if empresa:
                empresa_nombre = empresa.get("nombre")
        except Exception:
            pass

    set_user_session(
        user_id=user_id,
        email=profile.get("email", email),
        rol=profile["rol"],
        empresa_id=profile.get("empresa_id"),
        access_token=access_token,
        remember=remember,
        empresa_nombre=empresa_nombre,
    )
    logger.info("Login exitoso: email=%s rol=%s", email, profile["rol"])
    return None


@auth_bp.route("/logout")
def logout():
    try:
        sb = _get_supabase()
        token = session.get("_access_token")
        if token:
            sb.auth.sign_out()
    except Exception:
        pass
    clear_user_session()
    return redirect(url_for("auth.login"))


# ── Inicialización ────────────────────────────────────────────────────────────

def init_auth(app):
    """Registra el blueprint de autenticación y configura la sesión."""
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(days=30))
    app.register_blueprint(auth_bp)
