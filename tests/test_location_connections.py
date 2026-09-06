from songsim_campus import repo
from songsim_campus.db import connection, init_db
from songsim_campus.services import _current_year_and_semester, find_campus_place, search_places


def test_health_guide_connects_explicit_location_and_phone(app_env):
    init_db()
    synced = "2026-09-06T00:00:00+09:00"
    with connection() as conn:
        repo.replace_places(
            conn,
            [
                {
                    "slug": "virtus-hall",
                    "name": "비르투스관",
                    "category": "building",
                    "aliases": [],
                    "description": "",
                    "latitude": 37.0,
                    "longitude": 126.0,
                    "source_tag": "cuk_campus_map",
                    "last_synced_at": synced,
                }
            ],
        )
        repo.replace_campus_life_support_guides(
            conn,
            [
                {
                    "topic": "health_center",
                    "title": "보건실",
                    "summary": "건강 지원",
                    "steps": ["위치: 비르투스관 1층 104호", "운영시간: 08:30 ~ 17:30"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/health.do",
                    "source_tag": "cuk_campus_life_support_guides",
                    "last_synced_at": synced,
                }
            ],
        )
        repo.replace_phone_book_entries(
            conn,
            [
                {
                    "department": "보건실",
                    "tasks": "보건",
                    "phone": "4126",
                    "source_url": "https://www.catholic.ac.kr/ko/about/phone_book.do",
                    "source_tag": "cuk_phone_book",
                    "last_synced_at": synced,
                }
            ],
        )
        places = search_places(conn, query="보건실 어디야")
        assert len(places) == 1
        assert places[0].slug == "virtus-hall"
        facility = places[0].matched_facility
        assert facility.name == "보건실"
        assert facility.location_hint == "비르투스관 1층 104호"
        assert facility.phone_contacts[0].dial == "02-2164-4126"
        assert facility.source_url.endswith("health.do")
        assert search_places(conn, query="보건실", category="outdoor") == []
        assert search_places(conn, query="없는 시설 어디야") == []
        journey = find_campus_place(conn, query="보건실 어디야")
        assert {s.name for s in journey.sections} == {"places", "contacts"}


def test_only_rooms_present_in_current_courses_are_connected(app_env):
    init_db()
    year, semester = _current_year_and_semester()
    with connection() as conn:
        repo.replace_places(conn, [{
            "slug": "kim-sou-hwan-hall", "name": "김수환관", "category": "building",
            "aliases": ["K관"], "last_synced_at": "2026-09-06T00:00:00+09:00",
        }])
        repo.replace_courses(conn, [{
            "year": year, "semester": semester, "code": "QA001", "title": "테스트 과목",
            "room": "K106", "last_synced_at": "2026-09-06T00:00:00+09:00",
        }])
        places = search_places(conn, query="K106 어디야")
        assert places[0].slug == "kim-sou-hwan-hall"
        assert places[0].matched_facility.name == "K106"
        assert search_places(conn, query="K9999") == []
