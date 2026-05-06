from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from songsim_campus import api as api_module
from songsim_campus import services
from songsim_campus.api import create_app
from songsim_campus.api_docs import build_filtered_openapi
from songsim_campus.api_pages import (
    render_admin_observability_page,
    render_admin_sync_page,
    render_landing_page,
)
from songsim_campus.db import connection, init_db
from songsim_campus.repo import (
    replace_campus_facilities,
    replace_courses,
    replace_notices,
    replace_places,
    replace_restaurants,
    replace_transport_guides,
    update_place_opening_hours,
)
from songsim_campus.schemas import CampusLifeNotice
from songsim_campus.services import (
    refresh_academic_calendar_from_source,
    refresh_academic_status_guides_from_source,
    refresh_academic_support_guides_from_source,
    refresh_affiliated_notices_from_sources,
    refresh_campus_dining_menus_from_facilities_page,
    refresh_certificate_guides_from_certificate_page,
    refresh_facility_hours_from_facilities_page,
    refresh_leave_of_absence_guides_from_source,
    refresh_scholarship_guides_from_source,
    refresh_transport_guides_from_location_page,
    refresh_wifi_guides_from_source,
)
from songsim_campus.settings import clear_settings_cache


def test_healthz(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json() == {'ok': True}


def test_campus_life_notices_api_uses_services_wiring():
    assert api_module.list_campus_life_notices.__module__ == "songsim_campus.services"


def test_readyz_reports_database_and_table_status(client):
    response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["database"]["ok"] is True
    assert payload["tables"]["places"]["ok"] is True
    assert payload["tables"]["places"]["policy"] == "core"
    assert payload["tables"]["courses"]["ok"] is True
    assert payload["tables"]["courses"]["policy"] == "optional"
    assert payload["tables"]["sync_runs"]["ok"] is True


def test_readyz_marks_empty_required_public_dataset_as_not_ready(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    def fake_dataset_state(conn, table: str):
        if table == "certificate_guides":
            return {"name": table, "row_count": 0, "last_synced_at": None}
        return {
            "name": table,
            "row_count": 1,
            "last_synced_at": "2026-03-17T16:00:00+09:00",
        }

    monkeypatch.setattr("songsim_campus.services.repo.get_dataset_sync_state", fake_dataset_state)

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get("/readyz")

    clear_settings_cache()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["tables"]["certificate_guides"]["ok"] is False
    assert payload["tables"]["certificate_guides"]["policy"] == "core"
    assert payload["tables"]["certificate_guides"]["reason"] == "empty_or_unsynced"


def test_healthz_stays_liveness_only_when_required_public_dataset_is_empty(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    def fake_dataset_state(conn, table: str):
        if table == "certificate_guides":
            return {"name": table, "row_count": 0, "last_synced_at": None}
        return {
            "name": table,
            "row_count": 1,
            "last_synced_at": "2026-03-17T16:00:00+09:00",
        }

    monkeypatch.setattr("songsim_campus.services.repo.get_dataset_sync_state", fake_dataset_state)

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get("/healthz")

    clear_settings_cache()

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_readyz_caches_snapshot_within_ttl(app_env, monkeypatch):
    current = {"value": datetime.fromisoformat("2026-03-17T18:00:00+09:00")}
    dataset_calls: list[str] = []

    monkeypatch.setattr("songsim_campus.services._now", lambda: current["value"])

    def fake_dataset_state(conn, table: str):
        dataset_calls.append(table)
        return {
            "name": table,
            "row_count": 1,
            "last_synced_at": "2026-03-17T17:59:00+09:00",
        }

    monkeypatch.setattr("songsim_campus.services.repo.get_dataset_sync_state", fake_dataset_state)
    monkeypatch.setattr("songsim_campus.services.repo.list_sync_runs", lambda conn, limit=1: [])

    app = create_app()
    with TestClient(app) as public_client:
        first = public_client.get("/readyz")
        current["value"] += timedelta(seconds=10)
        second = public_client.get("/readyz")

    assert first.status_code == 200
    assert second.status_code == 200
    assert dataset_calls == list(services.SYNC_DATASET_TABLES)


def test_readyz_returns_stale_payload_while_refresh_is_slow(app_env, monkeypatch):
    current = {"value": datetime.fromisoformat("2026-03-17T18:30:00+09:00")}
    stale_snapshot = {
        "ok": True,
        "database": {"ok": True, "error": None},
        "tables": {
            **{
                table: {
                    "ok": True,
                    "name": f"{table}-stale",
                    "row_count": 1,
                    "last_synced_at": "2026-03-17T18:29:00+09:00",
                }
                for table in services.SYNC_DATASET_TABLES
            },
            "sync_runs": {"ok": True},
        },
    }
    fresh_snapshot = {
        "ok": True,
        "database": {"ok": True, "error": None},
        "tables": {
            **{
                table: {
                    "ok": True,
                    "name": f"{table}-fresh",
                    "row_count": 1,
                    "last_synced_at": "2026-03-17T18:31:00+09:00",
                }
                for table in services.SYNC_DATASET_TABLES
            },
            "sync_runs": {"ok": True},
        },
    }
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    monkeypatch.setattr("songsim_campus.services._now", lambda: current["value"])
    monkeypatch.setattr(
        "songsim_campus.services._compute_readiness_snapshot",
        lambda settings: stale_snapshot,
    )
    assert services.get_readiness_snapshot() == stale_snapshot

    current["value"] += timedelta(seconds=31)

    def slow_refresh(settings):
        started.set()
        release.wait(timeout=2)
        finished.set()
        return fresh_snapshot

    monkeypatch.setattr("songsim_campus.services._compute_readiness_snapshot", slow_refresh)

    app = create_app()
    with TestClient(app) as public_client:
        started_at = time.perf_counter()
        response = public_client.get("/readyz")
        elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert response.status_code == 200
    assert response.json() == stale_snapshot
    assert elapsed_ms < 200
    assert started.wait(timeout=1)

    release.set()
    assert finished.wait(timeout=1)


def test_admin_sync_route_is_disabled_by_default(client):
    response = client.get("/admin/sync")

    assert response.status_code == 404


def test_admin_observability_routes_are_disabled_by_default(client):
    html_response = client.get("/admin/observability")
    json_response = client.get("/admin/observability.json")

    assert html_response.status_code == 404
    assert json_response.status_code == 404


def test_public_readonly_mode_exposes_only_public_routes(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_ADMIN_ENABLED", "true")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-api.onrender.com")
    monkeypatch.setenv("SONGSIM_PUBLIC_MCP_URL", "https://songsim-mcp.onrender.com/mcp")
    def stub_affiliated_notices(conn, topic=None, query=None, limit=20):
        return [
            {
                "id": 1,
                "topic": "international_studies",
                "title": "국제학부 공지",
                "published_at": "2026-03-20",
                "summary": "국제학부 학사 공지",
                "source_url": "https://is.catholic.ac.kr/is/community/notice.do?mode=view&articleNo=1",
                "source_tag": "cuk_affiliated_notice_boards",
                "last_synced_at": "2026-03-20T10:00:00+09:00",
            }
        ]
    def stub_campus_life_notices(conn, topic=None, query=None, limit=20):
        if topic == "events":
            return [
                CampusLifeNotice(
                    id=266521,
                    topic="events",
                    title="[음악과] 『개교 170주년 기념』성심 오케스트라 연주회",
                    published_at="2025-11-28",
                    summary=(
                        "음악과에서 『개교 170주년 기념』성심 오케스트라 연주회를 개최하오니 "
                        "많은 관심과 참여 부탁드립니다."
                    ),
                    source_url="https://www.catholic.ac.kr/ko/campuslife/notice_event.do?mode=view&articleNo=266521&article.offset=0&articleLimit=16",
                    source_tag="cuk_campus_life_notices",
                    last_synced_at="2026-03-20T10:00:00+09:00",
                )
            ]
        return [
            CampusLifeNotice(
                id=269665,
                topic="outside_agencies",
                title="[인천병무지청] 2026년 4월 각 군 모집일정 안내",
                published_at="2026-03-20",
                summary=(
                    "접수기간: 2026.3.27.(금) 14시 ~ 2026.4.2.(목) 14시 "
                    "지원방법: 병무청 누리집"
                ),
                source_url="https://www.catholic.ac.kr/ko/campuslife/notice_outside.do?mode=view&articleNo=269665&article.offset=0&articleLimit=10",
                source_tag="cuk_campus_life_notices",
                last_synced_at="2026-03-20T10:00:00+09:00",
            )
        ]
    def stub_dormitory_guides(conn, topic=None, limit=20):
        return [
            {
                "id": 1,
                "topic": "hall_info",
                "title": "스테파노관",
                "summary": "성심교정 기숙사 소개",
                "steps": ["스테파노관 소개"],
                "links": [],
                "source_url": "https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do",
                "source_tag": "cuk_dormitory_guides",
                "last_synced_at": "2026-03-20T10:00:00+09:00",
            }
        ]
    def stub_student_exchange_guides(conn, topic=None, limit=20):
        return [
            {
                "id": 1,
                "topic": "exchange_student",
                "title": "상호교환 프로그램",
                "summary": "해외 교환학생 프로그램 안내",
                "steps": ["학기당 최대 19학점"],
                "links": [
                    {
                        "label": "교환학생 프로그램 알아보기",
                        "url": "https://oia.catholic.ac.kr/oia/admission/exchange-student.do",
                    }
                ],
                "source_url": "https://www.catholic.ac.kr/ko/support/exchange_oversea2.do",
                "source_tag": "cuk_student_exchange_guides",
                "last_synced_at": "2026-03-20T10:00:00+09:00",
            }
        ]
    def stub_student_activity_guides(conn, topic=None, limit=20):
        return [
            {
                "id": 1,
                "topic": "student_government",
                "title": "총학생회",
                "summary": "학생 자치 대표 기구",
                "steps": ["학생 의견 수렴"],
                "links": [],
                "source_url": "https://example.com/student-activity",
                "source_tag": "cuk_student_activity_guides",
                "last_synced_at": "2026-03-20T10:00:00+09:00",
            }
        ]
    def stub_about_resource_guides(conn, topic=None, limit=20):
        return [
            {
                "id": 1,
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
                "last_synced_at": "2026-03-20T10:00:00+09:00",
            }
        ]
    def stub_student_exchange_partners(conn, query=None, limit=20):
        return [
            {
                "id": 1,
                "partner_code": "00122",
                "university_name": "Utrecht University",
                "country_ko": "네덜란드",
                "country_en": "NETHERLANDS",
                "continent": "EUROPE",
                "location": "Utrecht",
                "agreement_date": None,
                "homepage_url": "https://www.uu.nl",
                "source_url": "https://www.catholic.ac.kr/ko/support/exchange_oversea1.do",
                "source_tag": "cuk_student_exchange_partners",
                "last_synced_at": "2026-03-20T10:00:00+09:00",
            }
        ]
    def stub_campus_life_support_guides(conn, topic=None, limit=20):
        topics = {
            "health_center": [
                {
                    "id": 1,
                    "topic": "health_center",
                    "title": "보건실",
                    "summary": "보건실 안내",
                    "steps": ["위치: 비르투스관 1층 104호"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/health.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
            "student_counseling": [
                {
                    "id": 2,
                    "topic": "student_counseling",
                    "title": "학생생활상담소",
                    "summary": "학생생활상담소 안내",
                    "steps": ["학생생활상담소 소개"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/counsel.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
            "disability_support": [
                {
                    "id": 3,
                    "topic": "disability_support",
                    "title": "장애학생지원센터",
                    "summary": "장애학생지원센터 안내",
                    "steps": ["학습지원"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/disability_service.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
            "student_reservist": [
                {
                    "id": 4,
                    "topic": "student_reservist",
                    "title": "직장예비군 가톨릭대학교 대대",
                    "summary": "직장예비군 안내",
                    "steps": ["편성안내"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/student_reservist.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
            "hospital_use": [
                {
                    "id": 5,
                    "topic": "hospital_use",
                    "title": "부속병원이용",
                    "summary": "부속병원이용 안내",
                    "steps": ["중앙의료원 소개"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/hospital1.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
            "facility_rental": [
                {
                    "id": 6,
                    "topic": "facility_rental",
                    "title": "콘서트홀",
                    "summary": "1~4시간: 2,000,000 원",
                    "steps": ["1~4시간: 2,000,000 원"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/rent_songsim.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
            "mobility_safety": [
                {
                    "id": 7,
                    "topic": "mobility_safety",
                    "title": "개인형 이동장치 안전관리교육",
                    "summary": "개인형 이동장치 운행 전 반드시 교육영상을 시청해주시기 바랍니다.",
                    "steps": ["개인형 이동장치 운행 전 반드시 교육영상을 시청해주시기 바랍니다."],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/service/safety.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
            "career_counseling": [
                {
                    "id": 8,
                    "topic": "career_counseling",
                    "title": "진로/취업 상담",
                    "summary": "가톨릭대학교 학부생 및 졸업생",
                    "steps": [
                        "가톨릭대학교 학부생 및 졸업생",
                        (
                            "트리니티 → AI코디(aicodi.catholic.ac.kr) → 통합상담 "
                            "→ 진로취업상담 → 상담신청"
                        ),
                    ],
                    "links": [
                        {
                            "label": "aicodi.catholic.ac.kr",
                            "url": "https://aicodi.catholic.ac.kr/",
                        }
                    ],
                    "source_url": (
                        "https://career.catholic.ac.kr/career/job/job_counseling.do"
                    ),
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        }
        return topics.get(topic, topics["health_center"])
    def stub_pc_software_entries(conn, query=None, limit=20):
        return [
            {
                "id": 1,
                "room": "마리아관 1실습실 (M307)",
                "pc_count": 51,
                "software_list": ["SPSS 25", "포토샵 CS6"],
                "source_url": "https://www.catholic.ac.kr/ko/campuslife/pc.do",
                "source_tag": "cuk_pc_software",
                "last_synced_at": "2026-03-20T10:00:00+09:00",
            }
        ]
    monkeypatch.setattr(services, "list_affiliated_notices", stub_affiliated_notices, raising=False)
    monkeypatch.setattr(services, "list_dormitory_guides", stub_dormitory_guides, raising=False)
    monkeypatch.setattr(
        services,
        "list_student_exchange_guides",
        stub_student_exchange_guides,
        raising=False,
    )
    monkeypatch.setattr(
        services,
        "list_student_activity_guides",
        stub_student_activity_guides,
        raising=False,
    )
    monkeypatch.setattr(
        services,
        "list_about_resource_guides",
        stub_about_resource_guides,
        raising=False,
    )
    monkeypatch.setattr(
        services,
        "search_student_exchange_partners",
        stub_student_exchange_partners,
        raising=False,
    )
    monkeypatch.setattr(
        services,
        "list_campus_life_support_guides",
        stub_campus_life_support_guides,
        raising=False,
    )
    monkeypatch.setattr(
        services,
        "search_pc_software_entries",
        stub_pc_software_entries,
        raising=False,
    )
    monkeypatch.setattr("songsim_campus.api.list_dormitory_guides", stub_dormitory_guides)
    monkeypatch.setattr(
        "songsim_campus.api.list_student_exchange_guides",
        stub_student_exchange_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.api.list_student_activity_guides",
        stub_student_activity_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.api.list_about_resource_guides",
        stub_about_resource_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.api.search_student_exchange_partners",
        stub_student_exchange_partners,
    )
    monkeypatch.setattr(
        "songsim_campus.api.list_campus_life_support_guides",
        stub_campus_life_support_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.api.list_campus_life_notices",
        stub_campus_life_notices,
    )
    monkeypatch.setattr(
        "songsim_campus.api.search_pc_software_entries",
        stub_pc_software_entries,
    )
    clear_settings_cache()

    app = create_app()
    with TestClient(app) as public_client:
        landing = public_client.get("/")
        docs = public_client.get("/docs")
        openapi = public_client.get("/openapi.json")
        places = public_client.get("/places", params={"query": "도서관"})
        affiliated_notices = public_client.get(
            "/affiliated-notices",
            params={"topic": "international_studies", "query": "공지"},
        )
        dormitory_guides = public_client.get(
            "/dormitory-guides",
            params={"topic": "hall_info"},
        )
        student_exchange_guides = public_client.get(
            "/student-exchange-guides",
            params={"topic": "exchange_student"},
        )
        student_activity_guides = public_client.get(
            "/student-activity-guides",
            params={"topic": "student_government"},
        )
        about_resource_guides = public_client.get(
            "/about-resource-guides",
            params={"topic": "rules"},
        )
        student_exchange_partners = public_client.get(
            "/student-exchange-partners",
            params={"query": "Utrecht"},
        )
        campus_life_support = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "health_center"},
        )
        campus_life_support_counseling = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "student_counseling"},
        )
        campus_life_support_disability = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "disability_support"},
        )
        campus_life_support_reservist = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "student_reservist"},
        )
        campus_life_support_hospital = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "hospital_use"},
        )
        campus_life_support_rental = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "facility_rental"},
        )
        campus_life_support_safety = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "mobility_safety"},
        )
        campus_life_support_career = public_client.get(
            "/campus-life-support-guides",
            params={"topic": "career_counseling"},
        )
        campus_life_notices = public_client.get(
            "/campus-life-notices",
            params={"query": "외부기관공지"},
        )
        campus_life_events = public_client.get(
            "/campus-life-notices",
            params={"topic": "events", "limit": 5},
        )
        pc_software = public_client.get(
            "/pc-software",
            params={"query": "SPSS"},
        )
        create_profile = public_client.post("/profiles", json={"display_name": "성심학생"})
        admin_sync = public_client.get("/admin/sync")

    clear_settings_cache()

    assert landing.status_code == 200
    assert "Songsim Campus MCP" in landing.text
    assert "https://songsim-api.onrender.com" in landing.text
    assert "https://songsim-mcp.onrender.com/mcp" in landing.text
    assert "/academic-support-guides" in landing.text
    assert "/academic-status-guides" in landing.text
    assert "/registration-guides" in landing.text
    assert "/class-guides" in landing.text
    assert "/seasonal-semester-guides" in landing.text
    assert "/academic-milestone-guides" in landing.text
    assert "/student-activity-guides" in landing.text
    assert "/about-resource-guides" in landing.text
    assert "/student-exchange-guides" in landing.text
    assert "/student-exchange-partners" in landing.text
    assert "/phone-book" in landing.text
    assert "/campus-life-support-guides" in landing.text
    assert "/campus-life-notices" in landing.text
    assert "행사안내 알려줘" in landing.text
    assert "학생상담 어디서 받아?" in landing.text
    assert "장애학생지원센터 뭐 해줘?" in landing.text
    assert "예비군 신고 시기 알려줘" in landing.text
    assert "부속병원 이용 안내해줘" in landing.text
    assert "성심교정 대관안내 알려줘" in landing.text
    assert "개인형 이동장치 안전교육 알려줘" in landing.text
    assert "진로/취업 상담 어디서 신청해?" in landing.text
    assert "/pc-software" in landing.text
    assert "/affiliated-notices" in landing.text
    assert "/dormitory-guides" in landing.text
    assert "configured without OAuth" in landing.text
    assert "GPT Actions OpenAPI" not in landing.text
    assert "/gpt/*" not in landing.text
    assert "Admin Sync" not in landing.text
    assert docs.status_code == 200
    assert places.status_code == 200
    assert affiliated_notices.status_code == 200
    assert affiliated_notices.json()[0]["topic"] == "international_studies"
    assert dormitory_guides.status_code == 200
    assert dormitory_guides.json()[0]["title"] == "스테파노관"
    assert student_exchange_guides.status_code == 200
    assert student_exchange_guides.json()[0]["topic"] == "exchange_student"
    assert student_activity_guides.status_code == 200
    assert student_activity_guides.json()[0]["topic"] == "student_government"
    assert about_resource_guides.status_code == 200
    assert about_resource_guides.json()[0]["topic"] == "rules"
    assert student_exchange_partners.status_code == 200
    assert student_exchange_partners.json()[0]["partner_code"] == "00122"
    assert campus_life_support.status_code == 200
    assert campus_life_support.json()[0]["topic"] == "health_center"
    assert campus_life_support_counseling.status_code == 200
    assert campus_life_support_counseling.json()[0]["topic"] == "student_counseling"
    assert campus_life_support_disability.status_code == 200
    assert campus_life_support_disability.json()[0]["topic"] == "disability_support"
    assert campus_life_support_reservist.status_code == 200
    assert campus_life_support_reservist.json()[0]["topic"] == "student_reservist"
    assert campus_life_support_hospital.status_code == 200
    assert campus_life_support_hospital.json()[0]["topic"] == "hospital_use"
    assert campus_life_support_rental.status_code == 200
    assert campus_life_support_rental.json()[0]["topic"] == "facility_rental"
    assert campus_life_support_safety.status_code == 200
    assert campus_life_support_safety.json()[0]["topic"] == "mobility_safety"
    assert campus_life_support_career.status_code == 200
    assert campus_life_support_career.json()[0]["topic"] == "career_counseling"
    assert campus_life_notices.status_code == 200
    assert campus_life_notices.json()[0]["topic"] == "outside_agencies"
    assert campus_life_events.status_code == 200
    assert campus_life_events.json()[0]["topic"] == "events"
    assert pc_software.status_code == 200
    assert pc_software.json()[0]["room"] == "마리아관 1실습실 (M307)"
    assert create_profile.status_code == 404
    assert admin_sync.status_code == 404
    assert "/academic-support-guides" in openapi.text
    assert "/academic-status-guides" in openapi.text
    assert "/registration-guides" in openapi.text
    assert "/class-guides" in openapi.text
    assert "/seasonal-semester-guides" in openapi.text
    assert "/academic-milestone-guides" in openapi.text
    assert "/student-activity-guides" in openapi.text
    assert "/about-resource-guides" in openapi.text
    assert "/student-exchange-guides" in openapi.text
    assert "/student-exchange-partners" in openapi.text
    assert "/phone-book" in openapi.text
    assert "/campus-life-support-guides" in openapi.text
    assert "/campus-life-notices" in openapi.text
    assert "/pc-software" in openapi.text
    assert "/affiliated-notices" in openapi.text
    assert "/dormitory-guides" in openapi.text
    assert "/profiles" not in openapi.text
    assert "/admin/sync" not in openapi.text


def test_public_readonly_mode_skips_automation_loop(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_AUTOMATION_ENABLED", "true")
    clear_settings_cache()

    calls: list[str] = []

    def fail_get_connection():
        calls.append("called")
        raise AssertionError("public readonly automation loop should not start")

    monkeypatch.setattr(api_module, "get_connection", fail_get_connection)

    app = create_app()
    with TestClient(app):
        time.sleep(0.05)

    clear_settings_cache()

    assert calls == []


def test_public_readonly_mode_skips_startup_sync(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_SYNC_OFFICIAL_ON_START", "true")
    clear_settings_cache()

    calls: list[str] = []

    def fail_sync(conn):
        calls.append("called")
        raise AssertionError("public readonly startup sync should not run")

    monkeypatch.setattr(api_module, "sync_official_snapshot", fail_sync)

    app = create_app()
    with TestClient(app):
        pass

    clear_settings_cache()

    assert calls == []


def test_public_readonly_affiliated_notices_deduplicate_titles(app_env, monkeypatch):
    init_db()
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    class DuplicateAffiliatedNoticeSource:
        topic = "international_studies"
        source_tag = "cuk_affiliated_notice_boards"

        def fetch_list(self, offset: int = 0, limit: int = 10):
            return "<list></list>"

        def parse_list(self, _html: str):
            return [
                {
                    "topic": self.topic,
                    "article_no": "100",
                    "title": "국제학부 공지",
                    "published_at": "2026-03-20",
                    "summary": "국제학부 학사 공지",
                    "source_url": "https://is.catholic.ac.kr/is/community/notice.do?mode=view&articleNo=100",
                    "source_tag": self.source_tag,
                },
                {
                    "topic": self.topic,
                    "article_no": "100",
                    "title": "국제학부 공지",
                    "published_at": "2026-03-20",
                    "summary": "중복 공지",
                    "source_url": "https://is.catholic.ac.kr/is/community/notice.do?mode=view&articleNo=100",
                    "source_tag": self.source_tag,
                },
                {
                    "topic": self.topic,
                    "article_no": "101",
                    "title": "국제학부 공결 신청 안내",
                    "published_at": "2026-03-19",
                    "summary": "국제학부 공결 신청 안내",
                    "source_url": "https://is.catholic.ac.kr/is/community/notice.do?mode=view&articleNo=101",
                    "source_tag": self.source_tag,
                },
            ]

        def fetch_detail(self, article_no: str, offset: int = 0, limit: int = 10):
            return article_no

        def parse_detail(
            self,
            article_no: str,
            *,
            default_title: str = "",
            default_category: str = "",
            default_summary: str = "",
            default_published_at: str = "",
            default_source_url: str | None = None,
        ):
            return {
                "topic": self.topic,
                "title": default_title,
                "published_at": default_published_at,
                "summary": default_summary,
                "source_url": default_source_url,
                "source_tag": self.source_tag,
            }

    with connection() as conn:
        refresh_affiliated_notices_from_sources(
            conn,
            sources=[DuplicateAffiliatedNoticeSource()],
            fetched_at="2026-03-20T10:00:00+09:00",
        )

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get(
            "/affiliated-notices",
            params={"topic": "international_studies", "limit": 5},
        )

    clear_settings_cache()

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["국제학부 공지", "국제학부 공결 신청 안내"]
    assert len(titles) == len(set(titles)) == 2


def test_api_docs_helper_preserves_filtered_openapi_shape(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    app = create_app()
    request = SimpleNamespace(base_url="https://fallback-api.onrender.com/")
    settings = SimpleNamespace(public_http_url="https://songsim-api.onrender.com")

    payload = build_filtered_openapi(
        app,
        request,
        settings=settings,
        title="Songsim Test Schema",
        description="Test filtered schema",
        path_metadata={
            "/places": {
                "operationId": "searchPlaces",
                "summary": "Search campus places",
                "description": "Places only",
            },
            "/courses": {
                "operationId": "searchCourses",
                "summary": "Search courses",
                "description": "Courses only",
            },
        },
    )

    clear_settings_cache()

    assert payload["info"]["title"] == "Songsim Test Schema"
    assert payload["info"]["description"] == "Test filtered schema"
    assert payload["servers"] == [{"url": "https://songsim-api.onrender.com"}]
    assert set(payload["paths"]) == {"/places", "/courses"}
    assert payload["paths"]["/places"]["get"]["operationId"] == "searchPlaces"
    assert "components" in payload


def test_api_page_helpers_render_expected_strings():
    landing_html = render_landing_page(
        public_http_url="https://songsim-api.onrender.com",
        mcp_url="https://songsim-mcp.onrender.com/mcp",
        public_readonly=True,
        oauth_enabled=False,
        admin_link_html="",
        gpt_actions_links_html="",
    )
    assert "Songsim Campus MCP" in landing_html
    assert "https://songsim-api.onrender.com" in landing_html
    assert "https://songsim-mcp.onrender.com/mcp" in landing_html
    assert "/academic-support-guides" in landing_html
    assert "/class-guides" in landing_html
    assert "/seasonal-semester-guides" in landing_html
    assert "/academic-milestone-guides" in landing_html
    assert "/student-exchange-guides" in landing_html
    assert "/student-exchange-partners" in landing_html
    assert "/phone-book" in landing_html
    assert "/campus-life-support-guides" in landing_html
    assert "/campus-life-notices" in landing_html
    assert "/pc-software" in landing_html
    assert "/affiliated-notices" in landing_html
    assert "/dormitory-guides" in landing_html
    assert "configured without OAuth" in landing_html
    assert "GPT Actions OpenAPI" not in landing_html
    assert "Admin Sync" not in landing_html

    sync_html = render_admin_sync_page(
        state={
            "datasets": [
                {
                    "name": "academic_support_guides",
                    "row_count": 3,
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            ],
            "recent_runs": [],
            "automation": SimpleNamespace(enabled=False, leader=False, jobs=[]),
        },
        official_campus_id="1",
        official_course_year=2026,
        official_course_semester=1,
        official_notice_pages=2,
    )
    assert "Songsim Admin Sync" in sync_html
    assert "Automation Status" in sync_html
    assert "academic_support_guides" in sync_html
    assert "affiliated_notices" in sync_html
    assert "student_exchange_guides" in sync_html
    assert "student_activity_guides" in sync_html

    observability_html = render_admin_observability_page(
        state={
            "readiness": {
                "ok": True,
                "database": {"ok": True, "error": None},
                "tables": {"places": {"ok": True, "row_count": 1, "last_synced_at": "2026-03-18"}},
            },
            "observability": {
                "process_started_at": "2026-03-18T10:00:00+09:00",
                "datasets": [
                    {
                        "name": "places",
                        "row_count": 1,
                        "last_synced_at": "2026-03-18T10:00:00+09:00",
                    }
                ],
                "cache": {
                    "fresh_hit": 0,
                    "stale_hit": 0,
                    "live_fetch_success": 0,
                    "live_fetch_error": 0,
                    "local_fallback": 1,
                    "restaurant_hours_fresh_hit": 0,
                    "restaurant_hours_stale_hit": 0,
                    "restaurant_hours_live_fetch_success": 0,
                    "restaurant_hours_live_fetch_error": 0,
                    "recent_events": [],
                },
                "sync": {
                    "recent_events": [],
                    "last_failure_at": None,
                    "last_failure_message": None,
                },
                "automation": {
                    "enabled": False,
                    "leader": False,
                    "jobs": [
                        {
                            "name": "snapshot",
                            "interval_minutes": 60,
                            "last_run_at": None,
                            "last_status": None,
                            "next_due_at": "2026-03-18T11:00:00+09:00",
                        }
                    ],
                },
                "recent_sync_runs": [],
            },
        }
    )
    assert "Songsim Observability" in observability_html
    assert "Recent Cache Events" in observability_html
    assert "snapshot" in observability_html


def test_public_readonly_mode_exposes_gpt_actions_openapi(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-api.onrender.com")
    clear_settings_cache()

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get("/gpt-actions-openapi.json")

    clear_settings_cache()

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "Songsim Campus GPT Actions"
    assert payload["servers"] == [{"url": "https://songsim-api.onrender.com"}]
    assert set(payload["paths"]) == {
        "/places",
        "/courses",
        "/academic-calendar",
        "/certificate-guides",
        "/leave-of-absence-guides",
        "/scholarship-guides",
        "/wifi-guides",
        "/notices",
        "/affiliated-notices",
        "/notice-categories",
        "/periods",
        "/library-seats",
        "/dining-menus",
        "/restaurants/search",
        "/restaurants/nearby",
        "/transport",
    }
    assert payload["paths"]["/places"]["get"]["operationId"] == "searchPlaces"
    assert payload["paths"]["/courses"]["get"]["operationId"] == "searchCourses"
    assert payload["paths"]["/academic-calendar"]["get"]["operationId"] == "listAcademicCalendar"
    assert payload["paths"]["/certificate-guides"]["get"]["operationId"] == "listCertificateGuides"
    assert (
        payload["paths"]["/leave-of-absence-guides"]["get"]["operationId"]
        == "listLeaveOfAbsenceGuides"
    )
    assert payload["paths"]["/scholarship-guides"]["get"]["operationId"] == "listScholarshipGuides"
    assert payload["paths"]["/wifi-guides"]["get"]["operationId"] == "listWifiGuides"
    course_parameters = payload["paths"]["/courses"]["get"]["parameters"]
    assert any(item["name"] == "period_start" for item in course_parameters)
    assert payload["paths"]["/notices"]["get"]["operationId"] == "listLatestNotices"
    assert (
        payload["paths"]["/notice-categories"]["get"]["operationId"]
        == "listNoticeCategories"
    )
    assert payload["paths"]["/periods"]["get"]["operationId"] == "listClassPeriods"
    assert payload["paths"]["/library-seats"]["get"]["operationId"] == "getLibrarySeatStatus"
    assert payload["paths"]["/dining-menus"]["get"]["operationId"] == "listDiningMenus"
    assert (
        payload["paths"]["/restaurants/nearby"]["get"]["operationId"]
        == "findNearbyRestaurants"
    )
    assert payload["paths"]["/restaurants/search"]["get"]["operationId"] == "searchRestaurants"
    assert payload["paths"]["/transport"]["get"]["operationId"] == "listTransportGuides"


def test_public_readonly_mode_exposes_gpt_actions_openapi_v2(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-api.onrender.com")
    clear_settings_cache()

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get("/gpt-actions-openapi-v2.json")

    clear_settings_cache()

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "Songsim Campus GPT Actions v2"
    assert payload["servers"] == [{"url": "https://songsim-api.onrender.com"}]
    assert set(payload["paths"]) == {
        "/gpt/places",
        "/gpt/notices",
        "/gpt/notice-categories",
        "/gpt/periods",
        "/gpt/library-seats",
        "/gpt/dining-menus",
        "/gpt/restaurants/search",
        "/gpt/restaurants/nearby",
        "/gpt/classrooms/empty",
    }
    assert payload["paths"]["/gpt/places"]["get"]["operationId"] == "searchPlacesForGpt"
    assert payload["paths"]["/gpt/notices"]["get"]["operationId"] == "listLatestNoticesForGpt"
    assert (
        payload["paths"]["/gpt/notice-categories"]["get"]["operationId"]
        == "listNoticeCategoriesForGpt"
    )
    assert payload["paths"]["/gpt/periods"]["get"]["operationId"] == "listPeriodsForGpt"
    assert (
        payload["paths"]["/gpt/library-seats"]["get"]["operationId"]
        == "getLibrarySeatStatusForGpt"
    )
    assert (
        payload["paths"]["/gpt/dining-menus"]["get"]["operationId"]
        == "listDiningMenusForGpt"
    )
    assert (
        payload["paths"]["/gpt/restaurants/search"]["get"]["operationId"]
        == "searchRestaurantsForGpt"
    )
    assert (
        payload["paths"]["/gpt/restaurants/nearby"]["get"]["operationId"]
        == "findNearbyRestaurantsForGpt"
    )
    assert (
        payload["paths"]["/gpt/classrooms/empty"]["get"]["operationId"]
        == "listEstimatedEmptyClassroomsForGpt"
    )


def test_gpt_places_endpoint_returns_compact_summary_payload(client):
    response = client.get("/gpt/places", params={"query": "도서관", "limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0] == {
        "name": "중앙도서관",
        "canonical_name": "중앙도서관",
        "aliases": ["도서관", "중도"],
        "category": "library",
        "short_location": "자료 열람과 시험기간 공부에 쓰는 중심 공간",
        "coordinates": {"latitude": 37.48643, "longitude": 126.80164},
        "highlights": [
            "별칭: 도서관, 중도",
            "자료 열람과 시험기간 공부에 쓰는 중심 공간",
            "운영: mon-fri: 08:30-22:00 / sat: 09:00-17:00",
        ],
    }


def test_places_endpoint_matches_facility_tenant_alias_from_override_taxonomy(client):
    response = client.get("/places", params={"query": "트러스트짐", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert payload[0]["slug"] == "student-center"
    assert payload[0]["name"] == "학생회관"


def test_places_endpoint_uses_alias_friendly_name_for_strong_alias_queries(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "sophie-barat-hall",
                    "name": "학생미래인재관",
                    "category": "building",
                    "aliases": ["학생회관", "학생센터"],
                    "description": "학생식당과 생활 편의시설이 있는 건물",
                    "latitude": 37.486466,
                    "longitude": 126.801297,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 생활 편의시설이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
            ],
        )

    student_response = client.get("/places", params={"query": "학생회관 어디야?", "limit": 1})
    k_hall_response = client.get("/places", params={"query": "K관 어디야?", "limit": 1})
    canonical_response = client.get("/places", params={"query": "김수환관 어디야?", "limit": 1})

    assert student_response.status_code == 200
    assert student_response.json()[0]["slug"] == "sophie-barat-hall"
    assert student_response.json()[0]["name"] == "학생회관"
    assert student_response.json()[0]["canonical_name"] == "학생미래인재관"

    assert k_hall_response.status_code == 200
    assert k_hall_response.json()[0]["slug"] == "kim-sou-hwan-hall"
    assert k_hall_response.json()[0]["name"] == "K관"
    assert k_hall_response.json()[0]["canonical_name"] == "김수환관"

    assert canonical_response.status_code == 200
    assert canonical_response.json()[0]["slug"] == "kim-sou-hwan-hall"
    assert canonical_response.json()[0]["name"] == "김수환관"
    assert canonical_response.json()[0]["canonical_name"] == "김수환관"


def test_places_endpoint_uses_alias_friendly_parent_name_for_facility_hits(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "sophie-barat-hall",
                    "name": "학생미래인재관",
                    "category": "building",
                    "aliases": ["학생회관", "학생센터"],
                    "description": "학생식당과 생활 편의시설이 있는 건물",
                    "latitude": 37.486466,
                    "longitude": 126.801297,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "CU",
                    "category": "편의점",
                    "phone": "032-343-3424",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~21:30 토,일 08:00~16:00 (야간 무인으로 24시간 운영)",
                    "place_slug": "sophie-barat-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            ],
        )

    response = client.get("/places", params={"query": "CU 어디야?", "limit": 1})

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["slug"] == "sophie-barat-hall"
    assert payload["name"] == "학생회관"
    assert payload["canonical_name"] == "학생미래인재관"
    assert payload["matched_facility"]["name"] == "CU"
    assert payload["matched_facility"]["location_hint"] == "학생회관 1층"


def test_places_endpoint_matches_generic_facility_nouns(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학회관"],
                    "description": "학생 편의시설이 많은 건물",
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "opening_hours": {
                        "트러스트짐": "평일 07:00~22:30",
                        "편의점": "상시 07:00~24:00",
                        "교내복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                    },
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {
                        "이마트24 K관점": "상시 07:00~24:00",
                    },
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    gym_response = client.get("/places", params={"query": "헬스장", "limit": 5})
    store_response = client.get("/places", params={"query": "편의점", "limit": 5})
    copy_response = client.get("/places", params={"query": "복사실", "limit": 5})
    atm_response = client.get("/places", params={"query": "ATM", "limit": 5})

    assert gym_response.status_code == 200
    assert [item["slug"] for item in gym_response.json()] == ["student-center"]
    assert gym_response.json()[0]["matched_facility"]["location_hint"] == "학생회관"
    assert store_response.status_code == 200
    assert [item["slug"] for item in store_response.json()[:2]] == [
        "student-center",
        "dormitory-stephen",
    ]
    assert store_response.json()[0]["matched_facility"]["location_hint"] == "학생회관"
    assert copy_response.status_code == 200
    assert [item["slug"] for item in copy_response.json()] == ["student-center"]
    assert copy_response.json()[0]["matched_facility"]["location_hint"] == "학생회관"
    assert atm_response.status_code == 200
    assert [item["slug"] for item in atm_response.json()] == ["student-center"]
    assert atm_response.json()[0]["matched_facility"]["location_hint"] == "학생회관"


def test_places_endpoint_supports_laundry_generic_facility_query(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {
                        "세탁소": "평일 09:00~18:00",
                    },
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {
                        "세탁소": "평일 09:00~18:00",
                    },
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학생센터"],
                    "description": "학생 편의시설이 많은 건물",
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "opening_hours": {
                        "세탁소": "평일 09:00~18:00",
                    },
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    response = client.get("/places", params={"query": "세탁소", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert [item["slug"] for item in payload[:3]] == [
        "kim-sou-hwan-hall",
        "student-center",
        "dormitory-stephen",
    ]
    assert payload[0]["matched_facility"]["name"] == "세탁소"
    assert payload[0]["matched_facility"]["location_hint"] == "김수환관"
    assert payload[0]["matched_facility"]["opening_hours"] == "평일 09:00~18:00"


def test_places_endpoint_generic_facility_nouns_prefer_building_then_facility_then_dormitory(
    client,
):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": [],
                    "description": "기숙사 생활시설 건물",
                    "opening_hours": {
                        "이마트24": "상시 07:00~24:00",
                        "교내복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                        "트러스트짐": "평일 07:00~22:30",
                    },
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["K관"],
                    "description": "강의동과 생활편의시설이 함께 있는 건물",
                    "opening_hours": {
                        "이마트24": "상시 07:00~24:00",
                        "교내복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                        "트러스트짐": "평일 07:00~22:30",
                    },
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학생센터"],
                    "description": "학생 편의시설이 많은 건물",
                    "opening_hours": {
                        "이마트24": "상시 07:00~24:00",
                        "교내복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                        "트러스트짐": "평일 07:00~22:30",
                    },
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    response = client.get("/places", params={"query": "편의점", "limit": 5})

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()[:3]] == [
        "kim-sou-hwan-hall",
        "student-center",
        "dormitory-stephen",
    ]


def test_places_endpoint_exposes_matched_facility_metadata(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학회관", "트러스트짐"],
                    "description": "학생 편의시설과 복사/은행/카페가 있는 공간",
                    "opening_hours": {
                        "복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                        "카페드림": "평일 08:00~22:00",
                        "트러스트짐": "평일 07:00~22:30",
                    },
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "central-library",
                    "name": "중앙도서관",
                    "category": "library",
                    "aliases": ["중도"],
                    "description": "자료 열람과 시험 준비를 위한 핵심 공간",
                    "latitude": 37.48643,
                    "longitude": 126.80164,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "복사실",
                    "category": "복사실",
                    "phone": "02-2164-4725",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:50~19:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 09:00~16:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "카페드림",
                    "category": "카페",
                    "phone": "010-9517-9417",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~22:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 07:00~22:30",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "CU",
                    "category": "편의점",
                    "phone": "032-343-3424",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~21:30 토,일 08:00~16:00 (야간 무인으로 24시간 운영)",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    facility_expectations = {
        "복사실이 어디야?": ("복사실", "02-2164-4725"),
        "우리은행 전화번호 알려줘": ("우리은행", "032-342-2641"),
        "카페드림 어디야?": ("카페드림", "010-9517-9417"),
        "트러스트짐 어디야?": ("트러스트짐", "032-342-5406"),
        "학생회관 1층 편의점 어디야?": ("CU", "032-343-3424"),
        "학생회관 1층 24시간 편의점 어디야?": ("CU", "032-343-3424"),
    }
    for query, (facility_name, phone) in facility_expectations.items():
        response = client.get("/places", params={"query": query, "limit": 1})
        assert response.status_code == 200
        payload = response.json()
        assert payload
        assert payload[0]["slug"] == "student-center"
        assert payload[0]["name"] == "학생회관"
        assert payload[0]["canonical_name"] == "학생회관"
        assert "matched_facility" in payload[0]
        assert payload[0]["matched_facility"]["name"] == facility_name
        assert payload[0]["matched_facility"]["phone"] == phone
        assert payload[0]["matched_facility"]["location_hint"] == "학생회관 1층"

    library_response = client.get("/places", params={"query": "중앙도서관이 어디야?", "limit": 1})
    assert library_response.json()[0].get("matched_facility") is None


def test_places_endpoint_populates_generic_facility_metadata_when_place_alias_matches(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["편의점"],
                    "description": "학생 편의시설과 복사/은행/카페가 있는 공간",
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        replace_campus_facilities(
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

    response = client.get("/places", params={"query": "편의점", "limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["slug"] == "student-center"
    assert payload[0]["matched_facility"]["name"] == "학생회관 편의점"
    assert payload[0]["matched_facility"]["location_hint"] == "학생회관 1층"
    assert payload[0]["matched_facility"]["opening_hours"] == "상시 07:00~24:00"


def test_restaurants_search_endpoint_matches_brand_alias_spacing_variants(client):
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "mammoth",
                    "name": "매머드익스프레스 부천가톨릭대학교점",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48556,
                    "longitude": 126.80379,
                    "tags": ["커피전문점", "매머드익스프레스"],
                    "description": "경기 부천시 원미구 지봉로 43",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-15T01:19:14+00:00",
                }
            ],
        )

    spaced_response = client.get("/restaurants/search", params={"query": "매머드 커피", "limit": 5})
    compact_response = client.get("/restaurants/search", params={"query": "매머드커피", "limit": 5})

    assert spaced_response.status_code == 200
    assert compact_response.status_code == 200
    spaced_payload = spaced_response.json()
    compact_payload = compact_response.json()
    assert [item["slug"] for item in spaced_payload] == ["mammoth"]
    assert [item["slug"] for item in compact_payload] == ["mammoth"]
    assert spaced_payload[0]["name"] == "매머드익스프레스 부천가톨릭대학교점"
    assert compact_payload[0]["name"] == "매머드익스프레스 부천가톨릭대학교점"


def test_gpt_restaurants_search_endpoint_returns_compact_brand_match(client):
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "ediya",
                    "name": "이디야커피 가톨릭대점",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48611,
                    "longitude": 126.80503,
                    "tags": ["커피전문점", "이디야커피"],
                    "description": "경기 부천시 원미구 지봉로 48",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-15T01:19:14+00:00",
                }
            ],
        )

    response = client.get("/gpt/restaurants/search", params={"query": "이디야", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "name": "이디야커피 가톨릭대점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 지봉로 48",
        }
    ]


def test_restaurants_search_endpoint_uses_kakao_live_fallback(client, monkeypatch):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class ApiBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "매머드익스프레스"
            return [
                services.KakaoPlace(
                    name="매머드익스프레스 가상의외부점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 소사구 경인옛로 37",
                    latitude=37.48186,
                    longitude=126.79612,
                    place_id="201",
                    place_url="https://place.map.kakao.com/201",
                ),
                services.KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiBrandKakaoClient)

    response = client.get("/restaurants/search", params={"query": "매머드커피", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload[:2]] == [
        "매머드익스프레스 부천가톨릭대학교점",
        "매머드익스프레스 가상의외부점",
    ]
    assert payload[0]["source_tag"] == "kakao_local"
    assert payload[0]["distance_meters"] is None
    assert payload[0]["estimated_walk_minutes"] is None


def test_gpt_restaurants_search_endpoint_uses_kakao_live_fallback(client, monkeypatch):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class ApiBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "이디야커피"
            return [
                services.KakaoPlace(
                    name="이디야커피 부천성모병원점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 부흥로 472",
                    latitude=37.48564,
                    longitude=126.79093,
                    place_id="202",
                    place_url="https://place.map.kakao.com/202",
                ),
                services.KakaoPlace(
                    name="이디야커피 가톨릭대점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 48",
                    latitude=37.48611,
                    longitude=126.80503,
                    place_id="102",
                    place_url="https://place.map.kakao.com/102",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiBrandKakaoClient)

    response = client.get("/gpt/restaurants/search", params={"query": "이디야", "limit": 5})

    assert response.status_code == 200
    assert response.json()[:2] == [
        {
            "name": "이디야커피 가톨릭대점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 지봉로 48",
        },
        {
            "name": "이디야커피 부천성모병원점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 부흥로 472",
        }
    ]


def test_restaurants_search_endpoint_filters_brand_noise_candidates(client, monkeypatch):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class ApiBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "스타벅스"
            return [
                services.KakaoPlace(
                    name="스타벅스 역곡역DT점 주차장",
                    category="교통시설 > 주차장",
                    address="경기 부천시 소사구 괴안동 112-25",
                    latitude=37.48345,
                    longitude=126.80935,
                    place_id="902",
                    place_url="https://place.map.kakao.com/902",
                ),
                services.KakaoPlace(
                    name="스타벅스 역곡역DT점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 소사구 경인로 485",
                    latitude=37.48354,
                    longitude=126.80929,
                    place_id="903",
                    place_url="https://place.map.kakao.com/903",
                ),
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiBrandKakaoClient)

    response = client.get("/restaurants/search", params={"query": "스타벅스", "limit": 5})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["스타벅스 역곡역DT점"]


def test_gpt_restaurants_search_endpoint_filters_brand_noise_candidates(client, monkeypatch):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class ApiBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "스타벅스"
            return [
                services.KakaoPlace(
                    name="스타벅스 역곡역DT점 주차장",
                    category="교통시설 > 주차장",
                    address="경기 부천시 소사구 괴안동 112-25",
                    latitude=37.48345,
                    longitude=126.80935,
                    place_id="902",
                    place_url="https://place.map.kakao.com/902",
                ),
                services.KakaoPlace(
                    name="스타벅스 역곡역DT점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 소사구 경인로 485",
                    latitude=37.48354,
                    longitude=126.80929,
                    place_id="903",
                    place_url="https://place.map.kakao.com/903",
                ),
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiBrandKakaoClient)

    response = client.get("/gpt/restaurants/search", params={"query": "스타벅스", "limit": 5})

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "스타벅스 역곡역DT점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 소사구 경인로 485",
        }
    ]


def test_gpt_restaurants_search_endpoint_supports_long_tail_brand_alias(client, monkeypatch):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class ApiBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "커피빈"
            return [
                services.KakaoPlace(
                    name="커피빈 역곡점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 70",
                    latitude=37.48621,
                    longitude=126.80491,
                    place_id="904",
                    place_url="https://place.map.kakao.com/904",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiBrandKakaoClient)

    response = client.get("/gpt/restaurants/search", params={"query": "커피빈", "limit": 5})

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "커피빈 역곡점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 지봉로 70",
        }
    ]


def test_gpt_restaurants_search_endpoint_exposes_origin_distance_for_long_tail_brand(
    client,
    monkeypatch,
):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()
    calls: list[int] = []

    class ApiBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "커피빈"
            assert x is not None and y is not None
            calls.append(radius)
            if radius == 15 * 75:
                return []
            assert radius == 5000
            return [
                services.KakaoPlace(
                    name="커피빈 역곡점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 70",
                    latitude=37.48621,
                    longitude=126.80491,
                    place_id="904",
                    place_url="https://place.map.kakao.com/904",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiBrandKakaoClient)

    response = client.get(
        "/gpt/restaurants/search",
        params={"query": "커피빈", "origin": "중도", "limit": 5},
    )

    assert response.status_code == 200
    assert calls == [15 * 75, 5000]
    payload = response.json()
    assert [item["name"] for item in payload] == ["커피빈 역곡점"]
    assert payload[0]["distance_meters"] is not None
    assert payload[0]["estimated_walk_minutes"] is not None


def test_restaurants_search_endpoint_expands_radius_for_long_tail_brand_with_origin(
    client,
    monkeypatch,
):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()
    calls: list[int] = []

    class ApiBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "커피빈"
            assert x is not None and y is not None
            calls.append(radius)
            if radius == 15 * 75:
                return []
            assert radius == 5000
            return [
                services.KakaoPlace(
                    name="커피빈 역곡점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 70",
                    latitude=37.48621,
                    longitude=126.80491,
                    place_id="904",
                    place_url="https://place.map.kakao.com/904",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiBrandKakaoClient)

    response = client.get(
        "/restaurants/search",
        params={"query": "커피빈", "origin": "중도", "limit": 5},
    )

    assert response.status_code == 200
    assert calls == [15 * 75, 5000]
    payload = response.json()
    assert [item["name"] for item in payload] == ["커피빈 역곡점"]
    assert payload[0]["distance_meters"] is not None
    assert payload[0]["estimated_walk_minutes"] is not None


def test_restaurants_search_endpoint_returns_404_for_unknown_origin(client):
    response = client.get(
        "/restaurants/search",
        params={"query": "매머드커피", "origin": "없는건물", "limit": 5},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Origin place not found: 없는건물"


def test_gpt_notices_endpoint_returns_normalized_category_and_summary_preview(client):
    long_summary = (
        "중앙도서관 이용 학생을 위한 장학 연계 프로그램 안내입니다. "
        "자세한 일정과 신청 자격, 제출 서류를 확인해 주세요. "
        "설명이 길어져도 GPT 응답에서는 짧은 미리보기만 내려가야 합니다. "
        "추가 문의는 도서관 장학 담당 부서로 연락해 주세요."
    )
    with connection() as conn:
        replace_notices(
            conn,
            [
                {
                    "title": "중앙도서관 장학 안내",
                    "category": "place",
                    "published_at": "2026-03-08",
                    "summary": long_summary,
                    "labels": ["도서관", "장학"],
                    "source_url": "https://example.edu/notices/central-library-aid",
                    "source_tag": "demo",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    response = client.get("/gpt/notices", params={"limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["title"] == "중앙도서관 장학 안내"
    assert payload[0]["category_display"] == "general"
    assert payload[0]["published_at"] == "2026-03-08"
    assert payload[0]["source_url"] == "https://example.edu/notices/central-library-aid"
    assert payload[0]["summary"].endswith("...")
    assert len(payload[0]["summary"]) <= 160
    assert payload[0]["summary"] != long_summary


def test_notice_endpoints_treat_employment_and_career_as_same_filter(client):
    with connection() as conn:
        replace_notices(
            conn,
            [
                {
                    "title": "진로취업상담 안내",
                    "category": "career",
                    "published_at": "2026-03-12",
                    "summary": "취업 상담 일정",
                    "labels": ["취업"],
                    "source_url": "https://example.edu/notices/career",
                    "source_tag": "demo",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "title": "채용 설명회 안내",
                    "category": "employment",
                    "published_at": "2026-03-13",
                    "summary": "채용 설명회 일정",
                    "labels": ["취업"],
                    "source_url": "https://example.edu/notices/employment",
                    "source_tag": "demo",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    api_response = client.get("/notices", params={"category": "employment", "limit": 10})
    gpt_response = client.get("/gpt/notices", params={"category": "career", "limit": 10})

    assert api_response.status_code == 200
    assert [item["title"] for item in api_response.json()] == [
        "채용 설명회 안내",
        "진로취업상담 안내",
    ]
    assert gpt_response.status_code == 200
    assert [item["title"] for item in gpt_response.json()] == [
        "채용 설명회 안내",
        "진로취업상담 안내",
    ]
    assert all(item["category_display"] == "employment" for item in gpt_response.json())


def test_notice_endpoints_normalize_place_category_to_general(client):
    with connection() as conn:
        replace_notices(
            conn,
            [
                {
                    "title": "중앙도서관 자리 안내",
                    "category": "place",
                    "published_at": "2026-03-12",
                    "summary": "도서관 좌석 안내",
                    "labels": ["도서관"],
                    "source_url": "https://example.edu/notices/place",
                    "source_tag": "demo",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    api_response = client.get("/notices", params={"limit": 1})
    gpt_response = client.get("/gpt/notices", params={"limit": 1})

    assert api_response.status_code == 200
    assert api_response.json()[0]["category"] == "general"
    assert gpt_response.status_code == 200
    assert gpt_response.json()[0]["category_display"] == "general"


def test_notice_category_metadata_endpoints_return_public_and_gpt_labels(client):
    api_response = client.get("/notice-categories")
    gpt_response = client.get("/gpt/notice-categories")

    assert api_response.status_code == 200
    assert api_response.json() == [
        {"category": "academic", "category_display": "학사", "aliases": []},
        {"category": "scholarship", "category_display": "장학", "aliases": []},
        {"category": "employment", "category_display": "취업", "aliases": ["career"]},
        {"category": "general", "category_display": "일반", "aliases": ["place"]},
    ]
    assert gpt_response.status_code == 200
    assert gpt_response.json() == [
        {"category": "academic", "category_display": "academic", "aliases": []},
        {"category": "scholarship", "category_display": "scholarship", "aliases": []},
        {
            "category": "employment",
            "category_display": "employment",
            "aliases": ["career"],
        },
        {"category": "general", "category_display": "general", "aliases": ["place"]},
    ]


def test_gpt_periods_endpoint_matches_standard_periods_truth(client):
    periods_response = client.get("/periods")
    gpt_periods_response = client.get("/gpt/periods")

    assert periods_response.status_code == 200
    assert gpt_periods_response.status_code == 200
    assert gpt_periods_response.json() == periods_response.json()


def test_gpt_nearby_restaurants_endpoint_returns_compact_summary_payload(client):
    response = client.get(
        "/gpt/restaurants/nearby",
        params={"origin": "central-library", "category": "western", "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0] == {
        "name": "도서관파스타",
        "category_display": "양식",
        "distance_meters": 31,
        "estimated_walk_minutes": 1,
        "price_hint": "11,000~15,000원",
        "open_now": None,
        "location_hint": "도서관 근처 데모 양식집",
    }


def test_classrooms_empty_endpoint_returns_estimated_empty_rooms_for_building_alias(client):
    with connection() as conn:
        replace_courses(
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

    response = client.get(
        "/classrooms/empty",
        params={"building": "N관", "at": "2026-03-16T10:15:00+09:00", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["building"]["slug"] == "nichols-hall"
    assert payload["building"]["name"] == "니콜스관"
    assert payload["year"] == 2026
    assert payload["semester"] == 1
    assert payload["availability_mode"] == "estimated"
    assert payload["observed_at"] is None
    assert payload["estimate_note"].startswith("공식 시간표 기준 예상 공실입니다.")
    assert [item["room"] for item in payload["items"]] == ["N301", "N201"]
    assert payload["items"][0]["available_now"] is True
    assert payload["items"][0]["availability_mode"] == "estimated"
    assert payload["items"][0]["source_observed_at"] is None
    assert payload["items"][0]["next_occupied_at"] is None
    assert payload["items"][1]["next_occupied_at"] == "2026-03-16T13:00:00+09:00"
    assert "데이터베이스" in (payload["items"][1]["next_course_summary"] or "")


def test_classrooms_empty_endpoint_prefers_official_realtime_when_source_is_available(
    client,
    monkeypatch,
):
    with connection() as conn:
        replace_courses(
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
        services,
        "_get_official_classroom_availability_source",
        lambda: RealtimeSource(),
    )

    response = client.get(
        "/classrooms/empty",
        params={"building": "니콜스관", "at": "2026-03-16T10:15:00+09:00"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["availability_mode"] == "realtime"
    assert payload["observed_at"] == "2026-03-16T10:10:00+09:00"
    assert "공식 실시간 공실" in payload["estimate_note"]
    assert [item["room"] for item in payload["items"]] == ["N101"]
    assert payload["items"][0]["availability_mode"] == "realtime"
    assert payload["items"][0]["source_observed_at"] == "2026-03-16T10:10:00+09:00"


def test_classrooms_empty_endpoint_rejects_non_classroom_place(client):
    response = client.get(
        "/classrooms/empty",
        params={"building": "정문", "at": "2026-03-16T10:15:00+09:00"},
    )

    assert response.status_code == 400
    assert "강의실 기반 건물" in response.json()["detail"]


def test_classrooms_empty_endpoint_returns_404_for_missing_building(client):
    response = client.get(
        "/classrooms/empty",
        params={"building": "없는건물", "at": "2026-03-16T10:15:00+09:00"},
    )

    assert response.status_code == 404


def test_classrooms_empty_endpoint_accepts_kim_sou_hwan_hall_as_building(client):
    response = client.get(
        "/classrooms/empty",
        params={"building": "김수환관", "at": "2026-03-16T10:15:00+09:00"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["building"]["slug"] == "kim-sou-hwan-hall"
    assert payload["availability_mode"] == "estimated"
    assert payload["items"]
    assert all(item["room"].startswith("K") for item in payload["items"])


def test_classrooms_empty_endpoint_prefers_short_query_building_preference_for_k_hall(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_courses(
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

    response = client.get(
        "/classrooms/empty",
        params={"building": "K관", "at": "2026-03-16T10:15:00+09:00"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["building"]["slug"] == "kim-sou-hwan-hall"
    assert [item["room"] for item in payload["items"]] == ["K201"]


def test_classrooms_empty_endpoint_returns_fast_empty_note_for_student_future_hall(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "sophie-barat-hall",
                    "name": "학생미래인재관",
                    "category": "building",
                    "aliases": ["학생회관", "학생센터"],
                    "description": "학생식당과 생활 편의시설이 있는 건물",
                    "latitude": 37.486466,
                    "longitude": 126.801297,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        replace_courses(conn, [])

    response = client.get(
        "/classrooms/empty",
        params={"building": "학생미래인재관", "at": "2026-03-16T10:15:00+09:00"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["building"]["slug"] == "sophie-barat-hall"
    assert payload["items"] == []
    assert "시간표 데이터를 찾지 못했습니다" in payload["estimate_note"]


def test_gpt_empty_classrooms_endpoint_returns_estimate_payload(client):
    with connection() as conn:
        replace_courses(
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

    response = client.get(
        "/gpt/classrooms/empty",
        params={"building": "니콜스", "at": "2026-03-16T10:15:00+09:00"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["building"]["slug"] == "nichols-hall"
    assert payload["availability_mode"] == "estimated"
    assert payload["items"][0]["room"] == "N201"
    assert payload["items"][0]["available_now"] is True
    assert payload["items"][0]["availability_mode"] == "estimated"
    assert payload["items"][0]["next_occupied_at"] == "2026-03-16T13:00:00+09:00"


def test_public_readonly_mode_exposes_privacy_page(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get("/privacy")

    clear_settings_cache()

    assert response.status_code == 200
    assert "Songsim Campus Privacy Policy" in response.text
    assert "ChatGPT Actions" in response.text
    assert "Kakao" in response.text


def test_admin_sync_route_rejects_non_loopback(remote_admin_client):
    response = remote_admin_client.get("/admin/sync")

    assert response.status_code == 403


def test_admin_observability_routes_reject_non_loopback(remote_admin_client):
    html_response = remote_admin_client.get("/admin/observability")
    json_response = remote_admin_client.get("/admin/observability.json")

    assert html_response.status_code == 403
    assert json_response.status_code == 403


def test_admin_sync_dashboard_runs_snapshot_and_shows_recent_history(admin_client, monkeypatch):
    def fake_snapshot(
        conn,
        *,
        campus: str | None = None,
        year: int | None = None,
        semester: int | None = None,
        notice_pages: int | None = None,
    ):
        assert campus == "1"
        assert year == 2026
        assert semester == 1
        assert notice_pages == 2
        return {
            "places": 5,
            "courses": 10,
            "notices": 4,
            "academic_support_guides": 5,
            "academic_status_guides": 3,
            "certificate_guides": 3,
            "leave_of_absence_guides": 2,
            "scholarship_guides": 4,
            "transport_guides": 2,
        }

    monkeypatch.setattr("songsim_campus.services.sync_official_snapshot", fake_snapshot)

    response = admin_client.post(
        "/admin/sync/run",
        data={
            "target": "snapshot",
            "campus": "1",
            "year": "2026",
            "semester": "1",
            "notice_pages": "2",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/sync"

    page = admin_client.get("/admin/sync")
    assert page.status_code == 200
    assert "Songsim Admin Sync" in page.text
    assert "Automation Status" in page.text
    assert "snapshot" in page.text
    assert "success" in page.text
    assert "academic_support_guides" in page.text
    assert "academic_status_guides" in page.text
    assert "certificate_guides" in page.text
    assert "leave_of_absence_guides" in page.text
    assert "scholarship_guides" in page.text
    assert "transport_guides" in page.text


def test_admin_observability_pages_render_runtime_state(admin_client, client, monkeypatch):
    services.reset_observability_state()

    def fake_snapshot(
        conn,
        *,
        campus: str | None = None,
        year: int | None = None,
        semester: int | None = None,
        notice_pages: int | None = None,
    ):
        return {
            "places": 5,
            "courses": 10,
            "notices": 4,
            "academic_support_guides": 5,
            "academic_status_guides": 3,
            "certificate_guides": 3,
            "leave_of_absence_guides": 2,
            "scholarship_guides": 4,
            "transport_guides": 2,
        }

    def broken_transport(conn, *, fetched_at: str | None = None, source=None):
        raise RuntimeError("transport sync exploded")

    monkeypatch.setattr("songsim_campus.services.sync_official_snapshot", fake_snapshot)
    monkeypatch.setattr(
        "songsim_campus.services.refresh_transport_guides_from_location_page",
        broken_transport,
    )

    nearby = client.get("/restaurants/nearby", params={"origin": "central-library", "limit": 3})
    assert nearby.status_code == 200

    success = admin_client.post(
        "/admin/sync/run",
        data={"target": "snapshot", "campus": "1", "year": "2026", "semester": "1"},
        follow_redirects=False,
    )
    failed = admin_client.post(
        "/admin/sync/run",
        data={"target": "transport_guides"},
        follow_redirects=False,
    )

    assert success.status_code == 303
    assert failed.status_code == 303

    html_page = admin_client.get("/admin/observability")
    json_page = admin_client.get("/admin/observability.json")

    assert html_page.status_code == 200
    assert "Songsim Observability" in html_page.text
    assert json_page.status_code == 200
    payload = json_page.json()
    assert payload["health"]["ok"] is True
    assert payload["readiness"]["ok"] is True
    assert payload["cache"]["local_fallback"] >= 1
    assert payload["sync"]["last_failure_message"] == "transport sync exploded"
    assert payload["automation"]["enabled"] is False
    assert payload["automation"]["leader"] is False
    assert {job["name"] for job in payload["automation"]["jobs"]} == {
        "snapshot",
        "library_seat_prewarm",
        "cache_cleanup",
    }
    assert payload["datasets"][0]["name"] == "places"
    assert payload["recent_sync_runs"][0]["status"] in {"success", "failed"}


def test_admin_sync_dashboard_passes_target_specific_form_values(admin_client, monkeypatch):
    captured: dict[str, object] = {}

    def fake_places(conn, *, campus: str = "1", fetched_at: str | None = None):
        captured["places"] = campus
        return []

    def fake_courses(
        conn,
        *,
        year: int | None = None,
        semester: int | None = None,
        fetched_at: str | None = None,
        source=None,
    ):
        captured["courses"] = (year, semester)
        return []

    def fake_notices(conn, *, pages: int = 1, fetched_at: str | None = None, source=None):
        captured["notices"] = pages
        return []

    monkeypatch.setattr("songsim_campus.services.refresh_places_from_campus_map", fake_places)
    monkeypatch.setattr("songsim_campus.services.refresh_courses_from_subject_search", fake_courses)
    monkeypatch.setattr("songsim_campus.services.refresh_notices_from_notice_board", fake_notices)

    assert admin_client.post(
        "/admin/sync/run",
        data={"target": "places", "campus": "7"},
        follow_redirects=False,
    ).status_code == 303
    assert admin_client.post(
        "/admin/sync/run",
        data={"target": "courses", "year": "2026", "semester": "1"},
        follow_redirects=False,
    ).status_code == 303
    assert admin_client.post(
        "/admin/sync/run",
        data={"target": "notices", "notice_pages": "3"},
        follow_redirects=False,
    ).status_code == 303

    assert captured["places"] == "7"
    assert captured["courses"] == (2026, 1)
    assert captured["notices"] == 3


def test_places_query_returns_library(client):
    response = client.get('/places', params={'query': '도서관'})
    assert response.status_code == 200
    names = [item['name'] for item in response.json()]
    assert '중앙도서관' in names


def test_courses_query_returns_expected_course(client):
    response = client.get('/courses', params={'query': '객체지향', 'year': 2026, 'semester': 1})
    assert response.status_code == 200
    items = response.json()
    assert items
    assert items[0]['title'] == '객체지향프로그래밍설계'


def test_courses_endpoint_recovers_typo_and_code_spacing_while_leaving_watchlist_queries_empty(
    client,
):
    with connection() as conn:
        replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE420",
                    "title": "임베디드시스템",
                    "professor": "담당교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 7,
                    "period_end": 8,
                    "room": "N401",
                    "raw_schedule": "월7~8(N401)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "MTH101",
                    "title": "데이터베이스활용",
                    "professor": "담당교수",
                    "department": "테스트학과",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 3,
                    "period_end": 4,
                    "room": "M101",
                    "raw_schedule": "월3~4(M101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "BIO102",
                    "title": "분자생물학개론",
                    "professor": "박요셉",
                    "department": "자연과학계열",
                    "section": "01",
                    "day_of_week": "화",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "S201",
                    "raw_schedule": "화1~2(S201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    typo_response = client.get(
        "/courses",
        params={"query": "데이타베이스", "year": 2026, "semester": 1, "limit": 5},
    )
    spaced_title_response = client.get(
        "/courses",
        params={"query": "데 이 터 베 이 스", "year": 2026, "semester": 1, "limit": 5},
    )
    spaced_code_response = client.get(
        "/courses",
        params={"query": "CSE 420", "year": 2026, "semester": 1, "limit": 5},
    )
    dashed_code_response = client.get(
        "/courses",
        params={"query": "CSE-420", "year": 2026, "semester": 1, "limit": 5},
    )
    mixed_case_code_response = client.get(
        "/courses",
        params={"query": "cSe 420", "year": 2026, "semester": 1, "limit": 5},
    )
    spaced_professor_response = client.get(
        "/courses",
        params={"query": "박 요 셉", "year": 2026, "semester": 1, "limit": 5},
    )
    source_gap_code_response = client.get(
        "/courses",
        params={"query": "CSE301", "year": 2026, "semester": 1, "limit": 5},
    )
    source_gap_professor_response = client.get(
        "/courses",
        params={"query": "김가톨", "year": 2026, "semester": 1, "limit": 5},
    )

    assert typo_response.status_code == 200
    assert [item["code"] for item in typo_response.json()] == ["MTH101"]
    assert spaced_title_response.status_code == 200
    assert [item["code"] for item in spaced_title_response.json()] == ["MTH101"]
    assert spaced_code_response.status_code == 200
    assert [item["code"] for item in spaced_code_response.json()] == ["CSE420"]
    assert dashed_code_response.status_code == 200
    assert [item["code"] for item in dashed_code_response.json()] == ["CSE420"]
    assert mixed_case_code_response.status_code == 200
    assert [item["code"] for item in mixed_case_code_response.json()] == ["CSE420"]
    assert spaced_professor_response.status_code == 200
    assert [item["code"] for item in spaced_professor_response.json()] == ["BIO102"]
    assert source_gap_code_response.status_code == 200
    assert source_gap_code_response.json() == []
    assert source_gap_professor_response.status_code == 200
    assert source_gap_professor_response.json() == []


def test_courses_endpoint_prioritizes_ranked_matches_over_general_substrings(client):
    with connection() as conn:
        replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "GEN900",
                    "title": "고급자료분석",
                    "professor": "담당교수",
                    "department": "테스트학과",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "M101",
                    "raw_schedule": "월1~2(M101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE900",
                    "title": "자료",
                    "professor": "담당교수",
                    "department": "테스트학과",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "M101",
                    "raw_schedule": "월1~2(M101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE901",
                    "title": "자료구조",
                    "professor": "담당교수",
                    "department": "테스트학과",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "M101",
                    "raw_schedule": "월1~2(M101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "HIS900",
                    "title": "컴퓨터개론",
                    "professor": "자료",
                    "department": "테스트학과",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "M101",
                    "raw_schedule": "월1~2(M101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    response = client.get("/courses", params={"query": "자료", "limit": 4})

    assert response.status_code == 200
    assert [item["code"] for item in response.json()] == ["CSE900", "CSE901", "HIS900", "GEN900"]


def test_nearby_restaurants_uses_origin(client):
    response = client.get(
        '/restaurants/nearby',
        params={'origin': 'central-library', 'budget_max': 10000, 'walk_minutes': 15},
    )
    assert response.status_code == 200
    items = response.json()
    assert items
    assert all(item['estimated_walk_minutes'] <= 15 for item in items)


def test_nearby_restaurants_endpoint_prefers_short_query_origin_preference_for_k_hall(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_restaurants(
            conn,
            [
                {
                    "slug": "k-hall-cafe",
                    "name": "K관카페",
                    "category": "cafe",
                    "min_price": 5000,
                    "max_price": 6000,
                    "latitude": 37.48631,
                    "longitude": 126.80121,
                    "tags": ["카페"],
                    "description": "김수환관 앞",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    response = client.get(
        "/restaurants/nearby",
        params={"origin": "K관", "walk_minutes": 5, "limit": 3},
    )

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == ["k-hall-cafe"]


def test_places_endpoint_prioritizes_exact_short_match_over_partial_noise(client):
    with connection() as conn:
        from songsim_campus.repo import replace_places

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

    response = client.get("/places", params={"query": "정문", "limit": 10})

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == ["main-gate"]


def test_places_endpoint_prefers_short_query_place_preference_for_k_hall(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    response = client.get("/places", params={"query": "K관", "limit": 10})

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == ["kim-sou-hwan-hall"]


def test_places_endpoint_normalizes_spacing_variants(client):
    response = client.get("/places", params={"query": "중앙 도서관", "limit": 5})

    assert response.status_code == 200
    assert response.json()
    assert response.json()[0]["slug"] == "central-library"


def test_places_endpoint_promotes_canonical_parent_place_for_k_hall_facilities(client):
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_campus_facilities(
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

    for query, facility_name in {
        "복사실이 어디야?": "교내복사실",
        "우리은행 전화번호 알려줘": "우리은행",
        "트러스트짐 어디야?": "트러스트짐",
    }.items():
        response = client.get("/places", params={"query": query, "limit": 1})
        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["slug"] == "kim-sou-hwan-hall"
        assert payload[0]["name"] == "K관"
        assert payload[0]["canonical_name"] == "김수환관"
        assert payload[0]["matched_facility"]["name"] == facility_name
        assert payload[0]["matched_facility"]["location_hint"] == "K관 1층"

    k_hall_response = client.get("/places", params={"query": "K관 어디야?", "limit": 1})
    assert k_hall_response.status_code == 200
    assert k_hall_response.json()[0]["slug"] == "kim-sou-hwan-hall"
    assert k_hall_response.json()[0]["name"] == "K관"
    assert k_hall_response.json()[0]["canonical_name"] == "김수환관"
    assert k_hall_response.json()[0].get("matched_facility") is None


def test_courses_endpoint_normalizes_spacing_variants(client):
    response = client.get("/courses", params={"query": "객체 지향", "year": 2026, "semester": 1})

    assert response.status_code == 200
    assert response.json()
    assert response.json()[0]["title"] == "객체지향프로그래밍설계"


def test_courses_endpoint_filters_by_period_start(client):
    response = client.get(
        "/courses",
        params={"year": 2026, "semester": 1, "period_start": 7, "limit": 5},
    )

    assert response.status_code == 200
    assert response.json()
    assert [item["code"] for item in response.json()] == ["CSE401"]
    assert all(item["period_start"] == 7 for item in response.json())


def test_nearby_restaurants_endpoint_uses_campus_graph_for_external_routes(client):
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "gate-bap",
                    "name": "정문백반",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.48590,
                    "longitude": 126.80282,
                    "tags": ["한식"],
                    "description": "테스트 식당",
                    "source_tag": "kakao_local",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    response = client.get(
        '/restaurants/nearby',
        params={'origin': 'central-library', 'walk_minutes': 15},
    )

    assert response.status_code == 200
    assert response.json()[0]['estimated_walk_minutes'] == 6


def test_nearby_restaurants_endpoint_falls_back_to_direct_distance_when_origin_is_not_in_graph(
    client,
):
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
                {
                    "slug": "gate-bap",
                    "name": "정문백반",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.48590,
                    "longitude": 126.80282,
                    "tags": ["한식"],
                    "description": "테스트 식당",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    response = client.get(
        "/restaurants/nearby",
        params={"origin": "annex-lobby", "walk_minutes": 15, "limit": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["slug"] for item in payload] == ["gate-bap"]
    assert payload[0]["estimated_walk_minutes"] == 1
    assert payload[0]["distance_meters"] is not None


def test_nearby_restaurants_endpoint_budget_max_requires_price_evidence(client):
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "budget-kimbap",
                    "name": "버짓김밥",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.48653,
                    "longitude": 126.80174,
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
                    "latitude": 37.48663,
                    "longitude": 126.80184,
                    "tags": ["카페"],
                    "description": "가격 정보가 없는 후보",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    response = client.get(
        "/restaurants/nearby",
        params={"origin": "central-library", "budget_max": 10000, "walk_minutes": 15},
    )

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == ["budget-kimbap"]


def test_place_detail_returns_404_for_missing_place(client):
    response = client.get('/places/does-not-exist')

    assert response.status_code == 404


def test_places_endpoint_matches_alias_from_override_taxonomy(client):
    response = client.get('/places', params={'query': '중도', 'limit': 5})

    assert response.status_code == 200
    payload = response.json()
    assert any(item['slug'] == 'central-library' for item in payload)


def test_nearby_restaurants_returns_404_for_missing_origin(client):
    response = client.get('/restaurants/nearby', params={'origin': 'does-not-exist'})

    assert response.status_code == 404


def test_nearby_restaurants_returns_400_for_ambiguous_origin(client):
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
                {
                    "slug": "test-bap",
                    "name": "테스트백반",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.4866,
                    "longitude": 126.8018,
                    "tags": ["한식"],
                    "description": "테스트 식당",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    response = client.get("/restaurants/nearby", params={"origin": "중도", "walk_minutes": 15})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Ambiguous origin: 중도.")


def test_nearby_restaurants_accepts_origin_alias(client):
    response = client.get('/restaurants/nearby', params={'origin': '중도', 'limit': 3})

    assert response.status_code == 200
    items = response.json()
    assert items
    assert all(item['origin'] == 'central-library' for item in items)


def test_nearby_restaurants_accepts_facility_alias_origin(client):
    response = client.get('/restaurants/nearby', params={'origin': '학생식당', 'limit': 3})

    assert response.status_code == 200
    items = response.json()
    assert items
    assert all(item['origin'] == 'student-center' for item in items)


def test_nearby_restaurants_can_filter_open_now(client):
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "cafe-dream",
                    "name": "카페드림",
                    "category": "cafe",
                    "min_price": 4000,
                    "max_price": 6500,
                    "latitude": 37.48695,
                    "longitude": 126.79995,
                    "tags": ["카페"],
                    "description": "테스트 카페",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "unknown-bap",
                    "name": "알수없음식당",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.4869,
                    "longitude": 126.7999,
                    "tags": ["한식"],
                    "description": "테스트 식당",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"카페드림": "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)"},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )

    response = client.get(
        "/restaurants/nearby",
        params={
            "origin": "central-library",
            "open_now": True,
            "at": "2026-03-15T11:00:00+09:00",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_nearby_restaurants_can_filter_open_now_for_late_night_hours(client):
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "night-snack",
                    "name": "야식분식",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.4869,
                    "longitude": 126.7999,
                    "tags": ["한식"],
                    "description": "야간 운영 테스트 식당",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"야식분식": "23:00~02:00"},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )

    response = client.get(
        "/restaurants/nearby",
        params={
            "origin": "central-library",
            "open_now": True,
            "at": "2026-03-16T23:30:00+09:00",
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["name"] == "야식분식"
    assert response.json()[0]["open_now"] is True


def test_nearby_restaurants_endpoint_reuses_kakao_cache(client, monkeypatch):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class ApiCacheKakaoClient:
        calls = 0

        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            type(self).calls += 1
            return [
                services.KakaoPlace(
                    name="가톨릭백반",
                    category="음식점 > 한식",
                    address="경기 부천시 원미구",
                    latitude=37.48674,
                    longitude=126.80182,
                    place_id="1",
                    place_url="https://place.map.kakao.com/1",
                )
            ]

    monkeypatch.setattr('songsim_campus.services.KakaoLocalClient', ApiCacheKakaoClient)

    first = client.get(
        '/restaurants/nearby',
        params={'origin': 'central-library', 'category': 'korean', 'walk_minutes': 15},
    )
    second = client.get(
        '/restaurants/nearby',
        params={'origin': 'central-library', 'category': 'korean', 'walk_minutes': 15},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert ApiCacheKakaoClient.calls == 1
    assert [item['name'] for item in first.json()] == [item['name'] for item in second.json()]
    assert all(item['source_tag'] == 'kakao_local' for item in first.json())
    assert all(item['source_tag'] == 'kakao_local_cache' for item in second.json())


def test_nearby_restaurants_endpoint_falls_back_to_local_results_when_cache_expired_and_live_fails(
    client,
    monkeypatch,
):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()
    old_now = datetime.fromisoformat("2026-03-10T12:00:00+09:00")
    expired_now = datetime.fromisoformat("2026-03-14T20:30:00+09:00")

    class ApiExpiredCacheKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            return [
                services.KakaoPlace(
                    name="가톨릭백반",
                    category="음식점 > 한식",
                    address="경기 부천시 원미구",
                    latitude=37.48674,
                    longitude=126.80182,
                    place_id="1",
                    place_url="https://place.map.kakao.com/1",
                )
            ]

    class ExplodingApiKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            raise services.httpx.HTTPError("boom")

    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "local-kimbap",
                    "name": "로컬김밥",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.48653,
                    "longitude": 126.80174,
                    "tags": ["한식"],
                    "description": "로컬 fallback 후보",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    monkeypatch.setattr("songsim_campus.services._now", lambda: old_now)
    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiExpiredCacheKakaoClient)
    first = client.get(
        "/restaurants/nearby",
        params={"origin": "central-library", "category": "korean", "walk_minutes": 15},
    )

    monkeypatch.setattr("songsim_campus.services._now", lambda: expired_now)
    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ExplodingApiKakaoClient)
    second = client.get(
        "/restaurants/nearby",
        params={"origin": "central-library", "category": "korean", "walk_minutes": 15},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert all(item["source_tag"] == "kakao_local" for item in first.json())
    assert [item["slug"] for item in second.json()] == ["local-kimbap"]
    assert all(
        item["source_tag"] not in {"kakao_local", "kakao_local_cache"}
        for item in second.json()
    )


def test_nearby_restaurants_endpoint_uses_kakao_detail_hours(client, monkeypatch):
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class ApiHoursKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            return [
                services.KakaoPlace(
                    name="가톨릭백반",
                    category="음식점 > 한식",
                    address="경기 부천시 원미구",
                    latitude=37.48674,
                    longitude=126.80182,
                    place_id="242731511",
                    place_url="https://place.map.kakao.com/242731511",
                )
            ]

    class ApiHoursDetailClient:
        def fetch_sync(self, place_id: str):
            assert place_id == "242731511"
            return {
                "open_hours": {
                    "all": {
                        "periods": [
                            {
                                "period_title": "기본 영업시간",
                                "days": [
                                    {
                                        "day_of_the_week": "월",
                                        "on_days": {
                                            "start_end_time_desc": "08:00 ~ 21:00"
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                }
            }

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", ApiHoursKakaoClient)
    monkeypatch.setattr("songsim_campus.services.KakaoPlaceDetailClient", ApiHoursDetailClient)

    response = client.get(
        "/restaurants/nearby",
        params={
            "origin": "central-library",
            "category": "korean",
            "open_now": True,
            "at": "2026-03-16T09:00:00+09:00",
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["name"] == "가톨릭백반"
    assert response.json()[0]["open_now"] is True


class ApiFacilitiesSource:
    def fetch(self):
        return '<facilities></facilities>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<facilities></facilities>'
        return [
            {
                'facility_name': '카페드림',
                'location': '중앙도서관 2층',
                'hours_text': '평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)',
                'category': '카페',
                'source_tag': 'cuk_facilities',
                'last_synced_at': fetched_at,
            }
        ]


class ApiDiningMenusSource:
    def fetch(self):
        return '<facilities-menu></facilities-menu>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<facilities-menu></facilities-menu>'
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

    def fetch_menu_document(self, url: str):
        return (
            b'%PDF-1.4\n'
            b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n'
            b'2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n'
            b'3 0 obj\n'
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R '
            b'/Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n'
            b'4 0 obj\n<< /Length 142 >>\nstream\nBT\n/F1 12 Tf\n72 720 Td\n'
            b'(Weekly Menu 2026.03.16 - 03.20) Tj\n0 -18 Td\n(Cafe Bona) Tj\n0 -18 Td\n'
            b'(Bulgogi Rice Bowl) Tj\n0 -18 Td\n(Lemon Tea) Tj\nET\nendstream\nendobj\n'
            b'5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n'
            b'xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n'
            b'0000000115 00000 n \n0000000241 00000 n \n0000000433 00000 n \n'
            b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n502\n%%EOF\n'
        )


class ApiTransportSource:
    def fetch(self):
        return '<transport></transport>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<transport></transport>'
        return [
            {
                'mode': 'bus',
                'title': '마을버스',
                'summary': '51번, 51-1번, 51-2번 버스',
                'steps': ['[가톨릭대학교, 역곡도서관] 정류장 하차'],
                'source_url': 'https://www.catholic.ac.kr/ko/about/location_songsim.do',
                'source_tag': 'cuk_transport',
                'last_synced_at': fetched_at,
            }
        ]


class ApiCertificateSource:
    def fetch(self):
        return "<certificate></certificate>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<certificate></certificate>"
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


class ApiLeaveOfAbsenceSource:
    def fetch(self):
        return "<leave></leave>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<leave></leave>"
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


class ApiAcademicCalendarSource:
    def fetch_range(self, *, start_date: str, end_date: str):
        assert start_date == "2026-03-01"
        assert end_date == "2027-02-28"
        return '{"data":[]}'

    def parse(self, payload: str, *, fetched_at: str):
        assert payload == '{"data":[]}'
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


class ApiScholarshipSource:
    def fetch(self):
        return "<scholarship></scholarship>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<scholarship></scholarship>"
        return [
            {
                "title": "공식 장학 문서",
                "summary": "장학금 지급 규정과 신입생/재학생 장학제도 공식 문서 링크",
                "steps": [],
                "links": [
                    {
                        "label": "재학생 장학제도",
                        "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/scholarship_songsim_251226-4pdf.pdf",
                    }
                ],
                "source_url": "https://www.catholic.ac.kr/ko/support/scholarship_songsim.do",
                "source_tag": "cuk_scholarship_guides",
                "last_synced_at": fetched_at,
            }
        ]


class ApiWifiGuideSource:
    def fetch(self):
        return "<wifi></wifi>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<wifi></wifi>"
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


class ApiAcademicSupportSource:
    def fetch(self):
        return "<academic-support></academic-support>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<academic-support></academic-support>"
        return [
            {
                "title": "수업 / 학점교류",
                "summary": "타 대학 학점교류 신청 · 관리 업무",
                "steps": ["타 대학 학점교류 신청 · 관리 업무"],
                "contacts": ["02-2164-4510", "02-2164-4048"],
                "source_url": "https://www.catholic.ac.kr/ko/support/academic_contact_information.do",
                "source_tag": "cuk_academic_support_guides",
                "last_synced_at": fetched_at,
            }
        ]


class ApiAcademicStatusSource:
    def __init__(self, status: str, rows: list[dict[str, object]]):
        self.status = status
        self.rows = rows

    def fetch(self):
        return f"<{self.status}></{self.status}>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == f"<{self.status}></{self.status}>"
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


def test_place_detail_returns_merged_opening_hours(client):
    with connection() as conn:
        refresh_facility_hours_from_facilities_page(conn, source=ApiFacilitiesSource())

    response = client.get('/places/central-library')
    payload = response.json()

    assert response.status_code == 200
    assert (
        payload['opening_hours']['카페드림']
        == '평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)'
    )


def test_dining_menus_endpoint_returns_current_week_rows(client):
    with connection() as conn:
        refresh_campus_dining_menus_from_facilities_page(conn, source=ApiDiningMenusSource())

    response = client.get('/dining-menus')
    payload = response.json()

    assert response.status_code == 200
    assert {item['venue_slug'] for item in payload} == {
        'buon-pranzo',
        'cafe-bona',
        'cafe-mensa',
    }
    bona = next(item for item in payload if item['venue_slug'] == 'cafe-bona')
    assert bona['place_name'] == '학생회관'
    assert bona['week_label'] == '3월 3주차 메뉴표 확인하기'
    assert bona['week_start'] == '2026-03-16'
    assert bona['source_url'] == 'https://www.catholic.ac.kr/menu/bona.pdf'
    assert 'Bulgogi Rice Bowl' in bona['menu_text']


def test_dining_menus_endpoint_supports_generic_and_specific_queries(client):
    with connection() as conn:
        refresh_campus_dining_menus_from_facilities_page(conn, source=ApiDiningMenusSource())

    generic_response = client.get('/dining-menus', params={'query': '학생식당 메뉴'})
    specific_response = client.get('/dining-menus', params={'query': '카페 보나 메뉴'})
    gpt_response = client.get('/gpt/dining-menus', params={'query': '교내 식당'})

    assert generic_response.status_code == 200
    assert len(generic_response.json()) == 3
    assert [item['venue_slug'] for item in specific_response.json()] == ['cafe-bona']
    assert gpt_response.status_code == 200
    assert gpt_response.json()[0]['menu_preview']
    assert gpt_response.json()[0]['source_url']


class ApiLibrarySeatStatusSource:
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


def test_library_seats_endpoints_return_live_or_filtered_rows(client, monkeypatch):
    monkeypatch.setattr(services, "LibrarySeatStatusSource", ApiLibrarySeatStatusSource)

    response = client.get("/library-seats")
    filtered = client.get("/library-seats", params={"query": "제1자유열람실"})
    gpt_response = client.get("/gpt/library-seats", params={"query": "열람실 남은 좌석"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["availability_mode"] == "live"
    assert payload["source_url"] == "http://203.229.203.240/8080/Domian5.asp"
    assert [item["room_name"] for item in payload["rooms"]] == [
        "제1자유열람실",
        "제2자유열람실",
    ]
    assert filtered.status_code == 200
    assert [item["room_name"] for item in filtered.json()["rooms"]] == ["제1자유열람실"]
    assert gpt_response.status_code == 200
    assert gpt_response.json()["rooms"][0]["remaining_seats"] == 28


def test_transport_endpoint_returns_guides(client):
    with connection() as conn:
        refresh_transport_guides_from_location_page(conn, source=ApiTransportSource())

    response = client.get('/transport', params={'mode': 'bus'})
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            'id': 1,
            'mode': 'bus',
            'title': '마을버스',
            'summary': '51번, 51-1번, 51-2번 버스',
            'steps': ['[가톨릭대학교, 역곡도서관] 정류장 하차'],
            'source_url': 'https://www.catholic.ac.kr/ko/about/location_songsim.do',
            'source_tag': 'cuk_transport',
            'last_synced_at': items[0]['last_synced_at'],
        }
    ]


def test_certificate_guides_endpoint_returns_guides(client):
    with connection() as conn:
        refresh_certificate_guides_from_certificate_page(conn, source=ApiCertificateSource())

    response = client.get("/certificate-guides")
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            "id": 1,
            "title": "인터넷 증명발급",
            "summary": "인터넷 증명신청 및 발급",
            "steps": [
                "수수료: 발급 : 국문 / 영문 1,000원(1매)",
                "유의사항: 영문증명서의 경우 영문 성명이 없으면 증명 발급이 되지 않음",
            ],
            "source_url": "https://catholic.certpia.com/",
            "source_tag": "cuk_certificate_guides",
            "last_synced_at": items[0]["last_synced_at"],
        }
    ]


def test_leave_of_absence_guides_endpoint_returns_guides(client):
    with connection() as conn:
        refresh_leave_of_absence_guides_from_source(conn, source=ApiLeaveOfAbsenceSource())

    response = client.get("/leave-of-absence-guides")
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            "id": 1,
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
            "last_synced_at": items[0]["last_synced_at"],
        }
    ]


def test_academic_calendar_endpoint_returns_events(client):
    with connection() as conn:
        refresh_academic_calendar_from_source(
            conn,
            source=ApiAcademicCalendarSource(),
            academic_year=2026,
        )

    response = client.get("/academic-calendar", params={"academic_year": 2026, "month": 3})
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            "id": 1,
            "academic_year": 2026,
            "title": "1학기 개시일",
            "start_date": "2026-03-03",
            "end_date": "2026-03-03",
            "campuses": ["성심", "성의", "성신"],
            "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
            "source_tag": "cuk_academic_calendar",
            "last_synced_at": items[0]["last_synced_at"],
        }
    ]


def test_scholarship_guides_endpoint_returns_guides(client):
    with connection() as conn:
        refresh_scholarship_guides_from_source(conn, source=ApiScholarshipSource())

    response = client.get("/scholarship-guides")
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            "id": 1,
            "title": "공식 장학 문서",
            "summary": "장학금 지급 규정과 신입생/재학생 장학제도 공식 문서 링크",
            "steps": [],
            "links": [
                {
                    "label": "재학생 장학제도",
                    "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/scholarship_songsim_251226-4pdf.pdf",
                }
            ],
            "source_url": "https://www.catholic.ac.kr/ko/support/scholarship_songsim.do",
            "source_tag": "cuk_scholarship_guides",
            "last_synced_at": items[0]["last_synced_at"],
        }
    ]


def test_wifi_guides_endpoint_returns_guides(client):
    with connection() as conn:
        refresh_wifi_guides_from_source(conn, source=ApiWifiGuideSource())

    response = client.get("/wifi-guides")
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            "id": 1,
            "building_name": "니콜스관",
            "ssids": ["catholic_univ", "강의실 호실명 (ex: N301)"],
            "steps": [
                "무선랜 안테나 검색 후 신호가 강한 SSID 선택 (최초 접속 시 보안키 입력)",
                "K관, A관(안드레아관) 보안키 : catholic!!(교내 동일)",
            ],
            "source_url": "https://www.catholic.ac.kr/ko/campuslife/wifi.do",
            "source_tag": "cuk_wifi_guides",
            "last_synced_at": items[0]["last_synced_at"],
        }
    ]


def test_academic_support_guides_endpoint_returns_guides(client):
    with connection() as conn:
        refresh_academic_support_guides_from_source(conn, source=ApiAcademicSupportSource())

    response = client.get("/academic-support-guides")
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            "id": 1,
            "title": "수업 / 학점교류",
            "summary": "타 대학 학점교류 신청 · 관리 업무",
            "steps": ["타 대학 학점교류 신청 · 관리 업무"],
            "contacts": ["02-2164-4510", "02-2164-4048"],
            "source_url": "https://www.catholic.ac.kr/ko/support/academic_contact_information.do",
            "source_tag": "cuk_academic_support_guides",
            "last_synced_at": items[0]["last_synced_at"],
        }
    ]


def test_academic_status_guides_endpoint_returns_guides_and_filters_by_status(client):
    with connection() as conn:
        refresh_academic_status_guides_from_source(
            conn,
            sources=[
                ApiAcademicStatusSource(
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
                ApiAcademicStatusSource(
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
                ApiAcademicStatusSource(
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
        )

    response = client.get("/academic-status-guides", params={"status": "dropout"})
    items = response.json()

    assert response.status_code == 200
    assert items == [
        {
            "id": 2,
            "status": "dropout",
            "title": "자퇴 신청 방법",
            "summary": "방문신청",
            "steps": ["학사지원팀에 자퇴원 제출"],
            "links": [],
            "source_url": "https://www.catholic.ac.kr/ko/support/dropout.do",
            "source_tag": "cuk_academic_status_guides",
            "last_synced_at": items[0]["last_synced_at"],
        }
    ]


def test_transport_endpoint_infers_subway_mode_from_query(client):
    with connection() as conn:
        replace_transport_guides(
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

    response = client.get("/transport", params={"query": "지하 철"})

    assert response.status_code == 200
    items = response.json()
    assert [item["mode"] for item in items] == ["subway"]
    assert items[0]["title"] == "1호선"


def test_transport_endpoint_returns_empty_for_unsupported_shuttle_query(client):
    with connection() as conn:
        replace_transport_guides(
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

    response = client.get("/transport", params={"query": "셔틀"})

    assert response.status_code == 200
    assert response.json() == []


def test_transport_endpoint_explicit_mode_wins_over_query(client):
    with connection() as conn:
        replace_transport_guides(
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

    response = client.get("/transport", params={"mode": "bus", "query": "지하철"})

    assert response.status_code == 200
    items = response.json()
    assert [item["mode"] for item in items] == ["bus"]
    assert items[0]["title"] == "시내버스"
