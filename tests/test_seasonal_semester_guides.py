from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from songsim_campus.db import connection, init_db
from songsim_campus.ingest.official_sources import SeasonalSemesterGuideSource
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    InvalidRequestError,
    list_seasonal_semester_guides,
    refresh_seasonal_semester_guides_from_source,
    sync_official_snapshot,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _record(call_order: list[str], name: str):
    def inner(*_args, **_kwargs):
        call_order.append(name)
        return []

    return inner


def test_seasonal_semester_guide_parser_extracts_expected_sections():
    rows = SeasonalSemesterGuideSource().parse(
        _fixture("class_summer_winter.html"),
        fetched_at="2026-03-19T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["신청대상", "학점 제한", "신청 시기", "신청절차"]
    eligibility = next(row for row in rows if row["title"] == "신청대상")
    assert eligibility["topic"] == "seasonal_semester"
    assert eligibility["source_tag"] == "cuk_seasonal_semester_guides"
    assert eligibility["summary"] == "재학생(휴학생 포함)"
    assert eligibility["steps"] == [
        "재학생(휴학생 포함)",
        "수료생은 계절학기 수강불가",
        (
            "휴학생 유의 사항: 휴학생은 본교 성심교정에 개설되는 계절학기 수업만 "
            "수강이 가능(휴학상태에서 타 대학 학점교류 불가)"
        ),
        (
            "휴학생 유의 사항: 휴학생이 계절학기 수강을 통해 졸업요건이 충족되더라도 "
            "휴학 신분으로 졸업하는 것은 불가능하며, 반드시 복학 후 한 학기 이상 "
            "이수(등록)한 후에 졸업 가능"
        ),
    ]
    assert not any(step.startswith("신청대상 ") for step in eligibility["steps"])

    credit_limit = next(row for row in rows if row["title"] == "학점 제한")
    assert credit_limit["summary"] == "학기당 6학점까지만 신청 가능"
    assert credit_limit["steps"] == [
        "학기당 6학점까지만 신청 가능",
        (
            "국제언어교육원 학점인정 교과목 및 학점교류(계절학기) 등을 통하여 "
            "취득한 학점수를 포함하여 6학점 이내에서 신청가능"
        ),
    ]

    timing = next(row for row in rows if row["title"] == "신청 시기")
    assert timing["summary"] == "매학기 본교 홈페이지에 계절학기 일정 공고"
    assert timing["steps"] == ["매학기 본교 홈페이지에 계절학기 일정 공고"]

    procedure = next(row for row in rows if row["title"] == "신청절차")
    assert procedure["summary"] == (
        "개설 교과목 확정 : 재학생을 대상으로 개설 희망과목 수요조사 및 본 "
        "수강신청을 실시하여 개설 교과목을 결정함."
    )
    assert procedure["steps"] == [
        (
            "개설 교과목 확정 : 재학생을 대상으로 개설 희망과목 수요조사 및 본 "
            "수강신청을 실시하여 개설 교과목을 결정함."
        ),
        (
            "수강신청 : 수요조사 결과 개설 교과목으로 확정된 과목에 대해, "
            "공지 된 신청기간동안 TRINITY에 접속하여 신청"
        ),
        "수업료 미납 시 수강신청은 무효 처리됨",
    ]


def test_seasonal_semester_guides_refresh_and_filter(app_env):
    init_db()

    class SeasonalSource:
        def __init__(self, title: str):
            self.title = title

        def fetch(self):
            return f"<{self.title}></{self.title}>"

        def parse(self, html: str, *, fetched_at: str):
            assert html == f"<{self.title}></{self.title}>"
            return [
                {
                    "topic": "seasonal_semester",
                    "title": self.title,
                    "summary": f"{self.title} 요약",
                    "steps": [f"{self.title} 단계"],
                    "links": [
                        {
                            "label": self.title,
                            "url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
                    "source_tag": "cuk_seasonal_semester_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    with connection() as conn:
        guides = refresh_seasonal_semester_guides_from_source(
            conn,
            sources=[
                SeasonalSource("신청대상"),
                SeasonalSource("학점 제한"),
                SeasonalSource("신청 시기"),
                SeasonalSource("신청절차"),
            ],
        )
        filtered = list_seasonal_semester_guides(conn, topic="seasonal_semester")

    assert [guide.topic for guide in guides] == [
        "seasonal_semester",
        "seasonal_semester",
        "seasonal_semester",
        "seasonal_semester",
    ]
    assert [guide.title for guide in filtered] == [
        "신청대상",
        "학점 제한",
        "신청 시기",
        "신청절차",
    ]


def test_seasonal_semester_guides_reject_invalid_topic(app_env):
    init_db()

    with connection() as conn:
        with pytest.raises(InvalidRequestError):
            list_seasonal_semester_guides(conn, topic="unknown_topic")


def test_seasonal_semester_guides_http_and_mcp_surfaces(client, app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()

    class SeasonalSource:
        def __init__(self, title: str):
            self.title = title

        def fetch(self):
            return f"<{self.title}></{self.title}>"

        def parse(self, html: str, *, fetched_at: str):
            assert html == f"<{self.title}></{self.title}>"
            return [
                {
                    "topic": "seasonal_semester",
                    "title": self.title,
                    "summary": f"{self.title} 요약",
                    "steps": [f"{self.title} 단계"],
                    "links": [
                        {
                            "label": self.title,
                            "url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
                    "source_tag": "cuk_seasonal_semester_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    with connection() as conn:
        refresh_seasonal_semester_guides_from_source(
            conn,
            sources=[
                SeasonalSource("신청대상"),
                SeasonalSource("학점 제한"),
                SeasonalSource("신청 시기"),
                SeasonalSource("신청절차"),
            ],
        )

    response = client.get("/seasonal-semester-guides", params={"topic": "seasonal_semester"})
    assert response.status_code == 200
    http_payload = response.json()
    assert [item["title"] for item in http_payload] == [
        "신청대상",
        "학점 제한",
        "신청 시기",
        "신청절차",
    ]
    assert http_payload[0] == {
        "id": 1,
        "topic": "seasonal_semester",
        "title": "신청대상",
        "summary": "신청대상 요약",
        "steps": ["신청대상 단계"],
        "links": [
            {
                "label": "신청대상",
                "url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
            }
        ],
        "source_url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
        "source_tag": "cuk_seasonal_semester_guides",
        "last_synced_at": http_payload[0]["last_synced_at"],
    }

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        tool_result = await mcp.call_tool(
            "tool_list_seasonal_semester_guides",
            {"topic": "seasonal_semester", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://seasonal-semester-guide")
        return (
            {tool.name: tool.model_dump(by_alias=True) for tool in tools},
            [str(resource.uri) for resource in resources],
            json.loads(tool_result[0].text),
            json.loads(list(resource_result)[0].content),
        )

    tool_payloads, resource_uris, payload, resource_payload = asyncio.run(main())
    clear_settings_cache()

    assert "tool_list_seasonal_semester_guides" in tool_payloads
    assert "songsim://seasonal-semester-guide" in resource_uris
    assert "계절학기" in tool_payloads["tool_list_seasonal_semester_guides"]["description"]
    assert "seasonal_semester" in (
        tool_payloads["tool_list_seasonal_semester_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert [item["topic"] for item in resource_payload] == [
        "seasonal_semester",
        "seasonal_semester",
        "seasonal_semester",
        "seasonal_semester",
    ]
    assert payload == {
        "id": 1,
        "topic": "seasonal_semester",
        "title": "신청대상",
        "summary": "신청대상 요약",
        "guide_summary": "신청대상 요약",
        "steps": ["신청대상 단계"],
        "links": [
            {
                "label": "신청대상",
                "url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
            }
        ],
        "source_url": "https://www.catholic.ac.kr/ko/support/class_summer_winter.do",
        "source_tag": "cuk_seasonal_semester_guides",
        "last_synced_at": payload["last_synced_at"],
    }
    assert resource_payload[0] == http_payload[0]


def test_sync_official_snapshot_includes_seasonal_semester_guides(app_env, monkeypatch):
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
        "songsim_campus.services.refresh_registration_guides_from_source",
        _record(call_order, "registration_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_class_guides_from_source",
        _record(call_order, "class_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_seasonal_semester_guides_from_source",
        _record(call_order, "seasonal_semester_guides"),
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
        "songsim_campus.services.refresh_scholarship_guides_from_source",
        _record(call_order, "scholarship"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_dormitory_guides_from_source",
        _record(call_order, "dormitory_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_about_resource_guides_from_source",
        _record(call_order, "about_resource_guides"),
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

    assert "seasonal_semester_guides" in summary
    assert "seasonal_semester_guides" in call_order
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
