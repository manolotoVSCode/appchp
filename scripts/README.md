# Scripts de migración

Esta carpeta contiene scripts de migración ya ejecutados en producción. Se conservan como referencia histórica y porque algunos están cubiertos por tests.

## Estado: todos ejecutados

| Script | Versión | Fecha aprox. | Estado |
|---|---|---|---|
| migrar_facturas_a_contratos.py | v2.12.0 | 2026-05-07 | Ejecutado |
| migrar_nombre_canonico.py | v2.13.x | 2026-05-07 | Ejecutado |
| migrar_seleccion_a_meses.py | v2.15.0 | 2026-05-09 | Ejecutado |

## ¿Por qué se conservan?

1. Los tres tienen tests en tests/ que los importan como referencia.
2. Sirven como documentación viva del flujo de migración cuando hubo cambio de schema.
3. Si en el futuro hay que reconstruir un entorno desde cero (e.g., staging nuevo), podrían reutilizarse.

## NO ejecutar sin contexto

Estos scripts NO son idempotentes en todos los casos. Antes de ejecutar cualquiera de ellos:
1. Leer el docstring del script.
2. Verificar el estado actual de la BD.
3. Hacer backup.
