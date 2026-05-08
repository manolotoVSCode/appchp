# Changelog

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
