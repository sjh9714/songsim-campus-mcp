from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .settings import get_settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_INIT_LOCK_KEY = 608_489_971_338_014_235
PUBLIC_READONLY_DB_CONNECTION_LIMIT = 4
DBConnection = Any

_CREATE_EXTENSION_RE = re.compile(
    r"^CREATE\s+EXTENSION\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)$",
    re.IGNORECASE,
)
_CREATE_TABLE_RE = re.compile(
    r"^CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE,
)
_ALTER_TABLE_ADD_COLUMN_RE = re.compile(
    r"^ALTER\s+TABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE,
)
_CREATE_INDEX_RE = re.compile(
    r"^CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE,
)


class _ManagedConnection:
    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        limiter: threading.BoundedSemaphore | None = None,
    ) -> None:
        self._conn = conn
        self._limiter = limiter
        self._closed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __enter__(self) -> _ManagedConnection:
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        try:
            return self._conn.__exit__(exc_type, exc, tb)
        finally:
            self._release_limiter()

    def close(self) -> None:
        try:
            self._conn.close()
        finally:
            self._release_limiter()

    def _release_limiter(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._limiter is not None:
            self._limiter.release()


_CONNECTION_LIMITERS: dict[str, threading.BoundedSemaphore] = {}


def _connection_limiter_key(settings: Any) -> str:
    return f"{settings.app_mode}:{settings.database_url}"


def _get_connection_limiter(settings: Any) -> threading.BoundedSemaphore | None:
    if settings.app_mode != "public_readonly":
        return None
    key = _connection_limiter_key(settings)
    limiter = _CONNECTION_LIMITERS.get(key)
    if limiter is None:
        limiter = threading.BoundedSemaphore(PUBLIC_READONLY_DB_CONNECTION_LIMIT)
        _CONNECTION_LIMITERS[key] = limiter
    return limiter


def get_connection() -> DBConnection:
    settings = get_settings()
    limiter = _get_connection_limiter(settings)
    if limiter is not None:
        limiter.acquire()
    try:
        conn = psycopg.connect(
            settings.database_url,
            row_factory=dict_row,
            connect_timeout=5,
            options="-c timezone=Asia/Seoul",
        )
    except Exception:
        if limiter is not None:
            limiter.release()
        raise
    return _ManagedConnection(conn, limiter=limiter)


def init_db() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [item.strip() for item in schema.split(";") if item.strip()]
    with get_connection() as conn:
        # Serialize schema bootstrap so API/MCP cold starts don't race on CREATE TABLE.
        conn.execute("SELECT pg_advisory_lock(%s)", (SCHEMA_INIT_LOCK_KEY,))
        for statement in statements:
            if _schema_statement_needs_execution(conn, statement):
                conn.execute(statement)
        conn.commit()


@contextmanager
def connection() -> Iterator[DBConnection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _schema_statement_needs_execution(conn: DBConnection, statement: str) -> bool:
    normalized = " ".join(statement.split())
    if match := _CREATE_EXTENSION_RE.match(normalized):
        return not _extension_exists(conn, match.group(1))
    if match := _CREATE_TABLE_RE.match(normalized):
        return not _relation_exists(conn, match.group(1))
    if match := _ALTER_TABLE_ADD_COLUMN_RE.match(normalized):
        table_name, column_name = match.groups()
        return not _column_exists(conn, table_name, column_name)
    if match := _CREATE_INDEX_RE.match(normalized):
        return not _relation_exists(conn, match.group(1))
    return True


def _extension_exists(conn: DBConnection, extension_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM pg_extension WHERE extname = %s",
        (extension_name,),
    ).fetchone()
    return row is not None


def _relation_exists(conn: DBConnection, relation_name: str) -> bool:
    row = conn.execute(
        "SELECT to_regclass(%s)",
        (f"public.{relation_name}",),
    ).fetchone()
    return _first_column_value(row) is not None


def _column_exists(conn: DBConnection, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    ).fetchone()
    return row is not None


def _first_column_value(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]
