# Estructura del proyecto chpapp

Árbol de directorios relevantes. Archivos de configuración de entorno y archivos generados se omiten.

```
chpapp/
│
├── calc/                          # Capa de cálculo — funciones puras, sin acceso a BD
│   ├── cels.py                    # Cálculo de Certificados de Energías Limpias (CELs CRE)
│   ├── cfe_util.py                # Utilidades compartidas para facturas CFE
│   ├── cogen.py                   # Motor de cogeneración: CoGenMes, CoGenResultado, calcular_cogen, calcular_cogen_ppa
│   ├── excepciones.py             # Excepciones de dominio del motor de cálculo
│   ├── historico.py               # Cálculo de histórico de ahorro para proyección 15 años
│   ├── modelado_chp.py            # Modelado CHP con curva de carga real medida
│   ├── nombre_canonico.py         # Generación de nombre canónico para facturas
│   ├── periodo.py                 # Utilidades de manejo de periodos (meses, rangos)
│   ├── telemetria_costos.py       # Precio unitario MXN/kWh y costo de periodo para telemetría
│   └── telemetria_kpis.py         # KPIs energéticos, económicos y de producción para telemetría
│
├── cli/                           # Scripts de línea de comandos (administración, seeds)
│
├── docs/                          # Documentación del proyecto
│   ├── deuda-tecnica.md           # Inventario de deuda técnica conocida
│   ├── estructura.md              # Este archivo
│   ├── multiusuario.md            # Notas sobre el modelo multiusuario
│   ├── supabase-conventions.md    # Convenciones de acceso a Supabase
│   ├── telemetria-calculos.md     # Inventario de funciones de cálculo de telemetría
│   ├── historico/                 # Diseños iniciales de entregables fase 1
│   └── superpowers/plans/         # Planes de implementación de sesiones de trabajo
│
├── models/                        # Dataclasses de dominio (solo datos, sin lógica de BD)
│   ├── cfe_invoice.py             # CFEInvoice, CFEPeriodo, CFEMemComponente
│   ├── cogen_result.py            # CoGenMes, CoGenResultado, CELsResultado
│   ├── contrato.py                # Contrato, constantes TIPO_ELECTRICO_BASICO, etc.
│   ├── factura_calificado.py      # FacturaCalificado (PPA)
│   ├── gas_invoice.py             # GasInvoice, GasConcepto
│   └── ppa_bloque.py              # PPABloque
│
├── parsers/                       # Parsers de PDF
│   ├── base.py                    # InvoiceParser (clase base abstracta)
│   ├── cfe/                       # Parser CFE GDMTH
│   │   └── gdmth.py
│   ├── electricidad_calificado/   # Parser facturas PPA
│   │   └── gin.py                 # GINParser para facturas GIN
│   └── gas/                       # Parser facturas gas ENGIE
│       └── engie.py
│
├── reports/                       # Generadores de Excel (openpyxl)
│
├── scripts/                       # Scripts de migración y utilidades de BD
│
├── storage/
│   ├── repository.py              # Única capa de acceso a Supabase — patrón repository
│   ├── schema.sql                 # DDL de referencia (no se ejecuta en runtime)
│   └── migrations/                # Scripts SQL de migración incremental
│
├── telemetria/                    # Scripts de seed y simulación de datos de telemetría
│
├── tests/
│   ├── fixtures/                  # PDFs reales para tests de parsers
│   ├── parsers/                   # Tests de parsers PDF
│   ├── test_auth.py
│   ├── test_dashboard_telemetria.py
│   ├── test_seleccion_mezcla.py
│   ├── test_telemetria_costos.py
│   └── ...
│
└── web/
    ├── app.py                     # create_app(), rutas de dashboard y telemetría
    ├── auth.py                    # Blueprint auth_bp — login, logout, sesión Flask
    ├── auth_permissions.py        # Helpers de permisos por rol y empresa
    ├── clientes.py                # Blueprint clientes_bp — rutas CRUD de clientes, contratos,
    │                              #   facturas, activos eléctricos, plantas
    ├── error_logger.py            # Logger de errores a Supabase
    ├── mediciones_parser.py       # Parser de archivos CSV de mediciones eléctricas
    ├── static/
    │   └── js/
    │       ├── dashboard-cogeneracion.js
    │       ├── dashboard-contabilidad.js
    │       └── dashboard-telemetria.js
    └── templates/
        └── clientes/
            ├── activos.html       # Árbol de activos eléctricos con historial de alimentación
            ├── activos.html       # Vista de telemetría por nodo
            └── ...
```

## Jerarquía de tablas Supabase relevante para Fase 2

```
clientes
└── plantas                        (FK cliente_id)
    ├── contratos                  (FK planta_id)
    │   ├── cfe_facturas           (FK contrato_id)
    │   ├── gas_facturas           (FK contrato_id)
    │   └── facturas_electricidad_calificado (FK contrato_id)
    ├── activos_electricos         (FK planta_id, autorreferencial activo_padre_id)
    │   ├── activo_alimentacion_vigencia  (FK activo_id — SIN CASCADE)
    │   └── medidor_activo_vigencia       (FK activo_id ON DELETE CASCADE)
    └── medidores                  (FK planta_id)
        └── mediciones_tiempo_real (FK medidor_id)
            ├── mediciones_agregadas_5min     (vista materializada)
            └── mediciones_agregadas_horarias (vista materializada)
```
