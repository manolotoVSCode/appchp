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

clientes: id, nombre, rfc (único), created_at.

cfe_facturas: id, cliente_id, uuid_cfdi, folio, serie, fecha_emision, periodo_inicio, periodo_fin, fecha_limite_pago, numero_servicio, rmu, tarifa, numero_medidor, multiplicador, carga_conectada_kw, demanda_contratada_kw, kw_max, kvarh, factor_potencia_pct, cargo_fijo_mxn, energia_total_mxn, cargo_factor_potencia_mxn, subtotal_mxn, iva_mxn, facturacion_periodo_mxn, derecho_alumbrado_publico_mxn, credito_aplicado_mxn, total_mxn, pdf_path.

cfe_periodos: id, factura_id, periodo (base, intermedio, punta), consumo_kwh, demanda_kw, costo_unitario_kwh.

cfe_mem_componentes: id, factura_id, nombre, cargo_fijo_mxn, cargo_demanda_mxn, cargo_energia_mxn, importe_mxn.

gas_facturas: id, cliente_id, uuid_cfdi, folio, fecha_emision, periodo_inicio, periodo_fin, fecha_limite_pago, nombre_proveedor, rfc_proveedor, numero_cliente, cuenta_contrato, punto_suministro, numero_caseta, tipo_lectura, consumo_m3_corregidos, consumo_sin_corregir_m3, poder_calorifico_gj_m3, consumo_total_gj, costo_unitario_total_gj, subtotal_mxn, iva_mxn, total_mxn.

gas_conceptos: id, factura_id, descripcion, clave_producto, cantidad_gj, precio_unitario_gj, importe_mxn.

## Variables de entorno requeridas

SUPABASE_URL: URL del proyecto Supabase.
SUPABASE_KEY: clave service_role del proyecto. Ver sección de seguridad y deuda técnica.
SECRET_KEY: clave secreta de Flask para firmar cookies de sesión. Generar con `python3 -c "import secrets; print(secrets.token_hex(32))"`. Obligatoria en producción; si se omite, la app regenera una clave en cada reinicio invalidando todas las sesiones.
APP_USER: nombre de usuario del operador (texto plano). Ejemplo: `operador`.
APP_PASSWORD_HASH: hash de la contraseña generado con werkzeug. Generar así:
  `python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('mi_password'))"`
  El hash resultante (formato `pbkdf2:sha256:...`) se pega directamente como valor de la variable. Nunca guardar la contraseña en texto plano. Para cambiar la contraseña, regenerar el hash y actualizar la variable de entorno en Render; reiniciar el servicio.

## Seguridad y deuda técnica reconocida

La aplicación usa la clave service_role de Supabase, que bypasea Row Level Security. Esto es deuda técnica explícita y aceptada para fase 1, justificada porque no hay autenticación de usuarios y el acceso es exclusivamente desde el backend bajo control del operador.

La clave service_role debe vivir exclusivamente en variables de entorno del servidor backend. Nunca en código fuente, nunca en frontend, nunca en repositorio público.

Cuando se introduzca autenticación de usuarios (entregable separado posterior, no parte de esta fase), se migrará al uso de la clave anon con políticas Row Level Security configuradas por usuario y por tenant. Esta migración es trabajo conocido y planeado.

## Parámetros del motor candidato (configurables, con valores por defecto)

Cobertura objetivo del consumo eléctrico mensual: 75% (rango editable 50% a 95%).

Rendimiento eléctrico del motor: 40%.

Rendimiento térmico aprovechable: 25%.

Eficiencia de la caldera de referencia (sustituida por el aprovechamiento térmico): 85%.

Horas de operación previstas: 720 horas mensuales (operación continua).

## Lógica de cálculo de cogeneración

Paso 1. Dimensionamiento. Consumo eléctrico mensual del cliente multiplicado por la cobertura objetivo. Resultado: energía a generar mensualmente, en kWh.

Paso 2. Distribución horaria. El consumo cubierto se distribuye proporcionalmente entre punta, intermedio y base según la distribución horaria de la tarifa GDMTH del cliente. El operador puede ajustar manualmente si conoce el régimen real de operación del motor.

Paso 3. Ahorro eléctrico bruto por horario. Para cada horario, consumo cubierto multiplicado por costo unitario de ese horario en la factura del cliente. La suma es el ahorro eléctrico bruto mensual.

Paso 4. Costo de gas adicional. Energía eléctrica generada dividida entre rendimiento eléctrico, convertida a metros cúbicos usando el poder calorífico real del gas extraído de las facturas (no factor estándar), multiplicado por costo unitario del gas del cliente.

Paso 5. Aprovechamiento térmico. Energía contenida en gas multiplicada por rendimiento térmico igual calor recuperable. Calor recuperable dividido entre eficiencia de caldera de referencia igual gas que el cliente deja de quemar. Multiplicar por costo unitario del gas. Resultado: ahorro térmico monetizado.

Paso 6. Ahorro neto y EBITDA. Ahorro eléctrico bruto más ahorro térmico menos costo de gas adicional. Cálculo mensual sobre las 12 facturas reales (preserva estacionalidad), suma anual.

## Restricciones de comunicación

Responder en español.

Estilo directo, minimalista, ejecutivo. Sin viñetas ni guiones en explicaciones; usar prosa estructurada en párrafos. Usar listas o viñetas solo cuando sea estrictamente necesario para la legibilidad técnica (por ejemplo, listar campos de una tabla).

Cuestionar decisiones cuando algo no parezca correcto. No aceptar acríticamente.

Si faltan datos para una decisión, detenerse y solicitar la información específica.

Antes de implementar, explicar la aproximación y esperar confirmación.

## Cómo trabajar con este proyecto

Cada sesión de trabajo se enfoca en un entregable específico. Al iniciar la sesión, leer este archivo para retomar contexto. Al cerrar, actualizar este archivo si hubo decisiones nuevas que afecten futuras sesiones.

Antes de tomar decisiones que no estén documentadas aquí, preguntar.
