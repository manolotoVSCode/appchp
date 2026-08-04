(function () {
  "use strict";

  // ── Paleta de colores ──────────────────────────────────────────────────────
  // Derivada de --color-primary del proyecto (#1F3A5F) y complementarios.
  const PALETA_RAMAS = [
    "#2E5C8A", "#3D7AB5", "#1F6B5C", "#2E8A6B",
    "#6B3D1F", "#8A5C2E", "#6B1F3D", "#8A2E5C",
    "#3D6B1F", "#5C8A2E", "#1F3D6B", "#2E5C8A",
  ];
  function _variante(hex, factor) {
    // Aclara un color hex mezclando con blanco (factor 0..1 = sin cambio..blanco)
    const r = parseInt(hex.slice(1,3),16), g=parseInt(hex.slice(3,5),16), b=parseInt(hex.slice(5,7),16);
    const mix = (c) => Math.round(c + (255 - c) * factor).toString(16).padStart(2,"0");
    return `#${mix(r)}${mix(g)}${mix(b)}`;
  }

  // ── Estado ─────────────────────────────────────────────────────────────────
  const root = document.getElementById("dashboard-telemetria-root");
  if (!root) return;

  const CLIENTE_ID = root.dataset.clienteId;
  const ENDPOINT   = root.dataset.endpoint;

  let _rango      = "24h";
  let _nodoId     = null;
  let _chartSun   = null;
  let _chartSerie = null;
  let _abort      = null;
  let _segmentoIds = []; // mapa: index de dataset → medidor_id

  // ── Helpers DOM ────────────────────────────────────────────────────────────
  const $  = (id) => document.getElementById(id);
  const fmt = (n, dec=2) => n == null ? "—" :
    Number(n).toLocaleString("es-MX", {maximumFractionDigits: dec, minimumFractionDigits: dec});

  function _mostrarError(msg) {
    const banner = $("telemetria-error-banner");
    if (banner) { $("telemetria-error-msg").textContent = msg; banner.classList.remove("d-none"); }
  }
  function _ocultarError() {
    const banner = $("telemetria-error-banner");
    if (banner) banner.classList.add("d-none");
  }
  function _mostrarLoading(visible) {
    const el = $("sunburst-loading");
    if (el) el.classList.toggle("d-none", !visible);
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
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        _mostrarLoading(false);
        if (data.error) { _mostrarError(data.error); return; }
        _renderTodo(data);
        $("ultima-actualizacion").textContent = "Actualizado " + new Date().toLocaleTimeString("es-MX");
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
    _renderSunburst(data.arbol_sunburst);
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

  // ── KPIs ───────────────────────────────────────────────────────────────────
  function _renderKPIs(kpis) {
    $("kpi-energia").textContent  = fmt(kpis.energia_total_kwh);
    $("kpi-demanda").textContent  = fmt(kpis.demanda_pico_kw);
    $("kpi-fp").textContent       = fmt(kpis.factor_potencia_promedio, 3);
    $("kpi-muestras").textContent = kpis.num_muestras != null
      ? kpis.num_muestras.toLocaleString("es-MX") : "—";
  }

  // ── Sunburst (Chart.js doughnut multi-anillo) ──────────────────────────────
  function _renderSunburst(raiz) {
    // Extraer transformadores (hijos de la acometida) y sus cargas
    const transformadores = raiz.hijos || [];
    const energiaAcometida = raiz.energia_kwh || 1;

    // Construir datasets
    // Dataset 0: anillo interno — acometida
    // Dataset 1: anillo medio — transformadores
    // Dataset 2: anillo externo — cargas finales

    const ds0 = { data: [energiaAcometida], backgroundColor: ["#1F3A5F"],
      hoverBackgroundColor: ["#2E5C8A"], borderWidth: 1,
      borderColor: "#fff", label: "Acometida" };

    const ds1Data = [], ds1Colors = [], ds1Hover = [], ds1Labels = [];
    const ds2Data = [], ds2Colors = [], ds2Hover = [], ds2Labels = [];
    _segmentoIds = { anillo1: [], anillo2: [] };

    let tIdx = 0;
    for (const t of transformadores) {
      const colorBase = PALETA_RAMAS[tIdx % PALETA_RAMAS.length];
      ds1Data.push(t.energia_kwh || 0);
      ds1Colors.push(colorBase);
      ds1Hover.push(_variante(colorBase, 0.15));
      ds1Labels.push(t.nombre);
      _segmentoIds.anillo1.push(t.id);

      const cargas = t.hijos || [];
      // Agrupar cargas < 5% de la energía del transformador en "Otros"
      const totalT = t.energia_kwh || 1;
      let otrosKwh = 0;
      for (const c of cargas) {
        const pct = (c.energia_kwh || 0) / totalT;
        if (pct < 0.05) {
          otrosKwh += c.energia_kwh || 0;
          _segmentoIds.anillo2.push(null); // "Otros" no navega
        } else {
          ds2Data.push(c.energia_kwh || 0);
          ds2Colors.push(_variante(colorBase, 0.4));
          ds2Hover.push(_variante(colorBase, 0.55));
          ds2Labels.push(c.nombre);
          _segmentoIds.anillo2.push(c.id);
        }
      }
      if (otrosKwh > 0) {
        ds2Data.push(otrosKwh);
        ds2Colors.push(_variante(colorBase, 0.6));
        ds2Hover.push(_variante(colorBase, 0.7));
        ds2Labels.push("Otros");
      }
      tIdx++;
    }

    const ds1 = { data: ds1Data, backgroundColor: ds1Colors,
      hoverBackgroundColor: ds1Hover, borderWidth: 1, borderColor: "#fff",
      label: "Transformadores", labels: ds1Labels };
    const ds2 = { data: ds2Data, backgroundColor: ds2Colors,
      hoverBackgroundColor: ds2Hover, borderWidth: 1, borderColor: "#fff",
      label: "Cargas", labels: ds2Labels };

    const config = {
      type: "doughnut",
      data: { datasets: [ds0, ds1, ds2] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "20%",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(ctx) {
                const ds = ctx.dataset;
                const lbl = ds.labels ? ds.labels[ctx.dataIndex] : raiz.nombre;
                const kwh = ctx.raw.toLocaleString("es-MX", {maximumFractionDigits: 1});
                return ` ${lbl}: ${kwh} kWh`;
              }
            }
          }
        },
        onClick(evt, elements) {
          if (!elements.length) return;
          const el = elements[0];
          const dsIdx = el.datasetIndex;
          const idx = el.index;
          let id = null;
          if (dsIdx === 1) id = (_segmentoIds.anillo1 || [])[idx];
          if (dsIdx === 2) id = (_segmentoIds.anillo2 || [])[idx];
          if (id) setNodo(id);
        }
      }
    };

    if (_chartSun) { _chartSun.destroy(); }
    const ctx = $("sunburstChart");
    if (ctx) _chartSun = new Chart(ctx, config);
  }

  // ── Serie temporal ─────────────────────────────────────────────────────────
  function _renderSerie(serie, nombreNodo) {
    const labels = (serie.labels || []).map((ts) => {
      try {
        const d = new Date(ts);
        if (_rango === "24h") return d.toLocaleTimeString("es-MX", {hour:"2-digit",minute:"2-digit"});
        return d.toLocaleDateString("es-MX", {day:"2-digit",month:"short"});
      } catch { return ts; }
    });

    const config = {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: `Potencia activa — ${nombreNodo}`,
          data: serie.potencia_kw || [],
          borderColor: "#2E5C8A",
          backgroundColor: "rgba(46,92,138,0.08)",
          pointRadius: labels.length > 200 ? 0 : 2,
          borderWidth: 1.5,
          tension: 0.2,
          fill: true,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
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

  // ── Controles ──────────────────────────────────────────────────────────────
  function setNodo(id) {
    _nodoId = id;
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
