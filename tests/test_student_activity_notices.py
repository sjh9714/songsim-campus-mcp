from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.student_activity_notices import StudentActivityNoticeSource
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_student_activity_notices,
    refresh_student_activity_notices_from_source,
    run_admin_sync,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _tool_payloads(result) -> list[dict[str, object]]:
    return [json.loads(item.text) for item in result]


def test_student_activity_notice_source_filters_official_notice_rows() -> None:
    source = StudentActivityNoticeSource()
    list_rows = source.parse_list(_fixture("student_activity_notice_list.html"))
    club_detail = source.parse_detail(
        _fixture("student_activity_notice_club_detail.html"),
        default_title=list_rows[0]["title"] or "",
        default_summary="",
        default_published_at=list_rows[0]["published_at"],
    )
    volunteer_detail = source.parse_detail(
        _fixture("student_activity_notice_volunteer_detail.html"),
        default_title=list_rows[1]["title"] or "",
        default_summary="",
        default_published_at=list_rows[1]["published_at"],
    )
    scholarship_detail = source.parse_detail(
        _fixture("student_activity_notice_scholarship_detail.html"),
        default_title=list_rows[2]["title"] or "",
        default_summary="",
        default_published_at=list_rows[2]["published_at"],
    )

    assert source.source_tag == "cuk_student_activity_notices"
    assert source.url.endswith("/campuslife/notice.do")
    assert list_rows[0]["article_no"] == "501"
    assert club_detail["topic"] == "club_recruitment"
    assert club_detail["summary"].startswith("중앙동아리연합회")
    assert volunteer_detail["topic"] == "volunteering"
    assert scholarship_detail["topic"] is None


def test_student_activity_notices_refresh_replace_and_list(app_env) -> None:
    init_db()

    class FixtureSource(StudentActivityNoticeSource):
        details = {
            "501": "student_activity_notice_club_detail.html",
            "502": "student_activity_notice_volunteer_detail.html",
            "503": "student_activity_notice_scholarship_detail.html",
        }

        def fetch_list(self, *, offset: int = 0, limit: int = 10) -> str:
            return _fixture("student_activity_notice_list.html")

        def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 10) -> str:
            return _fixture(self.details[article_no])

    with connection() as conn:
        refresh_student_activity_notices_from_source(
            conn,
            source=FixtureSource(),
            fetched_at="2026-03-24T00:00:00+09:00",
            pages=1,
        )
        all_notices = list_student_activity_notices(conn, limit=20)
        filtered = list_student_activity_notices(
            conn,
            topic="club_recruitment",
            query="신입부원",
            limit=20,
        )

        refresh_student_activity_notices_from_source(
            conn,
            source=FixtureSource(),
            fetched_at="2026-03-25T00:00:00+09:00",
            pages=0,
        )
        replaced = list_student_activity_notices(conn, limit=20)

    assert [notice.topic for notice in all_notices] == ["club_recruitment", "volunteering"]
    assert [notice.title for notice in filtered] == ["[학생지원팀] 중앙동아리 신입부원 모집 안내"]
    assert replaced == []


def test_student_activity_notices_sync_contract(app_env, monkeypatch) -> None:
    init_db()

    assert "student_activity_notices" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["student_activity_notices"] == "best_effort"
    assert "student_activity_notices" in services.PUBLIC_READY_BEST_EFFORT_DATASETS
    assert "student_activity_notices" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_student_activity_notices_from_source",
        lambda conn: [],
    )

    run = run_admin_sync(target="student_activity_notices")

    assert run.summary == {"student_activity_notices": 0}


def test_student_activity_notices_http_route_filters_and_rejects_invalid_topic(
    app_env,
) -> None:
    init_db()
    with connection() as conn:
        repo.replace_student_activity_notices(
            conn,
            [
                {
                    "topic": "club_recruitment",
                    "article_no": "501",
                    "title": "[학생지원팀] 중앙동아리 신입부원 모집 안내",
                    "published_at": "2026-03-22",
                    "summary": "중앙동아리연합회에서 신입부원을 모집합니다.",
                    "body_text": "중앙동아리연합회에서 신입부원을 모집합니다.",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice.do",
                    "source_tag": "cuk_student_activity_notices",
                    "last_synced_at": "2026-03-24T00:00:00+09:00",
                },
                {
                    "topic": "volunteering",
                    "article_no": "502",
                    "title": "[학부대학] 사회봉사 프로그램 참가자 모집",
                    "published_at": "2026-03-21",
                    "summary": "사회봉사 활동 참가자를 모집합니다.",
                    "body_text": "까리따스봉사단과 함께하는 사회봉사 활동 참가자를 모집합니다.",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice.do",
                    "source_tag": "cuk_student_activity_notices",
                    "last_synced_at": "2026-03-24T00:00:00+09:00",
                },
            ],
        )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/student-activity-notices",
            params={"topic": "volunteering", "query": "봉사단", "limit": 5},
        )
        invalid = client.get("/student-activity-notices", params={"topic": "invalid"})

    assert response.status_code == 200
    assert [item["topic"] for item in response.json()] == ["volunteering"]
    assert invalid.status_code == 400


def test_student_activity_notices_public_mcp_resource_and_tool_share_service_data(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        repo.replace_student_activity_notices(
            conn,
            [
                {
                    "topic": "club_recruitment",
                    "article_no": "501",
                    "title": "[학생지원팀] 중앙동아리 신입부원 모집 안내",
                    "published_at": "2026-03-22",
                    "summary": "중앙동아리연합회에서 신입부원을 모집합니다.",
                    "body_text": "중앙동아리연합회에서 신입부원을 모집합니다.",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice.do",
                    "source_tag": "cuk_student_activity_notices",
                    "last_synced_at": "2026-03-24T00:00:00+09:00",
                }
            ],
        )

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_student_activity_notices",
            {"topic": "club_recruitment", "limit": 5},
        )
        resource_result = await mcp.read_resource("songsim://student-activity-notices")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())
    tool_payload = _tool_payloads(tool_result)[0]
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["topic"] == "club_recruitment"
    assert tool_payload["notice_summary"] == "중앙동아리연합회에서 신입부원을 모집합니다."
    assert resource_payload[0]["source_tag"] == "cuk_student_activity_notices"

    clear_settings_cache()
