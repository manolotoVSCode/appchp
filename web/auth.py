# web/auth.py
from __future__ import annotations

import os
import urllib.parse

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

auth_bp = Blueprint("auth", __name__)
login_manager = LoginManager()


class _SingleUser(UserMixin):
    """Único usuario de la aplicación, definido por variables de entorno."""

    id = "operator"

    def get_id(self) -> str:
        return self.id


_USER = _SingleUser()


def _credenciales_validas(username: str, password: str) -> bool:
    app_user = os.environ.get("APP_USER", "")
    app_hash = os.environ.get("APP_PASSWORD_HASH", "")
    if not app_user or not app_hash:
        return False
    if username != app_user:
        return False
    try:
        return check_password_hash(app_hash, password)
    except Exception:
        return False


@login_manager.user_loader
def _load_user(user_id: str) -> _SingleUser | None:
    if user_id == _USER.id:
        return _USER
    return None


def _es_url_segura(url: str) -> bool:
    """Retorna True solo si la URL es relativa a este sitio (sin scheme ni host)."""
    if not url or not url.startswith("/") or url.startswith("//"):
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "" and parsed.netloc == ""


@login_manager.unauthorized_handler
def _unauthorized():
    return redirect(url_for("auth.login", next=request.path))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    from flask_wtf.csrf import generate_csrf  # noqa: F401 — activa el token en el contexto

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if _credenciales_validas(username, password):
            login_user(_USER, remember=True)
            raw_next = request.args.get("next", "")
            next_url = raw_next if _es_url_segura(raw_next) else url_for("dashboard")
            return redirect(next_url)
        error = "Credenciales incorrectas. Verifica usuario y contraseña."

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


def _validar_config_auth() -> None:
    """Falla al arranque si las variables de autenticación no están configuradas."""
    faltantes = []
    if not os.environ.get("APP_USER"):
        faltantes.append(
            "APP_USER no está configurada.\n"
            "  Agrega la variable de entorno APP_USER con el nombre de usuario del operador."
        )
    if not os.environ.get("APP_PASSWORD_HASH"):
        faltantes.append(
            "APP_PASSWORD_HASH no está configurada.\n"
            "  Genera el hash con:\n"
            "    python3 -c \"from werkzeug.security import generate_password_hash; "
            "print(generate_password_hash('tu_password', method='pbkdf2:sha256'))\"\n"
            "  Y agrégala como variable de entorno en el servidor."
        )
    if faltantes:
        raise RuntimeError(
            "La aplicación no puede arrancar: configuración de autenticación incompleta.\n\n"
            + "\n\n".join(faltantes)
        )


def init_auth(app):
    """Registra blueprint, LoginManager y configura cookies de sesión."""
    _validar_config_auth()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    app.register_blueprint(auth_bp)
