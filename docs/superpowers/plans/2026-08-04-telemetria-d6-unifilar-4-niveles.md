# Telemetría D6 — Unifilar 4 Niveles y Etiquetas Laterales

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un nivel visual de Subestación (SE) entre Acometida y Transformador en el diagrama unifilar, y reubicar las etiquetas del transformador a la derecha del símbolo doble círculo.

**Architecture:** Los nodos SE son virtuales — se derivan en el frontend agrupando los transformadores por el prefijo `/^T-(\d+)/` de su nombre. El backend no se toca. Todos los cambios son en `dashboard-telemetria.js` (lógica de layout y dibujo) y `dashboard.html` (altura del wrapper).

**Tech Stack:** SVG puro vía `document.createElementNS`, JavaScript ES6+, Flask/Jinja2.

## Global Constraints

- No modificar backend (`web/app.py`, `storage/repository.py`), ni base de datos, ni tests.
- No introducir dependencias externas.
- Los nodos SE tienen IDs string con prefijo `"grupo:"` (ej. `"grupo:SE-1"`). El backend solo recibe IDs numéricos; para nodos virtuales no se envía `nodo_id` al backend.
- R_TX = 26 (spec; actual en 2.77.0 es 28 — cambiar).
- MIN_SEP = 180 (mínimo entre centros de Tx; actual es 220 — cambiar).
- NIVEL_H = 100 (única constante de separación entre niveles; reemplaza NIVEL_H_TX=160 y NIVEL_H_CBT=160).
- PAD_Y = 30 (actual es 40 — cambiar).
- SVG resultante: ~424px de alto. Wrapper min-height: 500px.
- Responder en español. No añadir comentarios que no sean necesarios.

---

## Archivos que cambian

| Archivo | Cambio |
|---------|--------|
| `web/static/js/dashboard-telemetria.js` | Nueva función `_agruparPorSE`, nueva función `_dibujarSE`, reescribir `_renderUnifilar` (4 niveles), actualizar `_dibujarTransformador` (etiquetas a la derecha), actualizar constantes, actualizar `_handleClickNodo`/`setNodo`/`fetchDatos` para IDs virtuales |
| `web/templates/telemetria/dashboard.html` | `min-height:380px` → `min-height:500px` en `#unifilar-wrapper` |
| `CHANGELOG.md` | Entrada v2.78.0 |

---

### Task 1: JS + HTML — Nivel SE virtual, layout 4 niveles, etiquetas Tx a la derecha

**Files:**
- Modify: `web/static/js/dashboard-telemetria.js`
- Modify: `web/templates/telemetria/dashboard.html`
- Test: `tests/test_dashboard_telemetria.py` (sin cambios, solo verificar que pasan)

**Interfaces:**
- Consumes: `data.arbol_sunburst` del backend — estructura `{id, nombre, energia_kwh, potencia_nominal_kw, costo_mxn, hijos: [tx...]}` donde cada tx tiene `{id, nombre, energia_kwh, potencia_nominal_kw, hijos: [cbt]}`.
- Produces: función `_agruparPorSE(transformadores)` → array de nodos SE virtuales; función `_dibujarSE(g, nodo, cx, cy, seleccionado)` → `{x, y}`.

- [ ] **Step 1: Leer el archivo actual para tener el contexto exacto**

Lee `web/static/js/dashboard-telemetria.js` completo. El bloque de constantes está en las líneas 12-22.

- [ ] **Step 2: Reemplazar el bloque de constantes visuales (líneas 12-22)**

Reemplaza el bloque completo de constantes (desde `// Dimensiones de nodos` hasta el cierre del bloque `// Layout`) con:

```javascript
  // Dimensiones de nodos (px)
  const W_ACOM = 220; const H_ACOM = 64;
  const W_SE   = 100; const H_SE   = 40;   // subestación virtual (no existe en BD)
  const R_TX   = 26;                        // radio del círculo transformador
  const W_CBT  = 200; const H_CBT  = 64;   // cuadro de baja tensión

  // Layout
  const NIVEL_H = 100;   // separación entre centros de nivel (px)
  const MIN_SEP = 180;   // separación mínima entre centros de Tx (px)
  const PAD_X   = 60;
  const PAD_Y   = 30;
```

- [ ] **Step 3: Añadir la función `_agruparPorSE` antes de `_renderUnifilar`**

Justo antes de la línea que contiene `function _renderUnifilar(raiz)`, inserta:

```javascript
  /**
   * Agrupa transformadores por SE derivada del nombre (regex /^T-(\d+)/).
   * Devuelve nodos SE virtuales con IDs string "grupo:SE-N".
   */
  function _agruparPorSE(transformadores) {
    const grupos = new Map();
    transformadores.forEach((tx) => {
      const m = tx.nombre.match(/^T-(\d+)/);
      const key = m ? m[1] : "X";
      if (!grupos.has(key)) grupos.set(key, []);
      grupos.get(key).push(tx);
    });
    return Array.from(grupos.entries()).map(([num, txs]) => ({
      id: `grupo:SE-${num}`,
      nombre: `SE-${num}`,
      punto_medicion: "subestacion",
      energia_kwh: txs.reduce((s, t) => s + (t.energia_kwh || 0), 0),
      potencia_nominal_kw: txs.reduce((s, t) => s + (t.potencia_nominal_kw || 0), 0),
      costo_mxn: txs.reduce((s, t) => s + (t.costo_mxn || 0), 0),
      hijos: txs,
    }));
  }
```

- [ ] **Step 4: Añadir la función `_dibujarSE` después de `_dibujarAcometida`**

Justo después del cierre de `_dibujarAcometida` (después de la línea `return { x: cx, y: cy + H_ACOM / 2 };` y su cierre `}`), inserta:

```javascript
  /** Subestación virtual: rectángulo punteado 100×40, borde azul primario. */
  function _dibujarSE(g, nodo, cx, cy, seleccionado) {
    const x = cx - W_SE / 2;
    const y = cy - H_SE / 2;
    g.appendChild(_el("rect", {
      x, y, width: W_SE, height: H_SE, rx: 6,
      fill: "rgba(31,58,95,0.06)",
      stroke: seleccionado ? C_PRIMARIO : C_PRIMARIO_L,
      "stroke-width": seleccionado ? 3 : 1.5,
      "stroke-dasharray": "5,3",
      class: "unifilar-fondo",
    }));
    const t1 = _el("text", {
      x: cx, y: cy - 5,
      class: "unifilar-label", "text-anchor": "middle",
      "font-size": "12", "font-weight": "bold",
    });
    t1.textContent = nodo.nombre;
    g.appendChild(t1);
    if (nodo.energia_kwh != null) {
      const t2 = _el("text", {
        x: cx, y: cy + 9,
        class: "unifilar-label-small", "text-anchor": "middle", "font-size": "10",
      });
      t2.textContent = fmt(nodo.energia_kwh) + " kWh";
      g.appendChild(t2);
    }
    return { x: cx, y: cy + H_SE / 2 };
  }
```

- [ ] **Step 5: Reemplazar `_dibujarTransformador` (etiquetas a la derecha)**

Reemplaza la función completa `_dibujarTransformador` (desde `/** Transformador:` hasta el `}` de cierre) con:

```javascript
  /** Transformador: doble círculo con etiquetas a la derecha del símbolo. */
  function _dibujarTransformador(g, nodo, cx, cy, seleccionado) {
    const cy1 = cy - 6; const cy2 = cy + 6;
    const sw = seleccionado ? 3 : 1.5;
    g.appendChild(_el("circle", {
      cx, cy: cy1, r: R_TX, fill: "white",
      stroke: C_PRIMARIO, "stroke-width": sw, class: "unifilar-fondo",
    }));
    g.appendChild(_el("circle", {
      cx, cy: cy2, r: R_TX, fill: "rgba(255,255,255,0.7)",
      stroke: C_PRIMARIO, "stroke-width": sw, class: "unifilar-fondo",
    }));
    // Etiquetas a la derecha: elimina solape con líneas de conexión
    const nombreMatch = nodo.nombre.match(/^(T-\d+\.\d+)/);
    const kvaMatch    = nodo.nombre.match(/(\d+\s*kVA)/);
    const nombreCorto = nombreMatch ? nombreMatch[1] : nodo.nombre.substring(0, 12);
    const kvaCorto    = kvaMatch ? kvaMatch[1] : "";
    const kwh         = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
    const lx = cx + R_TX + 12;
    [
      [nombreCorto, "12", "bold"],
      [kvaCorto,    "10", "normal"],
      [kwh,         "10", "bold"],
    ].forEach(([l, fs, fw], i) => {
      if (!l) return;
      const t = _el("text", {
        x: lx, y: cy - 8 + i * 14,
        class: "unifilar-label-small", "text-anchor": "start",
        "font-size": fs, "font-weight": fw,
      });
      t.textContent = l;
      g.appendChild(t);
    });
    return { x: cx, y: cy2 + R_TX };
  }
```

- [ ] **Step 6: Reemplazar `_renderUnifilar` (layout 4 niveles)**

Reemplaza la función completa `_renderUnifilar` (desde el comentario `/** renderUnifilar` hasta el `}` de cierre de la función) con:

```javascript
  /**
   * renderUnifilar — layout vertical fijo 4 niveles.
   * Nivel 0: Acometida (centrada)
   * Nivel 1: Subestaciones virtuales SE (agrupan Txs por prefijo T-N)
   * Nivel 2: Transformadores (distribuidos uniformemente)
   * Nivel 3: CBTs (1:1 con cada Tx, alineados verticalmente)
   */
  function _renderUnifilar(raiz) {
    if (!raiz) return;
    const svg = $("unifilarSvg");
    if (!svg) return;
    svg.innerHTML = "";

    const wrapper = $("unifilar-wrapper");
    const wrapW  = wrapper ? wrapper.clientWidth - 48 : 900;

    const gruposSE    = _agruparPorSE(raiz.hijos || []);
    const todosLosTxs = gruposSE.flatMap((se) => se.hijos);
    const nTx = Math.max(todosLosTxs.length, 1);

    const svgW = Math.max(wrapW, nTx * MIN_SEP + PAD_X * 2);

    // Y de cada nivel (centros)
    const yAcom = PAD_Y + H_ACOM / 2;
    const ySE   = yAcom + NIVEL_H;
    const yTx   = ySE   + NIVEL_H;
    const yCbt  = yTx   + NIVEL_H;
    const svgH  = yCbt  + H_CBT / 2 + PAD_Y;

    svg.setAttribute("width",   svgW);
    svg.setAttribute("height",  svgH);
    svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

    // X de cada Tx: distribuidos uniformemente sobre el ancho del SVG
    const pasoTx = svgW / (nTx + 1);
    const txXmap = new Map();
    todosLosTxs.forEach((tx, i) => txXmap.set(tx.id, pasoTx * (i + 1)));

    // Nivel 0: Acometida
    const aX = svgW / 2;
    const gA = _crearGrupoNodo(raiz.id, "acometida_cfe");
    const { x: aOutX, y: aOutY } =
      _dibujarAcometida(gA, raiz, aX, yAcom, _nodoId === raiz.id);
    svg.appendChild(gA);

    // Niveles 1-3: SE → Tx → CBT
    gruposSE.forEach((se) => {
      // SE se centra en el promedio X de sus Txs hijos
      const seXs = se.hijos.map((tx) => txXmap.get(tx.id));
      const seX  = seXs.reduce((a, b) => a + b, 0) / seXs.length;

      // Línea Acometida → SE
      _dibujarLinea(svg, aOutX, aOutY, seX, ySE - H_SE / 2,
        se.energia_kwh, se.potencia_nominal_kw);

      // Símbolo SE
      const gSE = _crearGrupoNodo(se.id, "subestacion");
      _dibujarSE(gSE, se, seX, ySE, String(_nodoId) === se.id);
      svg.appendChild(gSE);

      // Cada Tx hijo de esta SE
      se.hijos.forEach((tx) => {
        const txX = txXmap.get(tx.id);

        // Línea SE → Tx
        _dibujarLinea(svg, seX, ySE + H_SE / 2, txX, yTx - R_TX - 6,
          tx.energia_kwh, tx.potencia_nominal_kw);

        // Símbolo Tx
        const gTx = _crearGrupoNodo(tx.id, "transformador");
        _dibujarTransformador(gTx, tx, txX, yTx, _nodoId === tx.id);
        svg.appendChild(gTx);

        // CBT hijo (1:1)
        const cbt = (tx.hijos || [])[0];
        if (cbt) {
          _dibujarLinea(svg, txX, yTx + R_TX + 6, txX, yCbt - H_CBT / 2,
            cbt.energia_kwh, cbt.potencia_nominal_kw);
          const gCBT = _crearGrupoNodo(cbt.id, "carga_final");
          _dibujarCBT(gCBT, cbt, txX, yCbt, _nodoId === cbt.id);
          svg.appendChild(gCBT);
        }
      });
    });
  }
```

- [ ] **Step 7: Actualizar `fetchDatos` para no enviar IDs virtuales al backend**

En la función `fetchDatos`, la línea actual es:
```javascript
    if (_nodoId) params.set("nodo_id", _nodoId);
```

Reemplázala con:
```javascript
    if (_nodoId !== null && _nodoId !== undefined &&
        !String(_nodoId).startsWith("grupo:")) {
      params.set("nodo_id", String(_nodoId));
    }
```

- [ ] **Step 8: Actualizar `_handleClickNodo` y `setNodo` para IDs virtuales**

Reemplaza la función `_handleClickNodo`:
```javascript
  function _handleClickNodo(id, tipo) {
    _nodoId = typeof id === "string" && id.startsWith("grupo:") ? id : parseInt(id, 10);
    fetchDatos();
  }
```

Reemplaza la función `setNodo`:
```javascript
  function setNodo(id) {
    _nodoId = typeof id === "string" && id.startsWith("grupo:") ? id : parseInt(id, 10);
    fetchDatos();
  }
```

- [ ] **Step 9: Actualizar `dashboard.html` — wrapper min-height**

En `web/templates/telemetria/dashboard.html`, en el div `#unifilar-wrapper`, cambia:
```html
       margin-bottom:1rem">
```

El atributo style completo es: `style="position:relative;min-height:380px;overflow-x:auto;background:#f8fafc;border-radius:8px;padding:24px;margin-bottom:1rem"`. Cambia `min-height:380px` a `min-height:500px`.

- [ ] **Step 10: Ejecutar los tests de backend para verificar que no hay regresión**

```bash
python3 -m pytest tests/test_dashboard_telemetria.py -v
```

Esperado: 8/8 passing. Si alguno falla, reportar el traceback sin intentar arreglar tests que dependan de lógica de backend no modificada.

- [ ] **Step 11: Commit**

```bash
git add web/static/js/dashboard-telemetria.js web/templates/telemetria/dashboard.html
git commit -m "feat(fase2-D6): agrega nivel de subestacion virtual y reubica etiquetas de transformador a la derecha"
```

---

### Task 2: CHANGELOG y push

**Files:**
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: commit del Task 1.
- Produces: entrada v2.78.0 en CHANGELOG, push a origin/main.

- [ ] **Step 1: Agregar entrada v2.78.0 al inicio de CHANGELOG.md**

Inserta al inicio del archivo (antes del primer `## [2.77.0]`):

```markdown
## [2.78.0] — 2026-08-04

### Refactorizado — Fase 2 D6: unifilar 4 niveles y etiquetas laterales

- `web/static/js/dashboard-telemetria.js` — nueva función `_agruparPorSE`: agrupa los transformadores hijo de la acometida por el prefijo `/^T-(\d+)/` y genera nodos SE virtuales con ID string `"grupo:SE-N"` (no existen en BD). Nueva función `_dibujarSE`: rectángulo 100×40 punteado, fondo azul claro, 2 líneas de texto (nombre SE y kWh del periodo).
- `web/static/js/dashboard-telemetria.js` — `_renderUnifilar` reescrito de 3 a 4 niveles: Acometida › SE › Transformador › CBT. Las SEs se distribuyen horizontalmente centradas sobre el grupo de Txs hijos; los Txs se distribuyen uniformemente. Constantes actualizadas: R_TX 28→26, MIN_SEP 220→180, NIVEL_H=100 (reemplaza NIVEL_H_TX=160 y NIVEL_H_CBT=160), PAD_Y 40→30.
- `web/static/js/dashboard-telemetria.js` — `_dibujarTransformador` actualizado: etiquetas (nombre corto, kVA, kWh) reubicadas a la derecha del símbolo doble círculo (text-anchor=start, x=cx+R_TX+12) eliminando el solape visual con las líneas de conexión.
- `web/static/js/dashboard-telemetria.js` — `fetchDatos`, `_handleClickNodo`, `setNodo` actualizados para manejar IDs virtuales (prefijo `"grupo:"`): no se envía `nodo_id` al backend para nodos SE; clic en SE muestra el agregado completo del árbol.
- `web/templates/telemetria/dashboard.html` — `#unifilar-wrapper` min-height 380→500 px para acomodar SVG de ~424 px.

```

- [ ] **Step 2: Commit y push**

```bash
git add CHANGELOG.md
git commit -m "chore: CHANGELOG v2.78.0 — telemetria D6 unifilar 4 niveles"
git push
```

- [ ] **Step 3: Verificar push exitoso**

```bash
git log --oneline -4
```

Esperado: los últimos 4 commits incluyen los de Task 1 y Task 2 de esta feature.

---

## Notas de implementación

**Agrupación SE para IBERICA TILES (datos actuales):**

| SE | Transformadores |
|----|----------------|
| SE-1 | T-1.1, T-1.2, T-1.3 |
| SE-2 | T-2.1 |
| SE-3 | T-3.1 |
| SE-X | T-SA (no match regex) |

(PLANTA_2 análogamente con T-4.x → SE-4, etc.)

**Por qué no enviar `nodo_id` para SE:** Los nodos SE no existen en la base de datos. El backend parsearia el ID "grupo:SE-1" como entero y fallaría. Omitir `nodo_id` hace que el backend devuelva el agregado completo del árbol, que es equivalente a "ver toda la SE combinada" — comportamiento aceptable y especificado.

**Cálculo de altura SVG con constantes finales:**

```
yAcom = 30 + 32 = 62
ySE   = 62 + 100 = 162
yTx   = 162 + 100 = 262
yCbt  = 262 + 100 = 362
svgH  = 362 + 32 + 30 = 424 px
```
