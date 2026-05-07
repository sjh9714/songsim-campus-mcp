from __future__ import annotations

import types

import pytest

from songsim_campus import repo, services
from songsim_campus.db import connection, init_db
from songsim_campus.schemas import StudentExchangeGuide
from songsim_campus.services import (
    InvalidRequestError,
    list_student_exchange_guides,
    sync_official_snapshot,
)


def _row(
    *,
    topic: str,
    title: str,
    summary: str,
    source_url: str,
    source_tag: str = "cuk_student_exchange_guides",
) -> dict[str, object]:
    return {
        "topic": topic,
        "title": title,
        "summary": summary,
        "steps": [f"{title} 단계"],
        "links": [{"label": title, "url": source_url}],
        "source_url": source_url,
        "source_tag": source_tag,
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


def test_student_exchange_guide_model_has_expected_shape() -> None:
    guide = StudentExchangeGuide.model_validate(
        {
            "id": 1,
            "topic": "exchange_student",
            "title": "교환학생 프로그램",
            "summary": "해외 교환학생 안내",
            "steps": ["1단계", "2단계"],
            "links": [{"label": "교환학생", "url": "https://example.com"}],
            "source_url": "https://example.com",
            "source_tag": "cuk_student_exchange_guides",
            "last_synced_at": "2026-03-20T00:00:00+09:00",
        }
    )

    assert guide.topic == "exchange_student"
    assert guide.links == [{"label": "교환학생", "url": "https://example.com"}]


def test_student_exchange_guides_repo_replace_and_service_filter(app_env):
    init_db()
    rows = [
        _row(
            topic="domestic_credit_exchange",
            title="신청대상",
            summary="국내 학점교류 신청대상",
            source_url="https://www.catholic.ac.kr/ko/support/exchange_domestic1.do",
        ),
        _row(
            topic="domestic_partner_universities",
            title="교류대학 현황",
            summary="국내 교류대학 현황",
            source_url="https://www.catholic.ac.kr/ko/support/exchange_domestic2.do",
        ),
        _row(
            topic="exchange_student",
            title="상호교환 프로그램",
            summary="해외 교환학생 프로그램",
            source_url="https://www.catholic.ac.kr/ko/support/exchange_oversea2.do",
        ),
        _row(
            topic="exchange_programs",
            title="EASCOM(East Asia Student Communication Program)",
            summary="해외 교류프로그램",
            source_url="https://www.catholic.ac.kr/ko/support/exchange_oversea3.do",
        ),
    ]

    with connection() as conn:
        repo.replace_student_exchange_guides(conn, rows)
        stored = repo.list_student_exchange_guides(conn, limit=20)
        filtered = list_student_exchange_guides(
            conn,
            topic="exchange_programs",
            limit=20,
        )

    assert [item["topic"] for item in stored] == [
        "domestic_credit_exchange",
        "domestic_partner_universities",
        "exchange_student",
        "exchange_programs",
    ]
    assert all(isinstance(item, StudentExchangeGuide) for item in filtered)
    assert [item.topic for item in filtered] == ["exchange_programs"]
    assert filtered[0].links == [
        {
            "label": "EASCOM(East Asia Student Communication Program)",
            "url": "https://www.catholic.ac.kr/ko/support/exchange_oversea3.do",
        }
    ]


def test_student_exchange_guides_reject_invalid_topic(app_env):
    init_db()

    with connection() as conn:
        with pytest.raises(InvalidRequestError):
            list_student_exchange_guides(conn, topic="unknown_topic")


def test_student_exchange_guides_refresh_raises_when_source_classes_are_missing(
    app_env, monkeypatch
):
    init_db()

    class DummySource:
        def __init__(self, _url: str):
            self.url = _url

        def fetch(self) -> str:
            return "<exchange />"

        def parse(self, _html: str, *, fetched_at: str):
            return [
                _row(
                    topic="domestic_credit_exchange",
                    title="신청대상",
                    summary=f"국내 학점교류 신청대상 ({fetched_at})",
                    source_url=self.url,
                )
            ]

    incomplete_module = types.SimpleNamespace(
        StudentExchangeDomesticCreditExchangeGuideSource=DummySource,
        StudentExchangeDomesticPartnerUniversitiesGuideSource=DummySource,
        StudentExchangeExchangeProgramsGuideSource=DummySource,
    )
    monkeypatch.setattr(services, "import_module", lambda *_args, **_kwargs: incomplete_module)

    with connection() as conn:
        with pytest.raises(RuntimeError, match="student exchange guide sources are unavailable"):
            services.refresh_student_exchange_guides_from_source(conn)


def test_student_exchange_guides_are_in_sync_snapshot_and_readiness(app_env, monkeypatch):
    init_db()

    assert "student_exchange_guides" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["student_exchange_guides"] == "core"
    assert "student_exchange_guides" in services.ADMIN_SYNC_TARGETS
    assert "student_exchange_guides" in services.PUBLIC_READY_CORE_DATASETS

    sentinel_rows = [
        _row(
            topic="domestic_credit_exchange",
            title="신청대상",
            summary="국내 학점교류 신청대상",
            source_url="https://www.catholic.ac.kr/ko/support/exchange_domestic1.do",
        )
    ]

    def stub(result):
        def inner(*_args, **_kwargs):
            return result

        return inner

    stubs = {
        "refresh_places_from_campus_map": ["places"],
        "refresh_campus_facilities_from_source": ["campus_facilities"],
        "refresh_library_hours_from_library_page": ["library_hours"],
        "refresh_facility_hours_from_facilities_page": ["facility_hours"],
        "refresh_campus_dining_menus_from_facilities_page": ["dining_menus"],
        "refresh_courses_from_subject_search": ["courses"],
        "refresh_notices_from_notice_board": ["notices"],
        "refresh_affiliated_notices_from_sources": ["affiliated_notices"],
        "refresh_academic_calendar_from_source": ["academic_calendar"],
        "refresh_certificate_guides_from_certificate_page": ["certificate_guides"],
        "refresh_leave_of_absence_guides_from_source": ["leave_of_absence_guides"],
        "refresh_academic_status_guides_from_source": ["academic_status_guides"],
        "refresh_registration_guides_from_source": ["registration_guides"],
        "refresh_class_guides_from_source": ["class_guides"],
        "refresh_seasonal_semester_guides_from_source": ["seasonal_semester_guides"],
        "refresh_academic_milestone_guides_from_source": ["academic_milestone_guides"],
        "refresh_student_activity_guides_from_source": ["student_activity_guides"],
        "refresh_student_activity_notices_from_source": ["student_activity_notices"],
        "refresh_about_resource_guides_from_source": ["about_resource_guides"],
        "refresh_service_policy_guides_from_source": ["service_policy_guides"],
        "refresh_newsroom_posts_from_source": ["newsroom_posts"],
        "refresh_campus_life_support_guides_from_source": ["campus_life_support_guides"],
        "refresh_pc_software_entries_from_source": ["pc_software_entries"],
        "refresh_student_exchange_guides_from_source": sentinel_rows,
        "refresh_dormitory_guides_from_source": ["dormitory_guides"],
        "refresh_phone_book_entries_from_source": ["phone_book_entries"],
        "refresh_scholarship_guides_from_source": ["scholarship_guides"],
        "refresh_academic_support_guides_from_source": ["academic_support_guides"],
        "refresh_wifi_guides_from_source": ["wifi_guides"],
        "refresh_transport_guides_from_location_page": ["transport_guides"],
    }
    for name, result in stubs.items():
        monkeypatch.setattr(services, name, stub(result))

    with connection() as conn:
        summary = sync_official_snapshot(conn)

    assert summary["student_exchange_guides"] == len(sentinel_rows)
    assert summary["academic_milestone_guides"] == 1
    assert summary["student_activity_notices"] == 1
    assert summary["about_resource_guides"] == 1
    assert summary["service_policy_guides"] == 1
    assert summary["newsroom_posts"] == 1
    assert summary["campus_life_support_guides"] == 1
    assert summary["pc_software_entries"] == 1
    assert summary["transport_guides"] == 1
