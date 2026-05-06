from __future__ import annotations

from songsim_campus import repo, services
from songsim_campus.db import connection, init_db
from songsim_campus.schemas import StudentExchangePartner
from songsim_campus.services import (
    refresh_student_exchange_partners_from_source,
    run_admin_sync,
    search_student_exchange_partners,
)
from songsim_campus.settings import clear_settings_cache

PARTNER_SOURCE_URL = "https://www.catholic.ac.kr/ko/support/exchange_oversea1.do"
PARTNER_SOURCE_TAG = "cuk_student_exchange_partners"


def _partner_row(
    *,
    partner_code: str,
    university_name: str,
    country_ko: str,
    country_en: str,
    continent: str,
    location: str | None = None,
    agreement_date: str | None = None,
    homepage_url: str | None = None,
    source_url: str = PARTNER_SOURCE_URL,
    source_tag: str = PARTNER_SOURCE_TAG,
) -> dict[str, object]:
    return {
        "partner_code": partner_code,
        "university_name": university_name,
        "country_ko": country_ko,
        "country_en": country_en,
        "continent": continent,
        "location": location,
        "agreement_date": agreement_date,
        "homepage_url": homepage_url,
        "source_url": source_url,
        "source_tag": source_tag,
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


def test_student_exchange_partner_model_has_expected_shape() -> None:
    partner = StudentExchangePartner.model_validate(
        {
            "id": 1,
            "partner_code": "00122",
            "university_name": "Utrecht University",
            "country_ko": "네덜란드",
            "country_en": "NETHERLANDS",
            "continent": "EUROPE",
            "location": None,
            "agreement_date": None,
            "homepage_url": "https://www.uu.nl",
            "source_url": PARTNER_SOURCE_URL,
            "source_tag": PARTNER_SOURCE_TAG,
            "last_synced_at": "2026-03-20T00:00:00+09:00",
        }
    )

    assert partner.partner_code == "00122"
    assert partner.homepage_url == "https://www.uu.nl"


def test_student_exchange_partner_source_refresh_replaces_rows(app_env) -> None:
    init_db()

    class DummySource:
        def __init__(self, *_args, **_kwargs):
            self.called = False

        def fetch(self) -> str:
            self.called = True
            return "{}"

        def parse(self, _payload: str, *, fetched_at: str):
            assert fetched_at == "2026-03-20T00:00:00+09:00"
            return [
                _partner_row(
                    partner_code="00004",
                    university_name="National Central University",
                    country_ko="대만",
                    country_en="TAIWAN, PROVINCE OF CHINA",
                    continent="ASIA",
                    location="Taoyuan",
                    agreement_date="2008-07-23",
                    homepage_url="http://www.ncu.edu.tw",
                ),
                _partner_row(
                    partner_code="00122",
                    university_name="Utrecht University",
                    country_ko="네덜란드",
                    country_en="NETHERLANDS",
                    continent="EUROPE",
                    homepage_url=None,
                ),
            ]

    with connection() as conn:
        rows = refresh_student_exchange_partners_from_source(
            conn,
            source=DummySource(),
            fetched_at="2026-03-20T00:00:00+09:00",
        )

        stored = repo.list_student_exchange_partners(conn, limit=20)

    assert [row.partner_code for row in rows] == ["00122", "00004"]
    assert stored[0]["homepage_url"] is None
    assert stored[1]["homepage_url"] == "http://www.ncu.edu.tw"
    assert stored[0]["source_tag"] == PARTNER_SOURCE_TAG
    assert stored[0]["source_url"] == PARTNER_SOURCE_URL


def test_student_exchange_partner_search_ranks_exact_and_contains_matches(app_env) -> None:
    init_db()
    rows = [
        _partner_row(
            partner_code="00004",
            university_name="National Central University",
            country_ko="대만",
            country_en="TAIWAN, PROVINCE OF CHINA",
            continent="ASIA",
            location="Taoyuan",
            agreement_date="2008-07-23",
            homepage_url="http://www.ncu.edu.tw",
        ),
        _partner_row(
            partner_code="00122",
            university_name="Utrecht University",
            country_ko="네덜란드",
            country_en="NETHERLANDS",
            continent="EUROPE",
        ),
        _partner_row(
            partner_code="00173",
            university_name="Massey University",
            country_ko="뉴질랜드",
            country_en="NEW ZEALAND",
            continent="OCEANIA",
        ),
        _partner_row(
            partner_code="00198",
            university_name="The American College of Greece",
            country_ko="그리스",
            country_en="GREECE",
            continent="EUROPE",
            location="Athens, Greece",
        ),
    ]

    with connection() as conn:
        repo.replace_student_exchange_partners(conn, rows)

        default_rows = search_student_exchange_partners(conn, limit=20)
        exact_country = search_student_exchange_partners(conn, query="네덜란드", limit=20)
        exact_continent = search_student_exchange_partners(conn, query="EUROPE", limit=20)
        korean_continent = search_student_exchange_partners(conn, query="유럽", limit=20)
        contains_name = search_student_exchange_partners(conn, query="University", limit=20)
        contains_location = search_student_exchange_partners(conn, query="Athens", limit=20)

    assert [row.university_name for row in default_rows] == [
        "The American College of Greece",
        "Utrecht University",
        "Massey University",
        "National Central University",
    ]
    assert [row.university_name for row in exact_country][:2] == ["Utrecht University"]
    assert [row.university_name for row in exact_continent][:2] == [
        "The American College of Greece",
        "Utrecht University",
    ]
    assert [row.university_name for row in korean_continent][:2] == [
        "The American College of Greece",
        "Utrecht University",
    ]
    assert [row.university_name for row in contains_name][:3] == [
        "Utrecht University",
        "Massey University",
        "National Central University",
    ]
    assert [row.university_name for row in contains_location] == [
        "The American College of Greece"
    ]


def test_student_exchange_partner_dataset_is_wired_into_sync_and_readiness(app_env, monkeypatch):
    init_db()

    assert "student_exchange_partners" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["student_exchange_partners"] == "core"
    assert "student_exchange_partners" in services.PUBLIC_READY_CORE_DATASETS
    assert "student_exchange_partners" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_student_exchange_partners_from_source",
        lambda conn, source=None, fetched_at=None: [],
    )

    with connection():
        run = run_admin_sync(target="student_exchange_partners")

    assert run.status == "success"
    assert run.summary == {"student_exchange_partners": 0}


def test_student_exchange_partner_snapshot_sync_in_public_readonly_mode(app_env, monkeypatch):
    init_db()
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    call_order: list[str] = []

    def stub(name: str):
        def inner(*_args, **_kwargs):
            call_order.append(name)
            return []

        return inner

    stubs = {
        "refresh_places_from_campus_map": "places",
        "refresh_campus_facilities_from_source": "campus_facilities",
        "refresh_library_hours_from_library_page": "library_hours",
        "refresh_facility_hours_from_facilities_page": "facility_hours",
        "refresh_campus_dining_menus_from_facilities_page": "dining_menus",
        "refresh_courses_from_subject_search": "courses",
        "refresh_notices_from_notice_board": "notices",
        "refresh_affiliated_notices_from_sources": "affiliated_notices",
        "refresh_academic_calendar_from_source": "academic_calendar",
        "refresh_certificate_guides_from_certificate_page": "certificate_guides",
        "refresh_leave_of_absence_guides_from_source": "leave_of_absence_guides",
        "refresh_academic_status_guides_from_source": "academic_status_guides",
        "refresh_registration_guides_from_source": "registration_guides",
        "refresh_class_guides_from_source": "class_guides",
        "refresh_seasonal_semester_guides_from_source": "seasonal_semester_guides",
        "refresh_academic_milestone_guides_from_source": "academic_milestone_guides",
        "refresh_campus_life_support_guides_from_source": "campus_life_support_guides",
        "refresh_pc_software_entries_from_source": "pc_software_entries",
        "refresh_student_exchange_guides_from_source": "student_exchange_guides",
        "refresh_about_resource_guides_from_source": "about_resource_guides",
        "refresh_service_policy_guides_from_source": "service_policy_guides",
        "refresh_dormitory_guides_from_source": "dormitory_guides",
        "refresh_phone_book_entries_from_source": "phone_book_entries",
        "refresh_student_exchange_partners_from_source": "student_exchange_partners",
        "refresh_scholarship_guides_from_source": "scholarship_guides",
        "refresh_academic_support_guides_from_source": "academic_support_guides",
        "refresh_wifi_guides_from_source": "wifi_guides",
        "refresh_transport_guides_from_location_page": "transport_guides",
    }
    for attr, name in stubs.items():
        monkeypatch.setattr(f"songsim_campus.services.{attr}", stub(name))

    with connection() as conn:
        summary = services.sync_official_snapshot(conn)

    assert "student_exchange_partners" in summary
    assert "student_exchange_partners" in call_order
    assert "about_resource_guides" in summary
    assert "about_resource_guides" in call_order
    assert "service_policy_guides" in summary
    assert "service_policy_guides" in call_order
    assert "campus_life_support_guides" in summary
    assert "campus_life_support_guides" in call_order
    assert "pc_software_entries" in summary
    assert "pc_software_entries" in call_order
