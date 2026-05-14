# Changelog

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
