(function () {
  "use strict";

  // ── Configuración inyectada por la plantilla ──────────────────────────────
  var cfg           = window.ACTIVOS_UNIFILAR_CONFIG || {};
  var CLIENTE_ID    = cfg.clienteId;
  var PLANTA_ID     = cfg.plantaId;
  var TODOS_ACTIVOS = cfg.todosActivos  || [];
  var PADRES_VALIDOS = cfg.padresValidos || {};
  var CSRF          = document.querySelector('meta[name="csrf-token"]')?.content || "";

  if (!CLIENTE_ID || !PLANTA_ID) return;   // plantilla no inyectó config → salir

  // ── Helpers ───────────────────────────────────────────────────────────────

  function baseUrl(activoId) {
    var base = "/clientes/" + CLIENTE_ID + "/planta/" + PLANTA_ID + "/activos";
    return activoId ? base + "/" + activoId : base;
  }

  function mostrarToast(msg, tipo) {
    tipo = tipo || "success";
    var t = document.getElementById("toast-activos");
    t.className = "toast align-items-center text-bg-" + tipo + " border-0";
    document.getElementById("toast-activos-msg").textContent = msg;
    bootstrap.Toast.getOrCreateInstance(t, { delay: 3500 }).show();
  }

  function mostrarError(elId, msg) {
    var el = document.getElementById(elId);
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
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
        return data;
      });
    });
  }

  // ── Selector de padres (reutilizado en Crear y Editar) ───────────────────

  function llenarPadresSelect(selectEl, tipoHijo, excluirId, padreActualId) {
    var tiposValidos = PADRES_VALIDOS[tipoHijo] || [];
    selectEl.innerHTML = '<option value="">-- sin padre (raiz) --</option>';
    var filtrado = TODOS_ACTIVOS
      .filter(function (a) { return tiposValidos.indexOf(a.tipo) !== -1 && a.activo && a.id !== excluirId; })
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

  // ── Unifilar interactivo ─────────────────────────────────────────────────

  var ES_ADMIN = document.getElementById("activos-unifilar-wrapper").dataset.esAdmin === "true";
  var _topologia = null;
  var _raiz = null;
  var _seleccionadoId = null;

  function cargarTopologia() {
    document.getElementById("activos-unifilar-cargando").style.display = "";
    document.getElementById("activos-unifilar-svg").style.display = "none";
    fetch(baseUrl() + "/topologia")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        _topologia = data;
        _raiz = data.raiz;
        _renderUnifilar();
      })
      .catch(function () {
        document.getElementById("activos-unifilar-cargando").textContent = "Error cargando activos.";
      });
  }

  function _renderUnifilar() {
    var svg = document.getElementById("activos-unifilar-svg");
    var wrapper = document.getElementById("activos-unifilar-wrapper");
    document.getElementById("activos-unifilar-cargando").style.display = "none";
    svg.style.display = "";
    if (!_raiz) {
      svg.innerHTML = '<text x="20" y="40" font-size="14" fill="#6b7280">Esta planta no tiene activos electricos.</text>';
      return;
    }
    var ind = _topologia.indicadores || {};
    UnifilarCore.renderUnifilar(_raiz, svg, wrapper, {
      nodoSeleccionadoId: _seleccionadoId,
      onClickNodo: _onClickNodo,
      modoEdicion: ES_ADMIN,
      padresValidos: _topologia.padres_validos,
      todosActivos: _topologia.todos_activos,
      indicadores: {
        con_medidor: new Set(ind.con_medidor || []),
        cabecera: new Map(Object.entries(ind.cabecera || {})),
        sin_contrato: new Set(ind.sin_contrato || []),
      },
      onDropSolicitud: _onDropSolicitud,
    });
  }

  function _onClickNodo(id) {
    _seleccionadoId = parseInt(id, 10);
    _renderUnifilar();
    _abrirPanel(id);
  }

  function _abrirPanel(activo_id) {
    var panel = document.getElementById("activos-detail-panel");
    var body  = document.getElementById("panel-activo-body");
    var nombre = document.getElementById("panel-activo-nombre");
    panel.style.display = "";
    nombre.textContent = "Cargando...";
    body.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div>';

    fetch(baseUrl(activo_id) + "/detalle")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        nombre.textContent = d.activo.nombre;
        body.innerHTML = _renderPanel(d);
      })
      .catch(function (e) {
        body.innerHTML = '<div class="alert alert-danger small">Error: ' + e.message + '</div>';
      });
  }

  function _esc(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function _renderPanel(d) {
    var a = d.activo;
    var badgeCol = {
      acometida: '#1F3A5F', subestacion: '#2E5C8A', transformador: '#5B8FB9',
      carga: '#A4C8E1', generacion: '#198754',
    };
    var bc = badgeCol[a.tipo] || '#6c757d';
    var textCol = (a.tipo === 'carga') ? '#1F3A5F' : '#fff';

    var html = '<div class="mb-2">' +
      '<span class="badge rounded-pill" style="background:' + bc + ';color:' + textCol + ';font-size:.6rem">' + a.tipo + '</span>' +
      (a.activo ? '' : '<span class="badge bg-secondary ms-1" style="font-size:.6rem">inactivo</span>') +
      '</div><div class="small mb-3">';
    if (a.capacidad_kva) html += '<div class="text-muted">Capacidad: <strong>' + a.capacidad_kva + ' kVA</strong></div>';
    if (a.potencia_nominal_kw) html += '<div class="text-muted">Pot. nominal: <strong>' + a.potencia_nominal_kw + ' kW</strong></div>';
    if (a.tipo_carga) html += '<div class="text-muted">Tipo carga: <strong>' + a.tipo_carga + '</strong></div>';
    if (a.notas) html += '<div class="text-muted">Notas: ' + _esc(a.notas) + '</div>';
    html += '</div>';

    // Botones de accion
    if (d.es_admin && a.activo) {
      html += '<div class="d-flex flex-wrap gap-1 mb-3">';
      html += '<button class="btn btn-outline-secondary btn-sm" onclick="abrirEditarActivo(' + a.id + ', ' + JSON.stringify(a).replace(/</g, '\\u003c') + ')" style="font-size:.7rem">' +
        '<i class="bi bi-pencil me-1"></i>Editar</button>';
      if (a.tipo !== 'acometida') {
        html += '<button class="btn btn-outline-primary btn-sm" onclick="abrirCambioAlimentacion(' + a.id + ', \'' + _esc(a.nombre).replace(/'/g, "\\'") + '\', ' + (a.activo_padre_id || 'null') + ')" style="font-size:.7rem">' +
          '<i class="bi bi-arrow-left-right me-1"></i>Cambio alim.</button>';
      }
      if (d.elegible_borrar) {
        html += '<button class="btn btn-danger btn-sm" onclick="confirmarEliminarPermanente(' + a.id + ', \'' + _esc(a.nombre).replace(/'/g, "\\'") + '\')" style="font-size:.7rem">' +
          '<i class="bi bi-trash3 me-1"></i>Eliminar</button>';
      } else {
        html += '<button class="btn btn-outline-danger btn-sm" onclick="confirmarDesactivar(' + a.id + ', \'' + _esc(a.nombre).replace(/'/g, "\\'") + '\')" style="font-size:.7rem">' +
          '<i class="bi bi-slash-circle me-1"></i>Desactivar</button>';
      }
      html += '</div>';
    }

    // Historiales
    if (d.historial_alimentacion && d.historial_alimentacion.length > 0) {
      html += _renderHistorialTable("Historial de alimentacion", d.historial_alimentacion, [
        {key:'fuente', label:'Fuente', render: function(v) { return v && v.nombre ? v.nombre + ' (' + v.tipo + ')' : '--'; }},
        {key:'vigente_desde', label:'Desde'}, {key:'vigente_hasta', label:'Hasta'}, {key:'motivo', label:'Motivo'}
      ]);
    }
    if (d.historial_medidor && d.historial_medidor.length > 0) {
      html += _renderHistorialTable("Historial de medidor", d.historial_medidor, [
        {key:'medidor_id', label:'Medidor ID'},
        {key:'vigente_desde', label:'Desde'}, {key:'vigente_hasta', label:'Hasta'}, {key:'motivo', label:'Motivo'}
      ]);
    }
    if (d.historial_contrato && d.historial_contrato.length > 0) {
      html += _renderHistorialTable("Historial de contrato", d.historial_contrato, [
        {key:'contrato', label:'Contrato', render: function(v) { return v && v.nombre ? v.nombre : '--'; }},
        {key:'vigente_desde', label:'Desde'}, {key:'vigente_hasta', label:'Hasta'}, {key:'motivo', label:'Motivo'}
      ]);
    }
    if (d.historial_rol && d.historial_rol.length > 0) {
      html += _renderHistorialTable("Historial de rol", d.historial_rol, [
        {key:'rol', label:'Rol'}, {key:'vigente_desde', label:'Desde'}, {key:'vigente_hasta', label:'Hasta'}
      ]);
    }

    return html;
  }

  function _renderHistorialTable(titulo, filas, cols) {
    var t = '<div class="mb-3"><div class="fw-semibold small mb-1">' + titulo + '</div>' +
      '<table class="panel-historial-table w-100">' +
      '<thead><tr>';
    cols.forEach(function (c) {
      t += '<th style="font-size:.65rem;color:#6c757d;padding:.1rem .3rem;border-bottom:1px solid #dee2e6">' + c.label + '</th>';
    });
    t += '</tr></thead><tbody>';
    filas.forEach(function (f) {
      var vigente = !f.vigente_hasta;
      t += '<tr' + (vigente ? ' style="font-weight:600;color:#0d6efd"' : '') + '>';
      cols.forEach(function (c) {
        var v;
        if (c.render) {
          v = c.render(f[c.key]);
        } else {
          v = f[c.key] || '--';
          if ((c.key === 'vigente_desde' || c.key === 'vigente_hasta') && f[c.key]) {
            v = f[c.key].substring(0, 10);
          }
        }
        t += '<td style="font-size:.7rem;padding:.1rem .3rem;border-bottom:1px solid #f0f0f0">' + v + '</td>';
      });
      t += '</tr>';
    });
    t += '</tbody></table></div>';
    return t;
  }

  // ── Drag → modal cambio alimentacion ──────────────────────────────────────

  function _onDropSolicitud(activo_id, nuevo_padre_id) {
    var todos = _topologia ? _topologia.todos_activos || [] : [];
    var activo = null;
    for (var i = 0; i < todos.length; i++) {
      if (todos[i].id === activo_id) { activo = todos[i]; break; }
    }
    abrirCambioAlimentacion(activo_id, (activo && activo.nombre) || String(activo_id), nuevo_padre_id);
  }

  // ── Cerrar panel ──────────────────────────────────────────────────────────

  var btnCerrar = document.getElementById("btn-cerrar-panel");
  if (btnCerrar) {
    btnCerrar.addEventListener("click", function () {
      _seleccionadoId = null;
      document.getElementById("activos-detail-panel").style.display = "none";
      _renderUnifilar();
    });
  }

  // ── Refresh tras modales ──────────────────────────────────────────────────

  ["modalCambioAlimentacion", "modalCrearActivo", "modalEditarActivo", "modalVincularMedidor"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("hidden.bs.modal", cargarTopologia);
  });

  // ── Crear activo ──────────────────────────────────────────────────────────

  window.actualizarPadresCrear = function () {
    var tipo = document.getElementById("crear-tipo").value;
    var grupo = document.getElementById("crear-padre-grupo");
    var sel = document.getElementById("crear-padre");
    var tiposValidos = PADRES_VALIDOS[tipo] || [];
    if (tiposValidos.length === 0) {
      grupo.style.display = "none";
      sel.value = "";
      return;
    }
    grupo.style.display = "";
    llenarPadresSelect(sel, tipo, null, null);
  };

  window.guardarCrearActivo = function () {
    limpiarError("crear-error");
    var tipo   = document.getElementById("crear-tipo").value;
    var nombre = document.getElementById("crear-nombre").value.trim();
    var padre  = document.getElementById("crear-padre").value || null;
    var kva    = parseFloat(document.getElementById("crear-kva").value) || null;
    var kw     = parseFloat(document.getElementById("crear-kw").value) || null;
    var tc     = document.getElementById("crear-tipo-carga").value.trim() || null;
    var notas  = document.getElementById("crear-notas").value.trim() || null;
    post(baseUrl() + "/crear", {
      tipo: tipo, nombre: nombre,
      activo_padre_id: padre ? parseInt(padre) : null,
      capacidad_kva: kva, potencia_nominal_kw: kw, tipo_carga: tc, notas: notas,
    }).then(function () {
      mostrarToast("Activo creado");
      bootstrap.Modal.getInstance(document.getElementById("modalCrearActivo"))?.hide();
    }).catch(function (e) {
      mostrarError("crear-error", e.message);
    });
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
    var id     = parseInt(document.getElementById("editar-activo-id").value);
    var nombre = document.getElementById("editar-nombre").value.trim();
    var kva    = parseFloat(document.getElementById("editar-kva").value) || null;
    var kw     = parseFloat(document.getElementById("editar-kw").value) || null;
    var tc     = document.getElementById("editar-tipo-carga").value.trim() || null;
    var notas  = document.getElementById("editar-notas").value.trim() || null;
    post(baseUrl(id) + "/editar", { nombre: nombre, capacidad_kva: kva, potencia_nominal_kw: kw, tipo_carga: tc, notas: notas })
      .then(function () {
        mostrarToast("Activo actualizado");
        bootstrap.Modal.getInstance(document.getElementById("modalEditarActivo"))?.hide();
      }).catch(function (e) {
        mostrarError("editar-error", e.message);
      });
  };

  // ── Cambio de alimentacion ────────────────────────────────────────────────

  var _cambioTipoActivo = "";

  window.abrirCambioAlimentacion = function (activoId, nombre, fuenteActualId) {
    document.getElementById("cambio-activo-id").value = activoId;
    document.getElementById("cambio-activo-nombre").textContent = nombre;
    limpiarError("cambio-error");

    var activo = TODOS_ACTIVOS.find(function (a) { return a.id === activoId; });
    _cambioTipoActivo = activo ? activo.tipo : "";

    var sel = document.getElementById("cambio-fuente-select");
    llenarPadresSelect(sel, _cambioTipoActivo, activoId, fuenteActualId);

    document.getElementById("cambio-desde").value = "";
    document.getElementById("cambio-motivo").value = "";
    bootstrap.Modal.getOrCreateInstance(document.getElementById("modalCambioAlimentacion")).show();
  };

  window.guardarCambioAlimentacion = function () {
    limpiarError("cambio-error");
    var activoId  = parseInt(document.getElementById("cambio-activo-id").value);
    var fuenteVal = document.getElementById("cambio-fuente-select").value;
    var desdeVal  = document.getElementById("cambio-desde").value;
    var motivo    = document.getElementById("cambio-motivo").value.trim() || null;

    if (!fuenteVal) { mostrarError("cambio-error", "Selecciona una fuente de alimentacion."); return; }
    if (!desdeVal) { mostrarError("cambio-error", "La fecha de inicio es obligatoria."); return; }

    var desde = new Date(desdeVal).toISOString();

    post(baseUrl(activoId) + "/cambio-alimentacion", {
      fuente_activo_id: parseInt(fuenteVal),
      desde: desde,
      motivo: motivo,
    }).then(function () {
      mostrarToast("Cambio de alimentacion declarado");
      bootstrap.Modal.getInstance(document.getElementById("modalCambioAlimentacion"))?.hide();
    }).catch(function (e) {
      mostrarError("cambio-error", e.message);
    });
  };

  // ── Desactivar ────────────────────────────────────────────────────────────

  window.confirmarDesactivar = function (id, nombre) {
    if (!confirm('Desactivar "' + nombre + '"? Esta operacion es reversible desde base de datos.')) return;
    post(baseUrl(id) + "/desactivar", {})
      .then(function () { mostrarToast("Activo desactivado"); cargarTopologia(); })
      .catch(function (e) { alert("Error: " + e.message); });
  };

  // ── Eliminar permanente ───────────────────────────────────────────────────

  window.confirmarEliminarPermanente = function (id, nombre) {
    if (!confirm(
      'Eliminar permanentemente "' + nombre + '"?\n\n' +
      'Esta operacion borra el activo y su registro de alta.\n' +
      'No se puede deshacer.'
    )) return;
    post(baseUrl(id) + "/eliminar-permanente", {})
      .then(function () { mostrarToast("Activo eliminado"); cargarTopologia(); })
      .catch(function (e) { alert("No se puede eliminar:\n" + e.message); });
  };

  // ── Vincular / desvincular medidor ────────────────────────────────────────

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
      }).catch(function (e) {
        mostrarError("vincular-error", e.message);
      });
  };

  window.desvinculaActivo = function (id) {
    if (!confirm("Desvincular el medidor de este activo? La vigencia quedara cerrada en el historial.")) return;
    post(baseUrl(id) + "/desvincular-medidor", {})
      .then(function () { mostrarToast("Medidor desvinculado"); cargarTopologia(); })
      .catch(function (e) { alert("Error: " + e.message); });
  };

  window.asignarContratoAcometida = function (id) {
    var contratoId = document.getElementById("contrato-sel-" + id)?.value || null;
    var desdeVal   = document.getElementById("contrato-desde-" + id)?.value;
    var motivo     = document.getElementById("contrato-motivo-" + id)?.value.trim() || null;
    if (!desdeVal) { alert("La fecha de inicio es obligatoria."); return; }
    var desde = new Date(desdeVal).toISOString();
    post(baseUrl(id) + "/contrato-acometida", {
      contrato_id: contratoId ? parseInt(contratoId) : null,
      desde: desde,
      motivo: motivo,
    }).then(function () {
      mostrarToast("Contrato asignado");
      cargarTopologia();
    }).catch(function (e) {
      alert("Error: " + e.message);
    });
  };

  window.declararRolMedidor = function (activoId, medidorId) {
    var rol      = document.getElementById("rol-sel-" + activoId)?.value;
    var desdeVal = document.getElementById("rol-desde-" + activoId)?.value;
    var motivo   = document.getElementById("rol-motivo-" + activoId)?.value.trim() || null;
    if (!desdeVal) { alert("La fecha de inicio es obligatoria."); return; }
    var desde = new Date(desdeVal).toISOString();
    post(baseUrl(activoId) + "/medidor-rol", {
      medidor_id: medidorId,
      rol: rol,
      desde: desde,
      motivo: motivo,
    }).then(function () {
      mostrarToast("Rol declarado");
      cargarTopologia();
    }).catch(function (e) {
      alert("Error: " + e.message);
    });
  };

  // ── Init ──────────────────────────────────────────────────────────────────
  cargarTopologia();

})();
