# Changelog

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
