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

  // ── Colores por posición de motor ─────────────────────────────────────────
  const _MOTOR_COLORS = [
    "rgba(42,98,168,0.85)",
    "rgba(210,90,30,0.85)",
    "rgba(50,155,75,0.85)",
    "rgba(155,50,155,0.85)",
  ];

  // ── Gestión dinámica de motores ───────────────────────────────────────────
  let _nextMotorId = 1;

  function _colorMotor(idx) {
    return _MOTOR_COLORS[idx % _MOTOR_COLORS.length];
  }

  function _actualizarTotalKw() {
    const total = Array.from(document.querySelectorAll(".motor-cap-kw"))
      .reduce((s, el) => s + (parseFloat(el.value) || 0), 0);
    const el = $("cap-nominal-total");
    if (el) el.textContent = total > 0
      ? Math.round(total).toLocaleString("es-MX") : "—";
  }

  function _actualizarBtnAddMotor() {
    const btn = $("btn-add-motor");
    if (!btn) return;
    btn.disabled = document.querySelectorAll(".motor-row").length >= 4;
  }

  function _crearMotorRow(motor, idx) {
    const div = document.createElement("div");
    div.className = "motor-row d-flex align-items-center gap-1 border rounded px-2 py-1";
    div.dataset.motorId = motor.id;
    div.style.background = "#f8f9fa";

    const dot = document.createElement("span");
    dot.style.cssText = `width:10px;height:10px;border-radius:50%;`
      + `background:${_colorMotor(idx)};flex-shrink:0`;

    const nombre = document.createElement("input");
    nombre.type = "text";
    nombre.className = "form-control form-control-sm motor-nombre";
    nombre.style.width = "95px";
    nombre.placeholder = `Motor ${motor.id}`;
    nombre.value = motor.nombre || `Motor ${motor.id}`;

    const cap = document.createElement("input");
    cap.type = "number";
    cap.className = "form-control form-control-sm motor-cap-kw";
    cap.style.width = "80px";
    cap.step = "10"; cap.min = "1";
    cap.placeholder = "kW";
    cap.value = motor.capacidad_kw > 0 ? motor.capacidad_kw : "";
    cap.addEventListener("input", _actualizarTotalKw);

    const lbl = document.createElement("span");
    lbl.className = "text-muted";
    lbl.style.fontSize = ".7rem";
    lbl.textContent = "kW";

    const btnRm = document.createElement("button");
    btnRm.type = "button";
    btnRm.className = "btn btn-sm btn-link text-danger p-0 ms-1";
    btnRm.title = "Quitar motor";
    btnRm.innerHTML = '<i class="bi bi-x-lg"></i>';
    btnRm.addEventListener("click", () => {
      // Al menos un motor debe quedar
      if (document.querySelectorAll(".motor-row").length <= 1) return;
      div.remove();
      _actualizarTotalKw();
      _actualizarBtnAddMotor();
    });

    div.append(dot, nombre, cap, lbl, btnRm);
    return div;
  }

  function _inicializarMotores(config) {
    const container = $("motores-config-container");
    if (!container) return;
    container.innerHTML = "";
    _nextMotorId = 0;
    config.forEach((m, i) => {
      _nextMotorId = Math.max(_nextMotorId, m.id || i + 1);
      container.appendChild(_crearMotorRow(m, i));
    });
    _actualizarTotalKw();
    _actualizarBtnAddMotor();
  }

  function getMotoresConfig() {
    return Array.from(document.querySelectorAll(".motor-row")).map((row, i) => ({
      id:           i + 1,
      nombre:       (row.querySelector(".motor-nombre").value.trim()) || `Motor ${i + 1}`,
      capacidad_kw: parseFloat(row.querySelector(".motor-cap-kw").value) || 0,
    })).filter(m => m.capacidad_kw > 0);
  }

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

  // ── Leer parámetros CHP ────────────────────────────────────────────────────
  function getParams() {
    return {
      motores_config:        getMotoresConfig(),
      margen_kw:             parseFloat($("param-margen-kw").value)    || 0,
      rendimiento_electrico: (parseFloat($("param-rendimiento").value) || 40) / 100,
      costo_om_kwh:          parseFloat($("param-costo-om").value)     || 0.30,
      autoconsumo_pct:       (parseFloat($("param-autoconsumo").value) || 3) / 100,
    };
  }

  // ── Leer parámetros de cogeneración ────────────────────────────────────────
  function getCogenParams() {
    const motores    = getMotoresConfig();
    const capNominal = motores.reduce((s, m) => s + (m.capacidad_kw || 0), 0);
    const precioKw   = parseFloat($("param-inversion-usd").value) || 1400;
    const inversion_usd = Math.round(capNominal * precioKw);
    const deduccionFiscal = $("param-deduccion-fiscal")?.checked ?? false;
    const aniosDeduccion  = parseInt($("param-anios-deduccion")?.value || "1", 10);
    return {
      rendimiento_termico:  (parseFloat($("param-rend-termico").value)  || 25) / 100,
      precio_gas:            parseFloat($("param-precio-gas").value)    || null,
      inversion_usd:         inversion_usd > 0 ? inversion_usd : null,
      factor_utilizacion:    parseFloat($("param-factor-util").value)   || 0.9132,
      deduccion_fiscal:      deduccionFiscal,
      anios_deduccion:       aniosDeduccion,
    };
  }

  // ── Agregación horaria ─────────────────────────────────────────────────────
  function agregarPorHora(ts_arr, demanda_arr, gen_arr, motores_data) {
    const buckets = {};
    ts_arr.forEach((t, i) => {
      const hora = t.slice(0, 13);
      if (!buckets[hora]) {
        buckets[hora] = { dem: [], gen: [] };
        if (motores_data) motores_data.forEach(m => { buckets[hora][m.id] = []; });
      }
      buckets[hora].dem.push(demanda_arr[i]);
      buckets[hora].gen.push(gen_arr[i]);
      if (motores_data) {
        motores_data.forEach(m => { buckets[hora][m.id].push(m.gen_kw[i] || 0); });
      }
    });
    const ts_h = [], dem_h = [], gen_h = [];
    const motor_h = {};
    if (motores_data) motores_data.forEach(m => { motor_h[m.id] = []; });
    Object.keys(buckets).sort().forEach(hora => {
      const b = buckets[hora];
      const n = b.dem.length;
      ts_h.push(hora + ":00:00");
      dem_h.push(b.dem.reduce((a, v) => a + v, 0) / n);
      gen_h.push(b.gen.reduce((a, v) => a + v, 0) / n);
      if (motores_data) {
        motores_data.forEach(m => {
          motor_h[m.id].push(b[m.id].reduce((a, v) => a + v, 0) / n);
        });
      }
    });
    return { ts_h, dem_h, gen_h, motor_h };
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
      margen_kw:             p.margen_kw,
      rendimiento_electrico: p.rendimiento_electrico,
      costo_om_kwh:          p.costo_om_kwh,
      autoconsumo_pct:       p.autoconsumo_pct,
    };
    if (p.motores_config && p.motores_config.length > 0) {
      qsObj.motores_config = JSON.stringify(p.motores_config);
    }
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

        // Primera carga: sincronizar motores y precio gas con datos del servidor
        if (_primerasCarga && data.params.motores_config) {
          _inicializarMotores(data.params.motores_config);
        }
        if (data.cogen_defaults && data.cogen_defaults.precio_gas_gj) {
          const inputGas = $("param-precio-gas");
          if (inputGas && parseFloat(inputGas.value) === 0) {
            inputGas.value = data.cogen_defaults.precio_gas_gj;
          }
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

        const motores = data.motores || [];
        const { ts_h, dem_h, gen_h, motor_h } = agregarPorHora(
          data.ts, data.demanda_kw, data.gen_neta_kw, motores
        );

        // Dataset demanda
        const datasets = [
          {
            label: "Demanda real (kW)",
            data: ts_h.map((t, i) => ({ x: t, y: dem_h[i] })),
            borderColor: "rgba(31,122,76,0.85)",
            backgroundColor: "transparent",
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.1,
          },
        ];

        // Datasets por motor (si hay más de uno se muestra individual; si es uno, se usa como total)
        if (motores.length > 1) {
          motores.forEach((m, idx) => {
            datasets.push({
              label: m.nombre || `Motor ${m.id}`,
              data: ts_h.map((t, i) => ({ x: t, y: (motor_h[m.id] || [])[i] || 0 })),
              borderColor: _colorMotor(idx),
              backgroundColor: "transparent",
              borderWidth: 1,
              pointRadius: 0,
              tension: 0.1,
            });
          });
        } else {
          // Motor único: mostrar como "Generación modelada"
          datasets.push({
            label: (motores[0] && motores[0].nombre) || "Generación modelada (kW)",
            data: ts_h.map((t, i) => ({ x: t, y: gen_h[i] })),
            borderColor: _colorMotor(0),
            backgroundColor: "transparent",
            borderWidth: 1,
            pointRadius: 0,
            tension: 0.1,
          });
        }

        // Con >1 motor, añadir línea total en trazo grueso/discontinuo
        if (motores.length > 1) {
          datasets.push({
            label: "Total generado (kW)",
            data: ts_h.map((t, i) => ({ x: t, y: gen_h[i] })),
            borderColor: "rgba(80,80,80,0.55)",
            backgroundColor: "transparent",
            borderWidth: 1.5,
            borderDash: [4, 3],
            pointRadius: 0,
            tension: 0.1,
          });
        }

        const chartData = { datasets };

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

        // Leyenda dinámica
        const leyendaEl = $("chp-leyenda-curva");
        if (leyendaEl) {
          leyendaEl.innerHTML = "";
          chartData.datasets.forEach(ds => {
            const span = document.createElement("span");
            const color = Array.isArray(ds.borderDash)
              ? "rgba(80,80,80,0.55)" : ds.borderColor;
            span.innerHTML = `<span style="display:inline-block;width:20px;height:2px;`
              + `background:${color};vertical-align:middle;margin-right:4px`
              + (Array.isArray(ds.borderDash) ? ";border-top:2px dashed " + color + ";height:0" : "")
              + `"></span>${ds.label}`;
            leyendaEl.appendChild(span);
          });
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
    if (cp.precio_gas)         qsObj.precio_gas         = cp.precio_gas;
    if (cp.inversion_usd)      qsObj.inversion_usd      = cp.inversion_usd;
    if (cp.factor_utilizacion) qsObj.factor_utilizacion = cp.factor_utilizacion;
    qsObj.deduccion_fiscal = cp.deduccion_fiscal ? 1 : 0;
    qsObj.anios_deduccion  = cp.anios_deduccion;

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
          const capNom   = getMotoresConfig().reduce((s, m) => s + (m.capacidad_kw || 0), 0);
          const precioKw = parseFloat($("param-inversion-usd").value) || 1400;
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

        // Usar datos fiscales cuando existan (activos con deducción, o iguales sin ella)
        const _flujoArr = (data.flujo_anual_15_fiscal?.length > 0)
          ? data.flujo_anual_15_fiscal : data.flujo_anual_15;
        const _acumArr  = (data.flujo_acum_15_fiscal?.length > 0)
          ? data.flujo_acum_15_fiscal  : (data.flujo_acum_15 || []);
        if (_flujoArr && _flujoArr.length > 0) {
          _renderFlujo(_flujoArr, _acumArr);
          _showB("chp-flujo-section");
        }

        if (data.tabla_mensual && data.tabla_mensual.length > 0) {
          _renderTablaMensual(data.tabla_mensual);
        }

        // ── CO2 ───────────────────────────────────────────────────────────
        const co2 = data.co2 || {};
        const elCO2Val = document.getElementById("chp-kpi-co2-val");
        if (elCO2Val) {
          const reduccion = parseFloat(co2.reduccion_t || 0);
          elCO2Val.textContent = reduccion > 0
            ? reduccion.toLocaleString("es-MX", {maximumFractionDigits:1})
              + " t CO₂/año"
            : "—";
        }
        const elCO2Sub = document.getElementById("chp-kpi-co2-sublabel");
        if (elCO2Sub && co2.reduccion_pct != null) {
          const arboles = co2.arboles
            ? " · ≈" + Math.round(co2.arboles).toLocaleString("es-MX")
              + " árboles"
            : "";
          elCO2Sub.textContent =
            parseFloat(co2.reduccion_pct).toFixed(1) + "% menos" + arboles;
        }
        const secCO2 = document.getElementById("chp-seccion-co2");
        if (secCO2) secCO2.style.display = co2.reduccion_t ? "" : "none";

        // Donuts CO2 (reusar lógica de dashboard-cogeneracion.js)
        // Actual
        if (typeof renderDonutComponentes === "function" && co2.actual_total_t) {
          const pElec = co2.actual_electricidad_t || 0;
          const pGas  = co2.actual_gas_t || 0;
          const totalActual = pElec + pGas;
          if (totalActual > 0) {
            renderDonutComponentes("chp-donut-co2-actual", [
              { label: "Electricidad", value: pElec,
                color: "rgba(31,122,76,0.75)" },
              { label: "Gas",          value: pGas,
                color: "rgba(232,181,71,0.85)" },
            ]);
          }
          // Proyectado
          const pElecProy = co2.proyectado_electricidad_t || 0;
          const pGasProy  = co2.proyectado_gas_t || 0;
          const totalProy = pElecProy + pGasProy;
          if (totalProy > 0) {
            renderDonutComponentes("chp-donut-co2-proyectado", [
              { label: "Electricidad", value: pElecProy,
                color: "rgba(31,122,76,0.75)" },
              { label: "Gas",          value: pGasProy,
                color: "rgba(232,181,71,0.85)" },
            ]);
          }
        }

        // ── CELs ──────────────────────────────────────────────────────────
        const cels = data.cels || {};
        const elCels = document.getElementById("chp-kpi-cels-val");
        if (elCels) {
          elCels.textContent = cels.cels_mwh_anual != null
            ? parseFloat(cels.cels_mwh_anual)
                .toLocaleString("es-MX", {maximumFractionDigits:2})
            : "—";
        }
        const elCelsEfic = document.getElementById("chp-kpi-cels-eficiencia");
        if (elCelsEfic) {
          elCelsEfic.textContent = cels.es_eficiente
            ? "Cogeneración eficiente ✓" : "";
          elCelsEfic.style.color = cels.es_eficiente ? "var(--color-primary)" : "";
        }

        // ── Energía limpia ────────────────────────────────────────────────
        const elEL = document.getElementById("chp-kpi-energia-limpia-val");
        if (elEL) {
          const pct = data.kpis?.energia_limpia_pct;
          elEL.textContent = pct != null
            ? parseFloat(pct).toLocaleString("es-MX",
                {minimumFractionDigits:1, maximumFractionDigits:1}) + " %"
            : "—";
        }

        // ── Capacidad nominal (desde calcular_cogen, no del modelado) ─────
        const elCapNom = document.getElementById("chp-kpi-cap-nominal-val");
        if (elCapNom && data.kpis?.capacidad_nominal_kw) {
          elCapNom.textContent =
            parseFloat(data.kpis.capacidad_nominal_kw)
              .toLocaleString("es-MX", {maximumFractionDigits:0}) + " kW";
        }

        // Actualizar link del botón Descargar Excel con los parámetros actuales
        actualizarLinkExcel(_modeladoId, getCogenParams());

      })
      .catch(err => {
        $("chp-cogen-error-msg").textContent = `Error al calcular cogeneración: ${err.message}`;
        _show("chp-cogen-error-banner");
      })
      .finally(() => _hide("chp-cogen-spinner"));
  }

  // ── Excel maestro ──────────────────────────────────────────────────────────
  function actualizarLinkExcel(modeladoId, p) {
    const btn = document.getElementById("btn-excel-modelado");
    if (!btn) return;
    btn.href =
      `/clientes/${CLIENTE_ID}/dashboard/modelado-chp/excel`
      + `?modelado_id=${modeladoId}`
      + `&rendimiento_termico=${p.rendimiento_termico}`
      + (p.precio_gas    ? `&precio_gas_gj=${p.precio_gas}`         : "")
      + (p.inversion_usd ? `&inversion_usd=${p.inversion_usd}`      : "")
      + `&deduccion_fiscal=${p.deduccion_fiscal ? 1 : 0}`
      + `&anios_deduccion=${p.anios_deduccion}`;
  }

  // ── guardarParams (fire and forget) ───────────────────────────────────────
  function guardarParams() {
    const p      = getParams();
    const cogenP = getCogenParams();
    const csrf   = document.querySelector('meta[name="csrf-token"]')?.content || "";
    fetch(`/clientes/${CLIENTE_ID}/dashboard/modelado-chp/params`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({
        motores:               p.motores_config,
        margen_kw:             p.margen_kw,
        rendimiento_electrico: parseFloat(document.getElementById("param-rendimiento")?.value) || 40,
        rendimiento_termico:   cogenP.rendimiento_termico * 100,
        precio_gas_gj:         cogenP.precio_gas || 0,
        costo_om_kwh:          p.costo_om_kwh,
        precio_motor_usd_kw:   parseFloat(document.getElementById("param-inversion-usd")?.value) || 1400,
        autoconsumo_pct:       p.autoconsumo_pct * 100,
        deduccion_fiscal:      document.getElementById("param-deduccion-fiscal")?.checked ?? false,
        anios_deduccion:       parseInt(document.getElementById("param-anios-deduccion")?.value || "1", 10),
      }),
    }).catch(() => {});
  }

  // ── Listeners ──────────────────────────────────────────────────────────────
  $("btn-recalcular").addEventListener("click", () => {
    guardarParams();
    fetchModelado();
  });

  $("btn-add-motor").addEventListener("click", () => {
    const rows = document.querySelectorAll(".motor-row");
    if (rows.length >= 4) return;
    _nextMotorId += 1;
    const idx = rows.length;
    const motor = { id: _nextMotorId, nombre: `Motor ${_nextMotorId}`, capacidad_kw: 0 };
    const container = $("motores-config-container");
    if (container) container.appendChild(_crearMotorRow(motor, idx));
    _actualizarTotalKw();
    _actualizarBtnAddMotor();
  });

  $("param-deduccion-fiscal").addEventListener("change", function () {
    const col = $("col-anios-deduccion");
    if (col) col.style.display = this.checked ? "" : "none";
  });

  document.addEventListener("medicionActivaChanged", e => {
    MEDICION_ID    = e.detail.medicion_id;
    _primerasCarga = true;
    [chpChart, chpCogenChart, chpCascadaChart, chpFlujoChart, chpDonutChart].forEach(c => { if (c) c.destroy(); });
    chpChart = chpCogenChart = chpCascadaChart = chpFlujoChart = chpDonutChart = null;
    fetchModelado();
  });

  // ── Carga inicial ──────────────────────────────────────────────────────────
  // Leer parámetros guardados de sesión
  const _sessionParamsRaw = root.dataset.sessionParams;
  let _sessionParams = {};
  try {
    _sessionParams = _sessionParamsRaw ? JSON.parse(_sessionParamsRaw) : {};
  } catch(e) { _sessionParams = {}; }

  // Aplicar parámetros guardados si existen (antes de inicializar motores)
  function aplicarSessionParams(p) {
    if (!p || Object.keys(p).length === 0) return;

    // Motores: preferir session params sobre chp_motores_config legacy
    if (p.motores && p.motores.length > 0) {
      _inicializarMotores(p.motores);
    }

    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el && val !== undefined && val !== null) el.value = val;
    };
    setVal("param-margen-kw",      p.margen_kw);
    setVal("param-rendimiento",    p.rendimiento_electrico);
    setVal("param-rend-termico",   p.rendimiento_termico);
    setVal("param-precio-gas",     p.precio_gas_gj);
    setVal("param-costo-om",       p.costo_om_kwh);
    setVal("param-inversion-usd",  p.precio_motor_usd_kw);
    setVal("param-autoconsumo",    p.autoconsumo_pct);
    setVal("param-anios-deduccion",p.anios_deduccion);

    const chk = document.getElementById("param-deduccion-fiscal");
    if (chk && p.deduccion_fiscal !== undefined) {
      chk.checked = !!p.deduccion_fiscal;
      const col = document.getElementById("col-anios-deduccion");
      if (col) col.style.display = chk.checked ? "" : "none";
    }
  }

  // Inicializar motores: session params tienen prioridad; fallback a chp_motores_config legacy
  (() => {
    if (_sessionParams.motores && _sessionParams.motores.length > 0) {
      _inicializarMotores(_sessionParams.motores);
    } else {
      let savedMotores = null;
      try { savedMotores = JSON.parse(root.dataset.motoresConfig); } catch (_) {}
      if (!savedMotores || !Array.isArray(savedMotores) || savedMotores.length === 0) {
        savedMotores = [{ id: 1, nombre: "Motor 1", capacidad_kw: 0 }];
      }
      _inicializarMotores(savedMotores);
    }
  })();

  // Aplicar resto de parámetros de sesión (sin motores, ya inicializados arriba)
  (() => {
    const p = _sessionParams;
    if (!p || Object.keys(p).length === 0) return;
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el && val !== undefined && val !== null) el.value = val;
    };
    setVal("param-margen-kw",      p.margen_kw);
    setVal("param-rendimiento",    p.rendimiento_electrico);
    setVal("param-rend-termico",   p.rendimiento_termico);
    setVal("param-precio-gas",     p.precio_gas_gj);
    setVal("param-costo-om",       p.costo_om_kwh);
    setVal("param-inversion-usd",  p.precio_motor_usd_kw);
    setVal("param-autoconsumo",    p.autoconsumo_pct);
    setVal("param-anios-deduccion",p.anios_deduccion);
    const chk = document.getElementById("param-deduccion-fiscal");
    if (chk && p.deduccion_fiscal !== undefined) {
      chk.checked = !!p.deduccion_fiscal;
      const col = document.getElementById("col-anios-deduccion");
      if (col) col.style.display = chk.checked ? "" : "none";
    }
  })();

  fetchModelado();

})();
