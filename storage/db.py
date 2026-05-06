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
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise ImportError(
                "DATABASE_URL is set but psycopg2 is not installed. "
                "Run: pip install psycopg2-binary"
            ) from None
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
        if self._lastrowid_val is not None:
            return self._lastrowid_val
        return self._cur.lastrowid


class _SqliteConn(Conn):
    dialect = "sqlite"

    def __init__(self, raw: sqlite3.Connection):
        self._raw = raw

    def execute(self, sql: str, params: tuple = ()) -> _SqliteCur:
        cur = self._raw.execute(sql, params)
        # If RETURNING is present, drain the cursor immediately so it is not
        # left open (an open cursor blocks commit() in SQLite).
        lastrowid_val = None
        if "RETURNING" in sql.upper():
            rows = cur.fetchall()
            if rows and "id" in dict(rows[0]):
                lastrowid_val = dict(rows[0])["id"]
        return _SqliteCur(cur, lastrowid_val)

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

        # If RETURNING is present, capture the id now (cursor position moves)
        lastrowid = None
        if "RETURNING" in sql.upper():
            row = cur.fetchone()
            if row:
                row_dict = dict(row)
                lastrowid = row_dict.get("id") or next(iter(row_dict.values()), None)

        return _PgCur(cur, lastrowid)

    def executemany(self, sql: str, seq: Any) -> None:
        cur = self._raw.cursor()
        try:
            cur.executemany(_to_pg(sql), seq)
        finally:
            cur.close()

    def executescript(self, sql: str) -> None:
        """Execute multiple statements separated by semicolons."""
        cur = self._raw.cursor()
        try:
            # Note: splits on ";" — DDL must not contain semicolons inside string literals or comments
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt and not stmt.startswith("PRAGMA"):
                    cur.execute(stmt)
        finally:
            cur.close()
        self._raw.commit()

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()
