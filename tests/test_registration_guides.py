from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from songsim_campus.db import connection, init_db
from songsim_campus.ingest.official_sources import (
    RegistrationBillLookupGuideSource,
    RegistrationPaymentAndReturnGuideSource,
    RegistrationPaymentByStudentGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_registration_guides,
    refresh_registration_guides_from_source,
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


def test_registration_guide_parsers_extract_expected_sections():
    rows = RegistrationBillLookupGuideSource().parse(
        _fixture("tuition_fee_payment_schedule.html"),
        fetched_at="2026-03-18T00:00:00+09:00",
    )
    assert {row["title"] for row in rows} == {"2025년도 1학기", "2025년도 2학기"}
    first = next(row for row in rows if row["title"] == "2025년도 1학기")
    assert first["topic"] == "bill_lookup"
    assert first["links"][0]["label"] == "등록금고지서"

    rows = RegistrationPaymentAndReturnGuideSource().parse(
        _fixture("tuition_payment_and_returning.html"),
        fetched_at="2026-03-18T00:00:00+09:00",
    )
    refund = next(row for row in rows if row["title"] == "등록금 반환기준")
    assert refund["topic"] == "payment_and_return"
    assert any("등록금의 5/6" in step for step in refund["steps"])

    rows = RegistrationPaymentByStudentGuideSource().parse(
        _fixture("tuition_payment_by_student.html"),
        fetched_at="2026-03-18T00:00:00+09:00",
    )
    titles = {row["title"] for row in rows}
    assert {"초과학기생", "전액장학생 (실납입액이 0원인 학생)"} <= titles


def test_registration_guides_refresh_and_filter(app_env):
    init_db()

    class RegistrationSource:
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
                    "links": [{"label": self.title, "url": "https://www.catholic.ac.kr/ko/support/registration.do"}],
                    "source_url": "https://www.catholic.ac.kr/ko/support/registration.do",
                    "source_tag": "cuk_registration_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    with connection() as conn:
        guides = refresh_registration_guides_from_source(
            conn,
            sources=[
                RegistrationSource("bill_lookup", "2025년도 1학기"),
                RegistrationSource("payment_and_return", "등록금 반환기준"),
                RegistrationSource("payment_by_student", "초과학기생"),
            ],
        )
        filtered = list_registration_guides(conn, topic="payment_and_return")

    assert [guide.topic for guide in guides] == [
        "bill_lookup",
        "payment_and_return",
        "payment_by_student",
    ]
    assert [guide.title for guide in filtered] == ["등록금 반환기준"]


def test_registration_guides_http_and_mcp_surfaces(client, app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()

    class RegistrationSource:
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
                    "links": [{"label": self.title, "url": "https://www.catholic.ac.kr/ko/support/registration.do"}],
                    "source_url": "https://www.catholic.ac.kr/ko/support/registration.do",
                    "source_tag": "cuk_registration_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    with connection() as conn:
        refresh_registration_guides_from_source(
            conn,
            sources=[
                RegistrationSource("bill_lookup", "2025년도 1학기"),
                RegistrationSource("payment_and_return", "등록금 반환기준"),
                RegistrationSource("payment_by_student", "초과학기생"),
            ],
        )

    response = client.get("/registration-guides", params={"topic": "payment_and_return"})
    assert response.status_code == 200
    http_payload = response.json()
    assert http_payload == [
        {
            "id": 2,
            "topic": "payment_and_return",
            "title": "등록금 반환기준",
            "summary": "등록금 반환기준 요약",
            "steps": ["등록금 반환기준 단계"],
            "links": [
                {
                    "label": "등록금 반환기준",
                    "url": "https://www.catholic.ac.kr/ko/support/registration.do",
                }
            ],
            "source_url": "https://www.catholic.ac.kr/ko/support/registration.do",
            "source_tag": "cuk_registration_guides",
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
            "tool_list_registration_guides",
            {"topic": "payment_and_return", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://registration-guide")
        return (
            {tool.name: tool.model_dump(by_alias=True) for tool in tools},
            [str(resource.uri) for resource in resources],
            json.loads(tool_result[0].text),
            json.loads(list(resource_result)[0].content),
        )

    tool_payloads, resource_uris, payload, resource_payload = asyncio.run(main())

    clear_settings_cache()

    assert "tool_list_registration_guides" in tool_payloads
    assert "songsim://registration-guide" in resource_uris
    assert "등록금 반환 기준" in tool_payloads["tool_list_registration_guides"]["description"]
    assert "payment_and_return" in (
        tool_payloads["tool_list_registration_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert [item["topic"] for item in resource_payload] == [
        "bill_lookup",
        "payment_and_return",
        "payment_by_student",
    ]
    payment_and_return_resource = next(
        item for item in resource_payload if item["topic"] == "payment_and_return"
    )
    assert payment_and_return_resource == http_payload[0]
    assert payload == {
        "id": 2,
        "topic": "payment_and_return",
        "title": "등록금 반환기준",
        "summary": "등록금 반환기준 요약",
        "guide_summary": "등록금 반환기준 요약",
        "steps": ["등록금 반환기준 단계"],
        "links": [
            {
                "label": "등록금 반환기준",
                "url": "https://www.catholic.ac.kr/ko/support/registration.do",
            }
        ],
        "source_url": "https://www.catholic.ac.kr/ko/support/registration.do",
        "source_tag": "cuk_registration_guides",
        "last_synced_at": payload["last_synced_at"],
    }
    assert resource_payload[0] == {
        "id": 1,
        "topic": "bill_lookup",
        "title": "2025년도 1학기",
        "summary": "2025년도 1학기 요약",
        "steps": ["2025년도 1학기 단계"],
        "links": [
            {
                "label": "2025년도 1학기",
                "url": "https://www.catholic.ac.kr/ko/support/registration.do",
            }
        ],
        "source_url": "https://www.catholic.ac.kr/ko/support/registration.do",
        "source_tag": "cuk_registration_guides",
        "last_synced_at": resource_payload[0]["last_synced_at"],
    }


def test_sync_official_snapshot_includes_registration_guides(app_env, monkeypatch):
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
        "songsim_campus.services.refresh_about_resource_guides_from_source",
        _record(call_order, "about_resource_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_service_policy_guides_from_source",
        _record(call_order, "service_policy_guides"),
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

    assert "registration_guides" in summary
    assert "registration_guides" in call_order
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
