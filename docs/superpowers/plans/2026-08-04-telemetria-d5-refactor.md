# Telemetría D5 — Refactor Completo (seed, agregación, layout, símbolos)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reestructurar el piloto de telemetría de Ibérica Tiles: un solo CBT por transformador, corrección del bug de 0 kWh, layout vertical fijo sin zoom semántico, y símbolos rediseñados.

**Architecture:** El seed refactorizado crea 1 CBT por transformador (12 en total). El backend es auditado para garantizar que `mediciones_por_hoja` llega correctamente a `_energia_nodo`. El frontend elimina la lógica de zoom y muestra siempre los 3 niveles (Acometida › Tx › CBT) con click para seleccionar.

**Tech Stack:** Python 3.11 (seed, Flask endpoint), JavaScript ES2020 (SVG puro), supabase-py, pytest.

## Global Constraints

- No modificar el esquema Supabase (tablas, columnas). Solo contenido.
- No introducir dependencias externas.
- Mantener `.limit(20000)` en todas las lecturas.
- No tocar Contabilidad, Cogeneración, parsers, mediciones_cincominutal, `/admin/telemetria`.
- No usar decoradores; verificación manual con `get_current_user()` se preserva.
- Acceso a Supabase exclusivamente vía supabase-py (no psycopg2, no SQL directo).
- Tests: `pytest tests/test_dashboard_telemetria.py` debe pasar sin regresiones.
- Responder en español; estilo directo y sin viñetas innecesarias.

---

### Task 1: Refactor seed_iberica.py — un CBT por transformador

**Files:**
- Modify: `scripts/seed_iberica.py`

**Interfaces:**
- Consumes: `telemetria.seed.generar_mediciones_por_carga(medidor, desde_utc, n, intervalo)` — sin cambios.
- Consumes: `storage.repository.crear_medidor_jerarquico`, `insertar_mediciones_batch` — sin cambios.
- Produces: 12 nodos `carga_final` en Supabase (6 por cliente), 8064 mediciones totales.

- [ ] **Step 1: Reemplazar PLANTA_1 con un solo CBT por transformador**

El mapeo exacto para PLANTA_1 (cliente_id=44):

```python
PLANTA_1 = {
    "cliente_id": 44,
    "acometida": {
        "nombre": "Acometida CFE-1 SE Poniente",
        "relacion_tc": "150/5",
    },
    "transformadores": [
        {
            "nombre": "T-1.1 (2500 kVA, MMC1)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-MMC1", "tipo_carga": "motor", "potencia_nominal_kw": 2400},
            ],
        },
        {
            "nombre": "T-1.2 (800 kVA, Vent. Atomizador 1)",
            "potencia_nominal_kw": 776,
            "cargas": [
                {"nombre": "CBT-Vent. Atomizador 1", "tipo_carga": "ventilador", "potencia_nominal_kw": 750},
            ],
        },
        {
            "nombre": "T-1.3 (1600 kVA, Zona Atomizado 1)",
            "potencia_nominal_kw": 1552,
            "cargas": [
                {"nombre": "CBT-Zona Atomizado 1", "tipo_carga": "atomizador", "potencia_nominal_kw": 1500},
            ],
        },
        {
            "nombre": "T-2.1 (2000 kVA, Zona Prensas)",
            "potencia_nominal_kw": 1940,
            "cargas": [
                {"nombre": "CBT-Zona Prensas", "tipo_carga": "prensa", "potencia_nominal_kw": 1900},
            ],
        },
        {
            "nombre": "T-3.1 (2000 kVA, Zona Hornos)",
            "potencia_nominal_kw": 1940,
            "cargas": [
                {"nombre": "CBT-Zona Hornos", "tipo_carga": "horno_tunel", "potencia_nominal_kw": 1900},
            ],
        },
        {
            "nombre": "T-SA (112.5 kVA, Serv. Auxiliares)",
            "potencia_nominal_kw": 109.125,
            "cargas": [
                {"nombre": "CBT-Serv. Auxiliares", "tipo_carga": "generico", "potencia_nominal_kw": 105},
            ],
        },
    ],
}
```

- [ ] **Step 2: Reemplazar PLANTA_2 con un solo CBT por transformador**

El mapeo exacto para PLANTA_2 (cliente_id=45):

```python
PLANTA_2 = {
    "cliente_id": 45,
    "acometida": {
        "nombre": "Acometida CFE-2 SE Sur",
        "relacion_tc": "150/5",
    },
    "transformadores": [
        {
            "nombre": "T-4.1 (2500 kVA, MMC2)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-MMC2", "tipo_carga": "motor", "potencia_nominal_kw": 2400},
            ],
        },
        {
            "nombre": "T-4.2 (800 kVA, Vent. Atomizador 2)",
            "potencia_nominal_kw": 776,
            "cargas": [
                {"nombre": "CBT-Vent. Atomizador 2", "tipo_carga": "ventilador", "potencia_nominal_kw": 750},
            ],
        },
        {
            "nombre": "T-4.3 (1000 kVA, Zona Atomizado 2)",
            "potencia_nominal_kw": 970,
            "cargas": [
                {"nombre": "CBT-Zona Atomizado 2", "tipo_carga": "atomizador", "potencia_nominal_kw": 950},
            ],
        },
        {
            "nombre": "T-5.1 (2500 kVA, Zona Prensas P2)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-Zona Prensas P2", "tipo_carga": "prensa", "potencia_nominal_kw": 2400},
            ],
        },
        {
            "nombre": "T-6.1 (2000 kVA, Zona Hornos P2)",
            "potencia_nominal_kw": 1940,
            "cargas": [
                {"nombre": "CBT-Zona Hornos P2", "tipo_carga": "horno_tunel", "potencia_nominal_kw": 1900},
            ],
        },
        {
            "nombre": "T-6.2 (2500 kVA, Pulido y Líneas 7-8)",
            "potencia_nominal_kw": 2425,
            "cargas": [
                {"nombre": "CBT-Pulido y Líneas 7-8", "tipo_carga": "pulidora", "potencia_nominal_kw": 2400},
            ],
        },
    ],
}
```

- [ ] **Step 3: Verificar que la lógica del seed no cambia**

No tocar `_crear_jerarquia`, `_sembrar_mediciones`, `_borrar_existentes`, `main`, ni la llamada a `generar_mediciones_por_carga`. Solo cambian las estructuras de datos PLANTA_1 y PLANTA_2.

- [ ] **Step 4: Verificar conteos esperados**

Tras el cambio, con `--forzar`:
- Acometidas: 2 (una por planta)
- Transformadores: 12 (6 por planta)
- Cargas finales (CBTs): 12 (1 por transformador = 6 por planta)
- Mediciones: 12 CBTs × 7 días × 24 horas × 4 por hora = 8064

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_iberica.py
git commit -m "feat(telemetria-D5): refactor seed a 1 CBT por transformador — 12 CBTs, 8064 mediciones"
```

---

### Task 2: Auditar y corregir bug de 0 kWh en agregación

**Files:**
- Modify: `web/app.py` (endpoint `cliente_dashboard_telemetria_data`)

**Interfaces:**
- Consumes: resultado de Task 1 (nueva estructura de CBTs) como contexto de validación.
- Produces: endpoint que devuelve kWh correctos para todos los nodos en vistas acometida, transformador y CBT.

**Contexto del bug:** Tras 2.76.3, el endpoint fetcha mediciones para `todas_hojas_ids` (todas las `carga_final` del árbol). La hipótesis principal es que los timestamps de las mediciones sembradas pueden estar fuera del rango de consulta, o que hay un problema de tipos (int vs str) en las claves de `mediciones_por_hoja`.

- [ ] **Step 1: Auditar el tipo de claves en mediciones_por_hoja**

En `web/app.py`, endpoint `cliente_dashboard_telemetria_data`, verificar:
- `todas_hojas_ids = [m["id"] for m in todos ...]` → Supabase devuelve `id` como `int`.
- `mediciones_por_hoja[hid]` → clave `int`.
- `_energia_nodo(mid)` → `mid` viene de `_arbol_sunburst_con_costo` → también `int`.
- `mediciones_por_hoja.get(mid, [])` → `mid` int, clave int. ✓

Si la auditoría confirma que el tipo es consistente (int-int), el bug es de datos (timestamps fuera de rango), no de código.

- [ ] **Step 2: Agregar log defensivo de conteos**

Al final del bucle de fetch de `mediciones_por_hoja`, agregar:

```python
# Diagnóstico: contar filas por hoja para detectar ventanas vacías
_n_filas_total = sum(len(v) for v in mediciones_por_hoja.values())
# Si todas las hojas están vacías, el sunburst mostrará 0 kWh
# (datos fuera del rango de fechas — re-ejecutar seed_iberica.py --forzar)
```

Este comentario es suficiente — no agregar prints ni logging que alteren el comportamiento.

- [ ] **Step 3: Corregir edge case hojas_ids_nodo fuera de todas_hojas_ids**

En el fallback `if not hojas_ids_nodo: hojas_ids_nodo = [nodo_id]`, el `nodo_id` podría ser un transformador (no `carga_final`). En ese caso, `mediciones_por_hoja.get(nodo_id, [])` devuelve `[]` porque el transformador no está en `todas_hojas_ids`.

Agregar fallback: si `hojas_ids_nodo` después del fallback incluye IDs que no son `carga_final`, incluirlos también en `todas_hojas_ids`:

```python
# Garantizar que hojas_ids_nodo esté cubierto en mediciones_por_hoja
# (edge case: nodo seleccionado es un tx sin cargas hijo)
ids_sin_datos = [hid for hid in hojas_ids_nodo if hid not in todas_hojas_ids]
for hid in ids_sin_datos:
    if rango == "24h":
        rows = _omr(hid, desde_iso, hasta_iso)
        mediciones_por_hoja[hid] = [
            {"ts": r["timestamp"], "kw": float(r.get("potencia_activa_kw") or 0),
             "fp": float(r.get("factor_potencia") or 0)}
            for r in rows
        ]
    else:
        rows = _oa15(hid, desde_iso, hasta_iso)
        mediciones_por_hoja[hid] = [
            {"ts": r["bucket_15min"], "kw": float(r.get("potencia_activa_kw") or 0),
             "fp": float(r.get("factor_potencia") or 0)}
            for r in rows
        ]
```

Este bloque va DESPUÉS del bucle principal de fetch y ANTES de la agregación.

- [ ] **Step 4: Ejecutar tests**

```bash
python3 -m pytest tests/test_dashboard_telemetria.py -v
```

Esperado: 8/8 passing.

- [ ] **Step 5: Commit**

```bash
git add web/app.py
git commit -m "fix(telemetria-D5): edge case hojas_ids_nodo no carga_final en mediciones_por_hoja"
```

---

### Task 3: Frontend — layout vertical fijo 3 niveles (Acometida › Tx › CBT)

**Files:**
- Modify: `web/static/js/dashboard-telemetria.js`
- Modify: `web/templates/telemetria/dashboard.html` (solo ajuste de min-height wrapper)

**Interfaces:**
- Consumes: `arbol_sunburst` del backend — estructura `{id, nombre, punto_medicion, potencia_nominal_kw, energia_kwh, costo_mxn, hijos: [...]}`.
- Produces: SVG siempre desplegado con 3 niveles, click selecciona nodo y actualiza KPIs/serie.

**Constantes a usar (exactas):**
```javascript
const W_ACOM = 220; const H_ACOM = 64;
const R_TX   = 28;           // aumentado de 22 a 28
const W_CBT  = 200; const H_CBT = 64;   // nuevo rectángulo CBT
const NIVEL_H_TX  = 160;     // separación acometida → nivel transformador
const NIVEL_H_CBT = 160;     // separación transformador → nivel CBT
const MIN_SEP = 220;         // separación mínima entre centros de transformador
const PAD_X   = 60;
const PAD_Y   = 40;
```

SVG height total: `PAD_Y + H_ACOM/2 + NIVEL_H_TX + (R_TX*2 + 12) + NIVEL_H_CBT + H_CBT + PAD_Y`
= `40 + 32 + 160 + 68 + 160 + 64 + 40` = **564 px**

(Usar esta fórmula explícitamente en el código.)

- [ ] **Step 1: Eliminar variables de estado de navegación**

Eliminar de la sección de estado:
- `_nodoRaizId` (ya no existe navegación por zoom)

Conservar:
- `_rango`, `_nodoId`, `_arbolCache`, `_chartSerie`, `_abort`

- [ ] **Step 2: Eliminar lógica de zoom semántico en _renderUnifilar**

Eliminar completamente:
- La función `_derivarSE` (agrupación por SE).
- Los tres bloques condicionales `if (vistaTx) ... else if (vistaSE) ... else`.
- Las variables `vistaAcometida`, `vistaSE`, `vistaTx`, `seMap`, `seKeys`.

Reemplazar con UN único layout:

```javascript
function _renderUnifilar(raiz) {
    if (!raiz) return;
    const svg = $("unifilarSvg");
    if (!svg) return;
    svg.innerHTML = "";

    const wrapper = $("unifilar-wrapper");
    const wrapW  = wrapper ? wrapper.clientWidth - 48 : 900;

    // Nivel 0: acometida
    const transformadores = raiz.hijos || [];
    const nTx = Math.max(transformadores.length, 1);

    const svgW = Math.max(wrapW, nTx * MIN_SEP + PAD_X * 2);
    const svgH = PAD_Y + H_ACOM/2 + NIVEL_H_TX + (R_TX*2 + 12) + NIVEL_H_CBT + H_CBT + PAD_Y;

    svg.setAttribute("width", svgW);
    svg.setAttribute("height", svgH);
    svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

    // Nivel 0: Acometida (centrada)
    const aX = svgW / 2;
    const aY = PAD_Y + H_ACOM / 2;
    const gA = _crearGrupoNodo(raiz.id, "acometida_cfe");
    const { x: aOutX, y: aOutY } = _dibujarAcometida(gA, raiz, aX, aY, _nodoId === raiz.id);
    svg.appendChild(gA);

    // Nivel 1: Transformadores + Nivel 2: CBTs (1:1)
    const paso = svgW / (nTx + 1);
    transformadores.forEach((tx, i) => {
        const txX = paso * (i + 1);
        const txY = aY + NIVEL_H_TX + R_TX + 6;   // centro Tx entre los dos círculos

        // Línea acometida → Tx
        _dibujarLinea(svg, aOutX, aOutY, txX, txY - R_TX - 6,
            tx.energia_kwh, tx.potencia_nominal_kw);

        // Símbolo Tx
        const gTx = _crearGrupoNodo(tx.id, "transformador");
        _dibujarTransformador(gTx, tx, txX, txY, _nodoId === tx.id);
        svg.appendChild(gTx);

        // CBT hijo (1:1)
        const cbt = (tx.hijos || [])[0];
        if (cbt) {
            const cbtX = txX;
            const cbtY = txY + R_TX + 6 + NIVEL_H_CBT;   // centro del CBT

            // Línea Tx → CBT (vertical)
            _dibujarLinea(svg, txX, txY + R_TX + 6, cbtX, cbtY - H_CBT / 2,
                cbt.energia_kwh, cbt.potencia_nominal_kw);

            // Rectángulo CBT
            const gCBT = _crearGrupoNodo(cbt.id, "carga_final");
            _dibujarCBT(gCBT, cbt, cbtX, cbtY, _nodoId === cbt.id);
            svg.appendChild(gCBT);
        }
    });
}
```

- [ ] **Step 3: Implementar _dibujarCBT (reemplaza _dibujarCarga)**

Nuevo símbolo CBT (rectángulo naranja 200×64, texto centrado):

```javascript
function _dibujarCBT(g, nodo, cx, cy, seleccionado) {
    const x = cx - W_CBT / 2;
    const y = cy - H_CBT / 2;
    const rect = _el("rect", {
        x, y, width: W_CBT, height: H_CBT, rx: 6,
        fill: "rgba(245,158,11,0.08)",
        stroke: seleccionado ? "#b45309" : C_CARGA,
        "stroke-width": seleccionado ? 4 : 2,
        class: "unifilar-fondo",
    });
    g.appendChild(rect);
    const nom = nodo.potencia_nominal_kw != null
        ? fmt(nodo.potencia_nominal_kw, 0) + " kW nom."
        : "";
    const kwh = nodo.energia_kwh != null ? fmt(nodo.energia_kwh) + " kWh" : "";
    g.appendChild(_multilineText(
        [nodo.nombre, nom, kwh], cx, cy - 12, 16, "unifilar-label-small"
    ));
    return { x: cx, y: cy + H_CBT / 2 };
}
```

- [ ] **Step 4: Actualizar _dibujarTransformador con R_TX=28**

Las constantes ya usan R_TX=28. Verificar que los cálculos de posición de etiquetas debajo del símbolo usen el nuevo radio:

```javascript
const labelY = cy2 + R_TX + 14;
```

Con R_TX=28: `cy2 = cy + 6`, `labelY = cy + 6 + 28 + 14 = cy + 48`.

- [ ] **Step 5: Actualizar _dibujarAcometida con W_ACOM=220**

Cambiar la constante `W_ACOM` de 180 a 220 en la declaración.

- [ ] **Step 6: Simplificar _handleClickNodo**

Eliminar la lógica de `se_agrupacion`, `_nodoRaizId`, y la asignación de primer Tx de la SE. El click ahora solo llama a `setNodo(id)`:

```javascript
function _handleClickNodo(id, tipo) {
    const nId = typeof id === "number" ? id : parseInt(id, 10);
    _nodoId = nId;
    fetchDatos();
}
```

- [ ] **Step 7: Simplificar setNodo**

Eliminar la actualización de `_nodoRaizId`. Solo actualiza `_nodoId`:

```javascript
function setNodo(id) {
    _nodoId = typeof id === "number" ? id : parseInt(id, 10);
    fetchDatos();
}
```

- [ ] **Step 8: Simplificar breadcrumbs**

El formato breadcrumb ahora es solo `"Cliente / Nodo seleccionado"`. El backend ya devuelve `nodo_seleccionado.ruta_breadcrumbs`; usar solo el último elemento (o los dos últimos) en vez de toda la ruta:

```javascript
function _renderBreadcrumbs(nodo) {
    const nav = $("breadcrumbs-telemetria");
    if (!nav) return;
    const ol = nav.querySelector("ol");
    ol.innerHTML = "";
    // Mostrar solo los 2 últimos segmentos de la ruta
    const ruta = nodo.ruta_breadcrumbs || [];
    const segmentos = ruta.length > 2 ? ruta.slice(-2) : ruta;
    segmentos.forEach((seg, idx) => {
        const li = document.createElement("li");
        li.className = "breadcrumb-item";
        if (idx === segmentos.length - 1) {
            li.classList.add("active");
            li.setAttribute("aria-current", "page");
            li.textContent = seg.nombre;
        } else {
            li.innerHTML = `<a href="#" data-nodo-id="${seg.id}">${seg.nombre}</a>`;
            li.querySelector("a").addEventListener("click", (e) => {
                e.preventDefault();
                setNodo(seg.id);
            });
        }
        ol.appendChild(li);
    });
}
```

- [ ] **Step 9: Ajustar min-height del wrapper en el HTML**

En `web/templates/telemetria/dashboard.html`, cambiar `min-height:280px` → `min-height:380px` en `#unifilar-wrapper` para acomodar el nuevo SVG de ~564 px.

- [ ] **Step 10: Eliminar _dibujarCarga y _crearGrupoNodo references a se_agrupacion**

Eliminar la función `_dibujarCarga` (ya no se usa; la reemplaza `_dibujarCBT`).
En `_crearGrupoNodo`, eliminar la línea que agrega clase `unifilar-se-agrupacion`.

- [ ] **Step 11: Ejecutar tests**

```bash
python3 -m pytest tests/test_dashboard_telemetria.py -v
```

Esperado: 8/8 passing (los tests son de backend; el JS no afecta los tests).

- [ ] **Step 12: Commit**

```bash
git add web/static/js/dashboard-telemetria.js web/templates/telemetria/dashboard.html
git commit -m "feat(telemetria-D5): layout vertical fijo 3 niveles sin zoom semantico, simbolos rediseñados"
```

---

### Task 4: Actualizar tests y CHANGELOG

**Files:**
- Modify: `tests/test_dashboard_telemetria.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: estructura de CBTs de Task 1 (nombre "CBT-*", 1 por transformador).
- Produces: 8/8 tests passing, CHANGELOG con entrada 2.77.0.

**Contexto de tests:** Los tests actuales usan `ARBOL_MOCK` con cargas "Horno 1" y "Horno 2" y `DESC_IDS_MOCK = [3, 4]`. Estos reflejan la estructura de árbol (acometida → transformador → cargas). La estructura interna del mock no necesita cambiar para los tests de backend — el nombre de las cargas no afecta la lógica de agregación. Solo el test `test_telemetria_data_nodo_carga_final_sin_agregacion` necesita verificación de que sigue pasando con la nueva lógica.

- [ ] **Step 1: Ejecutar todos los tests y verificar que pasan**

```bash
python3 -m pytest tests/test_dashboard_telemetria.py -v
```

Si algún test falla, identificar la causa y corregir.

- [ ] **Step 2: Actualizar ARBOL_MOCK si algún test usa nombre de carga específico**

Si algún test verifica el nombre "Horno 1" o "Horno 2", actualizarlo a "CBT-Zona Hornos" y "CBT-Zona Prensas". Buscar en el archivo antes de cambiar.

- [ ] **Step 3: Agregar entrada 2.77.0 al inicio de CHANGELOG.md**

Formato:

```markdown
## [2.77.0] — 2026-08-04

### Añadido/Refactorizado — Fase 2 D5: reestructuración completa de telemetría piloto

- `scripts/seed_iberica.py` — PLANTA_1 y PLANTA_2 refactorizadas: de N cargas inventadas por transformador a 1 CBT (Cuadro de Baja Tensión) por transformador. Planta 1: 6 CBTs (CBT-MMC1, CBT-Vent. Atomizador 1, CBT-Zona Atomizado 1, CBT-Zona Prensas, CBT-Zona Hornos, CBT-Serv. Auxiliares). Planta 2: 6 CBTs (CBT-MMC2, CBT-Vent. Atomizador 2, CBT-Zona Atomizado 2, CBT-Zona Prensas P2, CBT-Zona Hornos P2, CBT-Pulido y Líneas 7-8). Total: 12 CBTs, 8064 mediciones sintéticas (7d × 4/h).
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data`: fallback defensivo para el caso donde `hojas_ids_nodo` incluye IDs que no están en `todas_hojas_ids` (transformador sin cargas hijo). Los IDs faltantes se fetchan individualmente y se agregan a `mediciones_por_hoja` antes de la agregación.
- `web/static/js/dashboard-telemetria.js` — layout del unifilar completamente reescrito: se elimina la navegación por zoom semántico (nodoRaiz, vistaAcometida/vistaSE/vistaTx, grupos SE, breadcrumbs jerárquicos). El diagrama muestra SIEMPRE los 3 niveles completos: Acometida › Transformadores (fila) › CBT hijo (1:1). Click en cualquier nodo selecciona y actualiza KPIs/serie sin restructurar el árbol. Constantes: W_ACOM=220, R_TX=28, W_CBT=200×H_CBT=64, NIVEL_H_TX=160, NIVEL_H_CBT=160, MIN_SEP=220.
- `web/static/js/dashboard-telemetria.js` — nueva función `_dibujarCBT` (reemplaza `_dibujarCarga`): rectángulo 200×64 naranja con 3 líneas de texto (nombre CBT, potencia nominal, kWh). `_dibujarTransformador`: radio R_TX aumentado de 22 a 28. `_dibujarAcometida`: W_ACOM aumentado de 180 a 220.
- `web/templates/telemetria/dashboard.html` — `#unifilar-wrapper` min-height 280 → 380 px para acomodar el nuevo SVG de ~564 px.
```

- [ ] **Step 4: Commit final**

```bash
git add tests/test_dashboard_telemetria.py CHANGELOG.md
git commit -m "feat(telemetria-D5): refactor completo telemetria — CBTs, agregacion, layout vertical fijo"
git push
```

---
