from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.newsroom_resource_guides import (
    BrochureGuideSource,
    CukStoryGuideSource,
    GalleryGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_newsroom_resource_guides,
    refresh_newsroom_resource_guides_from_source,
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


def test_newsroom_resource_guide_parsers_extract_expected_rows() -> None:
    fetched_at = "2026-03-26T00:00:00+09:00"
    brochure = BrochureGuideSource().parse(
        _fixture("newsroom_brochure.do.html"),
        fetched_at=fetched_at,
    )
    story = CukStoryGuideSource().parse(
        _fixture("newsroom_cukstory.do.html"),
        fetched_at=fetched_at,
    )
    gallery = GalleryGuideSource().parse(
        _fixture("newsroom_gallery.do.html"),
        fetched_at=fetched_at,
    )

    assert brochure[0]["topic"] == "brochure"
    assert brochure[0]["links"][0]["label"] == "KO 2023 Brochure VIEW MORE"
    assert story[0]["topic"] == "cuk_story"
    assert story[0]["links"][0]["label"] == "Vol.27 2025년 가대이야기 VIEW MORE"
    assert gallery[0]["topic"] == "gallery"
    assert any("이미지 사진" in step for step in gallery[0]["steps"])


def test_newsroom_resource_guides_refresh_route_and_mcp(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()

    class BrochureFixtureSource(BrochureGuideSource):
        def fetch(self) -> str:
            return _fixture("newsroom_brochure.do.html")

    with connection() as conn:
        refresh_newsroom_resource_guides_from_source(
            conn,
            sources=[BrochureFixtureSource()],
            fetched_at="2026-03-26T00:00:00+09:00",
        )
        filtered = list_newsroom_resource_guides(conn, topic="brochure", limit=20)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/newsroom-resource-guides", params={"topic": "brochure"})
        invalid = client.get("/newsroom-resource-guides", params={"topic": "bad"})

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()
    try:
        mcp = build_mcp()
        tool = mcp._tool_manager.get_tool("tool_list_newsroom_resource_guides")
        result = tool.fn(topic="brochure", limit=5)
        payload = _tool_payloads(result)
        resource_text = _read_resource(mcp, "songsim://newsroom-resource-guide")
    finally:
        clear_settings_cache()

    assert services.PUBLIC_READY_DATASET_POLICIES["newsroom_resource_guides"] == "core"
    assert "newsroom_resource_guides" in services.ADMIN_SYNC_TARGETS
    assert [guide.topic for guide in filtered] == ["brochure"]
    assert response.status_code == 200
    assert invalid.status_code == 400
    assert payload[0]["topic"] == "brochure"
    assert json.loads(resource_text)[0]["source_tag"] == "cuk_newsroom_resource_guides"


def test_newsroom_resource_guides_repo_replace_is_available(app_env) -> None:
    init_db()
    with connection() as conn:
        repo.replace_newsroom_resource_guides(
            conn,
            [
                {
                    "topic": "gallery",
                    "title": "홍보자료실",
                    "summary": "이미지 사진 DB 안내",
                    "steps": ["DB 사이트로 접속합니다."],
                    "links": [{"label": "이미지 사진 DB 바로가기", "url": "http://220.68.30.40/"}],
                    "source_url": "https://www.catholic.ac.kr/ko/newsroom/gallery.do",
                    "source_tag": "cuk_newsroom_resource_guides",
                    "last_synced_at": "2026-03-26T00:00:00+09:00",
                }
            ],
        )
        rows = list_newsroom_resource_guides(conn, topic="gallery", limit=20)

    assert rows[0].title == "홍보자료실"
