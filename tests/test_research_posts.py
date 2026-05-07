from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.research_posts import ResearchResultPostSource
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_research_posts,
    refresh_research_posts_from_source,
    run_admin_sync,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _tool_payloads(result) -> list[dict[str, object]]:
    return list(result)


def _read_resource(mcp, uri: str) -> str:
    async def read() -> str:
        resource = await mcp._resource_manager.get_resource(uri)
        return await resource.read()

    return asyncio.run(read())


def test_research_result_post_source_defaults() -> None:
    source = ResearchResultPostSource()

    assert source.topic == "research_result"
    assert source.source_tag == "cuk_research_posts"
    assert source.url.endswith("/research/result.do")


def test_research_post_parser_extracts_list_and_detail_rows() -> None:
    source = ResearchResultPostSource()
    rows = source.parse_list(_fixture("research_result_list.html"))
    detail = source.parse_detail(
        _fixture("research_result_detail.html"),
        default_title=rows[0]["title"] or "",
        default_published_at=rows[0]["published_at"],
    )

    assert rows[0]["article_no"] == "900"
    assert rows[0]["title"] == "나건 교수팀, 지능형 하이드로겔 개발"
    assert rows[0]["published_at"] == "2026-04-24"
    assert detail["summary"].startswith("전기 자극으로 항암제 방출을")


def test_research_posts_refresh_replace_list_and_query(app_env) -> None:
    init_db()

    class ResearchFixtureSource(ResearchResultPostSource):
        def fetch_list(self, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("research_result_list.html")

        def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("research_result_detail.html")

    with connection() as conn:
        refresh_research_posts_from_source(
            conn,
            sources=[ResearchFixtureSource()],
            fetched_at="2026-03-26T00:00:00+09:00",
        )
        all_posts = list_research_posts(conn, limit=20)
        filtered = list_research_posts(
            conn,
            topic="research_result",
            query="하이드로겔",
            limit=20,
        )

    assert [post.topic for post in all_posts] == ["research_result"]
    assert [post.title for post in filtered] == ["나건 교수팀, 지능형 하이드로겔 개발"]


def test_research_posts_sync_contract(app_env, monkeypatch) -> None:
    init_db()

    assert "research_posts" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["research_posts"] == "best_effort"
    assert "research_posts" in services.PUBLIC_READY_BEST_EFFORT_DATASETS
    assert "research_posts" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_research_posts_from_source",
        lambda conn: [],
    )

    run = run_admin_sync(target="research_posts")

    assert run.summary == {"research_posts": 0}


def test_research_posts_http_route_and_mcp_surface(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        repo.replace_research_posts(
            conn,
            [
                {
                    "topic": "research_result",
                    "article_no": "900",
                    "title": "나건 교수팀, 지능형 하이드로겔 개발",
                    "published_at": "2026-04-24",
                    "summary": "전기 자극으로 항암제 방출을 조절합니다.",
                    "body_text": "전기 자극으로 항암제 방출을 정밀 조절합니다.",
                    "source_url": "https://www.catholic.ac.kr/ko/research/result.do",
                    "source_tag": "cuk_research_posts",
                    "last_synced_at": "2026-03-26T00:00:00+09:00",
                }
            ],
        )

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/research-posts", params={"query": "항암제"})
        invalid = client.get("/research-posts", params={"topic": "bad"})

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()
    try:
        mcp = build_mcp()
        tool = mcp._tool_manager.get_tool("tool_list_research_posts")
        result = tool.fn(topic="research_result", query="항암제", limit=5)
        payload = _tool_payloads(result)
        resource_text = _read_resource(mcp, "songsim://research-posts")
    finally:
        clear_settings_cache()

    assert response.status_code == 200
    assert response.json()[0]["topic"] == "research_result"
    assert invalid.status_code == 400
    assert payload[0]["source_tag"] == "cuk_research_posts"
    assert json.loads(resource_text)[0]["title"] == "나건 교수팀, 지능형 하이드로겔 개발"
