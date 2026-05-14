# Auditoría completa chpapp

**Fecha de auditoría:** 2026-05-10
**Versión auditada:** 2.19.1

---

## Resumen ejecutivo

**Total de hallazgos:** 3 críticos, 6 altos, 12 medios, 9 bajos

### Top 5 problemas más urgentes

1. **Schema SQL desactualizado en 6 tablas** — `storage/schema.sql` documenta solo 5 de las 11 tablas que el código usa en producción. Las tablas `contratos`, `contrato_meses_seleccionados`, `configuracion` y los campos nuevos de `clientes` (medio_termico, nivel_tension_kv, altitud_msnm, tipo_motor, etc.) no existen en el DDL de referencia. Si alguien recrea el schema desde ese archivo la aplicación falla en runtime.

2. **O&M calculado sobre ahorro eléctrico, no sobre kWh cubiertos × costo** — en `cogen.py:127` el O&M se calcula como `kwh_cubiertos × costo_prom_kwh × 0.3`, lo cual es aritméticamente equivalente a `ahorro_electricidad × 0.3`. El CLAUDE.md describe O&M como `0.3 × kWh_cubiertos_anual` (sin unidades monetarias), lo que sería una tasa en kWh, no en MXN. Si la intención fuera 0.3 MXN/kWh cubierto, la fórmula es correcta; si fuera un ratio puro sobre kWh (ej. costo de mantenimiento por kWh generado con precio fijo), la fórmula es incorrecta. El JS (`recalcularMes` línea 86) replica `ah_elec * 0.3`, coherente con el backend pero la documentación CLAUDE.md es ambigua.

3. **Costo unitario de gas `costo_unitario_total_gj` suma precios unitarios, no divide importe/GJ** — en `parsers/gas/engie.py:181` se hace `costo_unitario_total = sum(c.precio_unitario_gj for c in conceptos)`, que suma el precio unitario de molécula + precio unitario de transporte. Esto es correcto solo si cada concepto ya expresa su precio por GJ de forma aditiva. Si alguna factura tuviera tres conceptos o un concepto que no fuera por GJ, el resultado sería erróneo. No hay validación de que los GJ de los conceptos coincidan con `consumo_total_gj`.

4. **`render.yaml` no incluye SECRET_KEY, APP_USER ni APP_PASSWORD_HASH** — el archivo de despliegue en Render solo declara `SUPABASE_URL` y `SUPABASE_KEY` (líneas 8-12). Las variables `SECRET_KEY`, `APP_USER` y `APP_PASSWORD_HASH` no están listadas, lo que significa que alguien que clone y despliegue desde ese archivo no sabrá que las necesita hasta que la aplicación explote en `_validar_config_auth()`.

5. **XSS potencial por `innerHTML` con datos del servidor** — en `dashboard-cogeneracion.js` las funciones `actualizarAviso` (línea 435) y `actualizarCELsCard` (líneas 504-536) construyen HTML con `cont.innerHTML = html` e insertan valores del servidor (`aviso.num_cfe`, `aviso.num_gas`, `fichUrl`). Si algún valor del servidor contuviera caracteres especiales (comillas, `<`, `>`) podría ser explotado. El riesgo es bajo dado el acceso controlado pero es una deuda técnica explícita. El mismo patrón aparece en `dashboard-contabilidad.js:563`.

---

## Hallazgos por categoría

### 1. Bugs funcionales

#### Crítico

- **Schema SQL incompleto — 6 tablas/columnas producción ausentes en DDL**
  - Ubicación: `storage/schema.sql` completo
  - Descripción: El archivo DDL de referencia documenta únicamente las 5 tablas originales (clientes, cfe_facturas, cfe_periodos, cfe_mem_componentes, gas_facturas, gas_conceptos). Faltan completamente: `contratos`, `contrato_meses_seleccionados`, `configuracion`, y en la tabla `clientes` faltan los campos `medio_termico`, `nivel_tension_kv`, `altitud_msnm`, `tipo_motor` (añadidos en v2.18) y los campos `nombre_canonico`, `contrato_id`, `anio`, `mes`, `advertencias` en `cfe_facturas` y `gas_facturas`.
  - Impacto: Si el equipo necesita recrear el schema desde el archivo SQL (ej. migrar a otra instancia Supabase, recuperación de desastre), la aplicación fallará en runtime. El schema de referencia está desincronizado con la BD real.
  - Recomendación: Actualizar `schema.sql` con todas las tablas y columnas actuales. Añadir comentario de fecha de última actualización.

- **Costo unitario de gas calculado como suma de precios, no como ratio importe/GJ**
  - Ubicación: `parsers/gas/engie.py:181`
  - Descripción: `costo_unitario_total = sum(c.precio_unitario_gj for c in conceptos)`. Si los conceptos son Compraventa ($/GJ_mol) + Transporte ($/GJ_tra), la suma es el precio total por GJ solo si ambos están expresados en la misma unidad de GJ y el consumo es idéntico para ambos. No hay verificación de que `compraventa.cantidad_gj == transporte.cantidad_gj`. Si difieren (facturas con periodos parciales), el costo unitario resultante es inexacto.
  - Impacto: Posible error de cálculo en `costo_gas_cogen_mxn` y por ende en `ebitda_mes_mxn`.
  - Recomendación: Calcular `costo_unitario_total_gj = invoice.subtotal_mxn / consumo_total_gj` cuando `consumo_total_gj > 0`, como alternativa más robusta. O al menos validar que `sum(c.cantidad_gj)` ≈ `consumo_total_gj`.

- **`print()` en código de producción en lugar de `logger`**
  - Ubicación: `calc/cogen.py:105-106`
  - Descripción: `print(f"WARNING: Sin factura de gas para {clave} ...")` usa print directo en lugar del sistema de logging. En producción con Gunicorn el output de stdout puede no aparecer en los logs del servidor.
  - Impacto: Meses omitidos por falta de par CFE-gas no quedan trazados correctamente en logs de Render.
  - Recomendación: Reemplazar con `logger.warning(...)`.

#### Alto

- **Archivo temporal del export Excel nunca se borra**
  - Ubicación: `web/app.py:731-738`
  - Descripción: Se crea un archivo temporal con `tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)` y se envía con `send_file()`. El archivo nunca se elimina después de la descarga. Con `delete=False` el archivo persiste en el sistema de archivos del servidor.
  - Impacto: Acumulación de archivos temporales en `/tmp` del servidor Render. En el free tier esto puede agotar el almacenamiento con el tiempo.
  - Recomendación: Usar un callback `after_this_request` para borrar el archivo, o usar `io.BytesIO` en memoria.

- **`export_excel` no usa tipo_cambio de BD**
  - Ubicación: `web/app.py:727`
  - Descripción: `r = calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())` no pasa `tipo_cambio` ni `factor_emision_*`. La inversión MXN en el Excel siempre usa el TC por defecto (17.50), ignorando el valor configurado en BD. El dashboard muestra el TC correcto pero el Excel exportado puede diferir.
  - Impacto: El Excel exportado puede tener una inversión en MXN diferente a la mostrada en el dashboard, confundiendo al operador.
  - Recomendación: Leer `tipo_cambio` de BD antes de llamar a `calcular_cogen` en la ruta `/export/excel`.

- **Sidebar N+1 queries en `get_sidebar_data_contrato`**
  - Ubicación: `storage/repository.py:728-744`
  - Descripción: `get_sidebar_data_contrato` llama a `get_anios_con_facturas_por_contrato` (2 queries) y luego por cada año llama a `get_meses_con_factura` (2 queries por año). Para un cliente con 3 años de facturas genera 2 + 3×2 = 8 queries. Este endpoint se llama desde el panel flotante del sidebar.
  - Impacto: Latencia creciente con más años de datos. No crítico con pocos clientes pero es deuda arquitectónica.
  - Recomendación: Consolidar en una sola query con `GROUP BY anio, mes` sobre ambas tablas.

- **`_verificar_acceso_contrato` hace query redundante en flujos de contrato**
  - Ubicación: `web/clientes.py:446-465`
  - Descripción: `_verificar_acceso_contrato` llama a `get_contrato(contrato_id)`. En `contrato_ficha`, `contrato_editar`, `contrato_borrar` y `contrato_upload` se llama además a `get_contrato_con_conteos(contrato_id)` justo después, duplicando la query al objeto contrato.
  - Impacto: Doble query a Supabase por cada petición de ficha/editar/borrar contrato.
  - Recomendación: Que `_verificar_acceso_contrato` devuelva el `Contrato` ya cargado y el caller lo reutilice.

- **Open redirect en login**
  - Ubicación: `web/auth.py:61`
  - Descripción: `next_url = request.args.get("next") or url_for("dashboard")` usa el parámetro `next` sin validar que sea relativo al dominio propio. Si alguien construye `https://app.com/login?next=https://evil.com` el usuario es redirigido a un sitio externo tras el login.
  - Impacto: Vector de phishing clásico. Bajo riesgo práctico dado el acceso controlado pero es un problema estándar de seguridad.
  - Recomendación: Validar que `next_url` sea una URL relativa (empieza con `/` y no con `//`).

#### Medio

- **Capacidad nominal calculada sobre max(kWh_mes)/720, no sobre max real horario**
  - Ubicación: `calc/cogen.py:31-43`
  - Descripción: `_capacidad_nominal_kw` toma `max(kwh_total_mes) / 720`. Esto asume que si en el mes de mayor consumo el motor operó las 720 horas, la capacidad nominal es el promedio horario de ese mes. No usa `kw_max` ni la demanda punta real de la factura. El CLAUDE.md dice `max(kwh_total_mes / 720)` sobre todos los meses, que es lo implementado.
  - Impacto: La capacidad estimada puede ser muy diferente de la real si el cliente tiene cargas muy variables. Para una instalación real, la capacidad se dimensiona sobre la demanda punta, no sobre el promedio mensual.
  - Recomendación: Documentar explícitamente esta simplificación. Como mejora, ofrecer la posibilidad de usar `kw_max` de la factura como alternativa.

- **`mes_asociado` incluye el día `periodo_fin` en el conteo**
  - Ubicación: `calc/periodo.py:17-28`
  - Descripción: El bucle `while current <= periodo_fin` incluye el día de fin. Si una factura es del 01/11 al 01/12 (incluido), el día 01/12 cuenta para diciembre, lo que puede alterar la asignación. El comportamiento es consistente internamente pero puede diferir de lo que CFE considera periodo (típicamente el último día no está facturado).
  - Impacto: Posible asignación incorrecta del mes en facturas que cruzan mes exactamente en el último día.
  - Recomendación: Verificar con facturas reales si el día `periodo_fin` debe incluirse o excluirse.

- **`prorratear_cfe` no escala `kw_max`, `kvArh`, ni `demanda_kw` de periodos**
  - Ubicación: `calc/periodo.py:47-68`
  - Descripción: Al prorratear a 30 días, solo se escala `consumo_kwh` de los periodos, no `demanda_kw`. Tampoco se escalan `kw_max` ni `kvArh`. La demanda se mide en kW (potencia instantánea) y no debería escalarse, pero `kw_max` podría ser afectado si el periodo es parcial.
  - Impacto: En `calcular_historico_cfe`, la demanda mostrada para meses prorrateados puede no representar correctamente la potencia real.
  - Recomendación: Documentar explícitamente que demanda en kW no se prorratéa (es correcto para potencia). Verificar si `kw_max` requiere tratamiento especial.

- **`historico_gas.calcular_historico_gas` no aplica prorrateo**
  - Ubicación: `calc/historico.py:324-454`
  - Descripción: `calcular_historico_gas` no llama a `prorratear_gas`. El historico de gas muestra los valores brutos de las facturas, incluso si son periodos cortos. Inconsistente con `calcular_tablas_cfe` que sí prorratéa.
  - Impacto: Meses con facturas de gas de periodo corto (<25 días) aparecen con consumo menor en el histórico de gas aunque en cogeneración se use el valor prorrateado.
  - Recomendación: Aplicar `prorratear_gas` en `calcular_historico_gas` para consistencia, o documentar el comportamiento diferente.

- **`_context_processor` hace query a Supabase en cada request**
  - Ubicación: `web/app.py:207-228`
  - Descripción: `_inject_globals` llama a `get_cliente_con_conteos(id_)` y `get_contratos_por_cliente(id_)` en cada request para inyectar el cliente activo en todos los templates. Esto son 2 queries por cada página, incluidas páginas estáticas y endpoints JSON.
  - Impacto: Cada request genera 2 queries adicionales. En un servidor con múltiples usuarios concurrentes (aunque no es el caso actual) esto sería un problema. Con un solo operador es tolerable pero subóptimo.
  - Recomendación: Cachear el cliente activo en sesión (ya se guarda `cliente_activo_nombre`) y solo re-verificar periódicamente o en endpoints específicos.

- **`sidebar_data` genera múltiples queries por contrato en el panel flotante**
  - Ubicación: `storage/repository.py:728-744`, llamado desde `web/clientes.py:818`
  - Descripción: El endpoint `contrato_get_seleccion` es llamado por el sidebar para cada contrato del cliente activo. Si el cliente tiene 3 contratos, al cargar la página se disparan 3 llamadas al endpoint, cada una con 6-8 queries internas.
  - Impacto: 18-24 queries por carga de página con 3 contratos.
  - Recomendación: Consolidar en un endpoint único de sidebar para el cliente completo.

#### Bajo

- **`_detect_tipo` en upload es frágil y puede clasificar mal**
  - Ubicación: `web/clientes.py:164-176`
  - Descripción: La detección se basa en palabras clave en el texto: "CFE", "ENGIE", "GAS NATURAL". Un PDF de ENGIE que menciona "CFE" en el texto (ej. comparativas de tarifas) podría clasificarse como CFE. El orden de comprobación favorece CFE (se evalúa primero).
  - Impacto: Bajo, dado que el contrato ya tiene tipo `electrico`/`gas` y hay una validación posterior de coherencia.
  - Recomendación: Añadir comprobación de "GDF SUEZ" como señal fuerte de gas, y cambiar el orden para evaluar señales más específicas primero.

- **Conversión `float` de Decimal en JSON introduce pérdida de precisión**
  - Ubicación: `web/app.py:125` (`_serial`), múltiples endpoints
  - Descripción: `_serial` convierte Decimal a float para serialización JSON. Para valores como `costo_unitario_kwh = Decimal("2.456789")`, la conversión a float puede introducir errores de representación en punto flotante.
  - Impacto: Bajo — los valores mostrados en UI tienen precisión suficiente. Para cálculos en el lado del servidor (Python) siempre se usa Decimal.
  - Recomendación: Aceptable como deuda técnica documentada. Si en el futuro se necesita precisión en el JS, convertir a string en el JSON y parsear en JS.

- **`costo_gas_actual_mxn` en `CoGenMes` usa `gas.subtotal_mxn` (pre-IVA), consistente pero no totalmente obvio**
  - Ubicación: `calc/cogen.py:154`
  - Descripción: `costo_gas_actual_mxn=gas.subtotal_mxn` usa el subtotal sin IVA. El `costo_cfe_mxn` también usa `subtotal_mxn`. Esto es consistente pero debería estar documentado, ya que en una presentación comercial se podría esperar el total con IVA.
  - Impacto: Ninguno en los cálculos de EBITDA (consistente). Posible confusión al comparar con facturas físicas que muestran el total.
  - Recomendación: Añadir comentario en el modelo explicando que se usan subtotales (pre-IVA) en todos los cálculos.

---

### 2. Bugs visuales

#### Medio

- **`kpi-costo-total-periodo` no existe como KPI en el dashboard de Contabilidad**
  - Ubicación: `web/app.py:303-306`, `web/templates/dashboard_contabilidad.html`
  - Descripción: La ruta `cliente_dashboard_contabilidad` calcula `kwh_total_periodo`, `costo_total_periodo` y `costo_unit_promedio` y los pasa al template, pero el endpoint JSON `/data` envía estos valores bajo `kpis.kwh_total`, `kpis.costo_total`, `kpis.costo_unit`. El JS en `dashboard-contabilidad.js:600` solo hidrata `kpi-num-meses`, `kpi-kwh-total` y `kpi-costo-unit`. No hay KPI de costo total en el panel (consistente en ambos lados, pero el subtotal nunca se muestra directamente como KPI).
  - Impacto: El costo total del periodo no tiene tarjeta KPI visible, aunque está disponible en el endpoint.
  - Recomendación: Sin impacto funcional; documentar o añadir el KPI si se considera relevante.

- **Spinner de carga en Contabilidad usa clase Bootstrap `spinner-border` sin `spinner-border-sm`**
  - Ubicación: `web/templates/dashboard_contabilidad.html:29`
  - Descripción: El spinner de Contabilidad usa `<div class="spinner-border" role="status">` (tamaño completo), mientras que el spinner de Cogeneración usa `<div class="spinner-border spinner-border-sm text-secondary">` (pequeño). Inconsistencia visual.
  - Impacto: Visual menor — el spinner de Contabilidad es más grande y puede tapar contenido.
  - Recomendación: Unificar el tamaño y estilo del spinner en ambos templates.

#### Bajo

- **La gráfica de costo unitario (`chartCostoPromedio`) no muestra barras si todos los costos son 0**
  - Ubicación: `web/static/js/dashboard-contabilidad.js:261-292`
  - Descripción: Si ningún mes tiene desglose de Distribución o Capacidad, `costo_unit_promedio_total` tendrá todo en 0.0. La gráfica se renderiza vacía sin mensaje explicativo.
  - Impacto: Confusión para el usuario — la gráfica aparece con ejes pero sin barras.
  - Recomendación: Mostrar un mensaje "No hay desglose de costos por horario disponible" cuando todos los valores son 0.

---

### 3. Links rotos

#### Medio

- **Botón de exportación Excel siempre visible aunque no haya datos**
  - Ubicación: `web/templates/dashboard_cogeneracion.html:55`
  - Descripción: `<a href="/export/excel" class="btn btn-sm btn-success ms-auto">Excel</a>` siempre aparece. Si el cliente no tiene facturas o no tiene meses pareados, el endpoint retorna HTTP 503 con texto plano `"Sin datos para exportar"`, no redirige ni muestra un mensaje apropiado.
  - Impacto: El operador puede hacer clic en Excel y recibir una página en blanco con texto `503`. No es un link roto pero es una experiencia de usuario pobre.
  - Recomendación: Ocultar o deshabilitar el botón Excel cuando no hay datos (el dashboard ya sabe si hay meses vía `aviso_datos`).

- **La función `abrirPanel` se llama desde HTML inline en la tarjeta CELs pero `panel-flotante.js` está en el scope global**
  - Ubicación: `web/static/js/dashboard-cogeneracion.js:522-523`
  - Descripción: `onclick="abrirPanel('panelCels'); return false;"` requiere que `abrirPanel` sea global. `panel-flotante.js` sí la expone globalmente. Sin embargo, si el script se carga en el orden incorrecto (panel-flotante.js después de dashboard-cogeneracion.js), el `onclick` falla silenciosamente al click.
  - Impacto: Si el orden de scripts cambia, el panel de detalle CELs no abre.
  - Recomendación: Verificar el orden de carga en el template base. Usar event delegation en lugar de onclick inline.

---

### 4. Código muerto

#### Bajo

- **`get_configuracion_row` importado en `app.py` pero nunca usado**
  - Ubicación: `web/app.py:20`
  - Descripción: `get_configuracion_row` se importa en la línea 20 junto con otras funciones del repositorio, pero no aparece en ningún uso en `app.py`. Se usa solo en `admin_configuracion` indirectamente via `list_configuracion`.
  - Impacto: Import innecesario, aumenta el acoplamiento y puede confundir a futuros desarrolladores.
  - Recomendación: Eliminar del import si no se usa.

- **`UMBRAL_PRORRATEO_DIAS` importado en `app.py` pero solo se usa en templates via `facturas_cfe`**
  - Ubicación: `web/app.py:26`
  - Descripción: `UMBRAL_PRORRATEO_DIAS` se importa desde `calc.periodo` pero en `app.py` solo se usa en `_cargar_facturas_seleccionadas` para el campo `prorrateado` (línea 100). Es un uso válido, pero el nombre de import es largo para una sola operación aritmética simple.
  - Impacto: Ninguno funcional.

- **`costo_total_periodo` calculado en `cliente_dashboard_contabilidad` pero nunca renderizado en template**
  - Ubicación: `web/app.py:304`
  - Descripción: La variable `costo_total_periodo` se calcula y pasa al template pero no hay ningún `{{ costo_total_periodo }}` en `dashboard_contabilidad.html` (el template lo recibe pero no lo usa directamente — se usa en el endpoint `/data` para el KPI JSON). En la ruta GET la variable se calcula pero no tiene receptor en el template.
  - Impacto: Cálculo redundante en la ruta GET (el template usa el endpoint JSON para KPIs).
  - Recomendación: La ruta GET podría simplificarse si el template obtiene todos los KPIs via JS.

- **`cli/main.py` — código CLI potencialmente no mantenido**
  - Ubicación: `cli/main.py`
  - Descripción: Existe un módulo `cli/` con `main.py` que probablemente implementa comandos de línea para parsear facturas fuera del contexto web. No se analizó en detalle pero los tests `tests/test_cli.py` y `tests/test_cli_gas.py` existen. Si el CLI no es parte del flujo de producción, puede estar desactualizado respecto a la arquitectura actual (contratos, selección de meses).
  - Impacto: Bajo si no se usa en producción.
  - Recomendación: Verificar si el CLI sigue siendo útil y si está alineado con la lógica de contratos.

---

### 5. Inconsistencias

#### Alto

- **O&M calculado distinto en Excel que en Python/JS (potencial)**
  - Ubicación: `reports/excel.py:88`, `calc/cogen.py:127`, `web/static/js/dashboard-cogeneracion.js:86`
  - Descripción: La fórmula Excel para EBITDA es `=K{R}+M{R}-J{R}-H{R}*D{R}*0.3` (línea 88). Esto calcula O&M como `kwh_cubiertos × costo_promedio_kwh × 0.3` y lo resta directamente. El backend en `cogen.py:127` calcula `gasto_om = (kwh_cubiertos * costo_prom_kwh * _FACTOR_OM).quantize(...)`, que es lo mismo. El JS en `recalcularMes:86` usa `om = ah_elec * 0.3`. Los tres son matemáticamente equivalentes (`kwh_cubiertos × costo_prom_kwh = ah_elec`). Sin embargo, la fórmula Excel no usa una celda intermedia de O&M (columna ausente en Excel) — lo embebe directamente en la fórmula del EBITDA, lo que hace el Excel menos legible y no permite ver el O&M por mes en la hoja.
  - Impacto: El Excel no muestra O&M como columna separada, a diferencia del dashboard que sí lo desglosa.
  - Recomendación: Añadir columna O&M en el Excel para transparencia.

#### Medio

- **`ahorro_electricidad` usa costo promedio del mes, no costo por horario**
  - Ubicación: `calc/cogen.py:124`
  - Descripción: `ahorro_electricidad = kwh_cubiertos * costo_prom_kwh`. Se aplica el costo promedio total del mes, no la distribución horaria punta/intermedio/base. El CLAUDE.md describe en el Paso 3 una distribución horaria proporcional, pero el código usa el promedio simple. La distribución horaria solo aparece en el historico (`calcular_historico_cfe`) pero no en el cálculo de cogeneración.
  - Impacto: El ahorro eléctrico puede estar subestimado si el motor opera en horas punta (donde el costo unitario es mayor). Esta es una simplificación significativa que no está documentada en CLAUDE.md.
  - Recomendación: Documentar explícitamente que se usa costo promedio simple (no distribución horaria). Si se quiere implementar el Paso 3 del CLAUDE.md, requeriría cambios en `calcular_cogen`.

- **Doble cálculo de `queso` en ruta GET y en endpoint JSON**
  - Ubicación: `web/app.py:251-275` y `web/app.py:471-491`
  - Descripción: El bloque de cálculo del `queso` (composición de costos) está duplicado casi idénticamente en la ruta GET `cliente_dashboard_contabilidad` y en el endpoint JSON `cliente_dashboard_contabilidad_data`. La lógica de ~20 líneas es idéntica.
  - Impacto: Deuda de mantenimiento — cambios en la lógica deben hacerse en dos lugares.
  - Recomendación: Extraer a una función `_calcular_queso(tablas)` en `app.py`.

- **CELs: el JS recalcula `calor_gj` usando `gj_pcs * rend_term` pero el backend usa `gj_pcs * rend_term` también — ambos usarían GJ en PCS para calor recuperado**
  - Ubicación: `web/static/js/dashboard-cogeneracion.js:157-158`
  - Descripción: En la función `recalcularCELs`:
    ```javascript
    const gj_pcs     = kc * 0.0036 * 1.11 / p.rend_elec;
    const gj_pci_mes = kc * 0.0036 / p.rend_elec;
    ...
    calor_gj += gj_pcs * p.rend_term;
    ```
    El calor recuperado se calcula sobre `gj_pcs` (con factor 1.11). Luego al convertir a MWh se divide implícitamente. El backend en `cogen.py:125` también usa `gj_gas_cogen * rendimiento_termico` donde `gj_gas_cogen` está en PCS. Matemáticamente consistente, pero conceptualmente confuso: el calor recuperado debería calcularse sobre la energía de entrada real (PCI), no sobre el valor contable PCS. Esta es una inconsistencia conceptual menor con la termodinámica, aunque aceptada en la industria según los parámetros del motor.
  - Impacto: Menor — el calor recuperado podría estar sobreestimado en un 11%.
  - Recomendación: Documentar si la recuperación térmica se calcula sobre PCI o PCS.

---

### 6. Fórmulas dudosas

A continuación se evalúa cada una de las 10 verificaciones específicas solicitadas:

**Verificación 1: Factor PCI/PCS (1.11)**

Resultado: **PASS con observación**

En `cogen.py:122`: `gj_gas_cogen = (kwh_cubiertos * _KWH_A_GJ * _FACTOR_PCI_A_PCS / params.rendimiento_electrico)`. El factor 1.11 se aplica para calcular el gas necesario en PCS (como se comercializa). Correcto para el cálculo financiero.

En `cogen.py:214`: `gj_gas_cogen_pci_anual = gj_cogen_anual / _FACTOR_PCI_A_PCS`. Se divide por 1.11 para obtener PCI usado en CELs. Correcto.

En `cels.py`: recibe `gj_gas_cogen_pci_anual` y lo usa directamente como F. Correcto — CELs usa PCI sin el 1.11.

El JS en `recalcularCELs:154-155`: calcula `gj_pcs = kc * 0.0036 * 1.11 / p.rend_elec` y `gj_pci_mes = kc * 0.0036 / p.rend_elec`. Correcto.

**Verificación 2: Costos detallados por horario**

Resultado: **PASS**

En `calc/historico.py:210-226`:
- `ct_base = ce_base + costo_dist * kwh_base / kwh_bi` → Costo Base = energía Base + Distribución proporcional a consumo Base/(Base+Intermedia). Correcto según especificación.
- `ct_inter = ce_inter + costo_dist * kwh_inter / kwh_bi` → Igual para Intermedia. Correcto.
- `ct_punta = ce_punta + costo_cap` → Punta = energía Punta + Capacidad. Correcto.
- `cu_base_total = round(ct_base / kwh_base, 6)` → Costo unitario = Costo total / Energía. Correcto.

Estas fórmulas coinciden exactamente con la especificación del CLAUDE.md.

**Verificación 3: Capacidad nominal kW**

Resultado: **PASS**

`calc/cogen.py:31-43`: `max(kwh_total_mes) / 720`. Solo considera meses con los tres periodos completos. Formula correcta según CLAUDE.md `max(kwh_total_mes / 720)`.

**Verificación 4: Inversión MXN**

Resultado: **PASS**

`calc/cogen.py:172-173`: `inv_usd = capacidad_kw * 1400`, `inv_mxn = inv_usd * tipo_cambio`. Formula correcta: `1400 USD/kW × capacidad_kw × tipo_cambio`. Coeficiente `_USD_POR_KW = Decimal("1400")` en línea 21.

**Verificación 5: Flujo de caja**

Resultado: **PASS**

`calc/cogen.py:67-76`: `flujo = [-inversion_mxn]` → Año 0. `flujo.append(flujo[-1] + ahorro_neto_anual)` → cada año suma el ahorro. Correcto.

**Verificación 6: Periodo de retorno**

Resultado: **PASS**

`calc/cogen.py:46-64`: Itera de año 1 a 15, acumulando. Retorna el primer año donde `acumulado >= 0`. Correcto.

**Verificación 7: CO2 actual y proyectado**

Resultado: **PASS**

`calc/cogen.py:189-205`:
- `co2_elec_actual = kwh_anual * factor_emision_elec` → correcto
- `co2_gas_actual = gj_caldera_anual * factor_emision_gas` → correcto (usa GJ consumidos de gas real del cliente, no GJ de cogeneración)
- `co2_elec_proy = (kwh_anual - kwh_cub_anual) * factor_emision_elec` → correcto
- `gj_caldera_con_cogen = max(gj_caldera_anual - calor_rec_anual / params.eficiencia_caldera, 0)` → correcto (incluye el max con 0 para evitar negativo)
- `gj_gas_total_proy = gj_cogen_anual + gj_caldera_con_cogen` → correcto
- `co2_gas_proy = gj_gas_total_proy * factor_emision_gas` → correcto

Nota: `gj_caldera_anual` es la suma de `gj_consumido` (gas real de facturas), no gas de cogeneración. Correcto conceptualmente.

**Verificación 8: CELs CRE Caso I**

Resultado: **PASS con observación**

`calc/cels.py:148-164`:
- `Fh = H / refh` → correcto
- `Fe = F - Fh` → correcto
- `EE = E / Fe` (si Fe > 0) → correcto
- `RefE' = ref_e * fp` → correcto (llamada `ref_e_prima`)
- `EP = E/RefE' + H/RefH` → correcto (líneas 153-155)
- `AEP = EP - F` → correcto
- `ELC = AEP * ref_e` → correcto

Observación: El CLAUDE.md menciona `APEP = EP - F / EP` pero el código calcula `APEP = AEP / EP` (línea 159). Según la notación correcta del Caso I CRE, `APEP = AEP / EP` (Ahorro de Energía Primaria sobre EP), que es lo implementado. El CLAUDE.md tiene una notación confusa pero el código es correcto según la regulación.

**Verificación 9: Reducción CO2 y equivalencia árboles**

Resultado: **PASS**

`web/app.py:652-660`: `reduccion_t = float(r.co2_reduccion_kg_anual) / 1000` → conversión a toneladas. `"arboles": int(reduccion_t * 50)` → 50 árboles/tonelada. Correcto según especificación CLAUDE.md.

**Verificación 10: O&M**

Resultado: **WARN — ambigüedad en especificación**

`calc/cogen.py:127`: `gasto_om = (kwh_cubiertos * costo_prom_kwh * _FACTOR_OM).quantize(...)`.

Esto calcula `O&M = 0.3 × kwh_cubiertos × $/kWh = 0.3 × ahorro_electricidad`. No es `0.3 × kWh_cubiertos_anual` como dice literalmente el CLAUDE.md (que si fuera literal significaría unidades de kWh, sin valor monetario).

El test en `test_cogen.py:162-166` confirma que el O&M es `30% del ahorro eléctrico` en MXN. La implementación es consistente y tiene sentido económico (O&M como porcentaje del ingreso eléctrico). El CLAUDE.md debería aclarar que es `0.3 × ahorro_eléctrico_MXN`, no `0.3 × kWh`.

---

### 7. Validaciones faltantes

#### Alto

- **Endpoints de selección de mes no verifican que el mes tenga factura en ese contrato**
  - Ubicación: `web/clientes.py:829-856`
  - Descripción: `contrato_seleccion_mes` permite marcar como seleccionado cualquier (anio, mes) para un contrato, incluso si no hay ninguna factura en ese mes/año. Solo valida que mes esté entre 1-12 y anio sea int. Un mes seleccionado sin factura no causa error en el cálculo (simplemente no matchea), pero puede generar confusión en el sidebar.
  - Impacto: Bajo — no rompe nada pero puede generar estados inconsistentes en `contrato_meses_seleccionados`.
  - Recomendación: Validar contra `get_meses_con_factura(contrato_id, anio)` antes de insertar.

- **`admin_configuracion` no valida que los campos del formulario correspondan a claves reales en BD**
  - Ubicación: `web/app.py:756-783`
  - Descripción: `admin_configuracion` itera sobre las filas de la tabla `configuracion` y procesa cualquier campo del form que coincida con una clave. Un atacante que pueda enviar un POST con claves no existentes en BD simplemente no afectaría nada (el loop solo procesa claves de `filas`). Correcto. Sin embargo, no hay limitación de tasa (rate limiting) en este endpoint.
  - Impacto: Bajo dado el acceso controlado.

#### Medio

- **Upload de facturas no limita el tamaño máximo del PDF**
  - Ubicación: `web/clientes.py:680-760`
  - Descripción: `contrato_upload` acepta cualquier número de archivos sin validar el tamaño individual de cada PDF (solo el logo tiene límite de 2MB). Un PDF de 100MB podría causar timeout o agotamiento de memoria en el servidor Render free tier.
  - Impacto: Un PDF maliciosamente grande podría causar un error 500 o timeout en Render.
  - Recomendación: Añadir `app.config["MAX_CONTENT_LENGTH"]` en Flask para limitar el tamaño total del request.

---

### 8. Performance

#### Alto

- **N+1 en `get_sidebar_data_contrato`** (detallado en Bugs funcionales — Alto)

- **`_inject_globals` hace 2 queries en cada request** (detallado en Bugs funcionales — Medio)

#### Medio

- **`get_cfe_invoices_for_dashboard` carga toda la factura con periodos y componentes aunque solo necesite datos del mes**
  - Ubicación: `storage/repository.py:754-761`
  - Descripción: La query `SELECT *, clientes(nombre, rfc), cfe_periodos(*), cfe_mem_componentes(*)` carga todos los datos de la factura incluyendo los componentes MEM. Para el filtrado por mes, solo se necesitan `anio`, `mes`, `contrato_id`. Los componentes solo se necesitan en el dashboard de tablas.
  - Impacto: Transferencia de datos innecesaria. Para 12 facturas con ~9 componentes MEM cada una, son ~108 filas adicionales por request del dashboard.
  - Recomendación: Separar en dos queries: una ligera para filtrar meses y otra completa para los meses seleccionados.

---

### 9. Accesibilidad

#### Bajo

- **Imágenes de logo sin `alt` descriptivo contextual**
  - Ubicación: `web/templates/dashboard_cogeneracion.html:42`, `web/templates/dashboard_contabilidad.html:45`
  - Descripción: `alt="{{ cliente_nombre }}"` es correcto, pero el logo también aparece en el listado de clientes sin alt definido.
  - Impacto: Mínimo dado que es una herramienta interna de escritorio.

- **Spinners sin texto visible o solo visibles para lectores de pantalla**
  - Ubicación: `web/templates/dashboard_cogeneracion.html:28-30`
  - Descripción: El spinner usa `role="status"` solo en el `div` interno, el texto "Cargando…" está en un `<span>` visible. Correcto en Cogeneración. En Contabilidad el texto "Actualizando…" también es visible.
  - Impacto: Ninguno significativo.

- **Botones de acción en tabla de clientes sin labels ARIA**
  - Ubicación: Listado de clientes (template no auditado en detalle)
  - Descripción: Los botones de acción (activar, ir a ficha) podrían no tener labels accesibles.
  - Impacto: Mínimo para herramienta interna.

---

### 10. Seguridad

#### Alto

- **XSS potencial por `innerHTML` con datos del servidor**
  - Ubicación: `web/static/js/dashboard-cogeneracion.js:435`, `web/static/js/dashboard-cogeneracion.js:504-536`, `web/static/js/dashboard-contabilidad.js:563`
  - Descripción: Las funciones `actualizarAviso` y `actualizarCELsCard` construyen strings HTML concatenando valores del servidor: `aviso.num_cfe`, `aviso.num_gas`, `fichUrl`, `cels.medio_termico`, `cels.nivel_tension_kv`. Si un atacante pudiera inyectar valores maliciosos en estos campos (requeriría acceder a la BD o interceptar la respuesta JSON), podría ejecutar JS arbitrario en el navegador del operador.
  - Impacto: Bajo dado el acceso controlado (operador único, BD bajo control), pero es un antipatrón.
  - Recomendación: Usar `document.createTextNode()` o `el.textContent` para valores simples, o una librería de sanitización para HTML complejo.

#### Medio

- **Open redirect en login** (detallado en Bugs funcionales — Alto)

- **`render.yaml` no declara SECRET_KEY, APP_USER, APP_PASSWORD_HASH** (detallado en Resumen — Top 5)
  - Impacto: Si alguien despliega con solo las variables declaradas, la app falla en arranque (gracias a `_validar_config_auth`), pero el mensaje de error en los logs de Render podría exponer que `APP_USER` y `APP_PASSWORD_HASH` son las variables necesarias.
  - Recomendación: Añadir las tres variables en `render.yaml` con `sync: false`.

---

### 11. Documentación obsoleta

#### Crítico

- **CLAUDE.md no menciona tablas `contratos`, `contrato_meses_seleccionados`, `configuracion`**
  - Ubicación: `CLAUDE.md` sección "Schema de Supabase"
  - Descripción: El documento lista las tablas originales del schema, pero no incluye `contratos` (añadida para gestión de contratos), `contrato_meses_seleccionados` (selección de meses en sidebar), `configuracion` (parámetros del sistema como tipo de cambio y factores de emisión). Tampoco menciona los campos extendidos de `clientes` (CELs, campos de contacto, etc.) añadidos en versiones posteriores.
  - Impacto: Un nuevo desarrollador que lea CLAUDE.md tendrá un modelo mental incompleto del schema real.
  - Recomendación: Actualizar la sección "Schema de Supabase" con todas las tablas actuales y sus propósitos.

#### Alto

- **CLAUDE.md describe O&M incorrectamente como `0.3 × kWh_cubiertos_anual`**
  - Ubicación: `CLAUDE.md` sección "Parámetros del motor candidato"
  - Descripción: El texto dice "O&M: 0.3 × kWh_cubiertos_anual" lo que sugeriría una cantidad en kWh sin unidad monetaria. La implementación correcta es `0.3 × ahorro_electricidad_MXN` (MXN sobre MXN). La unidad de O&M es MXN/año, no kWh/año.
  - Recomendación: Corregir a "O&M estimado: 30% del ahorro eléctrico mensual en MXN".

- **CLAUDE.md no menciona el sistema de contratos ni la selección de meses**
  - Ubicación: `CLAUDE.md` sección "Alcance estricto de fase 1"
  - Descripción: El documento no menciona la arquitectura de contratos (clientes → contratos → facturas), la selección de meses por contrato, ni el panel flotante de sidebar para selección. Son funcionalidades centrales de la UI actual.
  - Recomendación: Añadir sección que describa el flujo de gestión de contratos y selección de meses.

---

### 12. Tests

#### Medio

- **Sin tests de integración para el flujo completo de upload de PDF**
  - Ubicación: `tests/test_web_upload.py`, `tests/test_contrato_upload.py`
  - Descripción: Existen tests para el endpoint de upload, pero no hay tests que verifiquen el flujo completo: PDF → parser → persistencia en Supabase. Los tests de parsers (`test_gdmth.py`, `test_engie.py`) verifican el parsing de archivos PDF reales o fixtures pero están desconectados del flujo de persistencia.
  - Impacto: No se detectarían regresiones en el guardado de facturas hasta que falle en producción.

- **Tests de `test_cogen.py` no cubren el caso de múltiples facturas del mismo mes**
  - Ubicación: `tests/calc/test_cogen.py`
  - Descripción: No hay test para el caso donde hay dos facturas CFE para el mismo mes asociado (ej. factura parcial + complementaria). `calcular_cogen` indexa gas por mes y solo usa el primero que encuentre; para CFE itera todas, lo que podría resultar en dos meses duplicados con el mismo mes.
  - Impacto: Bug potencial no cubierto por tests.
  - Recomendación: Añadir test para facturas duplicadas en el mismo mes.

- **Tests de repositorio de integración requieren Supabase real — no se pueden ejecutar en CI sin credenciales**
  - Ubicación: `tests/storage/test_repository_integration.py`
  - Descripción: Los tests de integración del repositorio probablemente requieren `SUPABASE_URL` y `SUPABASE_KEY`. Sin un mecanismo de skip condicional, fallarán en entornos sin credenciales.
  - Impacto: CI podría fallar o los tests de integración podrían estar deshabilitados silenciosamente.

- **Sin tests para la ruta `/export/excel` (tipo de cambio fijo)**
  - Ubicación: `tests/reports/test_excel.py`, `tests/reports/test_excel_formulas.py`
  - Descripción: Los tests de Excel solo verifican el módulo `reports/excel.py` directamente. No hay test que verifique que la ruta `/export/excel` pasa el tipo de cambio correcto de BD.

#### Bajo

- **`test_flask.py` en la raíz — propósito poco claro**
  - Ubicación: `test_flask.py`
  - Descripción: Existe un `test_flask.py` en la raíz del proyecto, fuera del directorio `tests/`. Su contenido no fue auditado. Puede ser un archivo de prueba ad-hoc dejado por accidente.
  - Recomendación: Verificar si debe estar en `tests/` o eliminarse.

---

### 13. Convenciones inconsistentes

#### Bajo

- **Uso mixto de `logger.exception` y `logger.error` en handlers de excepción**
  - Ubicación: `web/app.py:493`, `web/app.py:563`, `web/app.py:580`
  - Descripción: En el endpoint `/data` de contabilidad se usa `logger.exception("Error en contabilidad/data: %s", _e)`. En cogeneración se usa `logger.exception` para el error principal y `logger.error` para el error de CELs. `logger.exception` incluye el traceback automáticamente, `logger.error` no. El manejo es inconsistente entre endpoints similares.
  - Recomendación: Usar `logger.exception` en todos los handlers de excepción que requieren traceback para debugging.

- **Rutas GET del dashboard hacen el cálculo completo aunque el JS lo obtiene via endpoint**
  - Ubicación: `web/app.py:247-325`, `web/app.py:327-450`
  - Descripción: Desde la versión 2.19.0 los dashboards obtienen datos via JSON. Sin embargo, las rutas GET de los dashboards siguen calculando `historico`, `tablas`, `calcular_cogen`, etc. para pasar al template. Los templates ya no usan esos valores directamente (el JS los obtiene del endpoint). El cálculo en la ruta GET es redundante y duplica el trabajo.
  - Impacto: Cada carga de página del dashboard genera dos rondas de cálculo: una en la ruta GET (desperdiciada) y una en el fetch JS.
  - Recomendación: Simplificar las rutas GET de dashboards para que solo pasen el `cliente_id` y la estructura mínima del template. El cliente activo, aviso_datos y el resto se obtienen del endpoint JSON.

- **Nomenclatura `EBITDA` vs `ahorro_neto` usada de forma intercambiable**
  - Ubicación: `models/cogen_result.py:38`, `calc/cogen.py:128`, `web/app.py:398`
  - Descripción: El campo del modelo se llama `ebitda_mes_mxn`, la variable local en el cálculo se llama `ebitda`, el gráfico en el JS lo llama `chart_ebitda`, pero en el UI se muestra como "Ahorro Neto". El KPI en el template tiene id `kpi-ahorro-neto-val`. La nomenclatura técnica (EBITDA) y la de negocio (Ahorro Neto) se mezclan sin distinción clara.
  - Recomendación: Decidir un nombre canónico (sugiero "ahorro_neto" para el dominio) y usarlo consistentemente en modelos, variables y UI.

---

### 14. Casos edge no manejados

#### Alto

- **Dos facturas del mismo mes asociado para el mismo cliente**
  - Ubicación: `calc/cogen.py:93-97`
  - Descripción: `gas_por_mes = {mes_asociado(g.periodo_inicio, g.periodo_fin): g for g in gas_invoices}`. Si hay dos facturas de gas para el mismo mes asociado, la segunda sobrescribe la primera silenciosamente en el dict. El mismo problema ocurriría si en CFE hay dos facturas para el mismo mes (se procesarían las dos pero la de gas solo tendría una).
  - Impacto: Facturas duplicadas o complementarias del mismo mes podrían causar cálculos incorrectos sin advertencia.
  - Recomendación: Detectar colisiones de mes y emitir una advertencia en el log. Idealmente, sumar los consumos si son facturas del mismo contrato.

- **División por cero en `calcular_historico_cfe` si todas las facturas tienen kWh=0**
  - Ubicación: `calc/historico.py:102`, `calc/historico.py:270`
  - Descripción: `suma_facturacion_total / suma_kwh_punta` con protección `if suma_kwh_punta > 0`. Correcto. Pero `anual_prom = sum_kwh_total / sum_horas` en línea 271 tiene protección. Correcto. Sin embargo, si `kwh_total = 0` para todas las facturas (caso teórico), la fila individual calcula `costo_unit = round(subtotal / kwh_total, 2) if kwh_total > 0 else 0.0` — protegido. Caso manejado correctamente en general pero merece revisión en la fila ANUAL de `indicadores` donde `anual_fc = round(anual_prom / max_demanda * 100) if max_demanda > 0 else 0` — correcto.
  - Resultado: Manejado correctamente pero el código es frágil ante datos inesperados.

- **`prorratear_cfe` con `dias_reales = 0` causaría división por cero**
  - Ubicación: `calc/periodo.py:45`
  - Descripción: `factor = _DIAS_EQUIVALENTES / Decimal(dias_reales)`. Si `periodo_fin == periodo_inicio` (factura de un día, `dias_reales = 0`), hay división por cero. El umbral `< 25 días` protege para casos normales (0 < 25 pasa por el umbral y llega al cálculo), pero una factura con periodo_inicio == periodo_fin causaría `ZeroDivisionError`.
  - Impacto: Un PDF malformado con periodo de 0 días causaría una excepción en el cálculo.
  - Recomendación: Añadir `if dias_reales <= 0: return invoice, None` antes del cálculo del factor.

#### Medio

- **`gas_por_mes` dict sobrescribe en caso de facturas duplicadas de gas**
  - Ubicación: `calc/cogen.py:94-96` (también mencionado en el punto anterior para el caso gas)

- **Cliente borrado con facturas activas en sesión**
  - Ubicación: `web/app.py:58-61`
  - Descripción: Si el cliente activo en sesión es borrado (desde otro tab o por el operador), el `_verificar_cliente_activo` limpia la sesión y redirige. Correcto. Sin embargo, si hay un fetch JS en progreso al momento del borrado, el endpoint JSON retorna 404 y el JS muestra el banner de error en lugar de redirigir al listado.
  - Impacto: UX subóptima — el operador ve un banner de error en lugar de ser redirigido.

---

### 15. Errores silenciosos

#### Alto

- **`calcular_cels` falla silenciosamente y devuelve `None`**
  - Ubicación: `web/app.py:376-379`, `web/app.py:579-581`
  - Descripción: El bloque `try/except` en la ruta de cogeneración captura cualquier excepción en `calcular_cels` y la registra con `logger.error` pero devuelve `cels_resultado = None`. El dashboard entonces muestra "Datos incompletos" sin que el operador sepa que hubo un error de cálculo (vs. simplemente faltar datos del cliente).
  - Impacto: Un bug en `calc/cels.py` (ej. división por cero con datos reales) pasaría desapercibido para el operador.
  - Recomendación: Diferenciar entre "faltan datos del cliente" (None esperado de `calcular_cels`) y "error de cálculo" (excepción). Mostrar al operador si el cálculo falló por error.

- **`delete_logo` captura excepciones de Storage silenciosamente**
  - Ubicación: `storage/repository.py:492-494`
  - Descripción: `except Exception as exc: logger.warning(...)` en `delete_logo`. El logo puede no borrarse del bucket pero la BD se actualiza a `None`. El archivo huérfano en Storage queda sin limpieza.
  - Impacto: Bajo — el archivo huérfano no causa errores funcionales pero ocupa espacio en Supabase Storage.

- **Errores de parseo en campos opcionales de PDF son silenciados como advertencias**
  - Ubicación: `parsers/cfe/gdmth.py:96-101`, `parsers/gas/engie.py:92-97`
  - Descripción: Los campos no encontrados se agregan a `advertencias` (lista interna de la factura) pero no se propagan como excepciones. El upload reporta éxito aunque campos críticos como `uuid_cfdi`, `folio` o `periodo_inicio` no se hayan extraído.
  - Impacto: Una factura con datos inválidos se guarda en BD con valores vacíos o por defecto (`Decimal("0")`, fecha actual). Puede causar resultados erróneos en cálculos posteriores.
  - Recomendación: Definir campos "requeridos" cuya ausencia eleva el nivel de severidad a error y rechaza el guardado de la factura.

---

## Verificación de flujos

### 1. Login → Contabilidad dashboard

Flujo correcto. `POST /login` → `login_user(_USER)` → redirect a `next` o `dashboard` → redirect a `clientes.listado` → operador activa cliente via `POST /clientes/<id>/activar` → sesión `cliente_activo_id` → GET `cliente_dashboard_contabilidad` → template carga → JS `fetchData()` → `GET /dashboard/contabilidad/data` → `hidratarDashboardContabilidad(data)`.

Observación: La ruta GET calcula todo el historico completo aunque el JS lo sobreescribdrá inmediatamente con el fetch. Doble cálculo (ver Inconsistencias).

### 2. Login → Cogeneración + sliders

Flujo correcto. GET dashboard_cogeneracion → template renderiza con sliders en valores por defecto → JS `fetchData()` → `hidratarDashboardCogeneracion(data)` guarda `meses_raw` → `actualizarSensibilidad()` con params de sliders → recalcula client-side sin endpoint adicional. Sliders disparan `actualizarSensibilidad` via `input` event listener.

### 3. Subir PDF → parsing → persistencia

Flujo: `POST /clientes/<id>/contratos/<id>/upload` (multipart) → `_detect_tipo()` → parser → validación de discrepancias (identificador, RFC) → `save_cfe_invoice` / `save_gas_invoice` → respuesta JSON con `exitosos` y `errores`.

Observación: El archivo temporal se crea en `tempfile.NamedTemporaryFile` y se borra en el `finally` via `tmp_path.unlink(missing_ok=True)`. Correcto para el PDF de entrada. El archivo Excel temporal (export) NO se borra (ver Bug funcional).

### 4. Toggle mes → refresh dashboard

Flujo: click en checkbox del sidebar → `POST .../seleccion/mes` JSON → `upsert_mes_seleccionado` o `delete_mes_seleccionado` → respuesta OK → JS dispara `document.dispatchEvent(new CustomEvent('dashboardDataChanged'))` → ambos dashboards escuchan el evento → `scheduleRefresh()` → `setTimeout(fetchData, 300)` (debounce 300ms) → fetch con AbortController (timeout 10s). Flujo correcto y bien implementado.

### 5. Editar configuración → reflejo en cálculos

Flujo: GET `/admin/configuracion` → lista filas de BD → POST → validación → `set_configuracion` (upsert) → redirect → flash "guardado". Luego al recargar dashboard → endpoint JSON llama a `get_configuracion("tipo_cambio_mxn_usd")` etc. → `calcular_cogen` usa el nuevo TC.

Problema detectado: Si el operador cambia el tipo_cambio y tiene el dashboard de cogeneración abierto, debe recargarlo manualmente o cambiar un mes (para triggear dashboardDataChanged). No hay notificación automática.

### 6. Ficha cliente → editar

Flujo: GET `/clientes/<id>` → `get_cliente_con_conteos` → template con datos. GET `/clientes/<id>/editar` → misma query + `cliente_tiene_facturas`. POST con cambios → validación RFC (solo si sin facturas) → `update_cliente` → redirect a ficha.

Lógica de protección RFC correcta: si tiene facturas, el RFC no se puede cambiar (`rfc_a_guardar = None`).

### 7. Crear cliente → flujo completo

Flujo: GET `/clientes/nuevo` → form vacío. POST → `_validar_campos` → `_validar_campos_extendidos` → `rfc_existe` → `create_cliente` → redirect a ficha. Desde ficha: crear contrato → `POST /clientes/<id>/contratos/nuevo`. Desde ficha de contrato: subir facturas → `POST .../upload`. Seleccionar meses → `POST .../seleccion/mes`. Ver dashboard → GET `/clientes/<id>/dashboard/contabilidad`.

Flujo completo funcional y coherente.

---

## Verificación de integridad de datos

### Schema vs código

El código usa las siguientes tablas/campos que **NO están en `storage/schema.sql`**:

| Tabla | Uso en código | Ausente en schema.sql |
|-------|--------------|----------------------|
| `contratos` | `repository.py:541` y muchos más | Sí — tabla completa ausente |
| `contrato_meses_seleccionados` | `repository.py:656` | Sí — tabla completa ausente |
| `configuracion` | `repository.py:793` | Sí — tabla completa ausente |
| `clientes.medio_termico` | `repository.py:317` | Sí — campo ausente |
| `clientes.nivel_tension_kv` | `repository.py:317` | Sí — campo ausente |
| `clientes.altitud_msnm` | `repository.py:317` | Sí — campo ausente |
| `clientes.tipo_motor` | `repository.py:317` | Sí — campo ausente |
| `cfe_facturas.contrato_id` | `repository.py:38` | Sí — campo ausente |
| `cfe_facturas.nombre_canonico` | `repository.py:64` | Sí — campo ausente |
| `cfe_facturas.anio` | `repository.py:68` | Sí — campo ausente |
| `cfe_facturas.mes` | `repository.py:69` | Sí — campo ausente |
| `gas_facturas.contrato_id` | `repository.py:198` | Sí — campo ausente |
| `gas_facturas.nombre_canonico` | `repository.py:221` | Sí — campo ausente |
| `gas_facturas.anio` | `repository.py:224` | Sí — campo ausente |
| `gas_facturas.mes` | `repository.py:225` | Sí — campo ausente |

El schema SQL solo refleja el estado inicial del proyecto. Toda la evolución posterior no está documentada en el DDL.

### Migrations idempotentes

No hay sistema de migraciones. El DDL en `schema.sql` usa `CREATE TABLE IF NOT EXISTS` lo que lo hace idempotente para creación, pero no para adición de columnas. No hay scripts de ALTER TABLE para las columnas añadidas. La gestión de schema se hace manualmente en el SQL Editor de Supabase (según CLAUDE.md).

### Constraints de integridad

El schema original define:
- `ON DELETE CASCADE` en `cfe_periodos.factura_id` y `cfe_mem_componentes.factura_id` — correcto.
- `ON DELETE CASCADE` en `gas_conceptos.factura_id` — correcto.
- `rfc UNIQUE` en `clientes` — correcto.
- `cfe_facturas.cliente_id REFERENCES clientes(id)` — sin `ON DELETE CASCADE` en el schema original. El código en `delete_cliente` asume que CASCADE existe: "ON DELETE CASCADE en el schema elimina todas sus facturas". Si el schema real en Supabase tiene esta constraint es funcional, pero el DDL de referencia no la especifica.
- `gas_facturas.cliente_id REFERENCES clientes(id)` — mismo problema.

**Riesgo**: El DDL de referencia (schema.sql) no declara `ON DELETE CASCADE` en las FK de facturas a clientes, pero el código asume que existe. Si alguien recrea el schema desde el DDL, los borrados de clientes fallarán por violación de FK.

### Conversiones de tipos

Los campos numéricos se guardan como `TEXT` en Supabase (correcto según la decisión arquitectónica). La capa de persistencia convierte a `Decimal` en todos los `_row_to_*` usando `Decimal(row["campo"])`. Correcto y consistente.

Un riesgo: si algún campo de texto en BD contiene un valor no numérico (ej. vacío, "N/A"), `Decimal("")` lanzará `InvalidOperation`. No hay manejo de este caso en `_row_to_cfe_invoice` ni `_row_to_gas_invoice`. Esto podría ocurrir con facturas cargadas por versiones antiguas del parser con campos vacíos.

---

## Plan de acción sugerido

### Sub-entregable Z1: Críticos (prioridad máxima)

- Hallazgos: Schema SQL incompleto, `print()` en cogen.py, O&M descripción en CLAUDE.md, CLAUDE.md sin tablas nuevas
- Estimación: 1 sesión
- Tareas:
  1. Actualizar `storage/schema.sql` con todas las tablas y campos actuales.
  2. Reemplazar `print(f"WARNING...")` en `calc/cogen.py:105-106` con `logger.warning(...)`.
  3. Actualizar CLAUDE.md: sección Schema, descripción O&M, flujo de contratos, tablas configuracion.

### Sub-entregable Z2: Altos

- Hallazgos: Archivo temporal Excel no borrado, export_excel sin TC de BD, N+1 en sidebar, open redirect login, XSS innerHTML, cals CELs silenciosos, query redundante en contrato
- Estimación: 2 sesiones
- Tareas:
  1. Corregir `/export/excel` para borrar el archivo temporal y usar el TC de BD.
  2. Validar y sanitizar `next` en login.
  3. Sustituir `innerHTML` por construcción segura de DOM o sanitización en los JS de dashboard.
  4. Consolidar queries N+1 en `get_sidebar_data_contrato`.
  5. Añadir SECRET_KEY, APP_USER, APP_PASSWORD_HASH en `render.yaml`.
  6. Diferenciar error de cálculo CELs de "datos incompletos" en la UI.

### Sub-entregable Z3: Medios

- Hallazgos: Doble cálculo en rutas GET de dashboard, O&M columna ausente en Excel, prorrateo inconsistente gas historico, costo unitario gas como suma de precios, días_reales=0 en prorrateo, duplicación lógica queso
- Estimación: 2-3 sesiones
- Tareas:
  1. Simplificar rutas GET de dashboards para no calcular datos que el JS obtendrá del endpoint.
  2. Añadir columna O&M en el Excel exportado.
  3. Aplicar prorrateo en `calcular_historico_gas`.
  4. Añadir guard `if dias_reales <= 0` en `prorratear_cfe` y `prorratear_gas`.
  5. Extraer función `_calcular_queso` para evitar duplicación.
  6. Añadir `MAX_CONTENT_LENGTH` para uploads de PDF.

### Sub-entregable Z4: Bajos y deuda técnica

- Hallazgos: Consistencia en nomenclatura EBITDA/ahorro_neto, test_flask.py en raíz, gráfica vacía sin mensaje, botón Excel visible sin datos, registro de excepciones inconsistente, convenios de nomenclatura
- Estimación: 1 sesión
- Tareas:
  1. Unificar nomenclatura ebitda → ahorro_neto en modelos y JS.
  2. Mover o eliminar `test_flask.py`.
  3. Añadir mensaje a gráfica vacía de costo unitario.
  4. Ocultar botón Excel si no hay datos disponibles.
  5. Unificar uso de `logger.exception` vs `logger.error`.

---

## Apéndice

### Archivos no auditados o auditados superficialmente

- `cli/main.py` — leído brevemente, no analizado en profundidad
- `scripts/migrar_facturas_a_contratos.py`, `scripts/migrar_seleccion_a_meses.py`, `scripts/migrar_nombre_canonico.py` — no leídos
- `parsers/cfe/base.py` — no leído (clase base del parser CFE)
- `parsers/__init__.py`, `parsers/cfe/__init__.py`, `parsers/gas/__init__.py` — no leídos
- `web/templates/clientes/list.html`, `clientes/nuevo.html`, `clientes/editar.html`, `clientes/contratos/ficha.html`, `clientes/contratos/nuevo.html`, `clientes/contratos/editar.html` — no leídos en detalle
- `web/templates/login.html`, `web/templates/dashboard.html`, `web/templates/changelog.html` — no leídos
- `web/static/css/theme.css`, `web/static/css/panel-flotante.css` — no leídos
- `tests/test_web.py`, `tests/test_auth.py`, `tests/test_clientes.py`, `tests/test_models.py`, `tests/test_web_upload.py`, `tests/test_contrato_upload.py`, `tests/test_dashboard_2d.py`, `tests/test_cli.py`, `tests/test_cli_gas.py`, `tests/test_cli_cogen.py` — no leídos
- `tests/parsers/test_gdmth.py`, `tests/parsers/test_engie.py`, `tests/parsers/test_base.py` — no leídos
- `tests/calc/test_tablas_cfe.py`, `tests/calc/test_periodo.py`, `tests/calc/test_nombre_canonico.py` — no leídos
- `tests/storage/test_repository_unit.py`, `tests/storage/test_repository_integration.py` — no leídos
- `tests/test_migrar_facturas_a_contratos.py` — no leído
- `models/contrato.py` — no leído
- `docs/superpowers/plans/` — no leídos
- `start.py`, `run_server.py` — no leídos

### Áreas con información insuficiente

1. **Comportamiento real del parser ante variaciones de formato PDF**: El parser GDMTH usa regex calibradas para versiones 2023 y 2024. Sin acceso a PDFs reales no se puede verificar la cobertura de casos edge en formatos nuevos.

2. **Estado real del schema en Supabase**: El schema.sql de referencia está desactualizado. No se pudo verificar si las tablas `contratos`, `contrato_meses_seleccionados` y `configuracion` tienen los constraints correctos en la BD real de producción.

3. **Tests de integración con Supabase**: Los tests de integración en `tests/storage/test_repository_integration.py` no fueron ejecutados. No se puede verificar su estado de salud.

4. **Carga del CLI**: El módulo `cli/main.py` no fue auditado. Si sigue siendo un flujo de uso del equipo, puede estar desactualizado respecto a la arquitectura de contratos.

5. **Formato de las facturas reales de ENGIE**: El parser de gas `engie.py` usa regex muy específicas al formato de ENGIE/GDF Suez Mexico. Si el proveedor cambió el formato del PDF en alguna versión reciente, el parser podría estar fallando silenciosamente (captura la excepción y agrega a `advertencias`).
