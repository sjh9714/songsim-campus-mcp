from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.anniversary_guides import (
    AnniversaryDonationInfoGuideSource,
    AnniversaryEventScheduleGuideSource,
    AnniversaryMilestoneGuideSource,
    AnniversaryOnlineMuseumGuideSource,
    AnniversaryPresidentMessageGuideSource,
    AnniversaryPromoVideoGuideSource,
    AnniversarySloganGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_anniversary_guides,
    refresh_anniversary_guides_from_source,
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


def test_anniversary_source_defaults() -> None:
    sources = [
        AnniversaryPresidentMessageGuideSource(),
        AnniversaryMilestoneGuideSource(),
        AnniversarySloganGuideSource(),
        AnniversaryPromoVideoGuideSource(),
        AnniversaryOnlineMuseumGuideSource(),
        AnniversaryEventScheduleGuideSource(),
        AnniversaryDonationInfoGuideSource(),
    ]

    assert [source.topic for source in sources] == [
        "president_message",
        "milestone",
        "slogan",
        "promo_video",
        "online_museum",
        "event_schedule",
        "donation_info",
    ]
    assert {source.source_tag for source in sources} == {"cuk_anniversary_guides"}


def test_anniversary_guide_parser_extracts_expected_row() -> None:
    rows = AnniversaryPresidentMessageGuideSource().parse(
        _fixture("anniversary_president_message.html"),
        fetched_at="2026-03-26T00:00:00+09:00",
    )

    assert rows[0]["topic"] == "president_message"
    assert rows[0]["title"] == "총장 축사글"
    assert rows[0]["summary"].startswith("1855년 작은 불씨에서 시작된")
    assert any("최준규 신부" in step for step in rows[0]["steps"])


def test_anniversary_guides_refresh_route_and_mcp(app_env, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()

    class PresidentFixtureSource(AnniversaryPresidentMessageGuideSource):
        def fetch(self) -> str:
            return _fixture("anniversary_president_message.html")

    with connection() as conn:
        refresh_anniversary_guides_from_source(
            conn,
            sources=[PresidentFixtureSource()],
            fetched_at="2026-03-26T00:00:00+09:00",
        )
        filtered = list_anniversary_guides(conn, topic="president_message", limit=20)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/anniversary-guides", params={"topic": "president_message"})
        invalid = client.get("/anniversary-guides", params={"topic": "bad"})

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()
    try:
        mcp = build_mcp()
        tool = mcp._tool_manager.get_tool("tool_list_anniversary_guides")
        result = tool.fn(topic="president_message", limit=5)
        payload = _tool_payloads(result)
        resource_text = _read_resource(mcp, "songsim://anniversary-guide")
    finally:
        clear_settings_cache()

    assert services.PUBLIC_READY_DATASET_POLICIES["anniversary_guides"] == "core"
    assert "anniversary_guides" in services.ADMIN_SYNC_TARGETS
    assert [guide.topic for guide in filtered] == ["president_message"]
    assert response.status_code == 200
    assert invalid.status_code == 400
    assert payload[0]["topic"] == "president_message"
    assert json.loads(resource_text)[0]["source_tag"] == "cuk_anniversary_guides"


def test_anniversary_guides_repo_replace_is_available(app_env) -> None:
    init_db()
    with connection() as conn:
        repo.replace_anniversary_guides(
            conn,
            [
                {
                    "topic": "slogan",
                    "title": "슬로건",
                    "summary": "170주년 슬로건 안내",
                    "steps": ["진리 안에서 170년"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/170ani/slogan-170.do",
                    "source_tag": "cuk_anniversary_guides",
                    "last_synced_at": "2026-03-26T00:00:00+09:00",
                }
            ],
        )
        rows = list_anniversary_guides(conn, topic="slogan", limit=20)

    assert rows[0].summary == "170주년 슬로건 안내"
