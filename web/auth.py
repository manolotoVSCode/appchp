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
                     access_token: str, remember: bool = False) -> None:
    session.permanent = remember
    session["_user_id"] = user_id
    session["_user_email"] = email
    session["_user_rol"] = rol
    session["_empresa_id"] = empresa_id
    session["_access_token"] = access_token


def clear_user_session() -> None:
    for key in ("_user_id", "_user_email", "_user_rol", "_empresa_id",
                "_access_token", "_cp_cache", "cliente_activo_id",
                "cliente_activo_nombre", "cliente_activo_logo_url"):
        session.pop(key, None)


def get_current_user() -> dict | None:
    """Retorna dict con user_id, email, rol, empresa_id o None si no autenticado."""
    user_id = session.get("_user_id")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "email": session.get("_user_email", ""),
        "rol": session.get("_user_rol", ""),
        "empresa_id": session.get("_empresa_id"),
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


def _user_profile_exists(user_id: str) -> bool:
    return _get_user_profile(user_id) is not None


def _create_user_profile(user_id: str, email: str, rol: str,
                         empresa_id: int | None = None) -> bool:
    try:
        sb = _get_supabase()
        sb.table("user_profiles").insert({
            "id": user_id,
            "email": email,
            "rol": rol,
            "empresa_id": empresa_id,
            "activo": True,
        }).execute()
        return True
    except Exception as exc:
        logger.error("Error creando user_profile user_id=%s: %s", user_id, exc)
        return False


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
                raw_next = request.args.get("next", "")
                next_url = raw_next if _es_url_segura(raw_next) else url_for("dashboard")
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
        return "Error al iniciar sesión. Intenta nuevamente."

    if not res or not res.session:
        return "Correo o contraseña incorrectos."

    user_id = res.user.id
    access_token = res.session.access_token

    profile = _get_user_profile(user_id)
    if profile is None:
        logger.warning("Login sin perfil: user_id=%s email=%s", user_id, email)
        return "Tu cuenta no tiene perfil de acceso. Contacta al administrador."

    if not profile.get("activo", True):
        return "Tu cuenta está desactivada. Contacta al administrador."

    set_user_session(
        user_id=user_id,
        email=profile.get("email", email),
        rol=profile["rol"],
        empresa_id=profile.get("empresa_id"),
        access_token=access_token,
        remember=remember,
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


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if is_authenticated():
        return redirect(url_for("dashboard"))

    enviado = False
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            error = "Ingresa tu correo electrónico."
        else:
            try:
                sb = _get_supabase()
                redirect_to = url_for("auth.reset_password_nuevo", _external=True)
                sb.auth.reset_password_for_email(email, {"redirect_to": redirect_to})
                enviado = True
            except Exception as exc:
                logger.error("Error reset_password_for_email %s: %s", email, exc)
                # No revelar si el correo existe o no
                enviado = True

    return render_template("auth/reset_password.html", enviado=enviado, error=error)


@auth_bp.route("/reset-password/nuevo", methods=["GET", "POST"])
def reset_password_nuevo():
    """Formulario de nueva contraseña. El token llega en el hash URL (#access_token=...)."""
    error = None
    if request.method == "POST":
        token = request.form.get("access_token", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not token:
            error = "Token inválido o expirado. Solicita un nuevo enlace."
        elif len(password) < 8:
            error = "La contraseña debe tener al menos 8 caracteres."
        elif password != password2:
            error = "Las contraseñas no coinciden."
        else:
            error = _handle_password_reset(token, password)
            if error is None:
                flash("Contraseña actualizada correctamente. Ya puedes iniciar sesión.", "success")
                return redirect(url_for("auth.login"))

    return render_template("auth/reset_password_nuevo.html", error=error)


def _handle_password_reset(token: str, new_password: str) -> str | None:
    """Valida token y actualiza contraseña. Retorna error string o None si OK."""
    sb = _get_supabase()
    try:
        user_res = sb.auth.get_user(token)
        user_id = user_res.user.id
    except Exception as exc:
        logger.warning("Token inválido en reset_password: %s", exc)
        return "Token inválido o expirado. Solicita un nuevo enlace."

    try:
        sb.auth.admin.update_user_by_id(user_id, {"password": new_password})
        return None
    except Exception as exc:
        logger.error("Error actualizando password user_id=%s: %s", user_id, exc)
        return "Error al actualizar la contraseña. Intenta nuevamente."


@auth_bp.route("/aceptar-invitacion", methods=["GET", "POST"])
def aceptar_invitacion():
    """Flujo de aceptación de invitación.
    GET: el hash URL contiene access_token; JS lo extrae y hace POST automático.
    POST: servidor valida token, actualiza contraseña, crea sesión.
    """
    error = None
    if request.method == "POST":
        token = request.form.get("access_token", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not token:
            error = "Token de invitación inválido o expirado."
        elif len(password) < 8:
            error = "La contraseña debe tener al menos 8 caracteres."
        elif password != password2:
            error = "Las contraseñas no coinciden."
        else:
            error = _handle_accept_invitation(token, password)
            if error is None:
                flash("Cuenta activada correctamente. Bienvenido.", "success")
                return redirect(url_for("dashboard"))

    return render_template("auth/aceptar_invitacion.html", error=error)


def _handle_accept_invitation(token: str, new_password: str) -> str | None:
    """Activa cuenta de usuario invitado. Retorna error string o None si OK."""
    sb = _get_supabase()
    try:
        user_res = sb.auth.get_user(token)
        user = user_res.user
        user_id = user.id
        email = user.email
    except Exception as exc:
        logger.warning("Token inválido en aceptar_invitacion: %s", exc)
        return "Token de invitación inválido o expirado. Contacta al administrador."

    try:
        sb.auth.admin.update_user_by_id(user_id, {"password": new_password})
    except Exception as exc:
        logger.error("Error seteando password en invitación user_id=%s: %s", user_id, exc)
        return "Error al activar la cuenta. Contacta al administrador."

    # Asegurar que el perfil existe (pudo no crearse en el invite)
    if not _user_profile_exists(user_id):
        _create_user_profile(user_id, email, ROL_USUARIO_NORMAL)
        logger.warning("Perfil creado en aceptar_invitacion como usuario_normal: %s", email)

    # Iniciar sesión inmediatamente
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": new_password})
        if res and res.session:
            profile = _get_user_profile(user_id)
            if profile:
                set_user_session(
                    user_id=user_id,
                    email=profile.get("email", email),
                    rol=profile["rol"],
                    empresa_id=profile.get("empresa_id"),
                    access_token=res.session.access_token,
                    remember=False,
                )
    except Exception as exc:
        logger.warning("Error auto-login tras aceptar invitación: %s", exc)
        flash("Cuenta activada. Inicia sesión con tu nueva contraseña.", "success")
        return None  # Cuenta activada aunque no hayamos podido hacer auto-login

    return None


# ── Inicialización ────────────────────────────────────────────────────────────

def init_auth(app):
    """Registra el blueprint de autenticación y configura la sesión."""
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(days=30))
    app.register_blueprint(auth_bp)
