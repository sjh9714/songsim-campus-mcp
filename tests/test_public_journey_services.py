from __future__ import annotations

from datetime import date

import pytest

from songsim_campus import repo
from songsim_campus.db import connection, init_db
from songsim_campus.services import (
    campus_life_help,
    explain_academic_process,
    find_campus_place,
    find_study_resource,
    get_public_status_snapshot,
    get_today_campus_updates,
)

SYNCED_AT = "2026-05-14T09:10:00+09:00"


@pytest.fixture()
def initialized_db(app_env):
    init_db()


def test_get_today_campus_updates_groups_notices_and_calendar(initialized_db):
    with connection() as conn:
        repo.replace_notices(
            conn,
            [
                {
                    "title": "2026학년도 1학기 수강신청 변경 안내",
                    "category": "academic",
                    "published_at": "2026-03-02",
                    "summary": "수강신청 변경 기간 안내",
                    "labels": ["학사"],
                    "source_url": "https://www.catholic.ac.kr/notice/1",
                    "source_tag": "cuk_notices",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )
        repo.replace_academic_calendar(
            conn,
            [
                {
                    "academic_year": 2026,
                    "title": "중간고사",
                    "start_date": "2026-04-20",
                    "end_date": "2026-04-24",
                    "campuses": ["성심"],
                    "source_url": "https://www.catholic.ac.kr/calendar",
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )

        result = get_today_campus_updates(conn, at=date(2026, 4, 1), limit=5)

    section_names = {section.name for section in result.sections}
    assert result.journey == "today_campus_updates"
    assert "latest_notices" in section_names
    assert "academic_calendar" in section_names
    assert any(
        item["title"] == "2026학년도 1학기 수강신청 변경 안내"
        for item in result.sections[0].items
    )


def test_find_campus_place_wraps_place_search_with_next_steps(initialized_db):
    with connection() as conn:
        repo.replace_places(
            conn,
            [
                {
                    "slug": "student-union",
                    "name": "학생회관",
                    "canonical_name": "학생회관",
                    "category": "building",
                    "aliases": ["학생식당"],
                    "description": "학생식당과 편의시설이 있는 건물",
                    "latitude": 37.0,
                    "longitude": 127.0,
                    "source_tag": "cuk_campus_map",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )

        result = find_campus_place(conn, query="학생회관", limit=3)

    assert result.journey == "find_campus_place"
    assert result.query == "학생회관"
    assert result.sections[0].name == "places"
    assert result.sections[0].items[0]["slug"] == "student-union"
    assert "tool_get_place" in " ".join(result.next_steps)


def test_explain_academic_process_routes_across_official_guides(initialized_db):
    with connection() as conn:
        repo.replace_registration_guides(
            conn,
            [
                {
                    "topic": "payment_and_return",
                    "title": "등록금 반환 기준",
                    "summary": "등록금 반환 기준과 납부 안내",
                    "steps": ["개강 전후 기준에 따라 반환"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/registration",
                    "source_tag": "cuk_registration_guides",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )
        repo.replace_class_guides(
            conn,
            [
                {
                    "topic": "excused_absence",
                    "title": "공결 신청",
                    "summary": "공결 신청 방법",
                    "steps": ["신청서 제출"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/class",
                    "source_tag": "cuk_class_guides",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )

        result = explain_academic_process(conn, query="등록금 반환 기준", limit=5)

    assert result.journey == "explain_academic_process"
    assert result.sections[0].name == "registration_guides"
    assert result.sections[0].items[0]["topic"] == "payment_and_return"
    assert "uPortal" in " ".join(result.out_of_scope)


def test_find_study_resource_combines_library_pc_wifi_and_optional_empty_rooms(initialized_db):
    with connection() as conn:
        repo.replace_pc_software_entries(
            conn,
            [
                {
                    "room": "미카엘관 M101",
                    "pc_count": 30,
                    "software_list": ["SPSS", "Visual Studio"],
                    "source_url": "https://www.catholic.ac.kr/software",
                    "source_tag": "cuk_pc_software",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )
        repo.replace_wifi_guides(
            conn,
            [
                {
                    "building_name": "니콜스관",
                    "ssids": ["catholic_univ"],
                    "steps": ["보안키 입력 후 접속"],
                    "source_url": "https://www.catholic.ac.kr/wifi",
                    "source_tag": "cuk_wifi_guides",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )

        result = find_study_resource(conn, query="SPSS", limit=5)

    section_names = {section.name for section in result.sections}
    assert result.journey == "find_study_resource"
    assert "pc_software" in section_names
    assert "wifi_guides" in section_names
    assert any(
        "SPSS" in item.get("software_list", [])
        for section in result.sections
        for item in section.items
    )


def test_campus_life_help_combines_support_dormitory_and_activity_guides(initialized_db):
    with connection() as conn:
        repo.replace_campus_life_support_guides(
            conn,
            [
                {
                    "topic": "career_counseling",
                    "title": "진로/취업 상담",
                    "summary": "인재개발처 상담 신청 안내",
                    "steps": ["상담 신청"],
                    "links": [],
                    "source_url": "https://career.catholic.ac.kr/career/job/job_counseling.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": SYNCED_AT,
                }
            ],
        )

        result = campus_life_help(conn, query="진로 상담", limit=5)

    assert result.journey == "campus_life_help"
    assert result.sections[0].name == "campus_life_support_guides"
    assert result.sections[0].items[0]["topic"] == "career_counseling"
    assert "SNS" in " ".join(result.out_of_scope)


def test_public_status_snapshot_strips_operational_details(monkeypatch):
    monkeypatch.setattr(
        "songsim_campus.services.get_readiness_snapshot",
        lambda: {
            "ok": False,
            "database": {"ok": True, "error": None},
            "tables": {
                "places": {
                    "name": "places",
                    "ok": False,
                    "policy": "core",
                    "row_count": 0,
                    "last_synced_at": None,
                    "reason": "empty_or_unsynced",
                },
                "campus_life_notices": {
                    "name": "campus_life_notices",
                    "ok": True,
                    "policy": "best_effort",
                    "row_count": 0,
                    "last_synced_at": None,
                },
                "sync_runs": {"name": "sync_runs", "ok": True},
            },
        },
    )

    payload = get_public_status_snapshot()
    dumped = payload.model_dump()

    assert payload.ok is False
    assert {item.name for item in payload.datasets} == {"places", "campus_life_notices"}
    assert next(item for item in payload.datasets if item.name == "places").status == "empty"
    best_effort = next(item for item in payload.datasets if item.name == "campus_life_notices")
    assert best_effort.policy == "best_effort"
    assert best_effort.note and "best_effort" in best_effort.note
    assert "database" not in dumped
    assert "sync_runs" not in str(dumped)
