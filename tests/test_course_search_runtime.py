from __future__ import annotations

from typing import Any

from songsim_campus import repo
from songsim_campus.course_search_runtime import (
    course_match_preview,
    course_query_candidates,
    course_row_matches_queries,
    investigate_course_query_coverage,
    looks_like_course_code_query,
    normalize_course_query_text,
    rank_course_search_candidate,
    search_course_rows,
)
from songsim_campus.db import connection, init_db


def _course_row(
    *,
    year: int = 2026,
    semester: int = 1,
    code: str,
    title: str,
    professor: str | None = "담당교수",
    section: str = "01",
    department: str = "테스트학과",
    day_of_week: str = "월",
    period_start: int = 1,
    period_end: int = 2,
    room: str = "M101",
    raw_schedule: str = "월1~2(M101)",
    source_tag: str = "test",
) -> dict[str, Any]:
    return {
        "year": year,
        "semester": semester,
        "code": code,
        "title": title,
        "professor": professor,
        "department": department,
        "section": section,
        "day_of_week": day_of_week,
        "period_start": period_start,
        "period_end": period_end,
        "room": room,
        "raw_schedule": raw_schedule,
        "source_tag": source_tag,
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


class FakeCourseCoverageSource:
    def __init__(self, pages: dict[int, list[dict[str, Any]]]):
        self.pages = pages
        self.fetch_offsets: list[int] = []

    def fetch(
        self,
        *,
        year: int,
        semester: int,
        department: str = "ALL",
        completion_type: str = "ALL",
        query: str = "",
        offset: int = 0,
    ) -> str:
        self.fetch_offsets.append(offset)
        return str(offset)

    def parse(self, html: str, *, fetched_at: str) -> list[dict[str, Any]]:
        return list(self.pages.get(int(html), []))


def test_normalize_course_query_text_and_candidates_match_current_alias_behavior() -> None:
    assert normalize_course_query_text(None) is None
    assert normalize_course_query_text(" 데이타베이스 ") == "데이터베이스"
    assert normalize_course_query_text("CSE 420") == "CSE 420"

    assert looks_like_course_code_query("CSE420")
    assert looks_like_course_code_query("CSE-420")
    assert looks_like_course_code_query("cSe 420")
    assert not looks_like_course_code_query("데이터베이스")

    assert course_query_candidates(None) == [""]
    assert course_query_candidates("   ") == [""]
    assert course_query_candidates("데이타베이스") == ["데이터베이스"]
    assert course_query_candidates("CSE 420") == ["CSE 420", "CSE420"]
    assert course_query_candidates("CSE-420") == ["CSE-420", "CSE420"]
    assert course_query_candidates("cSe 420") == ["cSe 420", "cSe420"]


def test_course_row_matches_queries_and_rank_candidate_priorities() -> None:
    rows = {
        "exact_code": _course_row(code="CSE101", title="알고리즘개론"),
        "code_prefix": _course_row(code="CSE210", title="프로그래밍실습"),
        "exact_title": _course_row(code="MAT100", title="CSE"),
        "title_prefix": _course_row(code="MAT101", title="CSE 구조"),
        "exact_professor": _course_row(code="MAT102", title="수학", professor="CSE"),
        "professor_prefix": _course_row(code="MAT103", title="수학", professor="CSE 연구"),
        "partial": _course_row(code="MAT104", title="고급자료분석"),
    }

    assert course_row_matches_queries(rows["exact_code"], ["CSE101"])
    assert course_row_matches_queries(rows["exact_title"], ["CSE"])
    assert course_row_matches_queries(rows["exact_professor"], ["CSE"])
    assert not course_row_matches_queries(rows["partial"], ["없는과목"])

    assert rank_course_search_candidate(rows["exact_code"], queries=["CSE101"]) == 0
    assert rank_course_search_candidate(rows["code_prefix"], queries=["CSE"]) == 1
    assert rank_course_search_candidate(rows["exact_title"], queries=["CSE"]) == 2
    assert rank_course_search_candidate(rows["title_prefix"], queries=["CSE"]) == 3
    assert rank_course_search_candidate(rows["exact_professor"], queries=["CSE"]) == 4
    assert rank_course_search_candidate(rows["professor_prefix"], queries=["CSE"]) == 5
    assert rank_course_search_candidate(rows["partial"], queries=["자료"]) == 6


def test_course_match_preview_limits_to_requested_rows() -> None:
    rows = [
        _course_row(code="CSE101", title="알고리즘개론", professor="김가톨"),
        _course_row(code="CSE420", title="임베디드시스템", professor="박성심"),
        _course_row(code="MTH101", title="데이터베이스활용", professor="권보람"),
    ]

    assert course_match_preview(rows, limit=2) == [
        {
            "code": "CSE101",
            "title": "알고리즘개론",
            "professor": "김가톨",
            "department": "테스트학과",
            "section": "01",
        },
        {
            "code": "CSE420",
            "title": "임베디드시스템",
            "professor": "박성심",
            "department": "테스트학과",
            "section": "01",
        },
    ]


def test_search_course_rows_matches_current_course_search_behavior(app_env) -> None:
    init_db()

    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                _course_row(code="CSE420", title="임베디드시스템"),
                _course_row(code="MTH101", title="데이터베이스활용"),
                _course_row(code="BIO102", title="분자생물학개론", professor="박요셉"),
                _course_row(code="CHE103", title="화학실험", professor="김가톨"),
                _course_row(code="EEE200", title="CSE101 프로젝트"),
                _course_row(code="CSE101", title="알고리즘개론"),
                _course_row(code="MAT100", title="CSE"),
                _course_row(code="GEN900", title="고급자료분석"),
                _course_row(code="CSE900", title="자료"),
                _course_row(code="CSE901", title="자료구조"),
                _course_row(code="HIS900", title="컴퓨터개론", professor="자료"),
                _course_row(code="DAT103", title="Data Structures", year=2026, semester=1),
                _course_row(code="DAT100", title="Data Mining", year=2027, semester=1),
                _course_row(code="DAT102", title="Data Analytics", year=2026, semester=1),
                _course_row(code="DAT101", title="Data Models", year=2026, semester=2),
            ],
        )

        alias_courses = search_course_rows(conn, query="데이타베이스", limit=5)
        spaced_database_courses = search_course_rows(conn, query="데 이 터 베 이 스", limit=5)
        spaced_code_courses = search_course_rows(conn, query="CSE 420", limit=5)
        dashed_code_courses = search_course_rows(conn, query="CSE-420", limit=5)
        mixed_case_code_courses = search_course_rows(conn, query="cSe 420", limit=5)
        compact_code_courses = search_course_rows(conn, query="CSE420", limit=5)
        spaced_professor_courses = search_course_rows(conn, query="김 가 톨", limit=5)
        spaced_professor_two_courses = search_course_rows(conn, query="박 요 셉", limit=5)
        source_title_courses = search_course_rows(conn, query="자료", limit=10)
        tie_break_courses = search_course_rows(conn, query="Data", limit=10)

    assert [course["code"] for course in alias_courses] == ["MTH101"]
    assert [course["code"] for course in spaced_database_courses] == ["MTH101"]
    assert [course["code"] for course in spaced_code_courses] == ["CSE420"]
    assert [course["code"] for course in dashed_code_courses] == ["CSE420"]
    assert [course["code"] for course in mixed_case_code_courses] == ["CSE420"]
    assert [course["code"] for course in compact_code_courses] == ["CSE420"]
    assert [course["code"] for course in spaced_professor_courses] == ["CHE103"]
    assert [course["code"] for course in spaced_professor_two_courses] == ["BIO102"]
    assert [course["code"] for course in source_title_courses] == [
        "CSE900",
        "CSE901",
        "HIS900",
        "GEN900",
    ]
    assert [course["code"] for course in tie_break_courses] == [
        "DAT100",
        "DAT101",
        "DAT102",
        "DAT103",
    ]


def test_investigate_course_query_coverage_reports_statuses_for_source_db_and_search_gaps(
    app_env,
    monkeypatch,
) -> None:
    init_db()
    source = FakeCourseCoverageSource(
        {
            0: [
                _course_row(
                    code="05497",
                    title="데이터베이스활용",
                    professor="권보람",
                    department="경영학과",
                ),
                _course_row(
                    code="CSE420",
                    title="임베디드시스템",
                    professor="박성심",
                    department="컴퓨터정보공학부",
                ),
            ],
        }
    )

    with connection() as conn:
        repo.replace_courses(
            conn,
            [
                _course_row(
                    code="05497",
                    title="데이터베이스활용",
                    professor="권보람",
                    department="경영학과",
                ),
                _course_row(
                    code="CSE420",
                    title="임베디드시스템",
                    professor="박성심",
                    department="컴퓨터정보공학부",
                ),
            ],
        )
        reports = investigate_course_query_coverage(
            conn,
            queries=["데이타베이스", "CSE301", "김가톨", "CSE 420"],
            source=source,
            year=2026,
            semester=1,
            fetched_at="2026-03-20T00:00:00+09:00",
        )
        repo.replace_courses(conn, [])
        db_gap_reports = investigate_course_query_coverage(
            conn,
            queries=["데이터베이스"],
            source=source,
            year=2026,
            semester=1,
            fetched_at="2026-03-20T00:00:00+09:00",
        )
        repo.replace_courses(
            conn,
            [
                _course_row(
                    code="05497",
                    title="데이터베이스활용",
                    professor="권보람",
                    department="경영학과",
                ),
                _course_row(
                    code="CSE420",
                    title="임베디드시스템",
                    professor="박성심",
                    department="컴퓨터정보공학부",
                ),
            ],
        )
        monkeypatch.setattr(
            "songsim_campus.course_search_runtime.search_course_rows",
            lambda *args, **kwargs: [],
        )
        search_gap_reports = investigate_course_query_coverage(
            conn,
            queries=["CSE 420"],
            source=source,
            year=2026,
            semester=1,
            fetched_at="2026-03-20T00:00:00+09:00",
        )

    assert reports == [
        {
            "query": "데이타베이스",
            "year": 2026,
            "semester": 1,
            "status": "covered",
            "source_match_count": 1,
            "db_match_count": 1,
            "search_match_count": 1,
            "source_matches": [
                {
                    "code": "05497",
                    "title": "데이터베이스활용",
                    "professor": "권보람",
                    "department": "경영학과",
                    "section": "01",
                }
            ],
            "db_matches": [
                {
                    "code": "05497",
                    "title": "데이터베이스활용",
                    "professor": "권보람",
                    "department": "경영학과",
                    "section": "01",
                }
            ],
            "search_matches": [
                {
                    "code": "05497",
                    "title": "데이터베이스활용",
                    "professor": "권보람",
                    "department": "경영학과",
                    "section": "01",
                }
            ],
        },
        {
            "query": "CSE301",
            "year": 2026,
            "semester": 1,
            "status": "source_gap",
            "source_match_count": 0,
            "db_match_count": 0,
            "search_match_count": 0,
            "source_matches": [],
            "db_matches": [],
            "search_matches": [],
        },
        {
            "query": "김가톨",
            "year": 2026,
            "semester": 1,
            "status": "source_gap",
            "source_match_count": 0,
            "db_match_count": 0,
            "search_match_count": 0,
            "source_matches": [],
            "db_matches": [],
            "search_matches": [],
        },
        {
            "query": "CSE 420",
            "year": 2026,
            "semester": 1,
            "status": "covered",
            "source_match_count": 1,
            "db_match_count": 1,
            "search_match_count": 1,
            "source_matches": [
                {
                    "code": "CSE420",
                    "title": "임베디드시스템",
                    "professor": "박성심",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                }
            ],
            "db_matches": [
                {
                    "code": "CSE420",
                    "title": "임베디드시스템",
                    "professor": "박성심",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                }
            ],
            "search_matches": [
                {
                    "code": "CSE420",
                    "title": "임베디드시스템",
                    "professor": "박성심",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                }
            ],
        },
    ]
    assert db_gap_reports[0]["status"] == "db_gap"
    assert db_gap_reports[0]["source_match_count"] == 1
    assert db_gap_reports[0]["db_match_count"] == 0
    assert db_gap_reports[0]["search_match_count"] == 0
    assert search_gap_reports[0]["status"] == "search_gap"
    assert search_gap_reports[0]["source_match_count"] == 1
    assert search_gap_reports[0]["db_match_count"] == 1
    assert search_gap_reports[0]["search_match_count"] == 0


def test_current_year_and_semester_reads_the_clock_in_seoul():
    """학기 경계는 학교 시계로 넘긴다.

    current.month 를 그대로 쓰기 때문에, 6월 30일 밤 KST 를 UTC 로 읽으면
    아직 6월이어서 1학기로 잡힌다. 반대편 경계도 마찬가지다.
    """
    from datetime import datetime

    from songsim_campus.course_search_runtime import _current_year_and_semester

    def term(iso: str) -> tuple[int, int]:
        return _current_year_and_semester(datetime.fromisoformat(iso))

    # 2026-07-01 01:00 KST = 2026-06-30 16:00 UTC. 학교 기준으로는 이미 2학기다.
    assert term("2026-07-01T01:00:00+09:00") == (2026, 2)
    assert term("2026-06-30T16:00:00+00:00") == (2026, 2)

    # 2027-01-01 08:00 KST = 2026-12-31 23:00 UTC. 해가 바뀐 뒤다.
    assert term("2027-01-01T08:00:00+09:00") == (2027, 1)
    assert term("2026-12-31T23:00:00+00:00") == (2027, 1)
