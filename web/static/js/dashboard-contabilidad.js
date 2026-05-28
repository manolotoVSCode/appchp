/**
 * dashboard-contabilidad.js
 * Client-side rendering del dashboard de Contabilidad Energética.
 * Fetch al endpoint /clientes/<id>/dashboard/contabilidad/data
 * Escucha evento dashboardDataChanged para refrescar al cambiar meses.
 */

(function () {
  "use strict";

  // ── Referencias DOM ───────────────────────────────────────────────────────
  const root = document.getElementById("dashboard-contabilidad-root");
  if (!root) return;

  const CLIENTE_ID = parseInt(root.dataset.clienteId, 10);
  const DATA_URL   = `/clientes/${CLIENTE_ID}/dashboard/contabilidad/data`;

  const spinner    = document.getElementById("dashboard-spinner");
  const errorBanner= document.getElementById("dashboard-error-banner");
  const errorMsg   = document.getElementById("dashboard-error-msg");
  const btnReintentar = document.getElementById("btn-reintentar");

  // ── Instancias Chart.js ───────────────────────────────────────────────────
  let chartDemanda       = null;
  let chartConsumo       = null;
  let chartCostoPromedio = null;
  let quesoChart         = null;
  let chartGasConsumo    = null;
  let chartGasCostos     = null;
  let chartPpaConsumo    = null;
  let chartPpaCosto      = null;

  let quesoDatos    = null;
  let filtroActivo  = "__todos__";
  let esPPA         = false;  // se actualiza en hidratarDashboardContabilidad

  // ── AbortController + debounce ────────────────────────────────────────────
  let _abortCtrl  = null;
  let _debounceId = null;
  const DEBOUNCE_MS = 300;

  // ── Colores ───────────────────────────────────────────────────────────────
  const COLOR_PUNTA      = "rgba(216,90,90,0.75)";
  const COLOR_INTERMEDIO = "rgba(232,181,71,0.85)";
  const COLOR_BASE       = "rgba(31,122,76,0.70)";
  const COLOR_LINEA      = "#1A2D3F";
  const COLOR_GAS_CONSUMO= "rgba(232,181,71,0.80)";
  const COLOR_GAS_LINEA  = "#1F7A4C";
  const COLOR_GAS_MOL    = "rgba(200,148,111,0.85)";
  const COLOR_GAS_TRA    = "rgba(232,196,160,0.85)";

  // ── Plugin inline labels ──────────────────────────────────────────────────
  const labelPlugin = {
    id: "inlineLabels",
    afterDatasetsDraw(chart) {
      const ctx = chart.ctx;
      chart.data.datasets.forEach((ds, i) => {
        if (!ds._showLabels) return;
        const meta = chart.getDatasetMeta(i);
        meta.data.forEach((el, j) => {
          const val = ds.data[j];
          if (val == null) return;
          ctx.save();
          ctx.fillStyle = "#212529";
          ctx.font = "bold 10px sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(typeof val === "number" ? val.toFixed(4) : val, el.x, el.y - 4);
          ctx.restore();
        });
      });
    }
  };

  const gasLabelPlugin = {
    id: "gasInlineLabels",
    afterDatasetsDraw(chart) {
      const ctx = chart.ctx;
      chart.data.datasets.forEach((ds, i) => {
        if (!ds._gasLabels) return;
        const meta = chart.getDatasetMeta(i);
        meta.data.forEach((el, j) => {
          const val = ds.data[j];
          if (val == null) return;
          ctx.save();
          ctx.fillStyle = "#212529";
          ctx.font = "bold 10px sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(typeof val === "number" ? val.toFixed(2) : val, el.x, el.y - 4);
          ctx.restore();
        });
      });
    }
  };

  const pieSlicePlugin = {
    id: "pieSliceLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      const ds = chart.data.datasets[0];
      const total = ds.data.reduce((a, b) => a + b, 0);
      if (!total) return;
      const meta = chart.getDatasetMeta(0);
      meta.data.forEach((el, i) => {
        const val = ds.data[i];
        const p = Math.round(val / total * 100);
        if (p < 8) return;
        const mid = (el.startAngle + el.endAngle) / 2;
        const r = el.outerRadius * 0.65;
        ctx.save();
        ctx.fillStyle = "#fff";
        ctx.font = "bold 12px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(p + "%", el.x + r * Math.cos(mid), el.y + r * Math.sin(mid));
        ctx.restore();
      });
    }
  };

  if (window.Chart) {
    Chart.register(labelPlugin);
    Chart.register(gasLabelPlugin);
  }

  // ── Helpers de UI ─────────────────────────────────────────────────────────
  function showSpinner() {
    if (spinner) spinner.classList.add("visible");
    const mainContent = document.getElementById("dashboard-main-content");
    if (mainContent) mainContent.classList.add("dashboard-fading");
  }

  function hideSpinner() {
    if (spinner) spinner.classList.remove("visible");
    const mainContent = document.getElementById("dashboard-main-content");
    if (mainContent) mainContent.classList.remove("dashboard-fading");
  }

  function showError(msg) {
    hideSpinner();
    if (errorBanner) {
      errorBanner.classList.add("visible");
      if (errorMsg) errorMsg.textContent = msg || "No se pudo cargar el dashboard. Intenta recargar.";
    }
  }

  function hideError() {
    if (errorBanner) errorBanner.classList.remove("visible");
  }

  function fmt0(v)  { return "$" + Math.round(v).toLocaleString("es-MX"); }
  function fmtN(v)  { return v != null ? v.toLocaleString("es-MX", { maximumFractionDigits: 0 }) : "—"; }
  function setText(id, txt) { const el = document.getElementById(id); if (el) el.textContent = txt; }

  // ── Pie chart helpers ─────────────────────────────────────────────────────
  function _pct(val, total) {
    if (!total) return 0;
    return Math.round(val / total * 100);
  }

  function buildQuesoData(d) {
    const total = d.total;
    return {
      labels: [
        "Energía " + _pct(d.energia, total) + "%",
        "Demanda " + _pct(d.demanda, total) + "%",
        "Otros "   + _pct(d.otros,   total) + "%",
      ],
      datasets: [{
        data: [d.energia, d.demanda, d.otros],
        backgroundColor: ["#1F7A4C", "#4FA876", "#9A9A9A"],
        borderWidth: 2,
        borderColor: "#fff",
      }],
    };
  }

  function getQuesoData() {
    if (!quesoDatos) return null;
    if (filtroActivo === "__todos__") return quesoDatos.agregado;
    return quesoDatos.por_mes.find(m => m.label === filtroActivo) || quesoDatos.agregado;
  }

  function filtrarTablaIndicadores() {
    const body = document.getElementById("tablaIndicadoresBody");
    if (!body) return;
    body.querySelectorAll("tr").forEach(tr => {
      const mes = tr.dataset.mes;
      tr.style.display = (filtroActivo === "__todos__" || mes === filtroActivo) ? "" : "none";
    });
  }

  // ── Opciones de gráficas ─────────────────────────────────────────────────
  function opcionesDualEje(labelIzq, labelDer) {
    return {
      responsive: true,
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            label: ctx => {
              const v = ctx.raw;
              return ctx.dataset.label + ": " + (typeof v === "number"
                ? v.toLocaleString("es-MX", { maximumFractionDigits: 4 }) : v);
            }
          }
        }
      },
      scales: {
        x:  { stacked: false },
        y:  { position: "left",  title: { display: true, text: labelIzq }, beginAtZero: true },
        y2: { position: "right", title: { display: true, text: labelDer }, grid: { drawOnChartArea: false }, beginAtZero: true }
      }
    };
  }

  // ── Crear / actualizar Chart.js ───────────────────────────────────────────
  function upsertChartDemanda(hist) {
    const datasets = [
      { label: "Demanda Punta (kW)",      data: hist.demanda_punta,      backgroundColor: COLOR_PUNTA,      yAxisID: "y"  },
      { label: "Demanda Intermedio (kW)", data: hist.demanda_intermedio, backgroundColor: COLOR_INTERMEDIO, yAxisID: "y"  },
      { label: "Demanda Base (kW)",       data: hist.demanda_base,       backgroundColor: COLOR_BASE,       yAxisID: "y"  },
      { type: "line", label: "$/kWh total", data: hist.costo_unit_mes,
        borderColor: COLOR_LINEA, backgroundColor: "transparent",
        borderWidth: 2, pointRadius: 4, tension: 0.2, yAxisID: "y2", _showLabels: true }
    ];
    if (!chartDemanda) {
      const ctx = document.getElementById("chartDemanda");
      if (!ctx) return;
      const opts = opcionesDualEje("kW", "$/kWh");
      opts.scales.x.stacked = false;
      chartDemanda = new Chart(ctx, { type: "bar", data: { labels: hist.labels, datasets }, options: opts });
    } else {
      chartDemanda.data.labels = hist.labels;
      chartDemanda.data.datasets.forEach((ds, i) => { ds.data = datasets[i].data; });
      chartDemanda.update();
    }
  }

  function upsertChartConsumo(hist) {
    const datasets = [
      { label: "Base (kWh)",       data: hist.consumo_base,       backgroundColor: COLOR_BASE,       yAxisID: "y", stack: "kwh" },
      { label: "Intermedio (kWh)", data: hist.consumo_intermedio, backgroundColor: COLOR_INTERMEDIO, yAxisID: "y", stack: "kwh" },
      { label: "Punta (kWh)",      data: hist.consumo_punta,      backgroundColor: COLOR_PUNTA,      yAxisID: "y", stack: "kwh" },
      { type: "line", label: "$/kWh total", data: hist.costo_unit_mes,
        borderColor: COLOR_LINEA, backgroundColor: "transparent",
        borderWidth: 2, pointRadius: 4, tension: 0.2, yAxisID: "y2", _showLabels: true }
    ];
    if (!chartConsumo) {
      const ctx = document.getElementById("chartConsumo");
      if (!ctx) return;
      const opts = opcionesDualEje("kWh", "$/kWh");
      opts.scales.x.stacked = true;
      opts.scales.y.stacked = true;
      chartConsumo = new Chart(ctx, { type: "bar", data: { labels: hist.labels, datasets }, options: opts });
    } else {
      chartConsumo.data.labels = hist.labels;
      chartConsumo.data.datasets.forEach((ds, i) => { ds.data = datasets[i].data; });
      chartConsumo.update();
    }
  }

  function upsertChartCostoPromedio(cuProm) {
    const data = [cuProm.base || 0, cuProm.intermedio || 0, cuProm.punta || 0];
    if (!chartCostoPromedio) {
      const ctx = document.getElementById("chartCostoPromedio");
      if (!ctx) return;
      chartCostoPromedio = new Chart(ctx, {
        type: "bar",
        data: {
          labels: ["Base", "Intermedio", "Punta"],
          datasets: [{
            label: "$/kWh total (energía + distribución/capacidad)",
            data,
            backgroundColor: [COLOR_BASE, COLOR_INTERMEDIO, COLOR_PUNTA],
            _showLabels: true
          }]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: ctx => "$/kWh: " + ctx.raw.toFixed(4) } }
          },
          scales: {
            y: { beginAtZero: false, title: { display: true, text: "$/kWh" }, ticks: { callback: v => "$" + v.toFixed(4) } }
          }
        }
      });
    } else {
      chartCostoPromedio.data.datasets[0].data = data;
      chartCostoPromedio.update();
    }
  }

  function upsertChartQueso(qData) {
    const d = buildQuesoData(qData);
    if (!quesoChart) {
      const ctx = document.getElementById("chartQueso");
      if (!ctx) return;
      quesoChart = new Chart(ctx, {
        type: "pie",
        data: d,
        options: {
          responsive: true,
          plugins: {
            legend: { position: "right" },
            tooltip: {
              callbacks: {
                label: ctx => {
                  const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                  if (!total) return ctx.label + ": $0 (0%)";
                  const p = Math.round(ctx.raw / total * 100);
                  return ctx.label.split(" ")[0] + ": $" + Math.round(ctx.raw).toLocaleString("en-US") + " (" + p + "%)";
                }
              }
            }
          }
        },
        plugins: [pieSlicePlugin]
      });
    } else {
      quesoChart.data.labels   = d.labels;
      quesoChart.data.datasets[0].data = d.datasets[0].data;
      quesoChart.update();
    }
  }

  function upsertChartGasConsumo(gasHist) {
    const datasets = [
      { label: "CONSUMO (GJ)", data: gasHist.consumos_gj, backgroundColor: COLOR_GAS_CONSUMO, yAxisID: "y" },
      { type: "line", label: "COSTO UNITARIO ($/GJ)", data: gasHist.costos_unit_gj,
        borderColor: COLOR_GAS_LINEA, backgroundColor: "transparent",
        borderWidth: 2, pointRadius: 4, tension: 0.2, yAxisID: "y2", _gasLabels: true }
    ];
    if (!chartGasConsumo) {
      const ctx = document.getElementById("chartGasConsumo");
      if (!ctx) return;
      chartGasConsumo = new Chart(ctx, {
        type: "bar",
        data: { labels: gasHist.labels, datasets },
        options: {
          responsive: true,
          plugins: {
            legend: { position: "top" },
            tooltip: { callbacks: { label: ctx => ctx.dataset.label + ": " + ctx.raw.toLocaleString("es-MX", { maximumFractionDigits: 2 }) } }
          },
          scales: {
            y:  { position: "left",  title: { display: true, text: "GJ" }, beginAtZero: true, ticks: { callback: v => v.toLocaleString("en-US") } },
            y2: { position: "right", title: { display: true, text: "$/GJ" }, grid: { drawOnChartArea: false }, beginAtZero: true }
          }
        }
      });
    } else {
      chartGasConsumo.data.labels = gasHist.labels;
      chartGasConsumo.data.datasets.forEach((ds, i) => { ds.data = datasets[i].data; });
      chartGasConsumo.update();
    }
  }

  function upsertChartGasCostos(gasHist) {
    const datasets = [
      { label: "COSTO MOLÉCULA ($)", data: gasHist.costos_molecula_mxn, backgroundColor: COLOR_GAS_MOL, yAxisID: "y", stack: "costos" },
      { label: "COSTO TRANSPORTE ($)", data: gasHist.costos_transporte_mxn, backgroundColor: COLOR_GAS_TRA, yAxisID: "y", stack: "costos" },
      { type: "line", label: "COSTO UNITARIO ($/GJ)", data: gasHist.costos_unit_gj,
        borderColor: COLOR_GAS_LINEA, backgroundColor: "transparent",
        borderWidth: 2, pointRadius: 4, tension: 0.2, yAxisID: "y2", _gasLabels: true }
    ];
    if (!chartGasCostos) {
      const ctx = document.getElementById("chartGasCostos");
      if (!ctx) return;
      chartGasCostos = new Chart(ctx, {
        type: "bar",
        data: { labels: gasHist.labels, datasets },
        options: {
          responsive: true,
          plugins: {
            legend: { position: "top" },
            tooltip: { callbacks: { label: ctx => ctx.dataset.label + ": " + (ctx.dataset.yAxisID === "y2" ? ctx.raw.toFixed(2) : "$" + Math.round(ctx.raw).toLocaleString("es-MX")) } }
          },
          scales: {
            y:  { position: "left",  title: { display: true, text: "MXN" }, beginAtZero: true, stacked: true, ticks: { callback: v => "$" + Math.round(v).toLocaleString("en-US") } },
            y2: { position: "right", title: { display: true, text: "$/GJ" }, grid: { drawOnChartArea: false }, beginAtZero: true }
          }
        }
      });
    } else {
      chartGasCostos.data.labels = gasHist.labels;
      chartGasCostos.data.datasets.forEach((ds, i) => { ds.data = datasets[i].data; });
      chartGasCostos.update();
    }
  }

  function upsertChartPpaConsumo(historicoP) {
    const labels = historicoP.map(m => m.mes);
    const kwh    = historicoP.map(m => m.kwh_total);
    const precio = historicoP.map(m => m.precio_unitario_mxn_kwh);
    const datasets = [
      { label: "Consumo (kWh)", data: kwh, backgroundColor: "rgba(31,122,76,0.70)", yAxisID: "y" },
      { type: "line", label: "Precio (MXN/kWh)", data: precio,
        borderColor: "#1A2D3F", backgroundColor: "transparent",
        borderWidth: 2, pointRadius: 4, tension: 0.2, yAxisID: "y2", _showLabels: true }
    ];
    if (!chartPpaConsumo) {
      const ctx = document.getElementById("chartPpaConsumo");
      if (!ctx) return;
      const opts = opcionesDualEje("kWh", "MXN/kWh");
      chartPpaConsumo = new Chart(ctx, { type: "bar", data: { labels, datasets }, options: opts });
    } else {
      chartPpaConsumo.data.labels = labels;
      chartPpaConsumo.data.datasets.forEach((ds, i) => { ds.data = datasets[i].data; });
      chartPpaConsumo.update();
    }
  }

  function upsertChartPpaCosto(historicoP) {
    const labels = historicoP.map(m => m.mes);
    const costos = historicoP.map(m => m.costo_mxn);
    if (!chartPpaCosto) {
      const ctx = document.getElementById("chartPpaCosto");
      if (!ctx) return;
      chartPpaCosto = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{
            label: "Costo mensual (MXN)",
            data: costos,
            backgroundColor: "rgba(26,45,63,0.75)",
          }]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: ctx => "$" + Math.round(ctx.raw).toLocaleString("es-MX") } }
          },
          scales: {
            y: { beginAtZero: true, title: { display: true, text: "MXN" }, ticks: { callback: v => "$" + Math.round(v).toLocaleString("en-US") } }
          }
        }
      });
    } else {
      chartPpaCosto.data.labels = labels;
      chartPpaCosto.data.datasets[0].data = costos;
      chartPpaCosto.update();
    }
  }

  // ── Render de tablas en panels flotantes ──────────────────────────────────
  function renderConsumosDemandas(filas) {
    const tbody = document.getElementById("tbodyConsumosDemandas");
    if (!tbody) return;
    tbody.innerHTML = filas.map(f => {
      const esAnual = f.mes === "ANUAL";
      const cls = esAnual ? " class=\"total-row\"" : "";
      const star = f.prorrateado ? "<span class=\"badge bg-warning text-dark ms-1\" style=\"font-size:.6em\">★</span>" : "";
      const kw = v => v != null ? Math.round(v).toLocaleString("en-US") : "—";
      return `<tr${cls}>
        <td class="ps-3 small">${f.mes}${star}</td>
        <td class="text-end small">${Math.round(f.kwh_base).toLocaleString("en-US")}</td>
        <td class="text-end small">${Math.round(f.kwh_inter).toLocaleString("en-US")}</td>
        <td class="text-end small">${Math.round(f.kwh_punta).toLocaleString("en-US")}</td>
        <td class="text-end small">${Math.round(f.kwh_total).toLocaleString("en-US")}</td>
        <td class="text-end small">${kw(f.kw_base)}</td>
        <td class="text-end small">${kw(f.kw_inter)}</td>
        <td class="text-end small pe-3">${kw(f.kw_punta)}</td>
      </tr>`;
    }).join("");
    if (_paneles["panelConsumosDemandas"]) _paneles["panelConsumosDemandas"].ajustarAltura();
  }

  function renderCostosDetallados(filas) {
    const tbody = document.getElementById("tbodyCostosDetallados");
    if (!tbody) return;
    const m0 = v => v != null ? "$" + Math.round(v).toLocaleString("en-US") : "—";
    const f4 = v => v != null ? v.toFixed(4) : "—";
    tbody.innerHTML = filas.map(f => {
      const esAnual = f.mes === "ANUAL";
      const cls = esAnual ? " class=\"total-row\"" : "";
      const star = f.prorrateado ? "<span class=\"badge bg-warning text-dark ms-1\" style=\"font-size:.6em\">★</span>" : "";
      return `<tr${cls}>
        <td class="ps-3 small">${f.mes}${star}</td>
        <td class="text-end small">$${Math.round(f.ce_base).toLocaleString("en-US")}</td>
        <td class="text-end small">$${Math.round(f.ce_inter).toLocaleString("en-US")}</td>
        <td class="text-end small">$${Math.round(f.ce_punta).toLocaleString("en-US")}</td>
        <td class="text-end small">$${Math.round(f.ce_total).toLocaleString("en-US")}</td>
        <td class="text-end small">$${Math.round(f.costo_dist).toLocaleString("en-US")}</td>
        <td class="text-end small">$${Math.round(f.costo_cap).toLocaleString("en-US")}</td>
        <td class="text-end small">$${Math.round(f.costo_dem).toLocaleString("en-US")}</td>
        <td class="text-end small">${m0(f.ct_base)}</td>
        <td class="text-end small">${m0(f.ct_inter)}</td>
        <td class="text-end small">${m0(f.ct_punta)}</td>
        <td class="text-end small">${f4(f.cu_base_total)}</td>
        <td class="text-end small">${f4(f.cu_inter_total)}</td>
        <td class="text-end small">${f4(f.cu_punta_total)}</td>
        <td class="text-end small">$${Math.round(f.cargo_fp).toLocaleString("en-US")}</td>
        <td class="text-end small pe-3">$${Math.round(f.subtotal).toLocaleString("en-US")}</td>
      </tr>`;
    }).join("");
    if (_paneles["panelCostosDetallados"]) _paneles["panelCostosDetallados"].ajustarAltura();
  }

  function renderIndicadores(filas) {
    const tbody = document.getElementById("tablaIndicadoresBody");
    if (!tbody) return;
    tbody.innerHTML = filas.map(f => {
      const esAnual = f.mes === "ANUAL";
      const cls = esAnual ? " class=\"total-row\"" : "";
      const star = f.prorrateado ? "<span class=\"badge bg-warning text-dark ms-1\" style=\"font-size:.6em\">★</span>" : "";
      return `<tr data-mes="${f.mes}"${cls}>
        <td class="ps-3 small">${f.mes}${star}</td>
        <td class="text-end small">${f.costo_unit.toFixed(2)}</td>
        <td class="text-end small">${f.pct_energia}%</td>
        <td class="text-end small">${f.pct_demanda}%</td>
        <td class="text-end small">${f.factor_carga}%</td>
        <td class="text-end small pe-3">${f.demanda_prom.toLocaleString("es-MX", { maximumFractionDigits: 1 })}</td>
      </tr>`;
    }).join("");
    if (_paneles["panelIndicadores"]) _paneles["panelIndicadores"].ajustarAltura();
  }

  function renderDetalleCostoTotal(data) {
    const tbody = document.getElementById("tbodyDetalleCostoTotal");
    if (!tbody) return;
    const fmt = v => "$" + Math.round(v).toLocaleString("es-MX");
    const colores = {
      "Energía":         "#0D3B66",
      "Capacidad":       "#1F6FB2",
      "Distribución":    "#4A9FD8",
      "Otros Servicios": "#A8D0E6",
    };
    const filas = data.lineas.map(l => `
      <tr>
        <td class="small">
          <span class="donut-color-dot" style="background:${colores[l.nombre] || '#999'}"></span>${l.nombre}
        </td>
        <td class="text-end small">${fmt(l.monto)}</td>
      </tr>`).join("");
    const total = `
      <tr style="border-top:1px solid var(--color-primary-light); background:var(--color-primary-soft)">
        <td class="small"><strong>TOTAL</strong></td>
        <td class="text-end small"><strong>${fmt(data.total)}</strong></td>
      </tr>`;
    tbody.innerHTML = filas + total;

    // Donut
    const datosDonut = data.lineas.map(l => ({
      nombre: l.nombre,
      pct:    l.pct,
      color:  colores[l.nombre] || "#999",
    }));
    renderDonutComponentes("donutDetalleCostoTotal", datosDonut);
  }

  function renderGasHistorico(gasHist) {
    const tbody = document.getElementById("tbodyGasHistorico");
    if (!tbody || !gasHist) return;
    const f2  = v => v != null ? v.toLocaleString("es-MX", { maximumFractionDigits: 2, minimumFractionDigits: 2 }) : "—";
    const f4  = v => v != null ? v.toFixed(4) : "—";
    const f5  = v => v != null ? v.toFixed(5) : "—";
    const f6  = v => v != null ? v.toFixed(6) : "—";
    const mxn = v => v != null ? "$" + v.toLocaleString("es-MX", { maximumFractionDigits: 2 }) : "—";

    const renderFila = (f, esTotal) => {
      const cls = esTotal ? " class=\"total-row\"" : "";
      const star = (!esTotal && f.prorrateado) ? "<span class=\"badge bg-warning text-dark ms-1\" style=\"font-size:.6em\">★</span>" : "";
      const label = esTotal ? "TOTAL / PROM." : f.mes;
      return `<tr${cls}>
        <td class="ps-3 small">${label}${star}</td>
        <td class="text-end small">${f2(f.consumo_gj)}</td>
        <td class="text-end small">${f4(f.molecula_precio_gj)}</td>
        <td class="text-end small">${f4(f.transporte_precio_gj)}</td>
        <td class="text-end small">${mxn(f.costo_molecula_mxn)}</td>
        <td class="text-end small">${mxn(f.costo_transporte_mxn)}</td>
        <td class="text-end small">${mxn(f.costo_total_mxn)}</td>
        <td class="text-end small">${f4(f.costo_unit_gj)}</td>
        <td class="text-end small">${f6(f.costo_unit_kwh)}</td>
        <td class="text-end small">${f5(f.pcs_gj_m3)}</td>
        <td class="text-end small pe-3">${f5(f.pcs_kwh_m3)}</td>
      </tr>`;
    };

    tbody.innerHTML = gasHist.filas.map(f => renderFila(f, false)).join("") + renderFila(gasHist.total, true);
    if (_paneles["panelGasHistorico"]) _paneles["panelGasHistorico"].ajustarAltura();
  }

  // ── Actualizar banner de aviso ────────────────────────────────────────────
  function _mkAlerta(cls, titulo, ...nodos) {
    const div = document.createElement("div");
    div.className = "alert " + cls + " mb-4";
    div.setAttribute("role", "alert");
    const strong = document.createElement("strong");
    strong.textContent = titulo;
    div.appendChild(strong);
    nodos.forEach(n => div.appendChild(typeof n === "string" ? document.createTextNode(n) : n));
    return div;
  }

  function actualizarAviso(aviso) {
    const cont = document.getElementById("aviso-datos-container");
    if (!cont) return;
    cont.textContent = "";
    if (!aviso) return;

    if (aviso.tipo === "sin_facturas") {
      cont.appendChild(_mkAlerta("alert-info", "Sin facturas cargadas.",
        " Este cliente aún no tiene facturas registradas. Ve a la ficha del cliente y sube PDFs de CFE desde la ficha de cada contrato."));
    } else if (aviso.tipo === "sin_seleccion") {
      cont.appendChild(_mkAlerta("alert-warning", "No hay datos seleccionados para análisis.",
        " Selecciona meses en el sidebar de los contratos para ver el análisis."));
    } else if (aviso.tipo === "sin_par") {
      const nElec = parseInt(aviso.num_cfe, 10) || 0;
      const nGas  = parseInt(aviso.num_gas,  10) || 0;
      const msg = nElec > 0 && nGas === 0
        ? "Faltan facturas de gas para análisis completo. Se muestra solo análisis eléctrico."
        : "Faltan facturas eléctricas para análisis completo. Se muestra solo análisis de gas.";
      const div = document.createElement("div");
      div.className = "alert alert-secondary py-1 px-2 mb-2";
      div.style.fontSize = "0.8rem";
      div.textContent = msg;
      cont.appendChild(div);
    }
  }

  // ── Actualizar selector del queso ─────────────────────────────────────────
  function actualizarSelectorQueso(porMes) {
    const sel = document.getElementById("filtroMesQueso");
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = "<option value=\"__todos__\">Todo el periodo</option>" +
      porMes.map(m => `<option value="${m.label}">${m.label}</option>`).join("");
    sel.value = porMes.find(m => m.label === prev) ? prev : "__todos__";
    filtroActivo = sel.value;
  }

  // ── Función principal de hidratación ─────────────────────────────────────
  function hidratarDashboardContabilidad(data) {
    // Periodo label en header
    const periodoEl = document.getElementById("periodo-label");
    if (periodoEl) periodoEl.textContent = data.cliente.periodo_label || "";

    // Aviso
    actualizarAviso(data.aviso_datos);

    // Mostrar/ocultar secciones
    const tieneAviso = data.aviso_datos;
    const tipo = tieneAviso ? data.aviso_datos.tipo : null;
    const sinDatos = tipo === "sin_seleccion" || tipo === "sin_facturas";
    const mainSection = document.getElementById("dashboard-main-section");
    if (mainSection) mainSection.style.display = sinDatos ? "none" : "";
    if (sinDatos) return;

    esPPA = data.tipo_suministro_electrico === "electrico_calificado";

    // Link "Ver detalle" del Costo Total — solo visible en CFE GDMTH
    const linkDetCT = document.getElementById("link-detalle-costo-total");
    if (linkDetCT) linkDetCT.style.setProperty("display", esPPA ? "none" : "inline-block", "important");
    // Reset estado (invalida cache de datos al cambiar selección de meses)
    const detalleCT = document.getElementById("detalleCostoTotal");
    if (detalleCT) detalleCT.style.display = "none";
    const flechaCT = document.getElementById("detalle-costo-total-flecha");
    if (flechaCT) flechaCT.textContent = "▼";
    const tbodyDetCT = document.getElementById("tbodyDetalleCostoTotal");
    if (tbodyDetCT) tbodyDetCT.innerHTML = "";

    // Banner PPA
    const bannerPpa = document.getElementById("banner-ppa");
    if (bannerPpa) {
      if (esPPA) {
        const spanSum = document.getElementById("banner-ppa-suministrador");
        if (spanSum) spanSum.textContent = data.suministrador_ppa || "";
        bannerPpa.style.removeProperty("display");
      } else {
        bannerPpa.style.setProperty("display", "none", "important");
      }
    }

    // KPI subtitle
    const kpiLabel = document.getElementById("kpi-num-meses-label");
    if (kpiLabel) kpiLabel.textContent = esPPA ? "facturas PPA" : "facturas CFE";

    // Secciones GDMTH vs PPA
    const graficasGdmth = document.getElementById("graficas-gdmth");
    const graficasPpa   = document.getElementById("graficas-ppa");
    if (graficasGdmth) graficasGdmth.style.display = esPPA ? "none" : "";
    if (graficasPpa)   graficasPpa.style.display   = esPPA ? "" : "none";

    // Paneles flotantes GDMTH (ocultar para PPA)
    ["panelConsumosDemandas","panelCostosDetallados","panelIndicadores"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = esPPA ? "none" : "";
    });

    // Limpiar instancias de gráficas del modo opuesto al cambiar de tipo
    if (esPPA) {
      if (chartDemanda)       { chartDemanda.destroy();       chartDemanda = null; }
      if (chartConsumo)       { chartConsumo.destroy();       chartConsumo = null; }
      if (chartCostoPromedio) { chartCostoPromedio.destroy(); chartCostoPromedio = null; }
      if (quesoChart)         { quesoChart.destroy();         quesoChart = null; }
    } else {
      if (chartPpaConsumo) { chartPpaConsumo.destroy(); chartPpaConsumo = null; }
      if (chartPpaCosto)   { chartPpaCosto.destroy();   chartPpaCosto = null; }
    }

    const k = data.kpis;
    // KPIs
    setText("kpi-num-meses",   k.num_meses);
    setText("kpi-kwh-total",   Math.round(k.kwh_total).toLocaleString("es-MX"));
    setText("kpi-costo-unit",  "$" + k.costo_unit.toFixed(4));
    const costoTotal = k.costo_total;
    if (costoTotal != null) {
      setText("kpi-costo-total-periodo", "$" + Math.round(costoTotal).toLocaleString("es-MX"));
    }

    // Gráficas CFE
    if (data.historico && data.historico.labels && data.historico.labels.length) {
      upsertChartDemanda(data.historico);
      upsertChartConsumo(data.historico);
    }
    if (data.tablas && data.tablas.costo_unit_promedio_total) {
      upsertChartCostoPromedio(data.tablas.costo_unit_promedio_total);
    }

    // Tablas en paneles flotantes
    if (data.tablas) {
      if (data.tablas.consumos_demandas) renderConsumosDemandas(data.tablas.consumos_demandas);
      if (data.tablas.costos_detallados) renderCostosDetallados(data.tablas.costos_detallados);
      if (data.tablas.indicadores)       renderIndicadores(data.tablas.indicadores);
    }

    // Pie chart
    const quesoSection = document.getElementById("queso-section");
    if (data.queso) {
      if (quesoSection) quesoSection.style.display = "";
      quesoDatos = data.queso;
      actualizarSelectorQueso(data.queso.por_mes);
      filtrarTablaIndicadores();
      const qd = getQuesoData();
      if (qd) upsertChartQueso(qd);
    } else {
      if (quesoSection) quesoSection.style.display = "none";
    }

    // Sección gas
    const gasSection = document.getElementById("gas-section");
    if (data.historico_gas) {
      if (gasSection) gasSection.style.display = "";
      upsertChartGasConsumo(data.historico_gas);
      upsertChartGasCostos(data.historico_gas);
      renderGasHistorico(data.historico_gas);
    } else {
      if (gasSection) gasSection.style.display = "none";
    }

    // Gráficas PPA
    if (esPPA && data.historico_ppa && data.historico_ppa.length) {
      upsertChartPpaConsumo(data.historico_ppa);
      upsertChartPpaCosto(data.historico_ppa);
    }
  }

  // ── Fetch con AbortController y timeout ──────────────────────────────────
  function fetchData(isRetry) {
    if (!isRetry) {
      clearTimeout(_debounceId);
    }
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();
    const signal = _abortCtrl.signal;

    const scrollY = window.scrollY;
    showSpinner();
    hideError();

    const timeout = setTimeout(() => _abortCtrl.abort(), 10000);

    fetch(DATA_URL, { signal })
      .then(res => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(data => {
        clearTimeout(timeout);
        hidratarDashboardContabilidad(data);
        window.scrollTo(0, scrollY);
      })
      .catch(err => {
        clearTimeout(timeout);
        if (err.name === "AbortError") return;
        showError("No se pudo cargar el dashboard. Intenta recargar.");
      })
      .finally(() => hideSpinner());
  }

  function scheduleRefresh() {
    clearTimeout(_debounceId);
    _debounceId = setTimeout(() => fetchData(false), DEBOUNCE_MS);
  }

  // ── Event listeners ───────────────────────────────────────────────────────
  document.addEventListener("dashboardDataChanged", scheduleRefresh);

  if (btnReintentar) {
    btnReintentar.addEventListener("click", () => fetchData(true));
  }

  // Pie chart selector
  document.addEventListener("change", function (e) {
    if (e.target && e.target.id === "filtroMesQueso") {
      filtroActivo = e.target.value;
      const qd = getQuesoData();
      if (qd && quesoChart) {
        const nd = buildQuesoData(qd);
        quesoChart.data.labels = nd.labels;
        quesoChart.data.datasets[0].data = nd.datasets[0].data;
        quesoChart.update();
      }
      filtrarTablaIndicadores();
    }
  });

  // ── Handler "Ver detalle" Costo Total (registro único) ────────────────────
  document.getElementById("link-detalle-costo-total")?.addEventListener("click", async (e) => {
    e.preventDefault();
    const div    = document.getElementById("detalleCostoTotal");
    const flecha = document.getElementById("detalle-costo-total-flecha");
    if (!div || esPPA) return;

    if (div.style.display !== "none") {
      div.style.display = "none";
      if (flecha) flecha.textContent = "▼";
      return;
    }

    // Cargar datos del endpoint (cache: si tbody ya tiene filas, no vuelve a fetchar)
    const tbody = document.getElementById("tbodyDetalleCostoTotal");
    if (tbody && tbody.children.length === 0) {
      const clienteId = document.getElementById("dashboard-contabilidad-root")?.dataset.clienteId;
      if (!clienteId) return;
      try {
        const resp = await fetch(`/clientes/${clienteId}/dashboard/contabilidad/desglose-costo-total`);
        if (!resp.ok) { console.error("desglose-costo-total:", resp.status); return; }
        const data = await resp.json();
        if (data.lineas) renderDetalleCostoTotal(data);
      } catch (err) {
        console.error("desglose-costo-total:", err);
        return;
      }
    }

    div.style.display = "block";
    if (flecha) flecha.textContent = "▲";
  });

  // ── Botón Descargar datos ─────────────────────────────────────────────────
  document.getElementById("btn-descargar-datos")?.addEventListener("click", (e) => {
    e.preventDefault();
    const clienteId = document.getElementById("dashboard-contabilidad-root")?.dataset.clienteId;
    if (clienteId) {
      window.location.href = `/clientes/${clienteId}/dashboard/contabilidad/export-datos`;
    }
  });

  // ── Carga inicial ─────────────────────────────────────────────────────────
  fetchData(false);

  // ── Gráfica cincominutal ──────────────────────────────────────────────────
  let cincominutalChart = null;

  function cargarCincominutal(medicion_id) {
    const clienteId = root?.dataset.clienteId;
    if (!clienteId || !medicion_id) return;

    fetch(`/clientes/${clienteId}/mediciones/${medicion_id}/datos`)
      .then(r => r.json())
      .then(data => {
        const section = document.getElementById("medicion-cincominutal-section");
        if (!section) return;

        if (!data.ts || data.ts.length === 0) {
          section.style.display = "none";
          return;
        }

        section.style.display = "";

        const subtitulo = document.getElementById("medicion-subtitulo");
        if (subtitulo && data.ts.length > 0) {
          const d0 = data.ts[0].slice(0, 10);
          const d1 = data.ts[data.ts.length - 1].slice(0, 10);
          subtitulo.textContent = `Potencia media cada 5 minutos (kW) — ${d0} → ${d1}`;
        }

        const ctx = document.getElementById("chartCincominutal");
        if (!ctx) return;

        const chartData = {
          labels: data.ts,
          datasets: [{
            label: "Potencia (kW)",
            data: data.potencia_kw,
            borderColor: "rgba(31,122,76,0.85)",
            backgroundColor: "transparent",
            borderWidth: 1,
            pointRadius: 0,
            tension: 0.1,
          }],
        };

        const chartOptions = {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: c => `${c.parsed.y.toLocaleString("es-MX", {maximumFractionDigits:1})} kW`,
                title: ts => ts[0].label.replace("T", " ").slice(0,16)
              }
            }
          },
          scales: {
            x: {
              ticks: {
                maxTicksLimit: 31,
                callback: function(val, idx) {
                  const label = this.getLabelForValue(val);
                  if (!label) return "";
                  const dia = label.slice(8,10);
                  const prev = idx > 0 ? this.getLabelForValue(val - 1) : null;
                  const prevDia = prev ? prev.slice(8,10) : null;
                  return dia !== prevDia ? parseInt(dia, 10).toString() : "";
                },
                maxRotation: 0,
                autoSkip: false
              }
            },
            y: {
              min: 0,
              ticks: {
                callback: v => v.toLocaleString("es-MX", {maximumFractionDigits:0}) + " kW"
              }
            }
          }
        };

        if (!cincominutalChart) {
          cincominutalChart = new Chart(ctx, {type: "line", data: chartData, options: chartOptions});
        } else {
          cincominutalChart.data = chartData;
          cincominutalChart.update();
        }
      })
      .catch(err => console.error("cincominutal:", err));
  }

  document.addEventListener("medicionActivaChanged", e => {
    cargarCincominutal(e.detail.medicion_id);
  });

  const _medicionActivaInicial = root?.dataset.medicionActivaId;
  if (_medicionActivaInicial) cargarCincominutal(parseInt(_medicionActivaInicial, 10));

})();
