from __future__ import annotations

from songsim_campus import repo
from songsim_campus.db import connection, init_db
from songsim_campus.seed import seed_demo
from songsim_campus.services import (
    get_sync_dashboard_state,
    list_sync_runs,
    run_admin_sync,
)


def test_run_admin_sync_records_success_history_for_snapshot(app_env, monkeypatch):
    init_db()

    def fake_snapshot(
        conn,
        *,
        campus: str | None = None,
        year: int | None = None,
        semester: int | None = None,
        notice_pages: int | None = None,
    ):
        assert campus == "2"
        assert year == 2026
        assert semester == 1
        assert notice_pages == 2
        return {
            "places": 3,
            "dining_menus": 3,
            "courses": 5,
            "notices": 7,
            "affiliated_notices": 8,
            "campus_life_notices": 9,
            "certificate_guides": 2,
            "leave_of_absence_guides": 4,
            "academic_status_guides": 3,
            "registration_guides": 4,
            "class_guides": 4,
            "seasonal_semester_guides": 4,
            "academic_milestone_guides": 4,
            "student_activity_notices": 2,
            "about_resource_guides": 3,
            "service_policy_guides": 5,
            "newsroom_posts": 6,
            "dormitory_guides": 4,
            "phone_book_entries": 5,
            "campus_life_support_guides": 3,
            "pc_software_entries": 4,
            "scholarship_guides": 4,
            "academic_support_guides": 3,
            "transport_guides": 1,
        }

    monkeypatch.setattr("songsim_campus.services.sync_official_snapshot", fake_snapshot)

    run = run_admin_sync(campus="2", year=2026, semester=1, notice_pages=2)

    assert run.target == "snapshot"
    assert run.status == "success"
    assert run.summary == {
        "places": 3,
        "dining_menus": 3,
        "courses": 5,
        "notices": 7,
        "affiliated_notices": 8,
        "campus_life_notices": 9,
        "certificate_guides": 2,
        "leave_of_absence_guides": 4,
        "academic_status_guides": 3,
        "registration_guides": 4,
        "class_guides": 4,
        "seasonal_semester_guides": 4,
        "academic_milestone_guides": 4,
        "student_activity_notices": 2,
        "about_resource_guides": 3,
        "service_policy_guides": 5,
        "newsroom_posts": 6,
        "dormitory_guides": 4,
        "phone_book_entries": 5,
        "campus_life_support_guides": 3,
        "pc_software_entries": 4,
        "scholarship_guides": 4,
        "academic_support_guides": 3,
        "transport_guides": 1,
    }
    assert run.error_text is None
    assert run.finished_at is not None

    with connection() as conn:
        runs = list_sync_runs(conn, limit=10)
        dashboard = get_sync_dashboard_state(conn)

    assert runs[0].id == run.id
    assert runs[0].trigger == "manual"
    assert runs[0].params == {"campus": "2", "year": 2026, "semester": 1, "notice_pages": 2}
    assert dashboard["recent_runs"][0].id == run.id


def test_run_admin_sync_dispatches_target_specific_parameters(app_env, monkeypatch):
    init_db()
    seen: dict[str, object] = {}

    def fake_places(conn, *, campus: str = "1", fetched_at: str | None = None):
        seen["places"] = {"campus": campus, "fetched_at": fetched_at}
        return []

    def fake_courses(
        conn,
        *,
        year: int | None = None,
        semester: int | None = None,
        fetched_at: str | None = None,
        source=None,
    ):
        seen["courses"] = {"year": year, "semester": semester, "fetched_at": fetched_at}
        return []

    def fake_notices(conn, *, pages: int = 1, fetched_at: str | None = None, source=None):
        seen["notices"] = {"pages": pages, "fetched_at": fetched_at}
        return []

    def fake_affiliated_notices(
        conn,
        *,
        pages: int = 1,
        fetched_at: str | None = None,
        sources=None,
    ):
        seen["affiliated_notices"] = {"pages": pages, "fetched_at": fetched_at}
        return []

    def fake_campus_life_notices(
        conn,
        *,
        pages: int = 1,
        fetched_at: str | None = None,
        sources=None,
    ):
        seen["campus_life_notices"] = {"pages": pages, "fetched_at": fetched_at}
        return []

    def fake_dining_menus(conn, *, fetched_at: str | None = None, source=None):
        seen["dining_menus"] = {"fetched_at": fetched_at}
        return []

    def fake_scholarship_guides(conn, *, fetched_at: str | None = None, source=None):
        seen["scholarship_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_academic_status_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["academic_status_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_registration_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["registration_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_class_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["class_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_seasonal_semester_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["seasonal_semester_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_academic_milestone_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["academic_milestone_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_student_activity_notices(
        conn,
        *,
        pages: int = 1,
        fetched_at: str | None = None,
        source=None,
    ):
        seen["student_activity_notices"] = {"pages": pages, "fetched_at": fetched_at}
        return []

    def fake_about_resource_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["about_resource_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_service_policy_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["service_policy_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_newsroom_posts(conn, *, fetched_at: str | None = None, sources=None):
        seen["newsroom_posts"] = {"fetched_at": fetched_at}
        return []

    def fake_dormitory_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["dormitory_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_phone_book_entries(conn, *, fetched_at: str | None = None, source=None):
        seen["phone_book_entries"] = {"fetched_at": fetched_at}
        return []

    def fake_campus_life_support_guides(conn, *, fetched_at: str | None = None, sources=None):
        seen["campus_life_support_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_pc_software_entries(conn, *, fetched_at: str | None = None, source=None):
        seen["pc_software_entries"] = {"fetched_at": fetched_at}
        return []

    def fake_academic_support_guides(conn, *, fetched_at: str | None = None, source=None):
        seen["academic_support_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_leave_of_absence_guides(conn, *, fetched_at: str | None = None, source=None):
        seen["leave_of_absence_guides"] = {"fetched_at": fetched_at}
        return []

    def fake_library_seat_status(conn, *, fetched_at: str | None = None, source=None):
        seen["library_seat_status"] = {"fetched_at": fetched_at}
        return [
            {
                "room_name": "제1자유열람실",
                "remaining_seats": 28,
                "occupied_seats": 72,
                "total_seats": 100,
                "source_url": "http://203.229.203.240/8080/Domian5.asp",
                "source_tag": "cuk_library_seat_status",
                "last_synced_at": fetched_at or "2026-03-16T09:00:00+09:00",
            }
        ]

    monkeypatch.setattr("songsim_campus.services.refresh_places_from_campus_map", fake_places)
    monkeypatch.setattr("songsim_campus.services.refresh_courses_from_subject_search", fake_courses)
    monkeypatch.setattr("songsim_campus.services.refresh_notices_from_notice_board", fake_notices)
    monkeypatch.setattr(
        "songsim_campus.services.refresh_affiliated_notices_from_sources",
        fake_affiliated_notices,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_campus_life_notices_from_source",
        fake_campus_life_notices,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_campus_dining_menus_from_facilities_page",
        fake_dining_menus,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_leave_of_absence_guides_from_source",
        fake_leave_of_absence_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_scholarship_guides_from_source",
        fake_scholarship_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_academic_status_guides_from_source",
        fake_academic_status_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_registration_guides_from_source",
        fake_registration_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_class_guides_from_source",
        fake_class_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_seasonal_semester_guides_from_source",
        fake_seasonal_semester_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_academic_milestone_guides_from_source",
        fake_academic_milestone_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_student_activity_notices_from_source",
        fake_student_activity_notices,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_about_resource_guides_from_source",
        fake_about_resource_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_service_policy_guides_from_source",
        fake_service_policy_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_newsroom_posts_from_source",
        fake_newsroom_posts,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_dormitory_guides_from_source",
        fake_dormitory_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_phone_book_entries_from_source",
        fake_phone_book_entries,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_campus_life_support_guides_from_source",
        fake_campus_life_support_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_pc_software_entries_from_source",
        fake_pc_software_entries,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_academic_support_guides_from_source",
        fake_academic_support_guides,
    )
    monkeypatch.setattr(
        "songsim_campus.services.refresh_library_seat_status_cache",
        fake_library_seat_status,
    )

    places_run = run_admin_sync(target="places", campus="9")
    dining_run = run_admin_sync(target="dining_menus")
    leave_run = run_admin_sync(target="leave_of_absence_guides")
    status_run = run_admin_sync(target="academic_status_guides")
    registration_run = run_admin_sync(target="registration_guides")
    class_run = run_admin_sync(target="class_guides")
    seasonal_run = run_admin_sync(target="seasonal_semester_guides")
    milestone_run = run_admin_sync(target="academic_milestone_guides")
    student_activity_notices_run = run_admin_sync(target="student_activity_notices")
    about_resource_run = run_admin_sync(target="about_resource_guides")
    service_policy_run = run_admin_sync(target="service_policy_guides")
    newsroom_run = run_admin_sync(target="newsroom_posts")
    dormitory_run = run_admin_sync(target="dormitory_guides")
    phone_book_run = run_admin_sync(target="phone_book_entries")
    campus_life_support_run = run_admin_sync(target="campus_life_support_guides")
    pc_software_run = run_admin_sync(target="pc_software_entries")
    scholarship_run = run_admin_sync(target="scholarship_guides")
    library_run = run_admin_sync(target="library_seat_status")
    support_run = run_admin_sync(target="academic_support_guides")
    courses_run = run_admin_sync(target="courses", year=2026, semester=1)
    notices_run = run_admin_sync(target="notices", notice_pages=3)
    affiliated_run = run_admin_sync(target="affiliated_notices")
    campus_life_notices_run = run_admin_sync(target="campus_life_notices")

    assert places_run.summary == {"places": 0}
    assert dining_run.summary == {"dining_menus": 0}
    assert leave_run.summary == {"leave_of_absence_guides": 0}
    assert status_run.summary == {"academic_status_guides": 0}
    assert registration_run.summary == {"registration_guides": 0}
    assert class_run.summary == {"class_guides": 0}
    assert seasonal_run.summary == {"seasonal_semester_guides": 0}
    assert milestone_run.summary == {"academic_milestone_guides": 0}
    assert student_activity_notices_run.summary == {"student_activity_notices": 0}
    assert about_resource_run.summary == {"about_resource_guides": 0}
    assert service_policy_run.summary == {"service_policy_guides": 0}
    assert newsroom_run.summary == {"newsroom_posts": 0}
    assert affiliated_run.summary == {"affiliated_notices": 0}
    assert campus_life_notices_run.summary == {"campus_life_notices": 0}
    assert dormitory_run.summary == {"dormitory_guides": 0}
    assert phone_book_run.summary == {"phone_book_entries": 0}
    assert campus_life_support_run.summary == {"campus_life_support_guides": 0}
    assert pc_software_run.summary == {"pc_software_entries": 0}
    assert scholarship_run.summary == {"scholarship_guides": 0}
    assert support_run.summary == {"academic_support_guides": 0}
    assert library_run.summary == {"library_seat_status": 1}
    assert courses_run.summary == {"courses": 0}
    assert notices_run.summary == {"notices": 0}
    assert seen["places"] == {"campus": "9", "fetched_at": None}
    assert seen["dining_menus"] == {"fetched_at": None}
    assert seen["leave_of_absence_guides"] == {"fetched_at": None}
    assert seen["academic_status_guides"] == {"fetched_at": None}
    assert seen["registration_guides"] == {"fetched_at": None}
    assert seen["class_guides"] == {"fetched_at": None}
    assert seen["seasonal_semester_guides"] == {"fetched_at": None}
    assert seen["academic_milestone_guides"] == {"fetched_at": None}
    assert seen["student_activity_notices"] == {"pages": 3, "fetched_at": None}
    assert seen["about_resource_guides"] == {"fetched_at": None}
    assert seen["service_policy_guides"] == {"fetched_at": None}
    assert seen["newsroom_posts"] == {"fetched_at": None}
    assert seen["affiliated_notices"] == {"pages": 1, "fetched_at": None}
    assert seen["campus_life_notices"] == {"pages": 1, "fetched_at": None}
    assert seen["dormitory_guides"] == {"fetched_at": None}
    assert seen["phone_book_entries"] == {"fetched_at": None}
    assert seen["campus_life_support_guides"] == {"fetched_at": None}
    assert seen["pc_software_entries"] == {"fetched_at": None}
    assert seen["scholarship_guides"] == {"fetched_at": None}
    assert seen["academic_support_guides"] == {"fetched_at": None}
    assert seen["library_seat_status"] == {"fetched_at": None}
    assert seen["courses"] == {"year": 2026, "semester": 1, "fetched_at": None}
    assert seen["notices"] == {"pages": 3, "fetched_at": None}


def test_run_admin_sync_student_activity_notices_uses_notice_pages(app_env, monkeypatch):
    init_db()
    seen: dict[str, object] = {}

    def fake_student_activity_notices(conn, *, pages: int = 1, source=None):
        seen["student_activity_notices"] = {"pages": pages, "source": source}
        return []

    monkeypatch.setattr(
        "songsim_campus.services.refresh_student_activity_notices_from_source",
        fake_student_activity_notices,
    )

    run = run_admin_sync(target="student_activity_notices", notice_pages=4)

    assert run.summary == {"student_activity_notices": 0}
    assert run.params == {"notice_pages": 4}
    assert seen["student_activity_notices"] == {"pages": 4, "source": None}


def test_run_admin_sync_rolls_back_failed_target_and_records_failure(app_env, monkeypatch):
    init_db()

    def broken_transport(conn, *, fetched_at: str | None = None, source=None):
        repo.replace_transport_guides(
            conn,
            [
                {
                    "mode": "bus",
                    "title": "실패 전 임시 데이터",
                    "summary": "",
                    "steps": [],
                    "source_url": None,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-14T10:00:00+09:00",
                }
            ],
        )
        raise RuntimeError("transport sync exploded")

    monkeypatch.setattr(
        "songsim_campus.services.refresh_transport_guides_from_location_page",
        broken_transport,
    )

    run = run_admin_sync(target="transport_guides")

    assert run.status == "failed"
    assert run.summary == {}
    assert "transport sync exploded" in (run.error_text or "")

    with connection() as conn:
        assert repo.count_rows(conn, "transport_guides") == 0
        stored = list_sync_runs(conn, limit=10)

    assert stored[0].status == "failed"
    assert "transport sync exploded" in (stored[0].error_text or "")


def test_run_admin_sync_keeps_library_seat_cache_when_refresh_fails(app_env, monkeypatch):
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

    def broken_library_seat_status(conn, *, fetched_at: str | None = None, source=None):
        raise RuntimeError("seat refresh exploded")

    monkeypatch.setattr(
        "songsim_campus.services.refresh_library_seat_status_cache",
        broken_library_seat_status,
    )

    run = run_admin_sync(target="library_seat_status")

    assert run.status == "failed"
    assert run.summary == {}
    assert "seat refresh exploded" in (run.error_text or "")

    with connection() as conn:
        cached = repo.list_library_seat_status_cache(conn)
        stored = list_sync_runs(conn, limit=10)

    assert len(cached) == 1
    assert cached[0]["remaining_seats"] == 10
    assert stored[0].status == "failed"


def test_get_sync_dashboard_state_reports_row_counts_and_last_synced(app_env):
    init_db()
    seed_demo(force=True)

    with connection() as conn:
        state = get_sync_dashboard_state(conn)

    datasets = {item["name"]: item for item in state["datasets"]}
    assert datasets["places"]["row_count"] == 5
    assert datasets["courses"]["row_count"] > 0
    assert datasets["campus_dining_menus"]["row_count"] == 0
    assert datasets["certificate_guides"]["row_count"] == 0
    assert datasets["leave_of_absence_guides"]["row_count"] == 0
    assert datasets["academic_status_guides"]["row_count"] == 0
    assert datasets["scholarship_guides"]["row_count"] == 0
    assert datasets["academic_support_guides"]["row_count"] == 0
    assert datasets["notices"]["row_count"] > 0
    assert datasets["transport_guides"]["row_count"] == 0
    assert datasets["places"]["last_synced_at"] == "2026-03-13T09:00:00+09:00"
    assert datasets["campus_dining_menus"]["last_synced_at"] is None
    assert datasets["certificate_guides"]["last_synced_at"] is None
    assert datasets["leave_of_absence_guides"]["last_synced_at"] is None
    assert datasets["academic_status_guides"]["last_synced_at"] is None
    assert datasets["scholarship_guides"]["last_synced_at"] is None
    assert datasets["academic_support_guides"]["last_synced_at"] is None
    assert datasets["transport_guides"]["last_synced_at"] is None
    assert state["recent_runs"] == []
