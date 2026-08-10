/**
 * UnifilarCore — Motor SVG compartido para renderizado de esquemas unifilares.
 *
 * Exporta window.UnifilarCore = { renderUnifilar, detectarCiclo }.
 * No depende de ningún DOM ID hardcodeado; recibe el SVG y el contenedor
 * como parámetros.
 *
 * Usado por:
 *   - dashboard-telemetria.js (vista de solo lectura, con datos de energía)
 *   - activos-unifilar.js (vista de edición, con drag-drop y panel de detalle)
 */
(function (global) {
  "use strict";

  // ── Constantes visuales ────────────────────────────────────────────────────
  var NS = "http://www.w3.org/2000/svg";
  var C_PRIMARIO   = "#1F3A5F";
  var C_PRIMARIO_L = "#2E5C8A";
  var C_CARGA      = "#f59e0b";
  var C_GENERACION = "#198754";
  var C_LINEA_NORM = "#6b7280";
  var C_LINEA_ALTA = "#eab308";
  var C_LINEA_CRIT = "#dc2626";

  var W_ACOM = 220; var H_ACOM = 64;
  var W_SE   = 100; var H_SE   = 40;
  var R_TX   = 26;
  var W_CBT  = 200; var H_CBT  = 64;

  var NIVEL_H  = 100;
  var MIN_SEP  = 220;
  var PAD_X    = 60;
  var PAD_Y    = 30;

  // Mapeo punto_medicion → tipo genérico (para compatibilidad telemetría ↔ activos)
  var _TIPO_MAP = {
    acometida_cfe: "acometida",
    subestacion:   "subestacion",
    transformador: "transformador",
    carga_final:   "carga",
    generacion:    "generacion",
  };

  // ── Helpers de formato ─────────────────────────────────────────────────────
  function _fmt(n, dec) {
    if (n == null) return "\u2014";
    return Number(n).toLocaleString("es-MX", {
      maximumFractionDigits: dec, minimumFractionDigits: dec
    });
  }

  // ── SVG helpers ────────────────────────────────────────────────────────────
  function _el(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    if (attrs) {
      var keys = Object.keys(attrs);
      for (var i = 0; i < keys.length; i++) {
        e.setAttribute(keys[i], attrs[keys[i]]);
      }
    }
    return e;
  }

  function _text(txt, x, y, cls) {
    var t = _el("text", { x: x, y: y, "class": cls || "unifilar-label" });
    t.textContent = txt;
    return t;
  }

  function _multilineText(lines, cx, baseY, lineH, cls) {
    var g = _el("g");
    for (var i = 0; i < lines.length; i++) {
      if (lines[i] == null || lines[i] === "") continue;
      g.appendChild(_text(lines[i], cx, baseY + i * lineH, cls));
    }
    return g;
  }

  function _claseLinea(kwActivo, kwNominal) {
    if (!kwNominal || kwNominal <= 0) return "unifilar-linea-normal";
    var pct = kwActivo / kwNominal;
    if (pct >= 0.95) return "unifilar-linea-critica";
    if (pct >= 0.80) return "unifilar-linea-alta";
    return "unifilar-linea-normal";
  }

  // ── Resolución del tipo visual ─────────────────────────────────────────────
  function _tipoVisual(nodo) {
    // punto_medicion (telemetría) o tipo (activos)
    var pm = nodo.punto_medicion || nodo.tipo || "";
    return _TIPO_MAP[pm] || pm;
  }

  // ── Dibujo de nodos ───────────────────────────────────────────────────────

  function _dibujarAcometida(g, nodo, cx, cy, sel) {
    var x = cx - W_ACOM / 2;
    var y = cy - H_ACOM / 2;
    g.appendChild(_el("rect", {
      x: x, y: y, width: W_ACOM, height: H_ACOM, rx: 6,
      fill: "#eef2f7", stroke: C_PRIMARIO,
      "stroke-width": sel ? 4 : 2,
      "class": "unifilar-fondo",
    }));
    var kwh = nodo.energia_kwh != null ? _fmt(nodo.energia_kwh, 0) + " kWh" : "";
    g.appendChild(_multilineText(
      [nodo.nombre, kwh], cx, cy - 10, 16, "unifilar-label"
    ));
    return { x: cx, y: cy + H_ACOM / 2 };
  }

  function _dibujarSE(g, nodo, cx, cy, sel) {
    var x = cx - W_SE / 2;
    var y = cy - H_SE / 2;
    g.appendChild(_el("rect", {
      x: x, y: y, width: W_SE, height: H_SE, rx: 6,
      fill: "rgba(31,58,95,0.06)",
      stroke: sel ? C_PRIMARIO : C_PRIMARIO_L,
      "stroke-width": sel ? 3 : 1.5,
      "stroke-dasharray": "5,3",
      "class": "unifilar-fondo",
    }));
    var t1 = _el("text", {
      x: cx, y: cy - 5,
      "class": "unifilar-label", "text-anchor": "middle",
      "font-size": "12", "font-weight": "bold",
    });
    t1.textContent = nodo.nombre;
    g.appendChild(t1);
    if (nodo.energia_kwh != null) {
      var t2 = _el("text", {
        x: cx, y: cy + 9,
        "class": "unifilar-label-small", "text-anchor": "middle", "font-size": "10",
      });
      t2.textContent = _fmt(nodo.energia_kwh, 0) + " kWh";
      g.appendChild(t2);
    }
    return { x: cx, y: cy + H_SE / 2 };
  }

  function _dibujarTransformador(g, nodo, cx, cy, sel) {
    var cy1 = cy - 6;
    var cy2 = cy + 6;
    var sw = sel ? 3 : 1.5;
    g.appendChild(_el("circle", {
      cx: cx, cy: cy1, r: R_TX, fill: "white",
      stroke: C_PRIMARIO, "stroke-width": sw, "class": "unifilar-fondo",
    }));
    g.appendChild(_el("circle", {
      cx: cx, cy: cy2, r: R_TX, fill: "rgba(255,255,255,0.7)",
      stroke: C_PRIMARIO, "stroke-width": sw, "class": "unifilar-fondo",
    }));
    var nombreMatch = nodo.nombre.match(/^(T-\d+\.\d+)/);
    var kvaMatch    = nodo.nombre.match(/(\d+\s*kVA)/);
    var nombreCorto = nombreMatch ? nombreMatch[1] : nodo.nombre.substring(0, 12);
    var kvaCorto    = kvaMatch ? kvaMatch[1] : "";
    var kwh         = nodo.energia_kwh != null ? _fmt(nodo.energia_kwh, 0) + " kWh" : "";
    var lx = cx + R_TX + 44;
    var labels = [
      [nombreCorto, "12", "bold"],
      [kvaCorto,    "10", "normal"],
      [kwh,         "10", "bold"],
    ];
    for (var i = 0; i < labels.length; i++) {
      if (!labels[i][0]) continue;
      var t = _el("text", {
        x: lx, y: cy - 8 + i * 14,
        "class": "unifilar-label-small", "text-anchor": "start",
        "font-size": labels[i][1], "font-weight": labels[i][2],
      });
      t.textContent = labels[i][0];
      g.appendChild(t);
    }
    return { x: cx, y: cy2 + R_TX };
  }

  function _dibujarCBT(g, nodo, cx, cy, sel, esGeneracion) {
    var x = cx - W_CBT / 2;
    var y = cy - H_CBT / 2;
    var colorBorde  = esGeneracion ? C_GENERACION : C_CARGA;
    var colorFondo  = esGeneracion ? "rgba(25,135,84,0.08)" : "rgba(245,158,11,0.08)";
    var colorSelBorde = esGeneracion ? "#146c43" : "#b45309";
    g.appendChild(_el("rect", {
      x: x, y: y, width: W_CBT, height: H_CBT, rx: 6,
      fill: colorFondo,
      stroke: sel ? colorSelBorde : colorBorde,
      "stroke-width": sel ? 4 : 2,
      "class": "unifilar-fondo",
    }));
    var nom = nodo.potencia_nominal_kw != null
      ? _fmt(nodo.potencia_nominal_kw, 0) + " kW nom."
      : "";
    var kwh = nodo.energia_kwh != null ? _fmt(nodo.energia_kwh, 0) + " kWh" : "";
    g.appendChild(_multilineText(
      [nodo.nombre, nom, kwh], cx, cy - 12, 16, "unifilar-label-small"
    ));
    return { x: cx, y: cy + H_CBT / 2 };
  }

  function _dibujarLinea(svgEl, px, py, hx, hy, kwhHijo, kwNomHijo) {
    var miY = py + (hy - py) / 2;
    var d = "M " + px + " " + py + " L " + px + " " + miY + " L " + hx + " " + miY + " L " + hx + " " + hy;
    var cls = _claseLinea(kwhHijo, kwNomHijo);
    svgEl.appendChild(_el("path", { d: d, "class": cls }));
  }

  // ── Indicadores overlay ────────────────────────────────────────────────────
  function _addIndicadores(g, nodo, cx, cy, tipoV, opts) {
    if (!opts.indicadores) return;
    var ind = opts.indicadores;

    // Punto verde para activos con medidor
    if (ind.con_medidor && ind.con_medidor.has(nodo.id)) {
      g.appendChild(_el("circle", {
        cx: cx + (tipoV === "acometida" ? W_ACOM / 2 - 8 :
                  tipoV === "subestacion" ? W_SE / 2 - 6 :
                  tipoV === "transformador" ? R_TX + 30 :
                  W_CBT / 2 - 8),
        cy: cy - (tipoV === "acometida" ? H_ACOM / 2 - 8 :
                  tipoV === "subestacion" ? H_SE / 2 - 6 :
                  tipoV === "transformador" ? R_TX + 2 :
                  H_CBT / 2 - 8),
        r: 5,
        "class": "unifilar-indicador-medidor",
      }));
    }

    // Badge cabecera (solo telemetría / avanzado)
    if (ind.cabecera && ind.cabecera.has(nodo.id)) {
      var rol = ind.cabecera.get(nodo.id);
      var badgeX = cx + (tipoV === "acometida" ? W_ACOM / 2 + 4 :
                         tipoV === "transformador" ? R_TX + 36 :
                         W_CBT / 2 + 4);
      var badgeY = cy - 6;
      var bg = _el("rect", {
        x: badgeX, y: badgeY - 8, width: 12, height: 12, rx: 2,
        "class": "unifilar-indicador-cabecera-" + rol,
      });
      g.appendChild(bg);
    }

    // Warning para acometidas sin contrato
    if (ind.sin_contrato && ind.sin_contrato.has(nodo.id) && tipoV === "acometida") {
      var wx = cx - W_ACOM / 2 + 8;
      var wy = cy - H_ACOM / 2 + 12;
      var wt = _el("text", {
        x: wx, y: wy, "font-size": "14", "class": "unifilar-indicador-sin-contrato",
      });
      wt.textContent = "\u26A0";
      g.appendChild(wt);
    }
  }

  // ── Detección de ciclos ────────────────────────────────────────────────────
  function detectarCiclo(activo_id, nuevo_padre_id, todos) {
    var byId = {};
    for (var i = 0; i < todos.length; i++) {
      byId[todos[i].id] = todos[i];
    }
    var cursor_id = nuevo_padre_id;
    var visitado = {};
    while (cursor_id != null) {
      if (cursor_id === activo_id) return true;
      if (visitado[cursor_id]) break;
      visitado[cursor_id] = true;
      var nodo = byId[cursor_id];
      cursor_id = nodo ? nodo.activo_padre_id : null;
    }
    return false;
  }

  // ── Motor de layout y renderizado ──────────────────────────────────────────

  /**
   * renderUnifilar(raiz, svgEl, wrapEl, opts)
   *
   * opts: {
   *   nodoSeleccionadoId: int|null,
   *   onClickNodo: (id, tipo) => void,
   *   modoEdicion: bool,
   *   padresValidos: {tipo: [tipos...]},
   *   todosActivos: [{id, activo_padre_id, tipo}],
   *   indicadores: {
   *     con_medidor: Set<int>,
   *     cabecera: Map<int, str>,
   *     sin_contrato: Set<int>,
   *   },
   *   onDropSolicitud: (activo_id, nuevo_padre_id) => void,
   * }
   */
  function renderUnifilar(raiz, svgEl, wrapEl, opts) {
    opts = opts || {};
    if (!raiz || !svgEl) return;
    svgEl.innerHTML = "";

    var wrapW = wrapEl ? wrapEl.clientWidth - 48 : 900;

    // ── 1. Calcular profundidades ──────────────────────────────────────────
    var profMap = {};
    function _calcProf(nodo, prof) {
      profMap[nodo.id] = prof;
      var hijos = nodo.hijos || [];
      for (var i = 0; i < hijos.length; i++) _calcProf(hijos[i], prof + 1);
    }
    _calcProf(raiz, 0);
    var maxProf = 0;
    var profKeys = Object.keys(profMap);
    for (var i = 0; i < profKeys.length; i++) {
      if (profMap[profKeys[i]] > maxProf) maxProf = profMap[profKeys[i]];
    }

    // ── 2. Recolectar hojas ────────────────────────────────────────────────
    var hojas = [];
    function _recogerHojas(nodo) {
      if (!nodo.hijos || nodo.hijos.length === 0) hojas.push(nodo);
      else {
        for (var i = 0; i < nodo.hijos.length; i++) _recogerHojas(nodo.hijos[i]);
      }
    }
    _recogerHojas(raiz);
    var nHojas = Math.max(hojas.length, 1);
    var svgW = Math.max(wrapW, nHojas * MIN_SEP + PAD_X * 2);

    // ── 3. Asignar X ──────────────────────────────────────────────────────
    var xMap = {};
    var pasoHoja = svgW / (nHojas + 1);
    for (var i = 0; i < hojas.length; i++) {
      xMap[hojas[i].id] = pasoHoja * (i + 1);
    }
    function _asignarX(nodo) {
      if (!nodo.hijos || nodo.hijos.length === 0) return;
      for (var i = 0; i < nodo.hijos.length; i++) _asignarX(nodo.hijos[i]);
      var sum = 0, cnt = 0;
      for (var i = 0; i < nodo.hijos.length; i++) {
        var xh = xMap[nodo.hijos[i].id];
        if (xh != null) { sum += xh; cnt++; }
      }
      if (cnt > 0) xMap[nodo.id] = sum / cnt;
    }
    _asignarX(raiz);
    if (xMap[raiz.id] == null) xMap[raiz.id] = svgW / 2;

    // ── 4. Y según profundidad ─────────────────────────────────────────────
    function _hMedia(nodo) {
      var tv = _tipoVisual(nodo);
      switch (tv) {
        case "acometida":     return H_ACOM / 2;
        case "subestacion":   return H_SE / 2;
        case "transformador": return R_TX + 6;
        case "carga":         return H_CBT / 2;
        case "generacion":    return H_CBT / 2;
        default:              return H_SE / 2;
      }
    }
    function _cy(nodo) {
      return PAD_Y + profMap[nodo.id] * NIVEL_H + _hMedia(nodo);
    }

    var svgH = PAD_Y + (maxProf + 1) * NIVEL_H + PAD_Y;
    svgEl.setAttribute("width",   svgW);
    svgEl.setAttribute("height",  svgH);
    svgEl.setAttribute("viewBox", "0 0 " + svgW + " " + svgH);

    // ── Estado de drag ─────────────────────────────────────────────────────
    var _draggingId   = null;
    var _draggingTipo = null;
    var _ghostEl      = null;
    var _allGroups     = [];   // [{g, nodoId, tipoVisual}]

    // ── 5. Dibujo recursivo ────────────────────────────────────────────────
    function _dibujar(nodo, svgElParent) {
      var cx = xMap[nodo.id] != null ? xMap[nodo.id] : svgW / 2;
      var cy = _cy(nodo);
      var sel = opts.nodoSeleccionadoId === nodo.id;
      var tipoV = _tipoVisual(nodo);
      var outPt;

      var g = _crearGrupoNodo(nodo, tipoV);

      switch (tipoV) {
        case "acometida":
          outPt = _dibujarAcometida(g, nodo, cx, cy, sel);
          break;
        case "subestacion":
          outPt = _dibujarSE(g, nodo, cx, cy, sel);
          break;
        case "transformador":
          outPt = _dibujarTransformador(g, nodo, cx, cy, sel);
          break;
        case "generacion":
          outPt = _dibujarCBT(g, nodo, cx, cy, sel, true);
          break;
        case "carga":
          outPt = _dibujarCBT(g, nodo, cx, cy, sel, false);
          break;
        default:
          outPt = _dibujarSE(g, nodo, cx, cy, sel);
      }

      _addIndicadores(g, nodo, cx, cy, tipoV, opts);

      svgElParent.appendChild(g);
      _allGroups.push({ g: g, nodoId: nodo.id, tipoVisual: tipoV, cx: cx, cy: cy });

      var hijos = nodo.hijos || [];
      for (var j = 0; j < hijos.length; j++) {
        var hijo = hijos[j];
        var hx  = xMap[hijo.id] != null ? xMap[hijo.id] : svgW / 2;
        var hcy = _cy(hijo);
        var hTopY = hcy - _hMedia(hijo);
        _dibujarLinea(svgElParent, outPt.x, outPt.y, hx, hTopY,
          hijo.energia_kwh, hijo.potencia_nominal_kw);
        _dibujar(hijo, svgElParent);
      }
    }

    function _crearGrupoNodo(nodo, tipoV) {
      var g = _el("g", {
        "class": "unifilar-nodo",
        "data-nodo-id": String(nodo.id),
      });

      // Click handler
      if (opts.onClickNodo) {
        g.addEventListener("click", function (e) {
          // No disparar click si estamos en medio de un drag
          if (_draggingId != null) return;
          e.stopPropagation();
          opts.onClickNodo(nodo.id, tipoV);
        });
        g.style.cursor = "pointer";
      }

      // Hover
      g.addEventListener("mouseenter", function () {
        if (wrapEl) wrapEl.classList.add("hovering");
        g.classList.add("unifilar-highlight");
      });
      g.addEventListener("mouseleave", function () {
        if (wrapEl) wrapEl.classList.remove("hovering");
        g.classList.remove("unifilar-highlight");
      });

      // Drag (solo en modo edición y para tipos que no son acometida)
      if (opts.modoEdicion && tipoV !== "acometida") {
        g.setAttribute("draggable", "true");
        g.style.cursor = "grab";

        g.addEventListener("mousedown", function (e) {
          if (e.button !== 0) return;
          _draggingId   = nodo.id;
          _draggingTipo = tipoV;
          // Crear ghost
          _ghostEl = _el("circle", {
            cx: e.offsetX, cy: e.offsetY, r: 14,
            fill: "rgba(31,58,95,0.25)", stroke: C_PRIMARIO,
            "stroke-width": 2, "pointer-events": "none",
          });
          svgEl.appendChild(_ghostEl);
          _highlightDestinos(true);
        });
      }

      return g;
    }

    // ── Drag handlers globales en el SVG ────────────────────────────────────
    if (opts.modoEdicion) {
      svgEl.addEventListener("mousemove", function (e) {
        if (_draggingId == null || !_ghostEl) return;
        // Calcular coordenadas relativas al SVG
        var pt = svgEl.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        var svgPt = pt.matrixTransform(svgEl.getScreenCTM().inverse());
        _ghostEl.setAttribute("cx", svgPt.x);
        _ghostEl.setAttribute("cy", svgPt.y);
      });

      svgEl.addEventListener("mouseup", function (e) {
        if (_draggingId == null) return;
        var target = e.target;
        // Buscar el grupo nodo más cercano
        var gTarget = target.closest ? target.closest(".unifilar-nodo") : null;
        if (!gTarget) { _resetDrag(); return; }

        var destId = parseInt(gTarget.getAttribute("data-nodo-id"), 10);
        if (destId === _draggingId) { _resetDrag(); return; }

        // Buscar tipoVisual del destino
        var destInfo = null;
        for (var i = 0; i < _allGroups.length; i++) {
          if (_allGroups[i].nodoId === destId) { destInfo = _allGroups[i]; break; }
        }
        if (!destInfo) { _resetDrag(); return; }

        // Validar
        var validos = opts.padresValidos ? (opts.padresValidos[_draggingTipo] || []) : [];
        var esValido = validos.indexOf(destInfo.tipoVisual) !== -1;
        var creaCiclo = false;
        if (esValido && opts.todosActivos) {
          creaCiclo = detectarCiclo(_draggingId, destId, opts.todosActivos);
        }

        if (esValido && !creaCiclo && opts.onDropSolicitud) {
          opts.onDropSolicitud(_draggingId, destId);
        }

        _resetDrag();
      });

      // Si se sale del SVG, cancelar
      svgEl.addEventListener("mouseleave", function () {
        if (_draggingId != null) _resetDrag();
      });
    }

    function _highlightDestinos(activar) {
      if (!opts.padresValidos) return;
      var validos = opts.padresValidos[_draggingTipo] || [];
      for (var i = 0; i < _allGroups.length; i++) {
        var info = _allGroups[i];
        if (info.nodoId === _draggingId) continue;
        if (!activar) {
          info.g.classList.remove("unifilar-drop-valido", "unifilar-drop-invalido");
          continue;
        }
        var esDestValido = validos.indexOf(info.tipoVisual) !== -1;
        var creaCiclo = false;
        if (esDestValido && opts.todosActivos) {
          creaCiclo = detectarCiclo(_draggingId, info.nodoId, opts.todosActivos);
        }
        if (esDestValido && !creaCiclo) {
          info.g.classList.add("unifilar-drop-valido");
        } else {
          info.g.classList.add("unifilar-drop-invalido");
        }
      }
    }

    function _resetDrag() {
      _draggingId   = null;
      _draggingTipo = null;
      if (_ghostEl && _ghostEl.parentNode) {
        _ghostEl.parentNode.removeChild(_ghostEl);
      }
      _ghostEl = null;
      _highlightDestinos(false);
    }

    _dibujar(raiz, svgEl);
  }

  // ── Exportar ───────────────────────────────────────────────────────────────
  global.UnifilarCore = {
    renderUnifilar: renderUnifilar,
    detectarCiclo: detectarCiclo,
  };

})(window);
