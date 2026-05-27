# Convenciones de Supabase para CHPApp

Esta guía documenta cómo crear tablas nuevas en Supabase de forma coherente con la arquitectura del proyecto.

## Arquitectura de acceso

La aplicación accede a Supabase exclusivamente con la clave `service_role` desde el backend Flask. No hay acceso desde el cliente del navegador a la API REST de Supabase directamente.

Esto implica:

- Todas las tablas tienen RLS habilitado pero sin políticas. El acceso desde `anon` o `authenticated` está bloqueado.
- `service_role` ignora RLS, por lo que todas las operaciones del backend funcionan sin restricciones.
- A partir del 30 de octubre de 2026, las tablas nuevas en `public` requieren GRANT explícito para ser accesibles. Como solo usamos `service_role`, basta con conceder a ese rol.

## Patrón para crear una tabla nueva

Plantilla SQL a ejecutar en el SQL Editor de Supabase:

```sql
-- 1) Crear la tabla
CREATE TABLE IF NOT EXISTS nombre_tabla (
    id BIGSERIAL PRIMARY KEY,
    -- ... columnas ...
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2) Crear índices según necesidad
CREATE INDEX IF NOT EXISTS idx_nombre_tabla_campo ON nombre_tabla(campo);

-- 3) Habilitar RLS (postura segura, aunque service_role lo ignore)
ALTER TABLE nombre_tabla ENABLE ROW LEVEL SECURITY;

-- 4) GRANT explícito a service_role (necesario tras octubre 2026)
GRANT SELECT, INSERT, UPDATE, DELETE ON nombre_tabla TO service_role;
GRANT USAGE, SELECT ON SEQUENCE nombre_tabla_id_seq TO service_role;
```

Notas:

- Si la PK no es un BIGSERIAL (por ejemplo UUID), omitir el GRANT sobre el SEQUENCE.
- No conceder permisos a `anon` o `authenticated` salvo que se vaya a implementar acceso directo desde frontend con RLS policies, lo cual no es el caso de esta app.
- Si en el futuro se cambia de arquitectura para acceder con tokens de usuario en lugar de service_role, este documento debe actualizarse.

## Migraciones existentes

Las tablas creadas antes de octubre 30 de 2026 mantienen sus permisos actuales por defecto. No requieren GRANT retroactivo a menos que Supabase indique lo contrario en comunicaciones futuras.

## Verificación

Para confirmar que una tabla tiene los permisos correctos:

```sql
SELECT grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_name = 'nombre_tabla';
```

Debe aparecer `service_role` con los privilegios SELECT, INSERT, UPDATE, DELETE.
