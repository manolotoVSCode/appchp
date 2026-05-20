# Sistema multi-usuario — CHP App v2.31.0

## Arquitectura

La autenticación usa **Supabase Auth** (email + contraseña). El backend Flask valida credenciales contra Supabase, obtiene el perfil del usuario desde la tabla `user_profiles`, y almacena los datos en la sesión Flask (cookie firmada con SECRET_KEY).

No se usa flask-login. No hay credenciales en variables de entorno. Los usuarios se crean mediante invitación desde la propia app.

## Tabla user_profiles

```sql
CREATE TABLE user_profiles (
  id          UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email       TEXT        NOT NULL,
  rol         TEXT        NOT NULL CHECK (rol IN ('master_admin', 'admin', 'usuario_normal')),
  empresa_id  INTEGER     REFERENCES clientes(id) ON DELETE SET NULL,
  activo      BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Roles y permisos

| Acción | master_admin | admin | usuario_normal |
|--------|:---:|:---:|:---:|
| Ver todos los clientes | ✓ | ✓ | — (solo su empresa) |
| Crear cliente | ✓ | ✓ | — |
| Editar cliente | ✓ | ✓ | — |
| Borrar cliente / contrato / factura | ✓ | ✓ | — |
| Ver dashboards | ✓ | ✓ | ✓ (su empresa) |
| Configuración del sistema | ✓ | ✓ | — |
| Gestión de usuarios (`/admin/usuarios`) | ✓ | — | — |
| Invitar usuarios | ✓ | — | — |
| Borrar usuarios | ✓ (excepto sí mismo) | — | — |

## Configuración inicial en producción

1. Ejecutar migración SQL en Supabase SQL Editor:
   ```
   storage/migrations/202606_multiusuario.sql
   ```

2. Crear el primer usuario `master_admin` en **Supabase Dashboard > Authentication > Users** (botón "Invite user" o "Add user").

3. Insertar fila en `user_profiles`:
   ```sql
   INSERT INTO user_profiles (id, email, rol)
   VALUES ('<uuid-del-usuario>', 'correo@empresa.com', 'master_admin');
   ```

4. El `master_admin` puede iniciar sesión en `/auth/login` e invitar a los demás usuarios desde `/admin/usuarios`.

## Flujos de autenticación

### Login normal
1. GET `/auth/login` — muestra formulario email + contraseña.
2. POST `/auth/login` — llama `supabase.auth.sign_in_with_password`, obtiene perfil de `user_profiles`, almacena en sesión Flask.
3. Redirige a `/clientes`.

### Invitación de nuevo usuario (desde master_admin)
1. Master_admin abre `/admin/usuarios` y hace clic en "Invitar usuario".
2. Introduce email, selecciona rol (admin o usuario_normal) y empresa (si usuario_normal).
3. Backend llama `supabase.auth.admin.invite_user_by_email` + inserta fila en `user_profiles`.
4. Supabase envía email con enlace que contiene `#access_token=...&type=invite`.
5. Usuario hace clic → `/auth/aceptar-invitacion` → JS extrae token del hash → formulario de contraseña.
6. Backend valida token, actualiza contraseña, inicia sesión automáticamente.

### Reset de contraseña
1. GET `/auth/reset-password` → formulario de email.
2. POST → `supabase.auth.reset_password_for_email` → email con enlace `#access_token=...&type=recovery`.
3. Usuario hace clic → `/auth/reset-password/nuevo` → JS extrae token → formulario de nueva contraseña.
4. Backend valida token, actualiza contraseña, redirige al login.

## Archivos clave

- `web/auth.py` — Blueprint `auth_bp` (`/auth/*`), helpers de sesión, flujos de auth.
- `web/auth_permissions.py` — Funciones de control de acceso por rol.
- `web/templates/auth/` — Templates de login, reset password, aceptar invitación.
- `web/templates/admin/usuarios.html` — Gestión de usuarios (tabla + modal de invitación).
- `storage/migrations/202606_multiusuario.sql` — DDL de `user_profiles`.

## Sesión Flask

Claves en `flask.session` para un usuario autenticado:

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `_user_id` | str (UUID) | ID del usuario en auth.users |
| `_user_email` | str | Email del usuario |
| `_user_rol` | str | `master_admin` / `admin` / `usuario_normal` |
| `_empresa_id` | int | None | ID de empresa asignada (solo usuario_normal) |
| `_access_token` | str | JWT de Supabase (para sign_out) |

## Notas de seguridad

- La clave `service_role` de Supabase sigue siendo la única clave usada en el backend (bypasea RLS). Deuda técnica aceptada para fase 1.
- `SECRET_KEY` debe ser aleatoria y persistente en producción.
- Las sesiones son permanentes (30 días) si el usuario marca "Mantener sesión".
- El `usuario_normal` solo puede ver rutas `/clientes/<empresa_id>/...`. Cualquier intento de acceder a otra empresa redirige al listado con mensaje de error.
