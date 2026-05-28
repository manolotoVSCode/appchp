/**
 * dashboard-modelado-chp.js
 * Frontend del dashboard de Modelado CHP.
 * Consume los endpoints:
 *   GET  /clientes/<id>/dashboard/modelado-chp/data
 *   GET  /clientes/<id>/dashboard/modelado-chp/curva/<modelado_id>
 *   GET  /clientes/<id>/dashboard/modelado-chp/cogen-data
 *   POST /clientes/<id>/dashboard/modelado-chp/params
 */

(function () {
  "use strict";

  const root = document.getElementById("dashboard-modelado-chp-root");
  if (!root) return;

  const CLIENTE_ID  = parseInt(root.dataset.clienteId, 10);
  let   MEDICION_ID = parseInt(root.dataset.medicionId, 10);

  let chpChart         = null;
  let chpCogenChart    = null;
  let chpCascadaChart  = null;
  let chpFlujoChart    = null;
  let chpDonutChart    = null;
  let _modeladoId      = null;
  let _abortCtrl       = null;
  let _primerasCarga   = true;

  // ── Helpers DOM ────────────────────────────────────────────────────────────
  const $      = id => document.getElementById(id);
  const _show  = id => $(id)?.classList.remove("d-none");
  const _hide  = id => $(id)?.classList.add("d-none");
  const _showB = id => { const el = $(id); if (el) el.style.display = ""; };
  const _hideB = id => { const el = $(id); if (el) el.style.display = "none"; };

  // ── Formato ────────────────────────────────────────────────────────────────
  const MESES = ["ENE","FEB","MAR","ABR","MAY","JUN",
                 "JUL","AGO","SEP","OCT","NOV","DIC"];

  function fmtFecha(isoStr) {
    const d = new Date(isoStr);
    return `${String(d.getUTCDate()).padStart(2,"0")} ${MESES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }

  function _fmt(n, decimals) {
    return n.toLocaleString("es-MX", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  const _fmtMXN = v => "$" + Math.round(v).toLocaleString("es-MX");

  // ── Inversión total (precio/kW × cap nominal) ──────────────────────────────
  function actualizarInversionTotal() {
    const cap      = parseFloat($("param-cap-nominal-input").value) || 0;
    const precioKw = parseFloat($("param-inversion-usd").value)    || 1400;
    const total    = Math.round(cap * precioKw);
    const lbl      = $("chp-inversion-total-label");
    if (lbl) lbl.textContent = total > 0
      ? "$" + total.toLocaleString("es-MX") + " USD total"
      : "—";
  }

  $("param-cap-nominal-input").addEventListener("input",  actualizarInversionTotal);
  $("param-inversion-usd").addEventListener("input",      actualizarInversionTotal);
  $("param-num-motores").addEventListener("change",       actualizarInversionTotal);

  // ── Leer parámetros CHP ────────────────────────────────────────────────────
  function getParams() {
    return {
      num_motores:           parseInt($("param-num-motores").value, 10) || 1,
      capacidad_nominal_kw:  parseFloat($("param-cap-nominal-input").value) || 0,
      margen_kw:             parseFloat($("param-margen-kw").value)         || 0,
      rendimiento_electrico: (parseFloat($("param-rendimiento").value) || 40) / 100,
      costo_om_kwh:          parseFloat($("param-costo-om").value)          || 0.30,
      autoconsumo_pct:       (parseFloat($("param-autoconsumo").value) || 3) / 100,
    };
  }

  // ── Leer parámetros de cogeneración ────────────────────────────────────────
  function getCogenParams() {
    const precioKw   = parseFloat($("param-inversion-usd").value)      || 1400;
    const capNominal = parseFloat($("param-cap-nominal-input").value)   || 0;
    const inversion_usd = Math.round(capNominal * precioKw);
    return {
      rendimiento_termico:  (parseFloat($("param-rend-termico").value)  || 45) / 100,
      precio_gas:            parseFloat($("param-precio-gas").value)    || null,
      inversion_usd:         inversion_usd > 0 ? inversion_usd : null,
      factor_utilizacion:    parseFloat($("param-factor-util").value)   || 0.9132,
    };
  }

  // ── Agregación horaria ─────────────────────────────────────────────────────
  function agregarPorHora(ts_arr, demanda_arr, gen_arr) {
    const buckets = {};
    ts_arr.forEach((t, i) => {
      const hora = t.slice(0, 13); // "YYYY-MM-DDTHH"
      if (!buckets[hora]) buckets[hora] = { dem: [], gen: [] };
      buckets[hora].dem.push(demanda_arr[i]);
      buckets[hora].gen.push(gen_arr[i]);
    });
    const ts_h = [], dem_h = [], gen_h = [];
    Object.keys(buckets).sort().forEach(hora => {
      const b = buckets[hora];
      ts_h.push(hora + ":00:00");
      dem_h.push(b.dem.reduce((a, v) => a + v, 0) / b.dem.length);
      gen_h.push(b.gen.reduce((a, v) => a + v, 0) / b.gen.length);
    });
    return { ts_h, dem_h, gen_h };
  }

  // ── fetchModelado ──────────────────────────────────────────────────────────
  function fetchModelado() {
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();
    const signal = _abortCtrl.signal;

    _show("chp-spinner");
    _hide("chp-error-banner");
    _hide("chp-kpis-section");
    _hide("chp-tabla-section");
    _hideB("chp-cincominutal-section");
    _hideB("chp-cogen-section");

    const p = getParams();
    const qsObj = {
      medicion_id:           MEDICION_ID,
      num_motores:           p.num_motores,
      margen_kw:             p.margen_kw,
      rendimiento_electrico: p.rendimiento_electrico,
      costo_om_kwh:          p.costo_om_kwh,
      autoconsumo_pct:       p.autoconsumo_pct,
    };
    if (p.capacidad_nominal_kw > 0) qsObj.capacidad_nominal_kw = p.capacidad_nominal_kw;
    const qs = new URLSearchParams(qsObj);

    const timeoutId = setTimeout(() => _abortCtrl.abort(), 60_000);

    fetch(`/clientes/${CLIENTE_ID}/dashboard/modelado-chp/data?${qs}`, { signal })
      .then(r => {
        clearTimeout(timeoutId);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        if (!data.ok) throw new Error(data.error || "Error desconocido");

        const capNom   = data.params.capacidad_nominal_kw;
        const capInput = $("param-cap-nominal-input");

        if (_primerasCarga || !capInput.value) {
          capInput.value = Math.round(capNom);

          // Precio gas desde cogen_defaults si viene y el input sigue en 0
          if (data.cogen_defaults && data.cogen_defaults.precio_gas_gj) {
            const inputGas = $("param-precio-gas");
            if (inputGas && parseFloat(inputGas.value) === 0) {
              inputGas.value = data.cogen_defaults.precio_gas_gj;
            }
          }

          // Actualizar label inversión total (mantiene 1400 USD/kW como default)
          actualizarInversionTotal();
        }

        _primerasCarga = false;

        // KPIs modelado
        const k = data.kpis;
        $("kpi-gen-neta").textContent      = _fmt(k.gen_neta_anual_kwh  / 1000, 1);
        $("kpi-gen-bruta").textContent     = _fmt(k.gen_bruta_anual_kwh / 1000, 1);
        $("kpi-cobertura").textContent     = _fmt(k.cobertura_pct * 100,        1);
        $("kpi-horas-motor").textContent   = _fmt(k.horas_anuales_motor,        0);
        $("kpi-cap-promedio").textContent  = _fmt(k.capacidad_promedio_kw,      0);
        $("kpi-consumo-gas").textContent   = _fmt(k.consumo_gas_anual_gj,       1);
        $("kpi-costo-om-anual").textContent  = _fmt(k.costo_om_anual_mxn,      0);
        $("kpi-consumo-cliente").textContent = _fmt((data.params.consumo_anual_kwh || 0) / 1000, 1);

        _show("chp-kpis-section");

        _modeladoId = data.modelado_id;
        return fetchCurva(_modeladoId);
      })
      .catch(err => {
        if (err.name === "AbortError") return;
        clearTimeout(timeoutId);
        $("chp-error-msg").textContent = `Error al cargar el modelado: ${err.message}`;
        _show("chp-error-banner");
      })
      .finally(() => _hide("chp-spinner"));
  }

  // ── fetchCurva ─────────────────────────────────────────────────────────────
  function fetchCurva(modeladoId) {
    return fetch(`/clientes/${CLIENTE_ID}/dashboard/modelado-chp/curva/${modeladoId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        if (!data.ts || data.ts.length === 0) return;

        // Agregar a horas para la gráfica
        const { ts_h, dem_h, gen_h } = agregarPorHora(data.ts, data.demanda_kw, data.gen_neta_kw);

        const chartData = {
          datasets: [
            {
              label: "Demanda real (kW)",
              data: ts_h.map((t, i) => ({ x: t, y: dem_h[i] })),
              borderColor: "rgba(31,122,76,0.85)",
              backgroundColor: "transparent",
              borderWidth: 1,
              pointRadius: 0,
              tension: 0.1,
            },
            {
              label: "Generación modelada (kW)",
              data: ts_h.map((t, i) => ({ x: t, y: gen_h[i] })),
              borderColor: "rgba(42,98,168,0.85)",
              backgroundColor: "transparent",
              borderWidth: 1,
              pointRadius: 0,
              tension: 0.1,
            },
          ],
        };

        const chartOptions = {
          responsive: true,
          maintainAspectRatio: true,
          animation: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: c => `${c.dataset.label}: ${c.parsed.y.toLocaleString("es-MX", { maximumFractionDigits: 1 })} kW`,
                title: ts => ts[0].raw.x.replace("T", " ").slice(0, 16),
              },
            },
          },
          scales: {
            x: {
              type: "time",
              time: {
                unit: "day",
                tooltipFormat: "yyyy-MM-dd HH:mm",
                displayFormats: { day: "d" },
              },
              ticks: { maxTicksLimit: 31, maxRotation: 0, autoSkip: true },
              grid: {
                color: ctx => ctx.tick && ctx.tick.major ? "rgba(0,0,0,0.15)" : "transparent",
                lineWidth: ctx => ctx.tick && ctx.tick.major ? 1 : 0,
              },
              border: { display: false },
            },
            y: {
              min: 0,
              ticks: {
                callback: v => v.toLocaleString("es-MX", { maximumFractionDigits: 0 }) + " kW",
              },
              grid: { color: "rgba(0,0,0,0.06)" },
            },
          },
        };

        const canvas = $("chartCHP");
        if (!canvas) return;
        if (!chpChart) {
          chpChart = new Chart(canvas, { type: "line", data: chartData, options: chartOptions });
        } else {
          chpChart.data = chartData;
          chpChart.update();
        }

        // Subtítulo con rango de fechas
        const tsFirst = data.ts[0];
        const tsLast  = data.ts[data.ts.length - 1];
        $("chp-grafica-subtitulo").textContent =
          `${fmtFecha(tsFirst)} — ${fmtFecha(tsLast)} · Potencia media por hora (kW)`;

        _showB("chp-cincominutal-section");

        // Tabla diaria (datos originales 5-min)
        const byDay = {};
        data.ts.forEach((t, i) => {
          const day = t.slice(0, 10);
          if (!byDay[day]) byDay[day] = { dem: [], gen: [] };
          byDay[day].dem.push(data.demanda_kw[i]);
          byDay[day].gen.push(data.gen_neta_kw[i]);
        });

        const tbody = $("tbody-chp-diaria");
        if (tbody) {
          tbody.innerHTML = "";
          Object.entries(byDay).sort().forEach(([day, vals]) => {
            const n         = vals.dem.length;
            const sumDem    = vals.dem.reduce((a, b) => a + b, 0);
            const sumGen    = vals.gen.reduce((a, b) => a + b, 0);
            const cobertura = sumDem > 0 ? (sumGen / sumDem) * 100 : 0;
            const horasActivas = vals.gen.filter(v => v > 0).length / 12;
            const tr = document.createElement("tr");
            tr.innerHTML = `
              <td style="white-space:nowrap;font-size:.8rem">${day}</td>
              <td class="text-end">${_fmt(sumDem / n, 1)}</td>
              <td class="text-end">${_fmt(sumGen / n, 1)}</td>
              <td class="text-end">${_fmt(cobertura, 1)}</td>
              <td class="text-end">${_fmt(horasActivas, 1)}</td>
            `;
            tbody.appendChild(tr);
          });
          _show("chp-tabla-section");
        }

        return fetchCogenData(modeladoId);
      });
  }

  // ── Renderizado cogeneración ───────────────────────────────────────────────

  function chpRenderGraficaMensual(data) {
    const canvas = $("chp-chartCogen");
    if (!canvas) return;
    const labels      = data.chart_labels      || [];
    const ahorro_elec = data.chart_ahorro_elec || [];
    const ah_caldera  = data.chart_ahorro_caldera || [];
    const costo_gas   = data.chart_costo_gas   || [];
    const om          = data.chart_om          || [];
    const ebitda      = data.chart_ebitda      || [];

    const chartData = {
      labels,
      datasets: [
        { label: "Ahorro Electricidad", data: ahorro_elec,            backgroundColor: "rgba(106,138,154,0.65)", stack: "componentes" },
        { label: "Ahorro Caldera",      data: ah_caldera,             backgroundColor: "rgba(232,181,71,0.65)",  stack: "componentes" },
        { label: "Costo Gas Cogen",     data: costo_gas.map(v => -v), backgroundColor: "rgba(216,90,90,0.65)",  stack: "componentes" },
        { label: "O&M",                 data: om.map(v => -v),        backgroundColor: "rgba(180,100,180,0.65)", stack: "componentes" },
        {
          type: "line",
          label: "Ahorro Neto",
          data: ebitda,
          borderColor: "#1F7A4C",
          backgroundColor: "rgba(31,122,76,0.1)",
          borderWidth: 2,
          pointRadius: 4,
          fill: false,
          tension: 0.3,
        },
      ],
    };
    const opts = {
      responsive: true,
      maintainAspectRatio: true,
      animation: false,
      plugins: {
        legend: { display: true, position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${_fmtMXN(c.parsed.y)}` } },
      },
      scales: {
        x: { grid: { display: false } },
        y: { stacked: true, ticks: { callback: v => _fmtMXN(v) }, grid: { color: "rgba(0,0,0,0.06)" } },
      },
    };
    if (!chpCogenChart) {
      chpCogenChart = new Chart(canvas, { type: "bar", data: chartData, options: opts });
    } else {
      chpCogenChart.data = chartData;
      chpCogenChart.update();
    }
  }

  function _renderCascada(ah_elec, ah_caldera, costo_gas, om, ahorro_neto) {
    const canvas = $("chp-waterfallChart");
    if (!canvas) return;
    const labels = ["Ah. Eléctrico", "Ah. Caldera", "Costo Gas", "O&M", "Ahorro Neto"];
    const vals   = [ah_elec, ah_caldera, -costo_gas, -om, ahorro_neto];
    const colors = vals.map(v => v >= 0 ? "rgba(42,98,168,0.75)" : "rgba(200,60,60,0.75)");
    const chartData = {
      labels,
      datasets: [{ label: "MXN", data: vals, backgroundColor: colors, borderRadius: 3 }],
    };
    const opts = {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => _fmtMXN(c.parsed.x) } },
      },
      scales: {
        x: { ticks: { callback: v => _fmtMXN(v) }, grid: { color: "rgba(0,0,0,0.06)" } },
        y: { grid: { display: false } },
      },
    };
    if (!chpCascadaChart) {
      chpCascadaChart = new Chart(canvas, { type: "bar", data: chartData, options: opts });
    } else {
      chpCascadaChart.data = chartData;
      chpCascadaChart.update();
    }
  }

  function _renderFlujo(flujo_anual, flujo_acum) {
    const canvas = $("chp-chart15Year");
    if (!canvas) return;
    const labels = flujo_anual.map((_, i) => i === 0 ? "Inv." : `Año ${i}`);
    const chartData = {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Flujo anual",
          data: flujo_anual,
          backgroundColor: flujo_anual.map(v => v >= 0 ? "rgba(42,98,168,0.55)" : "rgba(200,60,60,0.45)"),
          yAxisID: "y",
        },
        {
          type: "line",
          label: "Flujo acumulado",
          data: flujo_acum,
          borderColor: "rgba(31,122,76,0.9)",
          backgroundColor: "transparent",
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.1,
          yAxisID: "y",
        },
      ],
    };
    const opts = {
      responsive: true,
      maintainAspectRatio: true,
      animation: false,
      plugins: {
        legend: { display: true, position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${_fmtMXN(c.parsed.y)}` } },
      },
      scales: {
        y: { ticks: { callback: v => _fmtMXN(v) }, grid: { color: "rgba(0,0,0,0.06)" } },
        x: { grid: { display: false } },
      },
    };
    if (!chpFlujoChart) {
      chpFlujoChart = new Chart(canvas, { type: "bar", data: chartData, options: opts });
    } else {
      chpFlujoChart.data = chartData;
      chpFlujoChart.update();
    }
  }

  function _renderDonutIngresos(ahElec, ahCaldera) {
    const canvas = $("chp-chartCompAhorroNeto");
    if (!canvas) return;
    const chartData = {
      labels: ["Ahorro Electricidad", "Ahorro Caldera"],
      datasets: [{
        data: [ahElec, ahCaldera],
        backgroundColor: ["#1F3A5F", "#E8B547"],
        borderWidth: 0,
      }],
    };
    const opts = {
      responsive: true,
      animation: false,
      plugins: {
        legend: { display: true, position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: c => `${c.label}: ${_fmtMXN(c.parsed)}` } },
      },
    };
    if (!chpDonutChart) {
      chpDonutChart = new Chart(canvas, { type: "doughnut", data: chartData, options: opts });
    } else {
      chpDonutChart.data = chartData;
      chpDonutChart.update();
    }
  }

  function _renderTablaMensual(filas) {
    const tbody = $("chp-tbody-tabla-mensual");
    if (!tbody) return;
    tbody.innerHTML = "";
    let sumAhElec = 0, sumAhCal = 0, sumGas = 0, sumOM = 0, sumEbitda = 0;
    filas.forEach(f => {
      sumAhElec  += f.ahorro_electricidad_mxn;
      sumAhCal   += f.ahorro_caldera_mxn;
      sumGas     += f.costo_gas_cogen_mxn;
      sumOM      += f.gasto_om_mes_mxn;
      sumEbitda  += f.ebitda_mes_mxn;
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="white-space:nowrap;font-size:.8rem">${f.periodo}</td>
        <td class="text-end">${_fmtMXN(f.ahorro_electricidad_mxn)}</td>
        <td class="text-end">${_fmtMXN(f.ahorro_caldera_mxn)}</td>
        <td class="text-end">${_fmtMXN(f.costo_gas_cogen_mxn)}</td>
        <td class="text-end">${_fmtMXN(f.gasto_om_mes_mxn)}</td>
        <td class="text-end fw-semibold">${_fmtMXN(f.ebitda_mes_mxn)}</td>
      `;
      tbody.appendChild(tr);
    });
    const tf = document.createElement("tr");
    tf.className = "table-light fw-bold";
    tf.innerHTML = `
      <td>Total</td>
      <td class="text-end">${_fmtMXN(sumAhElec)}</td>
      <td class="text-end">${_fmtMXN(sumAhCal)}</td>
      <td class="text-end">${_fmtMXN(sumGas)}</td>
      <td class="text-end">${_fmtMXN(sumOM)}</td>
      <td class="text-end">${_fmtMXN(sumEbitda)}</td>
    `;
    tbody.appendChild(tf);
  }

  // ── fetchCogenData ─────────────────────────────────────────────────────────
  function fetchCogenData(modeladoId) {
    _showB("chp-cogen-section");
    _show("chp-cogen-spinner");
    _hide("chp-cogen-error-banner");
    _hideB("chp-seccion-cascada");
    _hideB("chp-flujo-section");
    _hideB("chp-seccion-inversion");
    _hide("chp-graficaMensual-section");

    const cp = getCogenParams();
    const qsObj = {
      modelado_id:         modeladoId,
      rendimiento_termico: cp.rendimiento_termico,
    };
    if (cp.precio_gas)        qsObj.precio_gas        = cp.precio_gas;
    if (cp.inversion_usd)     qsObj.inversion_usd     = cp.inversion_usd;
    if (cp.factor_utilizacion) qsObj.factor_utilizacion = cp.factor_utilizacion;

    const qs = new URLSearchParams(qsObj);

    return fetch(`/clientes/${CLIENTE_ID}/dashboard/modelado-chp/cogen-data?${qs}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        if (!data.ok) throw new Error(data.error || "Error desconocido");

        const k         = data.kpis;
        const ahElec    = k.ahorro_electricidad_anual;
        const ahCaldera = k.ahorro_caldera_anual;
        const costoGas  = k.costo_gas_cogen_anual;
        const om        = k.gasto_om_anual;
        const ebitda    = k.ebitda_anual;
        const invMxn    = k.inversion_mxn || 0;

        // KPIs Ingresos
        $("chp-kpi-ah-elec-val").textContent        = _fmtMXN(ahElec);
        $("chp-kpi-caldera-val").textContent        = _fmtMXN(ahCaldera);
        $("chp-kpi-total-ingresos-val").textContent = _fmtMXN(ahElec + ahCaldera);

        // KPIs Gastos
        $("chp-kpi-gas-val").textContent          = _fmtMXN(costoGas);
        $("chp-kpi-om-val").textContent           = _fmtMXN(om);
        $("chp-kpi-total-gastos-val").textContent = _fmtMXN(costoGas + om);

        // Ahorro Neto
        $("chp-kpi-ahorro-neto-val").textContent = _fmtMXN(ebitda);

        // Donut composición ingresos
        _renderDonutIngresos(ahElec, ahCaldera);

        // Sección Inversión y Retorno
        if (invMxn > 0) {
          const capNom   = parseFloat($("param-cap-nominal-input").value) || 0;
          const precioKw = parseFloat($("param-inversion-usd").value)    || 1400;
          const invUsd   = Math.round(capNom * precioKw);

          const capNomEl = $("chp-kpi-cap-nominal-val");
          if (capNomEl) capNomEl.textContent = Math.round(capNom).toLocaleString("es-MX") + " kW";

          const invUsdEl = $("chp-kpi-inversion-usd-val");
          if (invUsdEl) invUsdEl.textContent = "$" + invUsd.toLocaleString("es-MX") + " USD";

          const invMxnEl = $("chp-kpi-inversion-mxn-val");
          if (invMxnEl) invMxnEl.textContent = _fmtMXN(invMxn) + " MXN";

          const pb = data.payback_con_beneficio ?? data.payback_inicial;
          const pbEl = $("chp-kpi-payback-val");
          if (pbEl) pbEl.textContent = pb != null ? _fmt(pb, 2) + " años*" : "> 15 años";

          _showB("chp-seccion-inversion");
        }

        chpRenderGraficaMensual(data);
        _show("chp-graficaMensual-section");

        _renderCascada(ahElec, ahCaldera, costoGas, om, ebitda);
        _showB("chp-seccion-cascada");

        if (data.flujo_anual_15 && data.flujo_anual_15.length > 0) {
          _renderFlujo(data.flujo_anual_15, data.flujo_acum_15 || []);
          _showB("chp-flujo-section");
        }

        if (data.tabla_mensual && data.tabla_mensual.length > 0) {
          _renderTablaMensual(data.tabla_mensual);
        }
      })
      .catch(err => {
        $("chp-cogen-error-msg").textContent = `Error al calcular cogeneración: ${err.message}`;
        _show("chp-cogen-error-banner");
      })
      .finally(() => _hide("chp-cogen-spinner"));
  }

  // ── guardarParams (fire and forget) ───────────────────────────────────────
  function guardarParams() {
    const p    = getParams();
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
    fetch(`/clientes/${CLIENTE_ID}/dashboard/modelado-chp/params`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ num_motores: p.num_motores, margen_kw: p.margen_kw }),
    }).catch(() => {});
  }

  // ── Listeners ──────────────────────────────────────────────────────────────
  $("btn-recalcular").addEventListener("click", () => {
    guardarParams();
    fetchModelado();
  });

  document.addEventListener("medicionActivaChanged", e => {
    MEDICION_ID    = e.detail.medicion_id;
    _primerasCarga = true;
    [chpChart, chpCogenChart, chpCascadaChart, chpFlujoChart, chpDonutChart].forEach(c => { if (c) c.destroy(); });
    chpChart = chpCogenChart = chpCascadaChart = chpFlujoChart = chpDonutChart = null;
    fetchModelado();
  });

  // ── Carga inicial ──────────────────────────────────────────────────────────
  fetchModelado();

})();
