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
    current_app,
    flash,
    make_response,
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
ROL_USUARIO_AVANZADO = "usuario_avanzado"
ROLES_VALIDOS = {ROL_MASTER_ADMIN, ROL_ADMIN, ROL_USUARIO_NORMAL, ROL_USUARIO_AVANZADO}


# ── Helpers de sesión ─────────────────────────────────────────────────────────

def set_user_session(user_id: str, email: str, rol: str, empresa_id: int | None,
                     access_token: str, remember: bool = False,
                     empresa_nombre: str | None = None,
                     nombre: str | None = None,
                     apellido: str | None = None,
                     clientes_ids: list[int] | None = None) -> None:
    from storage.repository import get_session_version
    session.permanent = remember
    session["_user_id"] = user_id
    session["_user_email"] = email
    session["_user_rol"] = rol
    session["_empresa_id"] = empresa_id
    session["_empresa_nombre"] = empresa_nombre
    session["_nombre"] = nombre
    session["_apellido"] = apellido
    session["_access_token"] = access_token
    session["_session_version"] = get_session_version(user_id) or 1

    if clientes_ids is not None:
        session["_clientes_ids"] = clientes_ids
    elif rol == ROL_USUARIO_NORMAL:
        from storage.repository import get_clientes_de_usuario
        ids = [c["id"] for c in get_clientes_de_usuario(user_id)]
        session["_clientes_ids"] = ids
        if len(ids) == 1:
            session["_empresa_id"] = ids[0]
        else:
            session["_empresa_id"] = empresa_id  # puede quedar NULL
    elif rol == ROL_USUARIO_AVANZADO:
        # usuario_avanzado opera sobre un único cliente (empresa_id)
        session["_clientes_ids"] = [empresa_id] if empresa_id else []
    else:
        session["_clientes_ids"] = []

    logger.debug(
        "set_user_session: clientes_ids=%s empresa_id=%s",
        session.get("_clientes_ids"), session.get("_empresa_id"),
    )


def clear_user_session() -> None:
    """Limpia completamente la sesión Flask del usuario, preservando el token CSRF."""
    csrf_token = session.get("csrf_token")
    session.clear()
    if csrf_token:
        session["csrf_token"] = csrf_token


def get_current_user() -> dict | None:
    """Retorna dict con user_id, email, rol, empresa_id, empresa_nombre, clientes_ids o None si no autenticado."""
    user_id = session.get("_user_id")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "email": session.get("_user_email", ""),
        "rol": session.get("_user_rol", ""),
        "empresa_id": session.get("_empresa_id"),
        "empresa_nombre": session.get("_empresa_nombre"),
        "nombre": session.get("_nombre"),
        "apellido": session.get("_apellido"),
        "clientes_ids": session.get("_clientes_ids", []),
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


def _verificar_session_version_con_cache(user_id: str) -> bool:
    """Verifica que _session_version de la cookie coincide con BD. Cache 5 minutos."""
    from time import time
    from storage.repository import get_session_version
    cookie_version = session.get("_session_version", 0)
    cache = session.get("_sv_check")
    if cache and cache.get("user_id") == user_id and time() - cache.get("ts", 0) < 300:
        return cookie_version == cache.get("version", -1)
    actual = get_session_version(user_id)
    if actual is None:
        return True  # error de red: asumir válido
    session["_sv_check"] = {"user_id": user_id, "ts": time(), "version": actual}
    return cookie_version == actual


def _verificar_activo_con_cache(user_id: str) -> bool:
    """Verifica si el usuario sigue activo en user_profiles, con cache de 5 minutos en sesión."""
    from time import time
    cache = session.get("_activo_check")
    if cache and cache.get("user_id") == user_id and time() - cache.get("ts", 0) < 300:
        return cache.get("activo", True)
    try:
        sb = _get_supabase()
        res = sb.table("user_profiles").select("activo").eq("id", user_id).limit(1).execute()
        rows = res.data or []
        activo = bool(rows and rows[0].get("activo", False))
    except Exception:
        # En error de red, asumir activo para no bloquear por fallo transitorio
        activo = True
    session["_activo_check"] = {"user_id": user_id, "ts": time(), "activo": activo}
    return activo


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
                    clientes_ids = session.get("_clientes_ids", [])
                    if not clientes_ids:
                        empresa_id = session.get("_empresa_id")
                        if empresa_id:
                            clientes_ids = [empresa_id]
                    if clientes_ids:
                        cliente_default = min(clientes_ids)
                        session["_empresa_id"] = cliente_default
                        return redirect(url_for(
                            "cliente_dashboard_contabilidad",
                            cliente_id=cliente_default,
                        ))
                    return render_template(
                        "auth/login.html",
                        error="Sin clientes asignados. Contacta al administrador.",
                    )
                if user and user["rol"] == ROL_USUARIO_AVANZADO:
                    empresa_id = session.get("_empresa_id")
                    if empresa_id:
                        return redirect(url_for("clientes.ficha", cliente_id=empresa_id))
                    return render_template(
                        "auth/login.html",
                        error="Sin cliente asignado. Contacta al administrador.",
                    )
                if user and user["rol"] == ROL_ADMIN:
                    empresa_id = session.get("_empresa_id")
                    if empresa_id:
                        return redirect(url_for("clientes.ficha", cliente_id=empresa_id))
                raw_next = request.args.get("next", "")
                if _es_url_segura(raw_next):
                    return redirect(raw_next)
                last_id = request.cookies.get("last_cliente_id", "").strip()
                if last_id and last_id.isdigit():
                    fallback = url_for("clientes.ficha", cliente_id=int(last_id))
                else:
                    fallback = url_for("clientes.listado")
                return redirect(fallback)

    return render_template("auth/login.html", error=error)


def _handle_login(email: str, password: str, remember: bool) -> str | None:
    """Intenta autenticar con Supabase. Retorna mensaje de error o None si OK."""
    from storage.repository import registrar_login_audit
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:500]

    sb = _get_supabase()
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        msg = str(exc).lower()
        if "invalid" in msg or "credentials" in msg or "email" in msg:
            registrar_login_audit(None, email, False, ip, user_agent, "invalid_credentials")
            return "Correo o contraseña incorrectos."
        logger.error("Error en sign_in_with_password para %s: %s", email, exc)
        registrar_login_audit(None, email, False, ip, user_agent, "other")
        return f"Error sign_in: {exc}"

    if not res or not res.session:
        registrar_login_audit(None, email, False, ip, user_agent, "invalid_credentials")
        return "Correo o contraseña incorrectos."

    user_id = res.user.id
    access_token = res.session.access_token

    # sign_in_with_password dispara _listen_to_auth_events(SIGNED_IN), que muta
    # sb.auth._headers["Authorization"] con el JWT del usuario (no service_role).
    # Esto contamina auth.admin.* para todas las peticiones siguientes del mismo proceso.
    # Resetear tanto postgrest como auth._headers al service_role key.
    import os
    try:
        service_key = os.environ["SUPABASE_KEY"]
        sb.auth._headers["Authorization"] = f"Bearer {service_key}"
        sb.postgrest.auth(service_key)
    except Exception:
        pass

    profile = _get_user_profile(user_id)
    if profile is None:
        logger.warning("Perfil no encontrado: user_id=%s", user_id)
        registrar_login_audit(user_id, email, False, ip, user_agent, "user_not_found")
        return "Tu cuenta no tiene perfil de acceso. Contacta al administrador."

    if not profile.get("activo", True):
        registrar_login_audit(user_id, email, False, ip, user_agent, "user_inactive")
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
        nombre=profile.get("nombre"),
        apellido=profile.get("apellido"),
    )
    registrar_login_audit(user_id, email, True, ip, user_agent, None)
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
    response = make_response(redirect(url_for("auth.login")))
    response.delete_cookie(
        "last_cliente_id",
        path="/",
        samesite="Lax",
        secure=not current_app.debug,
        httponly=True,
    )
    return response


# ── Inicialización ────────────────────────────────────────────────────────────

def init_auth(app):
    """Registra el blueprint de autenticación y configura la sesión."""
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(days=30))
    app.register_blueprint(auth_bp)
