# web/error_logger.py
from __future__ import annotations
import logging
import traceback as tb_module
from typing import Literal

logger = logging.getLogger(__name__)
Nivel = Literal["error_500", "error_403", "error_404", "validacion", "negocio"]


def log_error(
    nivel: Nivel,
    mensaje: str,
    exc: BaseException | None = None,
    codigo_http: int | None = None,
) -> None:
    try:
        from flask import request, has_request_context, session
        from storage.repository import _supabase
        import os

        ruta = metodo = user_agent = ip = None
        usuario_id = usuario_email = usuario_rol = None
        empresa_id = None

        if has_request_context():
            ruta = request.path
            metodo = request.method
            user_agent = request.headers.get("User-Agent", "")[:512]
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
            usuario_id = session.get("_user_id")
            usuario_email = session.get("_user_email")
            usuario_rol = session.get("_user_rol")
            raw_empresa = session.get("_empresa_id")
            if raw_empresa is not None:
                try:
                    empresa_id = int(raw_empresa)
                except (ValueError, TypeError):
                    empresa_id = None

        traceback_str = None
        if exc is not None:
            traceback_str = "".join(tb_module.format_exception(type(exc), exc, exc.__traceback__))

        payload = {
            "nivel": nivel,
            "ruta": ruta,
            "metodo": metodo,
            "codigo_http": codigo_http,
            "usuario_id": str(usuario_id) if usuario_id else None,
            "usuario_email": usuario_email,
            "usuario_rol": usuario_rol,
            "empresa_id": empresa_id,
            "mensaje": str(mensaje)[:2000],
            "traceback": traceback_str[:8000] if traceback_str else None,
            "user_agent": user_agent,
            "ip": str(ip)[:64] if ip else None,
        }

        _supabase.postgrest.auth(os.environ["SUPABASE_KEY"])
        _supabase.table("error_logs").insert(payload).execute()

    except Exception as inner:
        logger.warning("error_logger: fallo al persistir '%s': %s", mensaje, inner)
