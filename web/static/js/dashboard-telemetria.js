(function () {
  "use strict";

  // ── Constantes visuales ────────────────────────────────────────────────────
  const C_PRIMARIO   = "#1F3A5F";
  const C_PRIMARIO_L = "#2E5C8A";
  const C_CARGA      = "#f59e0b";   // naranja para cargas
  const C_LINEA_NORM = "#6b7280";
  const C_LINEA_ALTA = "#eab308";
  const C_LINEA_CRIT = "#dc2626";

  // Dimensiones de nodos (px)
  const W_ACOM = 220; const H_ACOM = 64;
  const W_SE   = 100; const H_SE   = 40;   // subestación virtual (no existe en BD)
  const R_TX   = 26;                        // radio del círculo transformador
  const W_CBT  = 200; const H_CBT  = 64;   // cuadro de baja tensión

  // Layout
  const NIVEL_H = 100;   // separación entre centros de nivel (px)
  const MIN_SEP = 220;   // separación mínima entre centros de Tx (px)
  const PAD_X   = 60;
  const PAD_Y   = 30;

  // ── Estado ─────────────────────────────────────────────────────────────────
  const root = document.getElementById("dashboard-telemetria-root");
  if (!root) return;

  const CLIENTE_ID = root.dataset.clienteId;
  const ENDPOINT   = root.dataset.endpoint;

  let _rango        = "24h";
  let _nodoId       = null;   // nodo cuyo time-series se muestra en la gráfica
  let _arbolCache   = null;   // último arbol_sunburst recibido del backend
  let _chartSerie   = null;
  let _abort        = null;
  let _rangoEnCurso = null;   // rango del fetch actualmente en vuelo (debounce)

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

  // ── Helpers DOM ────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const fmt = (n, dec = 2) =>
    n == null ? "—" :
    Number(n).toLocaleString("es-MX", { maximumFractionDigits: dec, minimumFractionDigits: dec });

  function _mostrarError(msg) {
    const b = $("telemetria-error-banner");
    if (b) { $("telemetria-error-msg").textContent = msg; b.classList.remove("d-none"); }
  }
  function _ocultarError() {
    const b = $("telemetria-error-banner");
    if (b) b.classList.add("d-none");
  }
  function _mostrarLoading(visible) {
    const badge = $("header-loading-badge");
    if (badge) badge.style.display = visible ? "inline" : "none";
  }

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

    // energia_kwh no muestra sparkline (evita confusión con segunda serie).
    const hasSpark = key !== "energia_kwh"
      && kpi.sparkline_actual && kpi.sparkline_actual.length > 0;
    const mostrarAnt = hasSpark && kpi.sparkline_anterior;
    const sparkHtml = hasSpark
      ? `<div class="kpi-sparkline-wrap">
           <canvas id="sp-${key}-act" height="32"></canvas>
           ${mostrarAnt ? `<canvas id="sp-${key}-ant" height="32"></canvas>` : ""}
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

  // ── Formulario de captura de producción mensual ──────────────────────────
  const _PROD_DEFAULT = 1200000;

  async function _postProduccion(anio, mes, m2) {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
    return fetch(
      `/clientes/${CLIENTE_ID}/telemetria/produccion`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ anio, mes, m2_mes: m2 }),
      }
    );
  }

  function _renderFormularioProduccion(anio, mes, m2Existente) {
    const wrap = document.createElement("div");
    wrap.className = "mt-3 pt-2 border-top";
    const valorInicial = m2Existente != null ? m2Existente : _PROD_DEFAULT;
    wrap.innerHTML = `
      <p class="small text-muted mb-1" style="font-size:.7rem">
        Producción del mes ${mes}/${anio} (m² totales):
      </p>
      <div class="d-flex gap-2 align-items-center">
        <input type="number" id="prod-m2-input" class="form-control form-control-sm"
               value="${valorInicial}" min="1" max="100000000" step="1"
               style="max-width:120px">
        <button type="button" id="btn-guardar-prod" class="btn btn-sm btn-primary">
          Guardar
        </button>
      </div>
      <p class="text-muted mb-0 mt-1" style="font-size:.65rem">
        Ingresa m² totales del mes y haz click en Guardar para calcular los KPIs de producción.
      </p>
      <div id="prod-feedback" class="mt-1" style="min-height:1.1em;font-size:.68rem"></div>
    `;

    requestAnimationFrame(() => {
      const btn   = document.getElementById("btn-guardar-prod");
      const input = document.getElementById("prod-m2-input");
      const fb    = document.getElementById("prod-feedback");
      if (!btn || !input) return;

      btn.addEventListener("click", async () => {
        const m2 = parseFloat(input.value);
        if (isNaN(m2) || m2 <= 0) {
          if (fb) { fb.textContent = "Ingresa un valor válido > 0."; fb.style.color = "#dc3545"; }
          return;
        }
        btn.disabled = true;
        if (fb) { fb.textContent = "Guardando…"; fb.style.color = "#6b7280"; }
        try {
          const resp = await _postProduccion(anio, mes, m2);
          const json = await resp.json().catch(() => ({}));
          if (!resp.ok) {
            if (fb) { fb.textContent = json.error || `Error ${resp.status}`; fb.style.color = "#dc3545"; }
          } else {
            if (fb) { fb.textContent = `Guardado: ${json.registros} días. Actualizando KPIs…`; fb.style.color = "#198754"; }
            fetchDatos();
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
      // Si ya hay producción registrada, pre-llenar con ese valor y NO auto-submit.
      const m2Existente = (kpisPaneles.produccion?.produccion_m2?.valor > 0)
        ? kpisPaneles.produccion.produccion_m2.valor
        : null;
      panes.produccion.appendChild(_renderFormularioProduccion(anio, mes, m2Existente));
    }

    // Restaurar pestaña activa (persiste entre re-fetches)
    _activarTab(_tabActivo);
  }

  // ── Fetch central ──────────────────────────────────────────────────────────
  async function fetchDatos() {
    if (_abort) _abort.abort();
    const controller = new AbortController();
    _abort = controller;
    _rangoEnCurso = _rango;

    // Ocultar pestaña Producción optimistamente: solo debe verse en rango 30d.
    // Se aplica antes de recibir respuesta para evitar flash si el rango cambia.
    const tabProduccionBtn = $("tab-produccion");
    if (tabProduccionBtn && _rango !== "30d") {
      tabProduccionBtn.style.display = "none";
      if (_tabActivo === "produccion") { _tabActivo = "energeticos"; _activarTab(_tabActivo); }
    }

    _mostrarLoading(true);
    _ocultarError();

    const params = new URLSearchParams({ rango: _rango });
    if (_nodoId !== null && _nodoId !== undefined) {
      params.set("nodo_id", String(_nodoId));
    }

    try {
      const resp = await fetch(`${ENDPOINT}?${params}`, { signal: controller.signal });
      // Error HTTP: mostrar banner pero NO limpiar la vista previa
      if (!resp.ok) { _mostrarError(`Error al cargar datos (HTTP ${resp.status})`); return; }
      const data = await resp.json();
      // Guardia: si este fetch fue abortado mientras se leía el body, no renderizar
      if (controller.signal.aborted) return;
      if (data.error) { _mostrarError(data.error); return; }
      _arbolCache = data.arbol_sunburst;
      _renderTodo(data);
      $("ultima-actualizacion").textContent =
        "Actualizado " + new Date().toLocaleTimeString("es-MX");
    } catch (e) {
      if (e.name === "AbortError") return;
      _mostrarError("Error al cargar datos de telemetría: " + e.message);
    } finally {
      _rangoEnCurso = null;
      if (!controller.signal.aborted) _mostrarLoading(false);
    }
  }

  // ── Breadcrumb navegable sobre el unifilar ─────────────────────────────────
  function _renderUnifilarBreadcrumb(nodo) {
    const ol = $("unifilar-breadcrumb-ol");
    if (!ol) return;
    ol.innerHTML = "";
    const ruta = (nodo.ruta_breadcrumbs || []);
    ruta.forEach((seg, idx) => {
      const li = document.createElement("li");
      li.className = "breadcrumb-item";
      if (idx === ruta.length - 1) {
        // Nodo actual: texto plano
        li.classList.add("active");
        li.setAttribute("aria-current", "page");
        li.textContent = seg.nombre;
      } else {
        // Ancestro: enlace clicable
        const a = document.createElement("a");
        a.href = "#";
        a.textContent = seg.nombre;
        a.dataset.nodoId = String(seg.id);
        a.addEventListener("click", (e) => {
          e.preventDefault();
          setNodo(seg.id);
        });
        li.appendChild(a);
      }
      ol.appendChild(li);
    });
  }

  // ── Render completo ────────────────────────────────────────────────────────
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

  // ── Breadcrumbs ────────────────────────────────────────────────────────────
  function _renderBreadcrumbs(nodo) {
    const nav = $("breadcrumbs-telemetria");
    if (!nav) return;
    const ol = nav.querySelector("ol");
    ol.innerHTML = "";
    const ruta = nodo.ruta_breadcrumbs || [];
    ruta.forEach((seg, idx) => {
      const li = document.createElement("li");
      li.className = "breadcrumb-item";
      if (idx === ruta.length - 1) {
        li.classList.add("active");
        li.setAttribute("aria-current", "page");
        li.textContent = seg.nombre;
      } else {
        li.innerHTML = `<a href="#" data-nodo-id="${seg.id}">${seg.nombre}</a>`;
        li.querySelector("a").addEventListener("click", (e) => {
          e.preventDefault();
          setNodo(seg.id);
        });
      }
      ol.appendChild(li);
    });
  }

  // ── Serie temporal ─────────────────────────────────────────────────────────
  function _renderSerie(serie, nombreNodo) {
    const labels = (serie.labels || []).map((ts) => {
      try {
        const d = new Date(ts);
        return _rango === "24h"
          ? d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })
          : d.toLocaleDateString("es-MX", { day: "2-digit", month: "short" });
      } catch { return ts; }
    });
    const config = {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: `Potencia activa — ${nombreNodo}`,
          data: serie.potencia_kw || [],
          borderColor: C_PRIMARIO_L,
          backgroundColor: "rgba(46,92,138,0.08)",
          pointRadius: labels.length > 200 ? 0 : 2,
          borderWidth: 1.5, tension: 0.2, fill: true,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { maxTicksLimit: 12, maxRotation: 0 } },
          y: { title: { display: true, text: "kW" }, beginAtZero: true }
        }
      }
    };
    if (_chartSerie) { _chartSerie.destroy(); }
    const ctx = $("serieTemporalChart");
    if (ctx) _chartSerie = new Chart(ctx, config);
  }

  // ════════════════════════════════════════════════════════════════════════════
  // UNIFILAR SVG
  // ════════════════════════════════════════════════════════════════════════════

  // ── SVG helpers ────────────────────────────────────────────────────────────

  const NS = "http://www.w3.org/2000/svg";

  function _el(tag, attrs = {}) {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
  }

  function _text(txt, x, y, cls) {
    const t = _el("text", { x, y, class: cls || "unifilar-label" });
    t.textContent = txt;
    return t;
  }

  function _multilineText(lines, cx, baseY, lineH, cls) {
    const g = _el("g");
    lines.forEach((l, i) => {
      if (l == null || l === "") return;
      g.appendChild(_text(l, cx, baseY + i * lineH, cls));
    });
    return g;
  }

  /** Clase CSS de la línea según % de carga. */
  function _claseLinea(kwActivo, kwNominal) {
    if (!kwNominal || kwNominal <= 0) return "unifilar-linea-normal";
    const pct = kwActivo / kwNominal;
    if (pct >= 0.95) return "unifilar-linea-critica";
    if (pct >= 0.80) return "unifilar-linea-alta";
    return "unifilar-linea-normal";
  }

  // ── Dibujo de nodos ────────────────────────────────────────────────────────

  /** Acometida CFE: rectángulo 220x64 con borde primario. */
  function _dibujarAcometida(g, nodo, cx, cy, seleccionado) {
    const x = cx - W_ACOM / 2;
    const y = cy - H_ACOM / 2;
    const rect = _el("rect", {
      x, y, width: W_ACOM, height: H_ACOM, rx: 6,
      fill: "#eef2f7", stroke: C_PRIMARIO,
      "stroke-width": seleccionado ? 4 : 2,
      class: "unifilar-fondo",
    });
    g.appendChild(rect);
    const kwh = nodo.energia_kwh != null ? fmt(nodo.energia_kwh, 0) + " kWh" : "";
    g.appendChild(_multilineText(
      [nodo.nombre, kwh], cx, cy - 10, 16, "unifilar-label"
    ));
    // punto de conexión inferior
    return { x: cx, y: cy + H_ACOM / 2 };
  }

  /** Subestación virtual: rectángulo punteado 100×40, borde azul primario. */
  function _dibujarSE(g, nodo, cx, cy, seleccionado) {
    const x = cx - W_SE / 2;
    const y = cy - H_SE / 2;
    g.appendChild(_el("rect", {
      x, y, width: W_SE, height: H_SE, rx: 6,
      fill: "rgba(31,58,95,0.06)",
      stroke: seleccionado ? C_PRIMARIO : C_PRIMARIO_L,
      "stroke-width": seleccionado ? 3 : 1.5,
      "stroke-dasharray": "5,3",
      class: "unifilar-fondo",
    }));
    const t1 = _el("text", {
      x: cx, y: cy - 5,
      class: "unifilar-label", "text-anchor": "middle",
      "font-size": "12", "font-weight": "bold",
    });
    t1.textContent = nodo.nombre;
    g.appendChild(t1);
    if (nodo.energia_kwh != null) {
      const t2 = _el("text", {
        x: cx, y: cy + 9,
        class: "unifilar-label-small", "text-anchor": "middle", "font-size": "10",
      });
      t2.textContent = fmt(nodo.energia_kwh, 0) + " kWh";
      g.appendChild(t2);
    }
    return { x: cx, y: cy + H_SE / 2 };
  }

  /** Transformador: doble círculo con etiquetas a la derecha del símbolo. */
  function _dibujarTransformador(g, nodo, cx, cy, seleccionado) {
    const cy1 = cy - 6; const cy2 = cy + 6;
    const sw = seleccionado ? 3 : 1.5;
    g.appendChild(_el("circle", {
      cx, cy: cy1, r: R_TX, fill: "white",
      stroke: C_PRIMARIO, "stroke-width": sw, class: "unifilar-fondo",
    }));
    g.appendChild(_el("circle", {
      cx, cy: cy2, r: R_TX, fill: "rgba(255,255,255,0.7)",
      stroke: C_PRIMARIO, "stroke-width": sw, class: "unifilar-fondo",
    }));
    // Etiquetas a la derecha: elimina solape con líneas de conexión
    const nombreMatch = nodo.nombre.match(/^(T-\d+\.\d+)/);
    const kvaMatch    = nodo.nombre.match(/(\d+\s*kVA)/);
    const nombreCorto = nombreMatch ? nombreMatch[1] : nodo.nombre.substring(0, 12);
    const kvaCorto    = kvaMatch ? kvaMatch[1] : "";
    const kwh         = nodo.energia_kwh != null ? fmt(nodo.energia_kwh, 0) + " kWh" : "";
    const lx = cx + R_TX + 44;
    [
      [nombreCorto, "12", "bold"],
      [kvaCorto,    "10", "normal"],
      [kwh,         "10", "bold"],
    ].forEach(([l, fs, fw], i) => {
      if (!l) return;
      const t = _el("text", {
        x: lx, y: cy - 8 + i * 14,
        class: "unifilar-label-small", "text-anchor": "start",
        "font-size": fs, "font-weight": fw,
      });
      t.textContent = l;
      g.appendChild(t);
    });
    return { x: cx, y: cy2 + R_TX };
  }

  /** Cuadro de Baja Tensión (CBT): rectángulo naranja 200×64. */
  function _dibujarCBT(g, nodo, cx, cy, seleccionado) {
    const x = cx - W_CBT / 2;
    const y = cy - H_CBT / 2;
    const rect = _el("rect", {
      x, y, width: W_CBT, height: H_CBT, rx: 6,
      fill: "rgba(245,158,11,0.08)",
      stroke: seleccionado ? "#b45309" : C_CARGA,
      "stroke-width": seleccionado ? 4 : 2,
      class: "unifilar-fondo",
    });
    g.appendChild(rect);
    const nom = nodo.potencia_nominal_kw != null
      ? fmt(nodo.potencia_nominal_kw, 0) + " kW nom."
      : "";
    const kwh = nodo.energia_kwh != null ? fmt(nodo.energia_kwh, 0) + " kWh" : "";
    g.appendChild(_multilineText(
      [nodo.nombre, nom, kwh], cx, cy - 12, 16, "unifilar-label-small"
    ));
    return { x: cx, y: cy + H_CBT / 2 };
  }

  /** Línea ortogonal de padre a hijo con etiqueta kWh. */
  function _dibujarLinea(svgEl, px, py, hx, hy, kwhHijo, kwNomHijo) {
    const miY = py + (hy - py) / 2;
    const d = `M ${px} ${py} L ${px} ${miY} L ${hx} ${miY} L ${hx} ${hy}`;
    const cls = _claseLinea(kwhHijo, kwNomHijo);
    svgEl.appendChild(_el("path", { d, class: cls }));
    // Etiqueta sobre el segmento horizontal
  }

  // ── Motor de layout ────────────────────────────────────────────────────────

  /**
   * Agrupa transformadores por SE derivada del nombre (regex /^T-(\d+)/).
   * Devuelve nodos SE virtuales con IDs string "grupo:SE-N".
   */
  function _agruparPorSE(transformadores) {
    const grupos = new Map();
    transformadores.forEach((tx) => {
      const m = tx.nombre.match(/^T-(\d+)/);
      const key = m ? m[1] : "X";
      if (!grupos.has(key)) grupos.set(key, []);
      grupos.get(key).push(tx);
    });
    return Array.from(grupos.entries()).map(([num, txs]) => ({
      id: `grupo:SE-${num}`,
      nombre: `SE-${num}`,
      punto_medicion: "subestacion",
      energia_kwh: txs.reduce((s, t) => s + (t.energia_kwh || 0), 0),
      potencia_nominal_kw: txs.reduce((s, t) => s + (t.potencia_nominal_kw || 0), 0),
      costo_mxn: txs.reduce((s, t) => s + (t.costo_mxn || 0), 0),
      hijos: txs,
    }));
  }

  /**
   * renderUnifilar — layout vertical fijo 4 niveles.
   * Nivel 0: Acometida (centrada)
   * Nivel 1: Subestaciones virtuales SE (agrupan Txs por prefijo T-N)
   * Nivel 2: Transformadores (distribuidos uniformemente)
   * Nivel 3: CBTs (1:1 con cada Tx, alineados verticalmente)
   */
  function _renderUnifilar(raiz) {
    if (!raiz) return;
    const svg = $("unifilarSvg");
    if (!svg) return;
    svg.innerHTML = "";

    const wrapper = $("unifilar-wrapper");
    const wrapW  = wrapper ? wrapper.clientWidth - 48 : 900;

    const gruposSE    = _agruparPorSE(raiz.hijos || []);
    const todosLosTxs = gruposSE.flatMap((se) => se.hijos);
    const nTx = Math.max(todosLosTxs.length, 1);

    const svgW = Math.max(wrapW, nTx * MIN_SEP + PAD_X * 2);

    // Y de cada nivel (centros)
    const yAcom = PAD_Y + H_ACOM / 2;
    const ySE   = yAcom + NIVEL_H;
    const yTx   = ySE   + NIVEL_H;
    const yCbt  = yTx   + NIVEL_H;
    const svgH  = yCbt  + H_CBT / 2 + PAD_Y;

    svg.setAttribute("width",   svgW);
    svg.setAttribute("height",  svgH);
    svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

    // X de cada Tx: distribuidos uniformemente sobre el ancho del SVG
    const pasoTx = svgW / (nTx + 1);
    const txXmap = new Map();
    todosLosTxs.forEach((tx, i) => txXmap.set(tx.id, pasoTx * (i + 1)));

    // Nivel 0: Acometida
    const aX = svgW / 2;
    const gA = _crearGrupoNodo(raiz.id, "acometida_cfe");
    const { x: aOutX, y: aOutY } =
      _dibujarAcometida(gA, raiz, aX, yAcom, _nodoId === raiz.id);
    svg.appendChild(gA);


    // Niveles 1-3: SE → Tx → CBT
    gruposSE.forEach((se) => {
      // SE se centra en el promedio X de sus Txs hijos
      const seXs = se.hijos.map((tx) => txXmap.get(tx.id));
      const seX  = seXs.reduce((a, b) => a + b, 0) / seXs.length;

      // Línea Acometida → SE
      _dibujarLinea(svg, aOutX, aOutY, seX, ySE - H_SE / 2,
        se.energia_kwh, se.potencia_nominal_kw);

      // Símbolo SE
      const gSE = _crearGrupoNodo(se.id, "subestacion");
      _dibujarSE(gSE, se, seX, ySE, String(_nodoId) === se.id);
      svg.appendChild(gSE);

      // Cada Tx hijo de esta SE
      se.hijos.forEach((tx) => {
        const txX = txXmap.get(tx.id);

        // Línea SE → Tx
        _dibujarLinea(svg, seX, ySE + H_SE / 2, txX, yTx - R_TX - 6,
          tx.energia_kwh, tx.potencia_nominal_kw);

        // Símbolo Tx
        const gTx = _crearGrupoNodoVisual(tx.id);
        _dibujarTransformador(gTx, tx, txX, yTx, _nodoId === tx.id);
        svg.appendChild(gTx);

        // CBT hijo (1:1)
        const cbt = (tx.hijos || [])[0];
        if (cbt) {
          _dibujarLinea(svg, txX, yTx + R_TX + 6, txX, yCbt - H_CBT / 2,
            cbt.energia_kwh, cbt.potencia_nominal_kw);
          const gCBT = _crearGrupoNodo(cbt.id, "carga_final");
          _dibujarCBT(gCBT, cbt, txX, yCbt, _nodoId === cbt.id);
          svg.appendChild(gCBT);
        }
      });
    });
  }

  /**
   * Crea un <g> con clase y data-nodo-id.
   * Añade event listeners de click y hover.
   */
  function _crearGrupoNodo(id, tipo) {
    const g = _el("g", { class: "unifilar-nodo", "data-nodo-id": String(id) });

    g.addEventListener("click", () => _handleClickNodo(id, tipo));

    const wrapper = $("unifilar-wrapper");
    g.addEventListener("mouseenter", () => {
      if (wrapper) wrapper.classList.add("hovering");
      g.classList.add("unifilar-highlight");
    });
    g.addEventListener("mouseleave", () => {
      if (wrapper) wrapper.classList.remove("hovering");
      g.classList.remove("unifilar-highlight");
    });
    return g;
  }

  /** Grupo visual sin click (hover únicamente). Usado para transformadores. */
  function _crearGrupoNodoVisual(id) {
    const g = _el("g", {
      class: "unifilar-nodo",
      "data-nodo-id": String(id),
      style: "cursor:default",
    });
    const wrapper = $("unifilar-wrapper");
    g.addEventListener("mouseenter", () => {
      if (wrapper) wrapper.classList.add("hovering");
      g.classList.add("unifilar-highlight");
    });
    g.addEventListener("mouseleave", () => {
      if (wrapper) wrapper.classList.remove("hovering");
      g.classList.remove("unifilar-highlight");
    });
    return g;
  }

  /** Maneja click en un nodo del unifilar. */
  function _handleClickNodo(id, tipo) {
    _nodoId = typeof id === "string" && id.startsWith("grupo:") ? id : parseInt(id, 10);
    fetchDatos();
  }

  // ── Controles ──────────────────────────────────────────────────────────────
  function setNodo(id) {
    _nodoId = typeof id === "string" && id.startsWith("grupo:") ? id : parseInt(id, 10);
    fetchDatos();
  }

  function setRango(r) {
    // Debounce: ignorar si este rango ya está en vuelo
    if (r === _rangoEnCurso) return;
    _rango = r;
    document.querySelectorAll("#rango-selector button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.rango === r);
    });
    fetchDatos();
  }

  // ── Event listeners ────────────────────────────────────────────────────────
  document.querySelectorAll("#rango-selector button").forEach((btn) => {
    btn.addEventListener("click", () => setRango(btn.dataset.rango));
  });
  const btnReintentar = $("btn-reintentar");
  if (btnReintentar) btnReintentar.addEventListener("click", fetchDatos);

  document.querySelectorAll("#kpi-tabs button[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      _tabActivo = btn.dataset.tab;
      _activarTab(_tabActivo);
    });
  });

  // ── Init ───────────────────────────────────────────────────────────────────
  fetchDatos();
})();
