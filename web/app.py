# web/app.py
from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect

from storage.repository import (
    get_facturas_para_dashboard,
    get_contratos_por_cliente,
    get_configuracion,
    get_configuracion_row,
    list_configuracion,
    set_configuracion,
)
from calc.cogen import calcular_cogen, calcular_payback, calcular_flujo_acumulado
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


def _calcular_periodo_label(cfe_invoices, gas_invoices) -> str:
    """Retorna etiqueta del periodo cubierto por las facturas seleccionadas."""
    anios: set[int] = set()
    for inv in cfe_invoices:
        anio, _ = mes_asociado(inv.periodo_inicio, inv.periodo_fin)
        anios.add(anio)
    for inv in gas_invoices:
        anio, _ = mes_asociado(inv.periodo_inicio, inv.periodo_fin)
        anios.add(anio)
    if not anios:
        return ""
    ordenados = sorted(anios)
    if len(ordenados) == 1:
        return str(ordenados[0])
    if len(ordenados) == 2 and ordenados[1] == ordenados[0] + 1:
        return f"{ordenados[0]}–{ordenados[1]}"
    return "Múltiples años"


def _cargar_facturas_seleccionadas(cliente_id: int):
    """Carga facturas CFE y gas seleccionadas del cliente y las formatea para templates.

    Retorna (cfe_invoices, gas_invoices, facturas_cfe, facturas_gas).
    Usa get_facturas_para_dashboard para compartir la query de meses seleccionados (4 queries en total).
    """
    cfe_invoices, gas_invoices = get_facturas_para_dashboard(cliente_id)

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


def _serial(obj):
    """Convierte Decimal/date recursivamente a tipos JSON-safe."""
    from decimal import Decimal
    from datetime import date as _date
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, _date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serial(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serial(v) for v in obj]
    return obj


def _calcular_queso(tablas: dict) -> dict | None:
    """Calcula datos para gráfica de composición de costo (pie chart) a partir de tablas CFE."""
    filas_mes = [f for f in tablas.get("costos_detallados", []) if f.get("mes") != "ANUAL"]
    if not filas_mes:
        return None
    tot_e = sum(f["ce_total"] for f in filas_mes)
    tot_d = sum(f["costo_dem"] for f in filas_mes)
    tot_s = sum(f["subtotal"] for f in filas_mes)
    return {
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


def _cels_to_dict(cels) -> dict | None:
    """Convierte CELsResultado a dict JSON-safe. None si cels es None."""
    if cels is None:
        return None
    return _serial({
        "es_eficiente": cels.es_eficiente,
        "cels_mwh_anual": cels.cels_mwh_anual,
        "capacidad_kw": cels.capacidad_kw,
        "capacidad_es_estimada": cels.capacidad_es_estimada,
        "medio_termico": cels.medio_termico,
        "nivel_tension_kv": cels.nivel_tension_kv,
        "altitud_msnm": cels.altitud_msnm,
        "tipo_motor": cels.tipo_motor,
        "E_mwh": cels.E_mwh,
        "F_mwh": cels.F_mwh,
        "H_mwh": cels.H_mwh,
        "RefE": cels.RefE,
        "RefH": cels.RefH,
        "fp": cels.fp,
        "RefE_prima": cels.RefE_prima,
        "Fh": cels.Fh,
        "Fe": cels.Fe,
        "EE": cels.EE,
        "EP": cels.EP,
        "AEP": cels.AEP,
        "APEP": cels.APEP,
        "AREL": cels.AREL,
        "ELC": cels.ELC,
        "porcentaje_ELC": cels.porcentaje_ELC,
    })


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
        from time import time
        from storage.repository import get_cliente_con_conteos as _get_cliente
        id_ = session.get("cliente_activo_id")
        if not id_:
            return {"cliente_activo": None, "app_version": _APP_VERSION}

        # Usar valor cacheado si es fresco (TTL 60s) y corresponde al mismo cliente
        cached = session.get("_cp_cache")
        if (cached and cached.get("id") == id_
                and time() - cached.get("ts", 0) < 60):
            return {"cliente_activo": cached["data"], "app_version": _APP_VERSION}

        # Cache miss: consultar BD
        cliente = _get_cliente(id_)
        if cliente is None:
            session.pop("cliente_activo_id", None)
            session.pop("cliente_activo_nombre", None)
            session.pop("cliente_activo_logo_url", None)
            session.pop("_cp_cache", None)
            return {"cliente_activo": None, "app_version": _APP_VERSION}
        contratos = get_contratos_por_cliente(id_)
        data = {
            "id": id_,
            "nombre": cliente["nombre"],
            "contratos": contratos,
            "logo_url": cliente.get("logo_url"),
        }
        session["_cp_cache"] = {"id": id_, "ts": time(), "data": data}
        return {"cliente_activo": data, "app_version": _APP_VERSION}

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
            queso = _calcular_queso(tablas)
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
        periodo_label = _calcular_periodo_label(cfe_invoices, gas_invoices)

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
            periodo_label=periodo_label,
        )

    @app.route("/clientes/<int:cliente_id>/dashboard/cogeneracion")
    def cliente_dashboard_cogeneracion(cliente_id: int):
        """Vista de Proyecto Cogeneración: análisis de oportunidad de cogeneración."""
        cliente, err = _verificar_cliente_activo(cliente_id)
        if err:
            return err

        try:
            from decimal import Decimal as _D
            cfe_invoices, gas_invoices, facturas_cfe, facturas_gas = _cargar_facturas_seleccionadas(cliente_id)
            _cfg = {r["clave"]: r["valor"] for r in list_configuracion()}
            tc_str = _cfg.get("tipo_cambio_mxn_usd")
            tipo_cambio = _D(tc_str) if tc_str else _D("17.50")
            fe_elec_str = _cfg.get("factor_emision_electricidad_kg_co2_kwh")
            fe_gas_str  = _cfg.get("factor_emision_gas_kg_co2_gj")
            fe_elec = _D(fe_elec_str) if fe_elec_str else None
            fe_gas  = _D(fe_gas_str)  if fe_gas_str  else None
            r = calcular_cogen(
                cfe_invoices, gas_invoices, CoGenParams(),
                tipo_cambio=tipo_cambio,
                factor_emision_elec=fe_elec,
                factor_emision_gas=fe_gas,
            )
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

        # ── CELs ─────────────────────────────────────────────────────────────────────
        try:
            from calc.cels import calcular_cels as _calcular_cels
            calor_recuperado_anual = sum(m.calor_recuperado_gj for m in r.meses)
            cels_resultado = _calcular_cels(
                kwh_cubiertos_anual=r.kwh_cubiertos_anual,
                gj_gas_cogen_pci_anual=r.gj_gas_cogen_pci_anual,
                calor_recuperado_gj_anual=calor_recuperado_anual,
                capacidad_nominal_kw=r.capacidad_nominal_kw,
                medio_termico=cliente.get("medio_termico"),
                nivel_tension_kv=cliente.get("nivel_tension_kv"),
                altitud_msnm=cliente.get("altitud_msnm"),
                tipo_motor=cliente.get("tipo_motor"),
                capacidad_instalada_kw=cliente.get("capacidad_instalada_kw"),
            )
        except Exception as _e_cels:
            import logging as _logging
            _logging.getLogger(__name__).error("Error calculando CELs: %s", _e_cels)
            cels_resultado = None

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
        chart_om = [float(m.gasto_om_mes_mxn) for m in r.meses]
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

        # Payback y flujo a 15 años (solo si hay inversión calculable)
        if r.inversion_mxn is not None and r.inversion_mxn > 0:
            payback_inicial = calcular_payback(r.inversion_mxn, r.ebitda_anual_mxn)
            flujo_acum_15 = [float(v) for v in calcular_flujo_acumulado(r.inversion_mxn, r.ebitda_anual_mxn)]
            flujo_anual_15 = [-float(r.inversion_mxn)] + [float(r.ebitda_anual_mxn)] * 15
        else:
            payback_inicial = None
            flujo_acum_15 = []
            flujo_anual_15 = []

        periodo_label = _calcular_periodo_label(cfe_invoices, gas_invoices)

        return render_template(
            "dashboard_cogeneracion.html",
            r=r,
            aviso_datos=aviso_datos,
            cliente_id=cliente_id,
            cliente_nombre=cliente["nombre"],
            logo_url=cliente.get("logo_url"),
            periodo_label=periodo_label,
            chart_labels=chart_labels,
            chart_ebitda=chart_ebitda,
            chart_ahorro_elec=chart_ahorro_elec,
            chart_ahorro_caldera=chart_ahorro_caldera,
            chart_costo_gas=chart_costo_gas,
            chart_om=chart_om,
            meses_raw=meses_raw,
            payback_inicial=payback_inicial,
            flujo_acum_15=flujo_acum_15,
            flujo_anual_15=flujo_anual_15,
            factor_emision_elec=float(fe_elec) if fe_elec is not None else None,
            factor_emision_gas=float(fe_gas)   if fe_gas  is not None else None,
            cels=cels_resultado,
            cliente_ficha_url=url_for("clientes.ficha", cliente_id=cliente_id),
        )

    # ── Endpoints JSON para dashboards (client-side rendering) ─────────────────

    @app.route("/clientes/<int:cliente_id>/dashboard/contabilidad/data")
    def cliente_dashboard_contabilidad_data(cliente_id: int):
        """JSON con todos los datos del dashboard de Contabilidad Energética."""
        from flask import jsonify
        activo_id = session.get("cliente_activo_id")
        if activo_id != cliente_id:
            return jsonify({"error": "no_autorizado"}), 403
        from storage.repository import get_cliente_con_conteos as _gcc
        cliente = _gcc(cliente_id)
        if cliente is None:
            return jsonify({"error": "no_encontrado"}), 404

        try:
            cfe_invoices, gas_invoices, facturas_cfe, facturas_gas = _cargar_facturas_seleccionadas(cliente_id)
            historico = calcular_historico_cfe(cfe_invoices)
            tablas = calcular_tablas_cfe(cfe_invoices)
            historico_gas = calcular_historico_gas(gas_invoices)
            queso = _calcular_queso(tablas)
        except Exception as _e:
            logger.exception("Error en contabilidad/data: %s", _e)
            return jsonify({"error": "error_calculo", "mensaje": str(_e)}), 500

        num_cfe_total = cliente["num_cfe"]
        num_gas_total = cliente["num_gas"]
        num_cfe_sel = len(facturas_cfe)
        num_gas_sel = len(facturas_gas)

        if num_cfe_total == 0 and num_gas_total == 0:
            aviso_datos = {"tipo": "sin_facturas", "num_cfe": 0, "num_gas": 0}
        elif num_cfe_sel == 0 and num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_seleccion"}
        elif num_cfe_sel == 0 or num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_par", "num_cfe": num_cfe_sel, "num_gas": num_gas_sel}
        else:
            aviso_datos = None

        kwh_total = sum(f["kwh_total"] for f in facturas_cfe)
        costo_total = sum(f["costo_mxn"] for f in facturas_cfe)
        costo_unit = costo_total / kwh_total if kwh_total > 0 else 0.0
        periodo_label = _calcular_periodo_label(cfe_invoices, gas_invoices)

        return jsonify({
            "estado": "ok",
            "aviso_datos": aviso_datos,
            "cliente": {"id": cliente_id, "nombre": cliente["nombre"], "periodo_label": periodo_label},
            "kpis": {
                "num_meses": len(facturas_cfe),
                "kwh_total": kwh_total,
                "costo_total": costo_total,
                "costo_unit": costo_unit,
            },
            "facturas_cfe": facturas_cfe,
            "facturas_gas": facturas_gas,
            "historico": historico,
            "tablas": tablas,
            "queso": queso,
            "historico_gas": historico_gas,
        })

    @app.route("/clientes/<int:cliente_id>/dashboard/cogeneracion/data")
    def cliente_dashboard_cogeneracion_data(cliente_id: int):
        """JSON con todos los datos del dashboard de Cogeneración."""
        from flask import jsonify
        from decimal import Decimal as _D

        activo_id = session.get("cliente_activo_id")
        if activo_id != cliente_id:
            return jsonify({"error": "no_autorizado"}), 403
        from storage.repository import get_cliente_con_conteos as _gcc
        cliente = _gcc(cliente_id)
        if cliente is None:
            return jsonify({"error": "no_encontrado"}), 404

        try:
            cfe_invoices, gas_invoices, facturas_cfe, facturas_gas = _cargar_facturas_seleccionadas(cliente_id)
            _cfg = {row["clave"]: row["valor"] for row in list_configuracion()}
            tc_str = _cfg.get("tipo_cambio_mxn_usd")
            tipo_cambio = _D(tc_str) if tc_str else _D("17.50")
            fe_elec_str = _cfg.get("factor_emision_electricidad_kg_co2_kwh")
            fe_gas_str  = _cfg.get("factor_emision_gas_kg_co2_gj")
            fe_elec = _D(fe_elec_str) if fe_elec_str else None
            fe_gas  = _D(fe_gas_str)  if fe_gas_str  else None
            r = calcular_cogen(
                cfe_invoices, gas_invoices, CoGenParams(),
                tipo_cambio=tipo_cambio,
                factor_emision_elec=fe_elec,
                factor_emision_gas=fe_gas,
            )
        except Exception as _e:
            logger.exception("Error en cogeneracion/data: %s", _e)
            return jsonify({"error": "error_calculo", "mensaje": str(_e)}), 500

        try:
            from calc.cels import calcular_cels as _calcular_cels
            calor_recuperado_anual = sum(m.calor_recuperado_gj for m in r.meses)
            cels_resultado = _calcular_cels(
                kwh_cubiertos_anual=r.kwh_cubiertos_anual,
                gj_gas_cogen_pci_anual=r.gj_gas_cogen_pci_anual,
                calor_recuperado_gj_anual=calor_recuperado_anual,
                capacidad_nominal_kw=r.capacidad_nominal_kw,
                medio_termico=cliente.get("medio_termico"),
                nivel_tension_kv=cliente.get("nivel_tension_kv"),
                altitud_msnm=cliente.get("altitud_msnm"),
                tipo_motor=cliente.get("tipo_motor"),
                capacidad_instalada_kw=cliente.get("capacidad_instalada_kw"),
            )
        except Exception as _e_cels:
            logger.error("Error calculando CELs en data endpoint: %s", _e_cels)
            cels_resultado = None

        num_cfe_total = cliente["num_cfe"]
        num_gas_total = cliente["num_gas"]
        num_cfe_sel = len(facturas_cfe)
        num_gas_sel = len(facturas_gas)

        if num_cfe_total == 0 and num_gas_total == 0:
            aviso_datos = {"tipo": "sin_facturas", "num_cfe": 0, "num_gas": 0}
        elif num_cfe_sel == 0 and num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_seleccion"}
        elif num_cfe_sel == 0 or num_gas_sel == 0:
            aviso_datos = {"tipo": "sin_par", "num_cfe": num_cfe_sel, "num_gas": num_gas_sel}
        elif not r.meses:
            aviso_datos = {"tipo": "sin_pares_mes", "num_cfe": num_cfe_sel, "num_gas": num_gas_sel}
        else:
            aviso_datos = None

        chart_labels        = [m.periodo_inicio.strftime("%b %Y") for m in r.meses]
        chart_ebitda        = [float(m.ebitda_mes_mxn)            for m in r.meses]
        chart_ahorro_elec   = [float(m.ahorro_electricidad_mxn)   for m in r.meses]
        chart_ahorro_caldera= [float(m.ahorro_caldera_mxn)        for m in r.meses]
        chart_costo_gas     = [float(m.costo_gas_cogen_mxn)       for m in r.meses]
        chart_om            = [float(m.gasto_om_mes_mxn)          for m in r.meses]

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

        tabla_mensual = [
            {
                "periodo": m.periodo_inicio.strftime("%b %Y"),
                "prorrateado": m.prorrateado,
                "nota_prorrateo": m.nota_prorrateo,
                "kwh_total": float(m.kwh_total),
                "costo_cfe_mxn": float(m.costo_cfe_mxn),
                "costo_promedio_kwh": float(m.costo_promedio_kwh),
                "gj_consumido": float(m.gj_consumido),
                "costo_unitario_gj": float(m.costo_unitario_gj),
                "costo_gas_actual_mxn": float(m.costo_gas_actual_mxn),
                "kwh_cubiertos": float(m.kwh_cubiertos),
                "gj_gas_cogen": float(m.gj_gas_cogen),
                "costo_gas_cogen_mxn": float(m.costo_gas_cogen_mxn),
                "ahorro_electricidad_mxn": float(m.ahorro_electricidad_mxn),
                "calor_recuperado_gj": float(m.calor_recuperado_gj),
                "ahorro_caldera_mxn": float(m.ahorro_caldera_mxn),
                "gasto_om_mes_mxn": float(m.gasto_om_mes_mxn),
                "ebitda_mes_mxn": float(m.ebitda_mes_mxn),
            }
            for m in r.meses
        ]

        if r.inversion_mxn is not None and r.inversion_mxn > 0:
            payback_inicial = calcular_payback(r.inversion_mxn, r.ebitda_anual_mxn)
            flujo_acum_15   = [float(v) for v in calcular_flujo_acumulado(r.inversion_mxn, r.ebitda_anual_mxn)]
            flujo_anual_15  = [-float(r.inversion_mxn)] + [float(r.ebitda_anual_mxn)] * 15
        else:
            payback_inicial = None
            flujo_acum_15   = []
            flujo_anual_15  = []

        co2 = None
        if r.co2_reduccion_kg_anual is not None:
            reduccion_t = float(r.co2_reduccion_kg_anual) / 1000
            co2 = {
                "actual_total_t": float(r.co2_actual_total_kg_anual) / 1000 if r.co2_actual_total_kg_anual else None,
                "reduccion_t": reduccion_t,
                "reduccion_pct": float(r.co2_reduccion_porcentaje) if r.co2_reduccion_porcentaje else 0.0,
                "arboles": int(reduccion_t * 50),
                "factor_emision_elec": float(fe_elec) if fe_elec else None,
                "factor_emision_gas": float(fe_gas) if fe_gas else None,
            }

        periodo_label = _calcular_periodo_label(cfe_invoices, gas_invoices)

        return jsonify({
            "estado": "ok",
            "aviso_datos": aviso_datos,
            "cliente": {"id": cliente_id, "nombre": cliente["nombre"], "periodo_label": periodo_label},
            "kpis": {
                "ahorro_electricidad_anual": float(r.ahorro_electricidad_anual_mxn),
                "ahorro_caldera_anual": float(r.ahorro_caldera_anual_mxn),
                "costo_gas_cogen_anual": float(r.costo_gas_cogen_anual_mxn),
                "gasto_om_anual": float(r.gasto_om_anual_mxn),
                "ebitda_anual": float(r.ebitda_anual_mxn),
                "kwh_total_anual": float(r.kwh_total_anual),
                "kwh_cubiertos_anual": float(r.kwh_cubiertos_anual),
                "gj_gas_cogen_anual": float(r.gj_gas_cogen_anual),
                "capacidad_nominal_kw": float(r.capacidad_nominal_kw) if r.capacidad_nominal_kw else None,
                "inversion_usd": float(r.inversion_usd) if r.inversion_usd else None,
                "inversion_mxn": float(r.inversion_mxn) if r.inversion_mxn else None,
                "tipo_cambio": float(r.tipo_cambio_mxn_usd) if r.tipo_cambio_mxn_usd else None,
            },
            "co2": co2,
            "cels": _cels_to_dict(cels_resultado),
            "chart_labels": chart_labels,
            "chart_ebitda": chart_ebitda,
            "chart_ahorro_elec": chart_ahorro_elec,
            "chart_ahorro_caldera": chart_ahorro_caldera,
            "chart_costo_gas": chart_costo_gas,
            "chart_om": chart_om,
            "meses_raw": meses_raw,
            "tabla_mensual": tabla_mensual,
            "totales": {
                "kwh_total_anual": float(r.kwh_total_anual),
                "kwh_cubiertos_anual": float(r.kwh_cubiertos_anual),
                "gj_gas_cogen_anual": float(r.gj_gas_cogen_anual),
                "costo_gas_cogen_anual_mxn": float(r.costo_gas_cogen_anual_mxn),
                "ahorro_electricidad_anual_mxn": float(r.ahorro_electricidad_anual_mxn),
                "ahorro_caldera_anual_mxn": float(r.ahorro_caldera_anual_mxn),
                "gasto_om_anual_mxn": float(r.gasto_om_anual_mxn),
                "ebitda_anual_mxn": float(r.ebitda_anual_mxn),
            },
            "payback_inicial": payback_inicial,
            "flujo_acum_15": flujo_acum_15,
            "flujo_anual_15": flujo_anual_15,
            "params": {
                "cobertura_electrica": float(r.params.cobertura_electrica),
                "rendimiento_electrico": float(r.params.rendimiento_electrico),
                "rendimiento_termico": float(r.params.rendimiento_termico),
                "eficiencia_caldera": float(r.params.eficiencia_caldera),
            },
            "cliente_ficha_url": url_for("clientes.ficha", cliente_id=cliente_id),
        })

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

    @app.route("/admin/configuracion", methods=["GET", "POST"])
    def admin_configuracion():
        """Página de configuración global del sistema."""
        from decimal import Decimal, InvalidOperation

        # Validaciones específicas por clave: (min, max)
        _RANGOS = {
            "tipo_cambio_mxn_usd":                    (Decimal("10"),  Decimal("30")),
            "factor_emision_electricidad_kg_co2_kwh": (Decimal("0.1"), Decimal("2.0")),
            "factor_emision_gas_kg_co2_gj":           (Decimal("10"),  Decimal("200")),
        }

        if request.method == "POST":
            filas = list_configuracion()
            errores = []
            nuevos_valores = {}
            for fila in filas:
                clave = fila["clave"]
                raw = request.form.get(clave, "").strip()
                try:
                    val = Decimal(raw)
                    if val <= 0:
                        raise ValueError("no positivo")
                    if clave in _RANGOS:
                        lo, hi = _RANGOS[clave]
                        if val < lo or val > hi:
                            raise ValueError("fuera de rango")
                    nuevos_valores[clave] = str(val)
                except (InvalidOperation, ValueError):
                    desc = fila.get("descripcion") or clave
                    if clave in _RANGOS:
                        lo, hi = _RANGOS[clave]
                        errores.append(f"{desc}: valor inválido (rango {lo} – {hi}).")
                    else:
                        errores.append(f"{desc}: debe ser un número positivo.")

            claves_conocidas = {fila["clave"] for fila in filas}
            for clave_form in request.form:
                if clave_form not in claves_conocidas and not clave_form.startswith("csrf"):
                    logger.warning("admin_configuracion: clave desconocida en POST: %r", clave_form)

            if errores:
                for msg in errores:
                    flash(msg, "danger")
                return redirect(url_for("admin_configuracion"))

            for clave, valor in nuevos_valores.items():
                set_configuracion(clave, valor)
            flash("Configuración guardada correctamente.", "success")
            return redirect(url_for("admin_configuracion"))

        filas = list_configuracion()
        return render_template("admin/configuracion.html", filas=filas)

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
