# Proyecto: chpapp

## Qué es

Aplicación web que analiza facturas de electricidad (CFE) y gas natural (ENGIE) de un cliente industrial mexicano, y calcula el ahorro neto y EBITDA mensual y anual de un proyecto de cogeneración con motor de gas natural. Cuantifica ahorro eléctrico por horario tarifario, recuperación de calor, costo de gas adicional y resultado neto.

Es una herramienta de uso interno del equipo comercial. No es producto SaaS para cliente final en su estado actual. El acceso del cliente o de personal del equipo fuera de México se hace siempre bajo presencia y control del operador.

Es la fase 1 de un proyecto mayor que evolucionará a SaaS multi-tenant de gestión energética, con monitoreo en tiempo real, IoT, módulos de mantenimiento, contexto regulatorio y API pública. Todo lo construido en fase 1 debe ser reutilizable en fases posteriores.

## Alcance estricto de fase 1

Dentro del alcance.

Parser de un solo modelo de factura CFE (tarifa GDMTH). Parser de facturas de un solo distribuidor de gas natural (ENGIE). Motor de cálculo de oportunidad de cogeneración con parámetros configurables vía sliders. Persistencia en Supabase. Dashboard web con visualización y sliders de sensibilidad. Generación de reporte de salida en Excel.

Fuera de alcance en fase 1.

Gestión de motores como activos. Alertas u órdenes de servicio. Aplicación móvil. Conectividad IoT o telemetría en tiempo real. API pública para terceros. Multi-tenant con aislamiento de datos por cliente. Autenticación robusta de usuarios externos.

## Stack tecnológico

Lenguaje: Python 3.11.

Backend web: Flask 3.x.

Persistencia: Supabase (PostgreSQL administrado) accedido vía SDK supabase-py por HTTPS. No se usa psycopg2 ni conexión directa al puerto 5432.

Extracción de PDF: pdfplumber con expresiones regulares para campos específicos.

Frontend: Bootstrap 5.3, Chart.js, Jinja2 templates servidos por Flask. Sin SPA.

Generación de reportes: openpyxl para Excel.

Tests: pytest. Combinación de tests unitarios con mocks del cliente Supabase y tests de integración mínimos contra una base Supabase de desarrollo separada.

Despliegue: Render free tier.

Gestión de dependencias: pip con requirements.txt.

## Decisiones arquitectónicas establecidas

El acceso a base de datos se hace exclusivamente vía supabase-py. No se mezclan psycopg2 ni acceso SQL directo. Esto desacopla la aplicación del proveedor de hosting (no requiere puerto 5432 abierto) y aprovecha capacidades nativas de Supabase como joins embebidos.

El patrón repository es la única vía de acceso a datos desde el resto de la aplicación. La capa web, los parsers y el motor de cálculo no manejan conexiones, dicts crudos ni cursores. Reciben y devuelven objetos de dominio.

El cliente Supabase se inicializa como singleton a nivel de módulo en storage/repository.py, leyendo SUPABASE_URL y SUPABASE_KEY de variables de entorno. Los tests reemplazan el singleton por mocks vía unittest.mock.patch.

La inicialización de schema no vive en código de aplicación. Las tablas existen en Supabase como infraestructura preestablecida. El DDL se documenta en storage/schema.sql como referencia, no se ejecuta en runtime.

Los campos numéricos en Supabase están tipados como text para preservar exactitud del PDF original. Toda aritmética del cálculo debe convertir explícitamente a Decimal, no a float.

## Aislamiento de fase 2

Las rutas y funcionalidades de fase 2 (telemetría, IoT, monitoreo en tiempo real) están aisladas mediante dos mecanismos: un feature flag de entorno y un decorador de acceso.

Variable de entorno `FASE2_HABILITADA` (valor `true`|`false`, defecto `false`). Se lee en `create_app()` y se almacena en `app.config["FASE2_HABILITADA"]`. Un context_processor inyecta `fase2_habilitada` en todos los templates para condicionar la UI sin consultar la config en cada vista.

Decorador `@require_master_admin_y_fase2` en `web/auth_permissions.py`. Si la flag está apagada devuelve 404 (la ruta no existe desde el punto de vista del cliente). Si la flag está encendida pero el rol no es `master_admin` devuelve 403. Esto permite exponer funcionalidades beta exclusivamente al operador autorizado durante la construcción de fase 2, sin necesidad de ramas de código separadas.

El sidebar muestra el bloque "Telemetría (Beta)" solo cuando `fase2_habilitada` es `True` y el usuario es `master_admin`. Los enlaces concretos de la sección se añadirán en entregas posteriores de fase 2.

## Schema de Supabase (tablas existentes)

clientes: id, nombre, rfc (único), notas, created_at, sector_industrial, contacto_nombre, contacto_cargo, contacto_email, contacto_telefono, direccion, estado, codigo_postal, tarifa_cfe, capacidad_instalada_kw, demanda_contratada_kw, anio_inicio_operacion, regimen_operacion, consumo_anual_estimado_mwh, logo_url, medio_termico, medio_termico_vapor_pct (INTEGER 0-100), nivel_tension_kv, altitud_msnm, tipo_motor.

contratos: id, cliente_id (FK clientes ON DELETE CASCADE), nombre, tipo ('electrico'|'gas'), identificador_real, notas, created_at.

cfe_facturas: id, cliente_id (FK clientes ON DELETE CASCADE), contrato_id (FK contratos ON DELETE SET NULL), uuid_cfdi, folio, serie, fecha_emision, periodo_inicio, periodo_fin, fecha_limite_pago, numero_servicio, rmu, tarifa, numero_medidor, multiplicador, carga_conectada_kw, demanda_contratada_kw, kw_max, kvarh, factor_potencia_pct, cargo_fijo_mxn, energia_total_mxn, cargo_factor_potencia_mxn, subtotal_mxn, iva_mxn, facturacion_periodo_mxn, derecho_alumbrado_publico_mxn, credito_aplicado_mxn, total_mxn, pdf_path, advertencias (JSON array), nombre_canonico, anio, mes.

cfe_periodos: id, factura_id (FK cfe_facturas ON DELETE CASCADE), periodo (base, intermedio, punta), consumo_kwh, demanda_kw, costo_unitario_kwh.

cfe_mem_componentes: id, factura_id (FK cfe_facturas ON DELETE CASCADE), nombre, cargo_fijo_mxn, cargo_demanda_mxn, cargo_energia_mxn, importe_mxn.

gas_facturas: id, cliente_id (FK clientes ON DELETE CASCADE), contrato_id (FK contratos ON DELETE SET NULL), uuid_cfdi, folio, fecha_emision, periodo_inicio, periodo_fin, fecha_limite_pago, nombre_proveedor, rfc_proveedor, numero_cliente, cuenta_contrato, punto_suministro, numero_caseta, tipo_lectura, consumo_m3_corregidos, consumo_sin_corregir_m3, poder_calorifico_gj_m3, consumo_total_gj, costo_unitario_total_gj, subtotal_mxn, iva_mxn, total_mxn, pdf_path, advertencias (JSON array), nombre_canonico, anio, mes.

gas_conceptos: id, factura_id (FK gas_facturas ON DELETE CASCADE), descripcion, clave_producto, cantidad_gj, precio_unitario_gj, importe_mxn.

contrato_meses_seleccionados: PK(contrato_id, anio, mes). FK contrato_id → contratos ON DELETE CASCADE.

configuracion: clave (PK), valor, descripcion, updated_at. Claves activas: tipo_cambio_mxn_usd, factor_emision_electricidad_kg_co2_kwh, factor_emision_gas_kg_co2_gj.

user_profiles: id (UUID PK → auth.users), email (TEXT), rol (TEXT: master_admin|admin|usuario_normal), empresa_id (INT NULL → clientes), activo (BOOL), created_at.

## Arquitectura de contratos y selección de meses

Un cliente puede tener múltiples contratos (`contratos`), cada uno de tipo 'electrico' o 'gas'. Las facturas CFE y de gas se vinculan a un contrato mediante `contrato_id`. Los dashboards filtran por meses seleccionados en la tabla `contrato_meses_seleccionados` (combinación única contrato_id + anio + mes). La selección se gestiona desde el sidebar expandible en la ficha del cliente: fetch AJAX al endpoint `GET /<cliente_id>/contratos/<contrato_id>/seleccion`, toggle individual vía `POST .../seleccion/mes`, selección masiva por año vía `POST .../seleccion/anio`. Solo se puede seleccionar un mes si existe al menos una factura (CFE o gas) para ese contrato/año/mes.

## Configuración del sistema

Parámetros globales editables en `/admin/configuracion` (requiere autenticación). Se persisten en la tabla `configuracion` de Supabase. Al agregar una clave nueva directamente en BD, aparece automáticamente en la UI sin cambios de código. Validaciones por clave: tipo_cambio_mxn_usd (10–30), factor_emision_electricidad_kg_co2_kwh (0.1–2.0), factor_emision_gas_kg_co2_gj (10–200). Claves desconocidas se validan como número positivo.

## Variables de entorno requeridas

SUPABASE_URL: URL del proyecto Supabase.
SUPABASE_KEY: clave service_role del proyecto. Ver sección de seguridad y deuda técnica.
SECRET_KEY: clave secreta de Flask para firmar cookies de sesión. Generar con `python3 -c "import secrets; print(secrets.token_hex(32))"`. Obligatoria en producción; si se omite, la app regenera una clave en cada reinicio invalidando todas las sesiones.

APP_USER y APP_PASSWORD_HASH fueron eliminadas en v2.31.0. La autenticación ahora usa Supabase Auth con email + contraseña. Los usuarios se gestionan desde `/admin/usuarios` (solo master_admin).

## Autenticación y roles (desde v2.32.0)

La app usa Supabase Auth (email + contraseña). No hay credenciales en variables de entorno.

Roles disponibles en `user_profiles.rol`:
- master_admin: acceso completo + gestión de usuarios en `/admin/usuarios`. No puede borrarse a sí mismo.
- admin: acceso completo a todos los clientes y facturas. No puede gestionar usuarios.
- usuario_normal: acceso de solo lectura a la empresa asignada (`empresa_id`). No puede borrar ni crear clientes.

Flujos de autenticación:
- Login: POST `/auth/login` con email + contraseña → `supabase.auth.sign_in_with_password` → sesión Flask.
- Logout: GET `/auth/logout` → limpia sesión Flask.
- Crear usuario: master_admin crea directamente desde `/admin/usuarios` (modal) → POST `/admin/usuarios/crear` → Supabase crea usuario con `email_confirm: True` y contraseña manual o generada. La contraseña se muestra una sola vez con alerta amarilla.
- Cambiar contraseña (admin): POST `/admin/usuarios/<id>/cambiar-password` → master_admin puede cambiar a cualquiera excepto otro master_admin; admin solo a usuario_normal y a sí mismo.
- Cambiar contraseña (propio): GET `/mi-perfil` → POST `/mi-perfil/cambiar-password`.
- Flujos eliminados en v2.32.0: invitación por email (`/auth/aceptar-invitacion`), reset password por email (`/auth/reset-password`).

Archivos clave:
- `web/auth.py`: Blueprint `auth_bp` (prefijo `/auth`), helpers `set_user_session`, `clear_user_session`, `get_current_user`, `is_authenticated`.
- `web/auth_permissions.py`: `usuario_puede_borrar`, `usuario_puede_crear`, `filtrar_empresas_para_usuario`, `validar_borrar_usuario`.
- Sesión Flask: claves `_user_id`, `_user_email`, `_user_rol`, `_empresa_id`, `_access_token`.
- Rutas públicas: `/auth/*`, `/healthz`, `/health`, `/static/*`.

Tests: sesión se inyecta directamente con `client.session_transaction()` (no llamar a Supabase). Ver `tests/test_auth.py`.

## Seguridad y deuda técnica reconocida

La aplicación usa la clave service_role de Supabase, que bypasea Row Level Security. Esto es deuda técnica explícita y aceptada para fase 1. La clave service_role debe vivir exclusivamente en variables de entorno del servidor backend.

La migración a clave anon con RLS por usuario/tenant es trabajo planeado para fases posteriores.

## Capacidad nominal del proyecto

La capacidad nominal de la cogeneración se calcula como:

capacidad_nominal_kw = math.ceil(max(kwh_total_mes / (dias_mes × 24)))

Donde:
- kwh_total_mes es la suma de kWh consumidos por horario (Base + Intermedia + Punta) de cada factura CFE seleccionada.
- dias_mes = (periodo_fin - periodo_inicio).days de cada factura (dinámico, no 720 fijo).
- Se toma el mes con mayor kWh/h entre los meses seleccionados.
- Se aplica math.ceil para redondear al entero superior, por consistencia con la metodología CFE GDMTH.

Para PPA la misma fórmula aplica usando los días de cada factura de electricidad calificada.

Esta capacidad se usa para:
- Selección de RefE en tabla CRE (cálculo de CELs).
- Cálculo de Inversión MXN.
- Visualización en caja "Capacidad Nominal" del dashboard.
- Cálculo del Beneficio Fiscal año 1 (vía inversión).

El campo capacidad_instalada_kw en BD no se usa para estos cálculos. Es información del cliente (demanda contratada CFE).

## Suministro eléctrico: básico vs calificado

La app soporta dos modalidades de suministro eléctrico, configurables por contrato.

Suministro básico (electrico_basico). Cliente recibe electricidad de CFE bajo tarifa GDMTH. Factura con desglose horario (Base/Intermedia/Punta), demandas kW, componentes MEM. Parser CFE GDMTH activo.

Suministro calificado (electrico_calificado). Cliente tiene contrato PPA con suministrador privado (calificado). Factura más simple: consumo MWh × precio unitario combinado, sin desglose horario. Datos del contrato PPA se capturan manualmente en la ficha del cliente.

Gas (gas). Sin cambios. Factura ENGIE u otro proveedor de gas natural.

CAMPOS DEL CONTRATO PPA EN FICHA DE CLIENTE

Campos editables en ficha del cliente, sección "Suministro Calificado (PPA)" (acordeón colapsable): suministrador, RFC suministrador, RPU, división, zona de carga CENACE, precio fijo USD/MWh, fecha inicio suministro, energía contratada anual MWh, capacidad máxima kW, margen reserva CENACE (%), URL PDF contrato, notas. Todos opcionales.

Endpoints: POST /clientes/<id>/ppa/datos (actualiza campos PPA del cliente), POST /clientes/<id>/ppa/bloques (actualiza bloques mensuales contratados MWh para un año).

BLOQUES MENSUALES CONTRATADOS

Por año contractual, el cliente tiene un bloque mensual contratado en MWh, capturado manualmente en la ficha. Tabla ppa_bloques_mensuales. Usado en sub-entregable C para detectar excedentes (consumo real vs bloque × 110%).

CONSTANTES DE TIPO EN models/contrato.py

TIPO_ELECTRICO_BASICO = 'electrico_basico'
TIPO_ELECTRICO_CALIFICADO = 'electrico_calificado'
TIPO_GAS = 'gas'
TIPOS_ELECTRICOS = (TIPO_ELECTRICO_BASICO, TIPO_ELECTRICO_CALIFICADO)

Donde el código compare tipo de contrato, usar las constantes de models/contrato.py, no strings literales. Para verificar si un contrato es eléctrico (cualquier modalidad): tipo in TIPOS_ELECTRICOS.

FACTURAS DE ELECTRICIDAD CALIFICADA (PPA)

Tabla: facturas_electricidad_calificado. Modelo: models/factura_calificado.py (FacturaCalificado). Campos: id, contrato_id, cliente_id, suministrador, rpu, serie_folio, periodo_inicio, periodo_fin, dias_facturados, anio, mes, nombre_canonico, consumo_kwh, precio_unitario_mxn_kwh, subtotal_mxn, iva_mxn, total_mxn, excedente_detectado, advertencias, pdf_url, parser_version, created_at. Todos los campos numéricos se almacenan como TEXT en Supabase y se convierten a Decimal al leer.

Nombre canónico: CALIFICADO-{AAAA}-{MM:02d}-{suministrador_slug} (snake_case del suministrador, o "sin_suministrador" si está vacío).

Excedente: consumo_kwh > bloque_contratado_mwh × 1000 × 1.10 (el bloque en ppa_bloques_mensuales está en MWh; comparar en la misma unidad).

Rutas CRUD (Blueprint clientes_bp, prefijo /clientes):
- GET/POST /<cliente_id>/contratos/<contrato_id>/factura_calificado/crear → factura_calificado_crear
- GET/POST /<cliente_id>/contratos/<contrato_id>/factura_calificado/<factura_id>/editar → factura_calificado_editar
- POST /<cliente_id>/contratos/<contrato_id>/factura_calificado/<factura_id>/borrar → factura_calificado_borrar

Validaciones (_validar_y_parsear_factura_calificado en web/clientes.py): periodo_inicio < periodo_fin, consumo_kwh > 0, precio_unitario > 0, subtotal > 0, coherencia IVA+subtotal vs total (tolerancia ±1 MXN), sin duplicado (mismo contrato_id + anio + mes).

Funciones de repositorio (storage/repository.py): create_factura_calificado, get_factura_calificado, get_facturas_calificado_por_contrato, get_facturas_calificado_por_cliente, update_factura_calificado, delete_factura_calificado, get_facturas_para_dashboard_calificado.

Sidebar y selección de meses: get_sidebar_data_contrato y get_meses_con_factura reciben contrato_tipo y despachan a la tabla correcta según sea electrico_basico o electrico_calificado. La selección de meses funciona igual que para contratos CFE.

## Parser de facturas calificadas (GIN)

Módulo `parsers/electricidad_calificado/gin.py`. Clase `GINParser` hereda de `InvoiceParser`. Retorna dataclass `GINInvoice` con 15 campos: suministrador, rfc_suministrador, rfc_receptor, serie_folio, folio_fiscal, fecha_factura (date|None), periodo_inicio (date), periodo_fin (date), rpu, consumo_kwh (Decimal), precio_unitario_mxn_kwh (Decimal), subtotal_mxn (Decimal), iva_mxn (Decimal|None), total_mxn (Decimal|None), advertencias (list[str]). VERSION = "1.0.0". Fixture real: `tests/fixtures/calificado/GIN_2024_09_SEPTIEMBRE.pdf` (septiembre 2024, IBERICA TILES, GIN040707G89). Validado con 16 tests en `tests/parsers/test_gin.py`.

## Upload de PDF calificado

Ruta `GET/POST /<cliente_id>/contratos/<contrato_id>/factura_calificado/upload`. Parsea PDF con `GINParser`, muestra preview de campos editables en template `factura_calificado_preview.html`, usuario confirma y datos se guardan vía POST a endpoint `factura_calificado_crear` (existente). Template `factura_calificado_upload.html` para el formulario de carga. Botón "+ Subir factura PPA (PDF)" añadido a la ficha del contrato calificado.

## Bloqueo de mezcla CFE/PPA

Un cliente no puede tener meses seleccionados de contratos `electrico_basico` y `electrico_calificado` simultáneamente. Validación ocurre en endpoints `POST .../seleccion/mes` y `POST .../seleccion/anio`: si `seleccionado=True` y el tipo opuesto ya tiene meses seleccionados, devuelve HTTP 409 con mensaje descriptivo. Función repositorio: `get_tipos_electricos_con_meses_seleccionados(cliente_id)` → `list[str]` con tipos que tienen meses activos. Tests: `tests/test_seleccion_mezcla.py` (5 tests).

## Parámetros del motor candidato (configurables, con valores por defecto)

Cobertura objetivo del consumo eléctrico mensual: 75% (rango editable 50% a 95%).

Rendimiento eléctrico del motor: 40%.

Rendimiento térmico aprovechable: 25%.

Eficiencia de la caldera de referencia (sustituida por el aprovechamiento térmico): 85%.

Horas de operación previstas: 720 horas mensuales (operación continua).

## Lógica de cálculo de cogeneración

Paso 1. Dimensionamiento. Consumo eléctrico mensual del cliente multiplicado por la cobertura objetivo. Resultado: energía a generar mensualmente, en kWh.

Paso 2. Distribución horaria (algoritmo greedy). El consumo cubierto se asigna primero al horario con mayor costo unitario (punta), luego a intermedio, luego a base, hasta agotar `kwh_cubiertos`. Si el total de kWh disponibles en los horarios más caros no es suficiente, se continúa al siguiente. Este orden greedy maximiza el ahorro eléctrico teórico.

Paso 3. Ahorro eléctrico — 3 componentes GDMTH. La tarifa GDMTH factura la demanda en dos componentes adicionales: Capacidad y Distribución. El precio unitario de cada uno se obtiene dividiendo el cargo de `cargo_demanda_mxn` del componente MEM entre el kW facturado, que CFE deriva como `ceil(kWh_total / (24 × días) / 0.57)` — siempre con redondeo al entero superior (ceiling), nunca normal ni truncado. El kW facturado para Capacidad es `min(kw_punta, ceil(D_actual))` y para Distribución es `min(kw_max, ceil(D_actual))`. La demanda efectiva post-cogeneración también usa ceiling: `ceil((kWh_post / (24 × días)) / 0.57)`. Asunción conservadora: `kw_max` no cambia con cogeneración (paradas mensuales). Implementación en `calc/cogen.py` con `math.ceil()` (Python) y replicado en `dashboard-cogeneracion.js` con `Math.ceil()` (JS). El campo correcto para precio unitario es `cargo_demanda_mxn` de `cfe_mem_componentes`, no `importe_mxn`.

Paso 4. Ahorro Otros Servicios (solo CFE GDMTH). Transmisión + CENACE + SCnMEM son cargos proporcionales al consumo (kWh). Se obtiene el `importe_mxn` de cada componente MEM (usar nombre exacto: `"Transmisión"`, `"CENACE"`, `"SCnMEM"`). `cargo_otros_total = transmision + cenace + scnmem`. `precio_otros_mxn_kwh = cargo_otros_total / kwh_total_orig`. `ahorro_otros_servicios = kwh_cubiertos × precio_otros_mxn_kwh`. Si algún componente no existe en la factura, se trata como 0. No aplica a PPA.

Ahorro Eléctrico Total CFE GDMTH (4 componentes): ahorro_energia + ahorro_capacidad + ahorro_distribucion + ahorro_otros_servicios.

Para PPA el ahorro eléctrico sigue siendo un solo componente: kwh_cubiertos × precio_promedio.

Paso 5. Costo de gas adicional. Energía eléctrica generada dividida entre rendimiento eléctrico, convertida a metros cúbicos usando el poder calorífico real del gas extraído de las facturas (no factor estándar), multiplicado por costo unitario del gas del cliente.

Paso 6. Aprovechamiento térmico. Energía contenida en gas multiplicada por rendimiento térmico igual calor recuperable. Calor recuperable dividido entre eficiencia de caldera de referencia igual gas que el cliente deja de quemar. Multiplicar por costo unitario del gas. Resultado: ahorro térmico monetizado.

Paso 7. Costo O&M (Operación y Mantenimiento). 0.3 MXN fijos por cada kWh cubierto por el motor. Es un costo FIJO por kWh generado, no un porcentaje del ahorro eléctrico ni del costo de la electricidad. O&M mensual = 0.3 MXN/kWh × kWh_cubiertos_mes. Constante `_FACTOR_OM = Decimal("0.3")` en `calc/cogen.py`.

Paso 8. Ahorro neto y EBITDA. Ahorro eléctrico bruto más ahorro térmico menos costo de gas adicional menos O&M. Cálculo mensual sobre las 12 facturas reales (preserva estacionalidad), suma anual.

## Medio térmico recuperado y RefH ponderado

La cogeneración puede recuperar calor en forma de vapor/agua caliente o gases de combustión directos. La CRE asigna distinto RefH a cada uno (vapor: 0.90, gases: 0.82). Cuando la cogeneración recupera ambos medios, el RefH se calcula ponderado por el porcentaje de cada uno.

Campo en BD: `medio_termico_vapor_pct` (INTEGER 0-100). Define el porcentaje de vapor. El porcentaje de gases = 100 - vapor_pct.

Fórmula RefH ponderado: RefH = (vapor_pct / 100) × 0.90 + ((100 - vapor_pct) / 100) × 0.82

Ejemplos: 100% vapor → RefH = 0.90. 0% vapor (100% gases) → RefH = 0.82. 50/50 → RefH = 0.86. 30/70 (30 vapor, 70 gases) → RefH = 0.844.

UI: dropdown en ficha/editar con cuatro opciones: sin especificar (value=""), vapor o agua caliente (value="vapor_o_agua", pct=100 fijo), gases de combustión directos (value="gases_combustion", pct=0 fijo), mezcla (value="mezcla", pct editable por operador). Campo % Vapor visible solo cuando se selecciona "mezcla".

Implementación: `REFH_VAPOR`, `REFH_GASES` y `_calcular_ref_h(pct)` en `calc/cels.py`. La función `calcular_cels` recibe `medio_termico_vapor_pct: int | None`; None → devuelve None (sin especificar). El campo `medio_termico` (string) se mantiene para etiqueta/display pero ya no determina el RefH.

Migración: `storage/migrations/202605_medio_termico_mezcla.sql`. Incluye ALTER TABLE + UPDATE para poblar `medio_termico_vapor_pct` en clientes existentes y normalizar `vapor_agua` → `vapor_o_agua`.

## Energía Limpia Generada (KPI dashboard)

Caja adicional en el bloque 2 del dashboard de Cogeneración. Fórmula: energia_limpia_pct = (cels_mwh_anual × 1000) / kwh_total_anual × 100. Se calcula en web/app.py después de obtener CELsResultado. Solo se muestra cuando el cliente califica como cogeneración eficiente (cels_resultado.es_eficiente = True). Se almacena en CoGenResultado.energia_limpia_pct (Decimal | None). Para IBERICA TILES 2024: ~25.5%.

## Beneficio Fiscal por Depreciación Inmediata

La Ley del ISR Artículo 34 fracción XIII permite deducción inmediata del 100% para activos de cogeneración eficiente certificada CRE. Cuando el cliente califica como cogeneración eficiente (cumple Caso I de CRE), puede deducir la totalidad de la inversión en el año fiscal 1. Cálculo del beneficio: beneficio_fiscal_anio_1 = inversion_mxn × tasa_ISR, donde tasa_ISR = 30% (constante _TASA_ISR en calc/cogen.py — régimen general personas morales en México). El beneficio se suma al Ahorro Neto del año 1 en la proyección del flujo acumulado a 15 años. Esto reduce significativamente el payback del proyecto. Para IBERICA TILES 2024 con inversión ~$48.1M MXN: beneficio ≈ $14.4M MXN. Si el cliente NO califica como cogeneración eficiente, el beneficio fiscal aún se muestra en la proyección (la ley aplica independientemente de CELs). La app siempre calcula el beneficio cuando hay inversión estimable.

El payback se calcula con interpolación lineal entre años (no año entero). Función `calcular_payback_decimal(inversion_mxn, flujo_anio_1, ahorro_neto_anual)` en `calc/cogen.py`. Retorna `Decimal` con 2 decimales, o `None` si no se alcanza en el horizonte de 15 años. Se muestra en la UI como "X.XX años*".

## Dashboard adaptado al tipo de suministro eléctrico

Los dos dashboards (Contabilidad Energética y Proyecto Cogeneración) se comportan de manera diferente según el tipo de suministro eléctrico seleccionado.

La función `get_tipo_suministro_electrico_seleccionado(cliente_id)` en `storage/repository.py` retorna `'electrico_basico'` | `'electrico_calificado'` | `None` leyendo los meses seleccionados activos. El bloqueo de mezcla garantiza que nunca haya ambos tipos activos simultáneamente.

En `web/app.py`, tanto las rutas HTML como los endpoints `/data` detectan el tipo antes de cargar datos. Para `electrico_calificado` cargan `get_facturas_ppa_y_gas_para_dashboard(cliente_id)` y llaman `calcular_cogen_ppa`. Para `electrico_basico` (o None) mantienen el path GDMTH original sin cambios. Los JSON de ambos endpoints incluyen `tipo_suministro_electrico` y `suministrador_ppa`.

Dashboard Contabilidad para PPA: banner "Suministro: Calificado (PPA) — {suministrador}", KPIs adaptados (badge "PPA" en vez de "CFE"), las gráficas GDMTH (demanda/consumo horario, costo unitario por horario, pie chart) se ocultan; se muestran dos gráficas PPA: consumo mensual vs precio, y costo mensual. La detección usa `data.tipo_suministro_electrico === "electrico_calificado"` en JS. Al cambiar modo se destruyen las instancias Chart.js del modo anterior.

Dashboard Cogeneración para PPA: banner, `recalcularPPA(m, p)` que usa `m.costo_promedio_kwh` para `ah_elec` (sin desglose horario ni cálculo Capacidad/Distribución), dispatch `esPPA ? recalcularPPA : recalcularMes` en `actualizarSensibilidad`, CELs card muestra "N/A", etiqueta de cascada "Ahorro Eléctrico (Total)". CO₂ y gas/caldera/O&M se calculan igual que GDMTH.

La función `calcular_cogen_ppa` en `calc/cogen.py` rellena todos los campos de `CoGenMes` con Decimal("0") para los campos exclusivos de GDMTH, por lo que es compatible con el mismo `CoGenResultado` y las mismas rutas de serialización JSON.

## Restricciones de comunicación

Responder en español.

Estilo directo, minimalista, ejecutivo. Sin viñetas ni guiones en explicaciones; usar prosa estructurada en párrafos. Usar listas o viñetas solo cuando sea estrictamente necesario para la legibilidad técnica (por ejemplo, listar campos de una tabla).

Cuestionar decisiones cuando algo no parezca correcto. No aceptar acríticamente.

Si faltan datos para una decisión, detenerse y solicitar la información específica.

Antes de implementar, explicar la aproximación y esperar confirmación.

## Cómo trabajar con este proyecto

Cada sesión de trabajo se enfoca en un entregable específico. Al iniciar la sesión, leer este archivo para retomar contexto. Al cerrar, actualizar este archivo si hubo decisiones nuevas que afecten futuras sesiones.

Antes de tomar decisiones que no estén documentadas aquí, preguntar.

---

## Estado de chats activos

Esta sección la mantiene Claude Code. Se actualiza en cada commit.
Permite retomar cualquier chat sin reconstruir contexto.

### Nuevas funcionalidades
Último tema resuelto: feat asignación múltiple de clientes a usuario_normal —
tabla usuario_clientes, sesión con clientes_ids, sidebar dinámico, panel
edición master_admin con checkboxes.
Pendiente: ejecutar migration 202606_usuario_clientes.sql en Supabase.

### Bugs App
Último tema resuelto: tabla componentes cogeneración con table-layout
fixed para Safari + colores donut resueltos desde CSS vars.
Pendiente: ninguno conocido.

### Diseño Visual App
Último tema resuelto: donut Contabilidad y Cogeneración restaurada a
paleta azules (#1F3A5F, #2E5C8A, #5B8FB9, #A4C8E1), dots de leyenda
sincronizados al mismo color del arco.
Pendiente: ninguno conocido.

### Auditorías App
Último tema resuelto: ninguno. Chat iniciado, modelo recomendado Opus 4.7.
Pendiente: auditoría de fase 1 al cierre del alcance.

### Integración Telemática
Último tema resuelto: v2.60.1 — fix generador sintético alineado al esquema
real (18 columnas exactas: potencia_activa_kw, factor_potencia, voltaje_l1_v,
etc.). Previo seed.py usaba columnas que no existen (kw_total, v_an, pf_total…)
causando PGRST204. Template medidor.html actualizado. Tests reforzados.
Pendiente: integración MQTT/pipeline real (entrega B2).
