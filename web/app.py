# web/app.py
from __future__ import annotations

import io
import sqlite3
import threading
from contextlib import redirect_stdout
from pathlib import Path

from flask import Flask, render_template

from storage.schema import init_db
from cli.main import procesar_factura_cfe, procesar_factura_gas
from calc.cogen import calcular_cogen
from models.cogen_result import CoGenParams


def _cargar_resultado(invoices_dir: Path):
    """Parsea todos los PDFs y devuelve CoGenResultado. Suprime prints de parsers."""
    conn = sqlite3.connect(":memory:")
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

    return calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())


def create_app(invoices_dir: str | Path = "invoices") -> Flask:
    """Flask app factory. El puerto abre de inmediato; los PDFs cargan en segundo plano."""
    app = Flask(__name__)
    app.config["RESULTADO"] = None
    app.config["CARGANDO"] = True

    def _cargar_en_segundo_plano():
        app.config["RESULTADO"] = _cargar_resultado(Path(invoices_dir))
        app.config["CARGANDO"] = False
        print("✓ Facturas cargadas — dashboard listo")

    threading.Thread(target=_cargar_en_segundo_plano, daemon=True).start()

    @app.route("/")
    def dashboard():
        if app.config["CARGANDO"]:
            return (
                "<html><head><meta http-equiv='refresh' content='5'>"
                "<title>Cargando...</title></head>"
                "<body style='font-family:sans-serif;padding:2rem'>"
                "<h2>⏳ Cargando facturas...</h2>"
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
        return render_template(
            "dashboard.html",
            r=r,
            chart_labels=chart_labels,
            chart_ebitda=chart_ebitda,
            chart_ahorro_elec=chart_ahorro_elec,
            chart_ahorro_caldera=chart_ahorro_caldera,
            chart_costo_gas=chart_costo_gas,
        )

    return app
