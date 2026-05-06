from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.student_activity_guides import (
    CampusMediaGuideSource,
    CentralClubGuideSource,
    InstitutionalClubGuideSource,
    RotcGuideSource,
    SocialVolunteeringGuideSource,
    StudentGovernmentGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_student_activity_guides,
    refresh_student_activity_guides_from_source,
    run_admin_sync,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _tool_payloads(result) -> list[dict[str, object]]:
    return [json.loads(item.text) for item in result]


def test_student_activity_source_defaults() -> None:
    government = StudentGovernmentGuideSource()
    media = CampusMediaGuideSource()
    volunteer = SocialVolunteeringGuideSource()
    rotc = RotcGuideSource()
    central_clubs = CentralClubGuideSource()
    institutional_clubs = InstitutionalClubGuideSource(
        "https://www.catholic.ac.kr/ko/campuslife/institutional_club1.do"
    )

    assert government.topic == "student_government"
    assert media.topic == "campus_media"
    assert volunteer.topic == "social_volunteering"
    assert rotc.topic == "rotc"
    assert central_clubs.topic == "central_clubs"
    assert institutional_clubs.topic == "institutional_clubs"
    assert government.source_tag == "cuk_student_activity_guides"
    assert media.source_tag == "cuk_student_activity_guides"
    assert volunteer.source_tag == "cuk_student_activity_guides"
    assert rotc.source_tag == "cuk_student_activity_guides"
    assert central_clubs.source_tag == "cuk_student_activity_guides"
    assert institutional_clubs.source_tag == "cuk_student_activity_guides"
    assert government.url.endswith("/campuslife/student_government.do")
    assert media.url.endswith("/campuslife/media.do")
    assert volunteer.url.endswith("/campuslife/volunteer.do")
    assert rotc.url.endswith("/campuslife/rotc.do")
    assert central_clubs.url.endswith("/campuslife/club.do")
    assert institutional_clubs.url.endswith("/campuslife/institutional_club1.do")


def test_student_government_parser_extracts_expected_rows() -> None:
    rows = StudentGovernmentGuideSource().parse(
        _fixture("student_government.do.html"),
        fetched_at="2026-03-21T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["조직구성", "총학생회", "총동아리연합회"]
    organization = rows[0]
    assert organization["topic"] == "student_government"
    assert organization["summary"].startswith("학생회는 가톨릭대학교에 재학하는 학생으로 조직")
    assert any(step == "총학생회원" for step in organization["steps"])
    assert any(step == "총동아리연합회" for step in organization["steps"])
    assert not any(step == "QUICK MENU" for step in organization["steps"])
    assert organization["links"] == [
        {
            "label": "학생커뮤니티 바로가기",
            "url": "https://www.instagram.com/cuk_student",
        }
    ]
    assert (
        rows[1]["summary"]
        == "총학생회는 학생 의견을 수렴하고 학교생활의 불편함을 해결하는 학생자치 기구입니다."
    )
    assert (
        rows[2]["summary"]
        == "총동아리연합회는 동아리 행정과 행사기획, 신규 가입 동아리 심의를 담당합니다."
    )


def test_campus_media_parser_extracts_expected_rows() -> None:
    rows = CampusMediaGuideSource().parse(
        _fixture("media.do.html"),
        fetched_at="2026-03-21T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "가톨릭대학보",
        "영자신문사(The CUK Forum)",
        "교육방송국(CUBS)",
        "성심교지",
    ]
    english_news = rows[1]
    assert any(step == "영자신문사를 매거진으로 만날 수 있는 곳" for step in english_news["steps"])
    assert any("김수환추기경국제관 1층 엘리베이터" in step for step in english_news["steps"])
    assert {item["label"] for item in english_news["links"]} == {
        "홈페이지 바로가기",
        "페이스북 바로가기",
        "인스타그램 바로가기",
    }
    assert rows[2]["links"][0]["label"] == "인스타그램 바로가기"


def test_social_volunteering_parser_extracts_expected_rows() -> None:
    rows = SocialVolunteeringGuideSource().parse(
        _fixture("volunteer.do.html"),
        fetched_at="2026-03-21T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "국제봉사단",
        "까리따스봉사단",
        "사랑나누기(기초교양필수 교과목)",
        "사랑나누기+",
    ]
    assert rows[0]["links"][0]["label"] == "국제봉사단 알아보기"
    assert rows[1]["links"][0]["label"] == "까리따스봉사단 알아보기"
    assert rows[2]["links"][0]["label"] == "사랑나누기 알아보기"
    assert rows[3]["links"][0]["label"] == "사랑나누기+ 알아보기"


def test_rotc_parser_extracts_expected_row() -> None:
    rows = RotcGuideSource().parse(
        _fixture("rotc.do.html"),
        fetched_at="2026-03-21T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["제 207 학생군사교육단"]
    row = rows[0]
    assert row["topic"] == "rotc"
    assert row["summary"] == "학군사관 후보생 선발 및 교육을 실시하는 학생군사교육단입니다."
    assert row["links"] == [
        {
            "label": "학생군사교육단 바로가기",
            "url": "https://rotc.catholic.ac.kr/rotc/index.html",
        }
    ]


def test_central_clubs_parser_extracts_overview_and_club_rows() -> None:
    rows = CentralClubGuideSource().parse(
        _fixture("club.do.html"),
        fetched_at="2026-03-21T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "중앙동아리 분과 안내",
        "밴드실험",
        "가현회",
        "GDGoC",
    ]
    overview = rows[0]
    assert overview["topic"] == "central_clubs"
    assert "공예분과: 밴드실험, 가현회" in overview["steps"]
    assert "학술분과: GDGoC" in overview["steps"]

    band = rows[1]
    assert band["summary"] == (
        "밴드실험은 음악을 사랑하는 학생들이 함께 합주와 공연을 준비하는 중앙동아리입니다."
    )
    assert "분과: 공예분과" in band["steps"]
    assert band["links"] == [
        {
            "label": "@cuk_band",
            "url": "https://www.instagram.com/cuk_band",
        }
    ]
    assert band["source_url"].endswith("/campuslife/club.do#pop-layer-club1")


def test_institutional_club_parser_extracts_expected_row() -> None:
    rows = InstitutionalClubGuideSource(
        "https://www.catholic.ac.kr/ko/campuslife/institutional_club1.do"
    ).parse(
        _fixture("institutional_club1.do.html"),
        fetched_at="2026-03-21T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["홍보콘텐츠 제작 동아리 ‘CUK프렌즈’"]
    row = rows[0]
    assert row["topic"] == "institutional_clubs"
    assert row["summary"] == (
        "CUK프렌즈는 학생들의 시각과 방법으로 가대인과 학교의 다양한 이야기를 소개하는 "
        "가톨릭대 홍보콘텐츠 제작 동아리입니다."
    )
    assert "대외협력팀 기관 동아리" in row["steps"]
    assert "‘CUK프렌즈’를 소개합니다." in row["steps"]
    assert any("SNS운영팀" in step for step in row["steps"])
    assert {item["label"] for item in row["links"]} == {"@lovecuk", "ilovecuk"}


def test_student_activity_guides_refresh_replace_and_list(app_env) -> None:
    init_db()

    class GovernmentFixtureSource(StudentGovernmentGuideSource):
        def fetch(self) -> str:
            return _fixture("student_government.do.html")

    class MediaFixtureSource(CampusMediaGuideSource):
        def fetch(self) -> str:
            return _fixture("media.do.html")

    class VolunteerFixtureSource(SocialVolunteeringGuideSource):
        def fetch(self) -> str:
            return _fixture("volunteer.do.html")

    class RotcFixtureSource(RotcGuideSource):
        def fetch(self) -> str:
            return _fixture("rotc.do.html")

    class CentralClubFixtureSource(CentralClubGuideSource):
        def fetch(self) -> str:
            return _fixture("club.do.html")

    class InstitutionalClubFixtureSource(InstitutionalClubGuideSource):
        def __init__(self):
            super().__init__("https://www.catholic.ac.kr/ko/campuslife/institutional_club1.do")

        def fetch(self) -> str:
            return _fixture("institutional_club1.do.html")

    with connection() as conn:
        refresh_student_activity_guides_from_source(
            conn,
            sources=[
                GovernmentFixtureSource(),
                MediaFixtureSource(),
                VolunteerFixtureSource(),
                RotcFixtureSource(),
                CentralClubFixtureSource(),
                InstitutionalClubFixtureSource(),
            ],
            fetched_at="2026-03-21T00:00:00+09:00",
        )
        all_guides = list_student_activity_guides(conn, limit=20)
        volunteering = list_student_activity_guides(
            conn,
            topic="social_volunteering",
            limit=20,
        )

        refresh_student_activity_guides_from_source(
            conn,
            sources=[RotcFixtureSource()],
            fetched_at="2026-03-22T00:00:00+09:00",
        )
        replaced = list_student_activity_guides(conn, limit=20)

    assert [guide.topic for guide in all_guides] == [
        "campus_media",
        "campus_media",
        "campus_media",
        "campus_media",
        "central_clubs",
        "central_clubs",
        "central_clubs",
        "central_clubs",
        "institutional_clubs",
        "rotc",
        "social_volunteering",
        "social_volunteering",
        "social_volunteering",
        "social_volunteering",
        "student_government",
        "student_government",
        "student_government",
    ]
    assert [guide.title for guide in volunteering] == [
        "국제봉사단",
        "까리따스봉사단",
        "사랑나누기(기초교양필수 교과목)",
        "사랑나누기+",
    ]
    assert [guide.title for guide in replaced] == ["제 207 학생군사교육단"]


def test_student_activity_guides_sync_contract(app_env, monkeypatch) -> None:
    init_db()

    assert "student_activity_guides" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["student_activity_guides"] == "core"
    assert "student_activity_guides" in services.PUBLIC_READY_CORE_DATASETS
    assert "student_activity_guides" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_student_activity_guides_from_source",
        lambda conn: [],
    )

    run = run_admin_sync(target="student_activity_guides")

    assert run.summary == {"student_activity_guides": 0}


def test_student_activity_guides_http_route_filters_and_rejects_invalid_topic(app_env) -> None:
    init_db()
    with connection() as conn:
        repo.replace_student_activity_guides(
            conn,
            [
                {
                    "topic": "campus_media",
                    "title": "가톨릭대학보",
                    "summary": "교내 언론",
                    "steps": ["가톨릭대학교 소통의 구심점 역할"],
                    "links": [{"label": "홈페이지 바로가기", "url": "https://example.com/news"}],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/media.do",
                    "source_tag": "cuk_student_activity_guides",
                    "last_synced_at": "2026-03-21T00:00:00+09:00",
                },
                {
                    "topic": "rotc",
                    "title": "제 207 학생군사교육단",
                    "summary": "ROTC",
                    "steps": ["학군사관 후보생 선발"],
                    "links": [{"label": "학생군사교육단 바로가기", "url": "https://example.com/rotc"}],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/rotc.do",
                    "source_tag": "cuk_student_activity_guides",
                    "last_synced_at": "2026-03-21T00:00:00+09:00",
                },
            ],
        )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/student-activity-guides",
            params={"topic": "campus_media", "limit": 5},
        )
        invalid = client.get("/student-activity-guides", params={"topic": "unknown"})

    assert response.status_code == 200
    assert [item["topic"] for item in response.json()] == ["campus_media"]
    assert invalid.status_code == 400


def test_student_activity_guides_public_mcp_resource_and_tool_share_service_data(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        repo.replace_student_activity_guides(
            conn,
            [
                {
                    "topic": "social_volunteering",
                    "title": "국제봉사단",
                    "summary": "나눔의 세계화를 실천하는 국제 사회봉사단입니다.",
                    "steps": ["나눔의 세계화를 실천"],
                    "links": [{"label": "국제봉사단 알아보기", "url": "https://example.com/international"}],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/volunteer.do",
                    "source_tag": "cuk_student_activity_guides",
                    "last_synced_at": "2026-03-21T00:00:00+09:00",
                }
            ],
        )

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_student_activity_guides",
            {"topic": "social_volunteering", "limit": 5},
        )
        resource_result = await mcp.read_resource("songsim://student-activity-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())
    tool_payload = _tool_payloads(tool_result)[0]
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["topic"] == "social_volunteering"
    assert tool_payload["guide_summary"] == "나눔의 세계화를 실천하는 국제 사회봉사단입니다."
    assert resource_payload[0]["source_tag"] == "cuk_student_activity_guides"

    clear_settings_cache()
