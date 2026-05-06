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
