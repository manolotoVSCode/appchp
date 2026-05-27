# Changelog

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
