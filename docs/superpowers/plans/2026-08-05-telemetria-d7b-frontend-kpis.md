# Frontend KPIs Telemetría D7-B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el panel de 6 tarjetas KPI horizontales del dashboard de telemetría por un panel de 3 pestañas (Energéticos / Económicos / Producción) con tarjetas de KPI individuales, gauge para Factor de Potencia, sparklines duales y formulario de captura de producción mensual.

**Architecture:** El frontend es JS puro (IIFE) que consume el JSON del endpoint existente `/data`; el backend sólo necesita un campo adicional (`punto_medicion`) en `nodo_seleccionado`. Los cambios son aditivos: se añaden funciones nuevas al JS existente, se reemplaza el bloque HTML de KPIs y se amplía el CSS. La lógica de pestañas es manual (sin dependencia de Bootstrap JS tab events), manteniendo `_tabActivo` como variable de estado.

**Tech Stack:** Python 3.11, Flask 3.x, Bootstrap 5.3 (nav-tabs CSS), Chart.js 4.4.4 (doughnut semicírculo para gauge, line para sparklines), Jinja2, pytest.

## Global Constraints

- Versión CHANGELOG: **2.82.0** (la spec dice 2.80.0 pero 2.79.0–2.81.0 ya existen).
- Sin librerías JS nuevas. Chart.js 4.4.4 ya cargado vía CDN.
- Acceso a Supabase exclusivamente vía supabase-py. No psycopg2.
- Los tests inyectan sesión Flask directamente (`client.session_transaction()`), sin llamar a Supabase.
- `FASE2_HABILITADA=true` requerido para que el endpoint de telemetría responda (abort 404 si False).
- Respuestas en español. Commits en español con `feat(fase2-D7-B):` prefix.
- Commit final: `feat(fase2-D7-B): frontend KPIs telemetria con tabs, tarjetas, gauge PF y formulario produccion manual`

---

## Mapa de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `web/templates/telemetria/dashboard.html` | Modificar | Reemplaza bloque `col-lg-4` KPI con estructura de 3 pestañas Bootstrap |
| `web/static/css/telemetria.css` | Modificar | Añade estilos para grid de KPIs, tarjetas v2, sparklines, gauge, badge delta |
| `web/static/js/dashboard-telemetria.js` | Modificar | Añade `_KPI_META`, renderers de tarjeta/gauge/sparkline, `_renderKpisPaneles`, `_renderFormularioProduccion`, estado `_tabActivo`; elimina `_renderKPIs` y `_renderComparativa` (código muerto) |
| `web/app.py` | Modificar | Añade `punto_medicion` al dict `nodo_seleccionado` en la respuesta JSON |
| `tests/test_dashboard_telemetria.py` | Modificar | Añade 5 tests para el endpoint POST `/telemetria/produccion` |
| `CHANGELOG.md` | Modificar | Entrada v2.82.0 |
| `CLAUDE.md` | Modificar | Actualiza sección "Nuevas funcionalidades" e "Integración Telemática" |

---

### Task 1: HTML structure + CSS additions

**Files:**
- Modify: `web/templates/telemetria/dashboard.html`
- Modify: `web/static/css/telemetria.css`

**Interfaces:**
- Consumes: nada de tareas anteriores (HTML estático)
- Produces: IDs DOM `pane-energeticos`, `pane-economicos`, `pane-produccion`, `kpi-tabs`, `tab-energeticos`, `tab-economicos`, `tab-produccion` — necesarios por Task 2 y 3 en JS.

- [ ] **Step 1: Reemplazar el bloque `col-lg-4` en dashboard.html**

La columna `<div class="col-lg-4 mb-3">` que empieza en la línea 76 contiene 6 tarjetas con IDs `kpi-energia`, `kpi-demanda`, `kpi-fp`, `kpi-muestras`, `kpi-costo`, `kpi-delta`. Reemplazar **todo** el contenido del `<div class="card-body">` de esa columna con:

```html
<div class="col-lg-4 mb-3">
  <div class="card border-0 shadow-sm h-100">
    <div class="card-body p-2">
      <ul class="nav nav-tabs nav-tabs-sm mb-2" id="kpi-tabs" role="tablist">
        <li class="nav-item" role="presentation">
          <button class="nav-link active" id="tab-energeticos"
                  type="button" role="tab"
                  data-tab="energeticos">Energéticos</button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link" id="tab-economicos"
                  type="button" role="tab"
                  data-tab="economicos">Económicos</button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link" id="tab-produccion"
                  type="button" role="tab"
                  data-tab="produccion">Producción</button>
        </li>
      </ul>
      <div class="tab-content" id="kpi-tab-content">
        <div class="tab-pane show active" id="pane-energeticos" role="tabpanel"
             aria-labelledby="tab-energeticos"></div>
        <div class="tab-pane" id="pane-economicos" role="tabpanel"
             aria-labelledby="tab-economicos"></div>
        <div class="tab-pane" id="pane-produccion" role="tabpanel"
             aria-labelledby="tab-produccion"></div>
      </div>
    </div>
  </div>
</div>
```

Eliminar los 6 `<div class="kpi-card ...">` y el `<h6 class="text-muted mb-3">KPIs del periodo</h6>` que existían antes. El resultado es que la columna derecha ahora muestra 3 tabs vacíos (sin error JS).

- [ ] **Step 2: Añadir estilos al final de `web/static/css/telemetria.css`**

Añadir al final del archivo (después del bloque existente `.unifilar-se-agrupacion`):

```css
/* ── D7-B: KPI paneles con tabs ──────────────────────────────────────────── */

#kpi-tabs .nav-link {
  font-size: .76rem;
  padding: .28rem .55rem;
}

/* Grid de una columna para las tarjetas */
.kpi-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: .45rem;
  padding: .2rem 0;
}

/* Tarjeta KPI v2 */
.kpi-card-v2 {
  border-left: 3px solid #2E5C8A;
  padding: .3rem .55rem;
  background: #f8fafc;
  border-radius: 0 4px 4px 0;
}
.kpi-card-v2 .kpi-label-v2 {
  font-size: .68rem;
  color: #6b7280;
  margin-bottom: .08rem;
  line-height: 1.2;
}
.kpi-card-v2 .kpi-value-v2 {
  font-size: 1.05rem;
  font-weight: 700;
  color: #1F3A5F;
  line-height: 1.2;
}
.kpi-card-v2 .kpi-unit-v2 {
  font-size: .68rem;
  color: #6b7280;
  margin-left: .2rem;
}

/* Badge de variación vs periodo anterior */
.kpi-delta-badge {
  font-size: .65rem;
  padding: .08rem .28rem;
  border-radius: 3px;
  margin-left: .3rem;
  vertical-align: middle;
}
.kpi-delta-badge.favorable    { background: #d1fae5; color: #065f46; }
.kpi-delta-badge.desfavorable { background: #fee2e2; color: #991b1b; }
.kpi-delta-badge.neutro       { background: #f3f4f6; color: #374151; }

/* Hint de fuente de precio */
.kpi-hint {
  font-size: .62rem;
  color: #9ca3af;
  margin-top: .1rem;
  line-height: 1.2;
}

/* Sparklines duales: actual (azul) + anterior (gris) */
.kpi-sparkline-wrap {
  display: flex;
  gap: 2px;
  margin-top: .2rem;
  height: 32px;
  align-items: flex-end;
}
.kpi-sparkline-wrap canvas {
  flex: 1;
  height: 32px !important;
  max-height: 32px;
}

/* Gauge de Factor de Potencia (doughnut semicírculo) */
.kpi-gauge-wrap {
  position: relative;
  width: 100%;
  max-width: 110px;
  margin: .15rem auto 0;
}
.kpi-gauge-label {
  position: absolute;
  bottom: 0;
  width: 100%;
  text-align: center;
  font-size: .78rem;
  font-weight: 700;
  color: #1F3A5F;
  pointer-events: none;
}
```

- [ ] **Step 3: Verificar visualmente que no hay errores de consola**

Abrir el dashboard de telemetría. Las 3 pestañas deben aparecer en la columna derecha. Al hacer clic entre ellas deben cambiar (panes vacíos, sin contenido). No debe haber errores en consola.

- [ ] **Step 4: Commit**

```bash
git add web/templates/telemetria/dashboard.html web/static/css/telemetria.css
git commit -m "feat(fase2-D7-B): estructura HTML de tabs KPI y estilos CSS para tarjetas, sparklines y gauge"
```

---

### Task 2: JS — Renderers aislados (tarjeta, gauge, sparkline) + estado de tab

**Files:**
- Modify: `web/static/js/dashboard-telemetria.js`

**Interfaces:**
- Consumes: IDs DOM de Task 1 (`pane-*`, `tab-*`).
- Produces (funciones disponibles para Task 3):
  - `_KPI_META` — objeto constante con metadata por clave KPI
  - `_destroySparklines()` — destruye todos los Chart.js de sparkline registrados
  - `_crearSparkline(canvas, data, color)` → `Chart` instance
  - `_renderKpiCard(key, kpi, nodoTipo)` → `HTMLElement | null`
  - `_renderKpiGauge(canvasId, kpi)` → `void` (crea Chart en canvas dado)
  - `_tabActivo` — variable de estado (string: `'energeticos'|'economicos'|'produccion'`)
  - `_activarTab(nombre)` — aplica clases Bootstrap al tab correcto

**Nota:** Estas funciones se añaden al IIFE existente. Aún no se llaman desde `_renderTodo`. Los tests de esta tarea son visuales (no hay runner de JS en el proyecto).

- [ ] **Step 1: Añadir `_KPI_META` y mapa de Chart.js de sparklines**

Insertar **inmediatamente después** del bloque `// ── Estado ─────` (después de la línea `let _abort = null;`) en `dashboard-telemetria.js`:

```javascript
  // ── Metadata de KPIs para labels, unidades y decimales ─────────────────
  const _KPI_META = {
    energia_kwh:               { label: "Energía en el periodo",  unit: "kWh",     dec: 1 },
    demanda_pico_kw:           { label: "Demanda pico",           unit: "kW",      dec: 1 },
    demanda_promedio_kw:       { label: "Demanda promedio",       unit: "kW",      dec: 1 },
    factor_potencia:           { label: "Factor de potencia",     unit: "",        dec: 3 },
    costo_total_mxn:           { label: "Costo total est.",       unit: "MXN",     dec: 0 },
    costo_unitario_mxn_kwh:    { label: "Costo unitario",         unit: "MXN/kWh", dec: 4 },
    pct_sobre_factura:         { label: "% sobre factura",        unit: "%",       dec: 1 },
    consumo_especifico_kwh_m2: { label: "Consumo específico",     unit: "kWh/m²",  dec: 2 },
    costo_especifico_mxn_m2:   { label: "Costo específico",       unit: "MXN/m²",  dec: 2 },
    produccion_m2:             { label: "Producción mensual",     unit: "m²",      dec: 0 },
  };

  // Registro de instancias Chart.js para sparklines y gauge (destruir antes de re-render)
  const _sparkInstances = new Map();

  function _destroySparklines() {
    _sparkInstances.forEach((chart) => { try { chart.destroy(); } catch (_) {} });
    _sparkInstances.clear();
  }

  // Estado de pestaña activa (persiste entre re-renders)
  let _tabActivo = "energeticos";
```

- [ ] **Step 2: Añadir `_crearSparkline`**

Insertar después del bloque de `_KPI_META` recién añadido (antes de `// ── Fetch central`):

```javascript
  // ── Sparkline: line chart minimalista 32px de altura ────────────────────
  function _crearSparkline(canvas, data, color) {
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: data.map((_, i) => i),
        datasets: [{
          data,
          borderColor: color,
          borderWidth: 1.2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        }],
      },
      options: {
        responsive: false,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
      },
    });
  }
```

- [ ] **Step 3: Añadir `_renderKpiCard`**

Insertar después de `_crearSparkline`:

```javascript
  // ── Tarjeta KPI estándar ─────────────────────────────────────────────────
  function _renderKpiCard(key, kpi, nodoTipo) {
    // Respetar flags de visibilidad
    if (kpi.oculto_en_nodo && nodoTipo && kpi.oculto_en_nodo.includes(nodoTipo)) return null;
    if (kpi.aplica_a_nodo  && nodoTipo && !kpi.aplica_a_nodo.includes(nodoTipo)) return null;

    const m   = _KPI_META[key] || { label: key, unit: "", dec: 2 };
    const act = kpi.actual;
    const dPct = kpi.delta_pct;

    let deltaHtml = "";
    if (dPct !== null && dPct !== undefined) {
      const esFavorable = kpi.es_favorable_menor ? dPct < 0 : dPct > 0;
      const cls  = esFavorable ? "favorable" : (dPct === 0 ? "neutro" : "desfavorable");
      const sign = dPct >= 0 ? "+" : "";
      const pctStr = Number(dPct).toLocaleString("es-MX",
        { maximumFractionDigits: 1, minimumFractionDigits: 1 });
      deltaHtml = `<span class="kpi-delta-badge ${cls}">${sign}${pctStr}%</span>`;
    }

    let hintHtml = "";
    if (key === "costo_unitario_mxn_kwh" && kpi.fuente_precio) {
      const hints = {
        factura_mes_exacto:   "Precio de factura del mes",
        factura_mes_anterior: "Precio est. último mes disponible",
        promedio_12m:         "Precio promedio 12 meses",
        sin_datos:            "Sin facturas registradas",
      };
      hintHtml = `<div class="kpi-hint">${hints[kpi.fuente_precio] || kpi.fuente_precio}</div>`;
    }

    const valStr = act != null
      ? Number(act).toLocaleString("es-MX",
          { maximumFractionDigits: m.dec, minimumFractionDigits: m.dec })
      : "—";
    const unitHtml = m.unit ? `<span class="kpi-unit-v2">${m.unit}</span>` : "";

    const hasSpark = kpi.sparkline_actual && kpi.sparkline_actual.length > 0;
    const sparkHtml = hasSpark
      ? `<div class="kpi-sparkline-wrap">
           <canvas id="sp-${key}-act" height="32"></canvas>
           ${kpi.sparkline_anterior ? `<canvas id="sp-${key}-ant" height="32"></canvas>` : ""}
         </div>`
      : "";

    const div = document.createElement("div");
    div.className = "kpi-card-v2";
    div.innerHTML = `
      <div class="kpi-label-v2">${m.label}</div>
      <div class="d-flex align-items-baseline flex-wrap">
        <span class="kpi-value-v2">${valStr}</span>
        ${unitHtml}
        ${deltaHtml}
      </div>
      ${hintHtml}
      ${sparkHtml}
    `;
    return div;
  }
```

- [ ] **Step 4: Añadir `_renderKpiGauge`**

Insertar después de `_renderKpiCard`:

```javascript
  // ── Gauge FP: doughnut semicírculo Chart.js ──────────────────────────────
  function _renderKpiGauge(canvasId, kpi) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const val    = kpi.actual != null ? parseFloat(kpi.actual) : 0;
    const maxVal = kpi.rango_max || 1.0;
    const filled = Math.min(Math.max(val, 0), maxVal);
    const color  = val >= 0.90 ? "#198754"
                 : val >= 0.80 ? "#ffc107"
                 : "#dc3545";
    const chart = new Chart(canvas, {
      type: "doughnut",
      data: {
        datasets: [{
          data: [filled, maxVal - filled],
          backgroundColor: [color, "#e5e7eb"],
          borderWidth: 0,
        }],
      },
      options: {
        circumference: 180,
        rotation: -90,
        responsive: true,
        maintainAspectRatio: true,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        cutout: "68%",
      },
    });
    _sparkInstances.set(canvasId, chart);
  }
```

- [ ] **Step 5: Añadir `_activarTab` y listener de clicks de tab**

Insertar después de `_renderKpiGauge`:

```javascript
  // ── Gestión de pestaña activa ────────────────────────────────────────────
  function _activarTab(nombre) {
    ["energeticos", "economicos", "produccion"].forEach((g) => {
      const btn  = $(`tab-${g}`);
      const pane = $(`pane-${g}`);
      if (!btn || !pane) return;
      const activo = g === nombre;
      btn.classList.toggle("active", activo);
      btn.setAttribute("aria-selected", String(activo));
      pane.classList.toggle("show",   activo);
      pane.classList.toggle("active", activo);
    });
  }
```

En el bloque `// ── Event listeners` (cerca del final del IIFE, antes de `// ── Init`), añadir:

```javascript
  document.querySelectorAll("#kpi-tabs button[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      _tabActivo = btn.dataset.tab;
      _activarTab(_tabActivo);
    });
  });
```

- [ ] **Step 6: Verificar que el dashboard carga sin errores de consola**

Abrir el dashboard. Las funciones existen pero aún no se llaman. No debe haber errores de JS. Los tabs siguen respondiendo al click (manejados por el nuevo listener).

- [ ] **Step 7: Commit**

```bash
git add web/static/js/dashboard-telemetria.js
git commit -m "feat(fase2-D7-B): renderers KPI (tarjeta, gauge, sparkline) y estado _tabActivo en JS"
```

---

### Task 3: JS orchestration + backend `punto_medicion` + wiring en `_renderTodo`

**Files:**
- Modify: `web/static/js/dashboard-telemetria.js`
- Modify: `web/app.py`

**Interfaces:**
- Consumes:
  - Todas las funciones de Task 2 (`_KPI_META`, `_destroySparklines`, `_crearSparkline`, `_renderKpiCard`, `_renderKpiGauge`, `_activarTab`, `_sparkInstances`, `_tabActivo`)
  - `CLIENTE_ID` (variable del IIFE, ya existente)
  - `data.kpis_paneles` del JSON del endpoint (estructura `{energeticos: {...}, economicos: {...}, produccion: {...}, meta: {...}}`)
  - `data.nodo_seleccionado.punto_medicion` (añadido al backend en este task)
- Produces:
  - `_renderKpisPaneles(kpisPaneles, nodoTipo, rango)` — función principal del panel
  - `_renderFormularioProduccion(anio, mes)` — formulario POST de m²
  - `_renderTodo` actualizado (sin `_renderKPIs` ni `_renderComparativa`)

- [ ] **Step 1: Añadir `punto_medicion` al JSON del backend**

En `web/app.py`, localizar el return del endpoint `cliente_dashboard_telemetria_data` (cerca de la línea 3111):

```python
        return jsonify({
            "nodo_seleccionado": {
                "id": nodo["id"],
                "nombre": nodo["nombre"],
                "ruta_breadcrumbs": _breadcrumbs(nodo),
            },
```

Reemplazar con:

```python
        return jsonify({
            "nodo_seleccionado": {
                "id": nodo["id"],
                "nombre": nodo["nombre"],
                "punto_medicion": nodo.get("punto_medicion"),
                "ruta_breadcrumbs": _breadcrumbs(nodo),
            },
```

- [ ] **Step 2: Añadir `_renderFormularioProduccion` al JS**

Insertar después de `_activarTab` (y antes de `// ── Fetch central`):

```javascript
  // ── Formulario de captura de producción mensual ──────────────────────────
  function _renderFormularioProduccion(anio, mes) {
    const wrap = document.createElement("div");
    wrap.className = "mt-3 pt-2 border-top";
    wrap.innerHTML = `
      <p class="small text-muted mb-1" style="font-size:.7rem">
        Captura producción del mes ${mes}/${anio} (m²):
      </p>
      <div class="d-flex gap-2 align-items-center">
        <input type="number" id="prod-m2-input" class="form-control form-control-sm"
               placeholder="m²" min="0" step="0.01" style="max-width:88px">
        <button type="button" id="btn-guardar-prod" class="btn btn-sm btn-primary">
          Guardar
        </button>
      </div>
      <div id="prod-feedback" class="mt-1" style="min-height:1.1em;font-size:.68rem"></div>
    `;

    // El listener se registra en el próximo tick para que el elemento esté en el DOM
    requestAnimationFrame(() => {
      const btn   = document.getElementById("btn-guardar-prod");
      const input = document.getElementById("prod-m2-input");
      const fb    = document.getElementById("prod-feedback");
      if (!btn || !input) return;

      btn.addEventListener("click", async () => {
        const m2 = parseFloat(input.value);
        if (isNaN(m2) || m2 < 0) {
          if (fb) { fb.textContent = "Ingresa un valor válido ≥ 0."; fb.style.color = "#dc3545"; }
          return;
        }
        btn.disabled = true;
        if (fb) { fb.textContent = "Guardando…"; fb.style.color = "#6b7280"; }
        try {
          const resp = await fetch(
            `/clientes/${CLIENTE_ID}/telemetria/produccion`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ anio, mes, m2_mes: m2 }),
            }
          );
          const json = await resp.json().catch(() => ({}));
          if (!resp.ok) {
            if (fb) { fb.textContent = json.error || `Error ${resp.status}`; fb.style.color = "#dc3545"; }
          } else {
            if (fb) { fb.textContent = `Guardado: ${json.registros} registros.`; fb.style.color = "#198754"; }
            input.value = "";
          }
        } catch (e) {
          if (fb) { fb.textContent = "Error de red."; fb.style.color = "#dc3545"; }
        } finally {
          btn.disabled = false;
        }
      });
    });
    return wrap;
  }
```

- [ ] **Step 3: Añadir `_renderKpisPaneles`**

Insertar después de `_renderFormularioProduccion`:

```javascript
  // ── Panel principal de KPIs con tabs ─────────────────────────────────────
  function _renderKpisPaneles(kpisPaneles, nodoTipo, rango) {
    if (!kpisPaneles) return;
    _destroySparklines();

    const panes = {
      energeticos: $("pane-energeticos"),
      economicos:  $("pane-economicos"),
      produccion:  $("pane-produccion"),
    };
    const tabBtns = {
      energeticos: $("tab-energeticos"),
      economicos:  $("tab-economicos"),
      produccion:  $("tab-produccion"),
    };

    // Limpiar panes
    Object.values(panes).forEach((p) => { if (p) p.innerHTML = ""; });

    // Pestaña Producción: visible sólo cuando rango está en solo_en_rango
    const soloEnRango = kpisPaneles.produccion && kpisPaneles.produccion.solo_en_rango;
    const produccionVisible = !soloEnRango || soloEnRango.includes(rango);
    if (tabBtns.produccion) tabBtns.produccion.style.display = produccionVisible ? "" : "none";
    // Si la tab activa era producción y ahora no es visible, redirigir a energéticos
    if (!produccionVisible && _tabActivo === "produccion") _tabActivo = "energeticos";

    // Render de cada grupo de KPIs
    const grupos = ["energeticos", "economicos"];
    if (produccionVisible) grupos.push("produccion");

    grupos.forEach((grupo) => {
      const kpis = kpisPaneles[grupo];
      if (!kpis || !panes[grupo]) return;

      const grid = document.createElement("div");
      grid.className = "kpi-grid";

      Object.entries(kpis).forEach(([key, kpi]) => {
        // Saltar claves meta del grupo (e.g. solo_en_rango)
        if (key === "solo_en_rango") return;
        if (!kpi || typeof kpi !== "object" || !("actual" in kpi)) return;

        if (kpi.es_gauge) {
          // Gauge: tarjeta con canvas semicírculo
          const gaugeId = `gauge-${key}`;
          const m = _KPI_META[key] || { label: key };
          const wrap = document.createElement("div");
          wrap.className = "kpi-card-v2";
          const valStr = kpi.actual != null
            ? Number(kpi.actual).toLocaleString("es-MX",
                { maximumFractionDigits: 3, minimumFractionDigits: 3 })
            : "—";
          wrap.innerHTML = `
            <div class="kpi-label-v2">${m.label}</div>
            <div class="kpi-gauge-wrap">
              <canvas id="${gaugeId}"></canvas>
              <div class="kpi-gauge-label">${valStr}</div>
            </div>
          `;
          grid.appendChild(wrap);
          requestAnimationFrame(() => _renderKpiGauge(gaugeId, kpi));
        } else {
          const card = _renderKpiCard(key, kpi, nodoTipo);
          if (card) grid.appendChild(card);
        }
      });

      panes[grupo].appendChild(grid);

      // Sparklines: registrar tras inserción en DOM
      requestAnimationFrame(() => {
        Object.entries(kpis).forEach(([key, kpi]) => {
          if (!kpi || typeof kpi !== "object" || kpi.es_gauge) return;
          if (kpi.sparkline_actual && kpi.sparkline_actual.length > 0) {
            const cAct = document.getElementById(`sp-${key}-act`);
            if (cAct) _sparkInstances.set(`sp-${key}-act`,
              _crearSparkline(cAct, kpi.sparkline_actual, C_PRIMARIO_L));
          }
          if (kpi.sparkline_anterior && kpi.sparkline_anterior.length > 0) {
            const cAnt = document.getElementById(`sp-${key}-ant`);
            if (cAnt) _sparkInstances.set(`sp-${key}-ant`,
              _crearSparkline(cAnt, kpi.sparkline_anterior, "#9ca3af"));
          }
        });
      });
    });

    // Formulario de producción en la pestaña Producción (rango 30d)
    if (produccionVisible && panes.produccion) {
      const meta  = kpisPaneles.meta || {};
      const hasta = meta.periodo_actual_hasta
        ? new Date(meta.periodo_actual_hasta)
        : new Date();
      const anio = hasta.getFullYear();
      const mes  = hasta.getMonth() + 1;
      panes.produccion.appendChild(_renderFormularioProduccion(anio, mes));
    }

    // Restaurar pestaña activa (persiste entre re-fetches)
    _activarTab(_tabActivo);
  }
```

- [ ] **Step 4: Actualizar `_renderTodo` y eliminar código muerto**

Localizar la función `_renderTodo` (cerca de la línea 89 del JS original):

```javascript
  function _renderTodo(data) {
    _renderBreadcrumbs(data.nodo_seleccionado);
    _renderKPIs(data.kpis);
    _renderUnifilar(data.arbol_sunburst);
    _renderSerie(data.serie_temporal, data.nodo_seleccionado.nombre);
    $("titulo-nodo").textContent = data.nodo_seleccionado.nombre;
    _renderComparativa(data.comparativa_mes_anterior);
  }
```

Reemplazar con:

```javascript
  function _renderTodo(data) {
    _renderBreadcrumbs(data.nodo_seleccionado);
    _renderKpisPaneles(
      data.kpis_paneles,
      data.nodo_seleccionado.punto_medicion,
      _rango,
    );
    _renderUnifilar(data.arbol_sunburst);
    _renderSerie(data.serie_temporal, data.nodo_seleccionado.nombre);
    $("titulo-nodo").textContent = data.nodo_seleccionado.nombre;
  }
```

Luego eliminar completamente las dos funciones que ya no se usan:
- La función `_renderKPIs(kpis)` (líneas ~126-146 del original)
- La función `_renderComparativa(comp)` (líneas ~149-170 del original)

Ambas eran actualizaciones de elementos DOM que ya no existen en el HTML (`kpi-energia`, `kpi-demanda`, `kpi-fp`, `kpi-muestras`, `kpi-costo`, `kpi-delta`, `kpi-delta-hint`, `kpi-costo-hint`).

- [ ] **Step 5: Verificar en el browser que los KPIs se renderizan**

Abrir el dashboard de telemetría. La columna derecha debe mostrar:
- Tab "Energéticos" activo con 4 tarjetas: Energía, Demanda pico, Demanda promedio, Factor de Potencia (gauge semicírculo).
- Tab "Económicos" con 3 tarjetas: Costo total est., Costo unitario, % sobre factura (esta última oculta si el nodo es acometida_cfe).
- Tab "Producción" visible sólo al seleccionar rango 30d; con 3 tarjetas y el formulario de captura de m².
- Los sparklines de `energia_kwh` (único KPI con sparkline en el backend actual) se muestran cuando hay datos.
- Al cambiar de rango, la tab activa se mantiene (excepto si era Producción y se cambia a 24h o 7d).

- [ ] **Step 6: Commit**

```bash
git add web/static/js/dashboard-telemetria.js web/app.py
git commit -m "feat(fase2-D7-B): _renderKpisPaneles, _renderFormularioProduccion, wiring en _renderTodo; punto_medicion en nodo_seleccionado"
```

---

### Task 4: Tests + CHANGELOG + CLAUDE.md

**Files:**
- Modify: `tests/test_dashboard_telemetria.py`
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: endpoint `POST /clientes/<id>/telemetria/produccion` (implementado en v2.81.0 en `web/app.py`)
- Produces: 5 tests nuevos (i–m) que validan auth, input y FASE2 del endpoint POST

- [ ] **Step 1: Escribir los 5 tests — verificar primero que fallan por razón esperada**

Los tests prueban el endpoint ya implementado; deben pasar desde el primer run. Añadir al final de `tests/test_dashboard_telemetria.py`:

```python
# ── Test i ─────────────────────────────────────────────────────────────────
def test_post_produccion_ok(client, app):
    """POST válido con m2_mes ≥ 0 → 200, ok=True, registros=N."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente_con_conteos), \
         patch("storage.repository.upsert_produccion_mes", return_value=20):
        resp = client.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 6, "m2_mes": 12000.0},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["registros"] == 20


# ── Test j ─────────────────────────────────────────────────────────────────
def test_post_produccion_sin_m2_mes_400(client, app):
    """POST sin campo m2_mes → 400."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente_con_conteos):
        resp = client.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 6},
        )
    assert resp.status_code == 400


# ── Test k ─────────────────────────────────────────────────────────────────
def test_post_produccion_m2_negativo_400(client, app):
    """POST con m2_mes negativo → 400."""
    app.config["FASE2_HABILITADA"] = True
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    with patch("storage.repository.get_cliente_con_conteos",
               side_effect=_mock_get_cliente_con_conteos):
        resp = client.post(
            "/clientes/44/telemetria/produccion",
            json={"anio": 2024, "mes": 6, "m2_mes": -100.0},
        )
    assert resp.status_code == 400


# ── Test l ─────────────────────────────────────────────────────────────────
def test_post_produccion_sin_autenticacion_redirige(client, app):
    """POST sin sesión activa → before_request redirige a login (302).

    El hook _require_login redirige antes de que el route pueda devolver 401.
    """
    app.config["FASE2_HABILITADA"] = True
    # Sin _injectar_sesion: usuario no autenticado
    resp = client.post(
        "/clientes/44/telemetria/produccion",
        json={"anio": 2024, "mes": 6, "m2_mes": 12000.0},
    )
    assert resp.status_code == 302


# ── Test m ─────────────────────────────────────────────────────────────────
def test_post_produccion_fase2_deshabilitada_404(client, app):
    """POST con FASE2_HABILITADA=False → 404."""
    app.config["FASE2_HABILITADA"] = False
    _injectar_sesion(client, "master_admin", cliente_activo_id=44)
    resp = client.post(
        "/clientes/44/telemetria/produccion",
        json={"anio": 2024, "mes": 6, "m2_mes": 12000.0},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Ejecutar tests y verificar que pasan**

```bash
pytest tests/test_dashboard_telemetria.py -v
```

Resultado esperado: todos los tests i–m en estado PASSED. Los tests a–h existentes también deben seguir pasando.

- [ ] **Step 3: Añadir entrada CHANGELOG v2.82.0**

En `CHANGELOG.md`, insertar **antes** de `## [2.81.0]` (al inicio del archivo, después de `# Changelog\n\n`):

```markdown
## [2.82.0] — 2026-08-05

### Añadido — Fase 2 D7-B: frontend KPIs telemetría con tabs, tarjetas, gauge PF y formulario producción

- `web/templates/telemetria/dashboard.html` — reemplaza el panel de 6 tarjetas KPI horizontales por estructura de 3 pestañas Bootstrap (Energéticos / Económicos / Producción). Panes vacíos renderizados por JS; HTML sin lógica.
- `web/static/css/telemetria.css` — añade `.kpi-grid`, `.kpi-card-v2`, `.kpi-delta-badge` (favorable/desfavorable/neutro), `.kpi-hint`, `.kpi-sparkline-wrap`, `.kpi-gauge-wrap`, `.kpi-gauge-label`.
- `web/static/js/dashboard-telemetria.js` — nuevas funciones: `_crearSparkline`, `_renderKpiCard` (tarjeta con badge delta y sparklines duales), `_renderKpiGauge` (doughnut semicírculo Chart.js para Factor de Potencia; verde ≥ 0.90, amarillo ≥ 0.80, rojo < 0.80), `_renderFormularioProduccion` (POST asíncrono con feedback inline), `_renderKpisPaneles` (respeta `oculto_en_nodo`, `aplica_a_nodo`, `solo_en_rango`; pestaña Producción oculta en rangos 24h y 7d; estado `_tabActivo` persiste entre re-fetches). Eliminadas `_renderKPIs` y `_renderComparativa` (código muerto tras eliminación de sus elementos DOM).
- `web/app.py` — añade `punto_medicion` al dict `nodo_seleccionado` en la respuesta JSON del endpoint `cliente_dashboard_telemetria_data`.
- `tests/test_dashboard_telemetria.py` — 5 tests nuevos (i–m): POST producción 200 ok, 400 sin m2_mes, 400 m2_mes negativo, 401 sin auth, 404 FASE2 deshabilitada.

```

- [ ] **Step 4: Actualizar CLAUDE.md**

Localizar la sección `### Nuevas funcionalidades` y reemplazar el bloque de "Último tema resuelto" / "Pendiente" con:

```
### Nuevas funcionalidades
Último tema resuelto: v2.82.0 — D7-B: panel KPI tabs (Energéticos/Económicos/Producción),
tarjetas v2 con badge delta, gauge FP (doughnut semicírculo), sparklines duales,
formulario POST producción mensual. Pestaña Producción visible sólo en rango 30d.
_tabActivo persiste entre re-fetches. punto_medicion añadido a nodo_seleccionado JSON.
Pendiente del usuario: validar si fórmula pct_costo_especifico=100/m² es intencional.
Pendiente: ejecutar migrations en Supabase:
  - 202606_usuario_clientes.sql
  - 202607_telemetria_jerarquia.sql
  - 202608_produccion_diaria.sql
  - 202609_mediciones_5min_horarias.sql
  - ALTER TABLE clientes ADD COLUMN IF NOT EXISTS chp_session_params JSONB;
```

Localizar la sección `### Integración Telemática` y actualizar:

```
### Integración Telemática
Último tema resuelto: v2.82.0 — D7-B completo: frontend KPIs tabs, gauge FP,
sparklines, formulario producción manual. Backend: punto_medicion en nodo_seleccionado.
Pendiente: ejecutar seed con --forzar en Supabase (si no se ejecutó); refrescar vistas
materializadas (REFRESH MATERIALIZED VIEW CONCURRENTLY mediciones_agregadas_5min/horarias);
frontend D7-C (si definido).
```

- [ ] **Step 5: Ejecutar suite completa**

```bash
pytest tests/test_dashboard_telemetria.py tests/test_telemetria_kpis.py -v
```

Resultado esperado: todos los tests PASSED (13 en test_dashboard_telemetria + 17 en test_telemetria_kpis = 30 tests).

- [ ] **Step 6: Commit final**

```bash
git add tests/test_dashboard_telemetria.py CHANGELOG.md CLAUDE.md
git commit -m "feat(fase2-D7-B): frontend KPIs telemetria con tabs, tarjetas, gauge PF y formulario produccion manual"
```
