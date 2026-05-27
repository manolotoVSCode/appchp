# Entregable 6 — Cloud Deployment (Render + Supabase) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the cogeneration dashboard to Render (app.chpmex.com) backed by Supabase (PostgreSQL), with a web drag-and-drop UI so clients can upload CFE and Gas PDFs from the browser.

**Architecture:** A thin `Conn` adapter in `storage/db.py` wraps either `sqlite3` (local dev/tests) or `psycopg2` (Supabase in production), selected via the `DATABASE_URL` env var. Both dialects are unified by translating `?→%s`, using `RETURNING id` in INSERTs, and returning dict-like rows — so `repository.py` needs minimal changes. The Flask upload endpoint auto-detects invoice type from PDF text, parses and saves to DB, then refreshes the in-memory analysis result.

**Tech Stack:** Python 3.9+, Flask 3.x, pdfplumber, psycopg2-binary, openpyxl, gunicorn, Render (hosting), Supabase (PostgreSQL), Bootstrap 5.3 (UI)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `requirements.txt` | Create | All pip dependencies including gunicorn + psycopg2-binary |
| `Procfile` | Create | Render/Heroku process declaration |
| `render.yaml` | Create | Render service config |
| `.env.example` | Create | Template for required env vars |
| `storage/db.py` | Create | `Conn` adapter + `get_connection()` factory |
| `storage/schema.py` | Modify | Add `_DDL_PG` (PostgreSQL DDL) beside existing `DDL` (SQLite) |
| `storage/repository.py` | Modify | Use `Any` type hint, remove `conn.row_factory = sqlite3.Row` calls (adapter handles it), add `RETURNING id` to 3 INSERTs |
| `cli/main.py` | Modify | Change `sqlite3.Connection` type hints to `Any` |
| `web/app.py` | Modify | Use `get_connection()` from `storage.db`; read `DATABASE_URL`/`SQLITE_PATH` from env |
| `web/templates/dashboard.html` | Modify | Add drag-and-drop upload card + JS upload logic |
| `tests/storage/test_db_adapter.py` | Create | Unit tests for `Conn` adapter (both dialects) |
| `tests/test_web_upload.py` | Create | Integration tests for `/upload` endpoint |

---

## Task 1: Deploy Configuration Files

**Files:**
- Create: `requirements.txt`
- Create: `Procfile`
- Create: `render.yaml`
- Create: `.env.example`

- [ ] **Step 1: Create requirements.txt**

```
flask>=3.0
pdfplumber>=0.11
openpyxl>=3.1
psycopg2-binary>=2.9
gunicorn>=22.0
python-dotenv>=1.0
```

- [ ] **Step 2: Create Procfile**

```
web: gunicorn "web.app:create_app()" --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

The `--timeout 120` is important: on first startup Supabase cold connections can be slow.

- [ ] **Step 3: Create render.yaml**

```yaml
services:
  - type: web
    name: chpapp
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn "web.app:create_app()" --bind 0.0.0.0:$PORT --workers 2 --timeout 120
    envVars:
      - key: DATABASE_URL
        sync: false   # set manually in Render dashboard from Supabase
      - key: PYTHON_VERSION
        value: 3.9.6
```

- [ ] **Step 4: Create .env.example**

```bash
# Copy to .env and fill in values
# For local development with SQLite (no DATABASE_URL needed):
# SQLITE_PATH=chpapp.db

# For production with Supabase PostgreSQL:
# DATABASE_URL=postgresql://user:password@host:5432/dbname

# Leave both unset to use in-memory SQLite (tests / CI)
```

- [ ] **Step 5: Verify gunicorn can find the app factory**

```bash
cd /Users/manoloto/Apps/chpapp
pip install gunicorn psycopg2-binary python-dotenv
gunicorn "web.app:create_app()" --bind 127.0.0.1:9091 --workers 1 --timeout 30 &
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9091/
# Expected: 200 or 503 (loading)
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt Procfile render.yaml .env.example
git commit -m "feat: add deploy config for Render (Procfile, render.yaml, requirements.txt)"
```

---

## Task 2: DB Connection Adapter (`storage/db.py`)

**Files:**
- Create: `storage/db.py`
- Create: `tests/storage/test_db_adapter.py`

### Background

`repository.py` uses:
- `conn.execute(sql, params)` → cursor
- `cur.fetchone()` / `cur.fetchall()` → dict-like rows via `conn.row_factory = sqlite3.Row`
- `cur.lastrowid` → id of last inserted row
- `conn.executescript(ddl)` → for `init_db()`
- `conn.commit()`, `conn.close()`

PostgreSQL differences:
- Placeholders: `?` → `%s`
- Row access: need `RealDictCursor` (not `sqlite3.Row`)
- `lastrowid`: not available in psycopg2 — use `RETURNING id` in INSERT and fetch the result
- `executescript`: not available — split on `;` and execute each statement
- `PRAGMA foreign_keys = ON`: not valid in PostgreSQL

SQLite 3.43 (this project) supports `RETURNING id` — we will add it to all INSERTs that need the row id.

- [ ] **Step 1: Write failing tests**

Create `tests/storage/test_db_adapter.py`:

```python
# tests/storage/test_db_adapter.py
from __future__ import annotations
import pytest
from storage.db import get_connection


def test_sqlite_execute_and_fetchone(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    conn.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT);")
    cur = conn.execute("INSERT INTO t (val) VALUES (?) RETURNING id", ("hello",))
    assert cur.lastrowid == 1
    conn.commit()
    row = conn.execute("SELECT * FROM t WHERE id = ?", (1,)).fetchone()
    assert row["val"] == "hello"
    conn.close()


def test_sqlite_fetchall_returns_list_of_dicts(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    conn.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT);")
    conn.execute("INSERT INTO t (val) VALUES (?)", ("a",))
    conn.execute("INSERT INTO t (val) VALUES (?)", ("b",))
    conn.commit()
    rows = conn.execute("SELECT * FROM t ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["val"] == "a"
    assert rows[1]["val"] == "b"
    conn.close()


def test_sqlite_row_factory_assignment_is_noop(tmp_path):
    """repository.py sets conn.row_factory = sqlite3.Row — must not crash."""
    import sqlite3
    conn = get_connection(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row  # must not raise
    conn.close()


def test_sqlite_executescript_creates_tables(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    conn.executescript("""
        CREATE TABLE a (id INTEGER PRIMARY KEY);
        CREATE TABLE b (id INTEGER PRIMARY KEY);
    """)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in row]
    assert "a" in names
    assert "b" in names
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/manoloto/Apps/chpapp
pytest tests/storage/test_db_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'storage.db'`

- [ ] **Step 3: Implement `storage/db.py`**

```python
# storage/db.py
from __future__ import annotations

import os
import sqlite3
from typing import Any


def get_connection(sqlite_path: str | None = None) -> "Conn":
    """Return a Conn wrapping sqlite3 or psycopg2 depending on DATABASE_URL.

    Priority:
      1. DATABASE_URL env var → PostgreSQL (psycopg2)
      2. sqlite_path argument → SQLite file
      3. SQLITE_PATH env var → SQLite file
      4. fallback → SQLite :memory:
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        import psycopg2
        import psycopg2.extras
        raw = psycopg2.connect(db_url)
        raw.autocommit = False
        return _PgConn(raw)

    path = sqlite_path or os.environ.get("SQLITE_PATH", ":memory:")
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys = ON")
    raw.row_factory = sqlite3.Row
    return _SqliteConn(raw)


class Conn:
    """Abstract interface for database connections."""
    dialect: str  # "sqlite" | "postgres"

    def execute(self, sql: str, params: tuple = ()) -> "Cur":
        raise NotImplementedError

    def executemany(self, sql: str, seq: Any) -> None:
        raise NotImplementedError

    def executescript(self, sql: str) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    # no-op property so repository.py can still write conn.row_factory = sqlite3.Row
    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, val: Any) -> None:
        pass  # adapter already handles dict-like rows


class Cur:
    """Abstract interface for cursors."""

    def fetchone(self) -> dict | None:
        raise NotImplementedError

    def fetchall(self) -> list[dict]:
        raise NotImplementedError

    @property
    def lastrowid(self) -> int | None:
        raise NotImplementedError


# ── SQLite implementation ─────────────────────────────────────────────────────

class _SqliteCur(Cur):
    def __init__(self, cur: sqlite3.Cursor, lastrowid_val: int | None = None):
        self._cur = cur
        self._lastrowid_val = lastrowid_val

    def fetchone(self) -> dict | None:
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict]:
        return [dict(r) for r in self._cur.fetchall()]

    @property
    def lastrowid(self) -> int | None:
        # If the INSERT used RETURNING id, lastrowid is on the raw cursor
        return self._cur.lastrowid if self._cur.lastrowid else self._lastrowid_val


class _SqliteConn(Conn):
    dialect = "sqlite"

    def __init__(self, raw: sqlite3.Connection):
        self._raw = raw

    def execute(self, sql: str, params: tuple = ()) -> _SqliteCur:
        cur = self._raw.execute(sql, params)
        return _SqliteCur(cur)

    def executemany(self, sql: str, seq: Any) -> None:
        self._raw.executemany(sql, seq)

    def executescript(self, sql: str) -> None:
        self._raw.executescript(sql)
        self._raw.row_factory = sqlite3.Row  # executescript resets row_factory

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


# ── PostgreSQL implementation ─────────────────────────────────────────────────

def _to_pg(sql: str) -> str:
    """Translate SQLite-style ? placeholders to psycopg2-style %s."""
    return sql.replace("?", "%s")


class _PgCur(Cur):
    def __init__(self, cur: Any, lastrowid_val: int | None = None):
        self._cur = cur
        self._lastrowid_val = lastrowid_val

    def fetchone(self) -> dict | None:
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict]:
        rows = self._cur.fetchall()
        return [dict(r) for r in rows]

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid_val


class _PgConn(Conn):
    dialect = "postgres"

    def __init__(self, raw: Any):
        import psycopg2.extras
        self._raw = raw
        self._cursor_factory = psycopg2.extras.RealDictCursor

    def execute(self, sql: str, params: tuple = ()) -> _PgCur:
        pg_sql = _to_pg(sql)
        cur = self._raw.cursor(cursor_factory=self._cursor_factory)
        cur.execute(pg_sql, params if params else None)

        # If RETURNING id is present, capture the id now (cursor position moves)
        lastrowid = None
        if "RETURNING id" in sql.upper():
            row = cur.fetchone()
            lastrowid = dict(row)["id"] if row else None

        return _PgCur(cur, lastrowid)

    def executemany(self, sql: str, seq: Any) -> None:
        cur = self._raw.cursor()
        cur.executemany(_to_pg(sql), seq)

    def executescript(self, sql: str) -> None:
        """Execute multiple statements separated by semicolons."""
        cur = self._raw.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("PRAGMA"):
                cur.execute(stmt)
        self._raw.commit()

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/storage/test_db_adapter.py -v
```

Expected: 4 passed

- [ ] **Step 5: Run full suite — expect all existing tests still pass**

```bash
pytest --tb=short -q
```

Expected: 129 passed (existing tests unchanged — they still use raw sqlite3 connections)

- [ ] **Step 6: Commit**

```bash
git add storage/db.py tests/storage/test_db_adapter.py
git commit -m "feat: add DB connection adapter for SQLite/PostgreSQL (storage/db.py)"
```

---

## Task 3: PostgreSQL Schema + Wire Adapter into Repository and App

**Files:**
- Modify: `storage/schema.py`
- Modify: `storage/repository.py`
- Modify: `cli/main.py`
- Modify: `web/app.py`

### 3a — PostgreSQL DDL in schema.py

- [ ] **Step 1: Write failing test**

Add to `tests/storage/test_schema.py` (append at end):

```python
def test_init_db_accepts_conn_adapter(tmp_path):
    """init_db must work with Conn adapter, not just raw sqlite3."""
    from storage.db import get_connection
    conn = get_connection(str(tmp_path / "test.db"))
    from storage.schema import init_db
    init_db(conn)  # must not raise
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    assert "cfe_facturas" in names
    assert "gas_facturas" in names
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/storage/test_schema.py::test_init_db_accepts_conn_adapter -v
```

Expected: FAIL — `sqlite3.Connection has no executescript` on our Conn wrapper (or similar).

- [ ] **Step 3: Update storage/schema.py**

Replace the entire file:

```python
# storage/schema.py
from __future__ import annotations
from typing import Any

# SQLite DDL — used locally and in tests
_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS clientes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT    NOT NULL,
    rfc        TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cfe_facturas (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id                    INTEGER NOT NULL REFERENCES clientes(id),
    uuid_cfdi                     TEXT,
    folio                         TEXT    NOT NULL,
    serie                         TEXT,
    fecha_emision                 TEXT    NOT NULL,
    periodo_inicio                TEXT    NOT NULL,
    periodo_fin                   TEXT    NOT NULL,
    fecha_limite_pago             TEXT    NOT NULL,
    numero_servicio               TEXT    NOT NULL,
    rmu                           TEXT,
    tarifa                        TEXT    NOT NULL,
    numero_medidor                TEXT    NOT NULL,
    multiplicador                 INTEGER NOT NULL,
    carga_conectada_kw            TEXT    NOT NULL,
    demanda_contratada_kw         TEXT    NOT NULL,
    kw_max                        TEXT    NOT NULL,
    kvArh                         TEXT    NOT NULL,
    factor_potencia_pct           TEXT    NOT NULL,
    cargo_fijo_mxn                TEXT    NOT NULL,
    energia_total_mxn             TEXT    NOT NULL,
    cargo_factor_potencia_mxn     TEXT    NOT NULL,
    subtotal_mxn                  TEXT    NOT NULL,
    iva_mxn                       TEXT    NOT NULL,
    facturacion_periodo_mxn       TEXT    NOT NULL,
    derecho_alumbrado_publico_mxn TEXT    NOT NULL,
    credito_aplicado_mxn          TEXT    NOT NULL,
    total_mxn                     TEXT    NOT NULL,
    pdf_path                      TEXT    NOT NULL,
    advertencias                  TEXT    NOT NULL DEFAULT '[]',
    created_at                    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cfe_periodos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    periodo             TEXT    NOT NULL,
    consumo_kwh         TEXT    NOT NULL,
    demanda_kw          TEXT    NOT NULL,
    costo_unitario_kwh  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cfe_mem_componentes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    nombre              TEXT    NOT NULL,
    cargo_fijo_mxn      TEXT    NOT NULL,
    cargo_demanda_mxn   TEXT    NOT NULL,
    cargo_energia_mxn   TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gas_facturas (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id               INTEGER NOT NULL REFERENCES clientes(id),
    uuid_cfdi                TEXT,
    folio                    TEXT    NOT NULL,
    fecha_emision            TEXT    NOT NULL,
    periodo_inicio           TEXT    NOT NULL,
    periodo_fin              TEXT    NOT NULL,
    fecha_limite_pago        TEXT    NOT NULL,
    nombre_proveedor         TEXT    NOT NULL,
    rfc_proveedor            TEXT    NOT NULL,
    numero_cliente           TEXT    NOT NULL,
    cuenta_contrato          TEXT    NOT NULL,
    punto_suministro         TEXT    NOT NULL,
    numero_caseta            TEXT    NOT NULL,
    tipo_lectura             TEXT    NOT NULL,
    consumo_m3_corregidos    TEXT    NOT NULL,
    consumo_sin_corregir_m3  TEXT    NOT NULL,
    poder_calorifico_gj_m3   TEXT    NOT NULL,
    consumo_total_gj         TEXT    NOT NULL,
    costo_unitario_total_gj  TEXT    NOT NULL,
    subtotal_mxn             TEXT    NOT NULL,
    iva_mxn                  TEXT    NOT NULL,
    total_mxn                TEXT    NOT NULL,
    pdf_path                 TEXT    NOT NULL,
    advertencias             TEXT    NOT NULL DEFAULT '[]',
    created_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gas_conceptos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id          INTEGER NOT NULL REFERENCES gas_facturas(id) ON DELETE CASCADE,
    descripcion         TEXT    NOT NULL,
    clave_producto      TEXT    NOT NULL,
    cantidad_gj         TEXT    NOT NULL,
    precio_unitario_gj  TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);
"""

# PostgreSQL DDL — used in production (Supabase)
_DDL_PG = """
CREATE TABLE IF NOT EXISTS clientes (
    id         SERIAL PRIMARY KEY,
    nombre     TEXT   NOT NULL,
    rfc        TEXT   NOT NULL UNIQUE,
    created_at TEXT   NOT NULL DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS cfe_facturas (
    id                            SERIAL PRIMARY KEY,
    cliente_id                    INTEGER NOT NULL REFERENCES clientes(id),
    uuid_cfdi                     TEXT,
    folio                         TEXT    NOT NULL,
    serie                         TEXT,
    fecha_emision                 TEXT    NOT NULL,
    periodo_inicio                TEXT    NOT NULL,
    periodo_fin                   TEXT    NOT NULL,
    fecha_limite_pago             TEXT    NOT NULL,
    numero_servicio               TEXT    NOT NULL,
    rmu                           TEXT,
    tarifa                        TEXT    NOT NULL,
    numero_medidor                TEXT    NOT NULL,
    multiplicador                 INTEGER NOT NULL,
    carga_conectada_kw            TEXT    NOT NULL,
    demanda_contratada_kw         TEXT    NOT NULL,
    kw_max                        TEXT    NOT NULL,
    kvArh                         TEXT    NOT NULL,
    factor_potencia_pct           TEXT    NOT NULL,
    cargo_fijo_mxn                TEXT    NOT NULL,
    energia_total_mxn             TEXT    NOT NULL,
    cargo_factor_potencia_mxn     TEXT    NOT NULL,
    subtotal_mxn                  TEXT    NOT NULL,
    iva_mxn                       TEXT    NOT NULL,
    facturacion_periodo_mxn       TEXT    NOT NULL,
    derecho_alumbrado_publico_mxn TEXT    NOT NULL,
    credito_aplicado_mxn          TEXT    NOT NULL,
    total_mxn                     TEXT    NOT NULL,
    pdf_path                      TEXT    NOT NULL,
    advertencias                  TEXT    NOT NULL DEFAULT '[]',
    created_at                    TEXT    NOT NULL DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS cfe_periodos (
    id                  SERIAL PRIMARY KEY,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    periodo             TEXT    NOT NULL,
    consumo_kwh         TEXT    NOT NULL,
    demanda_kw          TEXT    NOT NULL,
    costo_unitario_kwh  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cfe_mem_componentes (
    id                  SERIAL PRIMARY KEY,
    factura_id          INTEGER NOT NULL REFERENCES cfe_facturas(id) ON DELETE CASCADE,
    nombre              TEXT    NOT NULL,
    cargo_fijo_mxn      TEXT    NOT NULL,
    cargo_demanda_mxn   TEXT    NOT NULL,
    cargo_energia_mxn   TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gas_facturas (
    id                       SERIAL PRIMARY KEY,
    cliente_id               INTEGER NOT NULL REFERENCES clientes(id),
    uuid_cfdi                TEXT,
    folio                    TEXT    NOT NULL,
    fecha_emision            TEXT    NOT NULL,
    periodo_inicio           TEXT    NOT NULL,
    periodo_fin              TEXT    NOT NULL,
    fecha_limite_pago        TEXT    NOT NULL,
    nombre_proveedor         TEXT    NOT NULL,
    rfc_proveedor            TEXT    NOT NULL,
    numero_cliente           TEXT    NOT NULL,
    cuenta_contrato          TEXT    NOT NULL,
    punto_suministro         TEXT    NOT NULL,
    numero_caseta            TEXT    NOT NULL,
    tipo_lectura             TEXT    NOT NULL,
    consumo_m3_corregidos    TEXT    NOT NULL,
    consumo_sin_corregir_m3  TEXT    NOT NULL,
    poder_calorifico_gj_m3   TEXT    NOT NULL,
    consumo_total_gj         TEXT    NOT NULL,
    costo_unitario_total_gj  TEXT    NOT NULL,
    subtotal_mxn             TEXT    NOT NULL,
    iva_mxn                  TEXT    NOT NULL,
    total_mxn                TEXT    NOT NULL,
    pdf_path                 TEXT    NOT NULL,
    advertencias             TEXT    NOT NULL DEFAULT '[]',
    created_at               TEXT    NOT NULL DEFAULT TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS gas_conceptos (
    id                  SERIAL PRIMARY KEY,
    factura_id          INTEGER NOT NULL REFERENCES gas_facturas(id) ON DELETE CASCADE,
    descripcion         TEXT    NOT NULL,
    clave_producto      TEXT    NOT NULL,
    cantidad_gj         TEXT    NOT NULL,
    precio_unitario_gj  TEXT    NOT NULL,
    importe_mxn         TEXT    NOT NULL
);
"""

# Legacy: keep the name `DDL` pointing to SQLite DDL so existing tests importing
# `from storage.schema import DDL` continue to work unchanged.
DDL = _DDL_SQLITE


def init_db(conn: Any) -> None:
    """Create tables if they do not exist. Safe to call multiple times.

    Accepts either a raw sqlite3.Connection (legacy/tests) or a Conn adapter
    from storage.db (production).
    """
    import sqlite3 as _sqlite3

    if isinstance(conn, _sqlite3.Connection):
        # Legacy path: raw sqlite3 connection (used by existing tests)
        conn.executescript("PRAGMA foreign_keys = ON;\n" + _DDL_SQLITE)
        conn.commit()
    else:
        # Conn adapter path
        ddl = _DDL_PG if getattr(conn, "dialect", "sqlite") == "postgres" else _DDL_SQLITE
        conn.executescript(ddl)
```

- [ ] **Step 4: Run the new test — expect PASS**

```bash
pytest tests/storage/test_schema.py -v
```

Expected: all pass (including the new `test_init_db_accepts_conn_adapter`)

### 3b — Update repository.py to add RETURNING id

The 3 INSERTs that use `lastrowid` need `RETURNING id` appended. This works in both SQLite 3.35+ and PostgreSQL.

- [ ] **Step 5: Edit storage/repository.py — `_upsert_cliente`**

Find:
```python
    cur = conn.execute(
        "INSERT INTO clientes (nombre, rfc) VALUES (?, ?)",
        (nombre, rfc),
    )
    conn.commit()
    return cur.lastrowid
```

Replace with:
```python
    cur = conn.execute(
        "INSERT INTO clientes (nombre, rfc) VALUES (?, ?) RETURNING id",
        (nombre, rfc),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 6: Edit storage/repository.py — `save_cfe_invoice` INSERT**

Find the end of the INSERT in `save_cfe_invoice`:
```python
            pdf_path, advertencias
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
```

Replace with:
```python
            pdf_path, advertencias
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        RETURNING id
        """,
```

Then find:
```python
    factura_id = cur.lastrowid
```
Leave it unchanged — `cur.lastrowid` now works for both dialects.

- [ ] **Step 7: Edit storage/repository.py — `save_gas_invoice` INSERT**

Find:
```python
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
```

Replace with:
```python
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
```

Then find `factura_id = cur.lastrowid` (in save_gas_invoice) — leave unchanged.

- [ ] **Step 8: Remove conn.row_factory assignments from repository.py**

These lines are no-ops on the Conn adapter (adapter always returns dicts) and still work on raw sqlite3.Connection (via the no-op setter). No change needed — they're harmless.

- [ ] **Step 9: Update type hints in repository.py and cli/main.py**

In `storage/repository.py`, at the top add:
```python
from typing import Any
```

Change every `conn: sqlite3.Connection` type hint to `conn: Any`.
Also remove `import sqlite3` if it's no longer used for anything else (check first — it's used for `sqlite3.Row` in row_factory assignments; keep the import).

Actually: `sqlite3` is still imported for `sqlite3.Row` in the row_factory lines. Keep the import. Just change the type hints.

In `cli/main.py`, change:
- `conn: sqlite3.Connection` → `conn: Any`
- Add `from typing import Any` at top

- [ ] **Step 10: Update web/app.py to use get_connection()**

Replace the `_cargar_resultado` function in `web/app.py`. Current version uses raw `sqlite3.connect()`. New version:

```python
# web/app.py
from __future__ import annotations

import io
import os
import threading
from contextlib import redirect_stdout
from pathlib import Path

from flask import Flask, render_template, send_file

from storage.db import get_connection
from storage.schema import init_db
from cli.main import procesar_factura_cfe, procesar_factura_gas
from calc.cogen import calcular_cogen
from models.cogen_result import CoGenParams


def _cargar_resultado(invoices_dir: Path, db_path: Path | None = None):
    """Load CoGenResultado from DB or by parsing PDFs.

    Production (DATABASE_URL set): connect to PostgreSQL, skip PDF parsing.
    Local with db_path: use that SQLite file.
    Local without db_path: use :memory: SQLite and parse PDFs.
    """
    db_url = os.environ.get("DATABASE_URL", "")

    if db_url:
        # Production: Supabase PostgreSQL — data already in DB from uploads
        conn = get_connection()
    elif db_path and db_path.exists():
        # Local fast-load from existing SQLite file
        conn = get_connection(str(db_path))
    else:
        # Local: parse PDFs and store in SQLite (file or memory)
        target = str(db_path) if db_path else None
        conn = get_connection(target)
        init_db(conn)

        buf = io.StringIO()
        with redirect_stdout(buf):
            for pdf in sorted(invoices_dir.glob("CFE/*.pdf")):
                try:
                    procesar_factura_cfe(pdf, conn)
                except Exception:
                    pass
            for pdf in sorted(invoices_dir.glob("Gas/*.pdf")):
                try:
                    procesar_factura_gas(pdf, conn)
                except Exception:
                    pass

    from storage.repository import (
        list_cfe_invoices, load_cfe_invoice,
        list_gas_invoices, load_gas_invoice,
    )
    cfe_rows = list_cfe_invoices(conn)
    cfe_invoices = [load_cfe_invoice(conn, r["id"]) for r in cfe_rows]
    gas_rows = list_gas_invoices(conn)
    gas_invoices = [load_gas_invoice(conn, r["id"]) for r in gas_rows]
    conn.close()

    return calcular_cogen(cfe_invoices, gas_invoices, CoGenParams())


def _refresh_resultado(app: Flask) -> None:
    """Reload analysis from DB and update app.config. Called after uploads."""
    db_path_str = app.config.get("DB_PATH")
    db_path = Path(db_path_str) if db_path_str else None
    invoices_dir = Path(app.config.get("INVOICES_DIR", "invoices"))
    app.config["RESULTADO"] = _cargar_resultado(invoices_dir, db_path)


def create_app(
    invoices_dir: str | Path = "invoices",
    db_path: str | Path | None = None,
) -> Flask:
    """Flask app factory. Port opens immediately; data loads in background."""
    app = Flask(__name__)
    app.config["RESULTADO"] = None
    app.config["CARGANDO"] = True
    app.config["DB_PATH"] = str(db_path) if db_path else None
    app.config["INVOICES_DIR"] = str(invoices_dir)

    _invoices = Path(invoices_dir)
    _db = Path(db_path) if db_path else None

    def _cargar_en_segundo_plano():
        app.config["RESULTADO"] = _cargar_resultado(_invoices, _db)
        app.config["CARGANDO"] = False
        src = os.environ.get("DATABASE_URL", "") or (str(_db) if _db else str(_invoices))
        print(f"✓ Datos cargados ({src}) — dashboard listo")

    threading.Thread(target=_cargar_en_segundo_plano, daemon=True).start()

    @app.route("/")
    def dashboard():
        if app.config["CARGANDO"]:
            return (
                "<html><head><meta http-equiv='refresh' content='5'>"
                "<title>Cargando...</title></head>"
                "<body style='font-family:sans-serif;padding:2rem'>"
                "<h2>&#9203; Cargando facturas...</h2>"
                "<p>Esta página se actualiza automáticamente cada 5 segundos.</p>"
                "</body></html>",
                503,
            )
        r = app.config["RESULTADO"]
        chart_labels = [m.periodo_inicio.strftime("%b %Y") for m in r.meses]
        chart_ebitda = [float(m.ebitda_mes_mxn) for m in r.meses]
        chart_ahorro_elec = [float(m.ahorro_electricidad_mxn) for m in r.meses]
        chart_ahorro_caldera = [float(m.ahorro_caldera_mxn) for m in r.meses]
        chart_costo_gas = [float(m.costo_gas_cogen_mxn) for m in r.meses]
        meses_raw = [
            {
                "periodo": m.periodo_inicio.strftime("%b %Y"),
                "kwh_total": float(m.kwh_total),
                "costo_cfe_mxn": float(m.costo_cfe_mxn),
                "costo_promedio_kwh": float(m.costo_promedio_kwh),
                "gj_consumido": float(m.gj_consumido),
                "costo_unitario_gj": float(m.costo_unitario_gj),
                "costo_gas_actual_mxn": float(m.costo_gas_actual_mxn),
            }
            for m in r.meses
        ]
        return render_template(
            "dashboard.html",
            r=r,
            chart_labels=chart_labels,
            chart_ebitda=chart_ebitda,
            chart_ahorro_elec=chart_ahorro_elec,
            chart_ahorro_caldera=chart_ahorro_caldera,
            chart_costo_gas=chart_costo_gas,
            meses_raw=meses_raw,
        )

    @app.route("/export/excel")
    def export_excel():
        import tempfile
        from reports.excel import generar_excel
        r = app.config["RESULTADO"]
        if r is None:
            return "Datos no listos aún", 503
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmp_path = Path(f.name)
        generar_excel(r, tmp_path)
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name="analisis_cogen.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return app
```

- [ ] **Step 11: Run full test suite — expect 130+ passed**

```bash
pytest --tb=short -q
```

Expected: all prior tests pass + the new schema adapter test.

- [ ] **Step 12: Commit**

```bash
git add storage/schema.py storage/repository.py cli/main.py web/app.py
git commit -m "feat: wire DB adapter into schema, repository, and web app (Task 3)"
```

---

## Task 4: `/upload` Endpoint with PDF Auto-Detection

**Files:**
- Modify: `web/app.py` — add `/upload` route and `_detect_tipo()` helper
- Create: `tests/test_web_upload.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_web_upload.py`:

```python
# tests/test_web_upload.py
from __future__ import annotations
import io
import pytest
from pathlib import Path
from web.app import create_app

INVOICES_DIR = "invoices"


@pytest.fixture(scope="module")
def client():
    import time
    app = create_app(INVOICES_DIR)
    app.config["TESTING"] = True
    while app.config.get("CARGANDO", False):
        time.sleep(0.5)
    with app.test_client() as c:
        yield c


def test_upload_cfe_pdf_returns_200(client):
    """Uploading a real CFE PDF must return 200 with procesados=1."""
    pdf_path = Path("invoices/CFE/P2 2023_11 NOVIEMBRE.pdf")
    with open(pdf_path, "rb") as f:
        data = {"facturas": (io.BytesIO(f.read()), pdf_path.name)}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["procesados"] >= 1
    assert body["errores"] == []


def test_upload_gas_pdf_returns_200(client):
    """Uploading a real Gas PDF must return 200 with procesados=1."""
    pdf_path = Path("invoices/Gas/TRA0002119W1_I_I0000054727751484 Nov 23.pdf")
    with open(pdf_path, "rb") as f:
        data = {"facturas": (io.BytesIO(f.read()), pdf_path.name)}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["procesados"] >= 1
    assert body["errores"] == []


def test_upload_non_pdf_returns_error(client):
    """Uploading a non-PDF file must return 200 with an error entry."""
    data = {"facturas": (io.BytesIO(b"not a pdf"), "fake.pdf")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["errores"] != [] or body["procesados"] == 0


def test_upload_refreshes_dashboard(client):
    """After upload, dashboard must reflect the updated data."""
    resp = client.get("/")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_web_upload.py -v
```

Expected: FAIL — `405 METHOD NOT ALLOWED` (route doesn't exist yet)

- [ ] **Step 3: Add `_detect_tipo()` and `/upload` route to web/app.py**

Add the following BEFORE the `return app` line in `create_app()`:

```python
    def _detect_tipo(pdf_path: Path) -> str:
        """Return 'cfe' or 'gas' by reading the first page of the PDF."""
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = (pdf.pages[0].extract_text() or "").upper()
        if "COMISIÓN FEDERAL" in text or "C.F.E." in text or "CFE" in text:
            return "cfe"
        if "ENGIE" in text or "GAS NATURAL" in text or "GAS" in text:
            return "gas"
        raise ValueError("No se pudo determinar el tipo de factura (CFE o Gas)")

    @app.route("/upload", methods=["POST"])
    def upload_facturas():
        import tempfile
        from flask import jsonify, request

        files = request.files.getlist("facturas")
        if not files:
            return jsonify({"procesados": 0, "errores": [{"nombre": "", "error": "No se enviaron archivos"}]}), 400

        db_path_str = app.config.get("DB_PATH")
        db_path_val = Path(db_path_str) if db_path_str else None

        conn = get_connection(str(db_path_val) if db_path_val else None)
        init_db(conn)

        ok_count = 0
        errors = []

        for f in files:
            suffix = Path(f.filename).suffix.lower() if f.filename else ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                f.save(tmp.name)
                tmp_path = Path(tmp.name)
            try:
                tipo = _detect_tipo(tmp_path)
                if tipo == "cfe":
                    procesar_factura_cfe(tmp_path, conn)
                else:
                    procesar_factura_gas(tmp_path, conn)
                ok_count += 1
            except Exception as e:
                errors.append({"nombre": f.filename or "", "error": str(e)})
            finally:
                tmp_path.unlink(missing_ok=True)

        conn.close()

        # Refresh in-memory analysis result
        _refresh_resultado(app)

        return jsonify({"procesados": ok_count, "errores": errors})
```

Also add these imports at the top of `web/app.py` (if not already present):

```python
from storage.schema import init_db
```

(`get_connection` is already imported from `storage.db`)

- [ ] **Step 4: Run upload tests — expect PASS**

```bash
pytest tests/test_web_upload.py -v
```

Expected: 4 passed

- [ ] **Step 5: Run full suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add web/app.py tests/test_web_upload.py
git commit -m "feat: add /upload endpoint with CFE/Gas auto-detection (Task 4)"
```

---

## Task 5: Upload Drag-and-Drop UI

**Files:**
- Modify: `web/templates/dashboard.html`
- Modify: `tests/test_web.py` — add test for upload UI presence

- [ ] **Step 1: Write failing test**

Append to `tests/test_web.py`:

```python
def test_dashboard_contiene_upload_zone(client):
    resp = client.get("/")
    html = resp.data
    assert b"upload" in html
    assert b"Subir Facturas" in html or b"Arrastra" in html
    assert b"/upload" in html
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_web.py::test_dashboard_contiene_upload_zone -v
```

Expected: FAIL

- [ ] **Step 3: Add upload card to dashboard.html**

Insert the following HTML block AFTER the sensitivity sliders card (after line `</div>` closing `<!-- Sliders de sensibilidad -->`), BEFORE `<!-- Gráfica -->`:

```html
  <!-- Upload de facturas -->
  <div class="card shadow-sm mb-4" id="upload-card">
    <div class="card-body">
      <h5 class="card-title">Subir Facturas</h5>
      <div id="drop-zone"
           class="border border-2 border-dashed rounded p-4 text-center text-muted"
           style="cursor:pointer; border-color:#adb5bd !important;">
        <div id="drop-label">
          &#128196; Arrastra los PDFs aquí o
          <label for="file-input" class="text-primary" style="cursor:pointer;">
            selecciona archivos
          </label>
        </div>
        <input type="file" id="file-input" multiple accept=".pdf" class="d-none">
      </div>
      <div id="upload-status" class="mt-2 small"></div>
    </div>
  </div>
```

Add the following `<script>` block BEFORE the closing `</body>` tag:

```html
<script>
// ── Upload drag & drop ────────────────────────────────────────────────────────
const dropZone   = document.getElementById("drop-zone");
const fileInput  = document.getElementById("file-input");
const statusDiv  = document.getElementById("upload-status");

dropZone.addEventListener("dragover", e => {
  e.preventDefault();
  dropZone.classList.add("bg-light");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("bg-light"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("bg-light");
  subirArchivos(e.dataTransfer.files);
});
fileInput.addEventListener("change", () => subirArchivos(fileInput.files));
dropZone.addEventListener("click", e => {
  if (e.target !== document.querySelector("label[for='file-input']")) {
    fileInput.click();
  }
});

async function subirArchivos(files) {
  if (!files || files.length === 0) return;
  statusDiv.innerHTML = `<span class="text-info">&#9203; Subiendo ${files.length} archivo(s)...</span>`;

  const fd = new FormData();
  for (const f of files) fd.append("facturas", f);

  try {
    const resp = await fetch("/upload", { method: "POST", body: fd });
    const data = await resp.json();

    let html = "";
    if (data.procesados > 0) {
      html += `<span class="text-success">&#10003; ${data.procesados} factura(s) procesada(s).</span> `;
    }
    if (data.errores && data.errores.length > 0) {
      html += `<span class="text-danger">&#10007; ${data.errores.length} error(es): `;
      html += data.errores.map(e => `${e.nombre}: ${e.error}`).join("; ");
      html += "</span>";
    }
    statusDiv.innerHTML = html;

    if (data.procesados > 0) {
      setTimeout(() => window.location.reload(), 1500);
    }
  } catch (err) {
    statusDiv.innerHTML = `<span class="text-danger">Error de red: ${err.message}</span>`;
  }
}
</script>
```

- [ ] **Step 4: Run upload UI test — expect PASS**

```bash
pytest tests/test_web.py::test_dashboard_contiene_upload_zone -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 6: Push to GitHub**

```bash
git add web/templates/dashboard.html tests/test_web.py
git commit -m "feat: add drag-and-drop PDF upload UI to dashboard (Task 5)"
git push origin main
```

---

## Self-Review

### Spec coverage
| Requirement | Task |
|---|---|
| Deploy config (Render) | Task 1 |
| PostgreSQL schema (Supabase) | Task 3 |
| DB adapter SQLite↔PostgreSQL | Task 2 |
| Web upload endpoint | Task 4 |
| Drag & drop UI | Task 5 |
| Push to GitHub | Task 5 Step 6 |

All requirements covered. ✓

### Placeholder scan
No TBD, TODO, or vague steps found. ✓

### Type consistency
- `get_connection()` → `Conn` (Tasks 2, 3, 4) ✓
- `_refresh_resultado(app)` defined in Task 3, called in Task 4 ✓
- `init_db(conn)` signature unchanged — accepts both `sqlite3.Connection` and `Conn` ✓
- `procesar_factura_cfe(path, conn)` and `procesar_factura_gas(path, conn)` — type hint changed to `Any`, runtime compatible ✓
