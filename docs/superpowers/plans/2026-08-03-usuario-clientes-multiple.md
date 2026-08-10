# Asignación múltiple de clientes a usuario_normal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un `usuario_normal` tenga acceso a múltiples clientes (N:N), con sidebar dinámico y panel de asignación en `/admin/usuarios/<id>/editar`.

**Architecture:** Nueva tabla `usuario_clientes` como relación N:N. La sesión Flask almacena `_clientes_ids` (list[int]). `empresa_id` en `user_profiles` se conserva como fallback legacy para usuarios con un solo cliente. Las funciones de permisos se actualizan para leer de `clientes_ids` primero.

**Tech Stack:** Python 3.11, Flask 3.x, supabase-py, Jinja2, Bootstrap 5.3.

## Global Constraints

- Acceso a BD exclusivamente vía supabase-py. Prohibido psycopg2 o SQL directo.
- Todos los campos numéricos en Supabase son TEXT; convertir a Decimal o int al leer.
- Tests de repositorio usan `unittest.mock.patch` sobre `storage.repository._supabase`.
- Tests de Flask inyectan sesión vía `client.session_transaction()`. Nunca llamar a Supabase en tests web.
- No modificar acceso de `admin` ni `master_admin`.
- `empresa_id` en `user_profiles` NO se elimina — es fallback para compatibilidad.
- La cookie `last_cliente_id` sigue operando para admin/master_admin sin cambios.
- `usuario_normal` sigue sin acceso a ficha del cliente, borrado, creación ni gestión de usuarios.
- Responder en español en mensajes flash. Commits en inglés.

---

## Mapa de archivos

**Crear:**
- `storage/migrations/202606_usuario_clientes.sql`
- `tests/test_usuario_clientes.py`

**Modificar:**
- `storage/repository.py` — añadir 3 funciones al final
- `web/auth_permissions.py` — modificar `usuario_puede_ver_empresa` y `filtrar_empresas_para_usuario`
- `web/auth.py` — modificar `set_user_session()` y `get_current_user()`; actualizar redirect en `login()`
- `web/app.py` — actualizar `_require_login`, `_inject_globals` context_processor, y `admin_usuarios_editar`
- `web/templates/clientes/_base.html` — sección sidebar usuario_normal
- `web/templates/admin/editar_usuario.html` — reemplazar select empresa por checkboxes multi-cliente

---

## Task 1: SQL migration

**Files:**
- Create: `storage/migrations/202606_usuario_clientes.sql`

**Interfaces:**
- Produce: tabla `usuario_clientes` con PK (user_id, cliente_id), dos índices.

- [ ] **Step 1: Escribir el archivo SQL**

```sql
-- storage/migrations/202606_usuario_clientes.sql
-- Tabla de relación N:N usuario ↔ cliente
CREATE TABLE IF NOT EXISTS usuario_clientes (
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, cliente_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_clientes_user
    ON usuario_clientes (user_id);

CREATE INDEX IF NOT EXISTS idx_usuario_clientes_cliente
    ON usuario_clientes (cliente_id);

-- empresa_id en user_profiles pasa a ser legacy.
-- No se borra para mantener compatibilidad con usuarios existentes.
-- La nueva lógica lee de usuario_clientes primero; empresa_id es fallback.
```

- [ ] **Step 2: Commit**

```bash
git add storage/migrations/202606_usuario_clientes.sql
git commit -m "feat(db): add usuario_clientes N:N table"
```

---

## Task 2: Repository — tres funciones nuevas

**Files:**
- Modify: `storage/repository.py` (añadir al final del archivo)
- Test: `tests/test_usuario_clientes.py`

**Interfaces:**
- Consumes: `_supabase` singleton (ya existe en `storage/repository.py`)
- Produces:
  - `get_clientes_de_usuario(user_id: str) -> list[dict]`
  - `set_clientes_de_usuario(user_id: str, cliente_ids: list[int]) -> None`
  - `get_usuarios_de_cliente(cliente_id: int) -> list[dict]`

- [ ] **Step 1: Escribir tests en `tests/test_usuario_clientes.py`**

```python
# tests/test_usuario_clientes.py
"""Tests para funciones N:N usuario_clientes en repository."""
from __future__ import annotations
from unittest.mock import MagicMock, patch, call
import pytest


def _mock_supabase():
    return MagicMock()


# ── get_clientes_de_usuario ────────────────────────────────────────────────────

def test_get_clientes_de_usuario_retorna_lista_de_usuario_clientes():
    """Cuando hay filas en usuario_clientes, retorna clientes ordenados."""
    mock_sb = _mock_supabase()
    # usuario_clientes devuelve dos cliente_ids
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"cliente_id": 2},
        {"cliente_id": 5},
    ]
    # clientes devuelve los clientes correspondientes
    mock_sb.table.return_value.select.return_value.in_.return_value.order.return_value.execute.return_value.data = [
        {"id": 2, "nombre": "Alfa"},
        {"id": 5, "nombre": "Beta"},
    ]
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-1")
    assert len(result) == 2
    assert result[0]["id"] == 2
    assert result[1]["id"] == 5


def test_get_clientes_de_usuario_fallback_empresa_id():
    """Sin filas en usuario_clientes, hace fallback a empresa_id de user_profiles."""
    mock_sb = _mock_supabase()

    # Dos llamadas a table():
    # 1a: usuario_clientes → vacío
    # 2a: user_profiles → empresa_id=7
    # 3a: clientes por id 7
    call_count = {"n": 0}
    results = [
        # usuario_clientes
        MagicMock(**{"select.return_value.eq.return_value.execute.return_value.data": []}),
        # user_profiles
        MagicMock(**{"select.return_value.eq.return_value.limit.return_value.execute.return_value.data": [{"empresa_id": 7}]}),
        # clientes
        MagicMock(**{"select.return_value.eq.return_value.execute.return_value.data": [{"id": 7, "nombre": "Gamma"}]}),
    ]

    def table_side_effect(name):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(results):
            return results[idx]
        return MagicMock()

    mock_sb.table.side_effect = table_side_effect
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-2")
    assert len(result) == 1
    assert result[0]["id"] == 7


def test_get_clientes_de_usuario_retorna_lista_vacia_sin_asignaciones():
    """Sin filas en usuario_clientes y sin empresa_id, retorna lista vacía."""
    mock_sb = _mock_supabase()
    call_count = {"n": 0}
    results = [
        MagicMock(**{"select.return_value.eq.return_value.execute.return_value.data": []}),
        MagicMock(**{"select.return_value.eq.return_value.limit.return_value.execute.return_value.data": [{"empresa_id": None}]}),
    ]

    def table_side_effect(name):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(results):
            return results[idx]
        return MagicMock()

    mock_sb.table.side_effect = table_side_effect
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_clientes_de_usuario
        result = get_clientes_de_usuario("user-uuid-3")
    assert result == []


# ── set_clientes_de_usuario ────────────────────────────────────────────────────

def test_set_clientes_de_usuario_borra_e_inserta():
    """Debe borrar filas previas e insertar las nuevas."""
    mock_sb = _mock_supabase()
    delete_mock = MagicMock()
    insert_mock = MagicMock()
    mock_sb.table.return_value.delete.return_value.eq.return_value.execute = delete_mock
    mock_sb.table.return_value.insert.return_value.execute = insert_mock

    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import set_clientes_de_usuario
        set_clientes_de_usuario("user-uuid-1", [3, 7, 12])

    delete_mock.assert_called_once()
    insert_mock.assert_called_once()


def test_set_clientes_de_usuario_lista_vacia_solo_borra():
    """Con lista vacía: borra pero no inserta."""
    mock_sb = _mock_supabase()
    delete_mock = MagicMock()
    insert_mock = MagicMock()
    mock_sb.table.return_value.delete.return_value.eq.return_value.execute = delete_mock
    mock_sb.table.return_value.insert.return_value.execute = insert_mock

    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import set_clientes_de_usuario
        set_clientes_de_usuario("user-uuid-1", [])

    delete_mock.assert_called_once()
    insert_mock.assert_not_called()


# ── get_usuarios_de_cliente ────────────────────────────────────────────────────

def test_get_usuarios_de_cliente_retorna_lista():
    """Retorna lista de usuarios asignados al cliente."""
    mock_sb = _mock_supabase()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": "uuid-a", "user_profiles": {"email": "a@b.com", "nombre": "Ana", "apellido": "L"}},
        {"user_id": "uuid-b", "user_profiles": {"email": "x@y.com", "nombre": None, "apellido": None}},
    ]
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_usuarios_de_cliente
        result = get_usuarios_de_cliente(42)
    assert len(result) == 2
    assert result[0]["user_id"] == "uuid-a"
    assert result[0]["email"] == "a@b.com"


def test_get_usuarios_de_cliente_retorna_lista_vacia():
    """Sin asignaciones retorna lista vacía."""
    mock_sb = _mock_supabase()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    with patch("storage.repository._supabase", mock_sb):
        from storage.repository import get_usuarios_de_cliente
        result = get_usuarios_de_cliente(99)
    assert result == []
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_usuario_clientes.py -x -q 2>&1 | head -30
```

Esperado: ImportError o AttributeError (funciones no existen).

- [ ] **Step 3: Implementar las funciones al final de `storage/repository.py`**

Añadir justo antes del último `\n` del archivo:

```python
# ── Usuario ↔ Cliente (N:N) ───────────────────────────────────────────────────

def get_clientes_de_usuario(user_id: str) -> list[dict]:
    """
    Retorna lista de clientes asignados a un usuario_normal vía usuario_clientes.
    Ordena por nombre ASC. Si no hay filas en usuario_clientes, hace fallback a
    empresa_id de user_profiles (compatibilidad legacy).
    Cada dict tiene al menos {id, nombre, ...campos básicos de clientes}.
    """
    try:
        res = _supabase.table("usuario_clientes").select("cliente_id").eq("user_id", user_id).execute()
        rows = res.data or []
        if rows:
            ids = [r["cliente_id"] for r in rows]
            clientes_res = (
                _supabase.table("clientes")
                .select("id, nombre, rfc, sector_industrial, tarifa_cfe")
                .in_("id", ids)
                .order("nombre", desc=False)
                .execute()
            )
            return clientes_res.data or []
        # Fallback legacy: leer empresa_id de user_profiles
        profile_res = (
            _supabase.table("user_profiles")
            .select("empresa_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        profile_rows = profile_res.data or []
        empresa_id = profile_rows[0].get("empresa_id") if profile_rows else None
        if not empresa_id:
            return []
        cli_res = (
            _supabase.table("clientes")
            .select("id, nombre, rfc, sector_industrial, tarifa_cfe")
            .eq("id", empresa_id)
            .execute()
        )
        return cli_res.data or []
    except Exception as exc:
        logger.error("Error en get_clientes_de_usuario user_id=%s: %s", user_id, exc)
        return []


def set_clientes_de_usuario(user_id: str, cliente_ids: list[int]) -> None:
    """
    Reemplaza la asignación completa de clientes para un usuario.
    Borra todas las filas existentes en usuario_clientes para ese user_id
    e inserta las nuevas. Si cliente_ids está vacío, solo borra.
    """
    _supabase.table("usuario_clientes").delete().eq("user_id", user_id).execute()
    if not cliente_ids:
        return
    rows = [{"user_id": user_id, "cliente_id": cid} for cid in cliente_ids]
    _supabase.table("usuario_clientes").insert(rows).execute()


def get_usuarios_de_cliente(cliente_id: int) -> list[dict]:
    """
    Retorna lista de usuario_normal asignados a un cliente.
    Cada dict: {user_id, email, nombre, apellido}.
    """
    try:
        res = (
            _supabase.table("usuario_clientes")
            .select("user_id, user_profiles(email, nombre, apellido)")
            .eq("cliente_id", cliente_id)
            .execute()
        )
        rows = res.data or []
        result = []
        for r in rows:
            profile = r.get("user_profiles") or {}
            result.append({
                "user_id": r["user_id"],
                "email": profile.get("email", ""),
                "nombre": profile.get("nombre"),
                "apellido": profile.get("apellido"),
            })
        return result
    except Exception as exc:
        logger.error("Error en get_usuarios_de_cliente cliente_id=%s: %s", cliente_id, exc)
        return []
```

- [ ] **Step 4: Ejecutar tests — deben pasar**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_usuario_clientes.py -x -q
```

Esperado: 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add storage/repository.py tests/test_usuario_clientes.py
git commit -m "feat(repository): add get/set_clientes_de_usuario and get_usuarios_de_cliente"
```

---

## Task 3: auth_permissions.py — soporte multi-cliente

**Files:**
- Modify: `web/auth_permissions.py` (funciones `usuario_puede_ver_empresa` y `filtrar_empresas_para_usuario`)
- Test: `tests/test_usuario_clientes.py` (añadir sección)

**Interfaces:**
- Consumes: `user` dict con clave `clientes_ids: list[int]` (añadida en Task 4) y fallback `empresa_id: int | None`
- Produces: mismas firmas, lógica actualizada

- [ ] **Step 1: Añadir tests de permisos al archivo existente `tests/test_usuario_clientes.py`**

Añadir al final:

```python
# ── Permisos multi-cliente ─────────────────────────────────────────────────────

from web.auth_permissions import usuario_puede_ver_empresa, filtrar_empresas_para_usuario


def test_usuario_puede_ver_empresa_admin_ve_todo():
    user = {"rol": "admin", "clientes_ids": [], "empresa_id": None}
    assert usuario_puede_ver_empresa(99, user) is True


def test_usuario_puede_ver_empresa_master_admin_ve_todo():
    user = {"rol": "master_admin", "clientes_ids": [], "empresa_id": None}
    assert usuario_puede_ver_empresa(5, user) is True


def test_usuario_puede_ver_empresa_normal_con_lista():
    user = {"rol": "usuario_normal", "clientes_ids": [3, 7], "empresa_id": None}
    assert usuario_puede_ver_empresa(7, user) is True
    assert usuario_puede_ver_empresa(99, user) is False


def test_usuario_puede_ver_empresa_normal_fallback_empresa_id():
    """Sin clientes_ids, usa empresa_id legado."""
    user = {"rol": "usuario_normal", "clientes_ids": [], "empresa_id": 4}
    assert usuario_puede_ver_empresa(4, user) is True
    assert usuario_puede_ver_empresa(5, user) is False


def test_filtrar_empresas_admin_sin_filtro():
    clientes = [{"id": 1}, {"id": 2}, {"id": 3}]
    user = {"rol": "admin", "clientes_ids": [], "empresa_id": None}
    assert filtrar_empresas_para_usuario(clientes, user) == clientes


def test_filtrar_empresas_normal_multi():
    clientes = [{"id": 1}, {"id": 2}, {"id": 3}]
    user = {"rol": "usuario_normal", "clientes_ids": [1, 3], "empresa_id": None}
    result = filtrar_empresas_para_usuario(clientes, user)
    assert [c["id"] for c in result] == [1, 3]


def test_filtrar_empresas_normal_fallback():
    clientes = [{"id": 1}, {"id": 2}, {"id": 3}]
    user = {"rol": "usuario_normal", "clientes_ids": [], "empresa_id": 2}
    result = filtrar_empresas_para_usuario(clientes, user)
    assert [c["id"] for c in result] == [2]


def test_filtrar_empresas_normal_sin_asignacion():
    clientes = [{"id": 1}, {"id": 2}]
    user = {"rol": "usuario_normal", "clientes_ids": [], "empresa_id": None}
    assert filtrar_empresas_para_usuario(clientes, user) == []
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_usuario_clientes.py -k "filtrar or puede_ver" -x -q
```

Esperado: fallo porque las funciones actuales no conocen `clientes_ids`.

- [ ] **Step 3: Modificar `web/auth_permissions.py`**

Reemplazar `usuario_puede_ver_empresa` (líneas 76–83):

```python
def usuario_puede_ver_empresa(empresa_id: int, user: dict) -> bool:
    """
    master_admin y admin ven todas las empresas.
    usuario_normal: verifica en clientes_ids (multi) o empresa_id (fallback legacy).
    """
    if user.get("rol") in (ROL_MASTER_ADMIN, ROL_ADMIN):
        return True
    clientes_ids = user.get("clientes_ids", [])
    if clientes_ids:
        return empresa_id in clientes_ids
    return user.get("empresa_id") == empresa_id
```

Reemplazar `filtrar_empresas_para_usuario` (líneas 86–97):

```python
def filtrar_empresas_para_usuario(clientes: list[dict], user: dict) -> list[dict]:
    """
    Filtra la lista de clientes según el rol del usuario.
    master_admin/admin: sin filtro.
    usuario_normal: filtra por clientes_ids (multi) o empresa_id (fallback legacy).
    """
    if user.get("rol") in (ROL_MASTER_ADMIN, ROL_ADMIN):
        return clientes
    clientes_ids = user.get("clientes_ids", [])
    if clientes_ids:
        return [c for c in clientes if c.get("id") in clientes_ids]
    empresa_id = user.get("empresa_id")
    if empresa_id is None:
        return []
    return [c for c in clientes if c.get("id") == empresa_id]
```

- [ ] **Step 4: Ejecutar tests**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_usuario_clientes.py -x -q
```

Esperado: todos los tests de permisos PASS.

- [ ] **Step 5: Commit**

```bash
git add web/auth_permissions.py tests/test_usuario_clientes.py
git commit -m "feat(permissions): support multi-client list in usuario_normal checks"
```

---

## Task 4: auth.py — sesión con clientes_ids

**Files:**
- Modify: `web/auth.py`
  - `set_user_session()`: añadir parámetro y guardar `_clientes_ids`
  - `get_current_user()`: incluir `clientes_ids` en el dict retornado
  - `login()` y `_handle_login()`: ajustar redirect y carga de empresa_nombre

**Interfaces:**
- Consumes: `get_clientes_de_usuario(user_id: str) -> list[dict]` (Task 2)
- Produces: sesión Flask con clave `_clientes_ids: list[int]`; `get_current_user()` retorna dict con `clientes_ids: list[int]`

**Nota importante sobre `_handle_login`:** actualmente carga `empresa_nombre` solo si `profile["rol"] == ROL_USUARIO_NORMAL and profile.get("empresa_id")`. Con multi-cliente, cuando hay varios, `empresa_id` puede ser NULL. La lógica de `empresa_nombre` en sesión pasa a ser secundaria (el sidebar ya usa `clientes_usuario` del context_processor). Mantener el comportamiento legacy para 1 cliente.

- [ ] **Step 1: Modificar `set_user_session()` en `web/auth.py`**

Reemplazar la función completa (líneas 37–52):

```python
def set_user_session(user_id: str, email: str, rol: str, empresa_id: int | None,
                     access_token: str, remember: bool = False,
                     empresa_nombre: str | None = None,
                     nombre: str | None = None,
                     apellido: str | None = None,
                     clientes_ids: list[int] | None = None) -> None:
    from storage.repository import get_session_version
    session.permanent = remember
    session["_user_id"] = user_id
    session["_user_email"] = email
    session["_user_rol"] = rol
    session["_empresa_id"] = empresa_id
    session["_empresa_nombre"] = empresa_nombre
    session["_nombre"] = nombre
    session["_apellido"] = apellido
    session["_access_token"] = access_token
    session["_session_version"] = get_session_version(user_id) or 1

    if clientes_ids is not None:
        session["_clientes_ids"] = clientes_ids
    elif rol == ROL_USUARIO_NORMAL:
        # Carga bajo demanda si no se pasó explícitamente
        from storage.repository import get_clientes_de_usuario
        ids = [c["id"] for c in get_clientes_de_usuario(user_id)]
        session["_clientes_ids"] = ids
        # Mantener _empresa_id apuntando al único cliente si hay exactamente uno
        if len(ids) == 1:
            session["_empresa_id"] = ids[0]
        elif len(ids) != 1:
            session["_empresa_id"] = empresa_id  # puede quedar NULL
    else:
        session["_clientes_ids"] = []
```

- [ ] **Step 2: Modificar `get_current_user()` en `web/auth.py`**

Reemplazar la función (líneas 63–76):

```python
def get_current_user() -> dict | None:
    """Retorna dict con datos de sesión o None si no autenticado."""
    user_id = session.get("_user_id")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "email": session.get("_user_email", ""),
        "rol": session.get("_user_rol", ""),
        "empresa_id": session.get("_empresa_id"),
        "empresa_nombre": session.get("_empresa_nombre"),
        "nombre": session.get("_nombre"),
        "apellido": session.get("_apellido"),
        "clientes_ids": session.get("_clientes_ids", []),
    }
```

- [ ] **Step 3: Actualizar redirect post-login en `login()` (web/auth.py, líneas ~176–183)**

Reemplazar el bloque `if user and user["rol"] == ROL_USUARIO_NORMAL:`:

```python
if error is None:
    user = get_current_user()
    if user and user["rol"] == ROL_USUARIO_NORMAL:
        clientes_ids = user.get("clientes_ids", [])
        if clientes_ids:
            return redirect(url_for(
                "cliente_dashboard_contabilidad",
                cliente_id=clientes_ids[0]
            ))
        return render_template(
            "auth/login.html",
            error="Sin clientes asignados. Contacta al administrador.",
        )
    raw_next = request.args.get("next", "")
    if _es_url_segura(raw_next):
        return redirect(raw_next)
    last_id = request.cookies.get("last_cliente_id", "").strip()
    if last_id and last_id.isdigit():
        fallback = url_for("clientes.ficha", cliente_id=int(last_id))
    else:
        fallback = url_for("clientes.listado")
    return redirect(fallback)
```

- [ ] **Step 4: Verificar que los tests existentes de auth siguen pasando**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_auth.py -x -q
```

Los tests inyectan sesión directamente via `session_transaction()`, por lo que no llaman a `set_user_session`. Si algún test falla porque `_clientes_ids` no está en sesión inyectada, añadir la clave donde corresponda en el helper `_inject_session` del test.

**Si hay failures:** en `tests/test_auth.py`, actualizar el helper `_inject_session`:

```python
def _inject_session(client, rol="admin", empresa_id=None, empresa_nombre=None,
                    clientes_ids=None):
    with client.session_transaction() as sess:
        sess["_user_id"] = "test-user-uuid"
        sess["_user_email"] = "operador@test.com"
        sess["_user_rol"] = rol
        sess["_empresa_id"] = empresa_id
        sess["_empresa_nombre"] = empresa_nombre
        sess["_clientes_ids"] = clientes_ids or ([] if rol != "usuario_normal" else (
            [empresa_id] if empresa_id else []
        ))
```

- [ ] **Step 5: Commit**

```bash
git add web/auth.py tests/test_auth.py
git commit -m "feat(auth): store clientes_ids in session for usuario_normal"
```

---

## Task 5: app.py — before_request, context_processor, editar_usuario

**Files:**
- Modify: `web/app.py`
  - `_require_login` (before_request): usar `usuario_puede_ver_empresa` que ya lee `clientes_ids`
  - `_inject_globals` (context_processor): inyectar `clientes_usuario` para usuario_normal
  - `admin_usuarios_editar`: cargar/guardar multi-cliente, eliminar validación de empresa_id obligatoria

**Interfaces:**
- Consumes: `get_clientes_de_usuario`, `set_clientes_de_usuario`, `get_all_clientes_con_conteos` (ya existen)
- Consumes: `get_current_user()` con `clientes_ids` (Task 4)

- [ ] **Step 1: Actualizar `_require_login` para leer `clientes_ids` de sesión**

La función actual en líneas ~494–504 ya llama a `usuario_puede_ver_empresa(cid, user)`. Dado que `get_current_user()` ahora incluye `clientes_ids` en el dict, **no hay cambio de código necesario aquí** — la función de permisos ya recibe el user completo.

Verificar que funciona con un test de acceso denegado (añadir a `tests/test_usuario_clientes.py`):

```python
# ── Tests de acceso web ────────────────────────────────────────────────────────

import pytest

@pytest.fixture()
def app_fixture(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app

@pytest.fixture()
def web_client(app_fixture):
    return app_fixture.test_client()


def _inject_usuario_normal(client, clientes_ids, empresa_id=None):
    with client.session_transaction() as sess:
        sess["_user_id"] = "test-user-uuid"
        sess["_user_email"] = "cliente@test.com"
        sess["_user_rol"] = "usuario_normal"
        sess["_empresa_id"] = empresa_id or (clientes_ids[0] if clientes_ids else None)
        sess["_empresa_nombre"] = "Test Empresa"
        sess["_clientes_ids"] = clientes_ids
        sess["_session_version"] = 1


def test_usuario_normal_puede_acceder_a_cliente_asignado(web_client):
    """usuario_normal con clientes_ids=[3] puede GET /clientes/3/..."""
    from unittest.mock import patch, MagicMock
    _inject_usuario_normal(web_client, clientes_ids=[3], empresa_id=3)
    with patch("web.app._verificar_activo_con_cache", return_value=True), \
         patch("web.app._verificar_session_version_con_cache", return_value=True):
        resp = web_client.get("/clientes/3/dashboard/contabilidad", follow_redirects=False)
    # Puede ser 200 o redirect interno, pero NO 302 a listado
    assert resp.status_code != 302 or "/clientes/" not in (resp.headers.get("Location", ""))


def test_usuario_normal_bloqueado_en_cliente_no_asignado(web_client):
    """usuario_normal con clientes_ids=[3] recibe redirect al intentar /clientes/99/..."""
    from unittest.mock import patch
    _inject_usuario_normal(web_client, clientes_ids=[3], empresa_id=3)
    with patch("web.app._verificar_activo_con_cache", return_value=True), \
         patch("web.app._verificar_session_version_con_cache", return_value=True):
        resp = web_client.get("/clientes/99/dashboard/contabilidad", follow_redirects=False)
    assert resp.status_code == 302
```

- [ ] **Step 2: Actualizar `_inject_globals` context_processor para inyectar `clientes_usuario`**

En `web/app.py`, dentro de `_inject_globals()`, localizar el bloque que construye `base` (líneas ~506–545) y añadir al dict `base` antes del return:

```python
# Inyectar lista de clientes para usuario_normal (sidebar dinámico)
if current_user_data and current_user_data.get("rol") == "usuario_normal":
    from storage.repository import get_clientes_de_usuario as _gcdu
    uid = current_user_data.get("user_id")
    try:
        base["clientes_usuario"] = _gcdu(uid) if uid else []
    except Exception:
        base["clientes_usuario"] = []
else:
    base["clientes_usuario"] = []
```

Añadir también `clientes_usuario` en el return temprano (línea ~521 `return {**base, "cliente_activo": None}`): ya estará en `base`, así que no hay cambio adicional.

- [ ] **Step 3: Actualizar `admin_usuarios_editar` en `web/app.py`**

**En el bloque GET** (líneas ~2278–2285), añadir después de `clientes_list = get_all_clientes_con_conteos()`:

```python
from storage.repository import get_clientes_de_usuario as _gcdu
clientes_asignados = _gcdu(user_id)
clientes_asignados_ids = [c["id"] for c in clientes_asignados]
```

Y pasar al template:
```python
return render_template("admin/editar_usuario.html",
                       target=target, clientes=clientes_list,
                       clientes_asignados_ids=clientes_asignados_ids,
                       form_rol=target["rol"],
                       form_empresa_id=target.get("empresa_id"),
                       form_nombre=target.get("nombre"),
                       form_apellido=target.get("apellido"),
                       actor_puede_cambiar_rol=actor_puede_cambiar_rol)
```

**En el bloque POST** (líneas ~2243–2276):

1. Eliminar la validación `if rol == "usuario_normal" and not empresa_id:` (ya no aplica — un usuario puede tener 0, 1 o N clientes).

2. Calcular `empresa_id` desde los clientes seleccionados en lugar del select simple. Reemplazar el bloque de lectura de `empresa_id` y el update:

```python
if request.method == "POST":
    if actor_puede_cambiar_rol:
        rol = request.form.get("rol", "").strip()
        if rol not in ("admin", "usuario_normal"):
            flash("Rol no válido.", "danger")
            return redirect(url_for("admin_usuarios_editar", user_id=user_id))
    else:
        rol = target["rol"]

    nombre_ed = request.form.get("nombre", "").strip() or None
    apellido_ed = request.form.get("apellido", "").strip() or None

    if rol == "usuario_normal":
        cliente_ids_raw = request.form.getlist("cliente_ids")
        cliente_ids = [int(x) for x in cliente_ids_raw if x.isdigit()]
        # empresa_id legacy: apuntar al único si hay exactamente uno
        empresa_id_legacy = cliente_ids[0] if len(cliente_ids) == 1 else None
    else:
        cliente_ids = []
        empresa_id_legacy = None

    try:
        _supabase.postgrest.auth(os.environ["SUPABASE_KEY"])
        _supabase.table("user_profiles").update({
            "rol": rol,
            "empresa_id": empresa_id_legacy,
            "nombre": nombre_ed,
            "apellido": apellido_ed,
        }).eq("id", user_id).execute()

        if rol == "usuario_normal":
            from storage.repository import set_clientes_de_usuario as _scdu
            _scdu(user_id, cliente_ids)

        flash(f"Usuario {target['email']} actualizado correctamente.", "success")
    except Exception as exc:
        logger.error("Error actualizando usuario %s: %s", user_id, exc)
        flash(f"Error actualizando usuario: {exc}", "danger")
    return redirect(url_for("admin_usuarios"))
```

También actualizar el render del error de validación de rol (si toca mostrarlo):
```python
# En la ruta de error de rol inválido, pasar también clientes_asignados_ids
from storage.repository import get_clientes_de_usuario as _gcdu
clientes_asignados = _gcdu(user_id)
clientes_asignados_ids = [c["id"] for c in clientes_asignados]
clientes_list = get_all_clientes_con_conteos()
return render_template("admin/editar_usuario.html",
                       target=target, clientes=clientes_list,
                       clientes_asignados_ids=clientes_asignados_ids,
                       form_rol=rol, form_empresa_id=None,
                       form_nombre=nombre_ed, form_apellido=apellido_ed,
                       actor_puede_cambiar_rol=actor_puede_cambiar_rol)
```

- [ ] **Step 4: Ejecutar suite de tests**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_usuario_clientes.py tests/test_auth.py -x -q
```

Esperado: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app.py
git commit -m "feat(app): inject clientes_usuario in context_processor; update editar_usuario route for multi-client"
```

---

## Task 6: Template editar_usuario.html — checkboxes multi-cliente

**Files:**
- Modify: `web/templates/admin/editar_usuario.html`

**Interfaces:**
- Consumes: variable `clientes_asignados_ids: list[int]` inyectada desde la ruta (Task 5)
- Consumes: variable `clientes: list[dict]` (ya existente — lista completa de clientes)

- [ ] **Step 1: Reemplazar el bloque `#empresa-field` por checkboxes multi-cliente**

Localizar y reemplazar desde `<div class="mb-3" id="empresa-field"...>` hasta `</div>` (líneas 42–50 del template):

```html
<div class="mb-3" id="empresa-field" style="{{ '' if form_rol == 'usuario_normal' else 'display:none' }}">
  <label class="form-label fw-semibold">Clientes asignados</label>
  <div class="border rounded p-3" style="max-height:300px;overflow-y:auto">
    {% for c in clientes %}
    <div class="form-check">
      <input class="form-check-input" type="checkbox"
             name="cliente_ids" value="{{ c.id }}"
             id="cli-{{ c.id }}"
             {% if c.id in (clientes_asignados_ids or []) %}checked{% endif %}>
      <label class="form-check-label small" for="cli-{{ c.id }}">
        {{ c.nombre }}
      </label>
    </div>
    {% endfor %}
    {% if not clientes %}
    <p class="text-muted small mb-0">No hay clientes registrados.</p>
    {% endif %}
  </div>
  <div class="form-text text-muted">
    El usuario verá estos clientes en su sidebar y podrá acceder a sus dashboards en modo solo lectura.
  </div>
</div>
```

- [ ] **Step 2: Actualizar el JS para que `toggleEmpresaField` use el id correcto**

El JS actual referencia `empresa-field`. El nuevo div mantiene el mismo id, por lo que el JS existente funciona sin cambios. Verificar que la función `toggleEmpresaField` está correctamente llamada por `onchange` del select de rol.

La función existente (líneas 73–77) ya usa `document.getElementById('empresa-field')`, que coincide con el nuevo div. **No hay cambio necesario en JS.**

- [ ] **Step 3: Verificar que el template renderiza sin error**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_auth.py -x -q -k "editar"
```

Si no hay test específico para editar_usuario, añadir uno mínimo en `tests/test_usuario_clientes.py`:

```python
def test_editar_usuario_carga_correctamente(web_client):
    """GET /admin/usuarios/<id>/editar retorna 200 para master_admin."""
    from unittest.mock import patch, MagicMock
    with web_client.session_transaction() as sess:
        sess["_user_id"] = "master-uuid"
        sess["_user_email"] = "master@test.com"
        sess["_user_rol"] = "master_admin"
        sess["_empresa_id"] = None
        sess["_clientes_ids"] = []
        sess["_session_version"] = 1

    target_data = {
        "id": "target-uuid", "email": "cli@test.com",
        "rol": "usuario_normal", "empresa_id": 5,
        "nombre": "Test", "apellido": "User", "activo": True,
    }
    with patch("web.app._verificar_activo_con_cache", return_value=True), \
         patch("web.app._verificar_session_version_con_cache", return_value=True), \
         patch("storage.repository._supabase") as mock_sb, \
         patch("storage.repository.get_all_clientes_con_conteos", return_value=[{"id": 5, "nombre": "Empresa A"}]), \
         patch("storage.repository.get_clientes_de_usuario", return_value=[{"id": 5, "nombre": "Empresa A"}]):
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [target_data]
        mock_sb.postgrest.auth.return_value = None
        resp = web_client.get("/admin/usuarios/target-uuid/editar", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Clientes asignados" in resp.data
```

- [ ] **Step 4: Ejecutar tests**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/test_usuario_clientes.py -x -q
```

Esperado: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add web/templates/admin/editar_usuario.html tests/test_usuario_clientes.py
git commit -m "feat(ui): replace single empresa dropdown with multi-client checkboxes in editar_usuario"
```

---

## Task 7: Sidebar dinámico para usuario_normal

**Files:**
- Modify: `web/templates/clientes/_base.html` (sección sidebar usuario_normal, líneas 57–68)

**Interfaces:**
- Consumes: variable `clientes_usuario: list[dict]` inyectada por `_inject_globals` (Task 5)
- Consumes: variable `cliente_activo` (ya existe en context_processor)

- [ ] **Step 1: Reemplazar el bloque sidebar de usuario_normal**

Localizar el bloque (líneas 57–68):

```html
{% if current_user_data and current_user_data.rol == 'usuario_normal' %}
  <div class="sidebar-section">Mi empresa</div>
  {% if current_user_data.empresa_id %}
  <a href="{{ url_for('clientes.ficha', cliente_id=current_user_data.empresa_id) }}"
     class="sidebar-link{% if nav_active == 'clientes' %} active{% endif %}">
    <i class="bi bi-building"></i>{{ current_user_data.empresa_nombre or 'Mi empresa' }}
  </a>
  {% else %}
  <span class="sidebar-link" style="color:#8A9BB0;cursor:default">
    <i class="bi bi-building"></i>Sin empresa asignada
  </span>
  {% endif %}
```

Reemplazar por:

```html
{% if current_user_data and current_user_data.rol == 'usuario_normal' %}
  <div class="sidebar-section">Clientes</div>
  {% if clientes_usuario %}
    {% for c in clientes_usuario %}
    <a href="{{ url_for('cliente_dashboard_contabilidad', cliente_id=c.id) }}"
       class="sidebar-link{% if cliente_activo and cliente_activo.id == c.id %} active{% endif %}">
      <i class="bi bi-building"></i>{{ c.nombre }}
    </a>
    {% endfor %}
  {% else %}
  <span class="sidebar-link" style="color:#8A9BB0;cursor:default">
    <i class="bi bi-building"></i>Sin clientes asignados
  </span>
  {% endif %}
```

- [ ] **Step 2: Ejecutar tests completos**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/ -x -q
```

Esperado: todos PASS. Si falla algún test de template por `clientes_usuario` no definido en otros fixtures, añadir `clientes_usuario=[]` en los mocks correspondientes.

- [ ] **Step 3: Commit**

```bash
git add web/templates/clientes/_base.html
git commit -m "feat(sidebar): dynamic multi-client list for usuario_normal"
```

---

## Task 8: CHANGELOG, CLAUDE.md y push final

**Files:**
- Modify: `CHANGELOG.md` (entrada nueva al inicio)
- Modify: `CLAUDE.md` (sección "Estado de chats activos")

- [ ] **Step 1: Añadir entrada al inicio de CHANGELOG.md**

```markdown
## [2.69.0] — 2026-08-03

### Añadido — Asignación múltiple de clientes a usuario_normal

- `storage/migrations/202606_usuario_clientes.sql`: tabla `usuario_clientes` (PK user_id + cliente_id, FK a auth.users y clientes, dos índices).
- `storage/repository.py`:
  - `get_clientes_de_usuario(user_id)`: retorna clientes desde `usuario_clientes`; fallback a `empresa_id` de `user_profiles` para compatibilidad legacy.
  - `set_clientes_de_usuario(user_id, cliente_ids)`: reemplaza asignación completa (delete + insert).
  - `get_usuarios_de_cliente(cliente_id)`: lista de usuarios asignados a un cliente.
- `web/auth_permissions.py`: `usuario_puede_ver_empresa` y `filtrar_empresas_para_usuario` leen `clientes_ids` del dict de usuario; fallback a `empresa_id` si la lista está vacía.
- `web/auth.py`: `set_user_session()` carga y almacena `_clientes_ids` en sesión Flask para `usuario_normal`; `get_current_user()` incluye `clientes_ids` en el dict retornado; redirect post-login usa `clientes_ids[0]`.
- `web/app.py`:
  - `_inject_globals` context_processor inyecta `clientes_usuario` (list[dict]) para `usuario_normal`.
  - `admin_usuarios_editar`: GET pasa `clientes_asignados_ids`; POST lee `cliente_ids` (checkboxes multi), elimina validación de empresa_id obligatoria, llama a `set_clientes_de_usuario`, mantiene `empresa_id` legacy cuando hay exactamente 1 cliente.
- `web/templates/admin/editar_usuario.html`: sección "Clientes asignados" con checkboxes scrollables (max-height 300px), reemplaza select de empresa única.
- `web/templates/clientes/_base.html`: sidebar `usuario_normal` muestra lista dinámica de todos sus clientes asignados con enlace directo al dashboard.
- `tests/test_usuario_clientes.py` (nuevo): 16 tests cubriendo repositorio, permisos, acceso web y renderizado de template.
```

- [ ] **Step 2: Actualizar sección "Estado de chats activos" en CLAUDE.md**

Localizar la subsección `### Nuevas funcionalidades` y actualizar:

```
### Nuevas funcionalidades
Último tema resuelto: feat asignación múltiple de clientes a usuario_normal —
tabla usuario_clientes, sesión con clientes_ids, sidebar dinámico, panel
edición master_admin con checkboxes.
Pendiente: ejecutar migration 202606_usuario_clientes.sql en Supabase.
```

- [ ] **Step 3: Ejecutar suite completa final**

```bash
cd /Users/manoloto/Apps/CHPapp && python -m pytest tests/ -x -q
```

Reportar resultados. No continuar si hay failures.

- [ ] **Step 4: Commit final y push**

```bash
git add CHANGELOG.md CLAUDE.md
git commit -m "feat(usuarios): asignación múltiple de clientes a usuario_normal con sidebar dinámico"
git push
```

---

## Notas de verificación post-deploy

Antes de dar el feature por completo en producción, ejecutar manualmente en Supabase:

```sql
-- storage/migrations/202606_usuario_clientes.sql
CREATE TABLE IF NOT EXISTS usuario_clientes (
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, cliente_id)
);
CREATE INDEX IF NOT EXISTS idx_usuario_clientes_user ON usuario_clientes (user_id);
CREATE INDEX IF NOT EXISTS idx_usuario_clientes_cliente ON usuario_clientes (cliente_id);
```

Los usuarios existentes con `empresa_id` siguen funcionando via fallback hasta que se migren manualmente a `usuario_clientes`.
