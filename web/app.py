# web/app.py
from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Flask, render_template, send_file

from storage.repository import get_all_cfe_invoices, get_all_gas_invoices
from cli.main import procesar_factura_cfe, procesar_factura_gas
from calc.cogen import calcular_cogen
from calc.historico import calcular_historico_cfe
from calc.periodo import mes_asociado, UMBRAL_PRORRATEO_DIAS
from models.cogen_result import CoGenParams


def _cargar_datos():
    """Carga facturas desde Supabase, calcula cogeneración y prepara listas para el template."""
    cfe_invoices = get_all_cfe_invoices()
    gas_invoices = get_all_gas_invoices()
    resultado = calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())
    historico = calcular_historico_cfe(cfe_invoices)

    facturas_cfe = [
        {
            "periodo": f"{inv.periodo_inicio.strftime('%d %b %Y')} – {inv.periodo_fin.strftime('%d %b %Y')}",
            "mes_asociado": date(*mes_asociado(inv.periodo_inicio, inv.periodo_fin), 1).strftime("%b %Y"),
            "kwh_total": float(sum(p.consumo_kwh for p in inv.periodos)),
            "costo_mxn": float(inv.facturacion_periodo_mxn),
            "prorrateado": (inv.periodo_fin - inv.periodo_inicio).days < UMBRAL_PRORRATEO_DIAS,
        }
        for inv in sorted(cfe_invoices, key=lambda x: x.periodo_inicio)
    ]

    facturas_gas = [
        {
            "periodo": f"{inv.periodo_inicio.strftime('%d %b %Y')} – {inv.periodo_fin.strftime('%d %b %Y')}",
            "mes_asociado": date(*mes_asociado(inv.periodo_inicio, inv.periodo_fin), 1).strftime("%b %Y"),
            "gj_total": float(inv.consumo_total_gj),
            "costo_mxn": float(inv.subtotal_mxn),
            "prorrateado": (inv.periodo_fin - inv.periodo_inicio).days < UMBRAL_PRORRATEO_DIAS,
        }
        for inv in sorted(gas_invoices, key=lambda x: x.periodo_inicio)
    ]

    return resultado, facturas_cfe, facturas_gas, historico


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
    """Flask app factory. Data loads on first request."""
    app = Flask(__name__)
    app.config["RESULTADO"] = None
    app.config["FACTURAS_CFE"] = []
    app.config["FACTURAS_GAS"] = []
    app.config["HISTORICO"] = {}

    @app.route("/")
    def dashboard():
        if app.config["RESULTADO"] is None:
            try:
                r, fcfe, fgas, hist = _cargar_datos()
                app.config["RESULTADO"] = r
                app.config["FACTURAS_CFE"] = fcfe
                app.config["FACTURAS_GAS"] = fgas
                app.config["HISTORICO"] = hist
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
            chart_labels=chart_labels,
            chart_ebitda=chart_ebitda,
            chart_ahorro_elec=chart_ahorro_elec,
            chart_ahorro_caldera=chart_ahorro_caldera,
            chart_costo_gas=chart_costo_gas,
            meses_raw=meses_raw,
            facturas_cfe=app.config["FACTURAS_CFE"],
            facturas_gas=app.config["FACTURAS_GAS"],
            historico=app.config["HISTORICO"],
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
        from flask import jsonify, request

        files = request.files.getlist("facturas")
        if not files:
            return jsonify({"procesados": 0, "errores": [{"nombre": "", "error": "No se enviaron archivos"}]}), 400

        ok_count = 0
        errors = []

        for f in files:
            suffix = Path(f.filename).suffix.lower() if (f.filename and Path(f.filename).suffix) else ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                f.save(tmp.name)
                tmp_path = Path(tmp.name)
            try:
                tipo = _detect_tipo(tmp_path)
                if tipo == "cfe":
                    procesar_factura_cfe(tmp_path)
                else:
                    procesar_factura_gas(tmp_path)
                ok_count += 1
            except Exception as e:
                errors.append({"nombre": f.filename or "", "error": str(e)})
            finally:
                tmp_path.unlink(missing_ok=True)

        if ok_count > 0:
            r, fcfe, fgas, hist = _cargar_datos()
            app.config["RESULTADO"] = r
            app.config["FACTURAS_CFE"] = fcfe
            app.config["FACTURAS_GAS"] = fgas
            app.config["HISTORICO"] = hist

        return jsonify({"procesados": ok_count, "errores": errors})

    return app
