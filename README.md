# CHPApp — Análisis Energético

Aplicación web para análisis energético y de cogeneración, con dashboards de contabilidad y proyecciones financieras.

## Stack

- Backend: Flask 3 + Python
- Base de datos: Supabase (PostgreSQL)
- Autenticación: Supabase Auth
- Frontend: HTML + Bootstrap 5 + Chart.js
- Hosting: Render

## Estructura

- `web/` — aplicación Flask, rutas, templates, estáticos.
- `storage/` — capa de acceso a datos (repository pattern).
- `parsers/` — parsers de facturas PDF (CFE, gas, electricidad calificada).
- `calc/` — lógica de cálculo y proyecciones.
- `models/` — clases de dominio.
- `tests/` — suite de tests.
- `scripts/` — scripts de migración (ver scripts/README.md).
- `docs/` — documentación operativa y diseños históricos.

## Arranque local

Requisitos: Python 3.12+, acceso a Supabase del proyecto.

Variables de entorno necesarias:
- `SECRET_KEY` — clave para firmar cookies de sesión. Generar con `python -c "import secrets; print(secrets.token_hex(32))"`.
- `SUPABASE_URL` — URL del proyecto Supabase.
- `SUPABASE_KEY` — service_role key.

```bash
pip install -r requirements.txt
gunicorn web.app:create_app\(\)
```

## Documentación

- `CHANGELOG.md` — historial de versiones.
- `CLAUDE.md` — guía para asistentes y colaboradores.
