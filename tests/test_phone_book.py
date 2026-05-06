from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from songsim_campus.db import connection, init_db
from songsim_campus.ingest.official_sources import PhoneBookSource
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    refresh_phone_book_entries_from_source,
    search_phone_book_entries,
    sync_official_snapshot,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")
PHONE_BOOK_URL = "https://www.catholic.ac.kr/ko/about/phone_book.do"


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _record(call_order: list[str], name: str):
    def inner(*_args, **_kwargs):
        call_order.append(name)
        return []

    return inner


def _phone_book_row(
    *,
    department: str,
    tasks: str,
    phone: str,
    source_tag: str = "cuk_phone_book",
) -> dict[str, str]:
    return {
        "department": department,
        "tasks": tasks,
        "phone": phone,
        "source_url": PHONE_BOOK_URL,
        "source_tag": source_tag,
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


def test_phone_book_source_parser_extracts_expected_static_rows() -> None:
    rows = PhoneBookSource().parse(
        _fixture("phone_book.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert len(rows) == 36
    assert rows[0]["department"] == "교목실"
    assert rows[0]["tasks"] == "미사, 세례, 성경공부"
    assert rows[0]["phone"] == "4620"

    health = next(row for row in rows if row["department"] == "보건실")
    assert health["tasks"] == "보건, 약, 학생상해보험"
    assert health["phone"] == "4126"
    assert health["source_tag"] == "cuk_phone_book"
    assert health["source_url"] == PHONE_BOOK_URL

    it_support = next(row for row in rows if row["department"] == "정보통신지원팀")
    assert it_support["tasks"] == "개인정보, 네트워크, 트리니티"
    assert it_support["phone"] == "4160 / 02-740-9749 (웹메일)"

    student_support = next(row for row in rows if row["department"] == "학생지원팀")
    assert "유실물" in student_support["tasks"]

    dorm = next(row for row in rows if row["department"] == "기숙사운영팀")
    assert dorm["phone"] == "4661"


def test_phone_book_entries_refresh_replace_and_search(app_env):
    init_db()

    class FakePhoneBookSource:
        def __init__(self, rows: list[dict[str, str]]):
            self.rows = rows

        def fetch(self) -> str:
            return "<phone-book />"

        def parse(self, html: str, *, fetched_at: str):
            assert html == "<phone-book />"
            return [{**row, "last_synced_at": fetched_at} for row in self.rows]

    with connection() as conn:
        refresh_phone_book_entries_from_source(
            conn,
            source=FakePhoneBookSource(
                [
                    _phone_book_row(
                        department="학생지원팀",
                        tasks="장학, 유실물",
                        phone="4732",
                    ),
                    _phone_book_row(
                        department="정보통신지원팀",
                        tasks="개인정보, 네트워크, 트리니티",
                        phone="4160 / 02-740-9749 (웹메일)",
                    ),
                    _phone_book_row(
                        department="보건실",
                        tasks="보건, 약, 학생상해보험",
                        phone="4126",
                    ),
                    _phone_book_row(
                        department="기숙사운영팀",
                        tasks="기숙사 운영",
                        phone="4661",
                    ),
                    _phone_book_row(
                        department="학사지원팀",
                        tasks="수업, 성적, 학적, 학점",
                        phone="6522",
                    ),
                ]
            ),
        )
        all_entries = search_phone_book_entries(conn, query=None, limit=20)
        health = search_phone_book_entries(conn, query="보건실", limit=20)
        trinity = search_phone_book_entries(conn, query="트리니티", limit=20)
        lost_found = search_phone_book_entries(conn, query="유실물", limit=20)
        dorm = search_phone_book_entries(conn, query="기숙사 운영팀", limit=20)
        phone_match = search_phone_book_entries(conn, query="9749", limit=20)

        refresh_phone_book_entries_from_source(
            conn,
            source=FakePhoneBookSource(
                [
                    _phone_book_row(
                        department="보건실",
                        tasks="보건, 약, 학생상해보험",
                        phone="4126",
                    ),
                    _phone_book_row(
                        department="학생지원팀",
                        tasks="장학, 유실물",
                        phone="4732",
                    ),
                ]
            ),
        )
        replaced_entries = search_phone_book_entries(conn, query=None, limit=20)

    assert [item.department for item in all_entries] == [
        "기숙사운영팀",
        "보건실",
        "정보통신지원팀",
        "학사지원팀",
        "학생지원팀",
    ]
    assert [item.department for item in health] == ["보건실"]
    assert [item.department for item in trinity] == ["정보통신지원팀"]
    assert [item.department for item in lost_found] == ["학생지원팀"]
    assert [item.department for item in dorm] == ["기숙사운영팀"]
    assert [item.department for item in phone_match] == ["정보통신지원팀"]
    assert [item.department for item in replaced_entries] == ["보건실", "학생지원팀"]


def test_phone_book_http_and_mcp_surfaces(client, app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()

    class FakePhoneBookSource:
        def fetch(self) -> str:
            return "<phone-book />"

        def parse(self, html: str, *, fetched_at: str):
            assert html == "<phone-book />"
            return [
                {
                    **_phone_book_row(
                        department="보건실",
                        tasks="보건, 약, 학생상해보험",
                        phone="4126",
                    ),
                    "last_synced_at": fetched_at,
                },
                {
                    **_phone_book_row(
                        department="정보통신지원팀",
                        tasks="개인정보, 네트워크, 트리니티",
                        phone="4160 / 02-740-9749 (웹메일)",
                    ),
                    "last_synced_at": fetched_at,
                },
                {
                    **_phone_book_row(
                        department="학생지원팀",
                        tasks=(
                            "장학, 교내인턴십, 증명발급, 총학생회, 동아리, 장애학생지원센터, "
                            "유실물"
                        ),
                        phone="4732",
                    ),
                    "last_synced_at": fetched_at,
                },
            ]

    with connection() as conn:
        refresh_phone_book_entries_from_source(conn, source=FakePhoneBookSource())

    response = client.get("/phone-book", params={"query": "트리니티", "limit": 5})
    assert response.status_code == 200
    http_payload = response.json()
    assert http_payload == [
        {
            "id": 2,
            "department": "정보통신지원팀",
            "tasks": "개인정보, 네트워크, 트리니티",
            "phone": "4160 / 02-740-9749 (웹메일)",
            "source_url": PHONE_BOOK_URL,
            "source_tag": "cuk_phone_book",
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
            "tool_search_phone_book",
            {"query": "유실물", "limit": 5},
        )
        resource_result = await mcp.read_resource("songsim://phone-book")
        return (
            {tool.name: tool.model_dump(by_alias=True) for tool in tools},
            {str(resource.uri) for resource in resources},
            json.loads(tool_result[0].text),
            json.loads(list(resource_result)[0].content),
        )

    tool_payloads, resource_uris, tool_payload, resource_payload = asyncio.run(main())
    clear_settings_cache()

    assert "tool_search_phone_book" in tool_payloads
    assert "songsim://phone-book" in resource_uris
    assert "보건실" in tool_payloads["tool_search_phone_book"]["description"]
    assert "트리니티" in (
        tool_payloads["tool_search_phone_book"]["inputSchema"]["properties"]["query"][
            "description"
        ]
    )
    assert tool_payload["department"] == "학생지원팀"
    assert [item["department"] for item in resource_payload] == [
        "보건실",
        "정보통신지원팀",
        "학생지원팀",
    ]


def test_sync_official_snapshot_includes_phone_book_entries(app_env, monkeypatch):
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
        "songsim_campus.services.refresh_academic_milestone_guides_from_source",
        _record(call_order, "academic_milestone_guides"),
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
        "songsim_campus.services.refresh_phone_book_entries_from_source",
        _record(call_order, "phone_book_entries"),
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
        "songsim_campus.services.refresh_dormitory_guides_from_source",
        _record(call_order, "dormitory_guides"),
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_scholarship_guides_from_source",
        _record(call_order, "scholarship"),
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

    assert "phone_book_entries" in summary
    assert "phone_book_entries" in call_order
    assert "about_resource_guides" in summary
    assert "about_resource_guides" in call_order
    assert "service_policy_guides" in summary
    assert "service_policy_guides" in call_order
    assert "newsroom_posts" in summary
    assert "newsroom_posts" in call_order
    assert "campus_life_support_guides" in summary
    assert "campus_life_support_guides" in call_order
    assert "pc_software_entries" in summary
    assert "pc_software_entries" in call_order
    assert "student_exchange_partners" in summary
    assert "student_exchange_partners" in call_order
    assert "dormitory_guides" in summary
    assert "dormitory_guides" in call_order
