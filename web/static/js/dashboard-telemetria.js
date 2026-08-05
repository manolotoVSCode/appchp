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
  const R_TX   = 28;                       // radio del círculo transformador
  const W_CBT  = 200; const H_CBT  = 64;  // rectángulo cuadro de baja tensión

  // Layout
  const NIVEL_H_TX  = 160;   // separación acometida → nivel transformador
  const NIVEL_H_CBT = 160;   // separación transformador → nivel CBT
  const MIN_SEP = 220;       // separación mínima entre centros de transformador
  const PAD_X   = 60;        // padding lateral del SVG (px)
  const PAD_Y   = 40;        // padding superior del SVG (px)

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

  // ── Fetch central ──────────────────────────────────────────────────────────
  async function fetchDatos() {
    if (_abort) _abort.abort();
    const controller = new AbortController();
    _abort = controller;

    _mostrarLoading(true);
    _ocultarError();

    const params = new URLSearchParams({ rango: _rango });
    if (_nodoId) params.set("nodo_id", _nodoId);

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

  /** Transformador: doble círculo con etiquetas centradas debajo del símbolo. */
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
    // Etiquetas centradas debajo del símbolo (evita colisión horizontal entre Txs)
    const nombreMatch = nodo.nombre.match(/^(T-\d+\.\d+)/);
    const kvaMatch    = nodo.nombre.match(/(\d+\s*kVA)/);
    const nombreCorto = nombreMatch ? nombreMatch[1] : nodo.nombre.substring(0, 12);
    const kvaCorto    = kvaMatch ? kvaMatch[1] : "";
    const kwh         = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
    const labels      = [nombreCorto, kvaCorto, kwh].filter((x) => x);
    const labelY      = cy2 + R_TX + 14;
    labels.forEach((l, i) => {
      const t = _el("text", {
        x: cx, y: labelY + i * 13,
        class: "unifilar-label-small", "text-anchor": "middle", "font-size": "11",
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
    if (kwhHijo != null) {
      const lx = (px + hx) / 2;
      const ly = miY - 4;
      const t = _el("text", { x: lx, y: ly, class: "unifilar-valor-linea" });
      t.textContent = fmt(kwhHijo) + " kWh";
      svgEl.appendChild(t);
    }
  }

  // ── Motor de layout ────────────────────────────────────────────────────────

  /**
   * renderUnifilar — layout vertical fijo 3 niveles.
   * Nivel 0: Acometida (centrada)
   * Nivel 1: Transformadores
   * Nivel 2: CBTs (1:1 con cada Tx)
   */
  function _renderUnifilar(raiz) {
    if (!raiz) return;
    const svg = $("unifilarSvg");
    if (!svg) return;
    svg.innerHTML = "";

    const wrapper = $("unifilar-wrapper");
    const wrapW  = wrapper ? wrapper.clientWidth - 48 : 900;

    // Nivel 0: acometida
    const transformadores = raiz.hijos || [];
    const nTx = Math.max(transformadores.length, 1);

    const svgW = Math.max(wrapW, nTx * MIN_SEP + PAD_X * 2);
    const svgH = PAD_Y + H_ACOM / 2 + NIVEL_H_TX + (R_TX * 2 + 12) + NIVEL_H_CBT + H_CBT + PAD_Y;

    svg.setAttribute("width", svgW);
    svg.setAttribute("height", svgH);
    svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

    // Nivel 0: Acometida (centrada)
    const aX = svgW / 2;
    const aY = PAD_Y + H_ACOM / 2;
    const gA = _crearGrupoNodo(raiz.id, "acometida_cfe");
    const { x: aOutX, y: aOutY } = _dibujarAcometida(gA, raiz, aX, aY, _nodoId === raiz.id);
    svg.appendChild(gA);

    // Nivel 1: Transformadores + Nivel 2: CBTs (1:1)
    const paso = svgW / (nTx + 1);
    transformadores.forEach((tx, i) => {
      const txX = paso * (i + 1);
      const txY = aY + NIVEL_H_TX + R_TX + 6;   // centro Tx entre los dos círculos

      // Línea acometida → Tx
      _dibujarLinea(svg, aOutX, aOutY, txX, txY - R_TX - 6,
        tx.energia_kwh, tx.potencia_nominal_kw);

      // Símbolo Tx
      const gTx = _crearGrupoNodo(tx.id, "transformador");
      _dibujarTransformador(gTx, tx, txX, txY, _nodoId === tx.id);
      svg.appendChild(gTx);

      // CBT hijo (1:1)
      const cbt = (tx.hijos || [])[0];
      if (cbt) {
        const cbtX = txX;
        const cbtY = txY + R_TX + 6 + NIVEL_H_CBT;   // centro del CBT

        // Línea Tx → CBT (vertical)
        _dibujarLinea(svg, txX, txY + R_TX + 6, cbtX, cbtY - H_CBT / 2,
          cbt.energia_kwh, cbt.potencia_nominal_kw);

        // Rectángulo CBT
        const gCBT = _crearGrupoNodo(cbt.id, "carga_final");
        _dibujarCBT(gCBT, cbt, cbtX, cbtY, _nodoId === cbt.id);
        svg.appendChild(gCBT);
      }
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

  /** Maneja click en un nodo del unifilar. */
  function _handleClickNodo(id, tipo) {
    const nId = typeof id === "number" ? id : parseInt(id, 10);
    _nodoId = nId;
    fetchDatos();
  }

  // ── Controles ──────────────────────────────────────────────────────────────
  function setNodo(id) {
    _nodoId = typeof id === "number" ? id : parseInt(id, 10);
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

  // ── Init ───────────────────────────────────────────────────────────────────
  fetchDatos();
})();
