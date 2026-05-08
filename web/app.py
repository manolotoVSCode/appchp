# web/app.py
from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from storage.repository import get_all_cfe_invoices, get_all_gas_invoices
from cli.main import procesar_factura_cfe, procesar_factura_gas
from calc.cogen import calcular_cogen
from calc.historico import calcular_historico_cfe, calcular_tablas_cfe
from calc.nombre_canonico import generar_nombre_canonico
from calc.periodo import mes_asociado, UMBRAL_PRORRATEO_DIAS
from models.cogen_result import CoGenParams

logger = logging.getLogger(__name__)
csrf = CSRFProtect()


def _cargar_datos():
    """Carga facturas desde Supabase, calcula cogeneración y prepara listas para el template."""
    cfe_invoices = get_all_cfe_invoices()
    gas_invoices = get_all_gas_invoices()
    resultado = calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())
    historico = calcular_historico_cfe(cfe_invoices)
    tablas = calcular_tablas_cfe(cfe_invoices)

    facturas_cfe = [
        {
            "nombre_canonico": generar_nombre_canonico(inv),
            "periodo": f"{inv.periodo_inicio.strftime('%d %b %Y')} – {inv.periodo_fin.strftime('%d %b %Y')}",
            "mes_asociado": date(*mes_asociado(inv.periodo_inicio, inv.periodo_fin), 1).strftime("%b %Y"),
            "kwh_total": float(sum(p.consumo_kwh for p in inv.periodos)),
            "costo_mxn": float(inv.subtotal_mxn),
            "prorrateado": (inv.periodo_fin - inv.periodo_inicio).days < UMBRAL_PRORRATEO_DIAS,
        }
        for inv in sorted(cfe_invoices, key=lambda x: x.periodo_inicio)
    ]

    facturas_gas = [
        {
            "nombre_canonico": generar_nombre_canonico(inv),
            "periodo": f"{inv.periodo_inicio.strftime('%d %b %Y')} – {inv.periodo_fin.strftime('%d %b %Y')}",
            "mes_asociado": date(*mes_asociado(inv.periodo_inicio, inv.periodo_fin), 1).strftime("%b %Y"),
            "gj_total": float(inv.consumo_total_gj),
            "costo_mxn": float(inv.subtotal_mxn),
            "prorrateado": (inv.periodo_fin - inv.periodo_inicio).days < UMBRAL_PRORRATEO_DIAS,
        }
        for inv in sorted(gas_invoices, key=lambda x: x.periodo_inicio)
    ]

    return resultado, facturas_cfe, facturas_gas, historico, tablas


def _detect_tipo(pdf_path: Path) -> str:
    """Return 'cfe' or 'gas' by scanning the first page text."""
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


def create_app() -> Flask:
    """Flask app factory."""

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32))

    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = not app.debug
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = not app.debug
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    app.config["RESULTADO"] = None
    app.config["FACTURAS_CFE"] = []
    app.config["FACTURAS_GAS"] = []
    app.config["HISTORICO"] = {}
    app.config["TABLAS"] = {}

    # Autenticación, CSRF y blueprint de clientes
    from web.auth import init_auth
    from web.clientes import clientes_bp
    init_auth(app)
    csrf.init_app(app)
    app.register_blueprint(clientes_bp)

    # Rutas exentas de autenticación
    _PUBLIC = {"/login", "/healthz"}

    @app.before_request
    def _require_login():
        if request.path in _PUBLIC or request.path.startswith("/static"):
            return None
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))

    @app.route("/")
    def dashboard():
        """Redirige al listado de clientes. '/' ya no es el dashboard."""
        return redirect(url_for("clientes.listado"))

    @app.route("/clientes/<int:cliente_id>/dashboard")
    def cliente_dashboard(cliente_id: int):
        """Dashboard de cogeneración. En esta fase carga todos los datos del sistema."""
        from storage.repository import get_cliente_con_conteos
        from flask import flash

        # Validar que el cliente existe
        cliente = get_cliente_con_conteos(cliente_id)
        if cliente is None:
            flash("El cliente solicitado no existe.", "warning")
            return redirect(url_for("clientes.listado"))

        if app.config["RESULTADO"] is None:
            try:
                r, fcfe, fgas, hist, tablas = _cargar_datos()
                app.config["RESULTADO"] = r
                app.config["FACTURAS_CFE"] = fcfe
                app.config["FACTURAS_GAS"] = fgas
                app.config["HISTORICO"] = hist
                app.config["TABLAS"] = tablas
            except Exception as e:
                import traceback
                traceback.print_exc()
                return (
                    "<html><head><title>Error</title></head>"
                    "<body style='font-family:sans-serif;padding:2rem'>"
                    f"<h2>&#9888; Error al cargar datos</h2>"
                    f"<pre>{e}</pre>"
                    "</body></html>",
                    500,
                )

        r = app.config["RESULTADO"]
        sin_datos = not r.meses

        chart_labels = [m.periodo_inicio.strftime("%b %Y") for m in r.meses]
        chart_ebitda = [float(m.ebitda_mes_mxn) for m in r.meses]
        chart_ahorro_elec = [float(m.ahorro_electricidad_mxn) for m in r.meses]
        chart_ahorro_caldera = [float(m.ahorro_caldera_mxn) for m in r.meses]
        chart_costo_gas = [float(m.costo_gas_cogen_mxn) for m in r.meses]
        meses_raw = [
            {
                "periodo": m.periodo_inicio.strftime("%b %Y"),
                "kwh_total": float(m.kwh_total),
                "costo_cfe_mxn": float(m.costo_cfe_mxn),
                "costo_promedio_kwh": float(m.costo_promedio_kwh),
                "gj_consumido": float(m.gj_consumido),
                "costo_unitario_gj": float(m.costo_unitario_gj),
                "costo_gas_actual_mxn": float(m.costo_gas_actual_mxn),
            }
            for m in r.meses
        ]
        return render_template(
            "dashboard.html",
            r=r,
            sin_datos=sin_datos,
            cliente_id=cliente_id,
            cliente_nombre=cliente["nombre"],
            chart_labels=chart_labels,
            chart_ebitda=chart_ebitda,
            chart_ahorro_elec=chart_ahorro_elec,
            chart_ahorro_caldera=chart_ahorro_caldera,
            chart_costo_gas=chart_costo_gas,
            meses_raw=meses_raw,
            facturas_cfe=app.config["FACTURAS_CFE"],
            facturas_gas=app.config["FACTURAS_GAS"],
            historico=app.config["HISTORICO"],
            tablas=app.config["TABLAS"],
        )

    @app.route("/export/excel")
    def export_excel():
        import tempfile
        from reports.excel import generar_excel
        r = app.config["RESULTADO"]
        if r is None:
            return "Datos no listos aún", 503
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmp_path = Path(f.name)
        generar_excel(r, tmp_path)
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name="analisis_cogen.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/upload", methods=["POST"])
    def upload_facturas():
        import tempfile
        from flask import jsonify

        files = request.files.getlist("facturas")
        if not files:
            return jsonify({"procesados": 0, "errores": [{"nombre": "", "error": "No se enviaron archivos"}]}), 400

        logger.info("Upload recibido: %d archivo(s)", len(files))

        ok_count = 0
        exitosos = []
        errors = []

        for f in files:
            nombre = f.filename or "<sin nombre>"
            suffix = Path(f.filename).suffix.lower() if (f.filename and Path(f.filename).suffix) else ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                f.save(tmp.name)
                tmp_path = Path(tmp.name)
            try:
                tipo = _detect_tipo(tmp_path)
                logger.info("Procesando: '%s' (tipo=%s)", nombre, tipo)
                if tipo == "cfe":
                    factura_id, nombre_canonico = procesar_factura_cfe(tmp_path)
                else:
                    factura_id, nombre_canonico = procesar_factura_gas(tmp_path)
                logger.info("Factura guardada: '%s' → id=%d (tipo=%s)", nombre, factura_id, tipo)
                ok_count += 1
                exitosos.append({"nombre_original": nombre, "nombre_canonico": nombre_canonico})
            except Exception as e:
                logger.error(
                    "Error procesando '%s': %s: %s",
                    nombre, type(e).__name__, e,
                    exc_info=True,
                )
                errors.append({"nombre": nombre, "error": str(e)})
            finally:
                tmp_path.unlink(missing_ok=True)

        if ok_count > 0:
            r, fcfe, fgas, hist, tablas = _cargar_datos()
            app.config["RESULTADO"] = r
            app.config["FACTURAS_CFE"] = fcfe
            app.config["FACTURAS_GAS"] = fgas
            app.config["HISTORICO"] = hist
            app.config["TABLAS"] = tablas

        return jsonify({"procesados": ok_count, "exitosos": exitosos, "errores": errors})

    return app
