# web/app.py
from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect

from storage.repository import get_cfe_invoices_for_dashboard, get_gas_invoices_for_dashboard, get_contratos_por_cliente
from calc.cogen import calcular_cogen
from calc.historico import calcular_historico_cfe, calcular_tablas_cfe, calcular_historico_gas
from calc.nombre_canonico import generar_nombre_canonico
from calc.periodo import mes_asociado, UMBRAL_PRORRATEO_DIAS
from models.cogen_result import CoGenParams

logger = logging.getLogger(__name__)
csrf = CSRFProtect()

try:
    _APP_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
except FileNotFoundError:
    _APP_VERSION = ""


def _verificar_cliente_activo(cliente_id: int):
    """Verifica que cliente_id coincida con la sesión activa y exista en BD.

    Retorna (cliente_dict, None) si todo está bien.
    Retorna (None, response) si hay error; el caller debe retornar esa response.
    """
    from flask import flash
    from storage.repository import get_cliente_con_conteos

    activo_id = session.get("cliente_activo_id")
    if activo_id != cliente_id:
        flash(
            "El dashboard solicitado no corresponde al cliente activo. "
            "Selecciona el cliente desde el listado.",
            "warning",
        )
        return None, redirect(url_for("clientes.listado"))

    cliente = get_cliente_con_conteos(cliente_id)
    if cliente is None:
        session.pop("cliente_activo_id", None)
        session.pop("cliente_activo_nombre", None)
        flash("El cliente ya no existe.", "warning")
        return None, redirect(url_for("clientes.listado"))

    return cliente, None


def _cargar_facturas_seleccionadas(cliente_id: int):
    """Carga facturas CFE y gas seleccionadas del cliente y las formatea para templates.

    Retorna (cfe_invoices, gas_invoices, facturas_cfe, facturas_gas).
    """
    cfe_invoices = get_cfe_invoices_for_dashboard(cliente_id)
    gas_invoices = get_gas_invoices_for_dashboard(cliente_id)

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

    return cfe_invoices, gas_invoices, facturas_cfe, facturas_gas


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

    @app.context_processor
    def _inject_globals():
        from storage.repository import get_cliente_con_conteos as _get_cliente
        id_ = session.get("cliente_activo_id")
        if not id_:
            return {"cliente_activo": None, "app_version": _APP_VERSION}
        # Verifica que el cliente sigue existiendo en BD; limpia sesión si fue borrado
        cliente = _get_cliente(id_)
        if cliente is None:
            session.pop("cliente_activo_id", None)
            session.pop("cliente_activo_nombre", None)
            session.pop("cliente_activo_logo_url", None)
            return {"cliente_activo": None, "app_version": _APP_VERSION}
        contratos = get_contratos_por_cliente(id_)
        return {
            "cliente_activo": {
                "id": id_,
                "nombre": cliente["nombre"],
                "contratos": contratos,
                "logo_url": cliente.get("logo_url"),
            },
            "app_version": _APP_VERSION,
        }

    @app.route("/")
    def dashboard():
        """Redirige al listado de clientes."""
        return redirect(url_for("clientes.listado"))

    @app.route("/clientes/<int:cliente_id>/dashboard")
    def cliente_dashboard(cliente_id: int):
        """Redirige a Contabilidad Energética (primera vista del análisis del cliente)."""
        return redirect(url_for("cliente_dashboard_contabilidad", cliente_id=cliente_id))

    @app.route("/clientes/<int:cliente_id>/dashboard/contabilidad")
    def cliente_dashboard_contabilidad(cliente_id: int):
        """Vista de Contabilidad Energética: histórico eléctrico del cliente."""
        cliente, err = _verificar_cliente_activo(cliente_id)
        if err:
            return err

        try:
            cfe_invoices, gas_invoices, facturas_cfe, facturas_gas = _cargar_facturas_seleccionadas(cliente_id)
            historico = calcular_historico_cfe(cfe_invoices)
            tablas = calcular_tablas_cfe(cfe_invoices)
            # Datos para gráfica de composición del costo (pie chart)
            queso = None
            filas_mes = [f for f in tablas.get("costos_detallados", []) if f.get("mes") != "ANUAL"]
            if filas_mes:
                tot_e = sum(f["ce_total"] for f in filas_mes)
                tot_d = sum(f["costo_dem"] for f in filas_mes)
                tot_s = sum(f["subtotal"] for f in filas_mes)
                queso = {
                    "agregado": {
                        "energia": tot_e,
                        "demanda": tot_d,
                        "otros": max(0.0, tot_s - tot_e - tot_d),
                        "total": tot_s,
                    },
                    "por_mes": [
                        {
                            "label": f["mes"],
                            "energia": f["ce_total"],
                            "demanda": f["costo_dem"],
                            "otros": max(0.0, f["subtotal"] - f["ce_total"] - f["costo_dem"]),
                            "total": f["subtotal"],
                        }
                        for f in filas_mes
                    ],
                }
            historico_gas = calcular_historico_gas(gas_invoices)
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

        num_cfe_total = cliente["num_cfe"]
        num_gas_total = cliente["num_gas"]
        num_cfe_sel = len(facturas_cfe)
        num_gas_sel = len(facturas_gas)

        if num_cfe_total == 0 and num_gas_total == 0:
            aviso_datos = {"tipo": "sin_facturas", "num_cfe": 0, "num_gas": 0, "cliente_id": cliente_id}
        elif num_cfe_sel == 0 and num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_seleccion", "cliente_id": cliente_id}
        elif num_cfe_sel == 0 or num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_par", "num_cfe": num_cfe_sel, "num_gas": num_gas_sel}
        else:
            aviso_datos = None

        kwh_total_periodo = sum(f["kwh_total"] for f in facturas_cfe)
        costo_total_periodo = sum(f["costo_mxn"] for f in facturas_cfe)
        costo_unit_promedio = costo_total_periodo / kwh_total_periodo if kwh_total_periodo > 0 else 0.0

        return render_template(
            "dashboard_contabilidad.html",
            aviso_datos=aviso_datos,
            cliente_id=cliente_id,
            cliente_nombre=cliente["nombre"],
            logo_url=cliente.get("logo_url"),
            facturas_cfe=facturas_cfe,
            facturas_gas=facturas_gas,
            historico=historico,
            tablas=tablas,
            historico_gas=historico_gas,
            queso=queso,
            num_meses_analizados=len(facturas_cfe),
            kwh_total_periodo=kwh_total_periodo,
            costo_total_periodo=costo_total_periodo,
            costo_unit_promedio=costo_unit_promedio,
        )

    @app.route("/clientes/<int:cliente_id>/dashboard/cogeneracion")
    def cliente_dashboard_cogeneracion(cliente_id: int):
        """Vista de Proyecto Cogeneración: análisis de oportunidad de cogeneración."""
        cliente, err = _verificar_cliente_activo(cliente_id)
        if err:
            return err

        try:
            cfe_invoices, gas_invoices, facturas_cfe, facturas_gas = _cargar_facturas_seleccionadas(cliente_id)
            r = calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())
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

        num_cfe_total = cliente["num_cfe"]
        num_gas_total = cliente["num_gas"]
        num_cfe_sel = len(facturas_cfe)
        num_gas_sel = len(facturas_gas)

        if num_cfe_total == 0 and num_gas_total == 0:
            aviso_datos = {"tipo": "sin_facturas", "num_cfe": 0, "num_gas": 0, "cliente_id": cliente_id}
        elif num_cfe_sel == 0 and num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_seleccion", "cliente_id": cliente_id}
        elif num_cfe_sel == 0 or num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_par", "num_cfe": num_cfe_sel, "num_gas": num_gas_sel}
        elif not r.meses:
            aviso_datos = {"tipo": "sin_pares_mes", "num_cfe": num_cfe_sel, "num_gas": num_gas_sel}
        else:
            aviso_datos = None

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
            "dashboard_cogeneracion.html",
            r=r,
            aviso_datos=aviso_datos,
            cliente_id=cliente_id,
            cliente_nombre=cliente["nombre"],
            logo_url=cliente.get("logo_url"),
            chart_labels=chart_labels,
            chart_ebitda=chart_ebitda,
            chart_ahorro_elec=chart_ahorro_elec,
            chart_ahorro_caldera=chart_ahorro_caldera,
            chart_costo_gas=chart_costo_gas,
            meses_raw=meses_raw,
        )

    @app.route("/export/excel")
    def export_excel():
        import tempfile
        from flask import flash
        from reports.excel import generar_excel

        activo_id = session.get("cliente_activo_id")
        if activo_id is None:
            flash("Sin cliente activo. Selecciona un cliente primero.", "warning")
            return redirect(url_for("clientes.listado"))

        cfe_invoices, gas_invoices, _, _ = _cargar_facturas_seleccionadas(activo_id)
        r = calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())
        if not r.meses:
            return "Sin datos para exportar (sin meses pareados).", 503

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmp_path = Path(f.name)
        generar_excel(r, tmp_path)
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name="analisis_cogen.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.route("/changelog")
    def changelog():
        import markdown
        changelog_path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
        try:
            md_text = changelog_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            md_text = "_Sin changelog disponible._"
        content = markdown.markdown(md_text, extensions=["nl2br"])
        return render_template("changelog.html", content=content)

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/upload", methods=["POST"])
    def upload_facturas():
        from flask import jsonify
        return jsonify({
            "error": "Este endpoint fue eliminado. Usa /clientes/<id>/contratos/<id>/upload."
        }), 410

    return app
