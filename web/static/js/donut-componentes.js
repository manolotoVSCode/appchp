/**
 * donut-componentes.js
 * Función global reutilizable para dibujar un donut SVG con 4 segmentos.
 * Usada en Contabilidad (desglose costo total) y Cogeneración (ahorro eléctrico).
 */

/**
 * Construye el path SVG de un arco anular (segmento de donut).
 */
function arcPath(cx, cy, rOut, rIn, angIni, angFin) {
  const x1 = cx + rOut * Math.cos(angIni);
  const y1 = cy + rOut * Math.sin(angIni);
  const x2 = cx + rOut * Math.cos(angFin);
  const y2 = cy + rOut * Math.sin(angFin);
  const x3 = cx + rIn  * Math.cos(angFin);
  const y3 = cy + rIn  * Math.sin(angFin);
  const x4 = cx + rIn  * Math.cos(angIni);
  const y4 = cy + rIn  * Math.sin(angIni);
  const largeArc = (angFin - angIni) > Math.PI ? 1 : 0;
  return [
    `M ${x1} ${y1}`,
    `A ${rOut} ${rOut} 0 ${largeArc} 1 ${x2} ${y2}`,
    `L ${x3} ${y3}`,
    `A ${rIn} ${rIn} 0 ${largeArc} 0 ${x4} ${y4}`,
    'Z',
  ].join(' ');
}

/**
 * Resuelve una referencia CSS var(--nombre) al valor hexadecimal real.
 * SVG no resuelve variables CSS en atributos (solo en propiedades CSS),
 * por lo que es necesario leer el valor computado antes de generar el markup.
 * @param {string} color - p.ej. "var(--color-primary)" o "#1F7A4C"
 * @returns {string} valor resuelto
 */
function resolveColor(color) {
  if (!color) return color;
  const m = color.match(/^var\(--([^)]+)\)$/);
  if (!m) return color;
  return getComputedStyle(document.documentElement).getPropertyValue('--' + m[1]).trim() || color;
}

/**
 * Renderiza un donut SVG con 4 segmentos en el contenedor dado.
 * @param {string} containerId - id del div contenedor
 * @param {Array<{nombre: string, pct: number, color: string}>} datos
 */
function renderDonutComponentes(containerId, datos) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const W = 280, H = 280;
  const cx = W / 2, cy = H / 2;
  const rOut = 100, rIn = 60;

  const totalPct = datos.reduce((acc, d) => acc + d.pct, 0);
  if (totalPct === 0) {
    container.innerHTML = '<div class="text-center text-muted small p-4">Sin datos</div>';
    return;
  }

  const rMid = (rOut + rIn) / 2;
  let anguloInicio = -Math.PI / 2;
  const paths = datos.map(d => {
    const fraccion  = d.pct / totalPct;
    const anguloFin = anguloInicio + fraccion * Math.PI * 2;
    const midAngle  = anguloInicio + (anguloFin - anguloInicio) / 2;
    const seg = {
      path:      arcPath(cx, cy, rOut, rIn, anguloInicio, anguloFin),
      color:     resolveColor(d.color),
      nombre:    d.nombre,
      pct:       d.pct,
      labelX:    cx + rMid * Math.cos(midAngle),
      labelY:    cy + rMid * Math.sin(midAngle),
    };
    anguloInicio = anguloFin;
    return seg;
  });

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"
         style="width:100%; height:auto; display:block">
      ${paths.map(p => `
        <path d="${p.path}" fill="${p.color}" stroke="#fff" stroke-width="2">
          <title>${p.nombre}: ${p.pct}%</title>
        </path>`).join('')}
      ${paths.filter(p => p.pct >= 5).map(p => `
        <text x="${p.labelX.toFixed(1)}" y="${p.labelY.toFixed(1)}"
              text-anchor="middle" dominant-baseline="central"
              font-size="13" font-weight="600" fill="#fff"
              stroke="#000" stroke-width="2.5"
              style="paint-order:stroke fill"
              font-family="system-ui">${p.pct}%</text>`).join('')}
      <text x="${cx}" y="${cy - 6}" text-anchor="middle"
            font-size="14" font-weight="600" fill="#1A1A1A"
            font-family="system-ui">Composición</text>
      <text x="${cx}" y="${cy + 14}" text-anchor="middle"
            font-size="11" fill="#9A9A9A"
            font-family="system-ui">por componente</text>
    </svg>`;
}
