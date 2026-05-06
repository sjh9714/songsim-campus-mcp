from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.about_resource_guides import (
    AcademicHandbookGuideSource,
    BudgetAccountGuideSource,
    CampusTourGuideSource,
    ChurchLiteratureGuideSource,
    HistoryGuideSource,
    RuleGuideSource,
    UniversityBulletinGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_about_resource_guides,
    refresh_about_resource_guides_from_source,
    run_admin_sync,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _tool_payloads(result) -> list[dict[str, object]]:
    return [json.loads(item.text) for item in result]


def test_about_resource_source_defaults() -> None:
    rules = RuleGuideSource()
    bulletin = UniversityBulletinGuideSource()
    handbook = AcademicHandbookGuideSource()
    campus_tour = CampusTourGuideSource()
    history = HistoryGuideSource()
    church_literature = ChurchLiteratureGuideSource()
    budget_account = BudgetAccountGuideSource()

    assert rules.topic == "rules"
    assert bulletin.topic == "university_bulletin"
    assert handbook.topic == "academic_handbook"
    assert campus_tour.topic == "campus_tour"
    assert history.topic == "history"
    assert church_literature.topic == "church_literature"
    assert budget_account.topic == "budget_account"
    assert rules.source_tag == "cuk_about_resource_guides"
    assert bulletin.source_tag == "cuk_about_resource_guides"
    assert handbook.source_tag == "cuk_about_resource_guides"
    assert campus_tour.source_tag == "cuk_about_resource_guides"
    assert history.source_tag == "cuk_about_resource_guides"
    assert church_literature.source_tag == "cuk_about_resource_guides"
    assert budget_account.source_tag == "cuk_about_resource_guides"
    assert rules.url.endswith("/about/rule.do")
    assert bulletin.url.endswith("/about/univ_bulletin.do")
    assert handbook.url.endswith("/about/brochure_rule.do")
    assert campus_tour.url.endswith("/about/campus_tour.do")
    assert history.url.endswith("/about/history.do")
    assert church_literature.url.endswith("/about/church_literature2.do")
    assert budget_account.url.endswith("/about/budgetaccount.do")


def test_about_resource_parsers_extract_expected_rows() -> None:
    rules = RuleGuideSource().parse(
        _fixture("rule.do.html"),
        fetched_at="2026-03-22T00:00:00+09:00",
    )
    bulletin = UniversityBulletinGuideSource().parse(
        _fixture("univ_bulletin.do.html"),
        fetched_at="2026-03-22T00:00:00+09:00",
    )
    handbook = AcademicHandbookGuideSource().parse(
        _fixture("brochure_rule.do.html"),
        fetched_at="2026-03-22T00:00:00+09:00",
    )
    campus_tour = CampusTourGuideSource().parse(
        _fixture("campus_tour.do.html"),
        fetched_at="2026-03-22T00:00:00+09:00",
    )
    history = HistoryGuideSource().parse(
        _fixture("history.do.html"),
        fetched_at="2026-03-22T00:00:00+09:00",
    )
    church_literature = ChurchLiteratureGuideSource().parse(
        _fixture("church_literature2.do.html"),
        fetched_at="2026-03-22T00:00:00+09:00",
    )
    budget_account = BudgetAccountGuideSource().parse(
        _fixture("budgetaccount.do.html"),
        fetched_at="2026-03-22T00:00:00+09:00",
    )

    assert rules[0]["topic"] == "rules"
    assert rules[0]["title"] == "규정"
    assert rules[0]["summary"].startswith("가톨릭대학교 규정정보시스템")
    assert rules[0]["links"] == [
        {
            "label": "규정정보시스템 바로가기",
            "url": "http://rule.catholic.ac.kr:8080/lmxsrv/main/main.srv",
        }
    ]
    assert bulletin[0]["topic"] == "university_bulletin"
    assert {
        item["label"] for item in bulletin[0]["links"]
    } == {"2026 대학요람 PDF", "2025 대학요람 PDF"}
    assert bulletin[0]["links"][0]["url"] == (
        "https://www.catholic.ac.kr/ko/about/download/univ_bulletin_2026.pdf"
    )
    assert handbook[0]["topic"] == "academic_handbook"
    assert "최신 책자는 공식 PDF 링크를 기준으로 확인합니다." in handbook[0]["steps"]
    assert handbook[0]["links"][0]["label"] == "학사제도안내책자 PDF"
    assert campus_tour[0]["topic"] == "campus_tour"
    assert campus_tour[0]["title"] == "캠퍼스투어"
    assert campus_tour[0]["summary"].startswith("캠퍼스투어 신청대상")
    assert "10인 이상 ~ 100인 이하의 고등학교" in campus_tour[0]["steps"]
    assert "대외협력팀 / 02-2164-4169" in campus_tour[0]["steps"]
    assert campus_tour[0]["links"] == [
        {
            "label": "캠퍼스투어 신청하기",
            "url": "https://www.catholic.ac.kr/ko/about/campus_tour_step1.do",
        }
    ]
    assert history[0]["topic"] == "history"
    assert history[0]["title"] == "연혁"
    assert history[0]["summary"].startswith("가톨릭대학교 연혁")
    assert {item["label"] for item in history[0]["links"]} == {"1900년 이전", "1900~1990년"}
    assert history[0]["links"][0]["url"] == "https://www.catholic.ac.kr/ko/about/history1.do"
    assert church_literature[0]["topic"] == "church_literature"
    assert church_literature[0]["title"] == "가톨릭대학교회문헌"
    assert "교회문헌" in church_literature[0]["summary"]
    assert [item["label"] for item in church_literature[0]["links"]] == [
        "교황령 '교회의 심장부'",
        "한국 가톨릭 대학교 규정",
        "한국 가톨릭학교 교육헌장",
    ]
    assert budget_account[0]["topic"] == "budget_account"
    assert budget_account[0]["title"] == "예결산공고"
    assert budget_account[0]["summary"].startswith("예산/결산 공고 게시판")
    assert {item["label"] for item in budget_account[0]["links"]} == {
        "2026학년도 가톨릭대학교 자금예산서",
        "2024학년도 결산 공고",
    }


def test_about_resource_guides_refresh_replace_and_list(app_env) -> None:
    init_db()

    class RulesFixtureSource(RuleGuideSource):
        def fetch(self) -> str:
            return _fixture("rule.do.html")

    class BulletinFixtureSource(UniversityBulletinGuideSource):
        def fetch(self) -> str:
            return _fixture("univ_bulletin.do.html")

    class HandbookFixtureSource(AcademicHandbookGuideSource):
        def fetch(self) -> str:
            return _fixture("brochure_rule.do.html")

    class CampusTourFixtureSource(CampusTourGuideSource):
        def fetch(self) -> str:
            return _fixture("campus_tour.do.html")

    class HistoryFixtureSource(HistoryGuideSource):
        def fetch(self) -> str:
            return _fixture("history.do.html")

    class ChurchLiteratureFixtureSource(ChurchLiteratureGuideSource):
        def fetch(self) -> str:
            return _fixture("church_literature2.do.html")

    class BudgetAccountFixtureSource(BudgetAccountGuideSource):
        def fetch(self) -> str:
            return _fixture("budgetaccount.do.html")

    with connection() as conn:
        refresh_about_resource_guides_from_source(
            conn,
            sources=[
                RulesFixtureSource(),
                BulletinFixtureSource(),
                HandbookFixtureSource(),
                CampusTourFixtureSource(),
                HistoryFixtureSource(),
                ChurchLiteratureFixtureSource(),
                BudgetAccountFixtureSource(),
            ],
            fetched_at="2026-03-22T00:00:00+09:00",
        )
        all_guides = list_about_resource_guides(conn, limit=20)
        filtered = list_about_resource_guides(conn, topic="campus_tour", limit=20)

        refresh_about_resource_guides_from_source(
            conn,
            sources=[RulesFixtureSource()],
            fetched_at="2026-03-23T00:00:00+09:00",
        )
        replaced = list_about_resource_guides(conn, limit=20)

    assert [guide.topic for guide in all_guides] == [
        "academic_handbook",
        "budget_account",
        "campus_tour",
        "church_literature",
        "history",
        "rules",
        "university_bulletin",
    ]
    assert [guide.title for guide in filtered] == ["캠퍼스투어"]
    assert [guide.title for guide in replaced] == ["규정"]


def test_about_resource_guides_sync_contract(app_env, monkeypatch) -> None:
    init_db()

    assert "about_resource_guides" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["about_resource_guides"] == "core"
    assert "about_resource_guides" in services.PUBLIC_READY_CORE_DATASETS
    assert "about_resource_guides" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_about_resource_guides_from_source",
        lambda conn: [],
    )

    run = run_admin_sync(target="about_resource_guides")

    assert run.summary == {"about_resource_guides": 0}


def test_about_resource_guides_http_route_filters_and_rejects_invalid_topic(app_env) -> None:
    init_db()
    with connection() as conn:
        repo.replace_about_resource_guides(
            conn,
            [
                {
                    "topic": "rules",
                    "title": "규정",
                    "summary": "규정정보시스템 안내",
                    "steps": ["공식 규정정보시스템에서 원문을 확인합니다."],
                    "links": [
                        {
                            "label": "규정정보시스템 바로가기",
                            "url": "http://rule.catholic.ac.kr:8080/lmxsrv/main/main.srv",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/about/rule.do",
                    "source_tag": "cuk_about_resource_guides",
                    "last_synced_at": "2026-03-22T00:00:00+09:00",
                },
                {
                    "topic": "academic_handbook",
                    "title": "학사제도안내책자",
                    "summary": "학사제도 자료",
                    "steps": ["공식 PDF 링크에서 확인합니다."],
                    "links": [{"label": "PDF", "url": "https://example.com/handbook.pdf"}],
                    "source_url": "https://www.catholic.ac.kr/ko/about/brochure_rule.do",
                    "source_tag": "cuk_about_resource_guides",
                    "last_synced_at": "2026-03-22T00:00:00+09:00",
                },
            ],
        )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/about-resource-guides",
            params={"topic": "rules", "limit": 5},
        )
        invalid = client.get("/about-resource-guides", params={"topic": "not-a-topic"})

    assert response.status_code == 200
    assert [item["topic"] for item in response.json()] == ["rules"]
    assert invalid.status_code == 400


def test_about_resource_guides_public_mcp_resource_and_tool_share_service_data(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        repo.replace_about_resource_guides(
            conn,
            [
                {
                    "topic": "university_bulletin",
                    "title": "요람",
                    "summary": "가톨릭대학교 요람 PDF 안내",
                    "steps": ["공식 PDF 링크에서 최신 요람을 확인합니다."],
                    "links": [{"label": "요람 PDF", "url": "https://example.com/bulletin.pdf"}],
                    "source_url": "https://www.catholic.ac.kr/ko/about/univ_bulletin.do",
                    "source_tag": "cuk_about_resource_guides",
                    "last_synced_at": "2026-03-22T00:00:00+09:00",
                }
            ],
        )

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_about_resource_guides",
            {"topic": "university_bulletin", "limit": 5},
        )
        resource_result = await mcp.read_resource("songsim://about-resource-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())
    tool_payload = _tool_payloads(tool_result)[0]
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["topic"] == "university_bulletin"
    assert tool_payload["guide_summary"] == "가톨릭대학교 요람 PDF 안내"
    assert resource_payload[0]["source_tag"] == "cuk_about_resource_guides"

    clear_settings_cache()
