window.ActivosUnifilar = (function () {
  "use strict";

  // ── Module state ─────────────────────────────────────────────────────────
  var _cfg = {};
  var _topologia = null;
  var _lastRaiz = null;
  var _seleccionadoId = null;
  var CLIENTE_ID, PLANTA_ID, ES_ADMIN;
  var TODOS_ACTIVOS = [];
  var PADRES_VALIDOS = {};

  // ── Public: init ─────────────────────────────────────────────────────────
  function init(cfg) {
    _cfg = cfg || {};
    CLIENTE_ID   = _cfg.clienteId;
    PLANTA_ID    = _cfg.plantaId;
    ES_ADMIN     = !!_cfg.esAdmin;
    TODOS_ACTIVOS  = _cfg.todosActivos  || [];
    PADRES_VALIDOS = _cfg.padresValidos || {};

    // Attach modal refresh handlers
    ["modalCambioAlimentacion", "modalCrearActivo", "modalEditarActivo",
     "modalVincularMedidor"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("hidden.bs.modal", _recargar);
    });

    // Fetch topologia for indicators (async, re-renders if lastRaiz available)
    if (_cfg.topologiaUrl) _fetchTopologia();
  }

  // ── Public: renderUnifilar ────────────────────────────────────────────────
  function renderUnifilar(raiz, nodoId) {
    _lastRaiz = raiz;
    _seleccionadoId = nodoId != null ? parseInt(nodoId, 10) : null;

    var svgEl     = document.getElementById(_cfg.svgId || "activos-unifilar-svg");
    var wrapperEl = document.getElementById(_cfg.wrapperId || "activos-unifilar-wrapper");
    if (!svgEl || !wrapperEl) return;

    if (_cfg.loadingId) {
      var ldg = document.getElementById(_cfg.loadingId);
      if (ldg) ldg.style.display = "none";
    }
    svgEl.style.display = "";

    if (!raiz) {
      svgEl.innerHTML = '<text x="20" y="40" font-size="14" fill="#6b7280">Sin activos registrados.</text>';
      return;
    }

    var ind = (_topologia && _topologia.indicadores) || {};
    UnifilarCore.renderUnifilar(raiz, svgEl, wrapperEl, {
      nodoSeleccionadoId: _seleccionadoId,
      onClickNodo:        _onClickNodo,
      modoEdicion:        ES_ADMIN,
      padresValidos:      (_topologia && _topologia.padres_validos) || PADRES_VALIDOS,
      todosActivos:       (_topologia && _topologia.todos_activos)  || [],
      indicadores: {
        con_medidor:  new Set(ind.con_medidor || []),
        cabecera:     new Map(Object.entries(ind.cabecera || {})),
        sin_contrato: new Set(ind.sin_contrato || []),
      },
      onDropSolicitud: _onDropSolicitud,
    });
  }

  // ── Internals ─────────────────────────────────────────────────────────────

  function baseUrl(activoId) {
    var base = "/clientes/" + CLIENTE_ID + "/planta/" + PLANTA_ID + "/activos";
    return activoId ? base + "/" + activoId : base;
  }

  function mostrarToast(msg, tipo) {
    tipo = tipo || "success";
    var toastId = _cfg.toastId || "toast-activos";
    var t = document.getElementById(toastId);
    if (!t) return;
    t.className = "toast align-items-center text-bg-" + tipo + " border-0";
    var msgEl = t.querySelector(".toast-body") || document.getElementById("toast-activos-msg");
    if (msgEl) msgEl.textContent = msg;
    bootstrap.Toast.getOrCreateInstance(t, { delay: 3500 }).show();
  }

  function mostrarError(elId, msg) {
    var el = document.getElementById(elId);
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("d-none");
  }

  function limpiarError(elId) {
    var el = document.getElementById(elId);
    if (!el) return;
    el.textContent = "";
    el.classList.add("d-none");
  }

  function post(url, body) {
    var csrf = document.querySelector('meta[name="csrf-token"]');
    var csrfToken = csrf ? csrf.content : "";
    return fetch(url, {
      method:  "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body:    JSON.stringify(body),
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
        return data;
      });
    });
  }

  function llenarPadresSelect(selectEl, tipoHijo, excluirId, padreActualId) {
    var tiposValidos = PADRES_VALIDOS[tipoHijo] || [];
    selectEl.innerHTML = '<option value="">-- sin padre (raiz) --</option>';
    var filtrado = TODOS_ACTIVOS
      .filter(function (a) {
        return tiposValidos.indexOf(a.tipo) !== -1 && a.activo && a.id !== excluirId;
      })
      .sort(function (a, b) {
        if (a.misma_planta !== b.misma_planta) return b.misma_planta - a.misma_planta;
        return a.nombre.localeCompare(b.nombre);
      });
    filtrado.forEach(function (a) {
      var opt = document.createElement("option");
      opt.value = a.id;
      var plantaLabel = a.misma_planta ? "" : " -- " + a.planta_nombre;
      opt.textContent = a.nombre + " (" + a.tipo + ")" + plantaLabel;
      if (a.id === padreActualId) opt.selected = true;
      selectEl.appendChild(opt);
    });
  }

  function _fetchTopologia() {
    fetch(_cfg.topologiaUrl)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _topologia = data;
        if (_lastRaiz) renderUnifilar(_lastRaiz, _seleccionadoId);
      })
      .catch(function () {});
  }

  function _recargar() {
    if (_cfg.topologiaUrl) _fetchTopologia();
    if (_cfg.onRecargar) _cfg.onRecargar();
  }

  function _onClickNodo(id) {
    _seleccionadoId = parseInt(id, 10);
    if (ES_ADMIN) {
      if (_lastRaiz) renderUnifilar(_lastRaiz, _seleccionadoId);
      _abrirModal(_seleccionadoId);
    } else {
      if (_cfg.onNodoSeleccionado) _cfg.onNodoSeleccionado(_seleccionadoId);
    }
  }

  function _onDropSolicitud(activo_id, nuevo_padre_id) {
    var nombre = null;
    for (var i = 0; i < TODOS_ACTIVOS.length; i++) {
      if (TODOS_ACTIVOS[i].id === activo_id) { nombre = TODOS_ACTIVOS[i].nombre; break; }
    }
    if (!nombre && _topologia) {
      for (var j = 0; j < (_topologia.todos_activos || []).length; j++) {
        if (_topologia.todos_activos[j].id === activo_id) {
          nombre = _topologia.todos_activos[j].nombre || String(activo_id);
          break;
        }
      }
    }
    window.abrirCambioAlimentacion(activo_id, nombre || String(activo_id), nuevo_padre_id);
  }

  // ── Modal de detalle ──────────────────────────────────────────────────────

  function _findNodo(raiz, id) {
    if (!raiz) return null;
    if (raiz.id === id) return raiz;
    for (var i = 0; i < (raiz.hijos || []).length; i++) {
      var found = _findNodo(raiz.hijos[i], id);
      if (found) return found;
    }
    return null;
  }

  function _abrirModal(activo_id) {
    var modal = document.getElementById("modalActivoDetalle");
    if (!modal) return;
    var bodyEl   = document.getElementById("modal-activo-body");
    var tituloEl = document.getElementById("modal-activo-titulo");
    if (bodyEl)   bodyEl.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div>';
    if (tituloEl) tituloEl.textContent = "Cargando...";
    bootstrap.Modal.getOrCreateInstance(modal).show();
    var nodoCache = _findNodo(_lastRaiz, activo_id);
    fetch(baseUrl(activo_id) + "/detalle")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (tituloEl) tituloEl.textContent = (d.activo && d.activo.nombre) || "";
        if (bodyEl)   bodyEl.innerHTML = _renderModalContent(d, nodoCache);
      })
      .catch(function (e) {
        if (bodyEl) bodyEl.innerHTML = '<div class="alert alert-danger small">Error: ' + _esc(e.message) + '</div>';
      });
  }

  function _esc(str) {
    if (!str) return "";
    var d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function _renderModalContent(d, nodoCache) {
    var a = d.activo || {};
    var badgeCol = {
      acometida: "#1F3A5F", subestacion: "#2E5C8A", transformador: "#5B8FB9",
      carga: "#A4C8E1", generacion: "#198754",
    };
    var bc = badgeCol[a.tipo] || "#6c757d";
    var textCol = a.tipo === "carga" ? "#1F3A5F" : "#fff";

    // BLOQUE 1: Identidad y campos
    var html = '<div class="mb-2">' +
      '<span class="badge rounded-pill" style="background:' + bc + ';color:' + textCol + ';font-size:.65rem">' + _esc(a.tipo || "") + "</span>" +
      (a.activo ? "" : '<span class="badge bg-secondary ms-1" style="font-size:.65rem">inactivo</span>') +
      "</div>";
    html += '<div class="small mb-3">';
    if (a.capacidad_kva)      html += "<div class='text-muted'>Capacidad: <strong>" + a.capacidad_kva + " kVA</strong></div>";
    if (a.potencia_nominal_kw) html += "<div class='text-muted'>Pot. nominal: <strong>" + a.potencia_nominal_kw + " kW</strong></div>";
    if (a.tipo_carga)          html += "<div class='text-muted'>Tipo carga: <strong>" + _esc(a.tipo_carga) + "</strong></div>";
    if (a.notas)               html += "<div class='text-muted'>Notas: " + _esc(a.notas) + "</div>";
    html += "</div>";

    // Botones (admin, activo)
    if (d.es_admin && a.activo) {
      html += '<div class="d-flex flex-wrap gap-1 mb-3">';
      html += '<button class="btn btn-outline-secondary btn-sm" onclick="abrirEditarActivo(' +
        a.id + "," + JSON.stringify(a).replace(/</g, "\\u003c") +
        ')" style="font-size:.7rem"><i class="bi bi-pencil me-1"></i>Editar</button>';
      if (a.tipo !== "acometida") {
        html += '<button class="btn btn-outline-primary btn-sm" onclick="abrirCambioAlimentacion(' +
          a.id + ",'" + _esc(a.nombre || "").replace(/'/g, "\\'") + "'," +
          (a.activo_padre_id || "null") +
          ')" style="font-size:.7rem"><i class="bi bi-arrow-left-right me-1"></i>Cambio alim.</button>';
      }
      if (d.elegible_borrar) {
        html += '<button class="btn btn-danger btn-sm" onclick="confirmarEliminarPermanente(' +
          a.id + ",'" + _esc(a.nombre || "").replace(/'/g, "\\'") +
          '\')" style="font-size:.7rem"><i class="bi bi-trash3 me-1"></i>Eliminar</button>';
      } else {
        html += '<button class="btn btn-outline-danger btn-sm" onclick="confirmarDesactivar(' +
          a.id + ",'" + _esc(a.nombre || "").replace(/'/g, "\\'") +
          '\')" style="font-size:.7rem"><i class="bi bi-slash-circle me-1"></i>Desactivar</button>';
      }
      html += "</div>";
    }

    // BLOQUE 2: Cadena de alimentacion temporal
    var cadena = (nodoCache && nodoCache.cadena_tramos) || [];
    if (cadena.length > 0) {
      html += '<div class="mb-3"><div class="fw-semibold small mb-1">Cadena de alimentacion (periodo)</div>';
      if (cadena.length === 1) {
        html += '<div class="small text-muted">' + _esc((cadena[0].camino_nombres || []).join(" → ")) + "</div>";
      } else {
        html += '<table class="panel-historial-table w-100"><thead><tr>' +
          '<th style="font-size:.65rem;color:#6c757d;padding:.1rem .3rem;border-bottom:1px solid #dee2e6">Fuentes (padre → acometida)</th>' +
          '<th style="font-size:.65rem;color:#6c757d;padding:.1rem .3rem;border-bottom:1px solid #dee2e6">Desde</th>' +
          '<th style="font-size:.65rem;color:#6c757d;padding:.1rem .3rem;border-bottom:1px solid #dee2e6">Hasta</th>' +
          "</tr></thead><tbody>";
        cadena.forEach(function (t) {
          var nombres = _esc((t.camino_nombres || []).join(" → "));
          var desde = t.desde ? t.desde.substring(0, 10) : "--";
          var hasta = t.hasta ? t.hasta.substring(0, 10) : "--";
          html += "<tr><td style='font-size:.7rem;padding:.1rem .3rem;border-bottom:1px solid #f0f0f0'>" + nombres +
            "</td><td style='font-size:.7rem;padding:.1rem .3rem;border-bottom:1px solid #f0f0f0'>" + desde +
            "</td><td style='font-size:.7rem;padding:.1rem .3rem;border-bottom:1px solid #f0f0f0'>" + hasta + "</td></tr>";
        });
        html += "</tbody></table>";
      }
      html += "</div>";
    }

    // BLOQUE 3: Historiales
    if (d.historial_alimentacion && d.historial_alimentacion.length) {
      html += _renderHistorialTable("Historial de alimentacion", d.historial_alimentacion, [
        { key: "fuente", label: "Fuente", render: function (v) { return v && v.nombre ? _esc(v.nombre) + " (" + _esc(v.tipo) + ")" : "--"; } },
        { key: "vigente_desde", label: "Desde" },
        { key: "vigente_hasta", label: "Hasta" },
        { key: "motivo", label: "Motivo" },
      ]);
    }
    if (d.historial_medidor && d.historial_medidor.length) {
      html += _renderHistorialTable("Historial de medidor", d.historial_medidor, [
        { key: "medidor_id", label: "Medidor ID" },
        { key: "vigente_desde", label: "Desde" },
        { key: "vigente_hasta", label: "Hasta" },
        { key: "motivo", label: "Motivo" },
      ]);
    }
    if (d.historial_contrato && d.historial_contrato.length) {
      html += _renderHistorialTable("Historial de contrato", d.historial_contrato, [
        { key: "contrato", label: "Contrato", render: function (v) { return v && v.nombre ? _esc(v.nombre) : "--"; } },
        { key: "vigente_desde", label: "Desde" },
        { key: "vigente_hasta", label: "Hasta" },
        { key: "motivo", label: "Motivo" },
      ]);
    }
    if (d.historial_rol && d.historial_rol.length) {
      html += _renderHistorialTable("Historial de rol", d.historial_rol, [
        { key: "rol", label: "Rol" },
        { key: "vigente_desde", label: "Desde" },
        { key: "vigente_hasta", label: "Hasta" },
      ]);
    }

    // BLOQUE 4: Energia y coste del periodo
    if (nodoCache) {
      html += '<div class="mt-3 pt-2 border-top"><div class="fw-semibold small mb-1">Energia en el periodo</div><div class="small">';
      if (nodoCache.energia_kwh != null) {
        html += "<div>Energia: <strong>" +
          Number(nodoCache.energia_kwh).toLocaleString("es-MX", { maximumFractionDigits: 1 }) +
          " kWh</strong></div>";
      }
      if (nodoCache.costo_mxn != null) {
        html += "<div>Costo est.: <strong>$" +
          Number(nodoCache.costo_mxn).toLocaleString("es-MX", { maximumFractionDigits: 0 }) +
          " MXN</strong></div>";
      }
      if (nodoCache.energia_sin_costo_kwh > 0) {
        html += "<div class='text-muted'>Sin coste atribuido: " +
          Number(nodoCache.energia_sin_costo_kwh).toLocaleString("es-MX", { maximumFractionDigits: 1 }) +
          " kWh</div>";
      }
      html += "</div></div>";
    }

    return html;
  }

  function _renderHistorialTable(titulo, filas, cols) {
    var t = '<div class="mb-3"><div class="fw-semibold small mb-1">' + titulo + "</div>" +
      '<table class="panel-historial-table w-100"><thead><tr>';
    cols.forEach(function (c) {
      t += '<th style="font-size:.65rem;color:#6c757d;padding:.1rem .3rem;border-bottom:1px solid #dee2e6">' + c.label + "</th>";
    });
    t += "</tr></thead><tbody>";
    filas.forEach(function (f) {
      var vigente = !f.vigente_hasta;
      t += "<tr" + (vigente ? ' style="font-weight:600;color:#0d6efd"' : "") + ">";
      cols.forEach(function (c) {
        var v;
        if (c.render) {
          v = c.render(f[c.key]);
        } else {
          v = f[c.key] || "--";
          if ((c.key === "vigente_desde" || c.key === "vigente_hasta") && f[c.key]) {
            v = f[c.key].substring(0, 10);
          }
        }
        t += '<td style="font-size:.7rem;padding:.1rem .3rem;border-bottom:1px solid #f0f0f0">' + v + "</td>";
      });
      t += "</tr>";
    });
    t += "</tbody></table></div>";
    return t;
  }

  // ── Crear activo ──────────────────────────────────────────────────────────

  window.actualizarPadresCrear = function () {
    var tipo = document.getElementById("crear-tipo").value;
    var grupo = document.getElementById("crear-padre-grupo");
    var sel = document.getElementById("crear-padre");
    if (!grupo || !sel) return;
    var tiposValidos = PADRES_VALIDOS[tipo] || [];
    if (tiposValidos.length === 0) { grupo.style.display = "none"; sel.value = ""; return; }
    grupo.style.display = "";
    llenarPadresSelect(sel, tipo, null, null);
  };

  window.guardarCrearActivo = function () {
    limpiarError("crear-error");
    var tipo   = document.getElementById("crear-tipo").value;
    var nombre = (document.getElementById("crear-nombre").value || "").trim();
    var padre  = document.getElementById("crear-padre").value || null;
    var kva    = parseFloat(document.getElementById("crear-kva").value) || null;
    var kw     = parseFloat(document.getElementById("crear-kw").value) || null;
    var tc     = (document.getElementById("crear-tipo-carga").value || "").trim() || null;
    var notas  = (document.getElementById("crear-notas").value || "").trim() || null;
    post(baseUrl() + "/crear", {
      tipo: tipo, nombre: nombre,
      activo_padre_id: padre ? parseInt(padre) : null,
      capacidad_kva: kva, potencia_nominal_kw: kw, tipo_carga: tc, notas: notas,
    }).then(function () {
      mostrarToast("Activo creado");
      bootstrap.Modal.getInstance(document.getElementById("modalCrearActivo"))?.hide();
    }).catch(function (e) { mostrarError("crear-error", e.message); });
  };

  // ── Editar activo ──────────────────────────────────────────────────────────

  window.abrirEditarActivo = function (id, nodo) {
    document.getElementById("editar-activo-id").value  = id;
    document.getElementById("editar-nombre").value     = nodo.nombre || "";
    document.getElementById("editar-kva").value        = nodo.capacidad_kva || "";
    document.getElementById("editar-kw").value         = nodo.potencia_nominal_kw || "";
    document.getElementById("editar-tipo-carga").value = nodo.tipo_carga || "";
    document.getElementById("editar-notas").value      = nodo.notas || "";
    limpiarError("editar-error");
    bootstrap.Modal.getOrCreateInstance(document.getElementById("modalEditarActivo")).show();
  };

  window.guardarEditarActivo = function () {
    limpiarError("editar-error");
    var id    = parseInt(document.getElementById("editar-activo-id").value);
    var nombre = (document.getElementById("editar-nombre").value || "").trim();
    var kva   = parseFloat(document.getElementById("editar-kva").value) || null;
    var kw    = parseFloat(document.getElementById("editar-kw").value) || null;
    var tc    = (document.getElementById("editar-tipo-carga").value || "").trim() || null;
    var notas = (document.getElementById("editar-notas").value || "").trim() || null;
    post(baseUrl(id) + "/editar", { nombre: nombre, capacidad_kva: kva, potencia_nominal_kw: kw, tipo_carga: tc, notas: notas })
      .then(function () {
        mostrarToast("Activo actualizado");
        bootstrap.Modal.getInstance(document.getElementById("modalEditarActivo"))?.hide();
      }).catch(function (e) { mostrarError("editar-error", e.message); });
  };

  // ── Cambio de alimentacion ─────────────────────────────────────────────────

  window.abrirCambioAlimentacion = function (activoId, nombre, fuenteActualId) {
    document.getElementById("cambio-activo-id").value = activoId;
    document.getElementById("cambio-activo-nombre").textContent = nombre;
    limpiarError("cambio-error");
    var activo = TODOS_ACTIVOS.find(function (a) { return a.id === activoId; });
    var tipoActivo = activo ? activo.tipo : "";
    var sel = document.getElementById("cambio-fuente-select");
    if (sel) llenarPadresSelect(sel, tipoActivo, activoId, fuenteActualId);
    var desdeEl = document.getElementById("cambio-desde");
    if (desdeEl) desdeEl.value = "";
    var motivoEl = document.getElementById("cambio-motivo");
    if (motivoEl) motivoEl.value = "";
    bootstrap.Modal.getOrCreateInstance(document.getElementById("modalCambioAlimentacion")).show();
  };

  window.guardarCambioAlimentacion = function () {
    limpiarError("cambio-error");
    var activoId  = parseInt(document.getElementById("cambio-activo-id").value);
    var fuenteVal = document.getElementById("cambio-fuente-select").value;
    var desdeVal  = document.getElementById("cambio-desde").value;
    var motivo    = (document.getElementById("cambio-motivo").value || "").trim() || null;
    if (!fuenteVal) { mostrarError("cambio-error", "Selecciona una fuente de alimentacion."); return; }
    if (!desdeVal)  { mostrarError("cambio-error", "La fecha de inicio es obligatoria."); return; }
    var desde = new Date(desdeVal).toISOString();
    post(baseUrl(activoId) + "/cambio-alimentacion", {
      fuente_activo_id: parseInt(fuenteVal), desde: desde, motivo: motivo,
    }).then(function () {
      mostrarToast("Cambio de alimentacion declarado");
      bootstrap.Modal.getInstance(document.getElementById("modalCambioAlimentacion"))?.hide();
    }).catch(function (e) { mostrarError("cambio-error", e.message); });
  };

  // ── Desactivar / eliminar ──────────────────────────────────────────────────

  window.confirmarDesactivar = function (id, nombre) {
    if (!confirm('Desactivar "' + nombre + '"? Esta operacion es reversible desde base de datos.')) return;
    post(baseUrl(id) + "/desactivar", {})
      .then(function () { mostrarToast("Activo desactivado"); _recargar(); })
      .catch(function (e) { alert("Error: " + e.message); });
  };

  window.confirmarEliminarPermanente = function (id, nombre) {
    if (!confirm('Eliminar permanentemente "' + nombre + '"?\n\nEsta operacion borra el activo y su registro de alta.\nNo se puede deshacer.')) return;
    post(baseUrl(id) + "/eliminar-permanente", {})
      .then(function () { mostrarToast("Activo eliminado"); _recargar(); })
      .catch(function (e) { alert("No se puede eliminar:\n" + e.message); });
  };

  // ── Vincular medidor ───────────────────────────────────────────────────────

  window.abrirVincularMedidor = function (id, nombre) {
    document.getElementById("vincular-activo-id").value = id;
    document.getElementById("vincular-activo-nombre").textContent = nombre;
    limpiarError("vincular-error");
    bootstrap.Modal.getOrCreateInstance(document.getElementById("modalVincularMedidor")).show();
  };

  window.guardarVincularMedidor = function () {
    limpiarError("vincular-error");
    var id        = parseInt(document.getElementById("vincular-activo-id").value);
    var medidorId = parseInt(document.getElementById("vincular-medidor-select").value);
    post(baseUrl(id) + "/vincular-medidor", { medidor_id: medidorId })
      .then(function () {
        mostrarToast("Medidor vinculado");
        bootstrap.Modal.getInstance(document.getElementById("modalVincularMedidor"))?.hide();
      }).catch(function (e) { mostrarError("vincular-error", e.message); });
  };

  window.desvinculaActivo = function (id) {
    if (!confirm("Desvincular el medidor de este activo? La vigencia quedara cerrada en el historial.")) return;
    post(baseUrl(id) + "/desvincular-medidor", {})
      .then(function () { mostrarToast("Medidor desvinculado"); _recargar(); })
      .catch(function (e) { alert("Error: " + e.message); });
  };

  window.asignarContratoAcometida = function (id) {
    var contratoId = (document.getElementById("contrato-sel-" + id) || {}).value || null;
    var desdeVal   = (document.getElementById("contrato-desde-" + id) || {}).value;
    var motivo     = ((document.getElementById("contrato-motivo-" + id) || {}).value || "").trim() || null;
    if (!desdeVal) { alert("La fecha de inicio es obligatoria."); return; }
    var desde = new Date(desdeVal).toISOString();
    post(baseUrl(id) + "/contrato-acometida", {
      contrato_id: contratoId ? parseInt(contratoId) : null, desde: desde, motivo: motivo,
    }).then(function () { mostrarToast("Contrato asignado"); _recargar(); })
      .catch(function (e) { alert("Error: " + e.message); });
  };

  window.declararRolMedidor = function (activoId, medidorId) {
    var rol      = ((document.getElementById("rol-sel-" + activoId) || {}).value);
    var desdeVal = ((document.getElementById("rol-desde-" + activoId) || {}).value);
    var motivo   = ((document.getElementById("rol-motivo-" + activoId) || {}).value || "").trim() || null;
    if (!desdeVal) { alert("La fecha de inicio es obligatoria."); return; }
    var desde = new Date(desdeVal).toISOString();
    post(baseUrl(activoId) + "/medidor-rol", {
      medidor_id: medidorId, rol: rol, desde: desde, motivo: motivo,
    }).then(function () { mostrarToast("Rol declarado"); _recargar(); })
      .catch(function (e) { alert("Error: " + e.message); });
  };

  // ── Public API ─────────────────────────────────────────────────────────────
  return { init: init, renderUnifilar: renderUnifilar };
})();
