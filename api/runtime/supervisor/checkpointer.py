"""LangGraph checkpointer on the same SQLite file as the app documents table."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[3]

_conn: sqlite3.Connection | None = None
_saver: SqliteSaver | None = None


def sqlite_path() -> str:
    raw = os.environ.get("DATABASE_URL", f"sqlite:///{ROOT / 'api' / 'atelier.db'}")
    url = make_url(raw)
    if not url.drivername.startswith("sqlite"):
        raise RuntimeError("supervisor checkpointer expects a sqlite DATABASE_URL")
    database = url.database
    if not database or database == ":memory:":
        return ":memory:"
    return database


def get_checkpointer() -> SqliteSaver:
    global _conn, _saver
    if _saver is not None:
        return _saver
    path = sqlite_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(path, check_same_thread=False)
    _saver = SqliteSaver(_conn)
    _saver.setup()
    return _saver


def reset() -> None:
    global _conn, _saver
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = None
    _saver = None
