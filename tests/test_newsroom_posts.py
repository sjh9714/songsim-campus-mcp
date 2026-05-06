from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.newsroom_posts import PhotoNewsSource, PressSource
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_newsroom_posts,
    refresh_newsroom_posts_from_source,
    run_admin_sync,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _tool_payloads(result) -> list[dict[str, object]]:
    return [json.loads(item.text) for item in result]


def test_newsroom_source_defaults() -> None:
    photo_news = PhotoNewsSource()
    press = PressSource()

    assert photo_news.topic == "photo_news"
    assert press.topic == "press"
    assert photo_news.source_tag == "cuk_newsroom_posts"
    assert press.source_tag == "cuk_newsroom_posts"
    assert photo_news.url.endswith("/newsroom/photonews.do")
    assert press.url.endswith("/newsroom/press.do")


def test_newsroom_parsers_extract_expected_rows() -> None:
    photo_source = PhotoNewsSource()
    press_source = PressSource()

    photo_rows = photo_source.parse_list(_fixture("photonews_list.html"))
    photo_detail = photo_source.parse_detail(
        _fixture("photonews_detail.html"),
        default_title=photo_rows[0]["title"] or "",
        default_published_at=photo_rows[0]["published_at"],
    )
    press_rows = press_source.parse_list(_fixture("press_list.html"))
    press_detail = press_source.parse_detail(
        _fixture("press_detail.html"),
        default_title=press_rows[0]["title"] or "",
        default_summary=press_rows[0]["summary"] or "",
        default_published_at=press_rows[0]["published_at"],
    )

    assert photo_rows[0]["topic"] == "photo_news"
    assert photo_rows[0]["article_no"] == "300"
    assert photo_rows[0]["title"] == "성심교정 봄 캠퍼스 포토뉴스"
    assert photo_rows[0]["published_at"] == "2026-03-12"
    assert photo_rows[0]["thumbnail_url"] == (
        "https://www.catholic.ac.kr/_res/cuk/ko/img/photo-news.jpg"
    )
    assert photo_detail["summary"].startswith("가톨릭대학교 성심교정")
    assert press_rows[0]["topic"] == "press"
    assert press_rows[0]["article_no"] == "400"
    assert press_rows[0]["summary"] == "가톨릭뉴스"
    assert press_rows[0]["external_url"] == "https://media.example.com/cuk-press"
    assert press_rows[0]["source_url"] == (
        "https://www.catholic.ac.kr/ko/newsroom/press.do"
        "?mode=view&articleNo=400&article.offset=0&articleLimit=16"
    )
    assert press_detail["summary"] == "가톨릭뉴스"


def test_newsroom_posts_refresh_replace_and_list(app_env) -> None:
    init_db()

    class PhotoFixtureSource(PhotoNewsSource):
        def fetch_list(self, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("photonews_list.html")

        def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("photonews_detail.html")

    class PressFixtureSource(PressSource):
        def fetch_list(self, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("press_list.html")

        def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("press_detail.html")

    with connection() as conn:
        refresh_newsroom_posts_from_source(
            conn,
            sources=[PhotoFixtureSource(), PressFixtureSource()],
            fetched_at="2026-03-24T00:00:00+09:00",
        )
        all_posts = list_newsroom_posts(conn, limit=20)
        filtered = list_newsroom_posts(conn, topic="press", query="지역사회", limit=20)

        refresh_newsroom_posts_from_source(
            conn,
            sources=[PhotoFixtureSource()],
            fetched_at="2026-03-25T00:00:00+09:00",
        )
        replaced = list_newsroom_posts(conn, limit=20)

    assert [post.topic for post in all_posts] == ["photo_news", "press"]
    assert [post.title for post in filtered] == ["가톨릭대, 지역사회 협력 성과 발표"]
    assert [post.topic for post in replaced] == ["photo_news"]


def test_newsroom_posts_sync_contract(app_env, monkeypatch) -> None:
    init_db()

    assert "newsroom_posts" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["newsroom_posts"] == "best_effort"
    assert "newsroom_posts" in services.PUBLIC_READY_BEST_EFFORT_DATASETS
    assert "newsroom_posts" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_newsroom_posts_from_source",
        lambda conn: [],
    )

    run = run_admin_sync(target="newsroom_posts")

    assert run.summary == {"newsroom_posts": 0}


def test_newsroom_posts_http_route_filters_and_rejects_invalid_topic(app_env) -> None:
    init_db()
    with connection() as conn:
        repo.replace_newsroom_posts(
            conn,
            [
                {
                    "topic": "photo_news",
                    "article_no": "300",
                    "title": "성심교정 봄 캠퍼스 포토뉴스",
                    "published_at": "2026-03-12",
                    "summary": "성심교정 포토뉴스",
                    "thumbnail_url": "https://example.com/photo.jpg",
                    "external_url": None,
                    "source_url": "https://www.catholic.ac.kr/ko/newsroom/photonews.do",
                    "source_tag": "cuk_newsroom_posts",
                    "last_synced_at": "2026-03-24T00:00:00+09:00",
                },
                {
                    "topic": "press",
                    "article_no": "400",
                    "title": "가톨릭대, 지역사회 협력 성과 발표",
                    "published_at": "2026-03-11",
                    "summary": "가톨릭뉴스",
                    "thumbnail_url": None,
                    "external_url": "https://media.example.com/cuk-press",
                    "source_url": "https://www.catholic.ac.kr/ko/newsroom/press.do",
                    "source_tag": "cuk_newsroom_posts",
                    "last_synced_at": "2026-03-24T00:00:00+09:00",
                },
            ],
        )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/newsroom-posts",
            params={"topic": "press", "query": "지역사회", "limit": 5},
        )
        invalid = client.get("/newsroom-posts", params={"topic": "not-a-topic"})

    assert response.status_code == 200
    assert [item["topic"] for item in response.json()] == ["press"]
    assert invalid.status_code == 400


def test_newsroom_posts_public_mcp_resource_and_tool_share_service_data(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        repo.replace_newsroom_posts(
            conn,
            [
                {
                    "topic": "photo_news",
                    "article_no": "300",
                    "title": "성심교정 봄 캠퍼스 포토뉴스",
                    "published_at": "2026-03-12",
                    "summary": "성심교정 포토뉴스",
                    "thumbnail_url": "https://example.com/photo.jpg",
                    "external_url": None,
                    "source_url": "https://www.catholic.ac.kr/ko/newsroom/photonews.do",
                    "source_tag": "cuk_newsroom_posts",
                    "last_synced_at": "2026-03-24T00:00:00+09:00",
                }
            ],
        )

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_newsroom_posts",
            {"topic": "photo_news", "limit": 5},
        )
        resource_result = await mcp.read_resource("songsim://newsroom-posts")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())
    tool_payload = _tool_payloads(tool_result)[0]
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["topic"] == "photo_news"
    assert tool_payload["post_summary"] == "성심교정 포토뉴스"
    assert resource_payload[0]["source_tag"] == "cuk_newsroom_posts"

    clear_settings_cache()
