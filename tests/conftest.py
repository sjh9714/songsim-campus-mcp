from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from songsim_campus.api import create_app
from songsim_campus.services import reset_readiness_cache
from songsim_campus.settings import clear_settings_cache

ROOT_DIR = Path(__file__).resolve().parents[1]
POSTGRES_HOST = "127.0.0.1"
POSTGRES_PORT = 55432
POSTGRES_USER = "songsim"
POSTGRES_PASSWORD = "songsim"
POSTGRES_DEFAULT_DB = "songsim"


def _database_url(database: str) -> str:
    return (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{database}"
    )


def _run_compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )


def _wait_for_postgres() -> None:
    deadline = time.time() + 90
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with psycopg.connect(_database_url(POSTGRES_DEFAULT_DB), autocommit=True):
                return
        except psycopg.Error as exc:
            last_error = exc
            time.sleep(1)
    if last_error:
        raise last_error
    raise RuntimeError("Postgres did not become ready in time.")


def _postgres_is_ready() -> bool:
    try:
        with psycopg.connect(_database_url(POSTGRES_DEFAULT_DB), autocommit=True):
            return True
    except psycopg.Error:
        return False


def _drop_database(name: str) -> None:
    with psycopg.connect(_database_url("postgres"), autocommit=True) as conn:
        conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (name,),
        )
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)),
        )


@pytest.fixture(scope="session")
def postgres_server():
    started_with_compose = False
    if not _postgres_is_ready():
        _run_compose("up", "-d", "postgres")
        started_with_compose = True
        _wait_for_postgres()
    yield
    if started_with_compose:
        _run_compose("down", "-v")


@pytest.fixture()
def app_env(postgres_server, monkeypatch: pytest.MonkeyPatch):
    database_name = f"songsim_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_database_url("postgres"), autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)),
        )

    database_url = _database_url(database_name)
    monkeypatch.setenv("SONGSIM_DATABASE_URL", database_url)
    monkeypatch.delenv("SONGSIM_DATABASE_PATH", raising=False)
    monkeypatch.setenv("SONGSIM_SEED_DEMO_ON_START", "true")
    monkeypatch.setenv("SONGSIM_SYNC_OFFICIAL_ON_START", "false")
    monkeypatch.setenv("SONGSIM_ADMIN_ENABLED", "false")
    monkeypatch.setenv("SONGSIM_APP_MODE", "local_full")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "")
    monkeypatch.setenv("SONGSIM_PUBLIC_MCP_URL", "")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_ENABLED", "false")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_ISSUER", "")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_AUDIENCE", "")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_SCOPES", "songsim.read")
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "")
    # Settings 는 개발자의 .env 도 읽는다. 여기서 고정하지 않으면 각자의 로컬 값에
    # 따라 결과가 갈려서, CI 에서는 통과하는 테스트가 로컬에서만 깨진다.
    monkeypatch.setenv("SONGSIM_OFFICIAL_CAMPUS_ID", "1")
    monkeypatch.setenv("SONGSIM_OFFICIAL_NOTICE_PAGES", "3")
    clear_settings_cache()
    yield database_url
    clear_settings_cache()
    _drop_database(database_name)
    os.environ.pop("SONGSIM_DATABASE_URL", None)
    os.environ.pop("SONGSIM_SEED_DEMO_ON_START", None)
    os.environ.pop("SONGSIM_SYNC_OFFICIAL_ON_START", None)
    os.environ.pop("SONGSIM_ADMIN_ENABLED", None)
    os.environ.pop("SONGSIM_APP_MODE", None)
    os.environ.pop("SONGSIM_PUBLIC_HTTP_URL", None)
    os.environ.pop("SONGSIM_PUBLIC_MCP_URL", None)
    os.environ.pop("SONGSIM_MCP_OAUTH_ENABLED", None)
    os.environ.pop("SONGSIM_MCP_OAUTH_ISSUER", None)
    os.environ.pop("SONGSIM_MCP_OAUTH_AUDIENCE", None)
    os.environ.pop("SONGSIM_MCP_OAUTH_SCOPES", None)
    os.environ.pop("SONGSIM_KAKAO_REST_API_KEY", None)
    os.environ.pop("SONGSIM_OFFICIAL_CAMPUS_ID", None)
    os.environ.pop("SONGSIM_OFFICIAL_NOTICE_PAGES", None)
    os.environ.pop("SONGSIM_DATABASE_PATH", None)


@pytest.fixture(autouse=True)
def reset_readiness_runtime_cache():
    reset_readiness_cache()
    yield
    reset_readiness_cache()


@pytest.fixture()
def client(app_env: str):
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_client(app_env: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SONGSIM_ADMIN_ENABLED", "true")
    clear_settings_cache()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    clear_settings_cache()


@pytest.fixture()
def remote_admin_client(app_env: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SONGSIM_ADMIN_ENABLED", "true")
    clear_settings_cache()
    app = create_app()
    with TestClient(app, client=("8.8.8.8", 50000)) as test_client:
        yield test_client
    clear_settings_cache()
