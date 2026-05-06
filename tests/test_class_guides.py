from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from songsim_campus.db import connection, init_db
from songsim_campus.ingest.official_sources import (
    ClassCourseCancellationGuideSource,
    ClassCourseEvaluationGuideSource,
    ClassExcusedAbsenceGuideSource,
    ClassForeignLanguageRequirementGuideSource,
    ClassRegistrationChangeGuideSource,
    ClassRetakeGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    InvalidRequestError,
    list_class_guides,
    refresh_class_guides_from_source,
    sync_official_snapshot,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_class_guide_parsers_extract_expected_sections():
    rows = ClassRegistrationChangeGuideSource().parse(
        _fixture("register_for_class.html"),
        fetched_at="2026-03-19T00:00:00+09:00",
    )
    assert {row["title"] for row in rows} >= {
        "수강신청 · 변경기간",
        "수강신청 · 변경방법",
        "유의 사항",
    }
    change_period = next(row for row in rows if row["title"] == "수강신청 · 변경기간")
    assert change_period["topic"] == "registration_change"
    assert change_period["source_tag"] == "cuk_class_guides"
    assert change_period["summary"] == "매학기 본교 및 학사정보 홈페이지에 일정 공고"
    change_method = next(row for row in rows if row["title"] == "수강신청 · 변경방법")
    assert any("TRINITY" in step for step in change_method["steps"])

    rows = ClassRetakeGuideSource().parse(
        _fixture("re_register_for_class.html"),
        fetched_at="2026-03-19T00:00:00+09:00",
    )
    assert {row["title"] for row in rows} >= {
        "대상 교과목",
        "재수강 인정 교과목",
        "기준학점",
        "재수강 연도, 학기 및 성적",
        "유의 사항",
    }
    retake = next(row for row in rows if row["title"] == "대상 교과목")
    assert retake["topic"] == "retake"
    assert any("학기당 2과목 이내" in step for step in retake["steps"])

    rows = ClassCourseCancellationGuideSource().parse(
        _fixture("cancellation_of_class.html"),
        fetched_at="2026-03-19T00:00:00+09:00",
    )
    assert {row["title"] for row in rows} == {
        "수강과목 취소 기간",
        "수강과목 취소 절차",
    }
    assert rows[0]["topic"] == "course_cancellation"

    rows = ClassCourseEvaluationGuideSource().parse(
        _fixture("course_evaluation.html"),
        fetched_at="2026-03-19T00:00:00+09:00",
    )
    assert {row["title"] for row in rows} == {
        "수업평가 방법",
        "수업평가 기간",
    }
    assert rows[0]["topic"] == "course_evaluation"
    evaluation_method = next(row for row in rows if row["title"] == "수업평가 방법")
    assert "강의평가 메뉴" in evaluation_method["summary"]

    rows = ClassExcusedAbsenceGuideSource().parse(
        _fixture("absence_notification.html"),
        fetched_at="2026-03-19T00:00:00+09:00",
    )
    assert {row["title"] for row in rows} == {
        "공결허용기준",
        "신청방법",
    }
    excused = next(row for row in rows if row["title"] == "공결허용기준")
    assert excused["topic"] == "excused_absence"
    assert any("직계존속 및 배우자 사망" in step for step in excused["steps"])
    assert any("공결허용일수" in step for step in excused["steps"])
    application = next(row for row in rows if row["title"] == "신청방법")
    assert any(item["label"] == "공결허가원" for item in application["links"])

    rows = ClassForeignLanguageRequirementGuideSource().parse(
        _fixture("completion_requirements_for_foreign_language_2024.html"),
        fetched_at="2026-03-19T00:00:00+09:00",
    )
    assert {row["title"] for row in rows} >= {
        "외국어강의 인정 교과목",
        "주요내용",
        "교양부분 외국어강의 이수 의무",
        "학과(부)별 외국어강의 최소이수 학점",
        "비고사항",
        "FAQ",
    }
    faq = next(row for row in rows if row["title"] == "FAQ")
    assert faq["topic"] == "foreign_language_requirement"
    assert any("충족됩니다" in step for step in faq["steps"])


def _record(call_order: list[str], name: str):
    def inner(*_args, **_kwargs):
        call_order.append(name)
        return []

    return inner


def test_class_guides_refresh_and_filter(app_env):
    init_db()

    class ClassSource:
        def __init__(self, topic: str, title: str):
            self.topic = topic
            self.title = title

        def fetch(self):
            return f"<{self.topic}></{self.topic}>"

        def parse(self, html: str, *, fetched_at: str):
            assert html == f"<{self.topic}></{self.topic}>"
            return [
                {
                    "topic": self.topic,
                    "title": self.title,
                    "summary": f"{self.title} 요약",
                    "steps": [f"{self.title} 단계"],
                    "links": [{"label": self.title, "url": "https://www.catholic.ac.kr/ko/support/class.do"}],
                    "source_url": "https://www.catholic.ac.kr/ko/support/class.do",
                    "source_tag": "cuk_class_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    with connection() as conn:
        guides = refresh_class_guides_from_source(
            conn,
            sources=[
                ClassSource("registration_change", "수강신청 · 변경기간"),
                ClassSource("course_evaluation", "수업평가 방법"),
                ClassSource("excused_absence", "공결허용기준"),
            ],
        )
        filtered = list_class_guides(conn, topic="course_evaluation")

    assert [guide.topic for guide in guides] == [
        "registration_change",
        "course_evaluation",
        "excused_absence",
    ]
    assert [guide.title for guide in filtered] == ["수업평가 방법"]


def test_class_guides_reject_invalid_topic(app_env):
    init_db()

    with connection() as conn:
        with pytest.raises(InvalidRequestError):
            list_class_guides(conn, topic="unknown_topic")


def test_class_guides_http_and_mcp_surfaces(client, app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()

    class ClassSource:
        def __init__(self, topic: str, title: str):
            self.topic = topic
            self.title = title

        def fetch(self):
            return f"<{self.topic}></{self.topic}>"

        def parse(self, html: str, *, fetched_at: str):
            assert html == f"<{self.topic}></{self.topic}>"
            return [
                {
                    "topic": self.topic,
                    "title": self.title,
                    "summary": f"{self.title} 요약",
                    "steps": [f"{self.title} 단계"],
                    "links": [{"label": self.title, "url": "https://www.catholic.ac.kr/ko/support/class.do"}],
                    "source_url": "https://www.catholic.ac.kr/ko/support/class.do",
                    "source_tag": "cuk_class_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    with connection() as conn:
        refresh_class_guides_from_source(
            conn,
            sources=[
                ClassSource("registration_change", "수강신청 · 변경기간"),
                ClassSource("course_evaluation", "수업평가 방법"),
                ClassSource("foreign_language_requirement", "외국어강의 인정 교과목"),
            ],
        )

    response = client.get("/class-guides", params={"topic": "course_evaluation"})
    assert response.status_code == 200
    http_payload = response.json()
    assert http_payload == [
        {
            "id": 2,
            "topic": "course_evaluation",
            "title": "수업평가 방법",
            "summary": "수업평가 방법 요약",
            "steps": ["수업평가 방법 단계"],
            "links": [
                {
                    "label": "수업평가 방법",
                    "url": "https://www.catholic.ac.kr/ko/support/class.do",
                }
            ],
            "source_url": "https://www.catholic.ac.kr/ko/support/class.do",
            "source_tag": "cuk_class_guides",
            "last_synced_at": http_payload[0]["last_synced_at"],
        }
    ]

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        tool_result = await mcp.call_tool(
            "tool_list_class_guides",
            {"topic": "course_evaluation", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://class-guide")
        return (
            {tool.name: tool.model_dump(by_alias=True) for tool in tools},
            [str(resource.uri) for resource in resources],
            json.loads(tool_result[0].text),
            json.loads(list(resource_result)[0].content),
        )

    tool_payloads, resource_uris, payload, resource_payload = asyncio.run(main())
    clear_settings_cache()

    assert "tool_list_class_guides" in tool_payloads
    assert "songsim://class-guide" in resource_uris
    assert "수업평가" in tool_payloads["tool_list_class_guides"]["description"]
    assert "course_evaluation" in (
        tool_payloads["tool_list_class_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert [item["topic"] for item in resource_payload] == [
        "registration_change",
        "course_evaluation",
        "foreign_language_requirement",
    ]
    course_evaluation_resource = next(
        item for item in resource_payload if item["topic"] == "course_evaluation"
    )
    assert course_evaluation_resource == http_payload[0]
    assert payload == {
        "id": 2,
        "topic": "course_evaluation",
        "title": "수업평가 방법",
        "summary": "수업평가 방법 요약",
        "guide_summary": "수업평가 방법 요약",
        "steps": ["수업평가 방법 단계"],
        "links": [
            {
                "label": "수업평가 방법",
                "url": "https://www.catholic.ac.kr/ko/support/class.do",
            }
        ],
        "source_url": "https://www.catholic.ac.kr/ko/support/class.do",
        "source_tag": "cuk_class_guides",
        "last_synced_at": payload["last_synced_at"],
    }


def test_sync_official_snapshot_includes_class_guides(app_env, monkeypatch):
    call_order: list[str] = []

    monkeypatch.setattr(
        "songsim_campus.services.refresh_places_from_campus_map",
        _record(call_order, "places"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_campus_facilities_from_source",
        _record(call_order, "campus_facilities"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_library_hours_from_library_page",
        _record(call_order, "library"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_facility_hours_from_facilities_page",
        _record(call_order, "facility_hours"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_campus_dining_menus_from_facilities_page",
        _record(call_order, "dining"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_courses_from_subject_search",
        _record(call_order, "courses"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_notices_from_notice_board",
        _record(call_order, "notices"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_academic_calendar_from_source",
        _record(call_order, "calendar"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_class_guides_from_source",
        _record(call_order, "class_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_registration_guides_from_source",
        _record(call_order, "registration_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_certificate_guides_from_certificate_page",
        _record(call_order, "certificate"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_leave_of_absence_guides_from_source",
        _record(call_order, "leave"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_academic_status_guides_from_source",
        _record(call_order, "status"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_scholarship_guides_from_source",
        _record(call_order, "scholarship"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_campus_life_support_guides_from_source",
        _record(call_order, "campus_life_support_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_pc_software_entries_from_source",
        _record(call_order, "pc_software_entries"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_dormitory_guides_from_source",
        _record(call_order, "dormitory_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_student_activity_guides_from_source",
        _record(call_order, "student_activity_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_about_resource_guides_from_source",
        _record(call_order, "about_resource_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_service_policy_guides_from_source",
        _record(call_order, "service_policy_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_newsroom_posts_from_source",
        _record(call_order, "newsroom_posts"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_student_exchange_partners_from_source",
        _record(call_order, "student_exchange_partners"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_academic_support_guides_from_source",
        _record(call_order, "support"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_wifi_guides_from_source",
        _record(call_order, "wifi"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_transport_guides_from_location_page",
        _record(call_order, "transport"),
    )

    init_db()
    with connection() as conn:
        summary = sync_official_snapshot(conn, year=2026, semester=1, notice_pages=1)

    assert "class_guides" in summary
    assert "class_guides" in call_order
    assert "campus_life_support_guides" in summary
    assert "campus_life_support_guides" in call_order
    assert "pc_software_entries" in summary
    assert "pc_software_entries" in call_order
    assert "student_exchange_partners" in summary
    assert "student_exchange_partners" in call_order
    assert "dormitory_guides" in summary
    assert "dormitory_guides" in call_order
    assert "about_resource_guides" in summary
    assert "about_resource_guides" in call_order
    assert "service_policy_guides" in summary
    assert "service_policy_guides" in call_order
    assert "newsroom_posts" in summary
    assert "newsroom_posts" in call_order
