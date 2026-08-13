from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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
    """연결 하나를 감싸서, 다 쓰면 닫거나 풀에 돌려준다."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        pool: ConnectionPool | None = None,
    ) -> None:
        self._conn = conn
        self._pool = pool
        self._released = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __enter__(self) -> _ManagedConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        # psycopg 의 Connection.__exit__ 는 커밋/롤백까지 하고 연결을 닫는다.
        # 풀에서 빌린 연결을 닫아 버리면 풀을 쓰는 의미가 없으므로 여기서 직접 한다.
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self.close()
        return None

    def close(self) -> None:
        if self._released:
            return
        self._released = True
        if self._pool is not None:
            # 풀이 트랜잭션 상태를 되돌리고 다음 요청을 위해 연결을 살려 둔다.
            self._pool.putconn(self._conn)
        else:
            self._conn.close()


_POOLS: dict[str, ConnectionPool] = {}
_POOL_LOCK = threading.Lock()


def _get_pool(settings: Any) -> ConnectionPool | None:
    """배포된 공개 서비스에서만 연결을 재사용한다.

    이 서비스는 요청마다 psycopg.connect() 를 새로 열고 있었다. 그런데 앱은
    미국에서 돌고 데이터베이스는 서울에 있어서, TCP + TLS + 인증만 대여섯 왕복이
    붙는다. 실측으로 DB 를 쓰는 엔드포인트는 limit=1 이든 limit=50 이든 똑같이
    1.4초가 걸렸고, DB 를 안 쓰는 /healthz 는 0.3초였다. 1.1초가 통째로 연결
    수립 비용이었다는 뜻이다.

    로컬과 CLI, 테스트는 풀을 쓰지 않는다. 테스트는 케이스마다 새 데이터베이스를
    만들기 때문에 URL 이 계속 바뀌고, 그때마다 풀을 만들면 열린 연결만 쌓인다.
    실제로 이득이 있는 곳은 같은 URL 로 오래 사는 배포 서비스뿐이다.
    """
    if settings.app_mode != "public_readonly":
        return None
    key = str(settings.database_url)
    pool = _POOLS.get(key)
    if pool is not None:
        return pool
    with _POOL_LOCK:
        pool = _POOLS.get(key)
        if pool is None:
            pool = ConnectionPool(
                key,
                min_size=1,
                # 예전 세마포어와 같은 상한이다. Supabase 무료 플랜의 연결 수를
                # 넘지 않으려고 낮게 잡아 둔 값이라 그대로 따른다.
                max_size=PUBLIC_READONLY_DB_CONNECTION_LIMIT,
                kwargs={
                    "row_factory": dict_row,
                    "connect_timeout": 5,
                    "options": "-c timezone=Asia/Seoul",
                },
                timeout=10,
                # 빌려주기 전에 살아 있는지 한 번 확인한다. Supabase 쪽에서 유휴
                # 연결을 끊으면 죽은 연결이 요청에 그대로 나가 500 이 된다.
                # 확인 비용은 왕복 한 번이고, 새로 붙는 값(대여섯 왕복)보다 훨씬 싸다.
                check=ConnectionPool.check_connection,
                open=False,
            )
            # 백엔드가 잠들어 있어도 여기서 죽지 않는다. 실제 실패는 getconn 에서
            # 드러나고, API 는 그걸 503 으로 돌려준다.
            pool.open(wait=False)
            _POOLS[key] = pool
    return pool


def get_connection() -> DBConnection:
    settings = get_settings()
    pool = _get_pool(settings)
    if pool is not None:
        return _ManagedConnection(pool.getconn(), pool=pool)
    conn = psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        connect_timeout=5,
        options="-c timezone=Asia/Seoul",
    )
    return _ManagedConnection(conn)


def close_pools() -> None:
    """열려 있는 풀을 모두 닫는다. 프로세스를 내릴 때와 테스트 정리에 쓴다."""
    with _POOL_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close()


def init_db() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [item.strip() for item in schema.split(";") if item.strip()]
    with get_connection() as conn:
        # Serialize schema bootstrap so API/MCP cold starts don't race on CREATE TABLE.
        conn.execute("SELECT pg_advisory_lock(%s)", (SCHEMA_INIT_LOCK_KEY,))
        try:
            for statement in statements:
                if _schema_statement_needs_execution(conn, statement):
                    conn.execute(statement)
            conn.commit()
        finally:
            # 세션 단위 락이라 예전에는 연결이 닫히면서 같이 풀렸다. 이제 연결은
            # 풀로 돌아가 계속 살아 있으므로, 여기서 직접 풀지 않으면 락이 남는다.
            # 그러면 다음에 뜨는 서비스가 스키마 준비 단계에서 그대로 멈춘다.
            conn.execute("SELECT pg_advisory_unlock(%s)", (SCHEMA_INIT_LOCK_KEY,))
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


def _normalize_schema_statement(statement: str) -> str:
    """문장 앞에 붙은 주석 줄을 떼고 한 줄로 만든다.

    schema.sql 을 세미콜론으로 자르면 직전 주석이 다음 문장 앞에 딸려 온다.
    아래 정규식들은 ^CREATE / ^ALTER 로 시작하는지 보기 때문에 그 상태로는
    매칭이 빗나가고, 이미 있는 객체에 대해서도 문장을 실행하게 된다.

    소유자로 붙을 때는 전부 IF NOT EXISTS 라 조용히 넘어갔다. 권한을 좁힌
    역할로 붙이자마자 "must be owner of table" 로 기동이 실패해서 드러났다.
    """
    lines = [
        line
        for line in (raw.strip() for raw in statement.splitlines())
        if line and not line.startswith("--")
    ]
    return " ".join(" ".join(lines).split())


def _schema_statement_needs_execution(conn: DBConnection, statement: str) -> bool:
    normalized = _normalize_schema_statement(statement)
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
