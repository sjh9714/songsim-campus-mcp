from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

import songsim_campus.services as services_module
from songsim_campus import repo
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.kakao_places import KakaoPlace
from songsim_campus.repo import replace_places, replace_restaurants, update_place_opening_hours
from songsim_campus.seed import seed_demo
from songsim_campus.services import (
    InvalidRequestError,
    NotFoundError,
    _load_place_alias_overrides,
    _load_place_facility_keywords,
    _load_place_short_query_preferences,
    _load_restaurant_search_aliases,
    _load_restaurant_search_noise_terms,
    _parse_campus_walk_graph,
    find_nearby_restaurants,
    get_class_periods,
    get_library_seat_status,
    get_notice_categories,
    get_place,
    investigate_course_query_coverage,
    list_academic_calendar,
    list_academic_status_guides,
    list_academic_support_guides,
    list_affiliated_notices,
    list_campus_life_notices,
    list_campus_life_support_guides,
    list_certificate_guides,
    list_dormitory_guides,
    list_estimated_empty_classrooms,
    list_latest_notices,
    list_leave_of_absence_guides,
    list_scholarship_guides,
    list_student_activity_guides,
    list_transport_guides,
    list_wifi_guides,
    refresh_academic_calendar_from_source,
    refresh_academic_status_guides_from_source,
    refresh_academic_support_guides_from_source,
    refresh_affiliated_notices_from_sources,
    refresh_campus_dining_menus_from_facilities_page,
    refresh_campus_facilities_from_source,
    refresh_campus_life_notices_from_source,
    refresh_campus_life_support_guides_from_source,
    refresh_certificate_guides_from_certificate_page,
    refresh_courses_from_subject_search,
    refresh_dormitory_guides_from_source,
    refresh_facility_hours_from_facilities_page,
    refresh_leave_of_absence_guides_from_source,
    refresh_library_hours_from_library_page,
    refresh_notices_from_notice_board,
    refresh_places_from_campus_map,
    refresh_scholarship_guides_from_source,
    refresh_student_activity_guides_from_source,
    refresh_transport_guides_from_location_page,
    refresh_wifi_guides_from_source,
    search_campus_dining_menus,
    search_courses,
    search_places,
    search_restaurants,
    sync_official_snapshot,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")
SAMPLE_MENU_PDF_BASE64 = (
    "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5k"
    "b2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4K"
    "ZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3gg"
    "WzAgMCA2MTIgNzkyXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAv"
    "RjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCAxNDIgPj4Kc3Ry"
    "ZWFtCkJUCi9GMSAxMiBUZgo3MiA3MjAgVGQKKFdlZWtseSBNZW51IDIwMjYuMDMuMTYgLSAw"
    "My4yMCkgVGoKMCAtMTggVGQKKENhZmUgQm9uYSkgVGoKMCAtMTggVGQKKEJ1bGdvZ2kgUmlj"
    "ZSBCb3dsKSBUagowIC0xOCBUZAooTGVtb24gVGVhKSBUagpFVAplbmRzdHJlYW0KZW5kb2Jq"
    "CjUgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVs"
    "dmV0aWNhID4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAw"
    "MDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTE1IDAwMDAwIG4gCjAw"
    "MDAwMDAyNDEgMDAwMDAgbiAKMDAwMDAwMDQzMyAwMDAwMCBuIAp0cmFpbGVyCjw8IC9TaXpl"
    "IDYgL1Jvb3QgMSAwIFIgPj4Kc3RhcnR4cmVmCjUwMgolJUVPRgo="
)


def _fixture_json(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _sample_menu_pdf_bytes() -> bytes:
    return base64.b64decode(SAMPLE_MENU_PDF_BASE64)


def _restaurant_row(
    *,
    slug: str,
    name: str,
    latitude: float,
    longitude: float,
    category: str = "korean",
    source_tag: str = "test",
) -> dict:
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "min_price": 7000,
        "max_price": 9000,
        "latitude": latitude,
        "longitude": longitude,
        "tags": ["한식"],
        "description": "테스트 식당",
        "source_tag": source_tag,
        "last_synced_at": "2026-03-13T09:00:00+09:00",
    }


def _place_row(
    *,
    slug: str,
    name: str,
    category: str = "building",
    aliases: list[str] | None = None,
    description: str = "",
    latitude: float = 37.48590,
    longitude: float = 126.80282,
    opening_hours: dict[str, str] | None = None,
    source_tag: str = "test",
) -> dict:
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "aliases": aliases or [],
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "opening_hours": opening_hours or {},
        "source_tag": source_tag,
        "last_synced_at": "2026-03-13T09:00:00+09:00",
    }


def _dormitory_guide_row(
    *,
    topic: str,
    title: str,
    summary: str,
    steps: list[str],
    links: list[dict[str, str]] | None = None,
    source_url: str = "https://dorm.catholic.ac.kr/",
    source_tag: str = "cuk_dormitory_guides",
) -> dict:
    return {
        "topic": topic,
        "title": title,
        "summary": summary,
        "steps": steps,
        "links": links or [],
        "source_url": source_url,
        "source_tag": source_tag,
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


def _affiliated_notice_row(
    *,
    topic: str,
    title: str,
    published_at: str,
    summary: str,
    body_text: str = "",
    source_url: str = "https://example.com/notices/1",
    source_tag: str = "cuk_affiliated_notice_boards",
) -> dict:
    return {
        "topic": topic,
        "title": title,
        "published_at": published_at,
        "summary": summary,
        "body_text": body_text,
        "source_url": source_url,
        "source_tag": source_tag,
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


def _campus_life_notice_row(
    *,
    title: str,
    published_at: str,
    summary: str,
    topic: str = "outside_agencies",
    source_url: str = "https://example.com/campus-life-notices/1",
    source_tag: str = "cuk_campus_life_notices",
) -> dict:
    return {
        "topic": topic,
        "title": title,
        "published_at": published_at,
        "summary": summary,
        "source_url": source_url,
        "source_tag": source_tag,
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


def _course_row(
    *,
    year: int,
    semester: int,
    code: str,
    title: str,
    professor: str | None = "담당교수",
    section: str = "01",
    department: str = "테스트학과",
    source_tag: str = "test",
) -> dict:
    return {
        "year": year,
        "semester": semester,
        "code": code,
        "title": title,
        "professor": professor,
        "department": department,
        "section": section,
        "day_of_week": "월",
        "period_start": 1,
        "period_end": 2,
        "room": "M101",
        "raw_schedule": "월1~2(M101)",
        "source_tag": source_tag,
        "last_synced_at": "2026-03-13T09:00:00+09:00",
    }


def test_get_class_periods_returns_ten_periods(app_env):
    init_db()
    seed_demo(force=True)
    periods = get_class_periods()
    assert len(periods) == 10
    assert periods[0].start == '09:00'
    assert periods[-1].end == '18:50'


def test_get_notice_categories_returns_public_canonical_metadata(app_env):
    categories = get_notice_categories()

    assert [item.category for item in categories] == [
        "academic",
        "scholarship",
        "employment",
        "general",
    ]
    assert [item.category_display for item in categories] == [
        "학사",
        "장학",
        "취업",
        "일반",
    ]
    assert categories[2].aliases == ["career"]
    assert categories[3].aliases == ["place"]


def test_affiliated_notices_are_marked_best_effort_in_readiness_policy():
    assert services_module.PUBLIC_READY_DATASET_POLICIES["affiliated_notices"] == "best_effort"
    assert "affiliated_notices" in services_module.SYNC_DATASET_TABLES


def test_campus_life_notices_are_marked_best_effort_in_readiness_policy():
    assert services_module.PUBLIC_READY_DATASET_POLICIES["campus_life_notices"] == "best_effort"
    assert "campus_life_notices" in services_module.SYNC_DATASET_TABLES


class FakeLibrarySeatStatusSource:
    def fetch(self):
        return "<seat-status></seat-status>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<seat-status></seat-status>"
        return [
            {
                "room_name": "제1자유열람실",
                "remaining_seats": 28,
                "occupied_seats": 72,
                "total_seats": 100,
                "source_url": "http://203.229.203.240/8080/Domian5.asp",
                "source_tag": "cuk_library_seat_status",
                "last_synced_at": fetched_at,
            },
            {
                "room_name": "제2자유열람실",
                "remaining_seats": 25,
                "occupied_seats": 55,
                "total_seats": 80,
                "source_url": "http://203.229.203.240/8080/Domian5.asp",
                "source_tag": "cuk_library_seat_status",
                "last_synced_at": fetched_at,
            },
        ]


class FailingLibrarySeatStatusSource:
    def fetch(self):
        raise httpx.ConnectTimeout("timed out")


def test_get_library_seat_status_uses_fresh_cache_without_live_fetch(app_env):
    init_db()
    with connection() as conn:
        repo.replace_library_seat_status_cache(
            conn,
            [
                {
                    "room_name": "제1자유열람실",
                    "remaining_seats": 12,
                    "occupied_seats": 88,
                    "total_seats": 100,
                    "source_url": "http://203.229.203.240/8080/Domian5.asp",
                    "source_tag": "cuk_library_seat_status",
                    "last_synced_at": "2026-03-16T08:59:00+09:00",
                }
            ],
        )

        response = get_library_seat_status(
            conn,
            source=FailingLibrarySeatStatusSource(),
            now=datetime.fromisoformat("2026-03-16T09:00:00+09:00"),
        )

    assert response.availability_mode == "live"
    assert response.checked_at == "2026-03-16T08:59:00+09:00"
    assert response.rooms[0].remaining_seats == 12


def test_get_library_seat_status_fetches_live_rows_and_filters_room_query(app_env):
    init_db()
    with connection() as conn:
        response = get_library_seat_status(
            conn,
            query="제1자유열람실 남은 좌석",
            source=FakeLibrarySeatStatusSource(),
            now=datetime.fromisoformat("2026-03-16T09:00:00+09:00"),
        )

    assert response.availability_mode == "live"
    assert response.source_url == "http://203.229.203.240/8080/Domian5.asp"
    assert [room.room_name for room in response.rooms] == ["제1자유열람실"]
    assert response.rooms[0].remaining_seats == 28


def test_get_library_seat_status_falls_back_to_stale_cache_on_live_failure(app_env):
    init_db()
    with connection() as conn:
        repo.replace_library_seat_status_cache(
            conn,
            [
                {
                    "room_name": "제1자유열람실",
                    "remaining_seats": 10,
                    "occupied_seats": 90,
                    "total_seats": 100,
                    "source_url": "http://203.229.203.240/8080/Domian5.asp",
                    "source_tag": "cuk_library_seat_status",
                    "last_synced_at": "2026-03-16T08:50:00+09:00",
                }
            ],
        )

        response = get_library_seat_status(
            conn,
            source=FailingLibrarySeatStatusSource(),
            now=datetime.fromisoformat("2026-03-16T09:00:00+09:00"),
        )

    assert response.availability_mode == "stale_cache"
    assert response.checked_at == "2026-03-16T08:50:00+09:00"
    assert response.rooms[0].remaining_seats == 10
    assert response.note


def test_refresh_library_seat_status_cache_replaces_existing_rows_on_success(app_env):
    init_db()
    with connection() as conn:
        repo.replace_library_seat_status_cache(
            conn,
            [
                {
                    "room_name": "제1자유열람실",
                    "remaining_seats": 10,
                    "occupied_seats": 90,
                    "total_seats": 100,
                    "source_url": "http://203.229.203.240/8080/Domian5.asp",
                    "source_tag": "cuk_library_seat_status",
                    "last_synced_at": "2026-03-16T08:50:00+09:00",
                }
            ],
        )

        rows = services_module.refresh_library_seat_status_cache(
            conn,
            fetched_at="2026-03-16T09:00:00+09:00",
            source=FakeLibrarySeatStatusSource(),
        )

        cached = repo.list_library_seat_status_cache(conn)

    assert len(rows) == 2
    assert [row["room_name"] for row in cached] == ["제1자유열람실", "제2자유열람실"]
    assert cached[0]["last_synced_at"] == "2026-03-16T09:00:00+09:00"


def test_refresh_library_seat_status_cache_keeps_existing_rows_on_failure(app_env):
    init_db()
    with connection() as conn:
        repo.replace_library_seat_status_cache(
            conn,
            [
                {
                    "room_name": "제1자유열람실",
                    "remaining_seats": 10,
                    "occupied_seats": 90,
                    "total_seats": 100,
                    "source_url": "http://203.229.203.240/8080/Domian5.asp",
                    "source_tag": "cuk_library_seat_status",
                    "last_synced_at": "2026-03-16T08:50:00+09:00",
                }
            ],
        )

        with pytest.raises(httpx.ConnectTimeout):
            services_module.refresh_library_seat_status_cache(
                conn,
                fetched_at="2026-03-16T09:00:00+09:00",
                source=FailingLibrarySeatStatusSource(),
            )

        cached = repo.list_library_seat_status_cache(conn)

    assert len(cached) == 1
    assert cached[0]["remaining_seats"] == 10
    assert cached[0]["last_synced_at"] == "2026-03-16T08:50:00+09:00"


def test_get_library_seat_status_returns_unavailable_when_live_and_cache_are_missing(app_env):
    init_db()
    with connection() as conn:
        response = get_library_seat_status(
            conn,
            query="제1자유열람실",
            source=FailingLibrarySeatStatusSource(),
            now=datetime.fromisoformat("2026-03-16T09:00:00+09:00"),
        )

    assert response.availability_mode == "unavailable"
    assert response.rooms == []
    assert response.note


def test_search_places_matches_alias(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        places = search_places(conn, query='중도')
    assert any(item.name == '중앙도서관' for item in places)
    assert any(item.canonical_name == '중앙도서관' for item in places)


def test_search_places_uses_alias_friendly_name_for_strong_alias_queries(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="sophie-barat-hall",
                    name="학생미래인재관",
                    category="building",
                    aliases=["학생회관", "학생센터"],
                ),
                _place_row(
                    slug="kim-sou-hwan-hall",
                    name="김수환관",
                    category="building",
                    aliases=["김수환", "K관"],
                ),
                _place_row(
                    slug="central-library",
                    name="중앙도서관",
                    category="library",
                    aliases=["중도"],
                ),
                _place_row(
                    slug="nichols-hall",
                    name="니콜스관",
                    category="building",
                    aliases=["니콜스"],
                ),
            ],
        )

        student_hall = search_places(conn, query="학생회관 어디야?", limit=1)[0]
        k_hall = search_places(conn, query="K관 어디야?", limit=1)[0]
        library = search_places(conn, query="중도", limit=1)[0]
        nichols = search_places(conn, query="니콜스 어디 있어?", limit=1)[0]
        canonical = search_places(conn, query="김수환관 어디야?", limit=1)[0]

    assert student_hall.slug == "sophie-barat-hall"
    assert student_hall.name == "학생회관"
    assert student_hall.canonical_name == "학생미래인재관"

    assert k_hall.slug == "kim-sou-hwan-hall"
    assert k_hall.name == "K관"
    assert k_hall.canonical_name == "김수환관"

    assert library.slug == "central-library"
    assert library.name == "중앙도서관"
    assert library.canonical_name == "중앙도서관"

    assert nichols.slug == "nichols-hall"
    assert nichols.name == "니콜스관"
    assert nichols.canonical_name == "니콜스관"

    assert canonical.slug == "kim-sou-hwan-hall"
    assert canonical.name == "김수환관"
    assert canonical.canonical_name == "김수환관"


def test_search_places_prioritizes_exact_short_match_over_partial_noise(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "main-gate",
                    "name": "정문",
                    "category": "gate",
                    "aliases": ["학교 정문"],
                    "description": "성심교정의 정문",
                    "latitude": 37.4855,
                    "longitude": 126.8018,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "startup-incubator",
                    "name": "창업보육센터",
                    "category": "building",
                    "aliases": [],
                    "description": "정문 옆 창업 지원 공간",
                    "latitude": 37.4857,
                    "longitude": 126.8020,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        places = search_places(conn, query="정문", limit=10)

    assert [place.slug for place in places] == ["main-gate"]


def test_load_place_short_query_preferences_supports_context_specific_slugs(app_env):
    preferences = _load_place_short_query_preferences()

    assert preferences["K관"]["place_search"] == ["kim-sou-hwan-hall"]
    assert preferences["K관"]["origin"] == ["kim-sou-hwan-hall"]
    assert preferences["K관"]["building"] == ["kim-sou-hwan-hall"]
    assert preferences["정문"]["place_search"] == ["main-gate"]
    assert preferences["정문"]["origin"] == ["main-gate"]
    assert preferences["정문"]["building"] == []


def test_search_places_prefers_short_query_place_preference_for_k_hall(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    aliases=["K관"],
                    description="기숙사 생활시설 건물",
                ),
                _place_row(
                    slug="kim-sou-hwan-hall",
                    name="김수환관",
                    category="building",
                    aliases=["김수환", "K관"],
                    description="강의실과 연구실이 있는 건물",
                ),
            ],
        )
        places = search_places(conn, query="K관", limit=10)

    assert [place.slug for place in places] == ["kim-sou-hwan-hall"]


def test_search_places_keeps_category_filter_before_short_query_canonicalization(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="main-gate",
                    name="정문",
                    category="gate",
                    aliases=["학교 정문"],
                    description="성심교정의 정문",
                ),
                _place_row(
                    slug="startup-incubator",
                    name="창업보육센터",
                    category="building",
                    aliases=[],
                    description="정문 옆 창업 지원 공간",
                ),
            ],
        )
        places = search_places(conn, query="정문", category="building", limit=10)

    assert places == []


@pytest.mark.parametrize(
    ("query", "expected_slug"),
    [
        ("중앙 도서관", "central-library"),
        ("니콜스 관", "nichols-hall"),
    ],
)
def test_search_places_normalizes_spacing_variants(app_env, query, expected_slug):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        places = search_places(conn, query=query, limit=5)

    assert places
    assert places[0].slug == expected_slug


def test_search_courses_normalizes_spacing_variants(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        courses = search_courses(conn, query="객체 지향", year=2026, semester=1, limit=5)

    assert courses
    assert courses[0].title == "객체지향프로그래밍설계"


def test_search_courses_normalizes_database_alias_and_code_spacing(app_env):
    init_db()

    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                _course_row(year=2026, semester=1, code="CSE420", title="임베디드시스템"),
                _course_row(year=2026, semester=1, code="MTH101", title="데이터베이스활용"),
                _course_row(
                    year=2026,
                    semester=1,
                    code="BIO102",
                    title="분자생물학개론",
                    professor="박요셉",
                ),
                _course_row(
                    year=2026,
                    semester=1,
                    code="CHE103",
                    title="화학실험",
                    professor="김가톨",
                ),
            ],
        )
        alias_courses = search_courses(conn, query="데이타베이스", limit=5)
        spaced_database_courses = search_courses(conn, query="데 이 터 베 이 스", limit=5)
        spaced_code_courses = search_courses(conn, query="CSE 420", limit=5)
        dashed_code_courses = search_courses(conn, query="CSE-420", limit=5)
        mixed_case_code_courses = search_courses(conn, query="cSe 420", limit=5)
        compact_code_courses = search_courses(conn, query="CSE420", limit=5)
        spaced_professor_courses = search_courses(conn, query="김 가 톨", limit=5)
        spaced_professor_two_courses = search_courses(conn, query="박 요 셉", limit=5)

    assert [course.code for course in alias_courses] == ["MTH101"]
    assert [course.code for course in spaced_database_courses] == ["MTH101"]
    assert [course.code for course in spaced_code_courses] == ["CSE420"]
    assert [course.code for course in dashed_code_courses] == ["CSE420"]
    assert [course.code for course in mixed_case_code_courses] == ["CSE420"]
    assert [course.code for course in compact_code_courses] == ["CSE420"]
    assert [course.code for course in spaced_professor_courses] == ["CHE103"]
    assert [course.code for course in spaced_professor_two_courses] == ["BIO102"]


def test_search_courses_filters_by_period_start(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        courses = search_courses(conn, year=2026, semester=1, period_start=7, limit=5)

    assert courses
    assert [course.code for course in courses] == ["CSE401"]
    assert all(course.period_start == 7 for course in courses)


def test_search_courses_prioritizes_exact_code_over_title_substring(app_env):
    init_db()

    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                _course_row(year=2026, semester=1, code="EEE200", title="CSE101 프로젝트"),
                _course_row(year=2026, semester=1, code="CSE101", title="알고리즘개론"),
            ],
        )
        courses = search_courses(conn, query="CSE101", limit=5)

    assert [course.code for course in courses] == ["CSE101", "EEE200"]


def test_search_courses_prioritizes_code_prefix_over_exact_title(app_env):
    init_db()

    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                _course_row(year=2026, semester=1, code="MAT100", title="CSE"),
                _course_row(year=2026, semester=1, code="CSE210", title="프로그래밍실습"),
            ],
        )
        courses = search_courses(conn, query="CSE", limit=5)

    assert [course.code for course in courses] == ["CSE210", "MAT100"]


def test_search_courses_prioritizes_title_and_professor_matches_deterministically(app_env):
    init_db()

    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                _course_row(year=2026, semester=1, code="GEN900", title="고급자료분석"),
                _course_row(year=2026, semester=1, code="CSE900", title="자료"),
                _course_row(year=2026, semester=1, code="CSE901", title="자료구조"),
                _course_row(
                    year=2026,
                    semester=1,
                    code="HIS900",
                    title="컴퓨터개론",
                    professor="자료",
                ),
            ],
        )
        courses = search_courses(conn, query="자료", limit=10)

    assert [course.code for course in courses] == ["CSE900", "CSE901", "HIS900", "GEN900"]


def test_search_courses_uses_year_semester_and_title_tiebreak_for_equal_rank(app_env):
    init_db()

    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                _course_row(year=2026, semester=1, code="DAT103", title="Data Structures"),
                _course_row(year=2027, semester=1, code="DAT100", title="Data Mining"),
                _course_row(year=2026, semester=1, code="DAT102", title="Data Analytics"),
                _course_row(year=2026, semester=2, code="DAT101", title="Data Models"),
            ],
        )
        courses = search_courses(conn, query="Data", limit=10)

    assert [course.code for course in courses] == ["DAT100", "DAT101", "DAT102", "DAT103"]


def test_load_place_alias_overrides_contract():
    overrides = _load_place_alias_overrides()

    assert overrides["central-library"]["aliases"] == ["중도"]
    assert overrides["central-library"]["display_name"] == "중앙도서관"
    assert "학생식당" in overrides["sophie-barat-hall"]["aliases"]
    assert "트러스트짐" in overrides["sophie-barat-hall"]["aliases"]
    assert "카페 보나" in overrides["sophie-barat-hall"]["aliases"]
    assert "부온 프란조" in overrides["sophie-barat-hall"]["aliases"]
    assert overrides["sophie-barat-hall"]["display_name"] == "학생회관"
    assert "학생센터" in overrides["student-center"]["aliases"]
    assert overrides["student-center"]["display_name"] == "학생회관"
    assert overrides["nicholls-hall"]["aliases"] == ["니콜스"]
    assert overrides["nicholls-hall"]["display_name"] == "니콜스관"
    assert overrides["nichols-hall"]["display_name"] == "니콜스관"
    assert overrides["kim-sou-hwan-hall"]["category"] == "building"
    assert overrides["kim-sou-hwan-hall"]["display_name"] == "K관"


def test_load_restaurant_search_aliases_contract():
    aliases = _load_restaurant_search_aliases()

    assert aliases["매머드익스프레스"] == ["매머드커피", "매머드 커피", "매머드"]
    assert "메가커피" in aliases["메가MGC커피"]
    assert "이디야" in aliases["이디야커피"]
    assert aliases["스타벅스"] == ["스타벅스", "starbucks"]
    assert aliases["커피빈"] == ["커피빈", "coffee bean"]
    assert aliases["투썸플레이스"] == ["투썸", "투썸플레이스", "투썸 플레이스"]
    assert aliases["빽다방"] == ["빽다방"]


def test_load_restaurant_search_noise_terms_contract():
    noise_terms = _load_restaurant_search_noise_terms()

    assert noise_terms["name_terms"] == ["주차장"]
    assert noise_terms["tag_terms"] == ["교통시설"]
    assert noise_terms["description_terms"] == ["주차장"]


def test_load_place_facility_keywords_contract():
    keywords = _load_place_facility_keywords()

    assert keywords["헬스장"] == ["트러스트짐"]
    assert "이마트24" in keywords["편의점"]
    assert "우리은행" in keywords["ATM"]
    assert "운동장" in keywords["체육관"]


def test_search_places_matches_facility_tenant_alias_from_override_taxonomy(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        places = search_places(conn, query="트러스트짐", limit=3)

    assert places
    assert places[0].slug == "student-center"
    assert places[0].name == "학생회관"


def test_search_places_matches_building_synonym_from_override_taxonomy(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        places = search_places(conn, query="학생센터", limit=3)

    assert places
    assert places[0].slug == "student-center"
    assert places[0].name == "학생회관"


def test_search_places_matches_generic_facility_nouns_to_related_buildings(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="student-center",
                    name="학생회관",
                    category="facility",
                    description="학생 편의시설이 많은 건물",
                    opening_hours={
                        "트러스트짐": "평일 07:00~22:30",
                        "편의점": "상시 07:00~24:00",
                        "교내복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                    },
                ),
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    description="기숙사 생활시설 건물",
                    opening_hours={
                        "이마트24 K관점": "상시 07:00~24:00",
                    },
                ),
                _place_row(
                    slug="great-field",
                    name="대운동장",
                    category="outdoor",
                    description="야외 운동 공간",
                    opening_hours={
                        "운동장": "상시 개방",
                    },
                ),
            ],
        )
        gym_places = search_places(conn, query="헬스장", limit=5)
        store_places = search_places(conn, query="편의점", limit=5)
        copy_places = search_places(conn, query="복사실", limit=5)
        atm_places = search_places(conn, query="ATM", limit=5)
        gymnasium_places = search_places(conn, query="체육관", limit=5)

    assert [place.slug for place in gym_places] == ["student-center"]
    assert [place.slug for place in store_places[:2]] == ["student-center", "dormitory-stephen"]
    assert [place.slug for place in copy_places] == ["student-center"]
    assert [place.slug for place in atm_places] == ["student-center"]
    assert [place.slug for place in gymnasium_places] == ["great-field"]


def test_search_places_generic_facility_nouns_prefer_building_then_facility_then_dormitory(
    app_env,
):
    init_db()
    shared_hours = {
        "이마트24": "상시 07:00~24:00",
        "교내복사실": "평일 08:50~19:00",
        "우리은행": "평일 09:00~16:00",
        "트러스트짐": "평일 07:00~22:30",
        "세탁소": "평일 09:00~18:00",
    }
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    description="기숙사 생활시설 건물",
                    opening_hours=shared_hours,
                ),
                _place_row(
                    slug="kim-sou-hwan-hall",
                    name="김수환관",
                    category="building",
                    aliases=["K관"],
                    description="강의동과 생활편의시설이 함께 있는 건물",
                    opening_hours=shared_hours,
                ),
                _place_row(
                    slug="student-center",
                    name="학생회관",
                    category="facility",
                    aliases=["학생센터"],
                    description="학생 편의시설이 많은 건물",
                    opening_hours=shared_hours,
                ),
            ],
        )
        gym_places = search_places(conn, query="헬스장", limit=5)
        store_places = search_places(conn, query="편의점", limit=5)
        copy_places = search_places(conn, query="복사실", limit=5)
        atm_places = search_places(conn, query="ATM", limit=5)
        laundry_places = search_places(conn, query="세탁소", limit=5)

    expected_order = ["kim-sou-hwan-hall", "student-center", "dormitory-stephen"]
    laundry_order = ["kim-sou-hwan-hall", "student-center", "dormitory-stephen"]
    assert [place.slug for place in gym_places[:3]] == expected_order
    assert [place.slug for place in store_places[:3]] == expected_order
    assert [place.slug for place in copy_places[:3]] == expected_order
    assert [place.slug for place in atm_places[:3]] == expected_order
    assert [place.slug for place in laundry_places[:3]] == laundry_order
    assert gym_places[0].matched_facility is not None
    assert gym_places[0].matched_facility.location_hint == "김수환관"
    assert store_places[0].matched_facility is not None
    assert store_places[0].matched_facility.location_hint == "김수환관"
    assert copy_places[0].matched_facility is not None
    assert copy_places[0].matched_facility.location_hint == "김수환관"
    assert atm_places[0].matched_facility is not None
    assert atm_places[0].matched_facility.location_hint == "김수환관"
    assert laundry_places[0].matched_facility is not None
    assert laundry_places[0].matched_facility.name == "세탁소"
    assert laundry_places[0].matched_facility.location_hint == "김수환관"
    assert laundry_places[0].matched_facility.opening_hours == "평일 09:00~18:00"


def test_search_places_generic_facility_nouns_attach_matched_facility_when_place_alias_ties(
    app_env,
):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="student-center",
                    name="학생회관",
                    category="facility",
                    aliases=["학생센터", "편의점"],
                    description="학생 편의시설이 많은 건물",
                ),
            ],
        )
        repo.replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "학생회관 편의점",
                    "category": None,
                    "phone": None,
                    "location_text": "학생회관 1층",
                    "hours_text": "상시 07:00~24:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        places = search_places(conn, query="편의점", limit=1)

    assert places
    assert places[0].slug == "student-center"
    assert places[0].matched_facility is not None
    assert places[0].matched_facility.name == "학생회관 편의점"
    assert places[0].matched_facility.location_hint == "학생회관 1층"
    assert places[0].matched_facility.opening_hours == "상시 07:00~24:00"


def test_refresh_campus_facilities_replaces_rows_and_maps_place_slugs(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    aliases=["K관"],
                    category="dormitory",
                ),
                _place_row(
                    slug="kim-sou-hwan-hall",
                    name="김수환관",
                    aliases=["김수환", "K관"],
                    category="building",
                ),
                _place_row(
                    slug="central-library",
                    name="중앙도서관",
                    aliases=["중도"],
                    category="library",
                ),
            ],
        )

        class FacilitySnapshotSource:
            def fetch(self):
                return "<facilities></facilities>"

            def parse(self, html: str, *, fetched_at: str):
                assert html == "<facilities></facilities>"
                return [
                    {
                        "facility_name": "교내복사실",
                        "category": "복사실",
                        "phone": "02-2164-4725",
                        "location": "K관 1층",
                        "hours_text": "평일 08:50~19:00 (토/일/공휴일휴무)",
                        "source_tag": "cuk_facilities",
                        "last_synced_at": fetched_at,
                    },
                    {
                        "facility_name": "카페드림",
                        "category": "카페",
                        "phone": "010-9517-9417",
                        "location": "중앙도서관 2층",
                        "hours_text": "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)",
                        "source_tag": "cuk_facilities",
                        "last_synced_at": fetched_at,
                    },
                ]

        refresh_campus_facilities_from_source(conn, source=FacilitySnapshotSource())
        rows = repo.list_campus_facilities(conn, limit=10)

    assert [row["facility_name"] for row in rows] == ["교내복사실", "카페드림"]
    assert rows[0]["phone"] == "02-2164-4725"
    assert rows[0]["location_text"] == "K관 1층"
    assert rows[0]["place_slug"] == "kim-sou-hwan-hall"
    assert rows[1]["phone"] == "010-9517-9417"
    assert rows[1]["place_slug"] == "central-library"


def test_search_places_sentence_queries_prefer_exact_facility_match_with_metadata(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="student-center",
                    name="학생회관",
                    category="facility",
                    aliases=["학회관", "트러스트짐"],
                    description="학생 편의시설이 많은 건물",
                ),
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    aliases=["K관"],
                    description="기숙사 생활시설 건물",
                ),
                _place_row(
                    slug="central-library",
                    name="중앙도서관",
                    category="library",
                    aliases=["중도"],
                    description="자료 열람과 시험 준비를 위한 핵심 공간",
                ),
            ],
        )
        repo.replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "K관 1층",
                    "hours_text": "평일 07:00~22:30 토 09:30~18:00 (일/공휴일휴무)",
                    "place_slug": "dormitory-stephen",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "K관 1층",
                    "hours_text": "평일 09:00~16:00 (토,일/공휴일휴무)",
                    "place_slug": "dormitory-stephen",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "facility_name": "카페드림",
                    "category": "카페",
                    "phone": "010-9517-9417",
                    "location_text": "중앙도서관 2층",
                    "hours_text": "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)",
                    "place_slug": "central-library",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
            ],
        )

        gym_places = search_places(conn, query="트러스트짐 어디야?", limit=1)
        bank_places = search_places(conn, query="우리은행 전화번호 알려줘", limit=1)
        cafe_places = search_places(conn, query="카페드림 어디야?", limit=1)
        library_places = search_places(conn, query="중앙도서관이 어디야?", limit=1)

    assert gym_places[0].slug == "dormitory-stephen"
    assert gym_places[0].matched_facility is not None
    assert gym_places[0].matched_facility.name == "트러스트짐"
    assert gym_places[0].matched_facility.location_hint == "K관 1층"
    assert gym_places[0].matched_facility.phone == "032-342-5406"

    assert bank_places[0].slug == "dormitory-stephen"
    assert bank_places[0].matched_facility is not None
    assert bank_places[0].matched_facility.name == "우리은행"
    assert bank_places[0].matched_facility.phone == "032-342-2641"

    assert cafe_places[0].slug == "central-library"
    assert cafe_places[0].matched_facility is not None
    assert cafe_places[0].matched_facility.name == "카페드림"
    assert cafe_places[0].matched_facility.location_hint == "중앙도서관 2층"

    assert library_places[0].slug == "central-library"
    assert library_places[0].matched_facility is None


def test_search_places_promotes_canonical_parent_place_for_k_hall_facilities(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    aliases=["K관"],
                    description="기숙사 생활시설 건물",
                ),
                _place_row(
                    slug="kim-sou-hwan-hall",
                    name="김수환관",
                    category="building",
                    aliases=["김수환", "K관"],
                    description="강의실과 생활 편의시설이 함께 있는 건물",
                ),
            ],
        )
        repo.replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "교내복사실",
                    "category": "복사실",
                    "phone": "02-2164-4725",
                    "location_text": "K관 1층",
                    "hours_text": "평일 08:50~19:00 (토/일/공휴일휴무)",
                    "place_slug": "kim-sou-hwan-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "K관 1층",
                    "hours_text": "평일 09:00~16:00 (토,일/공휴일휴무)",
                    "place_slug": "kim-sou-hwan-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "K관 1층",
                    "hours_text": "평일 07:00~22:30 토 09:30~18:00 (일/공휴일휴무)",
                    "place_slug": "kim-sou-hwan-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
            ],
        )

        copy_room_places = search_places(conn, query="복사실이 어디야?", limit=1)
        bank_places = search_places(conn, query="우리은행 전화번호 알려줘", limit=1)
        gym_places = search_places(conn, query="트러스트짐 어디야?", limit=1)
        k_hall_places = search_places(conn, query="K관 어디야?", limit=1)

    assert copy_room_places[0].slug == "kim-sou-hwan-hall"
    assert copy_room_places[0].name == "K관"
    assert copy_room_places[0].canonical_name == "김수환관"
    assert copy_room_places[0].matched_facility is not None
    assert copy_room_places[0].matched_facility.name == "교내복사실"
    assert copy_room_places[0].matched_facility.location_hint == "K관 1층"

    assert bank_places[0].slug == "kim-sou-hwan-hall"
    assert bank_places[0].name == "K관"
    assert bank_places[0].canonical_name == "김수환관"
    assert bank_places[0].matched_facility is not None
    assert bank_places[0].matched_facility.name == "우리은행"
    assert bank_places[0].matched_facility.phone == "032-342-2641"

    assert gym_places[0].slug == "kim-sou-hwan-hall"
    assert gym_places[0].name == "K관"
    assert gym_places[0].canonical_name == "김수환관"
    assert gym_places[0].matched_facility is not None
    assert gym_places[0].matched_facility.name == "트러스트짐"

    assert k_hall_places[0].slug == "kim-sou-hwan-hall"
    assert k_hall_places[0].name == "K관"
    assert k_hall_places[0].canonical_name == "김수환관"
    assert k_hall_places[0].matched_facility is None


def test_search_places_uses_source_backed_facility_fallback_when_snapshot_is_empty(
    app_env, monkeypatch
):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    aliases=["K관"],
                ),
            ],
        )

        class LiveFacilitySource:
            def __init__(self, url: str):
                self.url = url

            def fetch(self):
                return "<facilities></facilities>"

            def parse(self, html: str, *, fetched_at: str):
                assert html == "<facilities></facilities>"
                return [
                    {
                        "facility_name": "교내복사실",
                        "category": "복사실",
                        "phone": "02-2164-4725",
                        "location": "K관 1층",
                        "hours_text": "평일 08:50~19:00 (토/일/공휴일휴무)",
                        "source_tag": "cuk_facilities",
                        "last_synced_at": fetched_at,
                    }
                ]

        monkeypatch.setattr(services_module, "CampusFacilitiesSource", LiveFacilitySource)
        monkeypatch.setenv(
            "SONGSIM_DATABASE_URL",
            "postgresql://songsim:secret@db.example.com:5432/songsim_public",
        )
        clear_settings_cache()

        places = search_places(conn, query="복사실이 어디야?", limit=1)

    assert places[0].slug == "dormitory-stephen"
    assert places[0].matched_facility is not None
    assert places[0].matched_facility.name == "교내복사실"
    assert places[0].matched_facility.phone == "02-2164-4725"
    assert places[0].matched_facility.location_hint == "K관 1층"


def test_search_restaurants_matches_brand_alias_with_spacing_normalization(app_env):
    init_db()
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="mammoth",
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="cafe",
                    latitude=37.48556,
                    longitude=126.80379,
                ),
                _restaurant_row(
                    slug="mega",
                    name="메가MGC커피 부천가톨릭대점",
                    category="cafe",
                    latitude=37.48637,
                    longitude=126.80495,
                ),
                _restaurant_row(
                    slug="ediya",
                    name="이디야커피 가톨릭대점",
                    category="cafe",
                    latitude=37.48611,
                    longitude=126.80503,
                ),
            ],
        )
        items = search_restaurants(conn, query="매머드 커피", limit=3)

    assert [item.slug for item in items] == ["mammoth"]
    assert items[0].name == "매머드익스프레스 부천가톨릭대학교점"


def test_search_restaurants_matches_brand_alias_against_snapshot_name_variants(app_env):
    init_db()
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="mammoth",
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="cafe",
                    latitude=37.48556,
                    longitude=126.80379,
                ),
                _restaurant_row(
                    slug="mega",
                    name="메가MGC커피 부천가톨릭대점",
                    category="cafe",
                    latitude=37.48637,
                    longitude=126.80495,
                ),
                _restaurant_row(
                    slug="ediya",
                    name="이디야커피 가톨릭대점",
                    category="cafe",
                    latitude=37.48611,
                    longitude=126.80503,
                ),
            ],
        )
        mega_items = search_restaurants(conn, query="메가커피", limit=3)
        ediya_items = search_restaurants(conn, query="이디야", limit=3)

    assert [item.slug for item in mega_items] == ["mega"]
    assert [item.slug for item in ediya_items] == ["ediya"]


def test_search_restaurants_snapshot_hit_skips_live_fetch(app_env):
    init_db()
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="mammoth",
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="cafe",
                    latitude=37.48556,
                    longitude=126.80379,
                )
            ],
        )
        items = search_restaurants(
            conn,
            query="매머드커피",
            limit=5,
            kakao_client=ExplodingKakaoClient(),
        )

    assert [item.slug for item in items] == ["mammoth"]
    assert items[0].distance_meters is None
    assert items[0].estimated_walk_minutes is None


def test_search_restaurants_can_use_kakao_live_results_without_origin(app_env):
    init_db()
    seed_demo(force=True)

    class BrandKakaoClient:
        def __init__(self):
            self.calls: list[tuple[str, float | None, float | None, int]] = []

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            self.calls.append((query, x, y, radius))
            return [
                KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                )
            ]

    client = BrandKakaoClient()
    with connection() as conn:
        library = get_place(conn, "central-library")
        items = search_restaurants(
            conn,
            query="매머드커피",
            category="cafe",
            limit=5,
            kakao_client=client,
        )

    assert client.calls == [("매머드익스프레스", library.longitude, library.latitude, 15 * 75)]
    assert [item.name for item in items] == ["매머드익스프레스 부천가톨릭대학교점"]
    assert items[0].source_tag == "kakao_local"
    assert items[0].distance_meters is None
    assert items[0].estimated_walk_minutes is None


@pytest.mark.parametrize(
    ("query", "expected_query", "result_name"),
    [
        ("스타벅스", "스타벅스", "스타벅스 역곡역DT점"),
        ("커피빈", "커피빈", "커피빈 역곡점"),
        ("투썸", "투썸플레이스", "투썸플레이스 역곡역점"),
        ("빽다방", "빽다방", "빽다방 역곡남부역점"),
    ],
)
def test_search_restaurants_resolves_long_tail_brand_aliases_via_live_fallback(
    app_env,
    query,
    expected_query,
    result_name,
):
    init_db()
    seed_demo(force=True)

    class LongTailBrandClient:
        def __init__(self):
            self.calls: list[str] = []

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            self.calls.append(query)
            return [
                KakaoPlace(
                    name=result_name,
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 99",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="901",
                    place_url="https://place.map.kakao.com/901",
                )
            ]

    client = LongTailBrandClient()
    with connection() as conn:
        items = search_restaurants(
            conn,
            query=query,
            limit=5,
            category="cafe",
            kakao_client=client,
        )

    assert client.calls == [expected_query]
    assert [item.name for item in items] == [result_name]


def test_search_restaurants_expands_radius_when_initial_brand_search_is_empty_without_origin(
    app_env,
):
    init_db()
    seed_demo(force=True)

    class TwoStageBrandClient:
        def __init__(self):
            self.calls: list[tuple[str, int]] = []

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            self.calls.append((query, radius))
            assert x is not None and y is not None
            if radius == 15 * 75:
                return []
            assert radius == 5000
            return [
                KakaoPlace(
                    name="커피빈 역곡점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 70",
                    latitude=37.48621,
                    longitude=126.80491,
                    place_id="904",
                    place_url="https://place.map.kakao.com/904",
                )
            ]

    client = TwoStageBrandClient()
    with connection() as conn:
        items = search_restaurants(
            conn,
            query="커피빈",
            limit=5,
            kakao_client=client,
        )

    assert client.calls == [("커피빈", 15 * 75), ("커피빈", 5000)]
    assert [item.name for item in items] == ["커피빈 역곡점"]
    assert items[0].distance_meters is None
    assert items[0].estimated_walk_minutes is None


def test_search_restaurants_expands_radius_when_initial_brand_search_is_empty_with_origin(
    app_env,
):
    init_db()
    seed_demo(force=True)

    class TwoStageBrandClient:
        def __init__(self):
            self.calls: list[tuple[str, int]] = []

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            self.calls.append((query, radius))
            assert x is not None and y is not None
            if radius == 15 * 75:
                return []
            assert radius == 5000
            return [
                KakaoPlace(
                    name="커피빈 역곡점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 70",
                    latitude=37.48621,
                    longitude=126.80491,
                    place_id="904",
                    place_url="https://place.map.kakao.com/904",
                )
            ]

    client = TwoStageBrandClient()
    with connection() as conn:
        items = search_restaurants(
            conn,
            query="커피빈",
            origin="중도",
            limit=5,
            kakao_client=client,
        )

    assert client.calls == [("커피빈", 15 * 75), ("커피빈", 5000)]
    assert [item.name for item in items] == ["커피빈 역곡점"]
    assert items[0].distance_meters is not None
    assert items[0].estimated_walk_minutes is not None


def test_search_restaurants_uses_stale_extended_radius_cache_without_live_refetch(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    stale_now = datetime.fromisoformat("2026-03-14T20:30:00+09:00")
    monkeypatch.setattr("songsim_campus.services._now", lambda: stale_now)

    class TwoStageBrandClient:
        def __init__(self):
            self.calls: list[tuple[str, int]] = []

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            self.calls.append((query, radius))
            if radius == 15 * 75:
                return []
            raise AssertionError("stale extended-radius cache should be used before live refetch")

    with connection() as conn:
        repo.replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="brand:커피빈",
            radius_meters=5000,
            fetched_at="2026-03-14T12:00:00+09:00",
            rows=[
                {
                    "id": -1,
                    "slug": "coffee-bean-yeokgok",
                    "name": "커피빈 역곡점",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48621,
                    "longitude": 126.80491,
                    "tags": ["커피전문점", "커피빈"],
                    "description": "경기 부천시 원미구 지봉로 70",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-14T12:00:00+09:00",
                    "kakao_place_id": "904",
                    "source_url": "https://place.map.kakao.com/904",
                }
            ],
        )
        items = search_restaurants(
            conn,
            query="커피빈",
            limit=5,
            kakao_client=TwoStageBrandClient(),
        )

    assert [item.name for item in items] == ["커피빈 역곡점"]
    assert items[0].source_tag == "kakao_local_cache"
    assert items[0].distance_meters is None
    assert items[0].estimated_walk_minutes is None


def test_search_restaurants_filters_non_restaurant_noise_from_live_fallback(app_env):
    init_db()
    seed_demo(force=True)

    class StarbucksClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "스타벅스"
            return [
                KakaoPlace(
                    name="스타벅스 역곡역DT점 주차장",
                    category="교통시설 > 주차장",
                    address="경기 부천시 소사구 괴안동 112-25",
                    latitude=37.48345,
                    longitude=126.80935,
                    place_id="902",
                    place_url="https://place.map.kakao.com/902",
                ),
                KakaoPlace(
                    name="스타벅스 역곡역DT점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 소사구 경인로 485",
                    latitude=37.48354,
                    longitude=126.80929,
                    place_id="903",
                    place_url="https://place.map.kakao.com/903",
                ),
            ]

    with connection() as conn:
        items = search_restaurants(
            conn,
            query="스타벅스",
            limit=5,
            kakao_client=StarbucksClient(),
        )

    assert [item.name for item in items] == ["스타벅스 역곡역DT점"]


def test_search_restaurants_without_origin_prioritizes_campus_adjacent_live_match(app_env):
    init_db()
    seed_demo(force=True)

    class BrandKakaoClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "매머드익스프레스"
            return [
                KakaoPlace(
                    name="매머드익스프레스 가상의외부점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 소사구 경인옛로 37",
                    latitude=37.48186,
                    longitude=126.79612,
                    place_id="201",
                    place_url="https://place.map.kakao.com/201",
                ),
                KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                ),
            ]

    with connection() as conn:
        items = search_restaurants(
            conn,
            query="매머드커피",
            limit=5,
            category="cafe",
            kakao_client=BrandKakaoClient(),
        )

    assert [item.name for item in items[:2]] == [
        "매머드익스프레스 부천가톨릭대학교점",
        "매머드익스프레스 가상의외부점",
    ]
    assert all(item.distance_meters is None for item in items[:2])
    assert all(item.estimated_walk_minutes is None for item in items[:2])


def test_search_restaurants_without_origin_prioritizes_campus_adjacent_snapshot_match(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="mammoth-outer",
                    name="매머드익스프레스 가상의외부점",
                    category="cafe",
                    latitude=37.48186,
                    longitude=126.79612,
                ),
                _restaurant_row(
                    slug="mammoth-campus",
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="cafe",
                    latitude=37.48556,
                    longitude=126.80379,
                ),
            ],
        )
        items = search_restaurants(conn, query="매머드커피", limit=5)

    assert [item.slug for item in items[:2]] == ["mammoth-campus", "mammoth-outer"]
    assert all(item.distance_meters is None for item in items[:2])
    assert all(item.estimated_walk_minutes is None for item in items[:2])


def test_search_restaurants_with_origin_returns_distance_fields_on_live_fallback(app_env):
    init_db()
    seed_demo(force=True)

    class OriginAwareBrandClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "매머드익스프레스"
            assert x is not None and y is not None
            assert radius == 15 * 75
            return [
                KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                )
            ]

    with connection() as conn:
        items = search_restaurants(
            conn,
            query="매머드커피",
            origin="중도",
            limit=5,
            kakao_client=OriginAwareBrandClient(),
        )

    assert [item.name for item in items] == ["매머드익스프레스 부천가톨릭대학교점"]
    assert items[0].distance_meters is not None
    assert items[0].estimated_walk_minutes is not None


def test_search_restaurants_uses_stale_cache_when_live_fetch_fails(app_env, monkeypatch):
    init_db()
    seed_demo(force=True)
    old_now = datetime.fromisoformat("2026-03-14T12:00:00+09:00")
    stale_now = datetime.fromisoformat("2026-03-14T20:30:00+09:00")

    class BrandKakaoClient:
        calls = 0

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            type(self).calls += 1
            assert query == "매머드익스프레스"
            return [
                KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                )
            ]

    monkeypatch.setattr("songsim_campus.services._now", lambda: old_now)
    with connection() as conn:
        first = search_restaurants(
            conn,
            query="매머드커피",
            limit=5,
            kakao_client=BrandKakaoClient(),
        )

    monkeypatch.setattr("songsim_campus.services._now", lambda: stale_now)
    with connection() as conn:
        second = search_restaurants(
            conn,
            query="매머드커피",
            limit=5,
            kakao_client=ExplodingKakaoClient(),
        )

    assert BrandKakaoClient.calls == 1
    assert [item.name for item in first] == [item.name for item in second]
    assert first[0].source_tag == "kakao_local"
    assert second[0].source_tag == "kakao_local_cache"
    assert second[0].distance_meters is None
    assert second[0].estimated_walk_minutes is None


def test_search_restaurants_live_fallback_applies_category_filter(app_env):
    init_db()
    seed_demo(force=True)

    class BrandKakaoClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            return [
                KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                )
            ]

    with connection() as conn:
        items = search_restaurants(
            conn,
            query="매머드커피",
            category="korean",
            limit=5,
            kakao_client=BrandKakaoClient(),
        )

    assert items == []


def test_find_nearby_restaurants_sorted(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        items = find_nearby_restaurants(conn, origin='central-library', walk_minutes=20)
    assert items
    walk_minutes = [item.estimated_walk_minutes for item in items]
    assert walk_minutes == sorted(walk_minutes)


def test_find_nearby_restaurants_accepts_origin_alias(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        slug_items = find_nearby_restaurants(
            conn,
            origin="central-library",
            walk_minutes=15,
            limit=3,
        )
        alias_items = find_nearby_restaurants(conn, origin="중도", walk_minutes=15, limit=3)

    assert [item.name for item in alias_items] == [item.name for item in slug_items]
    assert all(item.origin == "central-library" for item in alias_items)


def test_find_nearby_restaurants_accepts_facility_alias_as_origin(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        slug_items = find_nearby_restaurants(
            conn,
            origin="student-center",
            walk_minutes=15,
            limit=3,
        )
        alias_items = find_nearby_restaurants(conn, origin="학생식당", walk_minutes=15, limit=3)

    assert [item.name for item in alias_items] == [item.name for item in slug_items]
    assert all(item.origin == "student-center" for item in alias_items)


def test_find_nearby_restaurants_alias_origin_reuses_same_fresh_kakao_cache(app_env):
    init_db()
    seed_demo(force=True)
    client = FakeKakaoClient()

    class ShouldNotBeCalledKakaoClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            raise AssertionError("alias origin should resolve to the same fresh nearby cache key")

    with connection() as conn:
        slug_items = find_nearby_restaurants(
            conn,
            origin="central-library",
            category="korean",
            walk_minutes=15,
            limit=2,
            kakao_client=client,
        )
        alias_items = find_nearby_restaurants(
            conn,
            origin="중도",
            category="korean",
            walk_minutes=15,
            limit=2,
            kakao_client=ShouldNotBeCalledKakaoClient(),
        )

    assert client.calls == 1
    assert [item.name for item in alias_items] == [item.name for item in slug_items]
    assert all(item.origin == "central-library" for item in alias_items)
    assert all(item.source_tag == "kakao_local_cache" for item in alias_items)


def test_list_estimated_empty_classrooms_resolves_building_alias_and_sorts_available_rooms(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE110",
                    "title": "컴퓨팅사고",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 2,
                    "period_end": 3,
                    "room": "N101",
                    "raw_schedule": "월2~3(N101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE332",
                    "title": "데이터베이스",
                    "professor": "김가톨",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "월5~6(N201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE210",
                    "title": "알고리즘",
                    "professor": "박성심",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "화",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "N301",
                    "raw_schedule": "화1~2(N301)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        evaluated_at = datetime.fromisoformat("2026-03-16T10:15:00+09:00")
        by_name = list_estimated_empty_classrooms(conn, building="니콜스관", at=evaluated_at)
        by_alias = list_estimated_empty_classrooms(conn, building="N관", at=evaluated_at)

    assert by_name.building.slug == "nichols-hall"
    assert by_alias.building.slug == "nichols-hall"
    assert by_name.evaluated_at == "2026-03-16T10:15:00+09:00"
    assert by_name.estimate_note.startswith("공식 시간표 기준 예상 공실입니다.")
    assert [item.room for item in by_name.items] == ["N301", "N201"]
    assert [item.room for item in by_alias.items] == ["N301", "N201"]
    assert all(item.available_now is True for item in by_name.items)
    assert by_name.items[0].next_occupied_at is None
    assert by_name.items[0].next_course_summary is None
    assert by_name.items[1].next_occupied_at == "2026-03-16T13:00:00+09:00"
    assert "데이터베이스" in (by_name.items[1].next_course_summary or "")
    assert "월5~6(N201)" in (by_name.items[1].next_course_summary or "")


def test_list_estimated_empty_classrooms_returns_empty_with_note_when_building_has_no_room_data(
    app_env,
):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE332",
                    "title": "데이터베이스",
                    "professor": "김가톨",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "월5~6(N201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        payload = list_estimated_empty_classrooms(
            conn,
            building="김수환관",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )

    assert payload.building.slug == "kim-sou-hwan-hall"
    assert payload.items == []
    assert "시간표 데이터를 찾지 못했습니다" in payload.estimate_note


def test_list_estimated_empty_classrooms_accepts_colloquial_building_alias(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE332",
                    "title": "데이터베이스",
                    "professor": "김가톨",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "월5~6(N201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        payload = list_estimated_empty_classrooms(
            conn,
            building="니콜스",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )

    assert payload.building.slug == "nichols-hall"
    assert payload.items[0].room == "N201"


def test_list_estimated_empty_classrooms_prefers_short_query_building_preference_for_k_hall(
    app_env,
):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    aliases=["K관"],
                    description="기숙사 생활시설 건물",
                ),
                _place_row(
                    slug="kim-sou-hwan-hall",
                    name="김수환관",
                    category="building",
                    aliases=["김수환", "K관"],
                    description="강의실과 연구실이 있는 건물",
                ),
            ],
        )
        repo.replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE420",
                    "title": "알고리즘",
                    "professor": "홍길동",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "K201",
                    "raw_schedule": "월5~6(K201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        payload = list_estimated_empty_classrooms(
            conn,
            building="K관",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )

    assert payload.building.slug == "kim-sou-hwan-hall"
    assert [item.room for item in payload.items] == ["K201"]


def test_list_estimated_empty_classrooms_bounds_place_lookups_by_unique_room_set(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    synthetic_courses: list[dict[str, object]] = []
    for index in range(60):
        room_number = 100 + index
        synthetic_courses.append(
            {
                "year": 2026,
                "semester": 1,
                "code": f"CSE{room_number}",
                "title": f"니콜스 강의 {index}",
                "professor": "테스트교수",
                "department": "컴퓨터정보공학부",
                "section": "01",
                "day_of_week": "화",
                "period_start": 1,
                "period_end": 2,
                "room": f"N{room_number}",
                "raw_schedule": f"화1~2(N{room_number})",
                "source_tag": "test",
                "last_synced_at": "2026-03-13T09:00:00+09:00",
            }
        )
        synthetic_courses.append(
            {
                "year": 2026,
                "semester": 1,
                "code": f"MAT{room_number}",
                "title": f"김수환 강의 {index}",
                "professor": "테스트교수",
                "department": "수학과",
                "section": "01",
                "day_of_week": "화",
                "period_start": 1,
                "period_end": 2,
                "room": f"K{room_number}",
                "raw_schedule": f"화1~2(K{room_number})",
                "source_tag": "test",
                "last_synced_at": "2026-03-13T09:00:00+09:00",
            }
        )

    with connection() as conn:
        repo.replace_courses(conn, synthetic_courses)

        list_places_calls = 0
        original_list_places = repo.list_places

        def counting_list_places(*args, **kwargs):
            nonlocal list_places_calls
            list_places_calls += 1
            return original_list_places(*args, **kwargs)

        monkeypatch.setattr(repo, "list_places", counting_list_places)

        payload = list_estimated_empty_classrooms(
            conn,
            building="N관",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
            limit=100,
        )

    assert list_places_calls <= 2
    assert payload.building.slug == "nichols-hall"
    assert len(payload.items) == 60
    assert all(item.room.startswith("N") for item in payload.items)


def test_list_estimated_empty_classrooms_rejects_non_classroom_place(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn, pytest.raises(InvalidRequestError, match="강의실 기반 건물"):
        list_estimated_empty_classrooms(
            conn,
            building="정문",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )


def test_list_latest_notices_employment_filter_includes_legacy_career_rows(app_env):
    init_db()
    with connection() as conn:
        repo.replace_notices(
            conn,
            [
                {
                    "title": "진로취업상담 안내",
                    "category": "career",
                    "published_at": "2026-03-12",
                    "summary": "",
                    "labels": ["취창업"],
                    "source_url": "https://example.edu/career",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "title": "채용 설명회 안내",
                    "category": "employment",
                    "published_at": "2026-03-13",
                    "summary": "",
                    "labels": ["취업"],
                    "source_url": "https://example.edu/employment",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        employment_items = list_latest_notices(conn, category="employment", limit=10)
        career_items = list_latest_notices(conn, category="career", limit=10)

    assert [item.title for item in employment_items] == [
        "채용 설명회 안내",
        "진로취업상담 안내",
    ]
    assert [item.title for item in career_items] == [
        "채용 설명회 안내",
        "진로취업상담 안내",
    ]


def test_list_latest_notices_normalizes_public_display_categories(app_env):
    init_db()
    with connection() as conn:
        repo.replace_notices(
            conn,
            [
                {
                    "title": "중앙도서관 자리 안내",
                    "category": "place",
                    "published_at": "2026-03-12",
                    "summary": "",
                    "labels": ["도서관"],
                    "source_url": "https://example.edu/place",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "title": "채용 설명회 안내",
                    "category": "career",
                    "published_at": "2026-03-13",
                    "summary": "",
                    "labels": ["취업"],
                    "source_url": "https://example.edu/career",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "title": "알 수 없는 분류 안내",
                    "category": "mystery",
                    "published_at": "2026-03-11",
                    "summary": "",
                    "labels": [],
                    "source_url": "https://example.edu/mystery",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        notices = list_latest_notices(conn, limit=10)

    assert [(item.title, item.category) for item in notices] == [
        ("채용 설명회 안내", "employment"),
        ("중앙도서관 자리 안내", "general"),
        ("알 수 없는 분류 안내", "general"),
    ]


def test_list_estimated_empty_classrooms_prefers_official_realtime_data_when_available(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE110",
                    "title": "컴퓨팅사고",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 2,
                    "period_end": 3,
                    "room": "N101",
                    "raw_schedule": "월2~3(N101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE332",
                    "title": "데이터베이스",
                    "professor": "김가톨",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "월5~6(N201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    class RealtimeSource:
        def fetch_availability(self, *, building, at, year, semester):
            assert building.slug == "nichols-hall"
            assert year == 2026
            assert semester == 1
            return [
                {
                    "room": "N101",
                    "available_now": True,
                    "source_observed_at": "2026-03-16T10:10:00+09:00",
                },
                {
                    "room": "N201",
                    "available_now": False,
                    "source_observed_at": "2026-03-16T10:10:00+09:00",
                },
            ]

    monkeypatch.setattr(
        "songsim_campus.services._get_official_classroom_availability_source",
        lambda: RealtimeSource(),
    )

    with connection() as conn:
        payload = list_estimated_empty_classrooms(
            conn,
            building="니콜스관",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )

    assert [item.room for item in payload.items] == ["N101"]
    assert payload.items[0].availability_mode == "realtime"
    assert payload.items[0].source_observed_at == "2026-03-16T10:10:00+09:00"
    assert "공식 실시간 공실" in payload.estimate_note


def test_list_estimated_empty_classrooms_falls_back_per_room_when_realtime_coverage_is_partial(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE332",
                    "title": "데이터베이스",
                    "professor": "김가톨",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "월5~6(N201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE210",
                    "title": "알고리즘",
                    "professor": "박성심",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "화",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "N301",
                    "raw_schedule": "화1~2(N301)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    class PartialRealtimeSource:
        def fetch_availability(self, *, building, at, year, semester):
            return [
                {
                    "room": "N201",
                    "available_now": True,
                    "source_observed_at": "2026-03-16T10:10:00+09:00",
                }
            ]

    monkeypatch.setattr(
        "songsim_campus.services._get_official_classroom_availability_source",
        lambda: PartialRealtimeSource(),
    )

    with connection() as conn:
        payload = list_estimated_empty_classrooms(
            conn,
            building="니콜스관",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )

    assert [item.room for item in payload.items] == ["N301", "N201"]
    assert payload.items[0].availability_mode == "estimated"
    assert payload.items[1].availability_mode == "realtime"
    assert "함께 사용합니다" in payload.estimate_note


def test_list_estimated_empty_classrooms_falls_back_to_estimated_when_realtime_source_fails(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)

    class BrokenRealtimeSource:
        def fetch_availability(self, *, building, at, year, semester):
            raise RuntimeError("official classroom source failed")

    monkeypatch.setattr(
        "songsim_campus.services._get_official_classroom_availability_source",
        lambda: BrokenRealtimeSource(),
    )

    with connection() as conn:
        payload = list_estimated_empty_classrooms(
            conn,
            building="니콜스관",
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )

    assert payload.items
    assert all(item.availability_mode == "estimated" for item in payload.items)
    assert "조회에 실패해" in payload.estimate_note


def test_find_nearby_restaurants_uses_campus_graph_for_external_routes(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="gate-bap",
                    name="정문백반",
                    latitude=37.48590,
                    longitude=126.80282,
                    source_tag="kakao_local",
                )
            ],
        )
        items = find_nearby_restaurants(conn, origin="central-library", walk_minutes=15)

    assert len(items) == 1
    assert items[0].estimated_walk_minutes == 6
    assert items[0].distance_meters is not None


def test_find_nearby_restaurants_fall_back_to_direct_distance_when_origin_is_not_in_graph(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "annex-lobby",
                    "name": "별관로비",
                    "category": "facility",
                    "aliases": [],
                    "description": "",
                    "latitude": 37.48590,
                    "longitude": 126.80282,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="gate-bap",
                    name="정문백반",
                    latitude=37.48590,
                    longitude=126.80282,
                    source_tag="kakao_local",
                )
            ],
        )
        items = find_nearby_restaurants(conn, origin="annex-lobby", walk_minutes=15)

    assert len(items) == 1
    assert items[0].estimated_walk_minutes == 1


def test_parse_campus_walk_graph_rejects_invalid_edges():
    with pytest.raises(ValueError, match="unknown node"):
        _parse_campus_walk_graph(
            {
                "nodes": ["central-library", "main-gate"],
                "edges": [{"from": "central-library", "to": "north-gate", "walk_minutes": 3}],
            }
        )

    with pytest.raises(ValueError, match="positive"):
        _parse_campus_walk_graph(
            {
                "nodes": ["central-library", "main-gate"],
                "edges": [{"from": "central-library", "to": "main-gate", "walk_minutes": 0}],
            }
        )


def test_find_nearby_restaurants_raises_for_unknown_origin(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn, pytest.raises(NotFoundError):
        find_nearby_restaurants(conn, origin='unknown-place')


def test_find_nearby_restaurants_raises_for_ambiguous_origin_alias(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "library-a",
                    "name": "중앙도서관A",
                    "category": "library",
                    "aliases": ["중도"],
                    "description": "",
                    "latitude": 37.48643,
                    "longitude": 126.80164,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "library-b",
                    "name": "중앙도서관B",
                    "category": "library",
                    "aliases": ["중도"],
                    "description": "",
                    "latitude": 37.48653,
                    "longitude": 126.80174,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="test-bap",
                    name="테스트백반",
                    latitude=37.4866,
                    longitude=126.8018,
                )
            ],
        )

        with pytest.raises(InvalidRequestError, match="Ambiguous origin"):
            find_nearby_restaurants(conn, origin="중도", walk_minutes=15)


def test_find_nearby_restaurants_prefers_short_query_origin_preference_for_k_hall(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                _place_row(
                    slug="dormitory-stephen",
                    name="스테파노기숙사",
                    category="dormitory",
                    aliases=["K관"],
                    description="기숙사 생활시설 건물",
                    latitude=37.4851,
                    longitude=126.8032,
                ),
                _place_row(
                    slug="kim-sou-hwan-hall",
                    name="김수환관",
                    category="building",
                    aliases=["김수환", "K관"],
                    description="강의실과 연구실이 있는 건물",
                    latitude=37.4863,
                    longitude=126.8012,
                ),
            ],
        )
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="k-hall-cafe",
                    name="K관카페",
                    category="cafe",
                    latitude=37.48631,
                    longitude=126.80121,
                )
            ],
        )

        items = find_nearby_restaurants(conn, origin="K관", walk_minutes=5, limit=3)

    assert [item.slug for item in items] == ["k-hall-cafe"]


def test_find_nearby_restaurants_raises_when_origin_has_no_coordinates(app_env):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "mystery-hall",
                    "name": "미스터리관",
                    "category": "building",
                    "aliases": [],
                    "description": "",
                    "latitude": None,
                    "longitude": None,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    with connection() as conn, pytest.raises(NotFoundError):
        find_nearby_restaurants(conn, origin='mystery-hall')


class FakeKakaoClient:
    def __init__(self):
        self.calls = 0

    def search_sync(
        self,
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int = 1000,
    ):
        self.calls += 1
        assert query == '한식'
        assert x is not None and y is not None
        assert radius > 0
        return [
            KakaoPlace(
                name='가톨릭백반',
                category='음식점 > 한식',
                address='경기 부천시 원미구',
                latitude=37.48674,
                longitude=126.80182,
                place_id='1',
                place_url='https://place.map.kakao.com/1',
            ),
            KakaoPlace(
                name='성심돈까스',
                category='음식점 > 한식',
                address='경기 부천시 원미구',
                latitude=37.48691,
                longitude=126.80114,
                place_id='2',
                place_url='https://place.map.kakao.com/2',
            ),
        ]


def test_find_nearby_restaurants_can_use_kakao_live_results(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        items = find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=FakeKakaoClient(),
        )

    assert [item.name for item in items] == ['가톨릭백반', '성심돈까스']
    assert all(item.source_tag == 'kakao_local' for item in items)
    assert all(item.origin == 'central-library' for item in items)


class ExplodingKakaoClient:
    def search_sync(
        self,
        query: str,
        *,
        x: float | None = None,
        y: float | None = None,
        radius: int = 1000,
    ):
        raise httpx.HTTPError('boom')


def test_find_nearby_restaurants_reuses_fresh_kakao_cache_without_refetch(app_env):
    init_db()
    seed_demo(force=True)
    client = FakeKakaoClient()

    with connection() as conn:
        first = find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=client,
        )
        second = find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=ExplodingKakaoClient(),
        )

    assert client.calls == 1
    assert [item.name for item in first] == [item.name for item in second]
    assert all(item.source_tag == 'kakao_local' for item in first)
    assert all(item.source_tag == 'kakao_local_cache' for item in second)


def test_find_nearby_restaurants_prefers_stale_cache_without_live_refetch(app_env, monkeypatch):
    init_db()
    seed_demo(force=True)
    old_now = datetime.fromisoformat('2026-03-14T12:00:00+09:00')
    stale_now = datetime.fromisoformat('2026-03-14T20:30:00+09:00')
    client = FakeKakaoClient()

    class ShouldNotBeCalledKakaoClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            raise AssertionError("stale cache should be returned before live Kakao refetch")

    monkeypatch.setattr('songsim_campus.services._now', lambda: old_now)
    with connection() as conn:
        first = find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=client,
        )

    monkeypatch.setattr('songsim_campus.services._now', lambda: stale_now)
    with connection() as conn:
        second = find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=ShouldNotBeCalledKakaoClient(),
        )

    assert client.calls == 1
    assert [item.name for item in first] == [item.name for item in second]
    assert all(item.source_tag == 'kakao_local_cache' for item in second)


def test_find_nearby_restaurants_falls_back_to_local_restaurants_when_cache_expired_and_live_fails(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    old_now = datetime.fromisoformat('2026-03-10T12:00:00+09:00')
    expired_now = datetime.fromisoformat('2026-03-14T20:30:00+09:00')

    monkeypatch.setattr('songsim_campus.services._now', lambda: old_now)
    with connection() as conn:
        find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=FakeKakaoClient(),
        )

    monkeypatch.setattr('songsim_campus.services._now', lambda: expired_now)
    with connection() as conn:
        items = find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=ExplodingKakaoClient(),
        )

    assert items
    assert all(item.source_tag not in {'kakao_local', 'kakao_local_cache'} for item in items)


def test_find_nearby_restaurants_cache_key_ignores_budget_open_now_and_limit(app_env):
    init_db()
    seed_demo(force=True)
    client = FakeKakaoClient()

    with connection() as conn:
        find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=client,
            limit=10,
        )
        filtered = find_nearby_restaurants(
            conn,
            origin='central-library',
            category='korean',
            walk_minutes=15,
            kakao_client=ExplodingKakaoClient(),
            budget_max=15000,
            open_now=True,
            limit=1,
        )

    assert client.calls == 1
    assert filtered == []


def test_find_nearby_restaurants_budget_max_requires_price_evidence(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        library = get_place(conn, "central-library")
        replace_restaurants(
            conn,
            [
                {
                    "slug": "budget-kimbap",
                    "name": "버짓김밥",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": library.latitude + 0.0001,
                    "longitude": library.longitude + 0.0001,
                    "tags": ["한식"],
                    "description": "가격 정보가 있는 김밥집",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "mystery-price-cafe",
                    "name": "가격미상카페",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": library.latitude + 0.0002,
                    "longitude": library.longitude + 0.0002,
                    "tags": ["카페"],
                    "description": "가격 정보가 없는 후보",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "expensive-pasta",
                    "name": "비싼파스타",
                    "category": "western",
                    "min_price": 14000,
                    "max_price": 18000,
                    "latitude": library.latitude + 0.0003,
                    "longitude": library.longitude + 0.0003,
                    "tags": ["양식"],
                    "description": "예산 초과 후보",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        items = find_nearby_restaurants(
            conn,
            origin="central-library",
            budget_max=10000,
            walk_minutes=15,
            limit=10,
        )

    assert [item.slug for item in items] == ["budget-kimbap"]


@pytest.mark.parametrize(
    ("hours_text", "at", "expected"),
    [
        ("중식 11:30 ~ 14:00", "2026-03-16T12:00:00+09:00", True),
        ("08:00-21:00", "2026-03-16T07:00:00+09:00", False),
        ("상시 07:00~24:00", "2026-03-16T23:30:00+09:00", True),
        ("23:00~02:00", "2026-03-16T23:30:00+09:00", True),
        ("23:00~02:00", "2026-03-17T01:30:00+09:00", True),
        ("토 23:00~02:00", "2026-03-22T01:30:00+09:00", True),
        ("평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)", "2026-03-15T11:00:00+09:00", False),
        ("mon-fri 08:30-22:00", "2026-03-16T09:00:00+09:00", True),
        ("24시간 운영", "2026-03-15T03:00:00+09:00", True),
        ("휴무", "2026-03-16T12:00:00+09:00", False),
        ("문의", "2026-03-16T12:00:00+09:00", None),
    ],
)
def test_find_nearby_restaurants_marks_open_now_from_facility_hours(
    app_env,
    hours_text,
    at,
    expected,
):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        library = get_place(conn, "central-library")
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="cafe-dream",
                    name="카페드림",
                    latitude=library.latitude + 0.0001,
                    longitude=library.longitude + 0.0001,
                    category="cafe",
                )
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"카페드림": hours_text},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )

        items = find_nearby_restaurants(
            conn,
            origin="central-library",
            walk_minutes=15,
            at=datetime.fromisoformat(at),
        )

    assert items[0].open_now is expected


def test_find_nearby_restaurants_open_now_filters_closed_and_unknown_candidates(app_env):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        library = get_place(conn, "central-library")
        replace_restaurants(
            conn,
            [
                _restaurant_row(
                    slug="cafe-dream",
                    name="카페드림",
                    latitude=library.latitude + 0.0001,
                    longitude=library.longitude + 0.0001,
                    category="cafe",
                ),
                _restaurant_row(
                    slug="unknown-bap",
                    name="알수없음식당",
                    latitude=library.latitude + 0.0002,
                    longitude=library.longitude + 0.0002,
                ),
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"카페드림": "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)"},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )

        all_items = find_nearby_restaurants(
            conn,
            origin="central-library",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-15T11:00:00+09:00"),
        )
        filtered = find_nearby_restaurants(
            conn,
            origin="central-library",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-15T11:00:00+09:00"),
            open_now=True,
        )

    open_by_name = {item.name: item.open_now for item in all_items}
    assert open_by_name["카페드림"] is False
    assert open_by_name["알수없음식당"] is None
    assert filtered == []


def test_find_nearby_restaurants_prefers_official_facility_hours_before_kakao_detail(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    now = datetime.fromisoformat("2026-03-14T12:00:00+09:00")
    monkeypatch.setattr("songsim_campus.services._now", lambda: now)
    calls = {"detail": 0}

    class ExplodingDetailClient:
        def fetch_sync(self, place_id: str):
            calls["detail"] += 1
            raise AssertionError("detail client should not be used for official facility matches")

    monkeypatch.setattr("songsim_campus.services.KakaoPlaceDetailClient", ExplodingDetailClient)

    with connection() as conn:
        repo.replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="카페",
            radius_meters=15 * 75,
            fetched_at="2026-03-14T10:00:00+09:00",
            rows=[
                {
                    "id": -1,
                    "slug": "kakao-cafe-dream",
                    "name": "카페드림",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48695,
                    "longitude": 126.79995,
                    "tags": ["카페"],
                    "description": "테스트 카페",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-14T10:00:00+09:00",
                    "kakao_place_id": "242731511",
                    "source_url": "https://place.map.kakao.com/242731511",
                }
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"카페드림": "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)"},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )

        items = find_nearby_restaurants(
            conn,
            origin="central-library",
            category="cafe",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-15T11:00:00+09:00"),
        )

    assert items[0].open_now is False
    assert calls["detail"] == 0


def test_find_nearby_restaurants_reuses_fresh_kakao_hours_cache(app_env, monkeypatch):
    init_db()
    seed_demo(force=True)
    now = datetime.fromisoformat("2026-03-14T12:00:00+09:00")
    monkeypatch.setattr("songsim_campus.services._now", lambda: now)
    calls = {"detail": 0}

    class ExplodingDetailClient:
        def fetch_sync(self, place_id: str):
            calls["detail"] += 1
            raise AssertionError("fresh hours cache should be used before detail fetch")

    monkeypatch.setattr("songsim_campus.services.KakaoPlaceDetailClient", ExplodingDetailClient)

    with connection() as conn:
        repo.replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="한식",
            radius_meters=15 * 75,
            fetched_at="2026-03-14T10:00:00+09:00",
            rows=[
                {
                    "id": -1,
                    "slug": "kakao-gatolic-bap",
                    "name": "가톨릭백반",
                    "category": "korean",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48674,
                    "longitude": 126.80182,
                    "tags": ["한식"],
                    "description": "경기 부천시 원미구",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-14T10:00:00+09:00",
                    "kakao_place_id": "242731511",
                    "source_url": "https://place.map.kakao.com/242731511",
                }
            ],
        )
        repo.upsert_restaurant_hours_cache(
            conn,
            kakao_place_id="242731511",
            source_url="https://place.map.kakao.com/242731511",
            raw_payload=_fixture_json("kakao_place_detail.json"),
            opening_hours={
                "mon": "08:00 ~ 21:00",
                "tue": "08:00 ~ 21:00",
                "wed": "08:00 ~ 21:00",
                "thu": "08:00 ~ 21:00",
                "fri": "08:00 ~ 21:00",
                "sat": "10:00 ~ 18:00",
                "sun": "휴무",
            },
            fetched_at="2026-03-14T10:00:00+09:00",
        )

        items = find_nearby_restaurants(
            conn,
            origin="central-library",
            category="korean",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-16T09:00:00+09:00"),
        )

    assert items[0].open_now is True
    assert calls["detail"] == 0


def test_find_nearby_restaurants_fetches_and_reuses_kakao_detail_hours(app_env):
    init_db()
    seed_demo(force=True)

    class DetailAwareKakaoClient:
        calls = 0

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            type(self).calls += 1
            return [
                KakaoPlace(
                    name="가톨릭백반",
                    category="음식점 > 한식",
                    address="경기 부천시 원미구",
                    latitude=37.48674,
                    longitude=126.80182,
                    place_id="242731511",
                    place_url="https://place.map.kakao.com/242731511",
                )
            ]

    class DetailClient:
        calls = 0

        def fetch_sync(self, place_id: str):
            type(self).calls += 1
            assert place_id == "242731511"
            return _fixture_json("kakao_place_detail.json")

    class ExplodingDetailClient:
        calls = 0

        def fetch_sync(self, place_id: str):
            type(self).calls += 1
            raise AssertionError("hours cache should be reused on the second call")

    with connection() as conn:
        first = find_nearby_restaurants(
            conn,
            origin="central-library",
            category="korean",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-17T10:00:00+09:00"),
            kakao_client=DetailAwareKakaoClient(),
            kakao_place_detail_client=DetailClient(),
        )
        second = find_nearby_restaurants(
            conn,
            origin="central-library",
            category="korean",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-17T10:00:00+09:00"),
            kakao_client=ExplodingKakaoClient(),
            kakao_place_detail_client=ExplodingDetailClient(),
        )

    assert DetailAwareKakaoClient.calls == 1
    assert DetailClient.calls == 1
    assert ExplodingDetailClient.calls == 0
    assert first[0].open_now is True
    assert second[0].open_now is True


def test_find_nearby_restaurants_uses_stale_kakao_hours_cache_when_detail_fetch_fails(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    now = datetime.fromisoformat("2026-03-18T10:00:00+09:00")
    monkeypatch.setattr("songsim_campus.services._now", lambda: now)

    class BrokenDetailClient:
        def fetch_sync(self, place_id: str):
            raise httpx.HTTPError("detail fetch failed")

    with connection() as conn:
        repo.replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="한식",
            radius_meters=15 * 75,
            fetched_at="2026-03-18T09:00:00+09:00",
            rows=[
                {
                    "id": -1,
                    "slug": "kakao-gatolic-bap",
                    "name": "가톨릭백반",
                    "category": "korean",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48674,
                    "longitude": 126.80182,
                    "tags": ["한식"],
                    "description": "경기 부천시 원미구",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-18T09:00:00+09:00",
                    "kakao_place_id": "242731511",
                    "source_url": "https://place.map.kakao.com/242731511",
                }
            ],
        )
        repo.upsert_restaurant_hours_cache(
            conn,
            kakao_place_id="242731511",
            source_url="https://place.map.kakao.com/242731511",
            raw_payload=_fixture_json("kakao_place_detail.json"),
            opening_hours={"wed": "08:00 ~ 21:00"},
            fetched_at="2026-03-15T10:00:00+09:00",
        )

        items = find_nearby_restaurants(
            conn,
            origin="central-library",
            category="korean",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-18T10:00:00+09:00"),
            kakao_place_detail_client=BrokenDetailClient(),
        )

    assert items[0].open_now is True


class FakeCampusMapSource:
    def fetch_place_list(self, *, campus: str = '1'):
        assert campus == '1'
        return 'payload'

    def parse_place_list(self, payload: str, *, fetched_at: str):
        assert payload == 'payload'
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        return [
            {
                'slug': 'central-library',
                'name': '중앙도서관',
                'category': 'library',
                'aliases': ['도서관'],
                'description': '실제 캠퍼스맵 데이터',
                'latitude': 37.486853,
                'longitude': 126.799802,
                'opening_hours': {},
                'source_tag': 'cuk_campus_map',
                'last_synced_at': fetched_at,
            },
            {
                'slug': 'sophie-barat-hall',
                'name': '학생미래인재관',
                'category': 'building',
                'aliases': ['B관'],
                'description': '학생식당이 있는 건물',
                'latitude': 37.486466,
                'longitude': 126.801297,
                'opening_hours': {},
                'source_tag': 'cuk_campus_map',
                'last_synced_at': fetched_at,
            },
            {
                'slug': 'nicholls-hall',
                'name': '니콜스관',
                'category': 'building',
                'aliases': ['N관'],
                'description': '강의동',
                'latitude': 37.48587,
                'longitude': 126.802323,
                'opening_hours': {},
                'source_tag': 'cuk_campus_map',
                'last_synced_at': fetched_at,
            },
            {
                'slug': 'kim-sou-hwan-hall',
                'name': '김수환관',
                'category': 'dormitory',
                'aliases': [],
                'description': '강의실과 연구실, 기숙사가 함께 있는 건물',
                'latitude': 37.4855467,
                'longitude': 126.803851,
                'opening_hours': {},
                'source_tag': 'cuk_campus_map',
                'last_synced_at': fetched_at,
            },
        ]


class FakeCourseSource:
    def fetch(
        self,
        *,
        year: int,
        semester: int,
        department: str = 'ALL',
        completion_type: str = 'ALL',
        query: str = '',
        offset: int = 0,
    ):
        assert (year, semester, department, completion_type, query, offset) == (
            2026,
            1,
            'ALL',
            'ALL',
            '',
            0,
        )
        return '<html></html>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<html></html>'
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        return [
            {
                'year': 2026,
                'semester': 1,
                'code': '03149',
                'title': '자료구조',
                'professor': '박정흠',
                'department': '컴퓨터정보공학부',
                'section': '01',
                'day_of_week': '화',
                'period_start': 2,
                'period_end': 3,
                'room': 'BA203',
                'raw_schedule': '화2~3(BA203)',
                'source_tag': 'cuk_subject_search',
                'last_synced_at': fetched_at,
            }
        ]


class FakeNoticeSource:
    def fetch_list(self, *, offset: int = 0, limit: int = 10):
        assert offset == 0
        assert limit == 10
        return '<list></list>'

    def parse_list(self, html: str):
        assert html == '<list></list>'
        return [
            {
                'article_no': '1001',
                'title': '2026학년도 1학기 가족장학금 신청 안내',
                'board_category': '장학',
                'published_at': '2026-03-12',
                'source_url': 'https://example.edu/notice/1001',
            }
        ]

    def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 10):
        assert article_no == '1001'
        return '<detail></detail>'

    def parse_detail(self, html: str, *, default_title: str = '', default_category: str = ''):
        assert html == '<detail></detail>'
        assert default_title == '2026학년도 1학기 가족장학금 신청 안내'
        assert default_category == '장학'
        return {
            'title': default_title,
            'published_at': '2026-03-12',
            'summary': '가족장학금 신청 안내',
            'labels': ['장학'],
            'category': 'scholarship',
        }


class FakePaginatedCourseSource:
    def __init__(self):
        self.fetch_offsets: list[int] = []

    def fetch(
        self,
        *,
        year: int,
        semester: int,
        department: str = 'ALL',
        completion_type: str = 'ALL',
        query: str = '',
        offset: int = 0,
    ):
        assert (year, semester, department, completion_type, query) == (2026, 1, 'ALL', 'ALL', '')
        self.fetch_offsets.append(offset)
        return f'<html offset="{offset}"></html>'

    def parse(self, html: str, *, fetched_at: str):
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        if 'offset="0"' in html:
            return [
                {
                    'year': 2026,
                    'semester': 1,
                    'code': f'CSE{index:03d}',
                    'title': f'테스트과목{index:03d}',
                    'professor': '테스트교수',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                    'day_of_week': '월',
                    'period_start': 1,
                    'period_end': 1,
                    'room': f'N{100 + index}',
                    'raw_schedule': f'월1(N{100 + index})',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': fetched_at,
                }
                for index in range(50)
            ]
        if 'offset="50"' in html:
            return [
                {
                    'year': 2026,
                    'semester': 1,
                    'code': 'CSE049',
                    'title': '테스트과목049',
                    'professor': '테스트교수',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                    'day_of_week': '월',
                    'period_start': 1,
                    'period_end': 1,
                    'room': 'N149',
                    'raw_schedule': '월1(N149)',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': fetched_at,
                },
                {
                    'year': 2026,
                    'semester': 1,
                    'code': 'CSE999',
                    'title': '추가테스트과목',
                    'professor': '테스트교수',
                    'department': '컴퓨터정보공학부',
                    'section': '02',
                    'day_of_week': '화',
                    'period_start': 2,
                    'period_end': 3,
                    'room': 'N999',
                    'raw_schedule': '화2~3(N999)',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': fetched_at,
                },
            ]
        raise AssertionError(f'unexpected html: {html}')


class FakeCourseCoverageSource:
    def fetch(
        self,
        *,
        year: int,
        semester: int,
        department: str = 'ALL',
        completion_type: str = 'ALL',
        query: str = '',
        offset: int = 0,
    ):
        assert (year, semester, department, completion_type, query) == (2026, 1, 'ALL', 'ALL', '')
        return f'<html offset="{offset}"></html>'

    def parse(self, html: str, *, fetched_at: str):
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        if 'offset="0"' in html:
            return [
                {
                    'year': 2026,
                    'semester': 1,
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                    'day_of_week': '화',
                    'period_start': 1,
                    'period_end': 2,
                    'room': 'M307',
                    'raw_schedule': '화1~2(M307)',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': fetched_at,
                },
                {
                    'year': 2026,
                    'semester': 1,
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                    'day_of_week': '목',
                    'period_start': 5,
                    'period_end': 6,
                    'room': 'N201',
                    'raw_schedule': '목5~6(N201)',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': fetched_at,
                },
            ]
        return []


class FakeNoticeSourceWithDetailFailure:
    def fetch_list(self, *, offset: int = 0, limit: int = 10):
        assert offset == 0
        assert limit == 10
        return '<list></list>'

    def parse_list(self, html: str):
        assert html == '<list></list>'
        return [
            {
                'article_no': '2001',
                'title': '2026학년도 1학기 Major Discovery Week 특강 신청 마감 안내',
                'board_category': '학사',
                'published_at': '2026-03-14',
                'source_url': 'https://example.edu/notice/2001',
            }
        ]

    def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 10):
        raise httpx.ReadError('detail unavailable')


class FakeNoticeSourceWithGenericDetailLabel:
    def fetch_list(self, *, offset: int = 0, limit: int = 10):
        assert offset == 0
        assert limit == 10
        return '<list></list>'

    def parse_list(self, html: str):
        assert html == '<list></list>'
        return [
            {
                'article_no': '3001',
                'title': '2026학년도 1학기 Major Discovery Week 특강 신청 마감 안내',
                'board_category': '학사',
                'published_at': '2026-03-14',
                'source_url': 'https://example.edu/notice/3001',
            }
        ]

    def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 10):
        assert article_no == '3001'
        return '<detail></detail>'

    def parse_detail(self, html: str, *, default_title: str = '', default_category: str = ''):
        assert html == '<detail></detail>'
        assert default_title == '2026학년도 1학기 Major Discovery Week 특강 신청 마감 안내'
        assert default_category == '학사'
        return {
            'title': default_title,
            'published_at': '2026-03-14',
            'summary': '학사 일정과 특강 신청 마감 일정을 안내합니다.',
            'labels': ['공지'],
            'category': 'urgent',
        }


def test_refresh_places_from_campus_map_replaces_place_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_places_from_campus_map(
            conn,
            source=FakeCampusMapSource(),
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        places = search_places(conn, query='중앙')

    assert len(places) == 1
    assert places[0].source_tag == 'cuk_campus_map'


def test_refresh_places_from_campus_map_applies_place_alias_overrides(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        refresh_places_from_campus_map(
            conn,
            source=FakeCampusMapSource(),
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        place_alias_hits = search_places(conn, query='중도')
        restaurant_items = find_nearby_restaurants(conn, origin='학생식당', limit=1)
        classroom_payload = list_estimated_empty_classrooms(
            conn,
            building='니콜스',
            at=datetime.fromisoformat("2026-03-16T10:15:00+09:00"),
        )
        kim_place = get_place(conn, 'kim-sou-hwan-hall')

    assert any(item.slug == 'central-library' for item in place_alias_hits)
    assert restaurant_items
    assert restaurant_items[0].origin == 'sophie-barat-hall'
    assert classroom_payload.building.slug == 'nicholls-hall'
    assert kim_place.category == 'building'


def test_refresh_courses_from_subject_search_replaces_course_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_courses_from_subject_search(
            conn,
            source=FakeCourseSource(),
            year=2026,
            semester=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        courses = search_courses(conn, query='자료')

    assert len(courses) == 1
    assert courses[0].source_tag == 'cuk_subject_search'


def test_refresh_courses_from_subject_search_ingests_paginated_snapshot_and_dedupes(app_env):
    init_db()
    source = FakePaginatedCourseSource()

    with connection() as conn:
        refresh_courses_from_subject_search(
            conn,
            source=source,
            year=2026,
            semester=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        stored = repo.search_courses(conn, year=2026, semester=1, limit=200)

    assert source.fetch_offsets == [0, 50]
    assert len(stored) == 51
    assert any(item['code'] == 'CSE999' for item in stored)


def test_investigate_course_query_coverage_reports_covered_and_source_gaps(app_env):
    init_db()
    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                {
                    'year': 2026,
                    'semester': 1,
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                    'day_of_week': '화',
                    'period_start': 1,
                    'period_end': 2,
                    'room': 'M307',
                    'raw_schedule': '화1~2(M307)',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': '2026-03-13T09:00:00+09:00',
                },
                {
                    'year': 2026,
                    'semester': 1,
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                    'day_of_week': '목',
                    'period_start': 5,
                    'period_end': 6,
                    'room': 'N201',
                    'raw_schedule': '목5~6(N201)',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': '2026-03-13T09:00:00+09:00',
                },
            ],
        )
        reports = investigate_course_query_coverage(
            conn,
            queries=[
                '데이타베이스',
                '데 이 터 베 이 스',
                'CSE-420',
                'CSE301',
                '김가톨',
                '김 가 톨',
                'cSe 420',
                '박 요 셉',
            ],
            source=FakeCourseCoverageSource(),
            year=2026,
            semester=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )

    assert reports == [
        {
            'query': '데이타베이스',
            'year': 2026,
            'semester': 1,
            'status': 'covered',
            'source_match_count': 1,
            'db_match_count': 1,
            'search_match_count': 1,
            'source_matches': [
                {
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                }
            ],
            'db_matches': [
                {
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                }
            ],
            'search_matches': [
                {
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                }
            ],
        },
        {
            'query': '데 이 터 베 이 스',
            'year': 2026,
            'semester': 1,
            'status': 'covered',
            'source_match_count': 1,
            'db_match_count': 1,
            'search_match_count': 1,
            'source_matches': [
                {
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                }
            ],
            'db_matches': [
                {
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                }
            ],
            'search_matches': [
                {
                    'code': '05497',
                    'title': '데이터베이스활용',
                    'professor': '권보람',
                    'department': '경영학과',
                    'section': '01',
                }
            ],
        },
        {
            'query': 'CSE-420',
            'year': 2026,
            'semester': 1,
            'status': 'covered',
            'source_match_count': 1,
            'db_match_count': 1,
            'search_match_count': 1,
            'source_matches': [
                {
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                }
            ],
            'db_matches': [
                {
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                }
            ],
            'search_matches': [
                {
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                }
            ],
        },
        {
            'query': 'CSE301',
            'year': 2026,
            'semester': 1,
            'status': 'source_gap',
            'source_match_count': 0,
            'db_match_count': 0,
            'search_match_count': 0,
            'source_matches': [],
            'db_matches': [],
            'search_matches': [],
        },
        {
            'query': '김가톨',
            'year': 2026,
            'semester': 1,
            'status': 'source_gap',
            'source_match_count': 0,
            'db_match_count': 0,
            'search_match_count': 0,
            'source_matches': [],
            'db_matches': [],
            'search_matches': [],
        },
        {
            'query': '김 가 톨',
            'year': 2026,
            'semester': 1,
            'status': 'source_gap',
            'source_match_count': 0,
            'db_match_count': 0,
            'search_match_count': 0,
            'source_matches': [],
            'db_matches': [],
            'search_matches': [],
        },
        {
            'query': 'cSe 420',
            'year': 2026,
            'semester': 1,
            'status': 'covered',
            'source_match_count': 1,
            'db_match_count': 1,
            'search_match_count': 1,
            'source_matches': [
                {
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                }
            ],
            'db_matches': [
                {
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                }
            ],
            'search_matches': [
                {
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                }
            ],
        },
        {
            'query': '박 요 셉',
            'year': 2026,
            'semester': 1,
            'status': 'source_gap',
            'source_match_count': 0,
            'db_match_count': 0,
            'search_match_count': 0,
            'source_matches': [],
            'db_matches': [],
            'search_matches': [],
        },
    ]


def test_investigate_course_query_coverage_reports_db_gap_when_source_rows_are_not_synced(app_env):
    init_db()
    with connection() as conn:
        reports = investigate_course_query_coverage(
            conn,
            queries=['데이터베이스'],
            source=FakeCourseCoverageSource(),
            year=2026,
            semester=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )

    assert reports[0]['status'] == 'db_gap'
    assert reports[0]['source_match_count'] == 1
    assert reports[0]['db_match_count'] == 0
    assert reports[0]['search_match_count'] == 0


def test_investigate_course_query_coverage_reports_search_gap(
    app_env,
    monkeypatch,
):
    init_db()
    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                {
                    'year': 2026,
                    'semester': 1,
                    'code': 'CSE420',
                    'title': '임베디드시스템',
                    'professor': '박성심',
                    'department': '컴퓨터정보공학부',
                    'section': '01',
                    'day_of_week': '목',
                    'period_start': 5,
                    'period_end': 6,
                    'room': 'N201',
                    'raw_schedule': '목5~6(N201)',
                    'source_tag': 'cuk_subject_search',
                    'last_synced_at': '2026-03-13T09:00:00+09:00',
                }
            ],
        )
        monkeypatch.setattr('songsim_campus.services.search_courses', lambda *args, **kwargs: [])
        reports = investigate_course_query_coverage(
            conn,
            queries=['CSE 420'],
            source=FakeCourseCoverageSource(),
            year=2026,
            semester=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )

    assert reports[0]['status'] == 'search_gap'
    assert reports[0]['source_match_count'] == 1
    assert reports[0]['db_match_count'] == 1
    assert reports[0]['search_match_count'] == 0


def test_refresh_notices_from_notice_board_replaces_notice_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_notices_from_notice_board(
            conn,
            source=FakeNoticeSource(),
            pages=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        notices = list_latest_notices(conn)

    assert len(notices) == 1
    assert notices[0].category == 'scholarship'
    assert notices[0].source_tag == 'cuk_campus_notices'


def test_refresh_notices_from_notice_board_fallback_classifies_board_category(app_env):
    init_db()

    with connection() as conn:
        refresh_notices_from_notice_board(
            conn,
            source=FakeNoticeSourceWithDetailFailure(),
            pages=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        notices = list_latest_notices(conn)

    assert len(notices) == 1
    assert notices[0].category == 'academic'


def test_refresh_notices_from_notice_board_preserves_list_board_category_over_generic_detail_label(
    app_env,
):
    init_db()

    with connection() as conn:
        refresh_notices_from_notice_board(
            conn,
            source=FakeNoticeSourceWithGenericDetailLabel(),
            pages=1,
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        notices = list_latest_notices(conn)

    assert len(notices) == 1
    assert notices[0].category == 'academic'
    assert notices[0].labels == ['학사']


class FakeLibraryHoursSource:
    def fetch(self):
        return '<library></library>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<library></library>'
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        return [
            {
                'place_name': '중앙도서관',
                'opening_hours': {
                    '대출반납실': '학기중 평일 09:00-21:00 / 토요일 09:00-13:00',
                },
                'source_tag': 'cuk_library_hours',
                'last_synced_at': fetched_at,
            }
        ]


class FakeFacilitiesSource:
    def fetch(self):
        return '<facilities></facilities>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<facilities></facilities>'
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        return [
            {
                'facility_name': '카페드림',
                'location': '중앙도서관 2층',
                'hours_text': '평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)',
                'category': '카페',
                'source_tag': 'cuk_facilities',
                'last_synced_at': fetched_at,
            },
            {
                'facility_name': '매머드커피',
                'location': 'K관 1층',
                'hours_text': '평일 08:00~20:00 주말,공휴일 09:00~17:00',
                'category': '카페',
                'source_tag': 'cuk_facilities',
                'last_synced_at': fetched_at,
            },
            {
                'facility_name': '없는시설',
                'location': '없는관 1층',
                'hours_text': '상시 09:00~18:00',
                'category': '편의점',
                'source_tag': 'cuk_facilities',
                'last_synced_at': fetched_at,
            },
        ]


class FakeDiningMenuSource:
    requested_urls: list[str]

    def __init__(self, pdf_bytes: bytes | None = None, *, raise_on_fetch: bool = False):
        self.pdf_bytes = pdf_bytes if pdf_bytes is not None else _sample_menu_pdf_bytes()
        self.raise_on_fetch = raise_on_fetch
        self.requested_urls = []

    def fetch(self):
        return '<facilities-menu></facilities-menu>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<facilities-menu></facilities-menu>'
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        return [
            {
                'facility_name': 'Buon Pranzo 부온 프란조',
                'location': '학생미래인재관 2층',
                'hours_text': '중식 11:30 ~ 14:00',
                'category': '식당안내',
                'menu_week_label': '3월 3주차 메뉴표 확인하기',
                'menu_source_url': 'https://www.catholic.ac.kr/menu/buon.pdf',
                'source_tag': 'cuk_facilities',
                'last_synced_at': fetched_at,
            },
            {
                'facility_name': 'Café Bona 카페 보나',
                'location': '학생미래인재관 1층',
                'hours_text': '조식 08:00 ~ 09:30',
                'category': '식당안내',
                'menu_week_label': '3월 3주차 메뉴표 확인하기',
                'menu_source_url': 'https://www.catholic.ac.kr/menu/bona.pdf',
                'source_tag': 'cuk_facilities',
                'last_synced_at': fetched_at,
            },
            {
                'facility_name': 'Café Mensa 카페 멘사',
                'location': '김수환관 1층',
                'hours_text': '10:30~14:30',
                'category': '식당안내',
                'menu_week_label': '3월 3주차 메뉴표 확인하기',
                'menu_source_url': 'https://www.catholic.ac.kr/menu/mensa.pdf',
                'source_tag': 'cuk_facilities',
                'last_synced_at': fetched_at,
            },
        ]

    def fetch_menu_document(self, url: str) -> bytes:
        self.requested_urls.append(url)
        if self.raise_on_fetch:
            raise httpx.HTTPError('menu fetch failed')
        return self.pdf_bytes


class FakeTransportSource:
    def fetch(self):
        return '<transport></transport>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<transport></transport>'
        assert fetched_at == '2026-03-13T09:00:00+09:00'
        return [
            {
                'mode': 'subway',
                'title': '1호선',
                'summary': '역곡역 2번 출구 또는 소사역 3번 출구에서 도보 10분',
                'steps': ['인천역 ↔ 역곡역 : 35분 소요'],
                'source_url': 'https://www.catholic.ac.kr/ko/about/location_songsim.do',
                'source_tag': 'cuk_transport',
                'last_synced_at': fetched_at,
            }
        ]


class FakeCertificateSource:
    def fetch(self):
        return "<certificate></certificate>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<certificate></certificate>"
        assert fetched_at == "2026-03-17T15:00:00+09:00"
        return [
            {
                "title": "인터넷 증명발급",
                "summary": "인터넷 증명신청 및 발급",
                "steps": [
                    "수수료: 발급 : 국문 / 영문 1,000원(1매)",
                    "유의사항: 영문증명서의 경우 영문 성명이 없으면 증명 발급이 되지 않음",
                ],
                "source_url": "https://catholic.certpia.com/",
                "source_tag": "cuk_certificate_guides",
                "last_synced_at": fetched_at,
            }
        ]


class FakeLeaveOfAbsenceSource:
    def fetch(self):
        return "<leave></leave>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<leave></leave>"
        assert fetched_at == "2026-03-17T15:00:00+09:00"
        return [
            {
                "title": "신청방법",
                "summary": "Trinity 신청 → 휴학상담 → 휴학신청 승인 → 휴학최종 승인",
                "steps": ["STEP 1: Trinity 신청 (학생)"],
                "links": [
                    {
                        "label": "휴복학 FAQ (다운로드)",
                        "url": "https://www.catholic.ac.kr/cms/etcResourceDown.do?site=fake&key=fake",
                    }
                ],
                "source_url": "https://www.catholic.ac.kr/ko/support/leave_of_absence.do",
                "source_tag": "cuk_leave_of_absence_guides",
                "last_synced_at": fetched_at,
            }
        ]


class FakeAcademicCalendarSource:
    def fetch_range(self, *, start_date: str, end_date: str):
        assert start_date == "2026-03-01"
        assert end_date == "2027-02-28"
        return '{"data":[]}'

    def parse(self, payload: str, *, fetched_at: str):
        assert payload == '{"data":[]}'
        assert fetched_at == "2026-03-17T15:00:00+09:00"
        return [
            {
                "academic_year": 2026,
                "title": "1학기 개시일",
                "start_date": "2026-03-03",
                "end_date": "2026-03-03",
                "campuses": ["성심", "성의", "성신"],
                "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                "source_tag": "cuk_academic_calendar",
                "last_synced_at": fetched_at,
            }
        ]


class FakeScholarshipSource:
    def fetch(self):
        return "<scholarship></scholarship>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<scholarship></scholarship>"
        assert fetched_at == "2026-03-17T15:00:00+09:00"
        return [
            {
                "title": "장학금 신청",
                "summary": "홈페이지 공지사항 수시 게재하므로 장학별 해당 기간 내에 신청",
                "steps": [
                    (
                        "구분: 교내 / 장학금 종류: 근로(A/B/C) 및 인턴십 / 신청기간: "
                        "매 학기 초(3월/9월) / 수혜학기: 학기 말(7월 초/1월 초)"
                    )
                ],
                "links": [],
                "source_url": "https://www.catholic.ac.kr/ko/support/scholarship_songsim.do",
                "source_tag": "cuk_scholarship_guides",
                "last_synced_at": fetched_at,
            }
        ]


class FakeWifiGuideSource:
    def fetch(self):
        return "<wifi></wifi>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<wifi></wifi>"
        assert fetched_at == "2026-03-17T15:00:00+09:00"
        return [
            {
                "building_name": "니콜스관",
                "ssids": ["catholic_univ", "강의실 호실명 (ex: N301)"],
                "steps": [
                    "무선랜 안테나 검색 후 신호가 강한 SSID 선택 (최초 접속 시 보안키 입력)",
                    "K관, A관(안드레아관) 보안키 : catholic!!(교내 동일)",
                ],
                "source_url": "https://www.catholic.ac.kr/ko/campuslife/wifi.do",
                "source_tag": "cuk_wifi_guides",
                "last_synced_at": fetched_at,
            }
        ]


class FakeAcademicSupportSource:
    def __init__(self, rows=None):
        self._rows = rows or [
            {
                "title": "업무안내",
                "summary": "학사지원학부의 대표 서비스",
                "steps": ["전공과정, 수업운영, 학적, 졸업/교직, 학점교류 문의"],
                "contacts": ["02-2164-4510", "02-2164-4288"],
            }
        ]

    def fetch(self):
        return "<support></support>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<support></support>"
        assert fetched_at == "2026-03-17T15:00:00+09:00"
        return [
            {
                **row,
                "source_url": "https://www.catholic.ac.kr/ko/support/academic_contact_information.do",
                "source_tag": "cuk_academic_support_guides",
                "last_synced_at": fetched_at,
            }
            for row in self._rows
        ]


class FakeDormitorySongsimSource:
    def fetch(self):
        return "<dormitory-songsim></dormitory-songsim>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<dormitory-songsim></dormitory-songsim>"
        assert fetched_at == "2026-03-20T00:00:00+09:00"
        return [
            _dormitory_guide_row(
                topic="hall_info",
                title="스테파노관",
                summary="약 1,160여 명을 수용할 수 있는 성심교정 최대 규모의 기숙사",
                steps=[
                    "383개(1,167명) 규모",
                    "세탁실, 휴게실, 공용화장실, 세미나실, 짐 보관실",
                ],
                source_url="https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do",
            ),
            _dormitory_guide_row(
                topic="hall_info",
                title="안드레아관",
                summary="학생 476명 수용의 2인실 기숙사",
                steps=[
                    "238실(2인실), 학생 476명 수용",
                    "무인택배실, 우편함, 공동 세탁실, 층별 휴게실",
                ],
                source_url="https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do",
            ),
            _dormitory_guide_row(
                topic="hall_info",
                title="프란치스코관",
                summary="정문에서 도보 5분 이내의 생활관",
                steps=[
                    "14층, 총 28세대",
                    "각 세대 가전/가구 구비, 개별 취사",
                ],
                source_url="https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do",
            ),
            _dormitory_guide_row(
                topic="hall_info",
                title="기숙사운영팀",
                summary="성심교정 기숙사운영팀 연락처",
                steps=[
                    "전화: 02-2164-4660, 4661, 4663",
                    "메일: dormitory1@catholic.ac.kr",
                ],
                source_url="https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do",
            ),
        ]


class FakeDormitoryHomepageSource:
    def fetch(self):
        return "<dormitory-home></dormitory-home>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<dormitory-home></dormitory-home>"
        assert fetched_at == "2026-03-20T00:00:00+09:00"
        return [
            _dormitory_guide_row(
                topic="quick_links",
                title="입사안내 / 퇴사안내 / 생활안내 / 기숙사비 / FAQ",
                summary="입사안내",
                steps=["입사안내", "퇴사안내", "생활안내", "기숙사비", "FAQ"],
                links=[
                    {"label": "입사안내", "url": "https://dorm.catholic.ac.kr/dormitory/check/freshman.do"},
                    {"label": "퇴사안내", "url": "https://dorm.catholic.ac.kr/dormitory/check/resignation.do"},
                ],
            ),
            _dormitory_guide_row(
                topic="latest_notices",
                title="일반공지(K관/A관)",
                summary="K관/A관 일반공지 카드",
                steps=["K관/A관 일반공지 카드 1", "K관/A관 일반공지 카드 2"],
                links=[
                    {"label": "K관/A관 일반공지 카드 1", "url": "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do?mode=view&articleNo=1"},
                    {"label": "K관/A관 일반공지 카드 2", "url": "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do?mode=view&articleNo=2"},
                ],
            ),
            _dormitory_guide_row(
                topic="latest_notices",
                title="입퇴사공지(K관/A관)",
                summary="K관/A관 입퇴사공지 카드",
                steps=["K관/A관 입퇴사공지 카드 1"],
                links=[
                    {"label": "K관/A관 입퇴사공지 카드 1", "url": "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice1.do?mode=view&articleNo=3"},
                ],
            ),
            _dormitory_guide_row(
                topic="latest_notices",
                title="일반공지(프란치스코관)",
                summary="프란치스코관 일반공지 카드",
                steps=["프란치스코관 일반공지 카드 1"],
                links=[
                    {"label": "프란치스코관 일반공지 카드 1", "url": "https://dorm.catholic.ac.kr/dormitory/board/comm_notice3.do?mode=view&articleNo=4"},
                ],
            ),
            _dormitory_guide_row(
                topic="latest_notices",
                title="입퇴사공지(프란치스코관)",
                summary="프란치스코관 입퇴사공지 카드",
                steps=["프란치스코관 입퇴사공지 카드 1"],
                links=[
                    {"label": "프란치스코관 입퇴사공지 카드 1", "url": "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice.do?mode=view&articleNo=5"},
                ],
            ),
        ]


class FakeAffiliatedNoticeSource:
    def __init__(
        self,
        topic: str,
        items: list[dict[str, object]],
        *,
        source_tag: str = "cuk_affiliated_notice_boards",
        detail_failures: set[str] | None = None,
    ):
        self.topic = topic
        self.items = items
        self.source_tag = source_tag
        self.detail_failures = detail_failures or set()

    def fetch_list(self, *, offset: int = 0, limit: int = 10):
        assert limit == 10
        return f"<{self.topic}-list offset={offset}>"

    def parse_list(self, html: str):
        assert html.startswith(f"<{self.topic}-list")
        return self.items

    def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 10):
        assert limit == 10
        if article_no in self.detail_failures:
            raise httpx.HTTPError("detail fetch failed")
        return f"<detail article_no={article_no} offset={offset}>"

    def parse_detail(
        self,
        html: str,
        *,
        default_title: str,
        default_category: str = "",
        default_summary: str,
        default_published_at: str,
        default_source_url: str | None = None,
    ):
        assert html.startswith("<detail article_no=")
        return {
            "title": default_title,
            "summary": default_summary,
            "published_at": default_published_at,
            "source_url": default_source_url,
            "source_tag": self.source_tag,
        }


def test_refresh_affiliated_notices_dedupes_within_topic_and_preserves_cross_topic_duplicates(
    app_env,
):
    init_db()

    with connection() as conn:
        notices = refresh_affiliated_notices_from_sources(
            conn,
            sources=[
                FakeAffiliatedNoticeSource(
                    "international_studies",
                    [
                        {
                            "article_no": "1",
                            "title": "국제학부 공지 A",
                            "published_at": "2026-03-21",
                            "summary": "article number winner",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=1",
                        },
                        {
                            "article_no": "1",
                            "title": "국제학부 공지 A duplicate",
                            "published_at": "2026-03-22",
                            "summary": "article number duplicate",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=1-dup",
                        },
                    ],
                ),
                FakeAffiliatedNoticeSource(
                    "international_studies",
                    [
                        {
                            "article_no": "2",
                            "title": "국제학부 공지 B",
                            "published_at": "2026-03-20",
                            "summary": "source url winner",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=shared",
                        },
                        {
                            "article_no": "3",
                            "title": "국제학부 공지 C",
                            "published_at": "2026-03-19",
                            "summary": "source url duplicate",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=shared",
                        },
                    ],
                ),
                FakeAffiliatedNoticeSource(
                    "international_studies",
                    [
                        {
                            "article_no": "4",
                            "title": "국제학부 공지 D",
                            "published_at": "2026-03-18",
                            "summary": "title/published_at winner",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=4",
                        },
                        {
                            "article_no": "5",
                            "title": "국제학부 공지 D",
                            "published_at": "2026-03-18",
                            "summary": "title/published_at duplicate",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=5",
                        },
                        {
                            "article_no": "6",
                            "title": "국제학부 fallback 공지",
                            "published_at": "2026-03-17",
                            "summary": "fallback summary",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=6",
                        },
                    ],
                    detail_failures={"6"},
                ),
                FakeAffiliatedNoticeSource(
                    "dorm_k_a_general",
                    [
                        {
                            "article_no": "1",
                            "title": "국제학부 공지 A",
                            "published_at": "2026-03-21",
                            "summary": "cross-topic duplicate",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=1",
                        }
                    ],
                ),
            ],
            fetched_at="2026-03-20T00:00:00+09:00",
        )
        all_notices = list_affiliated_notices(conn, limit=20)

    assert len(notices) == 5
    assert len(all_notices) == 5
    assert [item.topic for item in all_notices].count("international_studies") == 4
    assert [item.topic for item in all_notices].count("dorm_k_a_general") == 1
    titles = [item.title for item in all_notices]
    assert titles.count("국제학부 공지 A") == 2
    assert "국제학부 공지 A duplicate" not in titles
    assert "국제학부 공지 C" not in titles
    assert "국제학부 공지 D duplicate" not in titles
    assert any(
        item.title == "국제학부 fallback 공지" and item.summary == "fallback summary"
        for item in all_notices
    )
    assert any(
        item.topic == "dorm_k_a_general"
        and item.title == "국제학부 공지 A"
        and item.source_url == "https://is.catholic.ac.kr/is/community/notice.do?articleNo=1"
        for item in all_notices
    )


class FakeAcademicStatusSource:
    def __init__(self, status: str, rows: list[dict[str, object]]):
        self.status = status
        self.rows = rows

    def fetch(self):
        return f"<{self.status}></{self.status}>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == f"<{self.status}></{self.status}>"
        assert fetched_at == "2026-03-17T15:00:00+09:00"
        source_urls = {
            "return_from_leave": "https://www.catholic.ac.kr/ko/support/return_from_leave_of_absence.do",
            "dropout": "https://www.catholic.ac.kr/ko/support/dropout.do",
            "re_admission": "https://www.catholic.ac.kr/ko/support/re_admission.do",
        }
        return [
            {
                **row,
                "status": self.status,
                "source_url": source_urls[self.status],
                "source_tag": "cuk_academic_status_guides",
                "last_synced_at": fetched_at,
            }
            for row in self.rows
        ]


def test_refresh_library_hours_merges_opening_hours_into_existing_place(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        refresh_library_hours_from_library_page(
            conn,
            source=FakeLibraryHoursSource(),
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        place = get_place(conn, 'central-library')

    assert place.source_tag == 'demo'
    assert place.opening_hours['대출반납실'] == '학기중 평일 09:00-21:00 / 토요일 09:00-13:00'


def test_refresh_facility_hours_merges_by_location_and_skips_unknown_places(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        places = refresh_facility_hours_from_facilities_page(
            conn,
            source=FakeFacilitiesSource(),
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        library = get_place(conn, 'central-library')
        hall = get_place(conn, 'kim-sou-hwan-hall')

    assert sorted(item.slug for item in places) == ['central-library', 'kim-sou-hwan-hall']
    assert library.opening_hours['카페드림'] == '평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)'
    assert hall.opening_hours['매머드커피'] == '평일 08:00~20:00 주말,공휴일 09:00~17:00'
    assert '없는시설' not in library.opening_hours


def test_refresh_campus_dining_menus_extracts_menu_text_and_links(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        menus = refresh_campus_dining_menus_from_facilities_page(
            conn,
            source=FakeDiningMenuSource(),
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        stored = search_campus_dining_menus(conn, limit=10)

    assert {item.venue_slug for item in menus} == {"buon-pranzo", "cafe-bona", "cafe-mensa"}
    assert len(stored) == 3
    bona = next(item for item in stored if item.venue_slug == "cafe-bona")
    assert bona.place_slug == "student-center"
    assert bona.place_name == "학생회관"
    assert bona.week_label == "3월 3주차 메뉴표 확인하기"
    assert bona.week_start == "2026-03-16"
    assert bona.week_end == "2026-03-20"
    assert bona.menu_text is not None
    assert "Bulgogi Rice Bowl" in bona.menu_text
    assert bona.source_url == "https://www.catholic.ac.kr/menu/bona.pdf"
    assert bona.source_tag == "cuk_facilities_menu"


def test_refresh_campus_dining_menus_preserves_link_when_pdf_extract_fails(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        menus = refresh_campus_dining_menus_from_facilities_page(
            conn,
            source=FakeDiningMenuSource(raise_on_fetch=True),
            fetched_at='2026-03-13T09:00:00+09:00',
        )

    assert len(menus) == 3
    assert all(item.menu_text is None for item in menus)
    assert all(item.source_url is not None for item in menus)
    assert all(item.week_label == "3월 3주차 메뉴표 확인하기" for item in menus)


def test_search_campus_dining_menus_supports_generic_and_specific_queries(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        refresh_campus_dining_menus_from_facilities_page(
            conn,
            source=FakeDiningMenuSource(),
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        all_rows = search_campus_dining_menus(conn, query="학생식당 메뉴", limit=10)
        bona_rows = search_campus_dining_menus(conn, query="카페 보나 메뉴", limit=10)

    assert {item.venue_slug for item in all_rows} == {
        "buon-pranzo",
        "cafe-bona",
        "cafe-mensa",
    }
    assert [item.venue_slug for item in bona_rows] == ["cafe-bona"]
    assert bona_rows[0].place_name == "학생회관"


def test_refresh_transport_guides_replaces_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_transport_guides_from_location_page(
            conn,
            source=FakeTransportSource(),
            fetched_at='2026-03-13T09:00:00+09:00',
        )
        guides = list_transport_guides(conn)

    assert len(guides) == 1
    assert guides[0].mode == 'subway'
    assert guides[0].title == '1호선'
    assert guides[0].source_tag == 'cuk_transport'


def test_refresh_certificate_guides_replaces_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_certificate_guides_from_certificate_page(
            conn,
            source=FakeCertificateSource(),
            fetched_at="2026-03-17T15:00:00+09:00",
        )
        guides = list_certificate_guides(conn)

    assert len(guides) == 1
    assert guides[0].title == "인터넷 증명발급"
    assert guides[0].source_url == "https://catholic.certpia.com/"
    assert guides[0].source_tag == "cuk_certificate_guides"


def test_refresh_leave_of_absence_guides_replaces_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_leave_of_absence_guides_from_source(
            conn,
            source=FakeLeaveOfAbsenceSource(),
            fetched_at="2026-03-17T15:00:00+09:00",
        )
        guides = list_leave_of_absence_guides(conn)

    assert len(guides) == 1
    assert guides[0].title == "신청방법"
    assert guides[0].links[0]["label"] == "휴복학 FAQ (다운로드)"
    assert guides[0].source_tag == "cuk_leave_of_absence_guides"


def test_refresh_academic_calendar_replaces_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_academic_calendar_from_source(
            conn,
            source=FakeAcademicCalendarSource(),
            academic_year=2026,
            fetched_at="2026-03-17T15:00:00+09:00",
        )
        events = list_academic_calendar(conn, academic_year=2026, limit=10)

    assert len(events) == 1
    assert events[0].title == "1학기 개시일"
    assert events[0].campuses == ["성심", "성의", "성신"]
    assert events[0].source_tag == "cuk_academic_calendar"


def test_refresh_scholarship_guides_replaces_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_scholarship_guides_from_source(
            conn,
            source=FakeScholarshipSource(),
            fetched_at="2026-03-17T15:00:00+09:00",
        )
        guides = list_scholarship_guides(conn)

    assert len(guides) == 1
    assert guides[0].title == "장학금 신청"
    assert guides[0].source_url == "https://www.catholic.ac.kr/ko/support/scholarship_songsim.do"
    assert guides[0].source_tag == "cuk_scholarship_guides"


def test_refresh_wifi_guides_replaces_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_wifi_guides_from_source(
            conn,
            source=FakeWifiGuideSource(),
            fetched_at="2026-03-17T15:00:00+09:00",
        )
        guides = list_wifi_guides(conn)

    assert len(guides) == 1
    assert guides[0].building_name == "니콜스관"
    assert guides[0].ssids == ["catholic_univ", "강의실 호실명 (ex: N301)"]
    assert guides[0].source_url == "https://www.catholic.ac.kr/ko/campuslife/wifi.do"
    assert guides[0].source_tag == "cuk_wifi_guides"


def test_refresh_academic_support_guides_replaces_rows(app_env):
    init_db()

    with connection() as conn:
        refresh_academic_support_guides_from_source(
            conn,
            source=FakeAcademicSupportSource(),
            fetched_at="2026-03-17T15:00:00+09:00",
        )
        guides = list_academic_support_guides(conn)

    assert len(guides) == 1
    assert guides[0].title == "업무안내"
    assert guides[0].contacts == ["02-2164-4510", "02-2164-4288"]
    assert guides[0].source_tag == "cuk_academic_support_guides"


def test_refresh_academic_status_guides_replaces_rows_and_filters_by_status(app_env):
    init_db()

    with connection() as conn:
        refresh_academic_status_guides_from_source(
            conn,
            sources=[
                FakeAcademicStatusSource(
                    "return_from_leave",
                    [
                        {
                            "title": "신청방법",
                            "summary": "TRINITY 복학신청",
                            "steps": ["TRINITY ⇒ 학적/졸업 ⇒ 복학신청"],
                            "links": [],
                        }
                    ],
                ),
                FakeAcademicStatusSource(
                    "dropout",
                    [
                        {
                            "title": "자퇴 신청 방법",
                            "summary": "방문신청",
                            "steps": ["학사지원팀에 자퇴원 제출"],
                            "links": [],
                        }
                    ],
                ),
                FakeAcademicStatusSource(
                    "re_admission",
                    [
                        {
                            "title": "지원자격",
                            "summary": "제적 후 1년 경과",
                            "steps": ["제적, 자퇴 후 1년이 경과한 자"],
                            "links": [],
                        }
                    ],
                ),
            ],
            fetched_at="2026-03-17T15:00:00+09:00",
        )
        guides = list_academic_status_guides(conn)
        dropout_guides = list_academic_status_guides(conn, status="dropout")

    assert len(guides) == 3
    assert [guide.status for guide in guides] == [
        "return_from_leave",
        "dropout",
        "re_admission",
    ]
    assert dropout_guides[0].title == "자퇴 신청 방법"
    assert dropout_guides[0].source_tag == "cuk_academic_status_guides"


def test_refresh_dormitory_guides_replaces_rows_and_filters_by_topic(app_env):
    init_db()

    with connection() as conn:
        repo.replace_dormitory_guides(
            conn,
            [
                {
                    "topic": "hall_info",
                    "title": "임시 기숙사",
                    "summary": "old",
                    "steps": ["old"],
                    "links": [],
                    "source_url": "https://example.com/old",
                    "source_tag": "old",
                    "last_synced_at": "2026-03-19T00:00:00+09:00",
                }
            ],
        )
        guides = refresh_dormitory_guides_from_source(
            conn,
            sources=[FakeDormitorySongsimSource(), FakeDormitoryHomepageSource()],
            fetched_at="2026-03-20T00:00:00+09:00",
        )
        all_guides = list_dormitory_guides(conn, limit=20)
        hall_guides = list_dormitory_guides(conn, topic="hall_info", limit=20)
        quick_links = list_dormitory_guides(conn, topic="quick_links", limit=20)
        latest_notices = list_dormitory_guides(conn, topic="latest_notices", limit=20)

    assert len(guides) == 9
    assert [guide.topic for guide in all_guides] == [
        "hall_info",
        "hall_info",
        "hall_info",
        "hall_info",
        "quick_links",
        "latest_notices",
        "latest_notices",
        "latest_notices",
        "latest_notices",
    ]
    assert [guide.title for guide in hall_guides] == [
        "스테파노관",
        "안드레아관",
        "프란치스코관",
        "기숙사운영팀",
    ]
    assert quick_links[0].links[0]["label"] == "입사안내"
    assert latest_notices[0].title == "일반공지(K관/A관)"
    assert len(latest_notices) == 4
    assert latest_notices[-1].links[0]["label"] == "프란치스코관 입퇴사공지 카드 1"
    assert all_guides[0].source_tag == "cuk_dormitory_guides"
    assert all_guides[0].source_url == "https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do"


def test_refresh_affiliated_notices_replaces_rows_and_orders_by_query_and_date(app_env):
    init_db()

    with connection() as conn:
        repo.replace_affiliated_notices(
            conn,
            [
                _affiliated_notice_row(
                    topic="international_studies",
                    title="오래된 임시 공지",
                    published_at="2026-03-01",
                    summary="old",
                    source_url="https://example.com/old",
                    source_tag="old",
                )
            ],
        )
        notices = refresh_affiliated_notices_from_sources(
            conn,
            sources=[
                FakeAffiliatedNoticeSource(
                    "international_studies",
                    [
                        {
                            "article_no": "1",
                            "title": "국제학부 공결 신청 안내",
                            "published_at": "2026-03-18",
                            "summary": "공결 신청",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=1",
                        },
                        {
                            "article_no": "2",
                            "title": "국제학부 일반 공지",
                            "published_at": "2026-03-19",
                            "summary": "공결 서식",
                            "source_url": "https://is.catholic.ac.kr/is/community/notice.do?articleNo=2",
                        },
                    ],
                ),
                FakeAffiliatedNoticeSource(
                    "dorm_k_a_general",
                    [
                        {
                            "article_no": "3",
                            "title": "기숙사 일반 공지",
                            "published_at": "2026-03-20",
                            "summary": "OT 안내",
                            "source_url": "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do?articleNo=3",
                        },
                        {
                            "article_no": "4",
                            "title": "생활 안내",
                            "published_at": "2026-03-02",
                            "summary": "요약에는 없는 문장",
                            "body_text": "본문에는 심야 출입 절차가 들어 있습니다.",
                            "source_url": "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do?articleNo=4",
                        }
                    ],
                ),
            ],
            fetched_at="2026-03-20T00:00:00+09:00",
        )
        all_notices = list_affiliated_notices(conn, limit=20)
        study_notices = list_affiliated_notices(
            conn,
            topic="international_studies",
            query="공결",
            limit=20,
        )
        latest_only = list_affiliated_notices(conn, query="공지", limit=20)
        body_only = list_affiliated_notices(
            conn,
            topic="dorm_k_a_general",
            query="심야 출입",
            limit=20,
        )

    assert len(notices) == 4
    assert [item.topic for item in all_notices] == [
        "dorm_k_a_general",
        "international_studies",
        "international_studies",
        "dorm_k_a_general",
    ]
    assert [item.title for item in study_notices] == [
        "국제학부 공결 신청 안내",
        "국제학부 일반 공지",
    ]
    assert [item.title for item in latest_only] == [
        "기숙사 일반 공지",
        "국제학부 일반 공지",
    ]
    assert [item.title for item in body_only] == ["생활 안내"]
    assert all_notices[0].source_tag == "cuk_affiliated_notice_boards"
    assert all_notices[0].source_url == "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do?articleNo=3"


def test_refresh_campus_life_notices_replaces_rows_and_orders_by_query_and_date(app_env):
    init_db()

    with connection() as conn:
        repo.replace_campus_life_notices(
            conn,
            [
                _campus_life_notice_row(
                    topic="outside_agencies",
                    title="오래된 임시 공지",
                    published_at="2026-03-01",
                    summary="old",
                    source_url="https://example.com/old",
                    source_tag="old",
                )
            ],
        )
        notices = refresh_campus_life_notices_from_source(
            conn,
            source=FakeAffiliatedNoticeSource(
                "outside_agencies",
                [
                    {
                        "article_no": "1",
                        "title": "외부기관 공지 A",
                        "published_at": "2026-03-18",
                        "summary": "지원 안내",
                        "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice_outside.do?articleNo=1",
                    },
                    {
                        "article_no": "2",
                        "title": "외부기관 일반 공지",
                        "published_at": "2026-03-19",
                        "summary": "공결 서식",
                        "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice_outside.do?articleNo=2",
                    },
                ],
                source_tag="cuk_campus_life_notices",
            ),
            fetched_at="2026-03-20T00:00:00+09:00",
        )
        all_notices = list_campus_life_notices(conn, limit=20)
        outside_only = list_campus_life_notices(
            conn,
            topic="outside_agencies",
            query="공지",
            limit=20,
        )
        latest_only = list_campus_life_notices(conn, query="공지", limit=20)

    assert len(notices) == 2
    assert [item.topic for item in all_notices] == ["outside_agencies", "outside_agencies"]
    assert [item.title for item in outside_only] == [
        "외부기관 일반 공지",
        "외부기관 공지 A",
    ]
    assert [item.title for item in latest_only] == [
        "외부기관 일반 공지",
        "외부기관 공지 A",
    ]
    assert all_notices[0].source_tag == "cuk_campus_life_notices"
    assert all_notices[0].source_url == "https://www.catholic.ac.kr/ko/campuslife/notice_outside.do?articleNo=2"


def test_refresh_campus_life_notices_merges_sources_with_topic_local_dedupe(app_env):
    init_db()

    with connection() as conn:
        notices = refresh_campus_life_notices_from_source(
            conn,
            sources=[
                FakeAffiliatedNoticeSource(
                    "outside_agencies",
                    [
                        {
                            "article_no": "1",
                            "topic": "outside_agencies",
                            "title": "캠퍼스 공지 A",
                            "published_at": "2026-03-21",
                            "summary": "outside winner",
                            "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice_outside.do?articleNo=1",
                        },
                        {
                            "article_no": "1",
                            "topic": "outside_agencies",
                            "title": "캠퍼스 공지 A duplicate",
                            "published_at": "2026-03-21",
                            "summary": "outside duplicate",
                            "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice_outside.do?articleNo=1-dup",
                        },
                    ],
                ),
                FakeAffiliatedNoticeSource(
                    "events",
                    [
                        {
                            "article_no": "1",
                            "topic": "events",
                            "title": "캠퍼스 공지 A",
                            "published_at": "2026-03-21",
                            "summary": "events winner",
                            "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice_event.do?articleNo=1",
                        },
                        {
                            "article_no": "1",
                            "topic": "events",
                            "title": "캠퍼스 공지 A duplicate",
                            "published_at": "2026-03-21",
                            "summary": "events duplicate",
                            "source_url": "https://www.catholic.ac.kr/ko/campuslife/notice_event.do?articleNo=1-dup",
                        },
                    ],
                ),
            ],
            fetched_at="2026-03-20T00:00:00+09:00",
        )
        all_notices = list_campus_life_notices(conn, limit=20)
        events_only = list_campus_life_notices(conn, topic="events", limit=20)

    assert len(notices) == 2
    assert {item.topic for item in all_notices} == {"outside_agencies", "events"}
    assert [item.title for item in all_notices].count("캠퍼스 공지 A") == 2
    assert {item.summary for item in all_notices} == {"outside winner", "events winner"}
    assert [item.topic for item in events_only] == ["events"]
    assert events_only[0].summary == "events winner"


def test_list_affiliated_notices_rejects_unknown_topic(app_env):
    init_db()

    with connection() as conn:
        repo.replace_affiliated_notices(
            conn,
            [
                _affiliated_notice_row(
                    topic="international_studies",
                    title="국제학부 공지",
                    published_at="2026-03-20",
                    summary="공지",
                    source_url="https://is.catholic.ac.kr/is/community/notice.do?articleNo=1",
                )
            ],
        )

    with connection() as conn, pytest.raises(InvalidRequestError, match="international_studies"):
        list_affiliated_notices(conn, topic="invalid")


def test_list_campus_life_notices_rejects_unknown_topic(app_env):
    init_db()

    with connection() as conn:
        repo.replace_campus_life_notices(
            conn,
            [
                _campus_life_notice_row(
                    title="외부기관 공지",
                    published_at="2026-03-20",
                    summary="공지",
                )
            ],
        )

    with connection() as conn, pytest.raises(
        InvalidRequestError,
        match="outside_agencies or events",
    ):
        list_campus_life_notices(conn, topic="invalid")


def test_list_campus_life_support_guides_accepts_new_topics_and_rejects_unknown_topic(
    app_env,
    monkeypatch,
):
    init_db()

    observed_topics: list[str | None] = []

    def fake_list(conn, topic=None, limit=20):
        observed_topics.append(topic)
        return []

    monkeypatch.setattr(services_module.repo, "list_campus_life_support_guides", fake_list)

    with connection() as conn:
        assert list_campus_life_support_guides(conn, topic="mobility_safety", limit=1) == []
        assert list_campus_life_support_guides(conn, topic="student_counseling", limit=1) == []
        assert list_campus_life_support_guides(conn, topic="disability_support", limit=1) == []
        assert list_campus_life_support_guides(conn, topic="student_reservist", limit=1) == []
        assert list_campus_life_support_guides(conn, topic="hospital_use", limit=1) == []
        assert list_campus_life_support_guides(conn, topic="facility_rental", limit=1) == []
        assert list_campus_life_support_guides(conn, topic="career_counseling", limit=1) == []

        with pytest.raises(InvalidRequestError, match="mobility_safety"):
            list_campus_life_support_guides(conn, topic="invalid", limit=1)

    assert observed_topics == [
        "mobility_safety",
        "student_counseling",
        "disability_support",
        "student_reservist",
        "hospital_use",
        "facility_rental",
        "career_counseling",
    ]


def test_list_dormitory_guides_rejects_unknown_topic(app_env):
    init_db()

    with connection() as conn:
        repo.replace_dormitory_guides(
            conn,
            [
                {
                    "topic": "hall_info",
                    "title": "스테파노관",
                    "summary": "소개",
                    "steps": ["소개"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do",
                    "source_tag": "cuk_dormitory_guides",
                    "last_synced_at": "2026-03-20T00:00:00+09:00",
                }
            ],
        )

    with connection() as conn, pytest.raises(InvalidRequestError, match="hall_info"):
        list_dormitory_guides(conn, topic="invalid")


def test_list_student_activity_guides_accepts_new_topics_and_rejects_unknown_topic(
    app_env,
    monkeypatch,
):
    init_db()

    observed_topics: list[str | None] = []

    def fake_list(conn, topic=None, limit=20):
        observed_topics.append(topic)
        return []

    monkeypatch.setattr(services_module.repo, "list_student_activity_guides", fake_list)

    with connection() as conn:
        assert list_student_activity_guides(conn, topic="student_government", limit=1) == []
        assert list_student_activity_guides(conn, topic="campus_media", limit=1) == []
        assert list_student_activity_guides(conn, topic="social_volunteering", limit=1) == []
        assert list_student_activity_guides(conn, topic="rotc", limit=1) == []
        assert list_student_activity_guides(conn, topic="central_clubs", limit=1) == []
        assert list_student_activity_guides(conn, topic="institutional_clubs", limit=1) == []

        with pytest.raises(
            InvalidRequestError,
            match="student_government, campus_media, social_volunteering, rotc",
        ):
            list_student_activity_guides(conn, topic="invalid", limit=1)

    assert observed_topics == [
        "student_government",
        "campus_media",
        "social_volunteering",
        "rotc",
        "central_clubs",
        "institutional_clubs",
    ]


def test_refresh_student_activity_guides_fetches_default_sources(app_env, monkeypatch):
    init_db()

    class GovernmentFixtureSource(services_module.StudentGovernmentGuideSource):
        def fetch(self) -> str:
            return (FIXTURES_DIR / "student_government.do.html").read_text(encoding="utf-8")

    class MediaFixtureSource(services_module.CampusMediaGuideSource):
        def fetch(self) -> str:
            return (FIXTURES_DIR / "media.do.html").read_text(encoding="utf-8")

    class VolunteerFixtureSource(services_module.SocialVolunteeringGuideSource):
        def fetch(self) -> str:
            return (FIXTURES_DIR / "volunteer.do.html").read_text(encoding="utf-8")

    class RotcFixtureSource(services_module.RotcGuideSource):
        def fetch(self) -> str:
            return (FIXTURES_DIR / "rotc.do.html").read_text(encoding="utf-8")

    class CentralClubFixtureSource(services_module.CentralClubGuideSource):
        def fetch(self) -> str:
            return (FIXTURES_DIR / "club.do.html").read_text(encoding="utf-8")

    class InstitutionalClubFixtureSource(services_module.InstitutionalClubGuideSource):
        def fetch(self) -> str:
            return (FIXTURES_DIR / "institutional_club1.do.html").read_text(encoding="utf-8")

    monkeypatch.setattr(services_module, "StudentGovernmentGuideSource", GovernmentFixtureSource)
    monkeypatch.setattr(services_module, "CampusMediaGuideSource", MediaFixtureSource)
    monkeypatch.setattr(
        services_module,
        "SocialVolunteeringGuideSource",
        VolunteerFixtureSource,
    )
    monkeypatch.setattr(services_module, "RotcGuideSource", RotcFixtureSource)
    monkeypatch.setattr(services_module, "CentralClubGuideSource", CentralClubFixtureSource)
    monkeypatch.setattr(
        services_module,
        "InstitutionalClubGuideSource",
        InstitutionalClubFixtureSource,
    )

    with connection() as conn:
        guides = refresh_student_activity_guides_from_source(
            conn,
            fetched_at="2026-03-21T00:00:00+09:00",
        )

    topics = [item.topic for item in guides]

    assert topics.count("campus_media") == 4
    assert topics.count("central_clubs") == 4
    assert topics.count("institutional_clubs") == 6
    assert topics.count("rotc") == 1
    assert topics.count("social_volunteering") == 4
    assert topics.count("student_government") == 3
    assert services_module.PUBLIC_READY_DATASET_POLICIES["student_activity_guides"] == "core"


def test_list_wifi_guides_preserves_snapshot_order_and_limit(app_env):
    init_db()

    with connection() as conn:
        repo.replace_wifi_guides(
            conn,
            [
                {
                    "building_name": "니콜스관",
                    "ssids": ["catholic_univ"],
                    "steps": ["SSID 선택"],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/wifi.do",
                    "source_tag": "cuk_wifi_guides",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
                {
                    "building_name": "그 외 건물",
                    "ssids": ["catholic_univ", "catholic_건물명"],
                    "steps": ["SSID 선택"],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/wifi.do",
                    "source_tag": "cuk_wifi_guides",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
            ],
        )
        guides = list_wifi_guides(conn, limit=1)

    assert [item.building_name for item in guides] == ["니콜스관"]


def test_refresh_campus_life_support_guides_uses_all_default_sources(app_env, monkeypatch):
    init_db()

    class FakeGuideSource:
        def __init__(self, topic: str, url: str):
            self.topic = topic
            self.url = url

        def fetch(self):
            return "<guide />"

        def parse(self, html: str, *, fetched_at: str):
            assert html == "<guide />"
            return [
                {
                    "topic": self.topic,
                    "title": f"{self.topic} title",
                    "summary": f"{self.topic} summary",
                    "steps": [f"{self.topic} step"],
                    "links": [],
                    "source_url": self.url,
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    monkeypatch.setattr(
        services_module,
        "HealthCenterGuideSource",
        lambda url: FakeGuideSource("health_center", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "LostFoundGuideSource",
        lambda url: FakeGuideSource("lost_found", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "ParkingGuideSource",
        lambda url: FakeGuideSource("parking", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "MobilitySafetyGuideSource",
        lambda url: FakeGuideSource("mobility_safety", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "FacilityRentalGuideSource",
        lambda url: FakeGuideSource("facility_rental", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "StudentCounselingGuideSource",
        lambda url: FakeGuideSource("student_counseling", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "DisabilitySupportGuideSource",
        lambda url: FakeGuideSource("disability_support", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "StudentReservistGuideSource",
        lambda url: FakeGuideSource("student_reservist", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "HospitalUseGuideSource",
        lambda url: FakeGuideSource("hospital_use", url),
        raising=False,
    )
    monkeypatch.setattr(
        services_module,
        "CareerCounselingGuideSource",
        lambda url: FakeGuideSource("career_counseling", url),
        raising=False,
    )

    with connection() as conn:
        guides = refresh_campus_life_support_guides_from_source(conn)

    assert len(guides) == 10
    assert {item.topic for item in guides} == {
        "health_center",
        "lost_found",
        "parking",
        "mobility_safety",
        "facility_rental",
        "student_counseling",
        "disability_support",
        "student_reservist",
        "hospital_use",
        "career_counseling",
    }
    assert {item.title for item in guides} == {
        "health_center title",
        "lost_found title",
        "parking title",
        "mobility_safety title",
        "facility_rental title",
        "student_counseling title",
        "disability_support title",
        "student_reservist title",
        "hospital_use title",
        "career_counseling title",
    }
    assert services_module.PUBLIC_READY_DATASET_POLICIES["campus_life_support_guides"] == "core"


def test_list_scholarship_guides_preserves_snapshot_order_and_limit(app_env):
    init_db()

    with connection() as conn:
        repo.replace_scholarship_guides(
            conn,
            [
                {
                    "title": "장학생 자격",
                    "summary": "당해학기 정규학기 재학생",
                    "steps": [],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/support/scholarship_songsim.do",
                    "source_tag": "cuk_scholarship_guides",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
                {
                    "title": "공식 장학 문서",
                    "summary": "장학금 지급 규정과 공식 문서 링크",
                    "steps": [],
                    "links": [
                        {
                            "label": "재학생 장학제도",
                            "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/scholarship_songsim_251226-4pdf.pdf",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/support/scholarship_songsim.do",
                    "source_tag": "cuk_scholarship_guides",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
            ],
        )
        guides = list_scholarship_guides(conn, limit=1)

    assert [item.title for item in guides] == ["장학생 자격"]


def test_list_academic_calendar_defaults_to_current_academic_year_and_prioritizes_songsim(
    app_env,
    monkeypatch,
):
    init_db()
    monkeypatch.setattr("songsim_campus.services._current_academic_year", lambda today=None: 2026)

    with connection() as conn:
        repo.replace_academic_calendar(
            conn,
            [
                {
                    "academic_year": 2025,
                    "title": "이전 학년도 행사",
                    "start_date": "2025-03-05",
                    "end_date": "2025-03-05",
                    "campuses": ["성심"],
                    "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
                {
                    "academic_year": 2026,
                    "title": "성의 전용 행사",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-01",
                    "campuses": ["성의"],
                    "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
                {
                    "academic_year": 2026,
                    "title": "1학기 개시일",
                    "start_date": "2026-03-03",
                    "end_date": "2026-03-03",
                    "campuses": ["성심", "성의", "성신"],
                    "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
            ],
        )
        events = list_academic_calendar(conn, limit=10)

    assert [item.title for item in events] == ["1학기 개시일", "성의 전용 행사"]


def test_list_academic_calendar_filters_by_month_and_query(app_env):
    init_db()

    with connection() as conn:
        repo.replace_academic_calendar(
            conn,
            [
                {
                    "academic_year": 2026,
                    "title": "추가 등록기간",
                    "start_date": "2026-03-31",
                    "end_date": "2026-04-03",
                    "campuses": ["성심"],
                    "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
                {
                    "academic_year": 2026,
                    "title": "중간고사",
                    "start_date": "2026-04-20",
                    "end_date": "2026-04-24",
                    "campuses": ["성심"],
                    "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
                {
                    "academic_year": 2026,
                    "title": "3월 행사",
                    "start_date": "2026-03-10",
                    "end_date": "2026-03-10",
                    "campuses": ["성심"],
                    "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                    "source_tag": "cuk_academic_calendar",
                    "last_synced_at": "2026-03-17T15:00:00+09:00",
                },
            ],
        )
        april = list_academic_calendar(conn, academic_year=2026, month=4, limit=10)
        registration = list_academic_calendar(conn, academic_year=2026, query="등록", limit=10)

    assert [item.title for item in april] == ["추가 등록기간", "중간고사"]
    assert [item.title for item in registration] == ["추가 등록기간"]


def test_list_transport_guides_infers_mode_from_query_and_normalizes_spacing(app_env):
    init_db()

    with connection() as conn:
        repo.replace_transport_guides(
            conn,
            [
                {
                    "mode": "bus",
                    "title": "마을버스",
                    "summary": "51번, 51-1번, 51-2번 버스",
                    "steps": ["[가톨릭대학교, 역곡도서관] 정류장 하차"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "mode": "subway",
                    "title": "1호선",
                    "summary": "역곡역 2번 출구 또는 소사역 3번 출구에서 도보 10분",
                    "steps": ["인천역 ↔ 역곡역 : 35분 소요"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        guides = list_transport_guides(conn, query="지하 철", limit=10)

    assert [guide.mode for guide in guides] == ["subway"]
    assert guides[0].title == "1호선"


def test_list_transport_guides_returns_empty_for_unsupported_shuttle_query(app_env):
    init_db()

    with connection() as conn:
        repo.replace_transport_guides(
            conn,
            [
                {
                    "mode": "bus",
                    "title": "마을버스",
                    "summary": "51번, 51-1번, 51-2번 버스",
                    "steps": ["[가톨릭대학교, 역곡도서관] 정류장 하차"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        guides = list_transport_guides(conn, query="셔틀", limit=10)

    assert guides == []


def test_list_transport_guides_explicit_mode_wins_over_query(app_env):
    init_db()

    with connection() as conn:
        repo.replace_transport_guides(
            conn,
            [
                {
                    "mode": "bus",
                    "title": "시내버스",
                    "summary": "3번, 5번 버스",
                    "steps": ["성심교정 정문 앞 정류장 하차"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "mode": "subway",
                    "title": "1호선",
                    "summary": "역곡역 2번 출구 또는 소사역 3번 출구에서 도보 10분",
                    "steps": ["인천역 ↔ 역곡역 : 35분 소요"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        guides = list_transport_guides(conn, mode="bus", query="지하철", limit=10)

    assert [guide.mode for guide in guides] == ["bus"]
    assert guides[0].title == "시내버스"


def test_list_transport_guides_neutral_query_reorders_by_text_match(app_env):
    init_db()

    with connection() as conn:
        repo.replace_transport_guides(
            conn,
            [
                {
                    "mode": "bus",
                    "title": "마을버스",
                    "summary": "51번, 51-1번, 51-2번 버스",
                    "steps": ["[가톨릭대학교, 역곡도서관] 정류장 하차"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "mode": "subway",
                    "title": "1호선",
                    "summary": "역곡역 2번 출구 또는 소사역 3번 출구에서 도보 10분",
                    "steps": ["인천역 ↔ 역곡역 : 35분 소요"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        guides = list_transport_guides(conn, query="2번 출구", limit=10)

    assert [guide.title for guide in guides] == ["1호선", "마을버스"]


def test_sync_official_snapshot_runs_opening_hours_before_courses_and_transport(
    app_env,
    monkeypatch,
):
    call_order: list[str] = []

    monkeypatch.setattr(
        'songsim_campus.services.refresh_places_from_campus_map',
        lambda conn, campus=None: call_order.append('places') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_campus_facilities_from_source',
        lambda conn: call_order.append('campus_facilities') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_library_hours_from_library_page',
        lambda conn: call_order.append('library') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_facility_hours_from_facilities_page',
        lambda conn: call_order.append('facilities') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_campus_dining_menus_from_facilities_page',
        lambda conn: call_order.append('dining_menus') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_courses_from_subject_search',
        lambda conn, year=None, semester=None: call_order.append('courses') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_notices_from_notice_board',
        lambda conn, pages=None: call_order.append('notices') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_affiliated_notices_from_sources',
        lambda conn, pages=None: call_order.append('affiliated_notices') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_campus_life_notices_from_source',
        lambda conn: call_order.append('campus_life_notices') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_academic_calendar_from_source',
        lambda conn: call_order.append('academic_calendar') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_certificate_guides_from_certificate_page',
        lambda conn: call_order.append('certificate_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_leave_of_absence_guides_from_source',
        lambda conn: call_order.append('leave_of_absence_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_academic_status_guides_from_source',
        lambda conn: call_order.append('academic_status_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_registration_guides_from_source',
        lambda conn: call_order.append('registration_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_class_guides_from_source',
        lambda conn: call_order.append('class_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_seasonal_semester_guides_from_source',
        lambda conn: call_order.append('seasonal_semester_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_academic_milestone_guides_from_source',
        lambda conn: call_order.append('academic_milestone_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_student_activity_guides_from_source',
        lambda conn: call_order.append('student_activity_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_student_activity_notices_from_source',
        lambda conn: call_order.append('student_activity_notices') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_about_resource_guides_from_source',
        lambda conn: call_order.append('about_resource_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_service_policy_guides_from_source',
        lambda conn: call_order.append('service_policy_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_newsroom_posts_from_source',
        lambda conn: call_order.append('newsroom_posts') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_student_exchange_guides_from_source',
        lambda conn: call_order.append('student_exchange_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_campus_life_support_guides_from_source',
        lambda conn: call_order.append('campus_life_support_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_pc_software_entries_from_source',
        lambda conn: call_order.append('pc_software_entries') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_dormitory_guides_from_source',
        lambda conn: call_order.append('dormitory_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_phone_book_entries_from_source',
        lambda conn: call_order.append('phone_book_entries') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_student_exchange_partners_from_source',
        lambda conn: call_order.append('student_exchange_partners') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_scholarship_guides_from_source',
        lambda conn: call_order.append('scholarship_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_academic_support_guides_from_source',
        lambda conn: call_order.append('academic_support_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_wifi_guides_from_source',
        lambda conn: call_order.append('wifi_guides') or [],
    )
    monkeypatch.setattr(
        'songsim_campus.services.refresh_transport_guides_from_location_page',
        lambda conn: call_order.append('transport') or [],
    )

    init_db()
    with connection() as conn:
        summary = sync_official_snapshot(conn, year=2026, semester=1, notice_pages=1)

    assert call_order == [
        'places',
        'campus_facilities',
        'library',
        'facilities',
        'dining_menus',
        'courses',
        'notices',
        'affiliated_notices',
        'campus_life_notices',
        'academic_calendar',
        'certificate_guides',
        'leave_of_absence_guides',
        'academic_status_guides',
        'registration_guides',
        'class_guides',
        'seasonal_semester_guides',
        'academic_milestone_guides',
        'student_activity_guides',
        'student_activity_notices',
        'about_resource_guides',
        'service_policy_guides',
        'newsroom_posts',
        'student_exchange_guides',
        'dormitory_guides',
        'phone_book_entries',
        'campus_life_support_guides',
        'pc_software_entries',
        'student_exchange_partners',
        'scholarship_guides',
        'academic_support_guides',
        'wifi_guides',
        'transport',
    ]
    assert summary['campus_facilities'] == 0
    assert summary['dining_menus'] == 0
    assert summary['academic_calendar'] == 0
    assert summary['certificate_guides'] == 0
    assert summary['leave_of_absence_guides'] == 0
    assert summary['academic_status_guides'] == 0
    assert summary['registration_guides'] == 0
    assert summary['class_guides'] == 0
    assert summary['seasonal_semester_guides'] == 0
    assert summary['academic_milestone_guides'] == 0
    assert summary['student_activity_guides'] == 0
    assert summary['student_activity_notices'] == 0
    assert summary['about_resource_guides'] == 0
    assert summary['service_policy_guides'] == 0
    assert summary['newsroom_posts'] == 0
    assert summary['affiliated_notices'] == 0
    assert summary['campus_life_notices'] == 0
    assert summary['campus_life_support_guides'] == 0
    assert summary['dormitory_guides'] == 0
    assert summary['phone_book_entries'] == 0
    assert summary['scholarship_guides'] == 0
    assert summary['academic_support_guides'] == 0
    assert summary['wifi_guides'] == 0
    assert summary['transport_guides'] == 0
