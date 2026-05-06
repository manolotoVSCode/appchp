# web/app.py
from __future__ import annotations

import io
import os
import threading
from contextlib import redirect_stdout
from pathlib import Path

from flask import Flask, render_template, send_file

from storage.db import get_connection
from storage.schema import init_db
from cli.main import procesar_factura_cfe, procesar_factura_gas
from calc.cogen import calcular_cogen
from models.cogen_result import CoGenParams


def _cargar_resultado(invoices_dir: Path, db_path: Path | None = None):
    """Load CoGenResultado from DB or by parsing PDFs.

    Production (DATABASE_URL set): connect to PostgreSQL, skip PDF parsing.
    Local with db_path: use that SQLite file.
    Local without db_path: use :memory: SQLite and parse PDFs.
    """
    db_url = os.environ.get("DATABASE_URL", "")

    if db_url:
        # Production: Supabase PostgreSQL — data already in DB from uploads
        conn = get_connection()
    elif db_path and db_path.exists():
        # Local fast-load from existing SQLite file
        conn = get_connection(str(db_path))
    else:
        # Local: parse PDFs and store in SQLite (file or memory)
        target = str(db_path) if db_path else None
        conn = get_connection(target)
        init_db(conn)

        buf = io.StringIO()
        with redirect_stdout(buf):
            for pdf in sorted(invoices_dir.glob("CFE/*.pdf")):
                try:
                    procesar_factura_cfe(pdf, conn)
                except Exception:
                    pass
            for pdf in sorted(invoices_dir.glob("Gas/*.pdf")):
                try:
                    procesar_factura_gas(pdf, conn)
                except Exception:
                    pass

    from storage.repository import (
        list_cfe_invoices, load_cfe_invoice,
        list_gas_invoices, load_gas_invoice,
    )
    cfe_rows = list_cfe_invoices(conn)
    cfe_invoices = [load_cfe_invoice(conn, r["id"]) for r in cfe_rows]
    gas_rows = list_gas_invoices(conn)
    gas_invoices = [load_gas_invoice(conn, r["id"]) for r in gas_rows]
    conn.close()

    return calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())


def _refresh_resultado(app: Flask) -> None:
    """Reload analysis from DB and update app.config. Called after uploads."""
    db_path_str = app.config.get("DB_PATH")
    db_path = Path(db_path_str) if db_path_str else None
    invoices_dir = Path(app.config.get("INVOICES_DIR", "invoices"))
    app.config["RESULTADO"] = _cargar_resultado(invoices_dir, db_path)


def create_app(
    invoices_dir: str | Path = "invoices",
    db_path: str | Path | None = None,
) -> Flask:
    """Flask app factory. Port opens immediately; data loads in background."""
    app = Flask(__name__)
    app.config["RESULTADO"] = None
    app.config["CARGANDO"] = True
    app.config["DB_PATH"] = str(db_path) if db_path else None
    app.config["INVOICES_DIR"] = str(invoices_dir)

    _invoices = Path(invoices_dir)
    _db = Path(db_path) if db_path else None

    def _cargar_en_segundo_plano():
        app.config["RESULTADO"] = _cargar_resultado(_invoices, _db)
        app.config["CARGANDO"] = False
        src = os.environ.get("DATABASE_URL", "") or (str(_db) if _db else str(_invoices))
        print(f"✓ Datos cargados ({src}) — dashboard listo")

    threading.Thread(target=_cargar_en_segundo_plano, daemon=True).start()

    @app.route("/")
    def dashboard():
        if app.config["CARGANDO"]:
            return (
                "<html><head><meta http-equiv='refresh' content='5'>"
                "<title>Cargando...</title></head>"
                "<body style='font-family:sans-serif;padding:2rem'>"
                "<h2>&#9203; Cargando facturas...</h2>"
                "<p>Esta página se actualiza automáticamente cada 5 segundos.</p>"
                "</body></html>",
                503,
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
        if "ENGIE" in text or "GAS NATURAL" in text or "GAS" in text:
            return "gas"
        raise ValueError("No se pudo determinar el tipo de factura (CFE o Gas)")

    @app.route("/upload", methods=["POST"])
    def upload_facturas():
        import tempfile
        from flask import jsonify, request

        files = request.files.getlist("facturas")
        if not files:
            return jsonify({"procesados": 0, "errores": [{"nombre": "", "error": "No se enviaron archivos"}]}), 400

        db_path_str = app.config.get("DB_PATH")
        db_path_val = Path(db_path_str) if db_path_str else None

        conn = get_connection(str(db_path_val) if db_path_val else None)
        init_db(conn)

        ok_count = 0
        errors = []

        for f in files:
            suffix = Path(f.filename).suffix.lower() if f.filename else ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                f.save(tmp.name)
                tmp_path = Path(tmp.name)
            try:
                tipo = _detect_tipo(tmp_path)
                if tipo == "cfe":
                    procesar_factura_cfe(tmp_path, conn)
                else:
                    procesar_factura_gas(tmp_path, conn)
                ok_count += 1
            except Exception as e:
                errors.append({"nombre": f.filename or "", "error": str(e)})
            finally:
                tmp_path.unlink(missing_ok=True)

        conn.close()
        _refresh_resultado(app)

        return jsonify({"procesados": ok_count, "errores": errors})

    return app
