/**
 * dashboard-modelado-chp.js
 * Frontend del dashboard de Modelado CHP.
 * Consume los endpoints:
 *   GET  /clientes/<id>/dashboard/modelado-chp/data
 *   GET  /clientes/<id>/dashboard/modelado-chp/curva/<modelado_id>
 *   POST /clientes/<id>/dashboard/modelado-chp/params
 */

(function () {
  "use strict";

  const root = document.getElementById("dashboard-modelado-chp-root");
  if (!root) return;

  const CLIENTE_ID  = parseInt(root.dataset.clienteId, 10);
  let   MEDICION_ID = parseInt(root.dataset.medicionId, 10);

  let chpChart    = null;
  let _modeladoId = null;
  let _abortCtrl  = null;

  // ── Helpers DOM ────────────────────────────────────────────────────────────
  const $  = id => document.getElementById(id);
  const _show = id => $( id)?.classList.remove("d-none");

  // ── Formato de fechas ──────────────────────────────────────────────────────
  const MESES = ["ENE","FEB","MAR","ABR","MAY","JUN",
                 "JUL","AGO","SEP","OCT","NOV","DIC"];

  function fmtFecha(isoStr) {
    const d = new Date(isoStr);
    return `${String(d.getUTCDate()).padStart(2,"0")} ${MESES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }
  const _hide = id => $( id)?.classList.add("d-none");

  function _fmt(n, decimals) {
    return n.toLocaleString("es-MX", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  // ── Leer parámetros actuales de los inputs ─────────────────────────────────
  function getParams() {
    return {
      num_motores:           parseInt($("param-num-motores").value, 10) || 1,
      margen_kw:             parseFloat($("param-margen-kw").value)   || 0,
      rendimiento_electrico: (parseFloat($("param-rendimiento").value) || 42) / 100,
      costo_om_kwh:          parseFloat($("param-costo-om").value)    || 0.015,
      autoconsumo_pct:       (parseFloat($("param-autoconsumo").value) || 3)  / 100,
    };
  }

  // ── fetchModelado ──────────────────────────────────────────────────────────
  function fetchModelado() {
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();
    const signal = _abortCtrl.signal;

    _show("chp-spinner");
    _hide("chp-error-banner");
    _hide("chp-kpis-section");
    _hide("chp-grafica-section");
    _hide("chp-tabla-section");

    const p = getParams();
    const qs = new URLSearchParams({
      medicion_id:           MEDICION_ID,
      num_motores:           p.num_motores,
      margen_kw:             p.margen_kw,
      rendimiento_electrico: p.rendimiento_electrico,
      costo_om_kwh:          p.costo_om_kwh,
      autoconsumo_pct:       p.autoconsumo_pct,
    });

    const timeoutId = setTimeout(() => _abortCtrl.abort(), 60_000);

    fetch(`/clientes/${CLIENTE_ID}/dashboard/modelado-chp/data?${qs}`, { signal })
      .then(r => {
        clearTimeout(timeoutId);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        if (!data.ok) throw new Error(data.error || "Error desconocido");

        // Capacidad nominal
        const capNom = data.params.capacidad_nominal_kw;
        const capUnit = data.params.cap_unitaria_kw;
        if ($("param-cap-nominal")) $("param-cap-nominal").textContent = _fmt(capNom, 0);
        if ($("param-cap-unitaria")) $("param-cap-unitaria").textContent = _fmt(capUnit, 0);

        // KPIs
        const k = data.kpis;
        $("kpi-gen-neta").textContent     = _fmt(k.gen_neta_anual_kwh  / 1000, 1);
        $("kpi-gen-bruta").textContent    = _fmt(k.gen_bruta_anual_kwh / 1000, 1);
        $("kpi-cobertura").textContent    = _fmt(k.cobertura_pct * 100,        1);
        $("kpi-horas-motor").textContent  = _fmt(k.horas_anuales_motor,        0);
        $("kpi-cap-promedio").textContent = _fmt(k.capacidad_promedio_kw,      0);
        $("kpi-consumo-gas").textContent  = _fmt(k.consumo_gas_anual_gj,       1);
        $("kpi-costo-om-anual").textContent = _fmt(k.costo_om_anual_mxn,      0);
        $("kpi-consumo-cliente").textContent = _fmt(k.consumo_cliente_mes_kwh / 1000, 1);

        _show("chp-kpis-section");

        _modeladoId = data.modelado_id;
        return fetchCurva(_modeladoId);
      })
      .catch(err => {
        if (err.name === "AbortError") return;
        clearTimeout(timeoutId);
        const banner = $("chp-error-banner");
        if (banner) {
          $("chp-error-msg").textContent = `Error al cargar el modelado: ${err.message}`;
          _show("chp-error-banner");
        }
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

        // ── Gráfica ──────────────────────────────────────────────────────────
        const chartData = {
          datasets: [
            {
              label: "Demanda real (kW)",
              data: data.ts.map((t, i) => ({ x: t, y: data.demanda_kw[i] })),
              borderColor: "rgba(31,122,76,0.85)",
              backgroundColor: "transparent",
              borderWidth: 1,
              pointRadius: 0,
              tension: 0.1,
            },
            {
              label: "Generación modelada (kW)",
              data: data.ts.map((t, i) => ({ x: t, y: data.gen_neta_kw[i] })),
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

        // Subtítulo: rango de fechas
        const tsFirst = data.ts[0];
        const tsLast  = data.ts[data.ts.length - 1];
        document.getElementById("chp-grafica-subtitulo").textContent =
          `${fmtFecha(tsFirst)} — ${fmtFecha(tsLast)}`;

        _show("chp-grafica-section");

        // ── Tabla diaria ─────────────────────────────────────────────────────
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
            const n      = vals.dem.length;
            const sumDem = vals.dem.reduce((a, b) => a + b, 0);
            const sumGen = vals.gen.reduce((a, b) => a + b, 0);
            const avgDem = sumDem / n;
            const avgGen = sumGen / n;
            const cobertura = sumDem > 0 ? (sumGen / sumDem) * 100 : 0;
            const horasActivas = vals.gen.filter(v => v > 0).length / 12;
            const tr = document.createElement("tr");
            tr.innerHTML = `
              <td style="white-space:nowrap;font-size:.8rem">${day}</td>
              <td class="text-end">${_fmt(avgDem, 1)}</td>
              <td class="text-end">${_fmt(avgGen, 1)}</td>
              <td class="text-end">${_fmt(cobertura, 1)}</td>
              <td class="text-end">${_fmt(horasActivas, 1)}</td>
            `;
            tbody.appendChild(tr);
          });
          _show("chp-tabla-section");
        }
      });
  }

  // ── guardarParams (fire and forget) ───────────────────────────────────────
  function guardarParams() {
    const p = getParams();
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
    fetch(`/clientes/${CLIENTE_ID}/dashboard/modelado-chp/params`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ num_motores: p.num_motores, margen_kw: p.margen_kw }),
    }).catch(() => {/* fire and forget */});
  }

  // ── Listeners ──────────────────────────────────────────────────────────────
  $("btn-recalcular")?.addEventListener("click", () => {
    guardarParams();
    fetchModelado();
  });

  document.addEventListener("medicionActivaChanged", e => {
    MEDICION_ID = e.detail.medicion_id;
    if (chpChart) {
      chpChart.destroy();
      chpChart = null;
    }
    fetchModelado();
  });

  // ── Carga inicial ──────────────────────────────────────────────────────────
  fetchModelado();

})();
