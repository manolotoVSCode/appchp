# web/app.py
from __future__ import annotations

import io
import sqlite3
import threading
from contextlib import redirect_stdout
from pathlib import Path

from flask import Flask, render_template, send_file

from storage.schema import init_db
from cli.main import procesar_factura_cfe, procesar_factura_gas
from calc.cogen import calcular_cogen
from models.cogen_result import CoGenParams


def _cargar_resultado(invoices_dir: Path, db_path: Path | None = None):
    """Carga CoGenResultado desde DB existente o parseando PDFs.

    Si db_path apunta a un archivo existente, lo usa directamente.
    Si db_path se da pero no existe, parsea los PDFs y guarda en db_path.
    Si db_path es None, parsea en memoria.
    """
    if db_path and db_path.exists():
        # Carga rápida: DB ya construida
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        # Primera vez: parsear PDFs
        target = str(db_path) if db_path else ":memory:"
        conn = sqlite3.connect(target)
        conn.execute("PRAGMA foreign_keys = ON")
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


def create_app(
    invoices_dir: str | Path = "invoices",
    db_path: str | Path | None = None,
) -> Flask:
    """Flask app factory. Puerto abre de inmediato; PDFs cargan en segundo plano."""
    app = Flask(__name__)
    app.config["RESULTADO"] = None
    app.config["CARGANDO"] = True

    _invoices = Path(invoices_dir)
    _db = Path(db_path) if db_path else None

    def _cargar_en_segundo_plano():
        app.config["RESULTADO"] = _cargar_resultado(_invoices, _db)
        app.config["CARGANDO"] = False
        src = f"DB: {_db}" if (_db and _db.exists()) else f"PDFs: {_invoices}"
        print(f"✓ Facturas cargadas ({src}) — dashboard listo")

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

    return app
