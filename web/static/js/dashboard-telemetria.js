(function () {
  "use strict";

  // ── Constantes visuales ────────────────────────────────────────────────────
  const C_PRIMARIO   = "#1F3A5F";
  const C_PRIMARIO_L = "#2E5C8A";
  const C_CARGA      = "#f59e0b";   // naranja para cargas ficticias
  const C_SE_FILL    = "rgba(31,58,95,0.04)";
  const C_LINEA_NORM = "#6b7280";
  const C_LINEA_ALTA = "#eab308";
  const C_LINEA_CRIT = "#dc2626";

  // Dimensiones de nodos (px)
  const W_ACOM = 180; const H_ACOM = 64;
  const W_SE   = 140; const H_SE   = 48;
  const R_TX   = 22;                       // radio del círculo transformador
  const W_CARG = 160; const H_CARG = 56;

  // Layout
  const NIVEL_H = 140;    // separación vertical entre niveles (px)
  const MIN_SEP = 210;    // separación mínima horizontal entre nodos hermanos (px)
  const PAD_X   = 60;     // padding lateral del SVG (px)
  const PAD_Y   = 40;     // padding superior del SVG (px)

  // ── Estado ─────────────────────────────────────────────────────────────────
  const root = document.getElementById("dashboard-telemetria-root");
  if (!root) return;

  const CLIENTE_ID = root.dataset.clienteId;
  const ENDPOINT   = root.dataset.endpoint;

  let _rango         = "24h";
  let _nodoId        = null;   // nodo cuyo time-series se muestra en la gráfica
  let _nodoRaizId    = null;   // raíz del unifilar: null | número | "grupo:SE-N"
  let _arbolCache    = null;   // último arbol_sunburst recibido del backend
  let _chartSerie    = null;
  let _abort         = null;

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
    const loading = $("unifilar-loading");
    const svg     = $("unifilarSvg");
    if (loading) loading.style.display = visible ? "flex" : "none";
    if (svg)     svg.style.display     = visible ? "none" : "block";
  }

  // ── Fetch central ──────────────────────────────────────────────────────────
  function fetchDatos() {
    if (_abort) _abort.abort();
    _abort = new AbortController();
    _mostrarLoading(true);
    _ocultarError();

    const params = new URLSearchParams({ rango: _rango });
    if (_nodoId) params.set("nodo_id", _nodoId);

    fetch(`${ENDPOINT}?${params}`, { signal: _abort.signal })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((data) => {
        _mostrarLoading(false);
        if (data.error) { _mostrarError(data.error); return; }
        _arbolCache = data.arbol_sunburst;
        _renderTodo(data);
        $("ultima-actualizacion").textContent =
          "Actualizado " + new Date().toLocaleTimeString("es-MX");
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        _mostrarLoading(false);
        _mostrarError("Error al cargar datos de telemetría: " + e.message);
      });
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

  // ── Helpers de árbol ───────────────────────────────────────────────────────

  /** Construye índice id → nodo del arbol_sunburst (BFS). */
  function _indexarArbol(raiz) {
    const idx = {};
    const cola = [raiz];
    while (cola.length) {
      const n = cola.shift();
      idx[n.id] = n;
      (n.hijos || []).forEach((h) => cola.push(h));
    }
    return idx;
  }

  /** Agrupa transformadores por subestación derivada del nombre. */
  function _derivarSE(nombre) {
    const m = nombre.match(/^T-(\d+)/);
    return m ? `SE-${m[1]}` : "Otros";
  }


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

  /** Acometida CFE: rectángulo 180x64 con borde primario. */
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

  /** SE agrupada: rectángulo redondeado con borde punteado. */
  function _dibujarSE(g, nombre, nTx, kwh, cx, cy, seleccionado) {
    const x = cx - W_SE / 2;
    const y = cy - H_SE / 2;
    const rect = _el("rect", {
      x, y, width: W_SE, height: H_SE, rx: 8,
      fill: C_SE_FILL, stroke: C_PRIMARIO,
      "stroke-width": seleccionado ? 4 : 1.5,
      "stroke-dasharray": "4 3",
      class: "unifilar-fondo",
    });
    g.appendChild(rect);
    const kwhStr = kwh != null ? fmt(kwh) + " kWh" : "";
    g.appendChild(_multilineText(
      [nombre, `${nTx} transformadores`, kwhStr], cx, cy - 8, 14, "unifilar-label-small"
    ));
    return { x: cx, y: cy + H_SE / 2 };
  }

  /** Transformador: doble círculo. */
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
    // Etiqueta a la derecha
    const ex = cx + R_TX + 8;
    const kwh = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
    const nom = nodo.potencia_nominal_kw ? fmt(nodo.potencia_nominal_kw) + " kW nom." : "";
    [nodo.nombre, kwh, nom].forEach((l, i) => {
      const t = _el("text", { x: ex, y: cy - 10 + i * 14, class: "unifilar-label-small",
        "text-anchor": "start", "font-size": "11" });
      t.textContent = l || "";
      g.appendChild(t);
    });
    return { x: cx, y: cy2 + R_TX };
  }

  /** Carga final: rectángulo naranja. */
  function _dibujarCarga(g, nodo, cx, cy, seleccionado) {
    const x = cx - W_CARG / 2;
    const y = cy - H_CARG / 2;
    const rect = _el("rect", {
      x, y, width: W_CARG, height: H_CARG, rx: 6,
      fill: "rgba(245,158,11,0.08)", stroke: seleccionado ? "#b45309" : C_CARGA,
      "stroke-width": seleccionado ? 4 : 2,
      class: "unifilar-fondo",
    });
    g.appendChild(rect);
    const tipo = nodo.tipo_carga ? nodo.tipo_carga.replace(/_/g, " ") : "";
    const kwh  = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
    g.appendChild(_multilineText(
      [nodo.nombre, tipo, kwh], cx, cy - 12, 16, "unifilar-label-small"
    ));
    return { x: cx, y: cy + H_CARG / 2 };
  }

  /** Línea ortogonal de padre a hijo con etiqueta kW · kWh. */
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
   * renderUnifilar — función principal.
   * Determina la vista según _nodoRaizId y dibuja el SVG.
   */
  function _renderUnifilar(raiz) {
    if (!raiz) return;
    const svg = $("unifilarSvg");
    if (!svg) return;
    svg.innerHTML = "";

    const wrapper = $("unifilar-wrapper");
    const wrapW  = wrapper ? wrapper.clientWidth - 48 : 800;

    // ── Determinar modo de vista ──────────────────────────────────────────
    const idx = _indexarArbol(raiz);

    let vistaAcometida = null;  // nodo acometida actual (si aplica)
    let vistaSE        = null;  // nombre "SE-N" (si aplica)
    let vistaTx        = null;  // nodo transformador (si aplica)

    if (_nodoRaizId === null) {
      // Vista inicial: mostrar la acometida raíz y sus SEs
      vistaAcometida = raiz;
    } else if (typeof _nodoRaizId === "string" && _nodoRaizId.startsWith("grupo:")) {
      // Vista SE: la acometida padre + la SE seleccionada con sus transformadores
      vistaSE = _nodoRaizId.replace("grupo:", "");
      vistaAcometida = raiz;
    } else {
      // nodoRaizId es un id numérico → puede ser acometida o transformador
      const n = idx[_nodoRaizId];
      if (!n) { vistaAcometida = raiz; }
      else if (n.punto_medicion === "transformador") { vistaTx = n; vistaAcometida = raiz; }
      else { vistaAcometida = n; }
    }

    // ── Calcular SEs a mostrar ────────────────────────────────────────────
    const transformadoresActivos = vistaAcometida ? (vistaAcometida.hijos || []) : [];

    // Agrupar transformadores por SE
    const seMap = {}; // SE-N → [tx, ...]
    transformadoresActivos.forEach((tx) => {
      const se = _derivarSE(tx.nombre);
      if (!seMap[se]) seMap[se] = [];
      seMap[se].push(tx);
    });
    const seKeys = Object.keys(seMap).sort();

    // ── Posicionar nodos ──────────────────────────────────────────────────
    // Cada modo dibuja 2 o 3 niveles según la vista.

    let svgH = PAD_Y * 2;
    let svgW = wrapW;

    if (vistaTx) {
      // Vista transformador: Tx arriba, cargas abajo
      const cargas = vistaTx.hijos || [];
      const nCargas = Math.max(cargas.length, 1);
      svgW  = Math.max(wrapW, nCargas * MIN_SEP + PAD_X * 2);
      svgH  = PAD_Y + NIVEL_H * 2 + H_CARG + PAD_Y;

      svg.setAttribute("width", svgW);
      svg.setAttribute("height", svgH);
      svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

      const txX = svgW / 2; const txY = PAD_Y + R_TX + 6;
      const gTx = _crearGrupoNodo(vistaTx.id, vistaTx.punto_medicion, false);
      const { x: txOutX, y: txOutY } = _dibujarTransformador(gTx, vistaTx, txX, txY,
        _nodoId === vistaTx.id);
      svg.appendChild(gTx);

      const paso = svgW / (nCargas + 1);
      cargas.forEach((c, i) => {
        const cx = paso * (i + 1); const cy = txY + NIVEL_H;
        _dibujarLinea(svg, txOutX, txOutY, cx, cy - H_CARG / 2,
          c.energia_kwh, c.potencia_nominal_kw);
        const gC = _crearGrupoNodo(c.id, c.punto_medicion, true);
        _dibujarCarga(gC, c, cx, cy, _nodoId === c.id);
        svg.appendChild(gC);
      });

    } else if (vistaSE) {
      // Vista SE: acometida arriba, la SE seleccionada en nivel 2, sus Txs abajo
      const txsSE = seMap[vistaSE] || [];
      const nTx   = Math.max(txsSE.length, 1);
      svgW  = Math.max(wrapW, nTx * MIN_SEP + PAD_X * 2);
      svgH  = PAD_Y + NIVEL_H * 3 + H_CARG + PAD_Y;

      svg.setAttribute("width", svgW);
      svg.setAttribute("height", svgH);
      svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

      // Nivel 0: acometida
      const aX = svgW / 2; const aY = PAD_Y + H_ACOM / 2;
      const gA = _crearGrupoNodo(vistaAcometida.id, "acometida_cfe", false);
      const { x: aOutX, y: aOutY } = _dibujarAcometida(gA, vistaAcometida, aX, aY,
        _nodoId === vistaAcometida.id);
      svg.appendChild(gA);

      // Nivel 1: SE
      const seX = svgW / 2; const seY = aY + NIVEL_H;
      const kwhSE = txsSE.reduce((s, t) => s + (t.energia_kwh || 0), 0);
      const gSE = _crearGrupoNodo("grupo:" + vistaSE, "se_agrupacion", true);
      const { x: seOutX, y: seOutY } = _dibujarSE(gSE, vistaSE, txsSE.length, kwhSE,
        seX, seY, _nodoRaizId === "grupo:" + vistaSE);
      _dibujarLinea(svg, aOutX, aOutY, seX, seY - H_SE / 2, kwhSE, null);
      svg.appendChild(gSE);

      // Nivel 2: transformadores
      const paso = svgW / (nTx + 1);
      txsSE.forEach((tx, i) => {
        const txX = paso * (i + 1); const txY = seY + NIVEL_H;
        _dibujarLinea(svg, seOutX, seOutY, txX, txY - R_TX - 6,
          tx.energia_kwh, tx.potencia_nominal_kw);
        const gT = _crearGrupoNodo(tx.id, "transformador", false);
        _dibujarTransformador(gT, tx, txX, txY, _nodoId === tx.id);
        svg.appendChild(gT);
      });

    } else {
      // Vista inicial / acometida seleccionada: acometida + SEs agrupadas
      const nSE  = Math.max(seKeys.length, 1);
      svgW  = Math.max(wrapW, nSE * MIN_SEP + PAD_X * 2);
      svgH  = PAD_Y + NIVEL_H * 2 + H_SE + PAD_Y;

      svg.setAttribute("width", svgW);
      svg.setAttribute("height", svgH);
      svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

      // Nivel 0: acometida
      const aX = svgW / 2; const aY = PAD_Y + H_ACOM / 2;
      const gA = _crearGrupoNodo(vistaAcometida.id, "acometida_cfe", false);
      const { x: aOutX, y: aOutY } = _dibujarAcometida(gA, vistaAcometida, aX, aY,
        _nodoId === vistaAcometida.id);
      svg.appendChild(gA);

      // Nivel 1: SEs
      const paso = svgW / (nSE + 1);
      seKeys.forEach((se, i) => {
        const txs  = seMap[se];
        const seX  = paso * (i + 1); const seY = aY + NIVEL_H;
        const kwhSE = txs.reduce((s, t) => s + (t.energia_kwh || 0), 0);
        _dibujarLinea(svg, aOutX, aOutY, seX, seY - H_SE / 2, kwhSE, null);
        const gSE = _crearGrupoNodo("grupo:" + se, "se_agrupacion", false);
        _dibujarSE(gSE, se, txs.length, kwhSE, seX, seY,
          _nodoRaizId === "grupo:" + se);
        svg.appendChild(gSE);
      });
    }
  }

  /**
   * Crea un <g> con clase y data-nodo-id.
   * Añade event listeners de click y hover.
   */
  function _crearGrupoNodo(id, tipo, esCargaFicticia) {
    const g = _el("g", { class: "unifilar-nodo", "data-nodo-id": String(id) });
    if (esCargaFicticia) g.classList.add("unifilar-carga-ficticia");
    if (tipo === "se_agrupacion") g.classList.add("unifilar-se-agrupacion");

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
    if (tipo === "carga_final") {
      // Click en carga: actualiza KPIs/gráfica sin cambiar nodoRaiz
      _nodoId = typeof id === "number" ? id : parseInt(id, 10);
      fetchDatos();
      return;
    }
    if (tipo === "se_agrupacion") {
      _nodoRaizId = String(id); // "grupo:SE-N"
      if (!_nodoId) {
        // Usar el primer Tx de la SE como nodo para KPIs
        if (_arbolCache) {
          const seNombre = String(id).replace("grupo:", "");
          const txs = (_arbolCache.hijos || []).filter(
            (n) => _derivarSE(n.nombre) === seNombre
          );
          if (txs.length) _nodoId = txs[0].id;
        }
      }
    } else if (tipo === "transformador") {
      _nodoRaizId = typeof id === "number" ? id : parseInt(id, 10);
      _nodoId = _nodoRaizId;
    } else if (tipo === "acometida_cfe") {
      _nodoRaizId = typeof id === "number" ? id : parseInt(id, 10);
      _nodoId = _nodoRaizId;
    }
    fetchDatos();
  }

  // ── Controles ──────────────────────────────────────────────────────────────
  /**
   * Navega a un nodo por su id (llamado desde breadcrumbs).
   * También actualiza _nodoRaizId para que el unifilar refleje el nivel correcto.
   */
  function setNodo(id) {
    _nodoId = id;
    // Resetear la raíz del unifilar según el tipo del nodo en caché
    if (_arbolCache) {
      const idx = _indexarArbol(_arbolCache);
      const nodo = idx[id];
      if (nodo) {
        if (nodo.punto_medicion === "acometida_cfe") {
          _nodoRaizId = null;          // vista inicial (acometida + SEs)
        } else if (nodo.punto_medicion === "transformador") {
          _nodoRaizId = id;            // vista transformador + cargas
        }
        // carga_final: no cambia _nodoRaizId (el usuario sigue viendo el Tx padre)
      }
    }
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
