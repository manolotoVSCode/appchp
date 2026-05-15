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

## Schema de Supabase (tablas existentes)

clientes: id, nombre, rfc (único), notas, created_at, sector_industrial, contacto_nombre, contacto_cargo, contacto_email, contacto_telefono, direccion, estado, codigo_postal, tarifa_cfe, capacidad_instalada_kw, demanda_contratada_kw, anio_inicio_operacion, regimen_operacion, consumo_anual_estimado_mwh, logo_url, medio_termico, nivel_tension_kv, altitud_msnm, tipo_motor.

contratos: id, cliente_id (FK clientes ON DELETE CASCADE), nombre, tipo ('electrico'|'gas'), identificador_real, notas, created_at.

cfe_facturas: id, cliente_id (FK clientes ON DELETE CASCADE), contrato_id (FK contratos ON DELETE SET NULL), uuid_cfdi, folio, serie, fecha_emision, periodo_inicio, periodo_fin, fecha_limite_pago, numero_servicio, rmu, tarifa, numero_medidor, multiplicador, carga_conectada_kw, demanda_contratada_kw, kw_max, kvarh, factor_potencia_pct, cargo_fijo_mxn, energia_total_mxn, cargo_factor_potencia_mxn, subtotal_mxn, iva_mxn, facturacion_periodo_mxn, derecho_alumbrado_publico_mxn, credito_aplicado_mxn, total_mxn, pdf_path, advertencias (JSON array), nombre_canonico, anio, mes.

cfe_periodos: id, factura_id (FK cfe_facturas ON DELETE CASCADE), periodo (base, intermedio, punta), consumo_kwh, demanda_kw, costo_unitario_kwh.

cfe_mem_componentes: id, factura_id (FK cfe_facturas ON DELETE CASCADE), nombre, cargo_fijo_mxn, cargo_demanda_mxn, cargo_energia_mxn, importe_mxn.

gas_facturas: id, cliente_id (FK clientes ON DELETE CASCADE), contrato_id (FK contratos ON DELETE SET NULL), uuid_cfdi, folio, fecha_emision, periodo_inicio, periodo_fin, fecha_limite_pago, nombre_proveedor, rfc_proveedor, numero_cliente, cuenta_contrato, punto_suministro, numero_caseta, tipo_lectura, consumo_m3_corregidos, consumo_sin_corregir_m3, poder_calorifico_gj_m3, consumo_total_gj, costo_unitario_total_gj, subtotal_mxn, iva_mxn, total_mxn, pdf_path, advertencias (JSON array), nombre_canonico, anio, mes.

gas_conceptos: id, factura_id (FK gas_facturas ON DELETE CASCADE), descripcion, clave_producto, cantidad_gj, precio_unitario_gj, importe_mxn.

contrato_meses_seleccionados: PK(contrato_id, anio, mes). FK contrato_id → contratos ON DELETE CASCADE.

configuracion: clave (PK), valor, descripcion, updated_at. Claves activas: tipo_cambio_mxn_usd, factor_emision_electricidad_kg_co2_kwh, factor_emision_gas_kg_co2_gj.

## Arquitectura de contratos y selección de meses

Un cliente puede tener múltiples contratos (`contratos`), cada uno de tipo 'electrico' o 'gas'. Las facturas CFE y de gas se vinculan a un contrato mediante `contrato_id`. Los dashboards filtran por meses seleccionados en la tabla `contrato_meses_seleccionados` (combinación única contrato_id + anio + mes). La selección se gestiona desde el sidebar expandible en la ficha del cliente: fetch AJAX al endpoint `GET /<cliente_id>/contratos/<contrato_id>/seleccion`, toggle individual vía `POST .../seleccion/mes`, selección masiva por año vía `POST .../seleccion/anio`. Solo se puede seleccionar un mes si existe al menos una factura (CFE o gas) para ese contrato/año/mes.

## Configuración del sistema

Parámetros globales editables en `/admin/configuracion` (requiere autenticación). Se persisten en la tabla `configuracion` de Supabase. Al agregar una clave nueva directamente en BD, aparece automáticamente en la UI sin cambios de código. Validaciones por clave: tipo_cambio_mxn_usd (10–30), factor_emision_electricidad_kg_co2_kwh (0.1–2.0), factor_emision_gas_kg_co2_gj (10–200). Claves desconocidas se validan como número positivo.

## Variables de entorno requeridas

SUPABASE_URL: URL del proyecto Supabase.
SUPABASE_KEY: clave service_role del proyecto. Ver sección de seguridad y deuda técnica.
SECRET_KEY: clave secreta de Flask para firmar cookies de sesión. Generar con `python3 -c "import secrets; print(secrets.token_hex(32))"`. Obligatoria en producción; si se omite, la app regenera una clave en cada reinicio invalidando todas las sesiones.
APP_USER: nombre de usuario del operador (texto plano). Ejemplo: `operador`.
APP_PASSWORD_HASH: hash de la contraseña generado con werkzeug. Generar así:
  `python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('mi_password', method='pbkdf2:sha256'))"`
  El hash resultante (formato `pbkdf2:sha256:...`) se pega directamente como valor de la variable. Nunca guardar la contraseña en texto plano. Para cambiar la contraseña, regenerar el hash y actualizar la variable de entorno en Render; reiniciar el servicio.

## Seguridad y deuda técnica reconocida

La aplicación usa la clave service_role de Supabase, que bypasea Row Level Security. Esto es deuda técnica explícita y aceptada para fase 1, justificada porque no hay autenticación de usuarios y el acceso es exclusivamente desde el backend bajo control del operador.

La clave service_role debe vivir exclusivamente en variables de entorno del servidor backend. Nunca en código fuente, nunca en frontend, nunca en repositorio público.

Cuando se introduzca autenticación de usuarios (entregable separado posterior, no parte de esta fase), se migrará al uso de la clave anon con políticas Row Level Security configuradas por usuario y por tenant. Esta migración es trabajo conocido y planeado.

## Capacidad nominal del proyecto

La capacidad nominal de la cogeneración se calcula como:

capacidad_nominal_kw = math.ceil(max(kwh_total_mes / 720))

Donde:
- kwh_total_mes es la suma de kWh consumidos por horario (Base + Intermedia + Punta) de cada factura CFE seleccionada.
- 720 son las horas mensuales estándar (24 × 30).
- Se toma el mes de mayor consumo entre los meses seleccionados.
- Se aplica math.ceil para redondear al entero superior, por consistencia con la metodología CFE GDMTH.

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

Paso 4. Costo de gas adicional. Energía eléctrica generada dividida entre rendimiento eléctrico, convertida a metros cúbicos usando el poder calorífico real del gas extraído de las facturas (no factor estándar), multiplicado por costo unitario del gas del cliente.

Paso 5. Aprovechamiento térmico. Energía contenida en gas multiplicada por rendimiento térmico igual calor recuperable. Calor recuperable dividido entre eficiencia de caldera de referencia igual gas que el cliente deja de quemar. Multiplicar por costo unitario del gas. Resultado: ahorro térmico monetizado.

Paso 6. Costo O&M (Operación y Mantenimiento). 0.3 MXN fijos por cada kWh cubierto por el motor. Es un costo FIJO por kWh generado, no un porcentaje del ahorro eléctrico ni del costo de la electricidad. O&M mensual = 0.3 MXN/kWh × kWh_cubiertos_mes. Constante `_FACTOR_OM = Decimal("0.3")` en `calc/cogen.py`.

Paso 7. Ahorro neto y EBITDA. Ahorro eléctrico bruto más ahorro térmico menos costo de gas adicional menos O&M. Cálculo mensual sobre las 12 facturas reales (preserva estacionalidad), suma anual.

## Energía Limpia Generada (KPI dashboard)

Caja adicional en el bloque 2 del dashboard de Cogeneración. Fórmula: energia_limpia_pct = (cels_mwh_anual × 1000) / kwh_total_anual × 100. Se calcula en web/app.py después de obtener CELsResultado. Solo se muestra cuando el cliente califica como cogeneración eficiente (cels_resultado.es_eficiente = True). Se almacena en CoGenResultado.energia_limpia_pct (Decimal | None). Para IBERICA TILES 2024: ~25.5%.

## Beneficio Fiscal por Depreciación Inmediata

La Ley del ISR Artículo 34 fracción XIII permite deducción inmediata del 100% para activos de cogeneración eficiente certificada CRE. Cuando el cliente califica como cogeneración eficiente (cumple Caso I de CRE), puede deducir la totalidad de la inversión en el año fiscal 1. Cálculo del beneficio: beneficio_fiscal_anio_1 = inversion_mxn × tasa_ISR, donde tasa_ISR = 30% (constante _TASA_ISR en calc/cogen.py — régimen general personas morales en México). El beneficio se suma al Ahorro Neto del año 1 en la proyección del flujo acumulado a 15 años. Esto reduce significativamente el payback del proyecto. Para IBERICA TILES 2024 con inversión ~$48.1M MXN: beneficio ≈ $14.4M MXN. Si el cliente NO califica como cogeneración eficiente, el beneficio fiscal aún se muestra en la proyección (la ley aplica independientemente de CELs). La app siempre calcula el beneficio cuando hay inversión estimable.

## Restricciones de comunicación

Responder en español.

Estilo directo, minimalista, ejecutivo. Sin viñetas ni guiones en explicaciones; usar prosa estructurada en párrafos. Usar listas o viñetas solo cuando sea estrictamente necesario para la legibilidad técnica (por ejemplo, listar campos de una tabla).

Cuestionar decisiones cuando algo no parezca correcto. No aceptar acríticamente.

Si faltan datos para una decisión, detenerse y solicitar la información específica.

Antes de implementar, explicar la aproximación y esperar confirmación.

## Cómo trabajar con este proyecto

Cada sesión de trabajo se enfoca en un entregable específico. Al iniciar la sesión, leer este archivo para retomar contexto. Al cerrar, actualizar este archivo si hubo decisiones nuevas que afecten futuras sesiones.

Antes de tomar decisiones que no estén documentadas aquí, preguntar.
