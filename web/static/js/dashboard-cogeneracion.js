/**
 * dashboard-cogeneracion.js
 * Client-side rendering del dashboard de Cogeneración.
 * Fetch al endpoint /clientes/<id>/dashboard/cogeneracion/data
 * Sliders recalculan client-side (sin llamar al endpoint).
 * Escucha dashboardDataChanged para refrescar datos base al cambiar meses.
 */

(function () {
  "use strict";

  const root = document.getElementById("dashboard-cogeneracion-root");
  if (!root) return;

  const CLIENTE_ID = parseInt(root.dataset.clienteId, 10);
  const DATA_URL   = `/clientes/${CLIENTE_ID}/dashboard/cogeneracion/data`;

  const spinner     = document.getElementById("dashboard-spinner");
  const errorBanner = document.getElementById("dashboard-error-banner");
  const errorMsg    = document.getElementById("dashboard-error-msg");
  const btnReintentar = document.getElementById("btn-reintentar");

  // ── Estado global de datos base (cargados del endpoint) ───────────────────
  let meses_raw   = [];         // datos mensuales crudos para sliders
  let celsBase    = null;       // CELsResultado del endpoint (para constantes de referencia)
  let inversionMxn = 0;        // inversión fija
  let tieneInversion = false;
  let co2Datos    = null;       // {actual_total_t, factor_emision_elec, factor_emision_gas}
  let beneficioFiscalAnio1 = 0;   // beneficio fiscal año 1 por depreciación inmediata

  // ── Instancias Chart.js ───────────────────────────────────────────────────
  let cogenChart = null;
  let chart15    = null;
  let waterfallChart = null;
  let donutIngChart  = null;
  let donutGasChart  = null;

  // ── AbortController + debounce ────────────────────────────────────────────
  let _abortCtrl  = null;
  let _debounceId = null;
  const DEBOUNCE_MS = 300;

  // ── Helpers formateo ──────────────────────────────────────────────────────
  const fmt  = v => "$" + Math.round(v).toLocaleString("es-MX");
  const fmt2 = v => v != null ? v.toLocaleString("es-MX", { maximumFractionDigits: 2, minimumFractionDigits: 2 }) : "N/A";
  const fmt4 = v => v != null ? v.toFixed(4) : "N/A";
  const setText = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  const setHtml = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };

  // ── UI spinner / error ────────────────────────────────────────────────────
  function showSpinner() {
    if (spinner) spinner.classList.add("visible");
    const mc = document.getElementById("dashboard-main-content");
    if (mc) mc.classList.add("dashboard-fading");
  }
  function hideSpinner() {
    if (spinner) spinner.classList.remove("visible");
    const mc = document.getElementById("dashboard-main-content");
    if (mc) mc.classList.remove("dashboard-fading");
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

  // ── Leer parámetros de sliders ────────────────────────────────────────────
  function leerParams() {
    return {
      cobertura:    (document.getElementById("cobertura")?.value ?? 75) / 100,
      rend_elec:    (document.getElementById("rendimiento-elec")?.value ?? 40) / 100,
      rend_term:    (document.getElementById("rendimiento-term")?.value ?? 25) / 100,
      efic_caldera: (document.getElementById("caldera")?.value ?? 85) / 100,
    };
  }

  // ── Recalcular mes con parámetros de sliders ──────────────────────────────
  function recalcularMes(m, p) {
    const kwh_cub = m.kwh_total * p.cobertura;
    // Greedy: cubrir primero el horario más caro (Energía)
    const periodos = [
        { kwh: m.kwh_punta,      cu: m.cu_punta },
        { kwh: m.kwh_intermedia, cu: m.cu_intermedia },
        { kwh: m.kwh_base,       cu: m.cu_base },
    ].sort((a, b) => b.cu - a.cu);
    let remaining = kwh_cub, ah_energia = 0;
    for (const per of periodos) {
        const covered = Math.min(remaining, per.kwh);
        ah_energia += covered * per.cu;
        remaining -= covered;
        if (remaining <= 0) break;
    }
    // Capacidad y Distribución (metodología GDMTH con redondeo ceiling)
    // CFE GDMTH factura demanda como ceil(kWh / horas / 0.57); se aplica tanto a demanda
    // actual (base del precio) como a demanda post-cogeneración (nueva demanda proyectada).
    if (m.kw_max > 0 && m.dias_mes > 0) {
        const d_ceil_actual = Math.ceil(m.kwh_total_orig / (24 * m.dias_mes) / 0.57);
        const kw_bill_cap   = Math.min(m.kw_punta || m.kw_max, d_ceil_actual);
        const kw_bill_dist  = Math.min(m.kw_max, d_ceil_actual);
        const kwh_post_orig = m.kwh_total_orig * (1 - p.cobertura);
        const d_ceil_post   = Math.ceil(kwh_post_orig / (24 * m.dias_mes) / 0.57);
        const kw_eff_cap    = Math.min(kw_bill_cap,  d_ceil_post);
        const kw_eff_dist   = Math.min(kw_bill_dist, d_ceil_post);
        var ah_cap  = m.precio_capacidad_kw  * Math.max(kw_bill_cap  - kw_eff_cap,  0);
        var ah_dist = m.precio_distribucion_kw * Math.max(kw_bill_dist - kw_eff_dist, 0);
    } else {
        var ah_cap = 0, ah_dist = 0;
    }
    const ah_elec = ah_energia + ah_cap + ah_dist;
    const gj_cogen   = kwh_cub * 0.0036 * 1.11 / p.rend_elec;  // 0.0036 = kWh→GJ; 1.11 = factor PCI→PCS
    const costo_gas  = gj_cogen * m.costo_unitario_gj;
    const calor_rec  = gj_cogen * p.rend_term;
    const ah_caldera = (calor_rec / p.efic_caldera) * m.costo_unitario_gj;
    const om         = kwh_cub * 0.3;
    return { ah_elec, ah_energia, ah_cap, ah_dist, ah_caldera, costo_gas, om,
             ahorro_neto: ah_elec + ah_caldera - costo_gas - om };
  }

  // ── Payback helpers ───────────────────────────────────────────────────────
  function calcularPaybackJS(invMxn, ahorroAnual) {
    if (ahorroAnual <= 0 || invMxn <= 0) return null;
    let acum = -invMxn;
    for (let i = 1; i <= 15; i++) { acum += ahorroAnual; if (acum >= 0) return i; }
    return -1;
  }
  function textoPayback(payback) {
    if (payback === null) return { texto: "No aplica", clase: "fs-5 fw-bold text-muted" };
    if (payback === -1)   return { texto: "> 15 años", clase: "fs-5 fw-bold text-danger" };
    const color = payback <= 5 ? "text-success" : payback <= 10 ? "text-warning" : "text-danger";
    return { texto: payback + " años", clase: "fs-5 fw-bold " + color };
  }

  // ── CO2 reactivo ──────────────────────────────────────────────────────────
  function recalcularCO2Proy(p) {
    if (!co2Datos || !co2Datos.factor_emision_elec) return null;
    const FE_ELEC = co2Datos.factor_emision_elec;
    const FE_GAS  = co2Datos.factor_emision_gas;
    const gj_caldera = meses_raw.reduce((s, m) => s + m.gj_consumido, 0);
    let kwh_cub_tot = 0, gj_cogen_tot = 0, calor_rec_tot = 0;
    meses_raw.forEach(m => {
      const kc = m.kwh_total * p.cobertura;
      const gj = kc * 0.0036 * 1.11 / p.rend_elec;
      kwh_cub_tot  += kc;
      gj_cogen_tot += gj;
      calor_rec_tot += gj * p.rend_term;
    });
    const kwh_total = meses_raw.reduce((s, m) => s + m.kwh_total, 0);
    const co2_elec  = Math.max((kwh_total - kwh_cub_tot) * FE_ELEC / 1000, 0);
    const gj_cal_cogen = Math.max(gj_caldera - calor_rec_tot / p.efic_caldera, 0);
    const co2_gas   = Math.max((gj_cogen_tot + gj_cal_cogen) * FE_GAS / 1000, 0);
    return co2_elec + co2_gas;
  }

  function actualizarCO2(p) {
    const el = document.getElementById("co2-reduccion-texto");
    if (!el || !co2Datos) return;
    const co2_proy = recalcularCO2Proy(p);
    if (co2_proy === null) return;
    const co2_actual = co2Datos.actual_total_t || 0;
    const reduccion  = co2_actual - co2_proy;
    const pct        = co2_actual > 0 ? reduccion / co2_actual * 100 : 0;
    const arboles    = Math.round(reduccion * 50);
    if (reduccion >= 0) {
      el.innerHTML = `<div class="kpi-label">Reducción CO₂</div>
        <div class="kpi-value text-success" style="font-size:1.2rem">${reduccion.toFixed(1)} t CO₂/año</div>
        <div class="kpi-sublabel">${Math.abs(pct).toFixed(1)}% menos · ≈${arboles.toLocaleString("es-MX")} árboles</div>`;
    } else {
      el.innerHTML = `<div class="kpi-label">Reducción CO₂</div>
        <div class="kpi-value text-danger" style="font-size:1.2rem">+${Math.abs(reduccion).toFixed(1)} t</div>
        <div class="kpi-sublabel">con esta configuración</div>`;
    }
  }

  // ── CELs reactivos a sliders ──────────────────────────────────────────────
  function recalcularCELs(p) {
    if (!celsBase) return null;
    const REFE        = celsBase.RefE;
    const REFH        = celsBase.RefH;
    const REFE_PRIMA  = celsBase.RefE_prima;
    const _GJ_A_MWH   = 277.778;
    let E_kwh = 0, gj_pci = 0, calor_gj = 0;
    meses_raw.forEach(m => {
      const kc         = m.kwh_total * p.cobertura;
      const gj_pcs     = kc * 0.0036 * 1.11 / p.rend_elec;
      const gj_pci_mes = kc * 0.0036 / p.rend_elec;
      E_kwh    += kc;
      gj_pci   += gj_pci_mes;
      // calor_gj usa PCS (no PCI): convención industrial en México; el poder calorífico superior
      // es el estándar en contratos de gas y en la metodología CRE para CELs.
      calor_gj += gj_pcs * p.rend_term;
    });
    const E  = E_kwh / 1000;
    const F  = gj_pci   * _GJ_A_MWH / 1000;
    const H  = calor_gj * _GJ_A_MWH / 1000;
    const Fh = REFH > 0 ? H / REFH : 0;
    const Fe = F - Fh;
    const EP = (REFE_PRIMA > 0 ? E / REFE_PRIMA : 0) + (REFH > 0 ? H / REFH : 0);
    const AEP  = EP - F;
    const ELC  = AEP * REFE;
    const cels_mwh = ELC > 0 ? ELC : 0;
    return {
      E, F, H, Fh, Fe, EP, AEP, ELC, cels_mwh,
      EE:    Fe > 0 ? E / Fe : null,
      APEP:  EP > 0 ? AEP / EP : null,
      AREL:  Fe > 0 ? AEP / Fe : null,
      pctELC: E > 0 ? ELC / E : null,
    };
  }

  function actualizarCELsUI(res) {
    if (!res) return;
    setText("cels-valor", fmt2(res.cels_mwh));
    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setTxt("cd-E",        fmt2(res.E)   + " MWh");
    setTxt("cd-F",        fmt2(res.F)   + " MWh");
    setTxt("cd-H",        fmt2(res.H)   + " MWh");
    setTxt("cd-Fh",       fmt2(res.Fh)  + " MWh");
    setTxt("cd-Fe",       fmt2(res.Fe)  + " MWh");
    setTxt("cd-EE",       fmt4(res.EE));
    setTxt("cd-EP",       fmt2(res.EP)  + " MWh");
    setTxt("cd-AEP",      fmt2(res.AEP) + " MWh");
    setTxt("cd-APEP",     fmt4(res.APEP));
    setTxt("cd-AREL",     fmt4(res.AREL));
    setTxt("cd-ELC",      fmt2(res.ELC) + " MWh");
    setTxt("cd-pctELC",   fmt4(res.pctELC));
    setTxt("cd-cels-final", fmt2(res.cels_mwh));
    const resEl = document.getElementById("cd-resultado");
    if (resEl) {
      if (res.ELC > 0) {
        resEl.textContent = "Cogeneración eficiente ✓";
        resEl.className   = "fw-bold text-success";
      } else {
        resEl.textContent = "No califica como cogeneración eficiente";
        resEl.className   = "fw-bold text-warning";
      }
    }
  }

  // ── Chart: gráfica mensual cogeneración ──────────────────────────────────
  function upsertCogenChart(labels, ahorro_elec, ahorro_caldera, costo_gas, om, ebitda) {
    const datasets = [
      { label: "Ahorro Electricidad", data: ahorro_elec,                    backgroundColor: "rgba(106,138,154,0.65)", stack: "componentes" },
      { label: "Ahorro Caldera",      data: ahorro_caldera,                 backgroundColor: "rgba(232,181,71,0.65)",  stack: "componentes" },
      { label: "Costo Gas Cogen",     data: costo_gas.map(v => -v),         backgroundColor: "rgba(216,90,90,0.65)",   stack: "componentes" },
      { label: "O&M",                 data: om.map(v => -v),                backgroundColor: "rgba(180,100,180,0.65)", stack: "componentes" },
      { type: "line", label: "Ahorro Neto", data: ebitda,
        borderColor: "#1F7A4C", backgroundColor: "rgba(31,122,76,0.1)",
        borderWidth: 2, pointRadius: 4, fill: false, tension: 0.3 }
    ];
    if (!cogenChart) {
      const ctx = document.getElementById("cogenChart");
      if (!ctx) return;
      cogenChart = new Chart(ctx, {
        type: "bar",
        data: { labels, datasets },
        options: {
          responsive: true,
          plugins: {
            legend: { position: "top" },
            tooltip: { callbacks: { label: ctx => ctx.dataset.label + ": $" + Math.abs(ctx.raw).toLocaleString("es-MX", { maximumFractionDigits: 0 }) } }
          },
          scales: {
            y: { ticks: { callback: v => "$" + Math.abs(v).toLocaleString("es-MX", { maximumFractionDigits: 0 }) } }
          }
        }
      });
    } else {
      cogenChart.data.labels = labels;
      cogenChart.data.datasets.forEach((ds, i) => { ds.data = datasets[i].data; });
      cogenChart.update();
    }
  }

  // ── Charts: waterfall y donuts de composición ─────────────────────────────
  function upsertGraficasComposicion(ah_elec, ah_caldera, costo_gas, om, ahorro_neto) {
    const secGraf = document.getElementById("seccion-graficas-composicion");
    if (secGraf) secGraf.style.display = "";

    // ── Waterfall (barras horizontales simuladas) ─────────────────────────────
    const wfCtx = document.getElementById("waterfallChart");
    if (wfCtx) {
      const wfLabels  = ["Ahorro Electricidad", "Ahorro Caldera", "Costo Gas Cogen", "O&M", "Ahorro Neto"];
      const wfValues  = [ah_elec, ah_caldera, -costo_gas, -om, ahorro_neto];
      const wfColors  = [
        "rgba(106,138,154,0.8)",   // azul grisáceo — elec
        "rgba(232,181,71,0.8)",    // dorado — caldera
        "rgba(216,90,90,0.8)",     // rojo — gas
        "rgba(180,100,180,0.8)",   // morado — O&M
        "rgba(31,122,76,0.85)",    // verde oscuro — neto
      ];
      const wfData = { labels: wfLabels, datasets: [{ data: wfValues, backgroundColor: wfColors }] };
      if (!waterfallChart) {
        waterfallChart = new Chart(wfCtx, {
          type: "bar",
          data: wfData,
          options: {
            indexAxis: "y",
            responsive: true,
            plugins: {
              legend: { display: false },
              tooltip: { callbacks: { label: c => "$" + Math.abs(Math.round(c.raw)).toLocaleString("es-MX") + " MXN" } }
            },
            scales: {
              x: { ticks: { callback: v => "$" + Math.abs(Math.round(v)).toLocaleString("es-MX", { maximumFractionDigits: 0 }) } }
            }
          }
        });
      } else {
        waterfallChart.data.datasets[0].data = wfValues;
        waterfallChart.update();
      }
    }

    // ── Donut Ingresos ────────────────────────────────────────────────────────
    const diCtx = document.getElementById("donutIngresosChart");
    if (diCtx) {
      const totalIng = ah_elec + ah_caldera;
      const diData = {
        labels: ["Ahorro Electricidad", "Ahorro Caldera"],
        datasets: [{ data: [ah_elec, ah_caldera], backgroundColor: ["rgba(106,138,154,0.8)", "rgba(232,181,71,0.8)"] }]
      };
      if (!donutIngChart) {
        donutIngChart = new Chart(diCtx, {
          type: "doughnut",
          data: diData,
          options: {
            responsive: true,
            plugins: {
              legend: { position: "bottom" },
              tooltip: {
                callbacks: {
                  label: c => {
                    const pct = totalIng > 0 ? (c.raw / totalIng * 100).toFixed(1) : 0;
                    return c.label + ": " + pct + "% ($" + Math.round(c.raw).toLocaleString("es-MX") + ")";
                  }
                }
              }
            }
          }
        });
      } else {
        donutIngChart.data.datasets[0].data = [ah_elec, ah_caldera];
        donutIngChart.update();
      }
    }

    // ── Donut Gastos ──────────────────────────────────────────────────────────
    const dgCtx = document.getElementById("donutGastosChart");
    if (dgCtx) {
      const totalGas = costo_gas + om;
      const dgData = {
        labels: ["Costo Gas Cogen", "O&M"],
        datasets: [{ data: [costo_gas, om], backgroundColor: ["rgba(216,90,90,0.8)", "rgba(180,100,180,0.8)"] }]
      };
      if (!donutGasChart) {
        donutGasChart = new Chart(dgCtx, {
          type: "doughnut",
          data: dgData,
          options: {
            responsive: true,
            plugins: {
              legend: { position: "bottom" },
              tooltip: {
                callbacks: {
                  label: c => {
                    const pct = totalGas > 0 ? (c.raw / totalGas * 100).toFixed(1) : 0;
                    return c.label + ": " + pct + "% ($" + Math.round(c.raw).toLocaleString("es-MX") + ")";
                  }
                }
              }
            }
          }
        });
      } else {
        donutGasChart.data.datasets[0].data = [costo_gas, om];
        donutGasChart.update();
      }
    }
  }

  // ── Chart: flujo 15 años ──────────────────────────────────────────────────
  function actualizarChart15(ahorroAnual, beneficioFiscal) {
    beneficioFiscal = beneficioFiscal || 0;
    const ctxEl = document.getElementById("chart15Year");
    if (!ctxEl || !tieneInversion || !inversionMxn) return;
    // Año 1 incluye beneficio fiscal
    const flujoAnio1 = ahorroAnual + beneficioFiscal;
    const flujoAnual = [-inversionMxn, flujoAnio1, ...Array(14).fill(ahorroAnual)];
    let acum = 0;
    const flujoAcum = flujoAnual.map(v => { acum += v; return acum; });
    const bgColors  = flujoAnual.map(v => v < 0 ? "rgba(216,90,90,0.75)" : "rgba(85,170,85,0.6)");
    if (!chart15) {
      chart15 = new Chart(ctxEl, {
        type: "bar",
        data: {
          labels: Array.from({ length: 16 }, (_, i) => "Año " + i),
          datasets: [
            { label: "Flujo anual", data: flujoAnual, backgroundColor: bgColors, order: 2 },
            { type: "line", label: "Flujo acumulado", data: flujoAcum,
              borderColor: "#1F7A4C", backgroundColor: "rgba(31,122,76,0.08)",
              borderWidth: 2, pointRadius: 4, fill: false, tension: 0.25, order: 1 },
            { type: "line", label: "_cero", data: Array(16).fill(0),
              borderColor: "rgba(130,130,130,0.35)", borderWidth: 1,
              borderDash: [5, 4], pointRadius: 0, fill: false, order: 0 }
          ]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { position: "top", labels: { filter: item => item.text !== "_cero" } },
            tooltip: {
              callbacks: {
                label: ctx => {
                  if (ctx.dataset.label === "_cero") return null;
                  if (ctx.datasetIndex === 0 && ctx.dataIndex === 1 && beneficioFiscal > 0) {
                    return [
                      ctx.dataset.label + ": $" + Math.abs(Math.round(ctx.raw)).toLocaleString("es-MX", { maximumFractionDigits: 0 }),
                      "  (incl. beneficio fiscal $" + Math.round(beneficioFiscal).toLocaleString("es-MX") + " — Art. 34 XIII LISR)"
                    ];
                  }
                  return ctx.dataset.label + ": $" + Math.abs(ctx.raw).toLocaleString("es-MX", { maximumFractionDigits: 0 });
                }
              }
            }
          },
          scales: { y: { ticks: { callback: v => "$" + v.toLocaleString("es-MX", { maximumFractionDigits: 0 }) } } }
        }
      });
    } else {
      chart15.data.datasets[0].data            = flujoAnual;
      chart15.data.datasets[0].backgroundColor = bgColors;
      chart15.data.datasets[1].data            = flujoAcum;
      chart15.update();
    }

    const notaFiscal = document.getElementById("nota-beneficio-fiscal");
    if (notaFiscal) notaFiscal.style.display = beneficioFiscal > 0 ? "" : "none";
  }

  // ── Actualización desde sliders ───────────────────────────────────────────
  function actualizarSensibilidad() {
    if (!meses_raw.length) return;
    const p = leerParams();

    setText("val-cobertura",        Math.round(p.cobertura * 100));
    setText("val-rendimiento-elec", Math.round(p.rend_elec * 100));
    setText("val-rendimiento-term", Math.round(p.rend_term * 100));
    setText("val-caldera",          Math.round(p.efic_caldera * 100));

    let ahorro_neto_anual = 0, ah_elec = 0, ah_caldera = 0, costo_gas = 0, om_anual = 0;
    const lChartE = [], lChartC = [], lChartG = [], lChartOM = [], lChartN = [];

    meses_raw.forEach(m => {
      const res = recalcularMes(m, p);
      ahorro_neto_anual += res.ahorro_neto;
      ah_elec   += res.ah_elec;
      ah_caldera += res.ah_caldera;
      costo_gas += res.costo_gas;
      om_anual  += res.om;
      lChartE.push(res.ah_elec);
      lChartC.push(res.ah_caldera);
      lChartG.push(res.costo_gas);
      lChartOM.push(res.om);
      lChartN.push(res.ahorro_neto);
    });

    const colorClass = ahorro_neto_anual < 0 ? "text-danger" : "text-success";

    const kpiAN = document.getElementById("kpi-ahorro-neto-val");
    if (kpiAN) { kpiAN.textContent = fmt(ahorro_neto_anual); kpiAN.className = "fs-2 fw-bold " + colorClass; }

    const sensEl = document.getElementById("ahorro-neto-sensibilidad");
    if (sensEl) { sensEl.textContent = fmt(ahorro_neto_anual); sensEl.className = "fs-5 " + colorClass; }

    setText("kpi-elec-val",           fmt(ah_elec));
    setText("kpi-caldera-val",        fmt(ah_caldera));
    setText("kpi-total-ingresos-val", fmt(ah_elec + ah_caldera));
    setText("kpi-gas-val",            fmt(costo_gas));
    setText("kpi-om-val",             fmt(om_anual));
    setText("kpi-total-gastos-val",   fmt(costo_gas + om_anual));

    // Payback
    if (tieneInversion) {
      const payback = calcularPaybackJS(inversionMxn, ahorro_neto_anual);
      const { texto, clase } = textoPayback(payback);
      const el = document.getElementById("kpi-payback-val");
      if (el) { el.textContent = texto; el.className = clase; }
      actualizarChart15(ahorro_neto_anual, beneficioFiscalAnio1);
    }

    // Actualizar gráfica mensual
    const labels = meses_raw.map(m => m.periodo);
    upsertCogenChart(labels, lChartE, lChartC, lChartG, lChartOM, lChartN);
    upsertGraficasComposicion(ah_elec, ah_caldera, costo_gas, om_anual, ahorro_neto_anual);

    actualizarCO2(p);
    const celRes = recalcularCELs(p);
    if (celRes) actualizarCELsUI(celRes);
  }

  // ── Render tabla mensual en panel flotante ────────────────────────────────
  function renderTablaMensual(filas, totales) {
    const tbody = document.getElementById("tbodyTablaMensual");
    if (!tbody) return;
    const fmtK = v => Math.round(v).toLocaleString("en-US");
    const fmtD = (v, d) => v.toLocaleString("es-MX", { maximumFractionDigits: d, minimumFractionDigits: d });

    const html = filas.map(m => {
      const star = m.prorrateado
        ? `<span class="badge bg-warning text-dark ms-1" style="font-size:.65em" title="${m.nota_prorrateo}">★ prorrateado</span>`
        : "";
      return `<tr>
        <td class="ps-3">${m.periodo}${star}</td>
        <td class="text-end small">${fmtK(m.kwh_total)}</td>
        <td class="text-end small">$${fmtK(m.costo_cfe_mxn)}</td>
        <td class="text-end small">${fmtD(m.costo_promedio_kwh, 4)}</td>
        <td class="text-end small">${fmtD(m.gj_consumido, 2)}</td>
        <td class="text-end small">${fmtD(m.costo_unitario_gj, 4)}</td>
        <td class="text-end small">$${fmtK(m.costo_gas_actual_mxn)}</td>
        <td class="text-end small">${fmtK(m.kwh_cubiertos)}</td>
        <td class="text-end small">${fmtD(m.gj_gas_cogen, 2)}</td>
        <td class="text-end small">$${fmtK(m.costo_gas_cogen_mxn)}</td>
        <td class="text-end small">$${fmtK(m.ahorro_electricidad_mxn)}</td>
        <td class="text-end small">${fmtD(m.calor_recuperado_gj, 2)}</td>
        <td class="text-end small">$${fmtK(m.ahorro_caldera_mxn)}</td>
        <td class="text-end small">$${fmtK(m.gasto_om_mes_mxn)}</td>
        <td class="text-end small ahorro-neto-cell pe-3">$${fmtK(m.ebitda_mes_mxn)}</td>
      </tr>`;
    }).join("");

    const tot = totales;
    const totalRow = `<tr class="total-row">
      <td class="ps-3"><strong>TOTAL ANUAL</strong></td>
      <td class="text-end small">${fmtK(tot.kwh_total_anual)}</td>
      <td class="text-end small"></td><td class="text-end small"></td>
      <td class="text-end small"></td><td class="text-end small"></td>
      <td class="text-end small"></td>
      <td class="text-end small">${fmtK(tot.kwh_cubiertos_anual)}</td>
      <td class="text-end small">${fmtD(tot.gj_gas_cogen_anual, 2)}</td>
      <td class="text-end small">$${fmtK(tot.costo_gas_cogen_anual_mxn)}</td>
      <td class="text-end small">$${fmtK(tot.ahorro_electricidad_anual_mxn)}</td>
      <td class="text-end small"></td>
      <td class="text-end small">$${fmtK(tot.ahorro_caldera_anual_mxn)}</td>
      <td class="text-end small">$${fmtK(tot.gasto_om_anual_mxn)}</td>
      <td class="text-end small ahorro-neto-cell pe-3">$${fmtK(tot.ebitda_anual_mxn)}</td>
    </tr>`;

    tbody.innerHTML = html + totalRow;
  }

  // ── Render panel CELs ─────────────────────────────────────────────────────
  function renderCelsDatosCliente(cels) {
    if (!cels) return;
    const etiqMedio = { vapor_agua: "Vapor o agua caliente", gases_combustion: "Gases de combustión directos" };
    const etiqTension = { lt_1: "Menor a 1.0 kV", "1_34": "1.0 a 34.5 kV", "69_85": "69 a 85 kV", "115_230": "115 a 230 kV", gt_400: "Mayor o igual a 400 kV" };
    const etiqMotor = { combustion_interna: "Motor de combustión interna", turbina_gas: "Turbina de gas" };
    setText("cd-medio-termico", etiqMedio[cels.medio_termico] || cels.medio_termico);
    setText("cd-nivel-tension", etiqTension[cels.nivel_tension_kv] || cels.nivel_tension_kv);
    setText("cd-altitud",       cels.altitud_msnm + " msnm");
    setText("cd-tipo-motor",    etiqMotor[cels.tipo_motor] || "Otros");
    setText("cd-capacidad",     fmt2(cels.capacidad_kw) + " kW" + (cels.capacidad_es_estimada ? " ⚠" : ""));
  }

  // ── Actualizar aviso ──────────────────────────────────────────────────────
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
        " Este cliente aún no tiene facturas registradas. Ve a la ficha del cliente y sube PDFs de CFE y gas desde la ficha de cada contrato."));
    } else if (aviso.tipo === "sin_seleccion") {
      cont.appendChild(_mkAlerta("alert-warning", "No hay datos seleccionados para análisis.",
        " Selecciona meses en el sidebar de los contratos para ver el análisis."));
    } else if (aviso.tipo === "sin_par") {
      const numCfe = parseInt(aviso.num_cfe, 10) || 0;
      const numGas = parseInt(aviso.num_gas, 10) || 0;
      const sCfe = document.createElement("strong");
      sCfe.textContent = numCfe + " factura" + (numCfe !== 1 ? "s" : "") + " CFE";
      const sGas = document.createElement("strong");
      sGas.textContent = numGas + " de gas";
      cont.appendChild(_mkAlerta("alert-info", "Análisis incompleto.",
        " El análisis de cogeneración requiere facturas tanto de electricidad (CFE) como de gas natural. Hay ", sCfe, " y ", sGas, " seleccionadas."));
    } else if (aviso.tipo === "sin_pares_mes") {
      const numCfe = parseInt(aviso.num_cfe, 10) || 0;
      const numGas = parseInt(aviso.num_gas, 10) || 0;
      cont.appendChild(_mkAlerta("alert-warning", "Sin periodos emparejados.",
        " Hay " + numCfe + " facturas CFE y " + numGas + " de gas, pero ningún mes tiene par CFE-gas en el mismo periodo."));
    }
  }

  // ── Función principal de hidratación ─────────────────────────────────────
  function hidratarDashboardCogeneracion(data) {
    // Periodo label
    const periodoEl = document.getElementById("periodo-label");
    if (periodoEl) periodoEl.textContent = data.cliente.periodo_label || "";

    actualizarAviso(data.aviso_datos);

    const tipo = data.aviso_datos ? data.aviso_datos.tipo : null;
    const sinDatos = tipo === "sin_seleccion";
    const mainSection = document.getElementById("dashboard-main-section");
    if (mainSection) mainSection.style.display = sinDatos ? "none" : "";
    if (sinDatos) return;

    // Guardar datos base para sliders
    meses_raw    = data.meses_raw || [];
    celsBase     = data.cels;
    inversionMxn = data.kpis.inversion_mxn || 0;
    tieneInversion = inversionMxn > 0;
    co2Datos     = data.co2;

    // KPIs Inversión y Retorno
    const secInversion = document.getElementById("seccion-inversion");
    if (secInversion) {
      const k = data.kpis;
      secInversion.style.display = k.capacidad_nominal_kw ? "" : "none";
      setText("kpi-capacidad-val", k.capacidad_nominal_kw
        ? k.capacidad_nominal_kw.toLocaleString("es-MX", { maximumFractionDigits: 2 }) + " kW"
        : "Sin datos");
      if (k.inversion_usd) {
        setText("kpi-inversion-usd-val", "$" + Math.round(k.inversion_usd).toLocaleString("en-US") + " USD");
        setText("kpi-inversion-mxn-val",
          "$" + Math.round(k.inversion_mxn).toLocaleString("en-US") + " MXN al tipo " +
          (k.tipo_cambio || 0).toFixed(2));
      }
    }

    // Energía Limpia Generada
    const elLimpia = document.getElementById("kpi-energia-limpia-val");
    if (elLimpia) {
      if (data.kpis.energia_limpia_pct != null) {
        elLimpia.textContent = data.kpis.energia_limpia_pct.toFixed(1) + "%";
        elLimpia.style.color = "var(--bs-success, #28a745)";
      } else {
        elLimpia.textContent = "N/D";
        elLimpia.style.color = "var(--bs-secondary, #6c757d)";
      }
    }

    beneficioFiscalAnio1 = data.kpis.beneficio_fiscal_anio_1_mxn || 0;

    // CO2 sección
    const co2Section = document.getElementById("co2-reduccion-texto");
    if (co2Section && !data.co2) {
      co2Section.innerHTML = `<div class="kpi-label">Reducción CO₂</div>
        <div class="kpi-sublabel">No disponible (sin factores de emisión)</div>`;
    }

    // CELs: determinar estado y actualizar card
    actualizarCELsCard(data.cels, data.cliente_ficha_url);
    if (data.cels) renderCelsDatosCliente(data.cels);

    // Tabla mensual
    renderTablaMensual(data.tabla_mensual || [], data.totales || {});

    // Trigger slider update (re-calcula todo con parámetros actuales)
    actualizarSensibilidad();

    // Payback con beneficio fiscal (override del cálculo JS local si el backend lo entrega)
    const paybackConBeneficio = data.payback_con_beneficio;
    if (tieneInversion && paybackConBeneficio !== null && paybackConBeneficio !== undefined) {
      const elPb = document.getElementById("kpi-payback-val");
      if (elPb) {
        const { texto, clase } = textoPayback(paybackConBeneficio);
        elPb.textContent = texto + (beneficioFiscalAnio1 > 0 ? " ★" : "");
        elPb.className = clase;
      }
    }

    // Gráfica 15 años: mostrar/ocultar contenedor
    const sec15 = document.getElementById("seccion-15-anios");
    if (sec15) sec15.style.display = tieneInversion ? "" : "none";
  }

  // ── Card de CELs ──────────────────────────────────────────────────────────
  function actualizarCELsCard(cels, fichUrl) {
    const card = document.getElementById("cels-card-body");
    if (!card) return;
    card.textContent = "";

    const icon = document.createElement("i");
    const inner = document.createElement("div");

    const lbl = document.createElement("div");
    lbl.className = "small text-muted mb-1";
    lbl.textContent = "CELs Generados";
    inner.appendChild(lbl);

    if (!cels) {
      icon.className = "bi bi-info-circle kpi-icon";
      icon.style.color = "var(--color-text-muted)";

      const titulo = document.createElement("div");
      titulo.className = "fw-bold text-muted";
      titulo.textContent = "Datos incompletos";
      inner.appendChild(titulo);

      const desc = document.createElement("div");
      desc.className = "text-muted small mt-1";
      desc.textContent = "Configura medio térmico, tensión, altitud y tipo de motor en la ficha del cliente.";
      inner.appendChild(desc);

      const link = document.createElement("a");
      link.setAttribute("href", fichUrl || "#");
      link.className = "small text-decoration-none mt-1 d-block";
      link.textContent = "Ir a ficha del cliente →";
      inner.appendChild(link);
    } else if (cels.es_eficiente) {
      icon.className = "bi bi-patch-check kpi-icon";
      icon.id = "cels-icono";
      icon.style.color = "var(--color-primary)";

      const valor = document.createElement("div");
      valor.className = "fs-4 fw-bold text-success";
      valor.id = "cels-valor";
      valor.textContent = fmt2(cels.cels_mwh_anual);
      inner.appendChild(valor);

      const unidad = document.createElement("div");
      unidad.className = "text-muted small";
      unidad.id = "cels-unidad";
      unidad.textContent = "MWh CEL/año";
      inner.appendChild(unidad);

      const estado = document.createElement("div");
      estado.className = "text-success small mt-1";
      estado.textContent = "Cogeneración eficiente ✓";
      inner.appendChild(estado);

      const link = document.createElement("a");
      link.setAttribute("href", "#");
      link.className = "small text-decoration-none mt-1 d-block";
      link.textContent = "Ver detalle CRE →";
      link.addEventListener("click", e => { e.preventDefault(); abrirPanel("panelCels"); });
      inner.appendChild(link);
    } else {
      icon.className = "bi bi-x-circle kpi-icon";
      icon.id = "cels-icono";
      icon.style.color = "var(--bs-warning)";

      const valor = document.createElement("div");
      valor.className = "fs-4 fw-bold text-warning";
      valor.id = "cels-valor";
      valor.textContent = "0";
      inner.appendChild(valor);

      const unidad = document.createElement("div");
      unidad.className = "text-muted small";
      unidad.id = "cels-unidad";
      unidad.textContent = "MWh CEL/año";
      inner.appendChild(unidad);

      const estado = document.createElement("div");
      estado.className = "text-warning small mt-1";
      estado.textContent = "No califica como cogeneración eficiente";
      inner.appendChild(estado);

      const link = document.createElement("a");
      link.setAttribute("href", "#");
      link.className = "small text-decoration-none mt-1 d-block";
      link.textContent = "Ver detalle CRE →";
      link.addEventListener("click", e => { e.preventDefault(); abrirPanel("panelCels"); });
      inner.appendChild(link);
    }

    card.appendChild(icon);
    card.appendChild(inner);
  }

  // ── Fetch con AbortController, debounce y timeout 10s ────────────────────
  function fetchData(isRetry) {
    if (!isRetry) clearTimeout(_debounceId);
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();
    const signal = _abortCtrl.signal;
    const scrollY = window.scrollY;
    showSpinner();
    hideError();
    const timeout = setTimeout(() => _abortCtrl.abort(), 10000);

    fetch(DATA_URL, { signal })
      .then(res => { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
      .then(data => {
        clearTimeout(timeout);
        hidratarDashboardCogeneracion(data);
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
  if (btnReintentar) btnReintentar.addEventListener("click", () => fetchData(true));

  ["cobertura", "rendimiento-elec", "rendimiento-term", "caldera"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", actualizarSensibilidad);
  });

  // ── Carga inicial ─────────────────────────────────────────────────────────
  fetchData(false);

})();
