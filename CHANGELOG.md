# Changelog

## [2.82.6] — 2026-08-06

### Corregido — Backend interpreta nodo_id virtual `grupo:SE-N` para agregación por subestación

- `web/app.py` — `cliente_dashboard_telemetria_data`: `request.args.get("nodo_id", type=int)`
  descartaba silenciosamente el formato `"grupo:SE-N"` enviado por el frontend al hacer clic
  en un nodo de subestación virtual del árbol. El endpoint caía al nodo acometida y mostraba
  datos de toda la planta en lugar de los de la SE seleccionada.
- Solución: leer `nodo_id_raw` como string. Si empieza con `"grupo:"`, extraer el número de SE,
  localizar los transformadores con prefijo `T-{num_se}.`, obtener sus descendientes
  `carga_final` y construir un `_nodo_virtual` dict con `id`, `nombre`, `punto_medicion`
  y `ruta_breadcrumbs`. La respuesta JSON usa `_nodo_virtual` cuando está disponible, o el
  dict de nodo real en caso contrario.
- Los KPIs, la serie temporal y la comparativa ya utilizan `hojas_ids_nodo`, que ahora
  agrega correctamente solo las cargas de la SE seleccionada.

## [2.82.5] — 2026-08-08

### Corregido — Ancla temporal del dashboard de telemetría desacoplada del reloj real

- `storage/repository.py` — nueva función `obtener_ultimo_timestamp_cliente(cliente_id)`:
  retorna `max(timestamp)` de `mediciones_tiempo_real` para todos los medidores del cliente.
  Usado como "ahora" en la ventana temporal del endpoint en modo demo.
- `web/app.py` — `cliente_dashboard_telemetria_data`: sustituye `datetime.now()` por
  `obtener_ultimo_timestamp_cliente()` con fallback a `now()`. Añade `modo_temporal`
  (`"sintetico"` | `"tiempo_real"`) en `kpis_paneles.meta`. Elimina el desfase entre datos
  sintéticos del seed y el reloj real, que causaba ceros cuando pasaban >24h sin re-seed.
  **DEUDA TÉCNICA REVERSIBLE:** revertir a `datetime.now()` cuando entren medidores físicos
  con MQTT continuo. Ver `CLAUDE.md` sección "Deuda técnica temporal".
- `CLAUDE.md` — documenta la deuda técnica con instrucción de reversión.
- Tests: `_mock_repo` y `_patch_costo` añaden mock de `obtener_ultimo_timestamp_cliente`
  con timestamp fijo para aislar los tests de llamadas reales a Supabase.

## [2.82.4] — 2026-08-08

### Corregido — Saturación de sockets Supabase (Errno 11 EAGAIN) y regresión pestaña Producción

- `web/app.py` — `cliente_dashboard_telemetria_data`: elimina `ThreadPoolExecutor`; los
  fetches por medidor pasan a ejecución secuencial. El tiempo de respuesta sube ~2–4s pero
  elimina la saturación de file descriptors en Render free tier (Errno 11 bajo carga
  concurrente). Se elimina el import de `concurrent.futures`.
- `storage/repository.py` — `_ejecutar_con_reintentos`: añade `httpx.ReadError` al tuple
  de excepciones reintentables (era la excepción exacta del traceback de producción; las
  excepciones anteriores eran insuficientes para capturarla).
- `web/static/js/dashboard-telemetria.js` — `fetchDatos`: oculta la pestaña Producción
  **al inicio de cada fetch** (pesimista) cuando el rango no es `30d`, en lugar de esperar
  la respuesta. Corrige la regresión donde la pestaña quedaba visible al cambiar de 30d a
  24h/7d mientras el fetch estaba en vuelo.

## [2.82.3] — 2026-08-08

### Corregido — Race condition al cambiar de rango temporal en dashboard de telemetría

- `web/static/js/dashboard-telemetria.js`:
  - Añade `_rangoEnCurso` (debounce): `setRango(r)` ignora el click si `r` ya está
    en vuelo, evitando que un doble-click sobre el mismo rango desplace el fetch en curso.
  - Añade guarda `if (controller.signal.aborted) return` tras `await resp.json()`:
    previene render stale cuando el browser entrega el body de una respuesta ya abortada.
  - Error HTTP (ej. 500): en lugar de `throw` que llega al catch, retorna directamente
    tras `_mostrarError(...)`. El DOM previo queda intacto; solo el banner de error aparece.

## [2.82.2] — 2026-08-07

### Corregido — Homogeneización de nombres de columnas entre vistas agregadas y tabla raw

- `storage/repository.py` — `obtener_mediciones_para_rango`: las vistas materializadas
  `mediciones_agregadas_5min` y `mediciones_agregadas_horarias` exponen
  `potencia_activa_promedio_kw`, `factor_potencia_promedio` y
  `energia_importada_periodo_kwh`, distintos a los de `mediciones_tiempo_real`.
  El código leía los nombres de la tabla raw, obtenía `None` y caía al default 0.
  Corregido: los tres campos se leen con los nombres reales de las vistas y se
  renombran a los canónicos (`potencia_activa_kw`, `factor_potencia`,
  `energia_activa_importada_kwh`) que consume el resto de la aplicación.
  Aplica a ambas ramas (24h → 5min; 7d/30d → horaria).

## [2.82.1] — 2026-08-06

### Corregido — Saturación de conexiones HTTP/2 a Supabase en endpoint de telemetría

- `storage/repository.py` — añade `ClientOptions(postgrest_client_timeout=30)` al singleton `_supabase` (timeout explícito de 30 s en lugar del default 120 s). Añade `_ejecutar_con_reintentos(fn)`: wrapper con hasta 3 intentos y backoff exponencial (2 s / 4 s / 8 s) ante `httpx.RemoteProtocolError`, `httpx.ReadTimeout` y `httpx.ConnectError`. `obtener_agregados_5min` y `obtener_agregados_horarios` envuelven su `.execute()` con el wrapper.
- `web/app.py` — restructura el `ThreadPoolExecutor` del endpoint `cliente_dashboard_telemetria_data`: de `max_workers=2` con dos tareas bulk (una por periodo) a `max_workers=4` con una tarea por medidor que serializa internamente el fetch actual y el fetch anterior, limitando las conexiones HTTP/2 concurrentes a 4.

## [2.82.0] — 2026-08-05

### Añadido — Fase 2 D7-B: frontend KPIs telemetría con tabs, tarjetas, gauge PF y formulario producción

- `web/templates/telemetria/dashboard.html` — reemplaza el panel de 6 tarjetas KPI horizontales por estructura de 3 pestañas Bootstrap (Energéticos / Económicos / Producción). Panes vacíos renderizados por JS; HTML sin lógica.
- `web/static/css/telemetria.css` — añade `.kpi-grid`, `.kpi-card-v2`, `.kpi-delta-badge` (favorable/desfavorable/neutro), `.kpi-hint`, `.kpi-sparkline-wrap`, `.kpi-gauge-wrap`, `.kpi-gauge-label`.
- `web/static/js/dashboard-telemetria.js` — nuevas funciones: `_crearSparkline`, `_renderKpiCard` (tarjeta con badge delta y sparklines duales), `_renderKpiGauge` (doughnut semicírculo Chart.js para Factor de Potencia; verde ≥ 0.90, amarillo ≥ 0.80, rojo < 0.80), `_renderFormularioProduccion` (POST asíncrono con feedback inline), `_renderKpisPaneles` (respeta `oculto_en_nodo`, `aplica_a_nodo`, `solo_en_rango`; pestaña Producción oculta en rangos 24h y 7d; estado `_tabActivo` persiste entre re-fetches). Eliminadas `_renderKPIs` y `_renderComparativa` (código muerto tras eliminación de sus elementos DOM).
- `web/app.py` — añade `punto_medicion` al dict `nodo_seleccionado` en la respuesta JSON del endpoint `cliente_dashboard_telemetria_data`.
- `tests/test_dashboard_telemetria.py` — 5 tests nuevos (i–m): POST producción 200 ok, 400 sin m2_mes, 400 m2_mes negativo, 302 sin auth (antes_request redirige), 404 FASE2 deshabilitada.

## [2.81.0] — 2026-08-05

### Añadido — Fase 2 D7-A v3: resolución 5-min, agregado horario, seed 207k muestras, endpoint POST producción

- `storage/migrations/202609_mediciones_5min_horarias.sql` — nuevas vistas materializadas `mediciones_agregadas_5min` (bucket de 5 min) y `mediciones_agregadas_horarias` (bucket horario), con índices únicos por (medidor_id, bucket) y jobs pg_cron de refresco (cada 5 min / cada hora).
- `storage/repository.py` — nuevas funciones `obtener_agregados_5min` y `obtener_agregados_horarios` que leen las nuevas vistas. `obtener_mediciones_para_rango` actualizado: rango='24h' → vista 5-min; rango='7d'/'30d' → vista horaria (antes usaba mediciones_tiempo_real y mediciones_agregadas_15min). Nuevas funciones `upsert_produccion_mes(cliente_id, anio, mes, m2_mes)` (distribuye m² por día con ponderación L-V:1.0/Sáb:0.6/Dom:0.0) y `obtener_produccion_para_periodo(cliente_id, desde, hasta, usar_promedio_historico)`.
- `scripts/seed_iberica.py` — `_sembrar_historico_60_dias` reescrita a resolución 5-min (288 muestras/día × 60 días × 12 CBTs = 207,360 total). Añadido checkpointing en `/tmp/seed_iberica_progress.json` con retry exponencial (hasta 5 intentos, backoff 2^n segundos). Verificación de migraciones antes de sembrar. `_sembrar_mediciones` base actualizada a 5-min (intervalo=5, n=2016).
- `calc/telemetria_costos.py` — nueva función `obtener_precio_unitario(cliente_id, anio, mes, historico_completo)` con soporte de cache pre-cargado para evitar N+1 queries.
- `web/app.py` — `kpis_paneles` restructurado a 10 KPIs: energeticos×4 (sin indice_utilizacion_pct), economicos×3 (sin ahorro_potencial_mxn; fuente_precio añadido a costo_unitario_mxn_kwh), produccion×3 (sin pct_costo_especifico; solo_en_rango: ["30d"] en el bloque). Nuevo endpoint `POST /clientes/<id>/telemetria/produccion` con validación de input y distribución por día.
- `tests/test_telemetria_kpis.py` — tests a-o: reemplazados test_e (→ precio_unitario con cache) y test_f (→ produccion_para_periodo con promedio histórico); actualizados test_g/h/k; añadidos test_l (solo_en_rango), test_m (POST distribución), test_n (POST validación), test_o (POST auth).

## [2.80.0] — 2026-08-05

### Añadido — Fase 2 D7-A v2: histórico 60 días, selección de fuente por rango, sparkline dinámico

- `calc/telemetria_kpis.py` — nueva función `determinar_periodo_anterior(rango, ahora)`: calcula (desde_ant, hasta_ant, etiqueta) desplazando 30 días atrás con la misma anchura del rango. Función `generar_sparkline` extendida con param `tipo='energia'|'potencia'|'factor_potencia'` (retrocompatible). `calcular_kpis_produccion` ahora calcula `pct_costo_especifico = (costo_esp / costo_total) × 100` en lugar de retornar None.
- `storage/repository.py` — nueva función `obtener_mediciones_para_rango(medidor_id, desde, hasta, rango)`: enruta a `mediciones_tiempo_real` para rango='24h' y a `mediciones_agregadas_15min` para '7d'/'30d', devuelve dicts homogeneizados con campo `timestamp` normalizado.
- `scripts/seed_iberica.py` — `_sembrar_historico_mes_anterior` (1 día) reemplazada por `_sembrar_historico_60_dias` (60 días × 96 muestras = 5,760 por CBT; idempotente: salta si >5,000 muestras; --forzar borra el rango completo). `_sembrar_produccion_diaria` ahora cubre 60 días.
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data`: fetch paralelo con `ThreadPoolExecutor(max_workers=2)` (periodo actual + anterior simultáneos); usa `determinar_periodo_anterior` para calcular ventana anterior; sparkline dinámico (24h→24 pts, 7d→7 pts, 30d→30 pts); `n_puntos_sparkline` añadido a `kpis_paneles.meta`; `periodo_anterior_etiqueta` usa la etiqueta calculada según el rango.
- `tests/test_telemetria_kpis.py` — 2 nuevos tests: `test_g_determinar_periodo_anterior` (verifica las tres variantes de rango), `test_h_obtener_mediciones_para_rango_elige_tabla` (verifica routing a tabla correcta y normalización de campos).

## [2.79.0] — 2026-08-05

### Añadido — Fase 2 D7-A: backend de KPIs de paneles de telemetría

- `storage/migrations/202608_produccion_diaria.sql` — nueva tabla `produccion_diaria (id, cliente_id, fecha, m2_producidos, created_at)` con UNIQUE(cliente_id, fecha) e índice por fecha. Requiere ejecución manual en Supabase.
- `calc/telemetria_kpis.py` — nuevo módulo con 6 funciones puras de cálculo: `calcular_kpis_energeticos` (energía trapezoidal, demanda pico/prom, FP ponderado por kW, índice utilización), `calcular_kpis_economicos` (costo total, unitario, % factura, ahorro potencial), `calcular_kpis_produccion` (consumo y costo específicos por m²), `atribuir_produccion_a_nodo` (m² proporcional al consumo), `calcular_baseline_movil` (energía del periodo histórico, fórmula provisional), `generar_sparkline` (reduce mediciones a N puntos por bucket temporal).
- `storage/repository.py` — nueva función `obtener_produccion_diaria(cliente_id, desde_fecha, hasta_fecha)`.
- `scripts/seed_iberica.py` — extendido con `_sembrar_produccion_diaria` (registros diarios con perfil L-V/Sáb/Dom, semilla determinista) y `_sembrar_historico_mes_anterior` (96 muestras por CBT del mismo día del mes anterior). Ambos bloques son idempotentes y respetan `--forzar`.
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data` extendido: nuevo bloque `kpis_paneles` con subclaves `energeticos` (5 KPIs), `economicos` (4 KPIs), `produccion` (4 KPIs) y `meta`. Cada KPI incluye `actual`, `anterior`, `delta_pct`, `sparkline_actual`, `sparkline_anterior` y flags de renderizado (`es_favorable_menor`, `aplica_a_nodo`, `oculto_en_nodo`, `es_gauge`).
- `tests/test_telemetria_kpis.py` — 9 nuevos tests: a-f unitarios (sin DB), g-i de integración contra el endpoint mockeado.

## [2.78.3] — 2026-08-05

### Fix — Fase 2 D6: desactiva click en nodos de transformador

- `web/static/js/dashboard-telemetria.js` — nueva función `_crearGrupoNodoVisual`: crea un `<g>` con hover (opacidad) pero sin listener de click y con `cursor:default`, sobreescribiendo el `cursor:pointer` de la clase `unifilar-nodo`. Los transformadores usan esta función en lugar de `_crearGrupoNodo`; acometida, SEs y CBTs conservan su comportamiento clickable.

## [2.78.2] — 2026-08-05

### Fix — Fase 2 D6: ampliar offset lateral de etiquetas de transformador

- `web/static/js/dashboard-telemetria.js` — offset horizontal de etiquetas del transformador aumentado de `cx + R_TX + 28` a `cx + R_TX + 44` (cx + 70 px), eliminando la superposición residual sobre el símbolo doble círculo. `MIN_SEP` ajustado de 200 a 220 px.

## [2.78.1] — 2026-08-05

### Fix — Fase 2 D6: kWh duplicado en líneas y colisión visual etiquetas Tx

- `web/static/js/dashboard-telemetria.js` — eliminado el `<text class="unifilar-valor-linea">` que dibujaba el kWh sobre cada línea de conexión del unifilar; el valor kWh ya aparece en el bloque de etiquetas laterales del nodo destino, por lo que era información duplicada.
- `web/static/js/dashboard-telemetria.js` — offset horizontal de etiquetas del transformador aumentado de `cx + R_TX + 12` a `cx + R_TX + 28` (cx + 54 px), eliminando la superposición visual sobre el segundo círculo del símbolo doble. `MIN_SEP` ajustado de 180 a 200 px para mantener la holgura entre transformadores adyacentes.

## [2.78.0] — 2026-08-04

### Refactorizado — Fase 2 D6: unifilar 4 niveles y etiquetas laterales

- `web/static/js/dashboard-telemetria.js` — nueva función `_agruparPorSE`: agrupa los transformadores hijo de la acometida por el prefijo `/^T-(\d+)/` y genera nodos SE virtuales con ID string `"grupo:SE-N"` (no existen en BD). Nueva función `_dibujarSE`: rectángulo 100×40 punteado, fondo azul claro, 2 líneas de texto (nombre SE y kWh del periodo).
- `web/static/js/dashboard-telemetria.js` — `_renderUnifilar` reescrito de 3 a 4 niveles: Acometida › SE › Transformador › CBT. Las SEs se distribuyen horizontalmente centradas sobre el grupo de Txs hijos; los Txs se distribuyen uniformemente. Constantes actualizadas: R_TX 28→26, MIN_SEP 220→180, NIVEL_H=100 (reemplaza NIVEL_H_TX=160 y NIVEL_H_CBT=160), PAD_Y 40→30.
- `web/static/js/dashboard-telemetria.js` — `_dibujarTransformador` actualizado: etiquetas (nombre corto, kVA, kWh) reubicadas a la derecha del símbolo doble círculo (text-anchor=start, x=cx+R_TX+12) eliminando el solape visual con las líneas de conexión.
- `web/static/js/dashboard-telemetria.js` — `fetchDatos`, `_handleClickNodo`, `setNodo` actualizados para manejar IDs virtuales (prefijo `"grupo:"`): no se envía `nodo_id` al backend para nodos SE; clic en SE muestra el agregado completo del árbol.
- `web/templates/telemetria/dashboard.html` — `#unifilar-wrapper` min-height 380→500 px para acomodar SVG de ~424 px.

## [2.77.0] — 2026-08-04

### Añadido/Refactorizado — Fase 2 D5: reestructuración completa de telemetría piloto

- `scripts/seed_iberica.py` — PLANTA_1 y PLANTA_2 refactorizadas: de N cargas inventadas por transformador a 1 CBT (Cuadro de Baja Tensión) por transformador. Planta 1: 6 CBTs (CBT-MMC1, CBT-Vent. Atomizador 1, CBT-Zona Atomizado 1, CBT-Zona Prensas, CBT-Zona Hornos, CBT-Serv. Auxiliares). Planta 2: 6 CBTs (CBT-MMC2, CBT-Vent. Atomizador 2, CBT-Zona Atomizado 2, CBT-Zona Prensas P2, CBT-Zona Hornos P2, CBT-Pulido y Líneas 7-8). Total: 12 CBTs, 8064 mediciones sintéticas (7d × 4/h).
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data`: fallback defensivo para el caso donde `hojas_ids_nodo` incluye IDs que no están en `todas_hojas_ids` (transformador sin cargas hijo). Los IDs faltantes se fetchan individualmente y se agregan a `mediciones_por_hoja` antes de la agregación.
- `web/static/js/dashboard-telemetria.js` — layout del unifilar completamente reescrito: se elimina la navegación por zoom semántico (nodoRaiz, vistaAcometida/vistaSE/vistaTx, grupos SE, breadcrumbs jerárquicos). El diagrama muestra SIEMPRE los 3 niveles completos: Acometida › Transformadores (fila) › CBT hijo (1:1). Click en cualquier nodo selecciona y actualiza KPIs/serie sin restructurar el árbol. Constantes: W_ACOM=220, R_TX=28, W_CBT=200×H_CBT=64, NIVEL_H_TX=160, NIVEL_H_CBT=160, MIN_SEP=220.
- `web/static/js/dashboard-telemetria.js` — nueva función `_dibujarCBT` (reemplaza `_dibujarCarga`): rectángulo 200×64 naranja con 3 líneas de texto (nombre CBT, potencia nominal, kWh). `_dibujarTransformador`: radio R_TX aumentado de 22 a 28. `_dibujarAcometida`: W_ACOM aumentado de 180 a 220.
- `web/templates/telemetria/dashboard.html` — `#unifilar-wrapper` min-height 280 → 380 px para acomodar el nuevo SVG de ~564 px.

## [2.76.3] — 2026-08-04

### Corregido — Fix integral D4: spinner, espacio SVG, texto de transformadores y energía en árbol

- `web/templates/telemetria/dashboard.html` — eliminado `#unifilar-loading` (div spinner 340 px que dominaba el viewport). El SVG permanece siempre visible; durante el primer fetch el wrapper muestra su fondo y el badge de cabecera indica actividad. Wrapper `min-height` 380 → 280 px. SVG `style` limpiado (sin `display:none`).
- `web/static/js/dashboard-telemetria.js` — `_mostrarLoading(visible)` simplificado: solo controla el badge de cabecera, sin lógica `esInicial`/`_primeraCarga`. Eliminadas las variables `_primeraCarga` y el parámetro `esInicial`. `fetchDatos` simplificado en consecuencia.
- `web/static/js/dashboard-telemetria.js` — alturas del SVG corregidas: cada fórmula tenía un `NIVEL_H` extra (140 px) sobre el contenido real. Nuevo: `vistaAcometida` 408 → 268 px, `vistaTx` 416 → 276 px, `vistaSE` 556 → 456 px (con margen para etiquetas bajo símbolo).
- `web/static/js/dashboard-telemetria.js` — `_dibujarTransformador`: etiquetas movidas de la derecha del símbolo (colisionaban con `MIN_SEP=210 px`) a debajo del símbolo, centradas (`text-anchor:middle`). Se parsea nombre corto `T-N.N` y potencia `N kVA` con regex; se filtra líneas vacías.
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data`: `mediciones_por_hoja` ahora se construye para **todas** las `carga_final` del árbol completo (`todas_hojas_ids`), no solo las del nodo seleccionado. `_energia_nodo` puede así calcular kWh correctos para todos los nodos del sunburst en cualquier vista. KPIs, serie temporal y comparativa siguen filtrando solo las hojas del nodo seleccionado (`hojas_ids_nodo`).
- `web/app.py` — `_arbol_sunburst_con_costo` incluye ahora `potencia_nominal_kw` en cada nodo (estaba ausente; JS recibía `undefined`).
- `tests/test_dashboard_telemetria.py` — test `test_telemetria_data_nodo_carga_final_sin_agregacion` actualizado: la nueva lógica consulta todos los medidores `carga_final` del árbol para el periodo actual; el test verifica que ambos medidores (3 y 4) son consultados y que solo medidores válidos del árbol aparecen en las llamadas.

## [2.76.2] — 2026-08-04

### Corregido — Spinner residual, layout comprimido e indicador de carga en cabecera

- `web/static/js/dashboard-telemetria.js` — `fetchDatos` reescrito como `async/await`: captura una referencia local `controller` al AbortController antes del primer `await`, eliminando el bug de cierre donde el `.finally()` leía `_abort` del módulo (ya reemplazado por un nuevo controlador). El guard en `finally` ahora comprueba `controller.signal.aborted` (este fetch específico) en lugar del módulo compartido. Variable `_primeraCarga` nueva: controla si el spinner grande (`#unifilar-loading`) se muestra u oculta, o solo el badge de cabecera.
- `web/static/js/dashboard-telemetria.js` — `_mostrarLoading(visible, esInicial=false)`: cuando `esInicial=false` (cambios de rango o nodo sobre un SVG ya renderizado), solo hace toggle del badge de cabecera; el SVG y el spinner grande no se tocan. Elimina el parpadeo del diagrama en cargas incrementales.
- `web/templates/telemetria/dashboard.html` — Badge `#header-loading-badge` en la cabecera junto a `#ultima-actualizacion`: pequeño spinner `spinner-border-sm` con texto "Cargando…" visible durante todos los fetches. `#unifilar-wrapper` min-height 520 → 380 px; `#unifilar-loading` y `#unifilarSvg` min-height 480 → 340 px. Canvas `#serieTemporalChart` height 240 → 180 px. Libera el fold para que los 6 KPI cards y la gráfica temporal sean visibles sin scroll en viewports estándar.
- `web/static/css/telemetria.css` — `.kpi-panel .kpi-card` padding vertical `.375rem`; `.kpi-panel .kpi-value` font-size `1.35rem`. Las 6 tarjetas caben en la columna derecha sin scroll interno.

## [2.76.1] — 2026-08-03

### Corregido — Spinner perpetuo en dashboard de telemetría

- `web/static/js/dashboard-telemetria.js` — `fetchDatos()` refactorizado: `_mostrarLoading(false)` movido de los callbacks `.then()` y `.catch()` a un bloque `.finally()` con guard `!_abort.signal.aborted`. La ruta `AbortError` retornaba antes sin ocultar el spinner, dejándolo visible indefinidamente tras cualquier fetch cancelado.

## [2.76.0] — 2026-08-04

### Añadido — Fase 2 D4: unifilar SVG interactivo reemplaza sunburst

- `web/static/js/dashboard-telemetria.js` — `_renderSunburst` eliminado; nuevo `_renderUnifilar` dibuja SVG puro top-down (sin D3 ni librerías): acometidas (rect), SEs agrupadas (rect punteado), transformadores (doble círculo), cargas ficticias (rect naranja). Navegación por zoom semántico: click en SE despliega transformadores, click en Tx despliega cargas, click en carga actualiza KPIs sin cambiar raíz. Hover resalta rama. Líneas ortogonales coloreadas por % de carga nominal (normal/amarillo/rojo) con etiqueta kWh.
- `web/templates/telemetria/dashboard.html` — layout reorganizado: unifilar ocupa la fila superior, gráfica temporal y panel KPIs en fila inferior (70/30). Estado vacío y breadcrumbs conservados.
- `web/static/css/telemetria.css` — CSS nuevo para clases del unifilar (hover, highlight, líneas coloreadas, cargas ficticias).

## [2.75.0] — 2026-08-03

### Añadido — Fase 2 D3: costo en pesos y comparativa mes anterior en telemetría

- `calc/telemetria_costos.py` — módulo nuevo: `obtener_precio_unitario_mxn_kwh` (CFE o PPA, fallback a mes anterior o últimas 12 facturas), `calcular_costo_periodo` (wrapper con `_mes_principal`).
- `storage/repository.py` — 4 funciones nuevas: `obtener_factura_cfe_cliente_mes`, `obtener_ultimas_facturas_cfe`, `obtener_factura_ppa_cliente_mes`, `obtener_ultimas_facturas_ppa`.
- `web/app.py` — endpoint `cliente_dashboard_telemetria_data` extendido: KPIs + `costo_mxn`, `precio_fuente`, `precio_mes_referencia`; bloque `comparativa_mes_anterior` (rango desplazado -30 días, `disponible` si ≥50% de muestras); `arbol_sunburst` ahora incluye `costo_mxn` por nodo.
- `web/templates/telemetria/dashboard.html` — 2 tarjetas KPI nuevas: "Costo en el periodo" (MXN) y "vs. mes anterior" (Δ%).
- `web/static/js/dashboard-telemetria.js` — `_renderKPIs` actualizada (costo + hint de fuente); `_renderComparativa` nueva (delta coloreado verde/rojo); `_renderTodo` llama a ambas; tooltip sunburst muestra kWh + MXN por segmento; `_costosPorId` mapeo id→costo para tooltip.
- `tests/test_telemetria_costos.py` — 7 tests: precio CFE mes exacto, fallback anterior, sin facturas, PPA, cálculo de costo, claves JSON del endpoint, aritmética de delta.

## [2.74.1] — 2026-08-03

### Corregido — CDN de Chart.js faltante en template de telemetría

- `web/templates/telemetria/dashboard.html` — agregado `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js">` antes del módulo propio en `{% block scripts %}`. Sin este CDN, el IIFE de `dashboard-telemetria.js` lanzaba "Chart is not defined" al intentar crear los gráficos de sunburst y serie temporal.

## [2.74.0] — 2026-08-03

### Añadido — Fase 2 D2: dashboard de telemetría para cliente

- `web/app.py` — dos rutas nuevas dentro de `create_app()`:
  - `GET /clientes/<id>/dashboard/telemetria` — vista HTML; guarda en sesión `nav_active="telemetria_cliente"`.
  - `GET /clientes/<id>/dashboard/telemetria/data` — endpoint JSON con sunburst, serie temporal y KPIs.
  - Ambas: respetan `FASE2_HABILITADA` (404 si False), usan `_verificar_cliente_activo` para auth.
- `web/templates/clientes/_base.html` — enlace "Telemetría (Beta)" en sidebar, visible cuando `fase2_habilitada`, usa `nav_active == 'telemetria_cliente'` para evitar colisión con el link admin.
- `web/templates/telemetria/dashboard.html` — template nuevo; extiende `clientes/_base.html`; muestra estado vacío si no hay medidores; breadcrumbs dinámicos, sunburst-wrapper, panel KPIs y gráfica de serie temporal.
- `web/static/js/dashboard-telemetria.js` — módulo IIFE nuevo; Chart.js doughnut multi-anillo (acometida / transformadores / cargas); colores por rama con variantes; click en segmento navega al nodo; gráfica de serie temporal adaptada al rango; breadcrumbs interactivos; manejo de errores con banner + reintentar.
- `tests/test_dashboard_telemetria.py` — 8 tests: acceso por rol, flag FASE2, estructura JSON, consistencia de energía sunburst, aislamiento de carga_final, estado vacío.

## [2.73.0] — 2026-08-03

### Añadido — Fase 2 D1: modelo jerárquico de medidores, perfiles por tipo de carga y seed masivo

- `storage/migrations/202607_telemetria_jerarquia.sql` — DDL: columnas `medidor_padre_id` (FK self-referencial), `tipo_carga` (TEXT), `potencia_nominal_kw` (NUMERIC 10,2) en tabla `medidores`; índice `idx_medidores_padre`.
- `storage/repository.py` — 4 funciones nuevas para telemetría jerárquica:
  - `crear_medidor_jerarquico(cliente_id, nombre, tipo_medidor, tipo_carga, potencia_nominal_kw, padre_id)` → dict con `id`.
  - `obtener_arbol_medidores(cliente_id)` → lista plana de medidores con campo `nivel` calculado en Python (0=raíz).
  - `obtener_hijos(padre_id)` → lista directa de hijos.
  - `obtener_descendientes_ids(raiz_id)` → lista plana de IDs de todos los descendientes (BFS).
- `telemetria/seed.py` — `_fraccion_carga(tipo_carga, t)` con perfiles por tipo: `horno_tunel` (carga plana 0.75–0.90), `atomizador` (ciclo escalonado 30→50→60→70 min), `prensa` (turno 16h pico 0.85), default (sinusoidal industrial). `generar_mediciones_por_carga(medidor_id, tipo_carga, potencia_nominal_kw, voltaje_base, inicio, fin, intervalo_min)` genera lecturas sintéticas con voltaje, corriente, fp y potencia coherentes; RNG seeded por `medidor_id` para reproducibilidad.
- `scripts/seed_iberica.py` — script CLI idempotente (verifica por nombre+cliente_id, `--forzar` re-seed). Crea jerarquía para clientes 44 (Planta 1) y 45 (Planta 2): 2 acometidas MT 13.8 kV, 12 transformadores, 34 cargas finales; siembra 7 días × intervalos de 15 min por carga final.
- `tests/test_telemetria_jerarquia.py` — 11 tests: a–d (mocks repository), e–j (verificación de perfiles de carga). Todos pasan sin red.

## [2.72.1] — 2026-08-03

### Corregido — _primerasCarga no sobreescribe motores guardados en sesión

- `web/static/js/dashboard-modelado-chp.js`:
  - Bloque `_primerasCarga` dentro de `fetchModelado()` refactorizado: eliminada la llamada a `_inicializarMotores(data.params.motores_config)` que sobreescribía los motores ya restaurados por `aplicarSessionParams()`. Los motores solo se modifican desde `aplicarSessionParams()` al inicio o desde la UI.
  - `_primerasCarga = false` movido dentro del bloque `if (_primerasCarga)` (estaba fuera).
  - Bloque `_primerasCarga` conserva solo: poblar precio gas desde `cogen_defaults` (si el input vale 0) y poblar capacidad nominal (solo si `_sessionParams` no tenía motores propios).
  - Eliminados los 4 `console.log` de diagnóstico del commit anterior.

## [2.72.0] — 2026-08-03

### Añadido — Modelado CHP: persistencia de parámetros de cabecera entre sesiones

- SQL (ejecutar en Supabase): `ALTER TABLE clientes ADD COLUMN IF NOT EXISTS chp_session_params JSONB;`
- `storage/repository.py` — `get_chp_session_params(cliente_id)` y `save_chp_session_params(cliente_id, params)`: leen/escriben la columna JSONB con los 10 parámetros de sesión.
- `web/clientes.py` — POST `/clientes/<id>/dashboard/modelado-chp/params`: endpoint reescrito para guardar todos los parámetros (`motores`, `margen_kw`, `rendimiento_electrico`, `rendimiento_termico`, `precio_gas_gj`, `costo_om_kwh`, `precio_motor_usd_kw`, `autoconsumo_pct`, `deduccion_fiscal`, `anios_deduccion`) vía `save_chp_session_params`; sin restricción de rol (antes rechazaba a `usuario_normal`).
- `web/app.py` — `cliente_dashboard_modelado_chp`: carga `chp_session_params` y lo pasa al template.
- `web/templates/dashboard_modelado_chp.html` — root div: añadido `data-session-params="{{ chp_session_params | tojson }}"`.
- `web/static/js/dashboard-modelado-chp.js`:
  - Al inicializar: lee `root.dataset.sessionParams`; si hay motores guardados los usa (prioridad sobre `chp_motores_config` legacy); aplica el resto de inputs numéricos y el checkbox de deducción fiscal.
  - `guardarParams()` ampliado: envía los 10 parámetros al endpoint en cada "Recalcular".
- Tests: 484 unitarios pasan; fallos restantes son `ConnectError` a Supabase (sin red local, pre-existentes).

## [2.71.0] — 2026-08-03

### Añadido — usuario_normal puede acceder a ficha de cliente en modo solo lectura

- `web/templates/clientes/_base.html` — sidebar `usuario_normal`: cada cliente ahora aparece en un `<div class="d-flex">` con el link al dashboard (flex-grow-1) y un botón `<i class="bi bi-info-circle">` a la ficha; el botón de ficha llama `activarCliente(id, null)` y deja navegar (`return true`).
- `web/templates/clientes/ficha.html` — acceso de `usuario_normal` permitido (el `before_request` ya valida `_clientes_ids`); controles de edición y borrado envueltos en `{% if current_user_data.rol != 'usuario_normal' %}`:
  - "Acciones cliente" (Editar ficha + Borrar cliente)
  - "+ Nuevo contrato" en la cabecera de Contratos
  - "Borrar" en cada fila de contrato (el botón "Detalles" queda visible)
  - "Crear primer contrato" en el estado vacío de contratos
  - Acordeón "Suministro Calificado (PPA)" completo (solo formularios de edición, sin valor informativo solo lectura)
  - Sección "Configuración de gas (proyección)" y mediciones ya estaban protegidas con `rol in ('master_admin', 'admin')`.

## [2.70.1] — 2026-08-03

### Añadido — Auto-carga de medición cincominutal al entrar a dashboards contabilidad y cogeneración

- `web/app.py` — `cliente_dashboard_contabilidad`: mismo bloque `get_mediciones_por_cliente` + `session["medicion_activa_id"]` que cogeneración; inicializa la sesión con la primera medición disponible si no hay ninguna activa.
- `web/templates/clientes/_base.html` — radio buttons del sidebar: condición `loop.first and not session.get('medicion_activa_id')` añadida como fallback a `checked`; muestra el primero marcado cuando la sesión no tiene medición activa.
- `web/static/js/dashboard-cogeneracion.js` — bloque de auto-disparo mejorado: si hay un radio ya `checked` lo dispara; si no, marca el primero y dispara `change`. Sustituye el bloque anterior de v2.70.0.
- `web/templates/dashboard_contabilidad.html` — ya tenía `data-medicion-activa-id` en el root div; `dashboard-contabilidad.js` ya leía ese atributo para auto-carga (sin cambios necesarios).

## [2.70.0] — 2026-08-03

### Añadido — Auto-selección de primera medición cincominutal en dashboard de cogeneración

- `web/app.py` — `cliente_dashboard_cogeneracion`: llama `get_mediciones_por_cliente(cliente_id)` y guarda `session["medicion_activa_id"]` con el id de la primera medición disponible si la sesión no tiene ninguna activa. No modifica el dashboard de contabilidad ni el de Modelado CHP.
- `web/static/js/dashboard-cogeneracion.js` — al final del IIFE, después de `fetchData(false)`, añade bloque que selecciona el primer radio `.sidebar-medicion-radio` si ninguno está marcado y dispara su evento `change`. Solo actúa si no hay ninguno previamente marcado.

## [2.69.3] — 2026-08-03

### Corregido — Sincronización de cliente_activo_id para usuario_normal multi-cliente

- `web/auth.py` — `login()`: guarda `session["cliente_activo_id"]` al redirigir a `usuario_normal` post-login.
- `web/app.py` — `_verificar_cliente_activo()`: si el usuario es `usuario_normal` y el `cliente_id` solicitado está en sus `_clientes_ids`, actualiza `cliente_activo_id` en sesión en lugar de rechazar con flash; sin bypass de la verificación de perfil en BD.
- `web/clientes.py` — POST `/clientes/<cliente_id>/activar`: nuevo endpoint que actualiza `cliente_activo_id` y `_empresa_id` en sesión; retorna JSON `{"ok": true}`; bloquea si el rol es `usuario_normal` y el cliente no está en sus clientes asignados.
- `web/templates/clientes/_base.html` — sidebar `usuario_normal`: links de clientes usan `onclick="activarCliente(...)"` que llama al endpoint antes de navegar; función JS `activarCliente()` usa CSRF token del meta tag.

## [2.69.2] — 2026-08-03

### Corregido — Redirect post-login usuario_normal con múltiples clientes

- `web/auth.py` — `login()`: redirect post-login para `usuario_normal` usa `min(clientes_ids)` como destino por defecto (en vez del primero de la lista); añade fallback a `_empresa_id` de sesión si `_clientes_ids` está vacío; sincroniza `session["_empresa_id"]` al valor elegido antes de redirigir.
- `web/auth.py` — `set_user_session()`: añade `logger.debug` con `clientes_ids` y `empresa_id` guardados en sesión para diagnóstico.

## [2.69.1] — 2026-08-03

### Corregido — Modal "Crear usuario" soporta asignación múltiple de clientes

- `web/templates/admin/usuarios.html`: reemplazado `<select name="empresa_id">` en el modal de creación por checkboxes scrollables `name="cliente_ids"` (mismo patrón que `editar_usuario.html`). IDs de checkboxes con prefijo `cli-crear-` para evitar conflictos. Help text actualizado.
- `web/app.py` — POST `/admin/usuarios/crear`:
  - Lee `request.form.getlist("cliente_ids")` en lugar de `empresa_id` del form.
  - Calcula `empresa_id` legacy (solo cuando hay exactamente 1 cliente seleccionado).
  - Elimina validación que exigía `empresa_id` para `usuario_normal`.
  - Llama `set_clientes_de_usuario(user_id, cliente_ids)` tras crear el perfil, en try/except independiente con flash warning si falla.

## [2.69.0] — 2026-08-03

### Añadido — Asignación múltiple de clientes a usuario_normal

- `storage/migrations/202606_usuario_clientes.sql`: tabla `usuario_clientes` (PK user_id + cliente_id, FK a auth.users y clientes, dos índices).
- `storage/repository.py`:
  - `get_clientes_de_usuario(user_id)`: retorna clientes desde `usuario_clientes`; fallback a `empresa_id` de `user_profiles` para compatibilidad legacy.
  - `set_clientes_de_usuario(user_id, cliente_ids)`: reemplaza asignación completa (delete + insert).
  - `get_usuarios_de_cliente(cliente_id)`: lista de usuarios asignados a un cliente.
- `web/auth_permissions.py`: `usuario_puede_ver_empresa` y `filtrar_empresas_para_usuario` leen `clientes_ids` del dict de usuario; fallback a `empresa_id` si la lista está vacía.
- `web/auth.py`: `set_user_session()` carga y almacena `_clientes_ids` en sesión Flask para `usuario_normal`; `get_current_user()` incluye `clientes_ids` en el dict retornado; redirect post-login usa `clientes_ids[0]`.
- `web/app.py`:
  - `_inject_globals` context_processor inyecta `clientes_usuario` (list[dict]) para `usuario_normal`.
  - `admin_usuarios_editar`: GET pasa `clientes_asignados_ids`; POST lee `cliente_ids` (checkboxes multi), elimina validación de empresa_id obligatoria, llama a `set_clientes_de_usuario`, mantiene `empresa_id` legacy cuando hay exactamente 1 cliente.
- `web/templates/admin/editar_usuario.html`: sección "Clientes asignados" con checkboxes scrollables (max-height 300px), reemplaza select de empresa única.
- `web/templates/clientes/_base.html`: sidebar `usuario_normal` muestra lista dinámica de todos sus clientes asignados con enlace directo al dashboard.
- `tests/test_usuario_clientes.py` (nuevo): 16 tests cubriendo repositorio, permisos, acceso web y renderizado de template.

## [2.68.0] — 2026-06-03

### Añadido — Modelado CHP: Excel maestro con fórmulas nativas

- `reports/excel_modelado_chp.py` (nuevo): genera un `.xlsx` con 5 hojas.
  - **Parámetros**: inputs editables (fondo amarillo) + valores fijos de simulación (fondo gris) + tabla de motores. Celdas B4–B20 como referencias canónicas.
  - **KPIs Económicos**: todas las celdas calculadas son fórmulas Excel que referencian `'Parámetros'!$B$N` — inversión, payback, ahorro eléctrico, caldera, gas, O&M, CO₂ y CELs.
  - **Tabla Mensual**: datos históricos de `r.meses` con fila TOTAL usando `=SUM()`.
  - **Flujo 15 Años**: año 0 fijo (inversión negativa), años 1-15 con fórmulas que referencian la celda de ahorro neto de KPIs Económicos.
  - **Curva Mensual**: datos horarios de la simulación cincominutal (agregados por hora).
- `web/clientes.py`: endpoint `GET /clientes/<id>/dashboard/modelado-chp/excel` — reutiliza exactamente la lógica de `/cogen-data`; requiere rol admin o master_admin; retorna descarga directa.
- `web/templates/dashboard_modelado_chp.html`: botón "Descargar Excel" en cabecera, visible solo para admin/master_admin.
- `web/static/js/dashboard-modelado-chp.js`: función `actualizarLinkExcel()` — construye la URL con parámetros actuales y se llama al final de `fetchCogenData()`.
- `tests/reports/test_excel_modelado_chp.py` (nuevo): 23 tests TDD que cubren estructura de hojas, fórmulas, referencias canónicas a Parámetros, totales SUM, flujo y curva.

## [2.67.4] — 2026-05-29

### Corregido — Modelado CHP: distribución proporcional + límite 8 000 h estricto + versionado cache

- `calc/modelado_chp.py`:
  - `MODELADO_CHP_VERSION = "2"` — incrementar cuando cambie el algoritmo para invalidar cache anterior.
  - `_LIMITE_HORAS_MES` calculado con `round(8000/12, 6)` para comparación con precisión decimal.
  - Dispatch reemplazado por distribución proporcional a capacidad: cada motor disponible recibe `gen_total × (cap_motor / cap_total_disponible)`; se apaga si no alcanza el piso del 60 %. Eliminada ordenación mayor→menor.
  - Acumulación de horas con `round(..., 6)` por motor para evitar drift de punto flotante.
- `storage/repository.py`:
  - `get_modelado_chp()`: añade `.eq("calc_version", _MODELADO_CHP_VERSION)` — registros sin versión o con versión anterior no generan cache hit.
  - `save_modelado_chp()`: guarda `calc_version` en el payload.
- `storage/migrations/202606_modelado_chp_calc_version.sql` (nuevo): `ALTER TABLE modelado_chp ADD COLUMN IF NOT EXISTS calc_version TEXT DEFAULT '1'`.

Verificación: 2 motores × 1 006 kW → `horas_anuales_motor = 8000.0`, `cobertura ≈ 66.93 %`.

## [2.67.3] — 2026-05-28

### Corregido — Modelado CHP: horas por motor acotadas a 8 000 h + capacidad nominal desde motores_config

- `calc/modelado_chp.py` — `modelar_chp()`: horas anuales proyectadas por motor ahora se acotan a `_LIMITE_HORAS_ANUALES` (8 000 h); se expone `horas_por_motor` (dict motor_id → h) y `capacidad_total_kw` en kpis.
- `web/clientes.py` — endpoint `modelado-chp/cogen-data`: `capacidad_nominal_kw` en JSON calculada como suma de `capacidad_kw` de cada motor en `motores_config`; fallback a `r.capacidad_nominal_kw` si la lista está vacía.

## [2.67.2] — 2026-05-28

### Corregido — Modelado CHP: energia_limpia_pct + regeneración curva al cambiar parámetros

- `calc/modelado_chp.py` — `calcular_cogen_desde_modelado()`: hook `energia_limpia_pct` desde `getattr(r, 'cels_mwh_anual', None)` + `kpis_modelado["consumo_cliente_mes_kwh"]` (guard seguro, activa cuando CELs estén disponibles en `r`).
- `web/clientes.py` — endpoint `modelado-chp/cogen-data`:
  - Paso 6b añadido: tras calcular `cels_resultado`, computa `r.energia_limpia_pct = cels_mwh_anual × 1000 / kwh_total × 100`; fallback a `consumo_cliente_mes_kwh × 12` cuando `kwh_total_anual = 0`.
  - JSON `kpis` incluye ahora `energia_limpia_pct` (float o null).
- `web/clientes.py` — endpoint `modelado-chp/data`: reestructurado bloque cache+curva. Cache hit con curva perdida → regenera solo la curva sin re-upsert del header (modelado_id estable). Cache miss → calcula, upserta, guarda curva. Lógica más explícita y sin rama condicional compartida.

## [2.67.1] — 2026-05-28

### Corregido — Modelado CHP: CO₂, CELs y energía limpia poblados en frontend

- `web/static/js/dashboard-modelado-chp.js` — bloque añadido en `fetchCogenData().then()`:
  - Lee `data.co2` y puebla `#chp-kpi-co2-val` (reducción en t/año), `#chp-kpi-co2-sublabel` (% menos + árboles), y `#chp-seccion-co2` (visibilidad).
  - Llama `renderDonutComponentes` para donuts actual/proyectado si la función está disponible.
  - Lee `data.cels` y puebla `#chp-kpi-cels-val` (MWh/año) y `#chp-kpi-cels-eficiencia`.
  - Lee `data.kpis.energia_limpia_pct` y puebla `#chp-kpi-energia-limpia-val`.
  - Lee `data.kpis.capacidad_nominal_kw` (desde `calcular_cogen`, no del modelado) para actualizar `#chp-kpi-cap-nominal-val`.
  - Flujo 15 años: usa `flujo_anual_15_fiscal`/`flujo_acum_15_fiscal` cuando existen, con fallback a los arrays sin beneficio.
- `web/templates/dashboard_modelado_chp.html` — añadido `<script src="donut-componentes.js">` antes de `dashboard-modelado-chp.js` para que `renderDonutComponentes` esté disponible globalmente.

## [2.66.5] — 2026-05-28

### Corregido — Modelado CHP: unique constraint, paginación curva, regeneración si falta curva
- `storage/migrations/202605_modelado_chp_fix_unique.sql` (nuevo): DROP+ADD UNIQUE constraint incluyendo `capacidad_nominal_kw` → alinea la BD con el nuevo `on_conflict`.
- `storage/repository.py`:
  - `save_modelado_chp()`: `on_conflict` añade `capacidad_nominal_kw`; return con guarda `None`.
  - `get_modelado_chp()`: añadido `.eq("capacidad_nominal_kw", float(round(float(x), 2)))`.
  - `get_modelado_chp_curva()`: ya tenía paginación — sin cambio.
- `web/clientes.py` — endpoint `modelado-chp/data`: flujo reemplazado por cache-check + curva-check + delete anterior + regeneración; `precio_gas_gj` incluido en `cogen_defaults` en ambos paths (antes faltaba en el path de cálculo).

**SQL a ejecutar en Supabase antes del deploy:**
```sql
ALTER TABLE modelado_chp
  DROP CONSTRAINT IF EXISTS
    modelado_chp_medicion_id_num_motores_margen_kw_rendimiento__key;
ALTER TABLE modelado_chp
  ADD CONSTRAINT modelado_chp_unique_params
  UNIQUE (medicion_id, num_motores, margen_kw, rendimiento_electrico,
          costo_om_kwh, autoconsumo_pct, capacidad_nominal_kw);
```

## [2.66.4] — 2026-05-28

### Verificado — Modelado CHP: gen_neta usa capacidad_nominal total (sin cambio)
- `calc/modelado_chp.py` — `modelar_chp()`: verificado que ambos bloques son correctos.
  - Bloque `objetivo_neto_kw >= capacidad_nominal_kw`: usa `capacidad_nominal_kw` total ✓ (no cap_unitaria_kw).
  - Bloque `else`: `cap_activa = cap_unitaria_kw * motores_activos` ✓; cuando `motores_activos == num_motores`, `cap_activa == capacidad_nominal_kw`.
  - No se realizó ningún cambio al archivo.
- Diagnóstico CO2/CELs: el endpoint `cogen-data` sí devuelve `"co2"` y `"cels"` en el JSON. El problema es que `fetchCogenData()` en `dashboard-modelado-chp.js` no lee esos campos ni puebla `chp-kpi-co2-val`, `chp-kpi-cels-val`, `chp-kpi-energia-limpia-val`. Pendiente de implementar en próxima sesión.

## [2.66.3] — 2026-05-28

### Corregido — Modelado CHP: get_modelado_chp cast explícito, eliminar label inversión total
- `storage/repository.py` — `get_modelado_chp()`: cast explícito `float(round(float(x), n))` en los cuatro parámetros flotantes (margen_kw, rendimiento_electrico, costo_om_kwh, autoconsumo_pct). Eliminado `.eq("capacidad_nominal_kw", ...)` para alinear con el `on_conflict` del upsert (que no incluye esa columna).
- `web/templates/dashboard_modelado_chp.html`: eliminado `div#chp-inversion-total-label` bajo el input `param-inversion-usd`.
- `web/static/js/dashboard-modelado-chp.js`: eliminada función `actualizarInversionTotal()` y sus tres listeners. El total USD se calcula internamente en `getCogenParams()` sin mostrarse.

## [2.66.2] — 2026-05-28

### Cambiado — Modelado CHP: inversión USD/kW, kW/motor eliminado, layout sección cogen
- `web/templates/dashboard_modelado_chp.html`:
  - Eliminado div `param-cap-unitaria` (texto "kW/motor").
  - Label "Inversión (USD total)" → "Precio motor (USD/kW)", `value` 0 → 1400, `step` 1000 → 100. Añadido `id="chp-inversion-total-label"` con total calculado dinámico.
  - Bloque `extra_styles` añadido con `.section-label`, `.kpi-section-label`, `.kpi-card-b2`, `.cascada-wrap`. Enlace a `panel-flotante.css`.
  - `div#chp-cogen-section` reemplazado por layout idéntico al dashboard de cogeneración: Ingresos, Gastos, Ahorro Neto Anual (donut), Impacto Ambiental, Inversión y Retorno, Gráfica Mensual, Cascada, Flujo 15 años, Panel flotante tabla mensual.
  - Script `panel-flotante.js` añadido al bloque `scripts`.
- `web/static/js/dashboard-modelado-chp.js`:
  - Eliminada función `actualizarCapUnitaria()` y sus listeners.
  - Añadida `actualizarInversionTotal()` con listeners en `param-cap-nominal-input` y `param-inversion-usd`.
  - `getCogenParams()`: `inversion_usd = Math.round(capNominal × precioKw)`.
  - `fetchModelado()` primera carga: no sobreescribe `param-inversion-usd`; llama `actualizarInversionTotal()`.
  - `fetchCogenData()`: IDs actualizados a los nuevos (`chp-kpi-ah-elec-val`, `chp-kpi-total-ingresos-val`, `chp-kpi-total-gastos-val`, `chp-kpi-ahorro-neto-val`, `chp-seccion-inversion`, `chp-kpi-inversion-usd-val`, `chp-kpi-inversion-mxn-val`, `chp-kpi-payback-val`). Añadidos total ingresos y total gastos.
  - `_renderCascada()`: canvas `chp-chartCascada` → `chp-waterfallChart`, `maintainAspectRatio: false`.
  - `_renderFlujo()`: canvas `chp-chartFlujo` → `chp-chart15Year`.
  - Añadida `_renderDonutIngresos()` con canvas `chp-chartCompAhorroNeto` (donut Electricidad/Caldera).
  - `medicionActivaChanged`: destruye también `chpDonutChart`.

## [2.66.1] — 2026-05-28

### Corregido — Modelado CHP: precio gas, gráfica mensual cogeneración, cabecera visual
- `web/clientes.py` — endpoint `/data`: añadido `precio_gas_gj` a `cogen_defaults`. Se calcula como promedio ponderado de `costo_unitario_total_gj × consumo_total_gj` de las últimas 12 facturas de gas del cliente. Fallback: campo `precio_gas_manual_mxn_gj_pcs` del registro del cliente; si no existe, 0.
- `web/templates/dashboard_modelado_chp.html` — `#chp-cogen-section`: añadido `<canvas id="chp-chartCogen" height="100">` dentro de `#chp-graficaMensual-section`. Estilos de cabecera actualizados: título con `font-size:.70rem; letter-spacing:.08em; border-bottom`; todos los labels `text-transform:uppercase; font-size:.70rem; font-weight:600; color:#6c757d`.
- `web/static/js/dashboard-modelado-chp.js`:
  - `fetchModelado()` — condición para auto-poblar `param-precio-gas` ahora verifica `parseFloat(inputGas.value) === 0` antes de sobreescribir (no pisaba valor editado por usuario).
  - `chpRenderGraficaMensual(data)` — nueva función. Gráfica stacked bar + line en canvas `id="chp-chartCogen"`, instancia `chpCogenChart`. Misma paleta que `upsertCogenChart` en cogeneracion.js: azul-gris (Ah. Eléctrico), amarillo (Ah. Caldera), rojo (Costo Gas, invertido), morado (O&M, invertido), línea verde (Ahorro Neto). Usa `data.chart_labels`, `data.chart_ahorro_elec`, `data.chart_ahorro_caldera`, `data.chart_costo_gas`, `data.chart_om`, `data.chart_ebitda`.
  - `fetchCogenData()`: llama `chpRenderGraficaMensual(data)` y muestra `#chp-graficaMensual-section` antes de la cascada.
  - `medicionActivaChanged`: destruye también `chpCogenChart`.

## [2.66.0] — 2026-05-28

### Cambiado — Modelado CHP: cabecera reorganizada + gráfica cincominutal integrada
- `web/templates/dashboard_modelado_chp.html`: card de parámetros reescrita en dos filas lógicas. Fila 1 (operación): cap. nominal, núm. motores, margen seguridad, autoconsumo. Fila 2 (cogeneración): rend. eléctrico, rend. térmico, precio gas, costo O&M, inversión USD total. Factor utilización como `<input type="hidden" value="0.9132">`. Eliminado `param-precio-vapor`. Orden de secciones: parámetros → gráfica cincominutal (`chp-cincominutal-section`) → KPIs modelado → sección cogen → tabla diaria.
- `web/templates/dashboard_modelado_chp.html`: gráfica (`id="chp-grafica-section"`) reemplazada por `id="chp-cincominutal-section"` con título "Perfil de demanda cincominutal" y subtítulo con rango de fechas. Usa `style="display:none"` gestionado vía JS.
- `web/static/js/dashboard-modelado-chp.js`: `actualizarCapUnitaria()` usa `Math.round` + `toLocaleString("es-MX")`; listeners añadidos al inicio del IIFE. En `fetchModelado()`: primera carga auto-pobla `param-inversion-usd = Math.round(capNom × 1400)` y `param-precio-gas` desde `data.cogen_defaults.precio_gas_gj` si existe. `getCogenParams()` elimina `precio_vapor`; `factor_utilizacion` lee valor decimal directo del hidden (sin dividir por 100). `fetchCurva()` muestra `chp-cincominutal-section` vía `style.display`. `medicionActivaChanged` destruye los tres charts en una sola expresión.

## [2.65.1] — 2026-05-28

### Corregido — save_modelado_chp: upsert + cast explícito en búsqueda
- `storage/repository.py` — `save_modelado_chp()`: reemplazado `.insert()` por `.upsert(..., on_conflict="medicion_id,num_motores,margen_kw,rendimiento_electrico,costo_om_kwh,autoconsumo_pct")`. Elimina error 23505 cuando `get_modelado_chp()` no encuentra el registro existente por desajuste de tipos.
- `storage/repository.py` — `get_modelado_chp()`: cast explícito en parámetros de búsqueda: `int(medicion_id)`, `int(num_motores)`, `float(round(margen_kw, 2))`, `float(round(rendimiento_electrico, 4))`, `float(round(costo_om_kwh, 6))`, `float(round(autoconsumo_pct, 4))`. Garantiza coincidencia de tipo con los valores almacenados en Supabase.

## [2.65.0] — 2026-05-28

### Añadido — Frontend Modelado CHP: gráfica horaria, parámetros cogen, sección cogeneración completa
- `web/static/js/dashboard-modelado-chp.js`:
  - `agregarPorHora(ts_arr, demanda_arr, gen_arr)` — agrega series de 5 min a promedios horarios por cubo `ts.slice(0,13)`. Usado exclusivamente para la gráfica; tabla diaria y encadenamiento siguen usando datos originales 5-min.
  - `getCogenParams()` — lee 5 nuevos inputs del header: `param-rend-termico` (%, /100), `param-precio-gas`, `param-precio-vapor`, `param-inversion-usd`, `param-factor-util` (%, /100).
  - `fetchCogenData(modeladoId)` — fetch a `/cogen-data`; popula KPIs (`chp-kpi-*`), muestra/oculta cards de inversión y payback, llama `_renderCascada()`, `_renderFlujo()`, `_renderTablaMensual()`.
  - `_renderCascada()` — gráfica horizontal bar (Chart.js) con los 5 componentes del ahorro neto; colores rojo/azul según signo.
  - `_renderFlujo(flujo_anual, flujo_acum)` — gráfica bar+line flujo 15 años usando arrays pre-calculados del endpoint (`flujo_anual_15`, `flujo_acum_15`).
  - `_renderTablaMensual(filas)` — tabla mensual con fila de totales calculada en JS; campos: `ahorro_electricidad_mxn`, `ahorro_caldera_mxn`, `costo_gas_cogen_mxn`, `gasto_om_mes_mxn`, `ebitda_mes_mxn`.
  - `fetchModelado()` popula `param-rend-termico` desde `data.cogen_defaults.rendimiento_termico` en primera carga; oculta sección cogen al recalcular.
  - Cadena de carga: `fetchModelado → fetchCurva → fetchCogenData`.
  - `medicionActivaChanged` destruye también `chpCascadaChart` y `chpFlujoChart`.
- `web/templates/dashboard_modelado_chp.html`:
  - Segunda fila de parámetros (con `<hr>` separador): 5 nuevos inputs (rend. térmico, precio gas, precio vapor, inversión USD/kW, factor utilización).
  - Sección `#chp-cogen-section` (oculta por defecto): spinner cogen, banner de error cogen, 7 KPI cards (ahorro eléctrico, ahorro caldera, costo gas, O&M, ahorro neto, inversión, payback), canvas `#chp-chartCascada`, canvas `#chp-chartFlujo`, acordeón con tabla mensual `#chp-tbody-tabla-mensual`.

## [2.64.0] — 2026-05-28

### Añadido — Backend cogeneración desde modelado CHP
- `calc/modelado_chp.py` — `calcular_cogen_desde_modelado()`: wrapper que adapta `kpis_modelado["cobertura_pct"]` como `CoGenParams.cobertura_electrica` y llama a `calcular_cogen()` sin modificarlo. Acepta `rendimiento_electrico`, `rendimiento_termico`, `eficiencia_caldera`, `cfe_invoices`, `gas_invoices`, `tipo_cambio`, `factor_emision_elec/gas`. Retorna `CoGenResultado`.
- `storage/repository.py` — `get_modelado_chp_by_id(modelado_id)`: lookup de cabecera por PK.
- `web/clientes.py` — endpoint `GET .../dashboard/modelado-chp/cogen-data`: obtiene cabecera del modelado por `modelado_id`; carga últimas 12 facturas CFE y gas; lee config global (tipo_cambio, factores emisión); llama `calcular_cogen_desde_modelado`; calcula CELs, CO₂, flujo 15 años, payback; retorna JSON compatible con `/cogeneracion/data` más campo `kpis_modelado` con los KPIs del CHP. `rendimiento_termico` y `eficiencia_caldera` llegan por QS con defaults 0.25 y 0.85.
- `web/clientes.py` — endpoint `/data`: añade campo `cogen_defaults` (`rendimiento_termico`, `eficiencia_caldera`) en ambos paths de respuesta (cache hit y cache miss).
- Imports añadidos en `clientes.py`: `get_ultimas_gas_invoices`, `get_modelado_chp_by_id`.

## [2.63.1] — 2026-05-28

### Corregido — Modelado CHP: capacidad nominal editable, proyección anual por cobertura
- `calc/modelado_chp.py`: parámetro renombrado `consumo_gas_mes_kwh` → `consumo_anual_kwh` (consumo real anual de facturas). Sección de cálculos finales reescrita: `gen_neta_mes_kwh` calculada desde la curva (suma `gen_neta_kw × 5/60`); `horas_mes_motor` como intervalos activos × `_INTERVALO_H`; `cap_promedio_kw` restringida a `capacidad_nominal_kw`; proyección anual via `consumo_anual_kwh × cobertura_pct` en lugar de `× 12`.
- `storage/repository.py`: `get_modelado_chp()` acepta y filtra por `capacidad_nominal_kw`; `save_modelado_chp()` incluye `capacidad_nominal_kw` en el payload.
- `storage/migrations/202605_modelado_chp.sql`: `ALTER TABLE modelado_chp ADD COLUMN IF NOT EXISTS capacidad_nominal_kw NUMERIC(10,2)`; UNIQUE constraint actualizado para incluir `capacidad_nominal_kw`.
- `web/clientes.py` — endpoint `modelado_chp_data`: calcula `consumo_anual_kwh` sumando las últimas 12 facturas CFE (periodos kWh) o PPA (`consumo_kwh`); obtiene `capacidad_nominal_kw` desde query param o `_capacidad_nominal_kw(cfe_inv)` como fallback; pasa ambos a `modelar_chp()` y los expone en `params` de la respuesta JSON.
- `web/static/js/dashboard-modelado-chp.js`: `getParams()` incluye `capacidad_nominal_kw` desde nuevo input; helper `_actualizarCapUnitaria()` recalcula kW/motor en tiempo real; input auto-poblado del backend en primera carga (o al cambiar medición); `kpi-consumo-cliente` muestra `consumo_anual_kwh` de facturas (no `consumo_cliente_mes_kwh`); listeners en `param-cap-nominal-input` y `param-num-motores`.
- `web/templates/dashboard_modelado_chp.html`: nota estática de capacidad nominal reemplazada por `<input id="param-cap-nominal-input">` editable (step=10, placeholder="auto") con `<span id="param-cap-unitaria">` debajo; etiqueta KPI renombrada a "Consumo anual (facturas)".

## [2.63.0] — 2026-05-28

### Añadido — Frontend completo del dashboard Modelado CHP
- `web/templates/dashboard_modelado_chp.html`: reemplazado template mínimo por dashboard completo — cabecera con logo, card de parámetros (6 inputs inline: num_motores, margen_kw, rendimiento_electrico, costo_om_kwh, autoconsumo_pct + botón Recalcular), spinner inicial, banner de error, 8 cards de KPIs en 2 filas, canvas `#chartCHP` con leyenda manual, tabla de resumen diario. `data-*` attrs para el JS.
- `web/static/js/dashboard-modelado-chp.js`: IIFE completo — `getParams()` lee los 5 inputs con conversiones (%→fracción); `fetchModelado()` construye query string, fetch con AbortController (timeout 60 s), actualiza cap-nominal/cap-unitaria y los 8 KPIs formateados (`toLocaleString es-MX`), llama `fetchCurva`; `fetchCurva(modeladoId)` fetch del endpoint curva, construye Chart.js `type:"line"` con eje X `type:"time"` via chartjs-adapter-date-fns (dos datasets: verde demanda real, azul generación modelada, `pointRadius:0`), subtítulo de rango de fechas, tabla diaria agrupada por día con demanda media, gen_neta media, cobertura % y horas activas; `guardarParams()` POST fire-and-forget con CSRF; listener `btn-recalcular`; listener `medicionActivaChanged` con destroy de chart; carga inicial `fetchModelado()`.
- `web/templates/clientes/editar.html`: 2 nuevos campos en la sección de parámetros técnicos — `chp_num_motores` (select 1–4) y `chp_margen_kw` (input number, step=10) — guardados vía el POST existente de editar cliente.

## [2.62.0] — 2026-05-28

### Añadido — Backend completo del dashboard Modelado CHP
- `storage/migrations/202605_modelado_chp.sql`: dos nuevos campos en `clientes` (`chp_num_motores SMALLINT`, `chp_margen_kw NUMERIC`) + tablas `modelado_chp` (cache de KPIs con UNIQUE por parámetros) y `modelado_chp_curva` (curva intervalo a intervalo de 5 min) + 4 índices. Solo generar; no se auto-ejecuta.
- `calc/modelado_chp.py`: motor de simulación CHP sobre serie cincominutal. Algoritmo greedy intervalo a intervalo: calcula `motores_activos` respetando carga mínima del 60 %, limit de 8 000 h anuales por motor y margen de seguridad. KPIs: `gen_neta_anual_kwh`, `gen_bruta_anual_kwh`, `cobertura_pct`, `consumo_gas_anual_gj`, `costo_om_anual_mxn`, `horas_anuales_motor`, `capacidad_promedio_kw`. Retorna curva completa para graficación.
- `storage/repository.py`: 6 funciones nuevas — `get_cliente_chp_params`, `update_cliente_chp_params`, `get_modelado_chp` (cache lookup por UNIQUE params), `save_modelado_chp` (insert cabecera), `save_modelado_chp_curva` (batch 1 000), `get_modelado_chp_curva` (paginación 1 000 igual que medición datos).
- `web/clientes.py`: imports de las 6 funciones nuevas; guardado de `chp_num_motores`/`chp_margen_kw` en el POST de editar cliente; 3 endpoints nuevos: `GET .../modelado-chp/data` (calcula o sirve cache + kpis), `GET .../modelado-chp/curva/<modelado_id>` (ts/demanda/gen arrays), `POST .../modelado-chp/params` (guarda params, solo admin+).
- `web/app.py`: imports `get_mediciones_por_cliente` y `get_cliente_chp_params`; ruta `GET /clientes/<id>/dashboard/modelado-chp` → `cliente_dashboard_modelado_chp` con verificación cliente activo, redirect si sin mediciones, plantilla `dashboard_modelado_chp.html`.
- `web/templates/clientes/_base.html`: enlace "Modelado CHP" en sidebar después de "Proyecto Cogeneración", visible solo cuando `mediciones_sidebar` no está vacío.
- `web/templates/dashboard_modelado_chp.html`: plantilla mínima con cards de estado (medición activa, num_motores, margen_kw) y `data-*` attrs para el JS del frontend (entrega siguiente).

## [2.61.0] — 2026-05-27

### Añadido — Gráfica de costo mensual por componente (dashboard Contabilidad)
- `web/app.py` (endpoint `desglose-costo-total`): nueva clave `mensual` en la respuesta JSON — lista de objetos `{mes, energia, capacidad, distribucion, otros, total, kwh, costo_unit}` por factura CFE seleccionada, ordenada cronológicamente. Las claves existentes `lineas` y `total` no se modificaron.
- `web/templates/dashboard_contabilidad.html`: bloque `#bloque-costo-mensual-componente` con `<canvas id="chartCostoMensualComponente">` añadido dentro del desplegable "Ver detalle".
- `web/static/js/dashboard-contabilidad.js`: variable `costoMensualComponenteChart`, función `upsertChartCostoMensualComponente(mensual)` — barras apiladas (Energía, Capacidad, Distribución, Otros Servicios) con línea $/kWh en eje derecho; patrón upsert idéntico a `upsertChartGasCostos`; colores donut `#0D3B66 / #1F6FB2 / #4A9FD8 / #A8D0E6` y `COLOR_LINEA`. `renderDetalleCostoTotal` llama la función cuando `data.mensual` está presente.
- `tests/test_dashboard_2d.py`: `test_desglose_costo_total_incluye_mensual` — verifica presencia de clave `mensual`, los 8 sub-campos, valores exactos (energia=10000, capacidad=4000, distribucion=3500, otros=2000, total=19500, kwh=17000) y `costo_unit ≈ 19500/17000`.

## [2.60.1] — 2026-05-28

### Corregido — Generador de telemetría desalineado del esquema real
- `telemetria/seed.py`: reescrito para producir EXACTAMENTE las 18 columnas de `mediciones_tiempo_real` (`potencia_activa_kw`, `potencia_reactiva_kvar`, `potencia_aparente_kva`, `factor_potencia`, `energia_activa_importada_kwh`, `energia_activa_exportada_kwh`, `energia_reactiva_importada_kvarh`, `energia_reactiva_exportada_kvarh`, `voltaje_l1_v/l2/l3`, `corriente_l1_a/l2/l3`, `frecuencia_hz`, `secuencia_fases`). Eliminadas las 30+ columnas ficticias previas (`kw_total`, `v_an`, `pf_total`, etc.) que causaban el PGRST204 en producción.
- `web/templates/telemetria/medidor.html`: referencias de columna actualizadas (`kw_total` → `potencia_activa_kw`, `pf_total` → `factor_potencia`, `v_an` → `voltaje_l1_v`, `i_a` → `corriente_l1_a`).
- `tests/test_telemetria_vista.py`: test e reforzado — verifica que las claves del dict sean exactamente el conjunto del esquema real (ni de más ni de menos), rangos fp/Hz/V, y monotonicidad del acumulador `energia_activa_importada_kwh`. 7/7 passed.

## [2.60.0] — 2026-05-27

### Añadido — Fase 2: Vista de telemetría solo lectura (Entrega B1)
- `telemetria/seed.py`: generador de mediciones sintéticas (`generar_mediciones_sinteticas`) — 96 lecturas × 15 min con perfil industrial realista (kW senoidal día/noche, V ≈ 13 800 V ±1 %, fp 0.88–0.97, Hz 60 ±0.05, acumuladores kwh/kvarh monótonos). Reutilizable desde rutas web y CLI.
- `web/app.py`: tres rutas de telemetría bajo `/admin/telemetria`, verificación manual (`get_current_user()` + flag `FASE2_HABILITADA`), sin decoradores. `telemetria_index` lista clientes/medidores. `telemetria_medidor` muestra últimas 200 mediciones de 24 h. `telemetria_sembrar` (POST) genera y persiste las 96 lecturas sintéticas vía `insertar_mediciones_batch`.
- `web/templates/telemetria/index.html`: selector de cliente + tabla de medidores con enlace a detalle.
- `web/templates/telemetria/medidor.html`: cabecera del medidor, botón "Sembrar datos de prueba (24 h)" (solo master_admin, con csrf_token), tabla de las últimas 200 mediciones (timestamp, kW, FP, V A-N, I A, Hz).
- `web/templates/clientes/_base.html`: reemplazado placeholder de fase 2 por enlace real `telemetria_index` en sidebar, visible solo si `fase2_habilitada` y `master_admin`.
- `tests/test_telemetria_vista.py`: 7 tests (a–f) — 404 sin flag, redirect para no-master_admin, 200 para master_admin, redirect en medidor inexistente, sembrado captura 96 mediciones con rangos validados, redirect para no-master_admin en POST sembrar. 7/7 passed.

### Corregido
- `web/app.py`: `abort` añadido al import de Flask (faltaba para las rutas nuevas).

## [2.59.1] — 2026-05-27

### Corregido — Alineación telemetría fase 2 con BD aplicada
- `storage/repository.py`: renombrada función `obtener_medidores_por_empresa(empresa_id)` → `obtener_medidores_por_cliente(cliente_id)`; parámetro y clave de payload `empresa_id` → `cliente_id` en `crear_medidor` y el filtro `.eq()` correspondiente. La BD usa `cliente_id INTEGER REFERENCES clientes(id)`, no `empresa_id`.
- `storage/migrations/202606_telemetria_fase2.sql`: reescrito para reflejar exactamente el SQL aplicado — `cliente_id` (no `empresa_id`), `creado_en` (no `created_at`), índice `idx_medidores_cliente`, PK de `mediciones_tiempo_real` = `(medidor_id, timestamp)` (sin columna `id BIGSERIAL`), columna `secuencia_fases TEXT`, ventana de agregación 30 minutos. Bloque pg_cron movido a comentario con instrucción de activación manual desde el panel de Supabase.
- `tests/test_repository_mediciones.py`: fixture `_MEDIDOR` actualizada (`empresa_id` → `cliente_id`); tests `test_obtener_medidores_por_empresa_*` renombrados a `test_obtener_medidores_por_cliente_*` y actualizados para llamar a la función renombrada. 12/12 passed.

## [2.59.0] — 2026-05-27

### Añadido — Fase 2: Capa de datos de telemetría (Entrega A)
- `storage/migrations/202606_telemetria_fase2.sql`: tres tablas (`medidores`, `mediciones_tiempo_real`, `mediciones_agregadas_15min`) + índices + función PL/pgSQL `agregar_mediciones_15min()` + job pg_cron `*/15 * * * *`. PostgreSQL nativo sin TimescaleDB; diseño migrable a hypertable. FK `medidores.empresa_id → clientes(id)`.
- `storage/repository.py`: 7 nuevas funciones — `crear_medidor`, `obtener_medidores_por_empresa`, `obtener_medidor`, `insertar_medicion`, `insertar_mediciones_batch` (chunks de 1000), `obtener_mediciones_recientes`, `obtener_agregados_15min`. Todas las lecturas incluyen `.limit(20000)` explícito.
- `tests/test_repository_mediciones.py`: 12 tests (12/12 passed) que cubren los 8 casos del spec (a–h): inserción y retorno con id, filtro por empresa, retorno None, set completo de variables Acuvim II, batch con división en chunks, rangos de fecha con `.limit(20000)`, y propagación de error FK.

## [2.48.0] — 2026-05-27

### Añadido
- `storage/repository.py`: nueva función `update_medicion(medicion_id, campos)` para PATCH.
- `web/clientes.py`: endpoint `PATCH/DELETE /<cliente_id>/mediciones/<medicion_id>` — actualiza campos editables (nombre, anio, mes) o borra con respuesta JSON. Endpoint `POST /<cliente_id>/mediciones/borrar-lote` — borra lista de ids en un solo request.
- `tests/test_mediciones.py`: 15 tests nuevos que cubren PATCH (nombre, mes/año, validación de rangos, campos vacíos, autorización, cliente incorrecto), DELETE (ok, no autorizado, no encontrado) y borrar-lote (ok, ids vacíos, no autorizado, mediciones ajenas).

### Corregido / Cambiado
- `web/static/js/dashboard-contabilidad.js`: helper `_fmtFechaEs()` convierte fechas ISO a "DD MMM YYYY" en español con meses en mayúsculas (ENE, FEB…). Subtítulo de la gráfica cincominutal pasa de "2026-03-01 → 2026-03-31" a "01 MAR 2026 → 31 MAR 2026".
- `web/templates/clientes/_base.html`: eliminado enlace "Subir medición" del sidebar (la acción ya existe en la ficha del cliente).
- `web/templates/clientes/ficha.html`: sección Mediciones rediseñada — título "Mediciones" (sin "Cincominutal"); columna "Subido por" eliminada; nueva columna "Tipo" con badge; edición inline de nombre y mes/año (clic → input, Enter/blur → PATCH, Escape cancela, flash verde de confirmación); checkboxes por fila + "seleccionar todo" con barra de acciones y conteo; borrado individual y en bloque con modal de confirmación obligatoria; botones deshabilitados durante peticiones en curso.

## [2.47.2] — 2026-05-27

### Corregido
- `storage/repository.py`: `get_medicion_datos()` — reemplaza `.limit(20000)` por paginación `.range()` en bucle de 1,000 en 1,000. Necesario porque PostgREST tiene `max-rows=1000` en servidor que el cliente no puede anular. Verificado: tabla con 8,927 filas devuelve las 8,927 correctamente.

## [2.47.1] — 2026-05-27

### Corregido
- `storage/repository.py`: `get_medicion_datos()` ya tenía `.limit(20000)` desde fix anterior — confirmado sin cambio.
- `web/templates/dashboard_contabilidad.html`: añade `chartjs-adapter-date-fns@3.0.0` vía CDN (necesario para eje `type: "time"`).
- `web/static/js/dashboard-contabilidad.js`: gráfica cincominutal — eje X cambia a `type:"time"` con `unit:"day"` y `displayFormats:{day:"d"}`; dataset usa puntos `{ts,x,y}`; grid vertical por día con línea sutil; eje Y con `min:0` y grid horizontal; fondo blanco.

## [2.47.0] — 2026-05-27

### Corregido
- `web/static/js/dashboard-contabilidad.js`: gráfica de perfil de demanda cincominutal — eje X ahora muestra los 31 días del mes completo. Se reemplaza el eje con `autoSkip:false` (comprimía ~8,900 puntos en 4 ticks) por eje categórico con `labelsEjeX`: solo el primer intervalo de cada día lleva el número de día, el resto es `""`, y el callback devuelve la etiqueta directamente. Tooltip corregido para leer `data.ts[dataIndex]` en lugar de `label`.

## [2.58.0] — 2026-05-27

### Añadido
- `web/app.py`: variable de entorno `FASE2_HABILITADA` leída en `create_app()` y almacenada en `app.config["FASE2_HABILITADA"]`; context_processor `inject_fase2_flag` inyecta `fase2_habilitada` (bool) en todos los templates.
- `web/auth_permissions.py`: decorador `@require_master_admin_y_fase2` — devuelve 404 si la flag está apagada, 403 si el rol no es `master_admin`. Importa `abort` y `current_app`.
- `web/templates/clientes/_base.html`: bloque sidebar "Telemetría (Beta)" visible únicamente cuando `fase2_habilitada` y rol `master_admin`.
- `tests/test_fase2_aislamiento.py`: 9 tests de aislamiento (a–i) que cubren el decorador, el context_processor y la visibilidad del sidebar bajo distintas combinaciones de flag y rol.
- `.env.example`: entradas `SECRET_KEY` y `FASE2_HABILITADA=false`.

### Documentación
- `CLAUDE.md`: sección "Aislamiento de fase 2" en "Decisiones arquitectónicas establecidas".

## [2.57.0] — 2026-05-27

### Añadido
- `web/error_logger.py`: función `log_error(nivel, mensaje, exc, codigo_http)` que persiste eventos en la tabla `error_logs` de Supabase. Falla silenciosa (warning en log local) si la escritura en BD falla.
- `web/templates/error.html`: página de error genérica (extiende `_base.html`) para 403, 404 y 500, con botón "Volver al inicio".
- `web/templates/admin/errores.html`: vista `/admin/errores` con tabla paginada (50/página), filtros por nivel/email/ruta/fechas, badges por nivel, modal de traceback para errores 500.
- `storage/migrations/202605_error_logs.sql`: DDL de la tabla `error_logs` con índices y GRANTs a `service_role`.

### Cambiado
- `web/app.py`: `from web.error_logger import log_error` al nivel de módulo; handlers globales `@app.errorhandler` para 403, 404 y `Exception` (500); ruta `GET /admin/errores` restringida a `master_admin`.
- `web/templates/clientes/_base.html`: enlace "Registro de Errores" en sidebar, sección Administración, visible solo para `master_admin`.
- `web/clientes.py`: `from web.error_logger import log_error` al nivel de módulo; todos los `flash(..., "danger")` precedidos de `log_error("negocio", ...)` o `log_error("validacion", ...)` según criterio.

## [2.56.1] — 2026-05-27

### Cambiado
- Los 11 SVG de `web/static/img/sectores/` pasan de silueta rellena a estilo outline: `fill="none"`, `stroke="#1A1A1A"`, `stroke-width="3"`, `stroke-linejoin="round"`, `stroke-linecap="round"`. `manufactura` y `textil` eliminan sus `<mask>` y añaden un `<circle>` de contorno para el agujero central.

## [2.56.0] — 2026-05-27

### Añadido
- 11 archivos SVG en `web/static/img/sectores/`: hotelero, manufactura, alimentos-y-bebidas, quimico, textil, pesquero, forestal, ceramico, plasticos, metalurgico, otro. Iconos minimalistas B&N, viewBox 100×100, sin texto.
- Función `obtener_logo_cliente(cliente)` en `web/app.py`: devuelve `logo_url` personalizado si existe, o el SVG del sector correspondiente, o `otro.svg` como fallback.
- Context processor `_inject_logo_helper`: expone `obtener_logo_cliente` en todos los templates Jinja2.

### Cambiado
- `ficha.html`: logo siempre visible vía `obtener_logo_cliente(cliente)`; eliminado el bloque `{% if cliente.logo_url %}`.
- `dashboard.html`, `dashboard_cogeneracion.html`, `dashboard_contabilidad.html`: eliminados los bloques condicionales `{% if logo_url %}`/`{% else %}`, ya que siempre hay un logo (personalizado o de sector).
- Rutas `cliente_dashboard_contabilidad` y `cliente_dashboard_cogeneracion` en `app.py`: pasan `logo_url=obtener_logo_cliente(cliente)` en lugar de `logo_url=cliente.get("logo_url")`.

## [2.55.2] — 2026-05-27

### Documentación
- `docs/supabase-conventions.md`: guía de convenciones para creación de tablas en Supabase. Documenta la arquitectura service_role + RLS sin políticas, el patrón SQL estándar (CREATE TABLE + índices + ENABLE ROW LEVEL SECURITY + GRANT a service_role), y la nota sobre el requisito de GRANT explícito a partir del 30 de octubre de 2026.

## [2.55.1] — 2026-05-27

### Seguridad
- `/changelog` ahora requiere rol `admin` o `master_admin`; devuelve 403 a `usuario_normal` y a usuarios no autenticados.
- Enlace "Changelog" en el footer del sidebar oculto para `usuario_normal` (sigue viendo el número de versión).

### Añadido
- Sección "Uso de cookies" en `privacidad.html`: documenta la cookie de sesión y `last_cliente_id`, declara ausencia de cookies de analítica/publicidad/rastreo, e informa al usuario de que puede eliminarlas desde el navegador.

## [2.55.0] — 2026-05-27

### Añadido
- `README.md` en raíz: stack, estructura, instrucciones de arranque local y variables de entorno.
- `scripts/README.md`: documenta los tres scripts de migración (versión, fecha, estado), explica por qué se conservan y advierte sobre ejecución sin contexto.
- `docs/historico/disenos-iniciales/README.md`: explica que los planes son documentos históricos, no documentación operativa.

### Cambiado
- `docs/superpowers/plans/` renombrada a `docs/historico/disenos-iniciales/` para reflejar su naturaleza histórica. Los seis archivos de diseño se mueven sin modificar contenido.

## [2.54.4] — 2026-05-27

### Eliminado
- `flask-login` y `python-dotenv` de `requirements.txt` — sin importaciones en el código desde v2.31.0.
- Variables `APP_USER` y `APP_PASSWORD_HASH` de `render.yaml` — eliminadas del sistema de autenticación en v2.31.0.
- Archivo `VERSION` — redundante; la versión se lee directamente desde `CHANGELOG.md`.

### Cambiado
- `web/app.py`: `_APP_VERSION` ahora se extrae con regex de la primera entrada `## [X.Y.Z]` del `CHANGELOG.md`, eliminando la dependencia del archivo `VERSION`.

## [2.54.3] — 2026-05-27

### Eliminado
- `web/templates/login.html` (192 líneas) — template huérfano, reemplazado por `auth/login.html` desde v2.31.0. Sin ningún `render_template` apuntando a él.
- `web/templates/auth/reset_password_nuevo.html` (78 líneas) — funcionalidad de reset password por email eliminada en v2.32.0. El handler ya no existía.
- `test_flask.py` (9 líneas) — snippet de diagnóstico, mini servidor Flask sin asserts. No era un test real.
- `start.py` (23 líneas) — punto de entrada antiguo que llamaba `create_app("invoices")` con argumento posicional que ya no existe en la firma actual. Hubiera roto en ejecución.
- `run_server.py` (30 líneas) — mismo problema. Llamaba `create_app(invoices_dir=..., db_path=...)`. La app arranca vía gunicorn en producción.
- `auditoria_chpapp.md` (~58 KB) — auditoría técnica histórica en la raíz. Artefacto de trabajo, no documentación operativa.
- `estructura.txt` (231 líneas) — árbol de directorios generado manualmente, obsoleto.
- `chpapp.db` (local) — base de datos SQLite de la era pre-Supabase. Estaba en `.gitignore`.
- `.DS_Store` raíz y subdirectorios (8 archivos, ~58 KB) — metadatos macOS. Añadido `**/.DS_Store` a `.gitignore` para cubrir subdirectorios.

## [2.54.2] — 2026-05-27

### Seguridad
- Eliminado `.env.bak` local (contenía `SUPABASE_URL` y `SUPABASE_KEY` en texto plano). Verificado con `git log --all --full-history -- .env.bak` que nunca llegó al repositorio — sin exposición de credenciales.
- Añadidos a `.gitignore`: `.env.bak`, `.env.*`, `*.env`. La regla anterior solo cubría `.env` literal; cualquier variante (`.env.local`, `.env.production`, `.env.bak`) quedaba sin protección.

## [2.54.1] — 2026-05-27

### Corregido
- Bug: `auth.admin.update_user_by_id` devolvía "User not allowed" al cambiar contraseña desde el panel admin. Causa raíz: en supabase-py v2, `sign_in_with_password` dispara el listener `_listen_to_auth_events(SIGNED_IN)` que muta `sb.auth._headers["Authorization"]` con el JWT del usuario autenticado (no service_role). Esto contamina el cliente singleton para todas las peticiones admin posteriores del mismo proceso. El reset existente `sb.postgrest.auth(SUPABASE_KEY)` solo corregía el cliente postgrest. Fix: añadir `sb.auth._headers["Authorization"] = f"Bearer {service_key}"` en el mismo bloque de restauración de `_handle_login`.

## [2.54.0] — 2026-05-27

### Seguridad
- Invalidación de sesiones al cambiar contraseña mediante `session_version`. La tabla `user_profiles` tiene nueva columna `session_version INTEGER DEFAULT 1`. Al hacer login, la versión se guarda en la sesión Flask. `before_request` la compara con BD en cada request (cache de 5 minutos). Al cambiar contraseña, `incrementar_session_version()` incrementa el contador en BD — todas las sesiones activas del usuario quedan inválidas en su siguiente request. El usuario que cambia su propia contraseña desde "Mi Perfil" no se desloguea: su sesión actual se refresca con la nueva versión.

### Migración requerida
DDL ejecutado en Supabase SQL Editor (`storage/migrations/202605_session_version.sql`):
```sql
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1;
```
Verificar: `SELECT id, email, session_version FROM user_profiles LIMIT 5;`

## [2.53.1] — 2026-05-27

### Añadido
- Enlace "Auditoría Login" en el sidebar, sección Administración, visible solo para `master_admin`. Icono `bi-shield-check`. Se activa con `nav_active = 'auditoria'` en el template correspondiente.

## [2.53.0] — 2026-05-27

### Añadido
- Auditoría de logins: tabla `login_audit` en Supabase registra cada intento de autenticación (exitoso o fallido) con `user_id`, `email`, `success`, `ip_address`, `user_agent`, `failure_reason` y `created_at`. La función `registrar_login_audit()` en `storage/repository.py` es falla-silenciosa: no bloquea el login si Supabase no responde. Cubiertas 4 causas de fallo: `invalid_credentials`, `user_not_found`, `user_inactive`, `other`.
- Vista `/admin/auditoria-logins` (acceso: master_admin y admin): tabla de los últimos 100 registros con filtros por email y resultado (éxito/fallo). Permite investigar el caso de sesiones en navegadores no reconocidos.

### Migración requerida
DDL ejecutado en Supabase SQL Editor (`storage/migrations/202605_login_audit.sql`):
```sql
CREATE TABLE IF NOT EXISTS login_audit (
    id BIGSERIAL PRIMARY KEY, user_id UUID, email TEXT,
    success BOOLEAN NOT NULL, ip_address TEXT, user_agent TEXT,
    failure_reason TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_login_audit_user_id    ON login_audit(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_login_audit_email      ON login_audit(email);
CREATE INDEX IF NOT EXISTS idx_login_audit_created_at ON login_audit(created_at DESC);
```

Consulta de investigación:
```sql
SELECT created_at, email, success, ip_address, user_agent, failure_reason
FROM login_audit
WHERE email = 'usuario@dominio.com'
ORDER BY created_at DESC
LIMIT 50;
```

## [2.52.2] — 2026-05-27

### Corregido
- Regresión crítica de v2.52.0: `session.clear()` borraba el token CSRF de Flask-WTF, causando "CSRF session token is missing" en el POST de login tras logout. `clear_user_session()` ahora preserva `csrf_token` antes de limpiar y lo restaura después.

## [2.52.1] — 2026-05-27

### Corregido
- `delete_cookie("last_cliente_id")` en logout ahora pasa `path="/"`, `samesite="Lax"`, `secure=not current_app.debug`, `httponly=True` — mismos atributos con los que se creó en `clientes.py`. Sin esta paridad el navegador no borraba la cookie.

## [2.52.0] — 2026-05-27

### Seguridad
- `clear_user_session()` reemplaza el `pop()` explícito por `session.clear()`. Garantiza que cualquier clave presente en sesión (incluyendo `_activo_check`, `_cp_cache`, `cliente_activo_id` y claves futuras) se elimina al hacer logout, sin depender de una lista explícita que puede quedar desactualizada.
- Logout borra la cookie `last_cliente_id` además de la sesión Flask. Antes, esta cookie persistía 30 días tras cerrar sesión, exponiendo el ID del último cliente visitado en el navegador.

## [2.51.0] — 2026-05-27

### Seguridad
- `SECRET_KEY` ahora es obligatoria: eliminado el fallback silencioso `os.urandom(32)`. Si la variable de entorno no está configurada, el proceso falla en el arranque con un `RuntimeError` descriptivo. Esto convierte un problema silencioso (sesiones invalidadas en cada cold start de Render) en un error evidente y detectable en despliegue.
- Verificación de `activo` en `before_request`: si un administrador desactiva una cuenta en `user_profiles.activo = false`, el usuario es deslogueado en su próximo request (máx. 5 minutos de latencia por cache TTL en sesión). Antes, la cuenta desactivada permanecía operativa hasta expirar la cookie de 30 días. Implementado con cache en sesión Flask para evitar una query a Supabase en cada request.

## [2.50.0] — 2026-05-27

### Refactorizado
- CSS — reemplazados 12 hardcodes del design system en templates y JS en-scope. Desglose: `clientes/_base.html` (5 fallbacks redundantes en mobile-block-screen eliminados: `var(--color-primary,#1F7A4C)` → `var(--color-primary)`, `var(--color-text-secondary,#5A5A5A)` × 2 → `var(--color-text-secondary)`, `var(--color-border,#E0E0E0)` → `var(--color-border)`, `var(--color-text-primary,#1A1A1A)` → `var(--color-text-primary)`); `dashboard_contabilidad.html` (1: `#6c757d` → `var(--color-text-muted)` en `.link-datos`); `dashboard_cogeneracion.html` (3: dos `var(--color-text-muted, #6c757d)` → `var(--color-text-muted)`, un `var(--color-secondary, #6c757d)` → `var(--color-text-muted)`); `dashboard-cogeneracion.js` (3: dos `"var(--bs-secondary, #6c757d)"` en `el.style.color` → `"var(--color-text-muted)"`, un `var(--color-text-muted,#6c757d)` → `var(--color-text-muted)`).
- CSS — añadida regla `.text-muted { color: var(--color-text-muted) !important; }` al final de `theme.css`. Sincroniza las ~229 ocurrencias de `.text-muted` en templates con el token `--color-text-muted: #9A9A9A` del design system (antes usaba Bootstrap `--bs-secondary-color` ≈ gris semitransparente). Cambio visual perceptible: gris más claro y opaco en toda la app.
- Ocurrencias NO tocadas: `dashboard.html:687` `borderColor:"#1F7A4C"` y `dashboard-cogeneracion.js:286,371` `borderColor`/`backgroundColor` — configuración interna de Chart.js, no CSS. `dashboard-contabilidad.js:48,172` `COLOR_GAS_LINEA`/`backgroundColor[]` — constantes y arrays de Chart.js. `donut-componentes.js:70` `fill="#1A1A1A"` — atributo SVG de presentación; CSS variables no aplican a atributos HTML.

### Verificado sin cambios
- `text-danger` (59×), `text-warning` (4×), `text-success` (6×), `text-secondary` (10×): uso semánticamente coherente en todos los casos analizados. No se interviene — Bootstrap los gestiona correctamente.

## [2.49.0] — 2026-05-27

### Refactorizado
- CSS — extraído el bloque `<style>` del sidebar de `clientes/_base.html` (243 líneas) al archivo independiente `web/static/css/sidebar.css` (248 líneas con cabecera). El template ahora carga `sidebar.css` como `<link>` después de `theme.css`.
- CSS — tokenizados 8 hardcodes en `sidebar.css`: `#F0F0F2` (5 ocurrencias hover) → `var(--color-sidebar-hover-bg)`; `#D0D0D0` (1 ocurrencia borde mes-btn) → `var(--color-sidebar-border-hard)`; `#5A5A5A` (1 ocurrencia texto mes-btn) → `var(--color-text-secondary)`; `#1F7A4C` (1 ocurrencia color contrato eléctrico básico) → `var(--color-primary)`.
- CSS — añadidas 3 variables nuevas a `theme.css :root`: `--color-sidebar-hover-bg: #F0F0F2`, `--color-sidebar-border-hard: #D0D0D0`, `--color-sidebar-dark-bg: #1A2D3F`.
- Colores sin variable equivalente que quedan hardcoded en `sidebar.css`: `#6A6A6A` (3×, texto links inactivos), `#8A8A8A` (1×, texto sub-links), `#F8F8F8` (1×, fondo mes disponible), `#C0C0C0`/`#EBEBEB` (mes no disponible), `#bbb`/`#555` (toggle button), `#0d6efd` (contrato calificado), `#d4a017` (contrato gas). Pendiente tokenizar en fases posteriores.

## [2.48.0] — 2026-05-27

### Refactorizado
- CSS — rediseño completo del sistema de jerarquía tipográfica de KPIs. Eliminado el selector atributo `[id^="kpi-"][id$="-val"]` con `!important` aplicado desde el contenedor. Eliminados los dos overrides de ID (`#kpi-inversion-mxn-val`, `#kpi-inversion-tc-val`). Reemplazados por tres clases directas sin `!important` aplicadas al elemento de valor: `.kpi-valor-primario` (2rem/800), `.kpi-valor-secundario` (1.5rem/700), `.kpi-valor-terciario` (1.15rem/600). Actualizados 8 elementos en dos templates: 4 en `dashboard_cogeneracion.html` (kpi-ahorro-neto-val, kpi-payback-val → primario; kpi-energia-limpia-val, kpi-capacidad-val → secundario) y 4 en `dashboard_contabilidad.html` (kpi-costo-total-periodo → primario; kpi-kwh-total, kpi-costo-unit → secundario; kpi-num-meses → terciario). Los tres elementos del cuadro Inversión estimada no reciben clase nueva — sus estilos inline ya controlan la tipografía directamente.
- Corrección involuntaria: los valores de CO₂ renderizados por JS (`kpi-value` + inline `font-size:1.2rem`) ahora respetan el tamaño 1.2rem especificado en el código; el sistema anterior los forzaba a 1.5rem con `!important`.

## [2.47.0] — 2026-05-27

### Refactorizado
- CSS — eliminadas 9 variables huérfanas de `theme.css` (confirmadas con grep de 0 usos): `--space-xs`, `--space-sm`, `--space-md`, `--space-xl`, `--space-2xl`, `--shadow-md`, `--shadow-lg`, `--radius-xl`, `--color-text-sidebar`. Se mantiene `--space-lg` (uso real en `.kpi-card`) y `--shadow-sm` (3 usos).
- CSS — introducida variable `--color-positive: #28a745` para valores positivos en KPIs financieros (Ahorro Neto, EBITDA, iconos de éxito). Separa semánticamente el verde de resultado positivo del verde marca `--color-primary`. Reemplazados todos los hardcodes `#28a745` en `dashboard_cogeneracion.html` (4 ocurrencias) y `dashboard-cogeneracion.js` (1 ocurrencia).

## [2.46.8] — 2026-05-26

### Corregido
- Dashboard Contabilidad PPA: link "Ver detalle ▼" seguía visible aunque JS asignaba `style.display="none"`. Causa: clase Bootstrap `d-inline-block` aplica `display:inline-block !important` y gana contra el inline style sin prioridad. Fix: cambiado a `style.setProperty("display", ..., "important")` para que el `!important` inline venza a Bootstrap.

## [2.46.7] — 2026-05-26

### Corregido
- Dashboard Contabilidad PPA: error 400 en consola al cargar. `esPPA` solo vivía en el scope de `hidratarDashboardContabilidad` y no era accesible en el click handler de "Ver detalle". Promovida a variable de módulo; el handler ahora hace `if (!div || esPPA) return` antes de cualquier fetch a `desglose-costo-total`.

### Verificado sin cambios
- Sidebar scroll fijo: estructura ya correcta (`#sidebar` flex-column, `#sidebar-content` flex:1/overflow-y:auto/min-height:0, `.sidebar-bottom` flex-shrink:0). Añadido `flex-shrink:0` a `.sidebar-brand` que faltaba explícitamente.
- Aviso `sin_par` Contabilidad: ya implementado como `alert-secondary` compacto con mensaje diferenciado según falta electricidad o gas. `sinDatos` no incluye `sin_par`. Sin cambios en lógica.

## [2.46.6] — 2026-05-26

### Corregido
- Dashboard Cogeneración: cuadro "Inversión estimada" — los tres valores (USD, MXN, TC) se renderizaban en 24px idéntico porque la regla `.kpi-nivel-secundario [id^="kpi-"][id$="-val"] { font-size: 1.5rem !important }` en `theme.css` capturaba los tres IDs y aplastaba los font-size inline. Añadidos overrides ID-selector en `theme.css` para `#kpi-inversion-mxn-val` (.8rem) y `#kpi-inversion-tc-val` (.65rem), ambos con `font-weight: 400 !important` para neutralizar también el 700 forzado por la regla genérica.

## [2.46.5] — 2026-05-26

### Corregido
- Dashboard Cogeneración: cuadro "Inversión estimada" — jerarquía tipográfica forzada con tamaños explícitos. USD: `1.5rem fw-bold` (eliminada clase `fs-4` que podía ser sobrescrita). MXN: `.8rem`. TC: `.65rem opacity:.7`. Los tres con `line-height:1.1` y `margin-bottom` escalonado para apilado compacto. La diferencia de tamaño entre USD y TC es ahora de ~2.3× (antes ~1.2×).

## [2.46.4] — 2026-05-26

### Revertido
- `dashboard-cogeneracion.js`: eliminado guard `window._cogDashLoaded` añadido por error en diagnóstico incorrecto de doble inicialización. No había problema real de ejecución múltiple del script.

## [2.46.3] — 2026-05-26

### Corregido
- Pie chart "Composición del costo eléctrico" (Contabilidad): revertido a colores originales `["#1F7A4C","#4FA876","#9A9A9A"]`. La paleta azul había sido aplicada por error en v2.46.1.
- Donut "Desglose del Costo Total" (Contabilidad): aplicada paleta azul monocromática (#0D3B66 Energía, #1F6FB2 Capacidad, #4A9FD8 Distribución, #A8D0E6 Otros Servicios) en `renderDetalleCostoTotal`.
- Donut "Ahorro Eléctrico" en caja Ingresos (Cogeneración): aplicada misma paleta azul en `renderDonutComponentes("donutAhorroElec")`.
- Cuadro Inversión (Cogeneración): JS y HTML ya estaban correctamente separados desde v2.46.2 — USD `fs-4`, MXN `.85rem`, TC `.7rem opacity:.75`. Sin cambios adicionales.
- Link "Ver detalle" Contabilidad PPA: ya estaba oculto correctamente cuando `esPPA`. Sin cambios adicionales.

## [2.46.2] — 2026-05-26

### Verificado y corregido
- Pie chart Contabilidad: paleta azul monocromática ya estaba aplicada correctamente desde v2.46.1. Sin cambios.
- Cuadro Inversión Cogeneración: estilos completados — MXN con `font-size:.85rem;line-height:1.2`, TC con `font-size:.7rem;line-height:1.2;opacity:.75`. La jerarquía USD > MXN > TC es ahora visualmente clara.
- Desglose costo total PPA: ya estaba correctamente oculto para PPA (reset siempre a `display:none` + link "Ver detalle" oculto cuando `esPPA`). Sin cambios.

## [2.46.1] — 2026-05-26

### Cambiado
- Dashboard Contabilidad: pie chart de distribución del costo eléctrico usa paleta monocromática azul (`#0D3B66`, `#1F6FB2`, `#4A9FD8`, `#A8D0E6`) para no colisionar con los colores de periodos horarios (verde Base, amarillo Intermedio, rojo Punta).
- Dashboard Cogeneración: tarjeta "Inversión estimada" jerarquiza tipográficamente: USD en `fs-4` (valor primario), MXN en `text-muted small` (valor secundario), y tipo de cambio en línea independiente `font-size:.7rem` como referencia.

## [2.46.0] — 2026-05-26

### Añadido
- Ficha del contrato: borrado masivo de facturas. Cada tabla (CFE, Gas, PPA) tiene un checkbox por fila y un checkbox maestro en el encabezado. Al seleccionar una o más facturas aparece una barra roja con el botón "Borrar seleccionadas". El modal de confirmación muestra el desglose por tipo. El borrado ejecuta una petición por factura en paralelo (Promise.all) usando los endpoints existentes. Si alguna falla, muestra resumen sin recargar.

## [2.45.6] — 2026-05-26

### Cambiado
- Dashboard Contabilidad (CFE GDMTH): aviso `sin_par` reemplazado por un banner discreto (`alert-secondary`, texto pequeño, sin icono) que indica qué categoría falta sin ocultar el dashboard ni bloquear la navegación.

## [2.45.5] — 2026-05-26

### Cambiado
- Upload batch (CFE y gas): la discrepancia de identificador ya no bloquea el guardado. La factura se persiste siempre; si el identificador no coincide con el del contrato, aparece un aviso naranja (⚠) junto al nombre en el resumen final. Eliminados el modal de confirmación de discrepancia, la lógica de `pendientes_confirmacion` en backend y frontend, y la queue `_pendingFiles`.

## [2.45.4] — 2026-05-26

### Corregido
- Ficha de cliente: caja "Facturas CFE" renombrada a "Facturas Electricidad" y ahora muestra `num_electricidad` (suma CFE + PPA). El modal de borrado también actualiza el texto a "facturas de electricidad".

## [2.45.3] — 2026-05-26

### Corregido
- Sidebar contratos PPA: la selección masiva por año ("botón maestro") no persistía en BD. `upsert_meses_seleccionados_anio` ahora recibe `contrato_tipo` y lo pasa a `get_meses_con_factura`, que así consulta `facturas_electricidad_calificado` en lugar de `cfe_facturas` para contratos PPA.

## [2.45.2] — 2026-05-26

### Corregido
- Dashboard Contabilidad PPA: eliminada la exigencia de par electricidad+gas para mostrar el dashboard. Para clientes PPA, gas es opcional; el aviso `sin_facturas` ahora usa `num_electricidad` (CFE+PPA) y `aviso_datos = None` se alcanza con solo tener facturas PPA seleccionadas. Las ramas `sin_par` y `sin_pares_mes` se conservan únicamente para la rama CFE GDMTH, que sí requiere el par histórico.

## [2.45.1] — 2026-05-26

### Corregido
- Listado de clientes: el conteo de facturas eléctricas ahora suma CFE + PPA (facturas_electricidad_calificado). Se añade `num_electricidad` y `num_calificado` al dict de cliente; `num_cfe` y `num_gas` se conservan para no romper consumidores existentes. La columna "Facturas CFE" pasa a llamarse "Facturas Electricidad" y el badge "Solo CFE" pasa a "Solo electricidad".

## [2.42.0] — 2026-05-25

### Añadido
- Dashboard Contabilidad — desplegable "Desglose del Costo Total": rediseñado con layout de dos columnas (tabla izquierda + donut SVG derecha). La columna de porcentaje se elimina; los porcentajes se leen visualmente en el donut. Cabecera de tabla transparente; fila TOTAL con fondo verde suave y borde superior.
- Dashboard Cogeneración — card INGRESOS / desplegable ahorro eléctrico: rediseñado con layout de dos columnas (tabla 3 cols — Componente/Original/Ahorro + donut SVG). La columna de porcentaje se elimina; el donut muestra la composición relativa del ahorro. Se actualiza en tiempo real al mover los sliders de sensibilidad.
- Nuevo archivo compartido `web/static/js/donut-componentes.js` con funciones globales `arcPath()` y `renderDonutComponentes()`, reutilizables entre dashboards.
- Nuevo CSS `.donut-color-dot` en `theme.css` para puntos de color en filas de tabla.

## [2.41.2] — 2026-05-25

### Cambiado
- Login — columna izquierda: eliminado el copyright al fondo del formulario. El panel blanco queda sin footer.
- Login — columna derecha: restructurado layout a `.login-right-inner` (flex row, contenido + gráficas) + `.login-right-footer-unified` al fondo. El footer unificado ocupa el ancho completo de la franja azul oscuro, separado por borde sutil, y contiene dos líneas: copyright corporativo y resumen del aviso de privacidad con link a `/privacidad`.
- Login — gráficas: añadida tercera gráfica hand-drawn SVG (donut antes/después de huella CO₂) debajo de las dos existentes. Los tres SVGs quedan envueltos en `<div>` con `.sketch-chart-caption`. Tamaños ajustados para encajar las tres gráficas verticalmente.

## [2.41.1] — 2026-05-25

### Añadido
- Login — columna derecha: footer discreto con resumen de protección de datos y link "Ver aviso de privacidad completo" que abre `/privacidad` en nueva pestaña. El layout de `.login-right` se reestructura a columna con `.login-right-main` como wrapper horizontal interno para el contenido y las gráficas SVG, y el footer al fondo con `margin-top: auto`.
- Página pública `/privacidad`: aviso de privacidad completo conforme a la LFPDPPP. Incluye identidad del Responsable, categorías de datos recabados, compromiso de confidencialidad de información operativa y financiera, finalidades, transferencias (Supabase, Render), plazos de conservación, derechos ARCO y medidas de seguridad. Accesible sin autenticación (agregada a `_PUBLIC_EXACT` en `before_request`). Template propio `privacidad.html` sin sidebar.

## [2.41.0] — 2026-05-25

### Añadido
- Dashboard Contabilidad y Cogeneración: botón "Descargar datos" en la barra de título. Descarga un Excel (.xlsx) generado en memoria con todos los datos del análisis activo. Contabilidad CFE: hojas KPIs, Consumos y demandas, Costos detallados, Indicadores, Gas natural. Contabilidad PPA: hojas KPIs, Facturas PPA, Gas natural. Cogeneración: hojas KPIs, Parámetros motor, Tabla mensual, Cascada ahorro, Flujo 15 años. Los parámetros de slider activos se incluyen en el export de cogeneración vía query string.
- Login: panel derecho restructurado con flexbox horizontal. Se añade columna de visuales decorativas con dos gráficas SVG dibujadas a mano — cascada de composición del ahorro y curva de flujo acumulado a 15 años con marcador de payback. La columna de visuales se oculta en pantallas < 1280 px.

### Cambiado
- Encabezados de tabla (`.table-primary-header th`): fondo cambia de verde oscuro (`#1F7A4C`) a verde suave (`#E8F4ED`) con texto en verde oscuro (`#155936`) y borde inferior `2px solid`. Elimina los estilos redundantes `.table-mes th` de `dashboard.html` y `dashboard_contabilidad.html`.
- Panel flotante: el método `abrir()` ahora mide la altura natural del contenido y la aplica como altura real, con tope del 95% del alto de la ventana. Antes usaba 85% del alto de forma fija. Garantiza que paneles con poco contenido no quedan con espacio vacío excesivo.

## [2.40.1] — 2026-05-25

### Corregido (ajustes UI v2.40.0)
- Contabilidad — 4ª caja KPI "Costo Total del Periodo": reemplaza el panel flotante por un desplegable inline bajo el bloque de KPIs. Link "Ver detalle ▼" visible solo en modo CFE GDMTH. Nuevo endpoint `GET /clientes/<id>/dashboard/contabilidad/desglose-costo-total` devuelve 4 categorías (Energía, Capacidad, Distribución, Otros Servicios) con importe MXN y % entero. La tabla invalida caché al cambiar selección de meses.
- Cogeneración — card INGRESOS: reestructura el layout para que el desglose de 4 componentes (Energía, Capacidad, Distribución, Otros Servicios) ocupe el ancho completo del card con grilla `col-3`. Los dos KPIs (Ahorro Electricidad / Ahorro Caldera) quedan en `row/col-6` arriba; Total Ingresos al fondo en ancho completo. Sustituye Bootstrap collapse por toggle `display:none` con flecha ▼/▲.

## [2.40.0] — 2026-05-21

### Añadido
- Sidebar: límite de 24 meses seleccionables por análisis. Si se intenta superar el límite (individual o por año completo), se muestra un toast Bootstrap de advertencia y la operación se aborta sin llamar al servidor.
- Componente JS reutilizable `mostrarBarraProgreso(container, actual, total, nombre)` en `_base.html`. Renderiza barra de progreso Bootstrap con texto contextual. Disponible en todos los templates que extienden `_base.html`.
- Upload bulk (ficha contrato): reemplaza texto "Subiendo X / Y: archivo" por barra de progreso visual durante subida múltiple de PDFs.
- Upload PPA (factura calificada): muestra barra de progreso al enviar el formulario de análisis de PDF (el proceso de parseo puede tardar varios segundos).
- Panel flotante: dimensiones por defecto cambiadas de 800×600 px fijos a 95% del ancho × 85% del alto de la ventana del navegador. Centra automáticamente en cualquier resolución.
- Dashboard Contabilidad: link "Ver detalles" en la tarjeta "Costo Total del Periodo" abre panel flotante `panelResumenCostoPeriodo` con tabla mensual (factura, mes, kWh, costo MXN pre-IVA) y fila de total.
- Dashboard Cogeneración — desglose Ahorro Eléctrico: panel de detalle ahora muestra tres columnas (Original MXN, Ahorro MXN, %) para cada componente (Energía, Capacidad, Distribución, Otros Servicios). "Original" es el costo real del componente sin cogeneración; "%" es el porcentaje de ahorro sobre el original.

### Corregido (nomenclatura regulatoria)
- Reemplazado "CRE" por "CNE" en todos los textos visibles en la UI (ficha cliente, dashboard cogeneración, templates nuevo/editar cliente, comentarios JS). Los identificadores de código (`calcular_cels`, `CELsResultado`, etc.) y referencias normativas (`RES/1838/2016`) no se modificaron.

## [2.39.1] — 2026-05-21

### Corregido
- Dashboard Cogeneración: cálculo de Capacidad Nominal ahora usa los días del mes calendario asociado en lugar de los días de facturación. Antes subestimaba la capacidad cuando una factura tenía días sobrantes (ej. 32 días facturados para octubre que solo tiene 31). Impacta también el cálculo de inversión y payback derivados.

### Tests
- `tests/calc/test_cogen.py`: 3 tests nuevos — `test_capacidad_nominal_dias_calendario` (verifica caso EUREKA oct-2018: 699→721 kW), `test_capacidad_nominal_periodo_exacto_mes` (enero 2024 alineado: 1000 kW exacto), `test_capacidad_nominal_multiples_facturas` (MAX de tres facturas distintas).

## [2.39.0] — 2026-05-21

### Corregido
- Parser CFE GDMTH (`parsers/cfe/gdmth.py`): regex `RE_KW_MAX` ahora acepta "kW Max" con espacio entre "kW" y "Max" (`[Kk][Ww]\s*[Mm]ax`), presente en facturas 2019-era de INDUSTRIAS EUREKA (cliente 39) y probablemente otros clientes con PDFs antiguos.
- Parser CFE GDMTH: si el campo `kWMax` no se encuentra en el PDF (regex sin coincidencia), el parser deriva el valor como `max(kW base, kW intermedia, kW punta)` y agrega advertencia descriptiva. Elimina los `kw_max = 0` silenciosos en facturas donde el campo existe en formato distinto.

### Añadido
- Tarjeta de solo lectura "Parámetros CRE (cogeneración eficiente)" en la ficha del cliente, visible únicamente para roles `admin` y `master_admin`. Muestra capacidad nominal derivada de las últimas facturas disponibles, RefH (ponderado por mezcla de medios térmicos), fp (factor de planta por nivel de tensión), RefE y RefE′ según tabla CRE RES/1838/2016.
- `storage/migrations/202605_eureka_kw_max_correccion.sql`: corrección idempotente de `kw_max` en las 12 facturas históricas de EUREKA (facturas con kw_max NULL o "0") usando `MAX(kW base, kW intermedia, kW punta)` de `cfe_periodos`. Incluye diagnóstico de otros clientes con el mismo defecto.
- `storage/migrations/202605_tipos_correctos.sql`: migración manual para cambiar columnas de tipo TEXT a NUMERIC/DATE/INTEGER en las tablas `cfe_facturas`, `cfe_periodos`, `cfe_mem_componentes`, `gas_facturas`, `gas_conceptos` y `facturas_electricidad_calificado`. Incluye pre-validación comentada para verificar valores convertibles antes de aplicar. No se ejecuta automáticamente.
- `storage/migrations/202605_tipos_correctos_rollback.sql`: rollback idempotente de la migración de tipos, devuelve todas las columnas a TEXT.
- `storage/migrations/202605_eureka_mem_cargos_correccion.sql`: corrección de asignación de tipo de cargo en componentes MEM de todas las facturas de EUREKA. Rederiva `cargo_fijo_mxn`, `cargo_demanda_mxn` y `cargo_energia_mxn` desde `importe_mxn` según el tipo de componente (regla determinista: Suministro→fijo, Distribución/Capacidad→demanda, demás→energía). Incluye diagnóstico previo con RAISE NOTICE por componente inconsistente.

### Tests
- `tests/parsers/test_gdmth.py`: 2 tests nuevos — `test_kw_max_regex_acepta_espacio` (verifica que el regex captura kWMax, kW Max, KW Max, kwmax) y `test_kw_max_fallback_desde_periodos` (verifica que el parser deriva kw_max desde las demandas horarias cuando el campo no está en el PDF, usando mock de pdfplumber).

## [2.38.2] — 2026-05-21

### Corregido
- Script SQL de corrección de la factura de julio 2024 de MASPESCA: calcula `costo_unitario_kwh` dentro del bloque DO con la misma fórmula del parser (`gen_h / kwh_h + shared_kwh`) en lugar de pasar NULL, que violaba la restricción NOT NULL de `cfe_periodos`.
- Endpoint POST `/upload/manual`: calcula automáticamente `costo_unitario_kwh` para cada periodo usando la función `calcular_costos_unitarios_kwh` de `calc/cfe_util.py`. Las facturas guardadas por captura manual ya tienen los costos unitarios correctos sin pedírselos al operador.

### Añadido
- `calc/cfe_util.py`: función `calcular_costos_unitarios_kwh(kwh_base, kwh_inter, kwh_punta, gen_b, gen_i, gen_p, transmision, cenace, scnmem)` — lógica extraída como utilidad reutilizable. El parser `gdmth.py` mantiene su implementación inline sin cambios.

### Cambiado
- Modal de captura manual: confirmado que no incluye ningún campo derivado (`costo_unitario_kwh`, `nombre_canonico`, `anio`, `mes`). El operador solo captura campos que aparecen impresos en el PDF.

## [2.38.1] — 2026-05-21

### Corregido
- Modal de captura manual de facturas CFE: ahora incluye TODOS los campos críticos (consumos kWh, demanda kW, factor de potencia, componentes MEM), organizados en 5 tabs (Identificación, Totales, Consumos, MEM, Motivo). Las facturas guardadas por captura manual ya no se almacenan con periodos y componentes vacíos.
- Endpoint POST `/upload/manual`: valida en backend que los 3 horarios de consumo (base/intermedio/punta con kWh > 0) y los 9 componentes MEM estén presentes antes de persistir. Retorna HTTP 400 con mensaje descriptivo si faltan.
- Factura julio 2024 del cliente MASPESCA: script SQL de corrección generado en `storage/migrations/202605_maspesca_julio2024_correccion.sql` (requiere ejecución manual en Supabase).

### Cambiado
- Modal de captura manual: campos reorganizados en 5 secciones tipo tab para facilitar la captura. Badges rojos por tab indican qué secciones tienen campos incompletos. Botón "Guardar factura" permanece desactivado hasta que todos los campos obligatorios estén completos.
- JS de captura manual: construye `periodos_json` y `componentes_mem_json` con asignación correcta de tipo de cargo por componente MEM (cargo_fijo, cargo_demanda, cargo_energia) antes del submit.

## [2.38.0] — 2026-05-21

### Corregido
- Dashboard Proyecto Cogeneración: ya no suma todos los meses seleccionados en el sidebar. Ahora usa siempre las últimas 12 facturas disponibles en BD (ordenadas por `periodo_inicio DESC`), independientemente de la selección del sidebar. El sidebar sigue controlando el Dashboard de Contabilidad Energética sin cambios.

### Añadido
- Etiqueta de rango de meses analizados en Dashboard Cogeneración: "Cálculo basado en los últimos 12 meses: junio 2024 a mayo 2025" (visible cuando hay datos suficientes).
- Nuevas funciones de repositorio: `get_ultimas_cfe_invoices`, `get_ultimas_gas_invoices`, `get_ultimas_ppa_invoices` — consultan las últimas N facturas directamente sin filtro de selección.
- Helpers `_cargar_ultimas_facturas_cogen` y `_cargar_ultimas_ppa_cogen` en `web/app.py`.
- Función `_calcular_rango_cogen` que produce la etiqueta legible del rango de meses.

### Cambiado
- Aviso "Datos insuficientes" en Dashboard Cogeneración: ya no menciona seleccionar meses en el sidebar; indica subir más facturas desde la ficha del cliente.
- Aviso "sin_seleccion" eliminado del flujo GDMTH en Dashboard Cogeneración (ya no aplica al no depender del sidebar).

## [2.36.0] — 2026-05-21

### Eliminado
- Validación "RFC discrepante" en flujo de carga de facturas (CFE y Gas). Tras v2.35.0 (RFC sin unicidad ni obligatoriedad), comparar el RFC de la factura con el del cliente perdió sentido. La factura se guarda directamente sin modal ni confirmación cuando el RFC difiere.

### Corregido
- Bug en upload masivo: el flujo de carga de múltiples PDFs ya no se detiene al encontrar un RFC distinto al del cliente. Ahora procesa todos los PDFs del batch sin interrupciones.

### Cambiado
- `contrato_upload` en `clientes.py`: el bloque `pendientes_confirmacion` ya solo aplica a discrepancia de **identificador** (numero de servicio CFE / cuenta contrato gas vs el identificador registrado en el contrato). RFC ignorado.
- `mostrarDiscrepancia()` en `contratos/ficha.html`: ya no muestra el ítem RFC en el modal de discrepancia.

## [2.35.0] — 2026-05-21

### Cambiado
- Creación y edición de cliente: solo **Nombre** es obligatorio. Todos los demás campos son opcionales.
- **RFC ya no es obligatorio** ni único. Puede estar vacío o duplicarse entre clientes. Si se llena, debe tener 12 o 13 caracteres.
- Eliminada validación de unicidad de RFC en backend y en BD (ver migración). Eliminada condición que impedía editar el RFC de un cliente con facturas cargadas.
- Validaciones de formato (email, código postal 5 dígitos, año de inicio) solo se aplican cuando el campo contiene valor. El campo vacío siempre es aceptado.
- Año de inicio de operación: límite superior extendido a `año actual + 5` (era `+ 1`).
- En la ficha del cliente, el campo RFC muestra "—" cuando está vacío/null (antes mostraba "None").

### Añadido
- Cinco nuevos sectores industriales en el dropdown: **Pesquero, Forestal, Cerámico, Plásticos, Metalúrgico** (se añaden tras los existentes, antes de "Otro").
- Migración `storage/migrations/202605_eliminar_unique_rfc.sql` (ejecutar manualmente en Supabase).
- Tests: `test_nuevo_cliente_sin_rfc`, `test_nuevo_cliente_rfc_duplicado_permitido`, `test_ficha_cliente_rfc_nulo_muestra_guion`, `test_editar_post_rfc_vacio`. Corrección de mocks preexistentes en tests de ficha que hacían conexiones reales a Supabase.

### Migración requerida
- Ejecutar `storage/migrations/202605_eliminar_unique_rfc.sql` en Supabase antes de desplegar.

## [2.34.0] — 2026-05-21

### Añadido
- **Gestión de usuarios para rol Administrador**: el rol `admin` ahora accede a `/admin/usuarios` y puede crear, editar, cambiar contraseña, activar/desactivar y borrar usuarios con rol `usuario_normal`. Los usuarios `master_admin` son invisibles para el admin. El admin no puede modificar ni ver a otros administradores (solo aparece "—" en su fila). El dropdown de rol en "Crear usuario" solo muestra "Cliente" cuando el actor es `admin`. El campo de rol en "Editar usuario" es de solo lectura para `admin` (se envía como campo oculto).
- Enlace "Gestión de Usuarios" en el sidebar ahora visible también para `admin` (antes solo para `master_admin`).

### Corregido
- `validar_borrar_usuario` en `auth_permissions.py` extendida: `admin` puede borrar `usuario_normal`; ninguno puede borrar `master_admin` ni otro `admin`.
- Rutas `admin_usuarios_borrar` y `admin_usuarios_desactivar` actualizadas para aceptar `admin` además de `master_admin`, con las validaciones de rol correspondientes.

## [2.33.4] — 2026-05-21

### Añadido
- **Sidebar scroll indicator**: gradiente + flecha visible sobre el footer cuando el contenido del sidebar desborda. El footer es ahora verdaderamente fijo (el área scrollable es `#sidebar-content`; el footer no scrollea). Footer reducido en tamaño de tipografía y padding.
- **Etiqueta de período en Contabilidad Energética**: el encabezado muestra ahora "Septiembre 2024 [CFE GDMTH] + Septiembre 2024 [Gas]" (o rango: "Enero a diciembre 2024 [CFE GDMTH]") en lugar del año genérico.
- **Precio de gas manual** (`precio_gas_manual_mxn_gj_pcs NUMERIC(10,4)` en tabla `clientes`): permite configurar un precio de gas de referencia (MXN/GJ PCS) por cliente. Visible y editable en ficha del cliente solo para admin/master_admin. Endpoint `POST /<cliente_id>/gas-manual`.
- Función `calcular_cogen_precio_manual()` en `calc/cogen.py`: calcula EBITDA con 12+ facturas CFE GDMTH y precio de gas manual, sin requerir facturas de gas emparejadas.
- **Validación 12 meses en dashboard Cogeneración** (solo suministro básico GDMTH): avisos `insuficiente_elec` (< 12 facturas eléctricas), `insuficiente_gas` (< 12 facturas gas sin precio manual), `meses_no_coinciden` (pares < 12). Los dos primeros bloquean el dashboard; el tercero muestra advertencia sin bloquear.
- **Fallback precio gas manual**: cuando hay ≥ 12 facturas CFE y < 12 facturas gas pero hay precio manual configurado, el dashboard usa `calcular_cogen_precio_manual` y muestra banner de advertencia "precio de gas manual".
- **Migración** `storage/migrations/202605_precio_gas_manual.sql`.

### Corregido
- Mensajes de error mezcla CFE/PPA más descriptivos: indican el tipo actualmente seleccionado y qué deseleccionar primero.
- Campo `precio_gas_fuente` (`"real"` | `"manual"` | `"ppa"`) incluido en el JSON del endpoint `/dashboard/cogeneracion/data`.

## [2.33.3] — 2026-05-21

### Corregido
- Bug: doble mensaje flash en editar usuario, cambiar contraseña y configuración. Causa: `get_flashed_messages()` está cacheado en el request context de Flask, por lo que `_base.html` y los templates hijos recibían la misma lista y la renderizaban dos veces. Fix: `usuarios.html` solo renderiza la categoría especial `password_generada`; `configuracion.html` y `mi_perfil.html` eliminan su bloque flash local (delegan todo a `_base.html`).
- Bug: nombre de empresa duplicado en sidebar para `usuario_normal`. La sección `sidebar-section` con `cliente_activo.nombre` (con botón "Detalles") aparecía también para `usuario_normal`, que ya ve el nombre en la sección "Mi empresa". Fix: ese bloque queda dentro de `{% if current_user_data.rol != 'usuario_normal' %}`, consolidando también el botón Detalles en el mismo condicional.

## [2.33.2] — 2026-05-20

### Cambiado
- Sidebar inferior: muestra nombre y apellido del usuario (si existen) en lugar del email; el email pasa a línea secundaria. Fallback a email si no hay nombre.
- Labels de rol en toda la UI: `master_admin` → "Super Admin", `admin` → "Administrador", `usuario_normal` → "Cliente". Implementado vía filtro Jinja2 `label_rol`.
- Botón "Detalles" del sidebar: oculto para `usuario_normal` (no tiene acceso a la ficha).
- Dropdowns de rol en crear/editar usuario: muestran "Administrador"/"Cliente" en lugar de strings internos.

### Añadido
- Campos `nombre` y `apellido` en `user_profiles` (migración `storage/migrations/202605_nombre_apellido.sql`).
- Formulario "Datos personales" en `/mi-perfil` para que cada usuario edite su nombre/apellido.
- Campos nombre/apellido en modal "Crear usuario" y en pantalla "Editar usuario".
- Cookie `last_cliente_id` (30 días): se guarda cuando admin/master_admin visita la ficha de un cliente. Al iniciar sesión, redirige al último cliente visitado si no hay parámetro `next`.
- Endpoint `POST /mi-perfil/cambiar-datos`: actualiza nombre/apellido en BD y en sesión Flask.

## [2.33.1] — 2026-05-21

### Corregido
- Bug: usuario_normal no veía contratos desplegables ni dashboards en el sidebar de su ficha. Causa: `ficha()` no seteaba `cliente_activo_id` en sesión (solo lo hacía el JS del listado, que usuario_normal nunca visita). Ahora `ficha()` activa el cliente en sesión directamente.
- Bug: botón "← Volver" aparecía para usuario_normal aunque no tiene listado de clientes. Ahora oculto para `usuario_normal`.

### Añadido
- Funcionalidad "Editar usuario" (`GET/POST /admin/usuarios/<id>/editar`). Master Admin puede modificar rol y empresa de cualquier usuario que no sea master_admin. Si el rol cambia a `admin`, empresa se limpia a NULL. Template `admin/editar_usuario.html`.
- Botón "Editar" (lápiz) por fila en `/admin/usuarios`, visible solo para master_admin en usuarios no master_admin.

## [2.33.0] — 2026-05-20

### Cambiado
- Redirect post-login para `usuario_normal`: ahora va DIRECTO a la ficha de su empresa, no pasa por listado.
- Sidebar del `usuario_normal`: muestra nombre de su empresa como único elemento de navegación. No muestra "Listado de Clientes", "Gestión de Usuarios" ni "Configuración".
- Badge de rol en sidebar inferior: oculto para `usuario_normal`. `master_admin` y `admin` siguen mostrándolo.
- Endpoint `GET /clientes/`: redirect transparente a `/clientes/<empresa_id>` cuando el usuario es `usuario_normal` con empresa asignada.

### Añadido
- Plantilla `error_sin_empresa.html` para caso edge donde `usuario_normal` no tiene empresa asignada (403, con botones Mi Perfil y Cerrar sesión).
- `empresa_nombre` almacenado en sesión Flask al login (consultado una sola vez desde BD). Disponible en `current_user_data.empresa_nombre` en templates.

## [2.32.0] — 2026-05-20

### Cambiado — Gestión de usuarios: creación directa en lugar de invitación por email

- **Flujo eliminado**: invitación por email (`/admin/usuarios/invitar`), activación de cuenta (`/auth/aceptar-invitacion`), reset password por email (`/auth/reset-password`, `/auth/reset-password/nuevo`).
- **Nuevo endpoint `POST /admin/usuarios/crear`**: master_admin crea usuario con contraseña manual o generada automáticamente. Supabase confirma el email automáticamente (`email_confirm: True`). Si la contraseña se genera, se muestra una sola vez con alerta amarilla.
- **Nuevo endpoint `POST /admin/usuarios/<id>/cambiar-password`**: master_admin puede cambiar contraseña de admin o usuario_normal; admin solo puede cambiar la de usuario_normal y la propia.
- **Nuevo endpoint `GET /mi-perfil`** y **`POST /mi-perfil/cambiar-password`**: cualquier usuario autenticado puede ver su información y cambiar su propia contraseña.
- **Templates**: `admin/usuarios.html` reescrito con modal "Crear usuario" (reemplaza "Invitar") y modal "Cambiar contraseña" por fila. `mi_perfil.html` nuevo. `auth/login.html` elimina el link "¿Olvidaste tu contraseña?" y agrega aviso de contactar al administrador.
- **Sidebar**: link "Mi Perfil" añadido en la sección inferior para todos los usuarios autenticados.
- **Templates eliminados**: `auth/aceptar_invitacion.html`, `auth/reset_password.html`.
- **Tests**: `test_reset_password_ruta_eliminada`, `test_aceptar_invitacion_ruta_eliminada`, `test_mi_perfil_requiere_autenticacion` añadidos.

## [2.31.0] — 2026-05-20

### Añadido — Sistema multi-usuario con Supabase Auth

- **Autenticación**: reemplazo completo del sistema de usuario único (APP_USER/APP_PASSWORD_HASH) por Supabase Auth. Login por email + contraseña. Variables de entorno `APP_USER` y `APP_PASSWORD_HASH` eliminadas.
- **Roles**: tres niveles — `master_admin` (gestión completa + usuarios), `admin` (acceso completo a todos los clientes), `usuario_normal` (solo lectura de su empresa asignada).
- **BD**: tabla `user_profiles` (id UUID → auth.users, email, rol, empresa_id, activo). Migración: `storage/migrations/202606_multiusuario.sql`.
- **Flujo de invitación**: master_admin invita desde `/admin/usuarios` → Supabase envía email → usuario activa cuenta con contraseña propia en `/auth/aceptar-invitacion`.
- **Flujo reset password**: `/auth/reset-password` → email con link → nueva contraseña en `/auth/reset-password/nuevo`.
- **`web/auth.py`**: reescrito. Blueprint `auth_bp` con prefijo `/auth`. Helpers `set_user_session`, `clear_user_session`, `get_current_user`, `is_authenticated`. JWT decode sin PyJWT.
- **`web/auth_permissions.py`**: nuevo módulo con `usuario_puede_borrar`, `usuario_puede_crear`, `filtrar_empresas_para_usuario`, `validar_borrar_usuario`.
- **`web/app.py`**: `before_request` usa `is_authenticated()` (sin flask-login). `context_processor` inyecta `current_user_data`. Rutas `/admin/usuarios`, `/admin/usuarios/invitar`, `/admin/usuarios/<id>/borrar`, `/admin/usuarios/<id>/desactivar`. Endpoint `/health` añadido.
- **`web/clientes.py`**: `listado()` filtra por empresa para `usuario_normal`. `nuevo()` y `borrar()` verifican permisos.
- **Templates**: `auth/login.html` (email-based), `auth/reset_password.html`, `auth/reset_password_nuevo.html`, `auth/aceptar_invitacion.html` (JS extrae token del hash URL). `admin/usuarios.html` con tabla + modal de invitación. Sidebar muestra email, rol y link "Usuarios" para master_admin.
- **Tests**: `test_auth.py` reescrito; fixtures de todos los tests actualizados para inyectar sesión directamente (sin llamar a Supabase).

### Migración requerida

Ejecutar `storage/migrations/202606_multiusuario.sql` en Supabase SQL Editor. Luego crear el primer usuario `master_admin` directamente en Supabase Dashboard > Authentication > Users, e insertar su fila en `user_profiles` con `rol = 'master_admin'`.

## [2.30.0] — 2026-05-20

### Añadido — Medio térmico con mezcla configurable y RefH ponderado

- **UI ficha/editar/nuevo cliente**: dropdown de medio térmico ampliado a 4 opciones (sin especificar, vapor o agua caliente, gases de combustión directos, mezcla). Cuando se selecciona "Mezcla", aparece campo editable "% Vapor" (entero 0-100, default 50). JS oculta/muestra el campo según la selección.
- **BD**: columna `medio_termico_vapor_pct` (INTEGER 0-100) en tabla `clientes`. Migración: `storage/migrations/202605_medio_termico_mezcla.sql`.
- **`calc/cels.py`**: constantes `REFH_VAPOR = 0.90` y `REFH_GASES = 0.82`. Función `_calcular_ref_h(pct)` que pondera ambos medios. `calcular_cels` acepta `medio_termico_vapor_pct: int | None`; None → sin especificar → no calcula CELs.
- `storage/repository.py`: `create_cliente` y `update_cliente` persisten `medio_termico_vapor_pct`.

### Migración requerida

Ejecutar `storage/migrations/202605_medio_termico_mezcla.sql` manualmente en Supabase SQL Editor. Convierte clientes existentes con `vapor_agua` → `vapor_o_agua` (string) y `vapor_pct = 100`; `gases_combustion` → `vapor_pct = 0`.

## [2.28.1] — 2026-05-14

### Fix — CELs para contratos PPA

- **`web/app.py`**: eliminados los guards `if tipo_suministro != TIPO_ELECTRICO_CALIFICADO:` que suprimían el cálculo de CELs y de `energia_limpia_pct` para suministro calificado. Ambas métricas se calculan ahora con la misma función `calcular_cels()` independientemente del tipo de suministro eléctrico.
- **`web/static/js/dashboard-cogeneracion.js`**: eliminado `|| esPPA` del early-return de `recalcularCELs`; eliminada la rama `if (esPPA) { _renderCelsPPA() }` en `hidratarDashboardCogeneracion`. La caja CELs muestra el valor calculado para GDMTH y PPA por igual.
- **Fundamento**: los CELs los genera el motor de cogeneración (CRE Caso I) en función de su eficiencia termodinámica, no del tipo de suministro eléctrico del cliente. Suprimir los CELs para PPA era un error de interpretación.

## [2.28.0] — 2026-05-14

### Sub-entregable C — Dashboards adaptados al tipo de suministro eléctrico (PPA vs GDMTH)

- **Fix doble file picker**: `factura_calificado_upload.html` — reemplazado `<label for="file-input">` por `<span>` para que solo el click handler del drop zone dispare el selector de archivo.
- **Repository**: `get_tipo_suministro_electrico_seleccionado(cliente_id)` — retorna `'electrico_basico'` | `'electrico_calificado'` | `None` según los meses seleccionados activos.
- **`calc/cogen.py`**: `calcular_cogen_ppa(ppa_invoices, gas_invoices, params, ...)` — versión simplificada del motor de cogeneración para suministro calificado. Ahorro eléctrico = kWh cubiertos × precio promedio PPA (sin desglose horario, sin Capacidad/Distribución). 7 unit tests en `tests/calc/test_cogen_ppa.py`.
- **`storage/repository.py`**: `get_facturas_ppa_y_gas_para_dashboard(cliente_id)` — carga facturas PPA y gas en 3 queries con una sola llamada a `get_meses_seleccionados_por_cliente`.
- **`web/app.py`**: ambos endpoints HTML y ambos endpoints `/data` detectan `tipo_suministro_electrico` y despachan al path PPA (`calcular_cogen_ppa`) o GDMTH (`calcular_cogen`) según corresponda. JSON output incluye `tipo_suministro_electrico`, `suministrador_ppa`, `historico_ppa`.
- **Dashboard Contabilidad**: banner "Suministro: Calificado (PPA) — {suministrador}", KPIs y badge adaptados, secciones GDMTH (gráficas de demanda/consumo horario, costo unitario por horario, pie chart) se ocultan para PPA y se muestran dos gráficas PPA (consumo mensual vs precio, costo mensual). Destrucción de instancias Chart.js al cambiar modo.
- **Dashboard Cogeneración**: banner PPA, `recalcularPPA()` para sliders (sin greedy horario ni cálculo Capacidad/Distribución), dispatch `esPPA ? recalcularPPA : recalcularMes`, CELs card muestra "N/A" para PPA, etiqueta cascada adaptativa ("Ahorro Eléctrico (Total)" para PPA).
- Aviso `sin_par` y `sin_pares_mes` usan lenguaje genérico ("facturas eléctricas") en ambos dashboards.

## [2.27.0] — 2026-05-14

### Sub-entregable B completo — Parser GIN, upload PDF, bloqueo de mezcla

- **Parser GIN**: `parsers/electricidad_calificado/gin.py` con `GINParser` (hereda `InvoiceParser`) y `GINInvoice` dataclass. Extrae 15 campos de facturas GIN. Validado contra PDF real IBERICA TILES septiembre 2024 con 16 tests en `tests/parsers/test_gin.py`.
- **Upload PDF calificado**: Ruta `GET/POST /<cliente_id>/contratos/<contrato_id>/factura_calificado/upload`. Parsea PDF con `GINParser` → preview editable → confirma y guarda vía `factura_calificado_crear` (existente). Templates: `factura_calificado_upload.html`, `factura_calificado_preview.html`. Botón "+ Subir factura PPA (PDF)" en ficha de contrato calificado.
- **Bloqueo de mezcla CFE/PPA**: Cliente no puede tener meses seleccionados de contratos básico y calificado simultáneamente. HTTP 409 con mensaje descriptivo. Validación en `POST .../seleccion/mes` y `POST .../seleccion/anio`. Función `get_tipos_electricos_con_meses_seleccionados(cliente_id)` → list[str]. Tests: `tests/test_seleccion_mezcla.py` (5 tests).
- **Fixture test**: `tests/fixtures/calificado/GIN_2024_09_SEPTIEMBRE.pdf`.

## [2.26.0] - 2026-05-14

### Añadido (sub-entregable B: facturas de electricidad calificada PPA)
- CRUD completo de facturas de electricidad calificada: carga manual desde la ficha del contrato, edición y borrado. Tabla `facturas_electricidad_calificado`.
- Modelo `models/factura_calificado.py` (FacturaCalificado) con campos: consumo_kwh, precio_unitario_mxn_kwh, subtotal_mxn, iva_mxn, total_mxn, excedente_detectado, suministrador, rpu, serie_folio, periodo_inicio, periodo_fin, advertencias, pdf_url.
- Validaciones: período coherente, consumo y precio positivos, coherencia IVA+subtotal vs total (±1 MXN), sin duplicado por contrato/año/mes, detección de excedente vs bloque contratado (×110%).
- Nombre canónico automático: `CALIFICADO-{AAAA}-{MM}-{suministrador_slug}`.
- Funciones de repositorio: `create_factura_calificado`, `get_factura_calificado`, `get_facturas_calificado_por_contrato`, `get_facturas_calificado_por_cliente`, `update_factura_calificado`, `delete_factura_calificado`, `get_facturas_para_dashboard_calificado`.
- `get_sidebar_data_contrato` y `get_meses_con_factura` ahora despachan a la tabla correcta según `contrato_tipo`.
- `get_sidebar_data_cliente` incluye facturas calificadas en el agrupamiento del sidebar.
- Ficha de contrato calificado: oculta zona de upload PDF, muestra botón "+ Nueva factura calificada", tabla de facturas con editar y borrar.
- Template `web/templates/clientes/contratos/factura_calificado_form.html` para crear/editar.
- Ficha de contrato: badges y textos de tipo actualizados para los tres valores (`electrico_basico`, `electrico_calificado`, `gas`); contador de facturas adaptado por tipo.
- `CLAUDE.md` actualizado con sección "Facturas de electricidad calificada (PPA)".

## [2.25.3] - 2026-05-14

### Corregido
- Al guardar bloques mensuales via AJAX y cambiar de año, los valores guardados desaparecían al volver al año anterior. La variable `_ppaBloques` (cargada al abrir la página) no se actualizaba tras el save; `precargarBloques()` leía datos desactualizados. Fix: `actualizarBloqueEnMemoria()` sincroniza `_ppaBloques` con los valores del form inmediatamente después del "✓ Guardado.".

## [2.25.2] - 2026-05-14

### Corregido
- Formularios PPA ("Guardar datos PPA" y "Guardar bloques") no enviaban request al backend — al hacer submit Flask redirigía a la misma ficha y el acordeón se cerraba al recargar la página, aparentando que no hubo request. Convertidos a AJAX con `fetch()`: el acordeón permanece abierto, se muestra "✓ Guardado." inline durante 4 segundos.
- Inputs de bloques mensuales no precargaban los valores guardados en BD. La ruta `ficha()` ahora pasa `ppa_bloques` al template; JavaScript precarga los 12 campos al cargar la página y al cambiar el selector de año.

## [2.25.1] - 2026-05-14

### Corregido
- Sección "Suministro Calificado (PPA)" no aparecía en la ficha de cliente en el deploy inicial de v2.25.0. El template `web/templates/clientes/ficha.html` tenía los cambios pero Render necesitaba redeploy. Forzado con este bump de versión.

## [2.25.0] - 2026-05-14

### Añadido (sub-entregable A: modelo de datos PPA)
- Soporte de modelo de datos para clientes con suministro eléctrico calificado (PPA).
- Tabla `contratos`: tipo ahora acepta `electrico_basico`, `electrico_calificado`, `gas`. Contratos existentes con `electrico` migrados a `electrico_basico`.
- Tabla `clientes`: 12 campos nuevos para datos del contrato PPA (suministrador, RFC, RPU, precio fijo USD/MWh, fecha inicio, energía contratada, capacidad máxima, margen reserva CENACE, zona de carga, división, PDF URL, notas).
- Tabla nueva `ppa_bloques_mensuales`: bloques contratados MWh por mes/año por cliente.
- Tabla nueva `facturas_electricidad_calificado`: estructura preparada para sub-entregable B (carga de facturas PPA).
- Ficha de cliente: sección acordeón "Suministro Calificado (PPA)" con formulario editable y sub-sección de bloques mensuales.
- Formulario de contrato: tipo ahora ofrece tres opciones (Eléctrico básico CFE, Eléctrico calificado PPA, Gas).
- `models/contrato.py`: constantes `TIPO_ELECTRICO_BASICO`, `TIPO_ELECTRICO_CALIFICADO`, `TIPO_GAS`, `TIPOS_ELECTRICOS`, `TIPOS_VALIDOS`.
- Archivo de migración: `storage/migrations/202605_ppa_support.sql`.

### Documentación
- `CLAUDE.md` actualizado con sección "Suministro eléctrico: básico vs calificado".

### Pendiente (sub-entregables B y C)
- B: Carga manual de facturas calificadas y aparición en sidebar.
- C: Dashboard adaptado al tipo de suministro del cliente.

## [2.24.7] — 2026-05-14

### Corregido
- `kpi-energia-limpia-val` ahora se recalcula en cada movimiento de slider (antes solo se fijaba en la carga inicial). Fórmula: `(cels_mwh × 1000 / kwh_total_anual) × 100`. Muestra "N/D" en gris cuando el cliente no califica como cogeneración eficiente.
- Periodo de Retorno unificado: `calcularPaybackJS` acepta ahora `beneficioFiscal` como tercer parámetro y lo suma al acumulado del año 1. Elimina el bloque de override post-`actualizarSensibilidad` que usaba el valor del backend con ★ y se sobreescribía al mover sliders. El asterisco `*` con tooltip aparece junto al valor cuando `beneficioFiscalAnio1 > 0`.

## [2.24.6] — 2026-05-14

### Corregido
- Capacidad usada para selección de RefE en cálculo de CELs: antes usaba capacidad_instalada_kw del cliente (campo BD); ahora usa la capacidad calculada como math.ceil(max(kwh_total_mes / 720)), consistente con Inversión y Capacidad Nominal del dashboard.
- Redondeo techo (math.ceil) aplicado a la capacidad calculada en todos los puntos donde se usa: selección RefE, Inversión, Beneficio Fiscal año 1, visualización Capacidad Nominal (sin decimales).

## [2.24.5] — 2026-05-13

### Cambiado
- Botón toggle del sidebar (escritorio): más sutil y menos intrusivo. Fondo transparente, sin borde, 28px, color gris `#bbb`. Posicionado en la esquina superior del borde derecho del sidebar en lugar del centro vertical.

### Removido
- Icono de descarga Excel del dashboard de Cogeneración. Los iconos Excel permanecen en Contabilidad Energética.

## [2.24.4] — 2026-05-13

### Removido
- Donuts de composición de Ingresos y Gastos en el bloque 1 del dashboard de Cogeneración. No aportaban claridad visual. Bloque 1 recupera el layout de dos columnas numéricas simples.

## [2.24.3] — 2026-05-13

### Añadido
- Botón para ocultar/mostrar el sidebar (escritorio ≥ 1024px). Icono `bi-chevron-left/right` en el borde derecho del sidebar. Al ocultarlo, el contenido principal se expande a ancho completo con transición 300ms. Estado persistido en `localStorage` (clave `sidebar_collapsed`) entre sesiones y entre dashboards.
- Distinción visual de contratos en sidebar: contratos eléctricos en verde `#1F7A4C`, contratos de gas en ámbar `#d4a017`. Se aplica al nombre del contrato únicamente; meses y años mantienen su estilo.

## [2.24.2] — 2026-05-13

### Cambiado (visual)
- Donuts de composición de Ingresos y Gastos: integrados dentro del bloque 1 (al lado derecho de los números) con tamaño fijo 130×130px y sin leyenda. Antes ocupaban espacio descomunal debajo del bloque. Tooltip sigue mostrando porcentaje y valor MXN.
- Cascada de Ahorro Neto: movida justo arriba de la gráfica del flujo de 15 años. Altura fija 280px. Nueva sección titulada "Composición del Ahorro Neto Anual".

### Removido
- Donuts grandes del área inferior del bloque 1 (reemplazados por los mini donuts integrados).

## [2.24.1] — 2026-05-13

### Añadido
- Botón de descarga Excel (icono `bi-file-earmark-excel` verde) a la izquierda del enlace "Ver datos" en todas las gráficas de ambos dashboards (7 gráficas en total).
- Endpoint genérico `GET /clientes/<id>/grafica/<grafica_id>/excel` con 7 handlers: `ahorro_neto_mensual`, `demanda_por_horario`, `consumo_por_horario`, `costo_unitario_promedio`, `composicion_costo`, `gas_consumo`, `gas_costos`.
- Generación con BytesIO + openpyxl; sin archivos temporales en disco. Nombre del archivo: `{cliente} - {tabla}.xlsx`.

## [2.24.0] — 2026-05-13

### Añadido
- Caja "Energía Limpia Generada" en bloque 2 del dashboard de Cogeneración. Muestra % del consumo total cubierto con CELs (`(cels_mwh × 1000) / kwh_total × 100`). Para IBERICA TILES: ~25.5%.
- Beneficio fiscal año 1 en flujo acumulado de 15 años. Aplica 30% de inversión como deducción inmediata (Art. 34 fracción XIII LISR — cogeneración eficiente CRE). Barra del año 1 visiblemente más alta; tooltip explica el beneficio. Para IBERICA TILES: ~$14.4M MXN adicionales en año 1.
- Payback recalculado incluyendo beneficio fiscal del año 1. Se expone como `payback_con_beneficio` en el endpoint `/data`.
- Gráfica de cascada horizontal (waterfall) en bloque 1 mostrando composición: Ahorro Electricidad + Ahorro Caldera − Costo Gas − O&M = Ahorro Neto.
- Dos donut charts con composición de Ingresos (Electricidad vs Caldera) y Gastos (Gas vs O&M).

### Cambiado (visual)
- Bloque 2 del dashboard reestructurado de 3 a 4 columnas (col-sm-6 col-lg-3). Responsive 4/2×2/1.
- Tipografía e iconos unificados en las 4 cajas del bloque 2 con clase `.kpi-card-b2`.
- Icono Ahorro Neto: `bi-cash-coin` (verde). Icono CO₂: hoja SVG verde sólida (sustituye outline anterior). Icono CELs: `bi-shield-check` (mantiene). Icono Energía Limpia: `bi-lightning-charge` (verde).

### Backend
- Nuevos campos en `CoGenResultado`: `beneficio_fiscal_anio_1_mxn`, `flujo_anio_1_con_beneficio_mxn`, `energia_limpia_pct`.
- Constante `_TASA_ISR = Decimal("0.30")` a nivel de módulo en `calc/cogen.py`.
- Endpoint `/data` expone `kpis.beneficio_fiscal_anio_1_mxn`, `kpis.energia_limpia_pct`, `flujo_anual_15_fiscal`, `flujo_acum_15_fiscal`, `payback_con_beneficio`.

### Documentación
- CLAUDE.md actualizado con secciones "Energía Limpia Generada" y "Beneficio Fiscal por Depreciación Inmediata".

---

## [2.23.1] — 2026-05-13

### Corregido (metodología crítica)

- Ahorro Capacidad y Ahorro Distribución calculados incorrectamente en versiones anteriores. Implementación completa de la metodología CFE GDMTH con redondeo ceiling:

  - **Redondeo ceiling obligatorio**: CFE GDMTH deriva kW facturados como `ceil(kWh_total / (24 × días) / 0.57)`. Se aplica con `math.ceil()` tanto para la demanda actual (base del precio unitario) como para la demanda post-cogeneración (demanda proyectada). Implementado en `calc/cogen.py` y replicado con `Math.ceil()` en `dashboard-cogeneracion.js`.

  - **Fórmulas MIN correctas**: `kw_facturado_capacidad = min(kw_punta, ceil(D_actual))` y `kw_facturado_distribucion = min(kw_max, ceil(D_actual))`. Para la reducción post-cogen: `kw_efectiva_cap = min(kw_facturado_cap, ceil(D_post))` y `kw_efectiva_dist = min(kw_facturado_dist, ceil(D_post))`.

  - **Campo correcto para precio unitario**: el precio se deriva de `cargo_demanda_mxn` del componente MEM (no de `importe_mxn` que incluye otros cargos).

  - **Campos de transparencia**: `CoGenMes` expone ahora `kw_facturado_capacidad`, `kw_facturado_distribucion`, `kw_efectiva_capacidad_post`, `kw_efectiva_distribucion_post` para trazabilidad y sliders JS.

  Validado para IBERICA TILES enero 2024: ceil(1624.22) = 1,625 kW → kw_bill_cap = 1,456, kw_bill_dist = 1,625, D_post = 407 kW → Capacidad ≈ $420,701 ✓, Distribución ≈ $123,932 ✓, Ahorro Electricidad TOTAL ≈ $1,509,288 ✓.

---

## [2.23.0] — 2026-05-13

### Cambiado

- Metodología de cálculo del ahorro eléctrico en cogeneración: reemplazada la simplificación de costo promedio del kWh por el algoritmo greedy de 3 componentes MEM de la tarifa GDMTH. El consumo cubierto se asigna primero al horario más caro (punta), luego a intermedio, luego a base, hasta agotar la cobertura objetivo. Los cargos de Capacidad y Distribución se mantienen en cero (supuesto conservador: el motor tiene paradas mensuales y `kw_max` no cambia). Afecta `calc/cogen.py` y el slider JS `recalcularMes` en `dashboard-cogeneracion.js`.

- `CoGenMes` y `CoGenResultado` en `models/cogen_result.py` exponen ahora los 3 componentes del ahorro eléctrico (`ahorro_energia`, `ahorro_capacidad`, `ahorro_distribucion`) a nivel mensual y anual, y los kWh asignados por horario (`kwh_punta_cubierto`, `kwh_intermedia_cubierto`, `kwh_base_cubierto`) y los kWh totales facturados por horario (`kwh_punta_total`, `kwh_intermedia_total`, `kwh_base_total`) con sus costos unitarios (`cu_punta_kwh`, `cu_intermedia_kwh`, `cu_base_kwh`).

- Endpoint JSON `/dashboard/cogeneracion/data`: `meses_raw` expone los 6 campos por periodo necesarios para que el slider JS replique el algoritmo greedy sin llamar al servidor. `tabla_mensual`, `kpis` y `totales` incluyen los 3 componentes del ahorro eléctrico.

### Corregido

- Bug crítico de serialización en sesión Flask: `get_contratos_por_cliente` devuelve objetos `Contrato` (dataclass), que no son JSON-serializables por itsdangerous. Se aplica `asdict()` antes de guardar en `session`, lo que eliminaba el error en toda navegación posterior a la primera carga. Afecta `web/app.py`.

- `from time import time` y `from collections import defaultdict` movidos al nivel de módulo en `web/app.py` y `storage/repository.py` (estaban dentro de funciones).

- Decorador `@login_required` fantasma en `web/clientes.py` (línea 828): nunca fue importado, causaba `NameError` en los tests. Eliminado.

- 8 tests en `tests/test_dashboard_2d.py` actualizados para reflejar la arquitectura de renderizado client-side: las aserciones de texto HTML (inyectado por JS) se reemplazaron por verificación del endpoint JSON `/data`.

### Añadido (sesión anterior, incluido en este release)

- Prorrateo de facturas de gas: si el periodo tiene menos de 25 días, se escala a 30 días equivalentes al igual que CFE. Afecta `calc/periodo.py` y `calc/cogen.py`.

- Helper `_construir_queso` en `web/app.py` para centralizar la lógica del gráfico de distribución del gasto eléctrico.

- Caché de contratos en `context_processor` para evitar queries repetidas por request.

- Spinner de carga en dashboard de contabilidad (ya existía en cogeneración).

- KPI "Costo Total" en dashboard de contabilidad.

- Endpoint batch `POST /<cliente_id>/contratos/<contrato_id>/seleccion/anio` para selección/deselección masiva de todos los meses de un año.

---

## [2.22.1] — 2026-05-12

### Corregido

- Bug introducido en v2.22.0: tras refactor a event delegation, el evento `dashboardDataChanged` no se disparaba tras toggle de mes. El dashboard quedaba con datos viejos hasta recarga manual. Causa raíz: `btn.closest("[data-anio]")` retornaba el propio botón (que tiene `data-anio` asignado), por lo que `maestroChk` era `null`, `actualizarMaestro` lanzaba TypeError, y el dispatch nunca alcanzaba a ejecutarse. Fix: `btn.parentElement.closest("[data-anio]")` para saltar el botón y encontrar el contenedor del año. Añadido guard `if (maestroChk)` antes de `actualizarMaestro` para que el dispatch siempre ocurra tras AJAX exitoso.

---

## [2.22.0] — 2026-05-11

### Performance

- Eliminados listeners por elemento en checkboxes/botones del sidebar. Ahora hay UN solo listener delegado en `#sidebar` para todos los clicks en `.mes-btn` y UN solo listener delegado para cambios en `.maestro-anio`. Antes cada botón de mes y cada checkbox de año tenía su propio `addEventListener`, lo que podía resultar en listeners duplicados. Ahora: cero handlers por elemento, un solo handler por tipo de evento en el contenedor padre.

- Debounce de 300ms ya operativo en ambos dashboards (`dashboard-cogeneracion.js`, `dashboard-contabilidad.js`). Clicks rápidos consecutivos en meses disparan UN solo fetch al endpoint `/data` al finalizar la ráfaga.

- Endpoint `/dashboard/cogeneracion/data` optimizado de 10 queries a 6 queries a Supabase. Nueva función `get_facturas_para_dashboard` comparte la consulta de meses seleccionados entre CFE y gas (−2 queries duplicadas). Las 3 llamadas separadas a `get_configuracion` reemplazadas por 1 `list_configuracion` con lookup en dict (−2 queries adicionales). Lo mismo aplicado al endpoint SSR de cogeneración. Ahorro estimado: ~400–600ms en latencia de red por request.

- Transición visual fluida activada en ambos dashboards: `showSpinner` aplica `opacity: 0.5` sobre `#dashboard-main-content` al iniciar fetch; `hideSpinner` lo restaura con `transition: opacity 0.15s`.

---

## [2.21.0] — 2026-05-11

### Corregido

- Open redirect en `/login`: el parámetro `next` ya se valida con `urllib.parse`; solo se acepta si es una URL relativa (empieza por `/`, sin `//`, sin esquema ni host). Afecta `web/auth.py`.
- XSS por `innerHTML` con datos del servidor en `dashboard-cogeneracion.js` (`actualizarAviso`, `actualizarCELsCard`, bloque CO2) y `dashboard-contabilidad.js` (`actualizarAviso`). Reemplazado por construcción explícita de DOM con `createElement`/`textContent`/`setAttribute`.
- Selección de mes sin factura: `POST .../seleccion/mes` ahora valida que exista al menos una factura para (contrato_id, anio, mes) antes de insertar en `contrato_meses_seleccionados`. Devuelve 400 si no hay factura. El `DELETE` (deselección) sigue siendo libre. Afecta `web/clientes.py`.
- N+1 queries en `get_sidebar_data_contrato`: consolida de 2+N×2+1 queries a 3 fijas (CFE, gas, seleccionados), agrupando en Python con `defaultdict`. Afecta `storage/repository.py`.
- `print()` en `calc/cogen.py` reemplazado por `logger.warning()`. Añadido logger de módulo con `logging.getLogger(__name__)`.

### Añadido

- `render.yaml`: variables `SECRET_KEY`, `APP_USER` y `APP_PASSWORD_HASH` declaradas con `sync: false`. Antes solo estaban `SUPABASE_URL` y `SUPABASE_KEY`.

### Cambiado

- `storage/schema.sql`: actualizado para reflejar el schema real. Añadidas tablas `contratos`, `contrato_meses_seleccionados`, `configuracion`. Añadidas columnas `contrato_id`, `nombre_canonico`, `anio`, `mes`, `advertencias` en `cfe_facturas` y `gas_facturas`. Añadidos campos CELs en `clientes`. Añadidos ON DELETE CASCADE/SET NULL, índices.
- `CLAUDE.md`: schema actualizado, descripción O&M corregida, nuevas secciones de arquitectura de contratos y configuración del sistema.
- `calc/cogen.py`: comentario en el cálculo de `ahorro_electricidad` explica la simplificación de usar costo promedio del kWh en lugar de costo por horario.

---

## [2.20.0] — 2026-05-11

### Corregido

- Fórmula de Gasto O&M en cogeneración. Antes calculaba como porcentaje (30%) del ahorro eléctrico en MXN (`kwh_cubiertos × $/kWh × 0.3`). Ahora correctamente como 0.3 MXN fijos por kWh cubierto (`kwh_cubiertos × 0.3`). Los valores anteriores de O&M estaban sobreestimados aproximadamente 2–3× (dependiendo del costo promedio del kWh), y el Ahorro Neto correspondiente estaba subestimado en la misma magnitud. Afecta `calc/cogen.py`, slider JS en `dashboard-cogeneracion.js` y tests.

---

## [2.19.1] — 2026-05-10

### Corregido

- `/admin/configuracion` solo mostraba el tipo de cambio. Ahora lista y permite editar todas las claves de la tabla `configuracion` de forma dinámica. Al insertar una clave nueva en BD, aparece automáticamente sin cambios de código. Validaciones específicas por clave: tipo de cambio (10–30), factor emisión electricidad (0.1–2.0), factor emisión gas (10–200). Claves desconocidas se validan como número positivo. Indicador visual de campo modificado (borde izquierdo verde).

---

## [2.19.0] — 2026-05-09

### Cambiado

- Sub-entregable G: renderizado client-side en ambos dashboards. Los dos dashboards (Contabilidad y Cogeneración) ahora obtienen sus datos vía fetch JSON al cargar y al cambiar la selección de meses, sin recarga de página. Nuevos endpoints `GET /clientes/<id>/dashboard/contabilidad/data` y `GET /clientes/<id>/dashboard/cogeneracion/data`. Nuevos módulos JS `dashboard-contabilidad.js` y `dashboard-cogeneracion.js` (patrón IIFE, Chart.js upsert, AbortController, debounce 300 ms, timeout 10 s, preservación de scroll). Los sliders de cogeneración siguen recalculando 100 % client-side sin llamar al endpoint. Spinner fijo en esquina superior derecha con fade-out; banner de error con botón "Reintentar".

---

## [2.18.0] — 2026-05-09

### Añadido

- Cálculo de Certificados de Energías Limpias (CELs) según metodología CRE Caso I (RES/1838/2016). Nuevo módulo `calc/cels.py` con función `calcular_cels`: tablas de RefE principal y alternativa (altitud), RefH por medio térmico, fp por nivel de tensión, fórmulas EP/AEP/ELC completas.
- Cuatro campos nuevos en la ficha del cliente: medio térmico de cogeneración, nivel de tensión de interconexión, altitud (msnm) y tipo de motor. Formularios de crear y editar actualizados. Sección "Datos regulatorios cogeneración (CELs)" en la ficha.
- Tarjeta "CELs Generados" en el dashboard de cogeneración (tercera columna junto a Ahorro Neto y Reducción CO₂). Tres estados: datos incompletos / cogeneración eficiente / no califica. Actualización reactiva al mover los sliders de sensibilidad.
- Panel flotante "Detalle Cálculo CELs según CRE (Caso I)" con todas las variables intermedias (E, F, H, Fh, Fe, EE, EP, AEP, APEP, AREL, ELC, %ELC) en tabla monoespaciada. Se actualiza reactivamente con los sliders.
- Campo `gj_gas_cogen_pci_anual` en `CoGenResultado`: energía de gas en PCI (sin factor 1.11) para uso exclusivo del cálculo regulatorio CELs.
- 15 tests nuevos en `tests/test_cels.py`: tablas de RefE, RefH, fp, lógica híbrida de capacidad, bug PCI/PCS, H=0 no eficiente, datos completos/incompletos.

### Cambiado

- Fila "Ahorro Neto + Huella de Carbono" reestructurada a tres columnas de igual ancho (`col-md-4`).
- Icono del árbol en "Reducción Huella de Carbono" cambiado de `bi-tree-fill` a SVG outline.

### Corregido

- Nombre del cliente en el listado aparecía en negrita y tamaño mayor al resto de celdas. Eliminado `<span class="fw-semibold" style="font-size:1rem">` y unificado con clase `small` igual que RFC, facturas y fecha.

---

## [2.17.0] — 2026-05-09

### Cambiado

- Dashboard cogeneración: eliminada sección "Huella de Carbono" con los dos donuts comparativos. La reducción de CO₂ se muestra ahora como tarjeta compacta con icono de árbol junto al Ahorro Neto Anual, en diseño de dos columnas. La tarjeta se actualiza reactivamente al mover los sliders.

---

## [2.16.0] — 2026-05-09

### Añadido

- Bloqueo de acceso en pantallas < 1024px: pantalla de bloqueo de página completa en todas las rutas (incluyendo login) con mensaje informativo de escritorio. Implementado con media query CSS, sin parpadeo en el primer render.
- Buscador en tiempo real en el listado de clientes: filtra por nombre, RFC, contacto y email. Case-insensitive, sin recarga de página.
- Ordenamiento por columna en el listado de clientes: Nombre, RFC, Facturas CFE, Facturas Gas, Alta. Indicador de dirección (▲/▼). Click alterna asc/desc; cambio de columna reinicia a ascendente.
- Badges de estado junto al nombre del cliente: "Sin facturas" (gris) si no tiene ninguna, "Solo CFE" o "Solo gas" (amarillo) si le falta una de las dos. Sin badge si tiene ambas.
- Conteo de clientes sobre la tabla: muestra total o "Mostrando N de M clientes" cuando hay filtro activo.
- Click en fila completa navega a la ficha del cliente. Cursor pointer y hover suave. Los botones de acción bloquean la propagación.

### Cambiado

- Ficha del cliente: eliminado botón "Ver dashboard" de las acciones.
- Ficha del cliente: eliminada columna "Editar" de la tabla de contratos (la edición sigue accesible desde la ficha del contrato).

---

## [2.15.0] — 2026-05-08

### Añadido

- Sidebar expandible por contrato: cada contrato del cliente activo aparece como sección colapsable en el sidebar; la primera expansión hace un fetch AJAX que carga años con facturas y estado de selección por mes, cacheado para expansiones posteriores.
- Selección de meses por contrato: rejilla de botones mes por año con tres estados (disponible, seleccionado, no-disponible). Checkbox maestro por año (selecciona/deselecciona todos los meses con factura). Botón "Ver años anteriores" si hay más de 3 años.
- Tres nuevos endpoints REST en el blueprint de clientes: `GET /<cliente_id>/contratos/<contrato_id>/seleccion` (datos del sidebar), `POST /seleccion/mes` (toggle de un mes), `POST /seleccion/anio` (selección masiva de año).
- Nueva tabla `contrato_meses_seleccionados(contrato_id, anio, mes)` con clave primaria compuesta y FK en cascada hacia `contratos`.
- Columnas `anio` y `mes` en `cfe_facturas` y `gas_facturas`, pobladas al momento de guardar la factura usando `mes_asociado`.
- Script de migración `scripts/migrar_seleccion_a_meses.py`: (1) puebla `anio`/`mes` en facturas existentes con `contrato_id NOT NULL`; (2) inserta en `contrato_meses_seleccionados` todas las combinaciones únicas. Idempotente.
- Etiqueta de periodo en el encabezado de ambos dashboards: muestra el año o rango de años de las facturas seleccionadas.
- Botón "Detalles" en el encabezado del sidebar de cliente activo, en lugar del link separado "Ficha cliente".

### Cambiado

- La selección de facturas pasa de columna booleana `seleccionada` en cada factura a tabla `contrato_meses_seleccionados`. Las columnas `seleccionada` han sido eliminadas del schema.
- Los loaders de dashboard (`get_cfe_invoices_for_dashboard`, `get_gas_invoices_for_dashboard`) filtran ahora por meses seleccionados en lugar de por flag booleano.
- La ficha del contrato ya no muestra checkboxes de selección; indica que la selección se gestiona desde el sidebar.
- Mensaje informativo en ambos dashboards sin datos actualizado para orientar al usuario al sidebar.
- Tamaño de fuente de los links principales del sidebar igualado a `.8rem`.

---

## [2.14.0] — 2026-05-09

### Añadido

- Sección "Huella de Carbono" en el dashboard de Cogeneración: dos donuts comparativos (huella actual sin cogeneración vs. huella proyectada con cogeneración) y caja resumen con reducción anual en toneladas CO₂, porcentaje y equivalencia en árboles.
- Nuevos campos en `CoGenResultado`: `co2_actual_electricidad_kg_anual`, `co2_actual_gas_kg_anual`, `co2_actual_total_kg_anual`, `co2_proyectado_electricidad_kg_anual`, `co2_proyectado_gas_kg_anual`, `co2_proyectado_total_kg_anual`, `co2_reduccion_kg_anual`, `co2_reduccion_porcentaje`. Todos `Decimal | None`.
- Dos nuevas claves en tabla `configuracion`: `factor_emision_electricidad_kg_co2_kwh` (0.435) y `factor_emision_gas_kg_co2_gj` (56.1). Si no están configuradas, la sección de huella no aparece.
- Reactividad al slider de cobertura y rendimientos: el donut proyectado y la caja resumen se recalculan en JS sin recarga de página. El donut actual es fijo.

### Cambiado

- `calcular_cogen` acepta dos nuevos parámetros opcionales: `factor_emision_elec` y `factor_emision_gas` (ambos `Decimal | None`, default `None`).

---

## [2.13.0] — 2026-05-08

### Añadido

- Capacidad nominal del motor: calculada como `max(kWh_mes) / 720 h` sobre las facturas CFE seleccionadas con los tres horarios completos.
- Inversión estimada: `capacidad_nominal_kw × 1 400 USD/kW`, convertida a MXN con el tipo de cambio configurable.
- Periodo de retorno (payback): calculado hasta un horizonte de 15 años; devuelve el año de cruce, "no_aplica" si el ahorro neto es ≤ 0, o "mayor_horizonte" si supera los 15 años.
- Tres nuevas tarjetas KPI en el dashboard cogeneración: Capacidad Nominal, Inversión (USD y MXN) y Periodo de Retorno.
- Gráfica de flujo de caja a 15 años: barras de flujo anual, línea de flujo acumulado y línea de referencia en cero. Se actualiza reactivamente al mover los sliders.
- Página de administración `/admin/configuracion`: permite establecer el tipo de cambio MXN/USD (rango 10–30) con persistencia en tabla `configuracion` de Supabase. Accesible desde el sidebar bajo "Administración".

### Cambiado

- `calcular_cogen` acepta parámetro `tipo_cambio` (Decimal, default 17.50) para permitir personalizar la conversión USD→MXN.
- El tipo de cambio se lee de la base de datos en cada petición al dashboard de cogeneración; si no está configurado usa 17.50 como fallback.

---

## [2.12.0] — 2026-05-08

### Añadido

- Dashboard cogeneración reestructurado: KPIs organizados en tres secciones (Ingresos, Gastos, Ahorro Neto) con color condicional rojo/verde según signo del resultado.
- O&M estimado: nuevo KPI mensual y anual calculado como 30 % del ahorro eléctrico. Incluye campo `gasto_om_mes_mxn` en `CoGenMes` y `gasto_om_anual_mxn` en `CoGenResultado`.
- Tabla mensual de cogeneración movida a panel flotante (igual que contabilidad); accesible mediante enlace "Ver datos" en el encabezado de la gráfica.
- Gráfica cogeneración: nuevo dataset "O&M" apilado como gasto; línea renombrada de "EBITDA" a "Ahorro Neto".

### Cambiado

- Corrección PCS/PCI aplicada al consumo de gas del motor: `gj_gas_cogen` se multiplica por el factor 1.11. El gas natural se cotiza en Poder Calorífico Superior (PCS) pero el rendimiento eléctrico del motor se define sobre Poder Calorífico Inferior (PCI); sin la corrección el consumo de gas se subestimaba un 11 %. La constante vive en `calc/cogen.py` como `_FACTOR_PCI_A_PCS = Decimal("1.11")`.
- "EBITDA" renombrado a "Ahorro Neto" en dashboard, template y gráfica. El cálculo ahora resta también el O&M.
- Fórmulas Excel actualizadas: `gj_gas_cogen` incorpora el factor 1.11; la columna "EBITDA Mes" pasa a llamarse "Ahorro Neto Mes" e incluye el descuento de O&M (30 % del ahorro eléctrico).
- Sliders de sensibilidad actualizados para aplicar el factor 1.11 y el O&M en el recálculo en tiempo real.

---

## [2.11.0] — 2026-05-08

### Añadido

- Selección de facturas por contrato: checkboxes individuales y selección masiva por contrato.
- Dashboard filtrado: el análisis de cogeneración usa exclusivamente las facturas marcadas como seleccionadas.
- Sesión de cliente activo: al abrir la ficha de un cliente queda activo en la sesión. El sidebar muestra la sección contextual con acceso directo a Ficha, contratos y Dashboard.
- Sub-items de contratos en el sidebar: cada contrato del cliente activo aparece como enlace directo bajo la Ficha.
- Diseño visual renovado: paleta verde corporativa, sidebar rediseñado, login de dos columnas con propuesta de valor.
- Changelog accesible desde el sidebar.

### Cambiado

- Sidebar: ancho aumentado a 240 px, nueva cabecera con título y subtítulo, footer con versión y texto legal.
- Dashboard: colores de KPI cards y gráficas actualizados a la paleta corporativa.
- Templates: eliminados colores azules hardcodeados; toda la paleta centralizada en `theme.css`.

### Corregido

- El context processor ahora inyecta los contratos del cliente activo en cada petición autenticada para poblar el sidebar.

---

## [2.10.0] — 2026-04-30

### Añadido

- Soporte multi-contrato: un cliente puede tener múltiples contratos eléctricos y de gas.
- Upload de facturas por contrato (`/clientes/<id>/contratos/<id>/upload`).
- Ficha de contrato con listado de facturas y botones de borrado individual.
- Tablas históricas en el dashboard: consumos y demandas, costos detallados por componente, indicadores de eficiencia.

---

## [2.9.0] — 2026-04-15

### Añadido

- Módulo de clientes: alta, edición y baja con confirmación por nombre.
- Dashboard de cogeneración filtrado por cliente.
- Exportación a Excel con tabla mensual completa.
- Sliders de sensibilidad para parámetros del motor candidato.
- Autenticación con usuario y contraseña hash almacenada en variables de entorno.
