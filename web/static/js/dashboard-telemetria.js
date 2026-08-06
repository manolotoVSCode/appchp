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

  let _rango      = "24h";
  let _nodoId     = null;   // nodo cuyo time-series se muestra en la gráfica
  let _arbolCache = null;   // último arbol_sunburst recibido del backend
  let _chartSerie = null;
  let _abort      = null;

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

  // ── Fetch central ──────────────────────────────────────────────────────────
  async function fetchDatos() {
    if (_abort) _abort.abort();
    const controller = new AbortController();
    _abort = controller;

    _mostrarLoading(true);
    _ocultarError();

    const params = new URLSearchParams({ rango: _rango });
    if (_nodoId !== null && _nodoId !== undefined &&
        !String(_nodoId).startsWith("grupo:")) {
      params.set("nodo_id", String(_nodoId));
    }

    try {
      const resp = await fetch(`${ENDPOINT}?${params}`, { signal: controller.signal });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.error) { _mostrarError(data.error); return; }
      _arbolCache = data.arbol_sunburst;
      _renderTodo(data);
      $("ultima-actualizacion").textContent =
        "Actualizado " + new Date().toLocaleTimeString("es-MX");
    } catch (e) {
      if (e.name === "AbortError") return;
      _mostrarError("Error al cargar datos de telemetría: " + e.message);
    } finally {
      if (!controller.signal.aborted) _mostrarLoading(false);
    }
  }

  // ── Render completo ────────────────────────────────────────────────────────
  function _renderTodo(data) {
    _renderBreadcrumbs(data.nodo_seleccionado);
    _renderKPIs(data.kpis);
    _renderUnifilar(data.arbol_sunburst);
    _renderSerie(data.serie_temporal, data.nodo_seleccionado.nombre);
    $("titulo-nodo").textContent = data.nodo_seleccionado.nombre;
    _renderComparativa(data.comparativa_mes_anterior);
  }

  // ── Breadcrumbs ────────────────────────────────────────────────────────────
  function _renderBreadcrumbs(nodo) {
    const nav = $("breadcrumbs-telemetria");
    if (!nav) return;
    const ol = nav.querySelector("ol");
    ol.innerHTML = "";
    // Mostrar solo los 2 últimos segmentos de la ruta
    const ruta = nodo.ruta_breadcrumbs || [];
    const segmentos = ruta.length > 2 ? ruta.slice(-2) : ruta;
    segmentos.forEach((seg, idx) => {
      const li = document.createElement("li");
      li.className = "breadcrumb-item";
      if (idx === segmentos.length - 1) {
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

  // ── KPIs ───────────────────────────────────────────────────────────────────
  function _renderKPIs(kpis) {
    $("kpi-energia").textContent  = fmt(kpis.energia_total_kwh);
    $("kpi-demanda").textContent  = fmt(kpis.demanda_pico_kw);
    $("kpi-fp").textContent       = fmt(kpis.factor_potencia_promedio, 3);
    $("kpi-muestras").textContent = kpis.num_muestras != null
      ? kpis.num_muestras.toLocaleString("es-MX") : "—";

    const costEl = $("kpi-costo");
    const hintEl = $("kpi-costo-hint");
    if (costEl) costEl.textContent = kpis.costo_mxn != null ? fmt(kpis.costo_mxn) : "N/D";
    if (hintEl) {
      const ref = kpis.precio_mes_referencia;
      const hints = {
        "factura_mes_exacto":   `Precio de ${ref || ""}`,
        "factura_mes_anterior": `Precio est. último mes disponible (${ref || ""})`,
        "promedio_12m":         "Precio promedio de los últimos 12 meses",
        "sin_datos":            "Sin facturas registradas para este cliente",
      };
      hintEl.textContent = hints[kpis.precio_fuente] || "";
    }
  }

  // ── Comparativa ────────────────────────────────────────────────────────────
  function _renderComparativa(comp) {
    const deltaEl = $("kpi-delta");
    const hintEl  = $("kpi-delta-hint");
    if (!deltaEl) return;
    if (!comp || !comp.disponible) {
      deltaEl.textContent = "N/D"; deltaEl.style.color = "";
      if (hintEl) hintEl.textContent = "Sin datos del mes anterior";
      return;
    }
    const pct = comp.energia_delta_pct;
    if (pct == null) { deltaEl.textContent = "N/D"; deltaEl.style.color = ""; }
    else {
      deltaEl.textContent = `${pct >= 0 ? "+" : ""}${pct.toLocaleString("es-MX", { maximumFractionDigits: 1 })}%`;
      deltaEl.style.color = pct > 0 ? "#dc3545" : "#198754";
    }
    if (hintEl) {
      const eStr = pct != null ? `Energía: ${pct >= 0 ? "+" : ""}${pct}%` : "";
      const cStr = comp.costo_delta_pct != null
        ? ` | Costo: ${comp.costo_delta_pct >= 0 ? "+" : ""}${comp.costo_delta_pct}%` : "";
      hintEl.textContent = eStr + cStr;
    }
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
    const kwh = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
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
      t2.textContent = fmt(nodo.energia_kwh) + " kWh";
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
    const kwh         = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
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
    const kwh = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
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
