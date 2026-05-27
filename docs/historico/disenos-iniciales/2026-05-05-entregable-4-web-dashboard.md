# Entregable 4 — Web Dashboard de Cogeneración

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servir un dashboard web que muestre el análisis mensual de cogeneración con KPIs, gráfica de barras y tabla detallada — todo cargado automáticamente desde los PDFs en `invoices/`.

**Architecture:** Flask app factory `create_app(invoices_dir)` carga los 24 PDFs al arrancar, calcula cogeneración con el motor existente y los guarda en `app.config`. Una sola ruta `/` renderiza `dashboard.html` (Jinja2) con Bootstrap 5 y Chart.js desde CDN — sin assets estáticos propios.

**Tech Stack:** Python 3.9.6, Flask, Jinja2 (incluido en Flask), Bootstrap 5 (CDN), Chart.js (CDN), pytest + Flask test client

---

## Dominio: Datos que muestra el dashboard

El objeto `CoGenResultado` (ya existente) tiene:
- `r.meses` — lista de `CoGenMes` ordenada cronológicamente
- `r.ebitda_anual_mxn`, `r.ahorro_electricidad_anual_mxn`, `r.ahorro_caldera_anual_mxn`, `r.costo_gas_cogen_anual_mxn` — totales anuales

Por cada `CoGenMes` (atributos para la tabla):
| Columna | Atributo |
|---------|----------|
| Periodo | `periodo_inicio.strftime("%b %Y")` |
| kWh Total | `kwh_total` |
| Costo CFE | `costo_cfe_mxn` |
| $/kWh | `costo_promedio_kwh` |
| GJ Gas Real | `gj_consumido` |
| $/GJ | `costo_unitario_gj` |
| Costo Gas Real | `costo_gas_actual_mxn` |
| kWh Cubiertos | `kwh_cubiertos` |
| GJ Cogen | `gj_gas_cogen` |
| Costo Gas Cogen | `costo_gas_cogen_mxn` |
| Ahorro Elec. | `ahorro_electricidad_mxn` |
| Calor Recup. (GJ) | `calor_recuperado_gj` |
| Ahorro Caldera | `ahorro_caldera_mxn` |
| EBITDA Mes | `ebitda_mes_mxn` |

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|-----------------|
| `requirements.txt` | Modificar | Agregar `flask` |
| `web/__init__.py` | Crear | Package vacío |
| `web/app.py` | Crear | `create_app(invoices_dir)` — carga datos, registra ruta |
| `web/templates/dashboard.html` | Crear | Template único con Bootstrap + Chart.js |
| `tests/test_web.py` | Crear | 5 tests de integración con Flask test client |

---

## Task 1: Flask app factory — web/app.py

**Files:**
- Modify: `requirements.txt`
- Create: `web/__init__.py`
- Create: `web/app.py`
- Create: `tests/test_web.py` (parcial — 2 tests básicos)

- [ ] **Step 1: Instalar Flask**

```bash
pip3 install flask && pip3 show flask | grep Version
```
Expected: `Version: 3.x.x` (o similar)

- [ ] **Step 2: Agregar flask a requirements.txt**

Contenido final de `requirements.txt`:
```
pdfplumber==0.11.4
pytest==8.3.5
pytest-cov==6.1.0
flask
```

- [ ] **Step 3: Escribir tests fallidos**

Crear `/Users/manoloto/Apps/chpapp/tests/test_web.py`:

```python
# tests/test_web.py
from __future__ import annotations
import pytest
from web.app import create_app

INVOICES_DIR = "invoices"


@pytest.fixture(scope="module")
def client():
    """Flask test client cargado con los 24 PDFs reales.
    scope=module para parsear los PDFs sólo una vez.
    """
    app = create_app(INVOICES_DIR)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_dashboard_status_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_dashboard_es_html(client):
    resp = client.get("/")
    assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data


def test_dashboard_contiene_ebitda(client):
    resp = client.get("/")
    assert b"EBITDA" in resp.data


def test_dashboard_contiene_12_periodos(client):
    """La tabla debe tener filas para los 12 meses."""
    resp = client.get("/")
    # Cada mes tiene una <tr> con clase 'mes-row'; hay 12
    assert resp.data.count(b"mes-row") == 12


def test_dashboard_contiene_total_anual(client):
    resp = client.get("/")
    assert b"TOTAL ANUAL" in resp.data
```

- [ ] **Step 4: Verificar que fallan**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'web'`

- [ ] **Step 5: Crear `web/__init__.py` (vacío)**

```bash
mkdir -p /Users/manoloto/Apps/chpapp/web/templates
touch /Users/manoloto/Apps/chpapp/web/__init__.py
```

- [ ] **Step 6: Crear `web/app.py`**

```python
# web/app.py
from __future__ import annotations

import io
import sqlite3
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
    """Flask app factory. Carga los PDFs de invoices_dir al crear la app."""
    app = Flask(__name__)

    resultado = _cargar_resultado(Path(invoices_dir))
    app.config["RESULTADO"] = resultado

    @app.route("/")
    def dashboard():
        r = app.config["RESULTADO"]
        chart_labels = [m.periodo_inicio.strftime("%b %Y") for m in r.meses]
        chart_ebitda = [float(m.ebitda_mes_mxn) for m in r.meses]
        chart_ahorro_elec = [float(m.ahorro_electricidad_mxn) for m in r.meses]
        chart_costo_gas = [float(m.costo_gas_cogen_mxn) for m in r.meses]
        return render_template(
            "dashboard.html",
            r=r,
            chart_labels=chart_labels,
            chart_ebitda=chart_ebitda,
            chart_ahorro_elec=chart_ahorro_elec,
            chart_costo_gas=chart_costo_gas,
        )

    return app
```

- [ ] **Step 7: Verificar tests que ya pueden pasar (importación + arranque)**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py::test_dashboard_status_200 -v 2>&1 | tail -5
```
Expected: FAIL con `TemplateNotFound: dashboard.html` (la app arranca pero el template no existe aún — eso es correcto)

- [ ] **Step 8: Commit parcial**

```bash
cd /Users/manoloto/Apps/chpapp && git add requirements.txt web/__init__.py web/app.py tests/test_web.py && git commit -m "feat: add Flask app factory with cogen data loading (Task 1)"
```

---

## Task 2: Dashboard HTML template — web/templates/dashboard.html

**Files:**
- Create: `web/templates/dashboard.html`

- [ ] **Step 1: Crear el template**

Crear `/Users/manoloto/Apps/chpapp/web/templates/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Análisis de Cogeneración — CHP México</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8f9fa; }
    .kpi-card { border-left: 4px solid; }
    .kpi-ebitda  { border-color: #198754; }
    .kpi-elec    { border-color: #0d6efd; }
    .kpi-caldera { border-color: #fd7e14; }
    .kpi-gas     { border-color: #dc3545; }
    .table-mes th { background: #1F4E79; color: #fff; white-space: nowrap; }
    .total-row td { background: #D9E1F2; font-weight: 600; }
    .ebitda-cell  { background: #E2EFDA; font-weight: 600; }
    .neg { color: #dc3545; }
  </style>
</head>
<body>
<div class="container-fluid py-4">

  <!-- Título -->
  <div class="d-flex align-items-center mb-4">
    <h1 class="h3 mb-0 me-3">⚡ Análisis de Cogeneración</h1>
    <span class="badge bg-secondary">{{ r.meses|length }} meses pareados</span>
  </div>

  <!-- KPI cards -->
  <div class="row g-3 mb-4">
    <div class="col-md-3">
      <div class="card kpi-card kpi-ebitda h-100 shadow-sm">
        <div class="card-body">
          <div class="text-muted small">EBITDA Anual</div>
          <div class="fs-4 fw-bold text-success">
            ${{ "{:,.0f}".format(r.ebitda_anual_mxn|float) }}
          </div>
          <div class="text-muted small">MXN / año</div>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card kpi-card kpi-elec h-100 shadow-sm">
        <div class="card-body">
          <div class="text-muted small">Ahorro Electricidad</div>
          <div class="fs-4 fw-bold text-primary">
            ${{ "{:,.0f}".format(r.ahorro_electricidad_anual_mxn|float) }}
          </div>
          <div class="text-muted small">MXN / año</div>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card kpi-card kpi-caldera h-100 shadow-sm">
        <div class="card-body">
          <div class="text-muted small">Ahorro Caldera</div>
          <div class="fs-4 fw-bold text-warning">
            ${{ "{:,.0f}".format(r.ahorro_caldera_anual_mxn|float) }}
          </div>
          <div class="text-muted small">MXN / año</div>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card kpi-card kpi-gas h-100 shadow-sm">
        <div class="card-body">
          <div class="text-muted small">Costo Gas Cogen</div>
          <div class="fs-4 fw-bold text-danger">
            ${{ "{:,.0f}".format(r.costo_gas_cogen_anual_mxn|float) }}
          </div>
          <div class="text-muted small">MXN / año</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Gráfica -->
  <div class="card shadow-sm mb-4">
    <div class="card-body">
      <h5 class="card-title">EBITDA Mensual vs Componentes</h5>
      <canvas id="cogenChart" height="90"></canvas>
    </div>
  </div>

  <!-- Tabla mensual -->
  <div class="card shadow-sm">
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="table table-sm table-hover table-mes mb-0">
          <thead>
            <tr>
              <th>Periodo</th>
              <th class="text-end">kWh Total</th>
              <th class="text-end">Costo CFE (MXN)</th>
              <th class="text-end">$/kWh</th>
              <th class="text-end">GJ Gas Real</th>
              <th class="text-end">$/GJ</th>
              <th class="text-end">Costo Gas Real</th>
              <th class="text-end">kWh Cubiertos</th>
              <th class="text-end">GJ Cogen</th>
              <th class="text-end">Costo Gas Cogen</th>
              <th class="text-end">Ahorro Elec.</th>
              <th class="text-end">Calor (GJ)</th>
              <th class="text-end">Ahorro Caldera</th>
              <th class="text-end ebitda-cell">EBITDA Mes</th>
            </tr>
          </thead>
          <tbody>
            {% for m in r.meses %}
            <tr class="mes-row">
              <td>{{ m.periodo_inicio.strftime("%b %Y") }}</td>
              <td class="text-end">{{ "{:,.0f}".format(m.kwh_total|float) }}</td>
              <td class="text-end">{{ "${:,.0f}".format(m.costo_cfe_mxn|float) }}</td>
              <td class="text-end">{{ "{:.4f}".format(m.costo_promedio_kwh|float) }}</td>
              <td class="text-end">{{ "{:,.2f}".format(m.gj_consumido|float) }}</td>
              <td class="text-end">{{ "{:.4f}".format(m.costo_unitario_gj|float) }}</td>
              <td class="text-end">{{ "${:,.0f}".format(m.costo_gas_actual_mxn|float) }}</td>
              <td class="text-end">{{ "{:,.0f}".format(m.kwh_cubiertos|float) }}</td>
              <td class="text-end">{{ "{:,.2f}".format(m.gj_gas_cogen|float) }}</td>
              <td class="text-end">{{ "${:,.0f}".format(m.costo_gas_cogen_mxn|float) }}</td>
              <td class="text-end">{{ "${:,.0f}".format(m.ahorro_electricidad_mxn|float) }}</td>
              <td class="text-end">{{ "{:,.2f}".format(m.calor_recuperado_gj|float) }}</td>
              <td class="text-end">{{ "${:,.0f}".format(m.ahorro_caldera_mxn|float) }}</td>
              <td class="text-end ebitda-cell">{{ "${:,.0f}".format(m.ebitda_mes_mxn|float) }}</td>
            </tr>
            {% endfor %}
            <tr class="total-row">
              <td><strong>TOTAL ANUAL</strong></td>
              <td class="text-end">{{ "{:,.0f}".format(r.kwh_total_anual|float) }}</td>
              <td class="text-end"></td>
              <td class="text-end"></td>
              <td class="text-end"></td>
              <td class="text-end"></td>
              <td class="text-end"></td>
              <td class="text-end">{{ "{:,.0f}".format(r.kwh_cubiertos_anual|float) }}</td>
              <td class="text-end">{{ "{:,.2f}".format(r.gj_gas_cogen_anual|float) }}</td>
              <td class="text-end">{{ "${:,.0f}".format(r.costo_gas_cogen_anual_mxn|float) }}</td>
              <td class="text-end">{{ "${:,.0f}".format(r.ahorro_electricidad_anual_mxn|float) }}</td>
              <td class="text-end"></td>
              <td class="text-end">{{ "${:,.0f}".format(r.ahorro_caldera_anual_mxn|float) }}</td>
              <td class="text-end ebitda-cell">{{ "${:,.0f}".format(r.ebitda_anual_mxn|float) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Parámetros usados -->
  <div class="mt-3 text-muted small">
    Parámetros: cobertura eléctrica={{ (r.params.cobertura_electrica * 100)|int }}% ·
    rendimiento eléctrico={{ (r.params.rendimiento_electrico * 100)|int }}% ·
    rendimiento térmico={{ (r.params.rendimiento_termico * 100)|int }}% ·
    eficiencia caldera={{ (r.params.eficiencia_caldera * 100)|int }}%
  </div>

</div><!-- /container-fluid -->

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>
const ctx = document.getElementById("cogenChart");
new Chart(ctx, {
  type: "bar",
  data: {
    labels: {{ chart_labels | tojson }},
    datasets: [
      {
        label: "Ahorro Electricidad",
        data: {{ chart_ahorro_elec | tojson }},
        backgroundColor: "rgba(13,110,253,0.6)",
        stack: "componentes"
      },
      {
        label: "Ahorro Caldera",
        data: {{ chart_ahorro_caldera | tojson }},
        backgroundColor: "rgba(253,126,20,0.6)",
        stack: "componentes"
      },
      {
        label: "Costo Gas Cogen",
        data: {{ chart_costo_gas | tojson }}.map(v => -v),
        backgroundColor: "rgba(220,53,69,0.6)",
        stack: "componentes"
      },
      {
        type: "line",
        label: "EBITDA",
        data: {{ chart_ebitda | tojson }},
        borderColor: "#198754",
        backgroundColor: "rgba(25,135,84,0.1)",
        borderWidth: 2,
        pointRadius: 4,
        fill: false,
        tension: 0.3,
        stack: undefined
      }
    ]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { position: "top" },
      tooltip: {
        callbacks: {
          label: function(ctx) {
            const v = Math.abs(ctx.raw);
            return ctx.dataset.label + ": $" + v.toLocaleString("es-MX", {maximumFractionDigits: 0});
          }
        }
      }
    },
    scales: {
      y: {
        ticks: {
          callback: v => "$" + Math.abs(v).toLocaleString("es-MX", {maximumFractionDigits: 0})
        }
      }
    }
  }
});
</script>
</body>
</html>
```

**Nota importante:** El template usa `chart_ahorro_caldera` pero en `web/app.py` del Task 1 se pasó `chart_ahorro_elec` y `chart_costo_gas`. Hay que agregar `chart_ahorro_caldera` al `render_template`. Actualizar la función `dashboard()` en `web/app.py`:

```python
@app.route("/")
def dashboard():
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
```

- [ ] **Step 2: Correr todos los tests**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/test_web.py -v
```
Expected: 5 PASS

- [ ] **Step 3: Correr suite completa (no romper nada)**

```bash
cd /Users/manoloto/Apps/chpapp && python3 -m pytest tests/ -q --tb=short --ignore=tests/test_web.py && python3 -m pytest tests/test_web.py -v
```
Expected: 120 passed + 5 passed = 125 total

- [ ] **Step 4: Commit**

```bash
cd /Users/manoloto/Apps/chpapp && git add web/templates/dashboard.html web/app.py && git commit -m "feat: add dashboard HTML template with Bootstrap + Chart.js (Task 2)"
```

---

## Task 3: Entry point + smoke test visual

**Files:**
- Create: `run_server.py`

- [ ] **Step 1: Crear `run_server.py`**

```python
# run_server.py
"""Punto de entrada para el servidor de desarrollo.

Uso:
    python3 run_server.py
    python3 run_server.py --port 8080
    python3 run_server.py --invoices /ruta/a/invoices
"""
from __future__ import annotations

import argparse
from web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard de Cogeneración")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--invoices", default="invoices", help="Directorio con PDFs")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(f"Cargando facturas desde '{args.invoices}'...")
    app = create_app(args.invoices)
    print(f"Servidor listo → http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test — arrancar el servidor y verificar respuesta**

En una terminal, ejecutar:
```bash
cd /Users/manoloto/Apps/chpapp && python3 run_server.py
```
Expected output:
```
Cargando facturas desde 'invoices'...
Servidor listo → http://127.0.0.1:5000/
```

En otra terminal (o con timeout):
```bash
cd /Users/manoloto/Apps/chpapp && python3 -c "
import subprocess, time, urllib.request, sys

proc = subprocess.Popen(['python3', 'run_server.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(8)  # esperar a que cargue los 24 PDFs

try:
    resp = urllib.request.urlopen('http://127.0.0.1:5000/', timeout=5)
    html = resp.read().decode()
    assert 'EBITDA' in html, 'EBITDA no encontrado'
    assert 'TOTAL ANUAL' in html, 'TOTAL ANUAL no encontrado'
    assert html.count('mes-row') == 12, f'Se esperaban 12 mes-row, encontrados: {html.count(\"mes-row\")}'
    print('OK → Dashboard responde correctamente con 12 meses y EBITDA')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
finally:
    proc.terminate()
"
```
Expected: `OK → Dashboard responde correctamente con 12 meses y EBITDA`

- [ ] **Step 3: Commit final**

```bash
cd /Users/manoloto/Apps/chpapp && git add run_server.py && git commit -m "feat: add run_server.py entry point for web dashboard (Task 3)"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ Dashboard web que carga PDFs automáticamente
- ✅ 4 KPI cards: EBITDA anual, Ahorro Elec., Ahorro Caldera, Costo Gas Cogen
- ✅ Gráfica de barras apiladas con EBITDA como línea
- ✅ Tabla con 12 meses + fila TOTAL ANUAL, 14 columnas
- ✅ Bootstrap 5 + Chart.js desde CDN (sin assets propios)
- ✅ Entry point `run_server.py` con argparse
- ✅ 5 tests de integración con Flask test client

**2. Placeholder scan:** Ninguno encontrado.

**3. Type consistency:**
- `chart_ahorro_caldera` se agrega en Task 2 — la nota en Task 2 Step 1 lo documenta explícitamente
- `r.params.cobertura_electrica` en el template: es `Decimal`, el filtro `|int` de Jinja2 necesita `(r.params.cobertura_electrica * 100)|int` — Jinja2 acepta Decimal en operaciones aritméticas ✅
- `chart_labels | tojson` — Flask incluye `tojson` como filtro Jinja2 por defecto ✅
- `m.kwh_total | float` — Jinja2 aplica `float()` al Decimal ✅
