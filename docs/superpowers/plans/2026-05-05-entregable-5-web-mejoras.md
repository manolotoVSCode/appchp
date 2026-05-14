# Entregable 5 — Mejoras Web: BD Persistente + Exportar Excel + Sensibilidad

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tres mejoras al dashboard web: (1) DB en disco para arranque rápido, (2) botón para descargar el Excel, (3) sliders de sensibilidad que recalculan el EBITDA en tiempo real en el navegador.

**Architecture:** Task 1 modifica `web/app.py` y `run_server.py` para soportar un SQLite en disco (`chpapp.db`) — si existe lo usa, si no lo crea. Task 2 añade una ruta `/export/excel` y un botón en el template. Task 3 embebe los datos mensuales como JSON en el HTML y añade sliders + JS que recalculan los valores del lado del cliente sin tocar el servidor.

**Tech Stack:** Python 3.9.6, Flask, SQLite (stdlib), openpyxl, Vanilla JS (sin dependencias adicionales)

---

## Estado actual del código relevante

- `web/app.py`: `create_app(invoices_dir)` con `_cargar_resultado(invoices_dir)` que parsea PDFs en hilo de fondo
- `run_server.py`: arranca Flask en `host:port` con `--invoices` y `--port` args
- `storage/schema.py`: `init_db(conn)` — crea todas las tablas
- `storage/repository.py`: `save_cfe_invoice`, `save_gas_invoice`, `list_cfe_invoices`, `load_cfe_invoice`, `list_gas_invoices`, `load_gas_invoice`
- `cli/main.py`: `procesar_factura_cfe(pdf, conn)`, `procesar_factura_gas(pdf, conn)`
- `reports/excel.py`: `generar_excel(resultado, output_path) -> Path`
- `models/cogen_result.py`: `CoGenResultado`, `CoGenMes`, `CoGenParams`

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|-----------------|
| `web/app.py` | Modificar | `_cargar_resultado(invoices_dir, db_path)` con soporte DB + ruta `/export/excel` |
| `web/templates/dashboard.html` | Modificar | Botón exportar + sliders + JS de sensibilidad |
| `run_server.py` | Modificar | Agregar `--db` arg |
| `tests/test_web.py` | Modificar | Tests para export y sliders |

---

## Task 1: BD persistente — arranque en 2 segundos

**Files:**
- Modify: `web/app.py`
- Modify: `run_server.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Escribir tests fallidos**

Agregar al final de `/Users/manoloto/Apps/chpapp/tests/test_web.py`:

```python
def test_carga_desde_db_existente(tmp_path):
    """Si existe chpapp.db, la app carga desde él sin parsear PDFs."""
    import sqlite3
    import time
    from storage.schema import init_db
    from cli.main import procesar_factura_cfe, procesar_factura_gas

    # Construir un DB mínimo con 1 factura CFE + 1 gas
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    procesar_factura_cfe(Path("invoices/CFE/P2 2023_11 NOVIEMBRE.pdf"), conn)
    procesar_factura_gas(Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf"), conn)
    conn.close()

    # Crear app con db_path — debe cargar rápido (no parsea PDFs)
    app = create_app("invoices", db_path=str(db_file))
    app.config["TESTING"] = True
    while app.config.get("CARGANDO", False):
        time.sleep(0.1)

    with app.test_client() as c:
        resp = c.get("/")
    assert resp.status_code == 200
    assert resp.data.count(b"mes-row") == 1
```

Y agregar `from pathlib import Path` al bloque de imports de `tests/test_web.py`.

- [ ] **Step 2: Verificar que falla**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py::test_carga_desde_db_existente -v 2>&1 | tail -10
```
Expected: `TypeError: create_app() got an unexpected keyword argument 'db_path'`

- [ ] **Step 3: Modificar `web/app.py`**

Reemplazar el contenido completo de `/Users/manoloto/Apps/chpapp/web/app.py`:

```python
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

    return app
```

- [ ] **Step 4: Modificar `run_server.py`**

Reemplazar el contenido completo de `/Users/manoloto/Apps/chpapp/run_server.py`:

```python
# run_server.py
"""Punto de entrada para el servidor de desarrollo.

Uso:
    python3 run_server.py                          # parsea PDFs en memoria
    python3 run_server.py --db chpapp.db           # crea/reutiliza DB en disco
    python3 run_server.py --db chpapp.db --port 8080
"""
from __future__ import annotations

import argparse
from web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard de Cogeneración")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--invoices", default="invoices", help="Directorio con PDFs")
    parser.add_argument("--db", default=None, help="Ruta SQLite (crea si no existe)")
    args = parser.parse_args()

    app = create_app(invoices_dir=args.invoices, db_path=args.db)
    msg = f"desde DB '{args.db}'" if args.db else "parseando PDFs"
    print(f"Servidor → http://{args.host}:{args.port}/  (cargando {msg}...)")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Correr el test nuevo**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py::test_carga_desde_db_existente -v
```
Expected: PASS

- [ ] **Step 6: Correr suite completa**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/ -q --tb=short
```
Expected: 126 passed

- [ ] **Step 7: Commit**

```bash
cd /Users/manoloto/Apps/chpapp && git add web/app.py run_server.py tests/test_web.py && git commit -m "feat: persistent SQLite DB support for fast server startup (Task 1)"
```

---

## Task 2: Botón Exportar Excel

**Files:**
- Modify: `web/app.py` (ya incluye la ruta en Task 1 — verificar que esté)
- Modify: `web/templates/dashboard.html`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Escribir test fallido**

Agregar al final de `/Users/manoloto/Apps/chpapp/tests/test_web.py`:

```python
def test_export_excel_descarga_xlsx(client):
    resp = client.get("/export/excel")
    assert resp.status_code == 200
    assert resp.content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(resp.data) > 1000  # archivo real, no vacío


def test_dashboard_contiene_boton_exportar(client):
    resp = client.get("/")
    assert b"export/excel" in resp.data
```

- [ ] **Step 2: Verificar que fallan**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py::test_export_excel_descarga_xlsx tests/test_web.py::test_dashboard_contiene_boton_exportar -v 2>&1 | tail -10
```
Expected: `test_export_excel_descarga_xlsx` PASS (la ruta ya existe en app.py desde Task 1), `test_dashboard_contiene_boton_exportar` FAIL (el botón no está en el template aún).

- [ ] **Step 3: Agregar botón al template**

En `/Users/manoloto/Apps/chpapp/web/templates/dashboard.html`, localizar la línea del título:

```html
  <!-- Título -->
  <div class="d-flex align-items-center mb-4">
    <h1 class="h3 mb-0 me-3">&#9889; Análisis de Cogeneración</h1>
    <span class="badge bg-secondary">{{ r.meses|length }} meses pareados</span>
  </div>
```

Reemplazarla con:

```html
  <!-- Título -->
  <div class="d-flex align-items-center mb-4">
    <h1 class="h3 mb-0 me-3">&#9889; Análisis de Cogeneración</h1>
    <span class="badge bg-secondary me-2">{{ r.meses|length }} meses pareados</span>
    <a href="/export/excel" class="btn btn-sm btn-success ms-auto">
      &#8681; Exportar Excel
    </a>
  </div>
```

- [ ] **Step 4: Correr tests**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py -q --tb=short
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/manoloto/Apps/chpapp && git add web/templates/dashboard.html tests/test_web.py && git commit -m "feat: add Excel export button and /export/excel route (Task 2)"
```

---

## Task 3: Sliders de sensibilidad

**Files:**
- Modify: `web/templates/dashboard.html`
- Modify: `tests/test_web.py`

Los datos mensuales raw ya se pasan desde `web/app.py` (Task 1) como `meses_raw` — lista de dicts con `kwh_total`, `costo_promedio_kwh`, `costo_unitario_gj`, etc. El JavaScript recalcula con las mismas fórmulas de `calc/cogen.py`.

- [ ] **Step 1: Escribir test fallido**

Agregar al final de `/Users/manoloto/Apps/chpapp/tests/test_web.py`:

```python
def test_dashboard_contiene_sliders(client):
    resp = client.get("/")
    html = resp.data
    assert b'type="range"' in html        # al menos un slider
    assert b"cobertura" in html           # slider de cobertura
    assert b"meses_raw" in html           # datos raw para JS
```

- [ ] **Step 2: Verificar que falla**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py::test_dashboard_contiene_sliders -v 2>&1 | tail -5
```
Expected: FAIL

- [ ] **Step 3: Agregar sliders al template**

En `/Users/manoloto/Apps/chpapp/web/templates/dashboard.html`, insertar el bloque de sliders **entre las KPI cards y la gráfica** (después de `</div>` del `row g-3 mb-4` y antes de `<!-- Gráfica -->`):

```html
  <!-- Sliders de sensibilidad -->
  <div class="card shadow-sm mb-4">
    <div class="card-body">
      <h5 class="card-title">Análisis de sensibilidad</h5>
      <div class="row g-3">
        <div class="col-md-3">
          <label class="form-label small">
            Cobertura eléctrica: <strong id="val-cobertura">75</strong>%
          </label>
          <input type="range" class="form-range" id="cobertura"
                 min="50" max="100" step="1" value="75">
        </div>
        <div class="col-md-3">
          <label class="form-label small">
            Rendimiento eléctrico: <strong id="val-rendimiento-elec">40</strong>%
          </label>
          <input type="range" class="form-range" id="rendimiento-elec"
                 min="20" max="60" step="1" value="40">
        </div>
        <div class="col-md-3">
          <label class="form-label small">
            Rendimiento térmico: <strong id="val-rendimiento-term">25</strong>%
          </label>
          <input type="range" class="form-range" id="rendimiento-term"
                 min="5" max="45" step="1" value="25">
        </div>
        <div class="col-md-3">
          <label class="form-label small">
            Eficiencia caldera: <strong id="val-caldera">85</strong>%
          </label>
          <input type="range" class="form-range" id="caldera"
                 min="60" max="99" step="1" value="85">
        </div>
      </div>
      <div class="mt-2 small text-muted">
        EBITDA anual estimado:
        <strong class="text-success fs-5" id="ebitda-sensibilidad">—</strong>
      </div>
    </div>
  </div>
```

- [ ] **Step 4: Agregar datos raw y script de sensibilidad al template**

Al final del `<body>`, **antes** de `</body>`, insertar después del script de Chart.js existente:

```html
<script>
// ── Datos base (inmutables) ────────────────────────────────────────────────
const meses_raw = {{ meses_raw | tojson }};

// ── Recalcular con parámetros dados ───────────────────────────────────────
function recalcularMes(m, p) {
  const kwh_cub     = m.kwh_total * p.cobertura;
  const gj_cogen    = kwh_cub * 0.0036 / p.rend_elec;
  const costo_gas   = gj_cogen * m.costo_unitario_gj;
  const ah_elec     = kwh_cub * m.costo_promedio_kwh;
  const calor_rec   = gj_cogen * p.rend_term;
  const ah_caldera  = (calor_rec / p.efic_caldera) * m.costo_unitario_gj;
  return ah_elec + ah_caldera - costo_gas;
}

function leerParams() {
  return {
    cobertura:   document.getElementById("cobertura").value / 100,
    rend_elec:   document.getElementById("rendimiento-elec").value / 100,
    rend_term:   document.getElementById("rendimiento-term").value / 100,
    efic_caldera:document.getElementById("caldera").value / 100,
  };
}

function actualizarSensibilidad() {
  const p = leerParams();

  // Actualizar labels de sliders
  document.getElementById("val-cobertura").textContent      = Math.round(p.cobertura * 100);
  document.getElementById("val-rendimiento-elec").textContent = Math.round(p.rend_elec * 100);
  document.getElementById("val-rendimiento-term").textContent = Math.round(p.rend_term * 100);
  document.getElementById("val-caldera").textContent        = Math.round(p.efic_caldera * 100);

  // Recalcular EBITDA anual
  const ebitda_anual = meses_raw.reduce((sum, m) => sum + recalcularMes(m, p), 0);
  document.getElementById("ebitda-sensibilidad").textContent =
    "$" + ebitda_anual.toLocaleString("es-MX", {maximumFractionDigits: 0});
}

// Escuchar cambios en cualquier slider
["cobertura","rendimiento-elec","rendimiento-term","caldera"].forEach(id => {
  document.getElementById(id).addEventListener("input", actualizarSensibilidad);
});

// Inicializar con valores por defecto
actualizarSensibilidad();
</script>
```

- [ ] **Step 5: Correr tests**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py -q --tb=short
```
Expected: 8 passed

- [ ] **Step 6: Correr suite completa**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/ -q --tb=short
```
Expected: 128 passed

- [ ] **Step 7: Commit**

```bash
cd /Users/manoloto/Apps/chpapp && git add web/templates/dashboard.html tests/test_web.py && git commit -m "feat: add sensitivity analysis sliders with live JS recalculation (Task 3)"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ BD persistente: `--db chpapp.db` para arranque rápido
- ✅ Botón Exportar Excel: ruta `/export/excel` + enlace en header
- ✅ Sliders de sensibilidad: 4 parámetros, JS live recalculation, EBITDA anual actualizado

**2. Placeholder scan:** Ninguno.

**3. Type consistency:**
- `meses_raw` se define en `web/app.py` dashboard() y se usa en template como `{{ meses_raw | tojson }}` ✅
- `create_app(invoices_dir, db_path=None)` — `db_path` es `str | Path | None` en firma y en test se pasa `str(db_file)` ✅
- `/export/excel` definido en app.py (Task 1) y referenciado en template (Task 2) y test (Task 2) ✅
- JS `recalcularMes` usa claves `kwh_total`, `costo_promedio_kwh`, `costo_unitario_gj` que coinciden exactamente con las del dict `meses_raw` en app.py ✅
