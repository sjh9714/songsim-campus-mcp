from __future__ import annotations

from pathlib import Path

import songsim_campus.db as db_module
from songsim_campus.db import connection, get_connection, init_db
from songsim_campus.settings import clear_settings_cache


def test_get_connection_uses_configured_database_url(app_env):
    conn = get_connection()
    try:
        row = conn.execute("SELECT current_database() AS name").fetchone()
    finally:
        conn.close()

    assert row["name"].startswith("songsim_test_")


def test_get_connection_reuses_one_connection_in_public_readonly(app_env, monkeypatch):
    """배포 모드에서는 요청마다 새로 붙지 않고 연결을 재사용한다.

    앱은 미국에서 돌고 데이터베이스는 서울에 있다. 요청마다 새로 붙으면
    TCP + TLS + 인증만 대여섯 왕복이 붙는데, 실측으로 그게 요청당 1.1초였다.
    같은 백엔드 프로세스로 붙는지를 pid 로 확인한다.
    """
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()
    db_module.close_pools()
    try:
        pids = []
        for _ in range(6):
            with connection() as conn:
                pids.append(conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])

        # 정확히 한 개라고 못 박지는 않는다. 풀이 min_size 를 채우는 동안 두 개가
        # 잠깐 생길 수 있다. 중요한 건 요청 수만큼 새로 붙지 않는다는 것이다.
        assert len(set(pids)) < len(pids), f"요청마다 새로 붙었다: {pids}"
        assert len(set(pids)) <= db_module.PUBLIC_READONLY_DB_CONNECTION_LIMIT, pids
    finally:
        db_module.close_pools()
        clear_settings_cache()


def test_get_connection_does_not_pool_outside_public_readonly(app_env):
    """로컬과 CLI, 테스트는 풀을 쓰지 않는다.

    테스트는 케이스마다 새 데이터베이스를 만들기 때문에 URL 이 계속 바뀐다.
    거기까지 풀을 만들면 쓰지도 않을 연결만 쌓인다.
    """
    db_module.close_pools()
    pids = []
    for _ in range(2):
        with connection() as conn:
            pids.append(conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])

    assert not db_module._POOLS
    assert len(set(pids)) == 2, "풀을 쓰지 않는데 같은 연결이 돌아왔다"


def test_pooled_connection_is_returned_clean_after_an_error(app_env, monkeypatch):
    """실패한 트랜잭션을 그대로 풀에 돌려주면 다음 요청이 같이 죽는다."""
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()
    db_module.close_pools()
    try:
        try:
            with connection() as conn:
                conn.execute("SELECT * FROM 존재하지_않는_테이블")
        except Exception:
            pass

        with connection() as conn:
            assert conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
    finally:
        db_module.close_pools()
        clear_settings_cache()


def test_init_db_skips_a_statement_that_has_a_comment_in_front_of_it(monkeypatch, tmp_path):
    """앞에 붙은 주석 때문에 "이미 있으니 건너뛴다" 판정을 놓치면 안 된다.

    schema.sql 을 세미콜론으로 자르면 직전 주석이 다음 문장 앞에 딸려 온다.
    정규식이 ^ALTER 로 시작하는지 보기 때문에 매칭이 빗나가고, 이미 있는 컬럼에
    대해서도 ALTER 를 실행했다. 소유자로 붙을 때는 IF NOT EXISTS 라 조용히
    넘어갔지만, 권한을 좁힌 역할로 붙으면 "must be owner of table" 로 죽는다.
    """
    schema_path = tmp_path / "schema.sql"
    schema_path.write_text(
        "\n".join(
            [
                "CREATE TABLE IF NOT EXISTS existing_table (id INTEGER PRIMARY KEY);",
                "-- 이 주석이 다음 문장에 딸려 붙는다.",
                "-- 두 줄이어도 마찬가지다.",
                "ALTER TABLE existing_table ADD COLUMN IF NOT EXISTS existing_column TEXT;",
            ]
        ),
        encoding="utf-8",
    )
    fake_connection = _FakeConnection()
    monkeypatch.setattr(db_module, "SCHEMA_PATH", schema_path)
    monkeypatch.setattr(db_module, "get_connection", lambda: fake_connection)

    init_db()

    assert fake_connection.executed == [], (
        f"이미 있는 컬럼인데 실행했다: {fake_connection.executed}"
    )


def test_init_db_creates_postgis_schema(app_env):
    init_db()

    with connection() as conn:
        extension = conn.execute(
            "SELECT extname FROM pg_extension WHERE extname = 'postgis'"
        ).fetchone()
        places_geom = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'places' AND column_name = 'geom'
            """
        ).fetchone()
        notices_labels = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'notices' AND column_name = 'labels_json'
            """
        ).fetchone()
        sync_started = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'sync_runs' AND column_name = 'started_at'
            """
        ).fetchone()
        sync_trigger = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'sync_runs' AND column_name = 'trigger'
            """
        ).fetchone()
        profile_department = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'profiles' AND column_name = 'department'
            """
        ).fetchone()
        profile_interests = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'profile_interests' AND column_name = 'tags_json'
            """
        ).fetchone()
        restaurant_hours = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'restaurant_hours_cache' AND column_name = 'opening_hours_json'
            """
        ).fetchone()
        restaurant_cache_place_id = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'restaurant_cache_items' AND column_name = 'kakao_place_id'
            """
        ).fetchone()
        library_seat_remaining = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'library_seat_status_cache' AND column_name = 'remaining_seats'
            """
        ).fetchone()
        library_seat_synced = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'library_seat_status_cache' AND column_name = 'last_synced_at'
            """
        ).fetchone()
        geom_index = conn.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'restaurants' AND indexname = 'idx_restaurants_geom'
            """
        ).fetchone()
        course_room_index = conn.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'courses' AND indexname = 'idx_courses_year_semester_room'
            """
        ).fetchone()

    assert extension["extname"] == "postgis"
    assert places_geom["data_type"] == "USER-DEFINED"
    assert notices_labels["data_type"] == "jsonb"
    assert sync_started["data_type"] == "timestamp with time zone"
    assert sync_trigger["data_type"] == "text"
    assert profile_department["data_type"] == "text"
    assert profile_interests["data_type"] == "jsonb"
    assert restaurant_hours["data_type"] == "jsonb"
    assert restaurant_cache_place_id["data_type"] == "text"
    assert library_seat_remaining["data_type"] == "integer"
    assert library_seat_synced["data_type"] == "timestamp with time zone"
    assert geom_index["indexname"] == "idx_restaurants_geom"
    assert course_room_index["indexname"] == "idx_courses_year_semester_room"


def test_init_db_acquires_schema_lock_before_running_statements(monkeypatch, tmp_path):
    schema_path = tmp_path / "schema.sql"
    schema_path.write_text(
        "CREATE TABLE IF NOT EXISTS alpha (id integer);"
        "CREATE TABLE IF NOT EXISTS beta (id integer);",
        encoding="utf-8",
    )
    executed: list[str] = []

    class FakeResult:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()
            return False

        def execute(self, statement, params=None):
            if statement == "SELECT pg_advisory_lock(%s)":
                executed.append(f"{statement}::{params!r}")
                return FakeResult((1,))
            if statement == "SELECT to_regclass(%s)":
                return FakeResult((None,))
            executed.append(statement if params is None else f"{statement}::{params!r}")
            return FakeResult(None)

        def commit(self):
            executed.append("COMMIT")

        def close(self):
            executed.append("CLOSE")

    fake_conn = FakeConnection()

    monkeypatch.setattr(db_module, "SCHEMA_PATH", Path(schema_path))
    monkeypatch.setattr(db_module, "get_connection", lambda: fake_conn)

    init_db()

    assert executed[0].startswith("SELECT pg_advisory_lock(")
    assert "CREATE TABLE IF NOT EXISTS alpha (id integer)" in executed[1]
    assert "CREATE TABLE IF NOT EXISTS beta (id integer)" in executed[2]
    assert executed[-2:] == ["COMMIT", "CLOSE"]


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.lock_calls: list[str] = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, statement: str, params=None):
        if statement in {
            "SELECT pg_advisory_lock(%s)",
            "SELECT pg_advisory_unlock(%s)",
        }:
            self.lock_calls.append(statement)
            return _FakeResult((1,))
        if statement == "SELECT 1 FROM pg_extension WHERE extname = %s":
            return _FakeResult((1,))
        if statement == "SELECT to_regclass(%s)":
            relation_name = params[0]
            if relation_name in {
                "public.existing_table",
                "public.existing_idx",
            }:
                return _FakeResult((relation_name,))
            return _FakeResult((None,))
        if "FROM information_schema.columns" in statement:
            table_name, column_name = params
            if (table_name, column_name) == ("existing_table", "existing_column"):
                return _FakeResult((1,))
            return _FakeResult(None)
        self.executed.append(" ".join(statement.split()))
        return _FakeResult(None)

    def commit(self) -> None:
        self.committed = True


def test_init_db_executes_only_missing_schema_statements(
    monkeypatch,
    tmp_path: Path,
) -> None:
    schema_path = tmp_path / "schema.sql"
    schema_path.write_text(
        "\n".join(
            [
                "CREATE EXTENSION IF NOT EXISTS postgis;",
                "CREATE TABLE IF NOT EXISTS existing_table (id INTEGER PRIMARY KEY);",
                "CREATE TABLE IF NOT EXISTS missing_table (id INTEGER PRIMARY KEY);",
                "ALTER TABLE existing_table ADD COLUMN IF NOT EXISTS existing_column TEXT;",
                "ALTER TABLE existing_table ADD COLUMN IF NOT EXISTS missing_column TEXT;",
                "CREATE INDEX IF NOT EXISTS existing_idx ON existing_table(id);",
                "CREATE INDEX IF NOT EXISTS missing_idx ON missing_table(id);",
            ]
        ),
        encoding="utf-8",
    )
    fake_connection = _FakeConnection()

    monkeypatch.setattr(db_module, "SCHEMA_PATH", schema_path)
    monkeypatch.setattr(db_module, "get_connection", lambda: fake_connection)

    init_db()

    assert fake_connection.executed == [
        "CREATE TABLE IF NOT EXISTS missing_table (id INTEGER PRIMARY KEY)",
        "ALTER TABLE existing_table ADD COLUMN IF NOT EXISTS missing_column TEXT",
        "CREATE INDEX IF NOT EXISTS missing_idx ON missing_table(id)",
    ]
    assert fake_connection.committed is True

    # 스키마 락은 세션 단위다. 예전에는 연결이 닫히면서 같이 풀렸지만, 이제 연결은
    # 풀에 살아남으므로 직접 풀어야 한다. 안 그러면 다음에 뜨는 서비스가 스키마
    # 준비 단계에서 그대로 멈춘다.
    assert fake_connection.lock_calls == [
        "SELECT pg_advisory_lock(%s)",
        "SELECT pg_advisory_unlock(%s)",
    ]
