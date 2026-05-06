from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from songsim_campus import qa_eval, repo
from songsim_campus.db import connection, init_db
from songsim_campus.public_api_eval_corpus_builder import (
    COARSE_CAP_ENFORCED_DOMAINS,
    DOMAIN_QUOTAS,
    STYLE_QUOTAS,
    TRUTH_MODE_QUOTAS,
    build_public_api_eval_corpus,
    coarse_request_key_from_payload,
)
from songsim_campus.qa_eval import (
    DEFAULT_CORPUS_PATH,
    DEFAULT_WATCHLIST_PATH,
    EvalCorpusRow,
    EvalTruthRow,
    build_truth_rows,
    load_eval_rows,
    render_validation_report,
    run_evaluation,
    run_row_evaluation,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_load_eval_rows_rejects_duplicate_ids(tmp_path: Path) -> None:
    corpus_path = tmp_path / "duplicate.jsonl"
    _write_jsonl(
        corpus_path,
        [
            {
                "id": "QA001",
                "domain": "place",
                "style": "normal",
                "user_utterance": "중앙도서관 위치 알려줘",
                "api_request": {"path": "/places", "params": {"query": "중앙도서관"}},
                "expected_mcp_flow": "prompt_find_place -> tool_search_places -> tool_get_place",
                "truth_mode": "exact_value",
                "pass_rule": {"summary_kind": "places_top3"},
                "watch_policy": "none",
                "notes": "",
            },
            {
                "id": "QA001",
                "domain": "place",
                "style": "normal",
                "user_utterance": "정문 위치 알려줘",
                "api_request": {"path": "/places", "params": {"query": "정문"}},
                "expected_mcp_flow": "tool_search_places -> tool_get_place",
                "truth_mode": "exact_value",
                "pass_rule": {"summary_kind": "places_top3"},
                "watch_policy": "none",
                "notes": "",
            },
        ],
    )

    with pytest.raises(ValueError, match="Duplicate evaluation id"):
        load_eval_rows(corpus_path)


def test_load_eval_rows_rejects_invalid_truth_mode(tmp_path: Path) -> None:
    corpus_path = tmp_path / "invalid.jsonl"
    _write_jsonl(
        corpus_path,
        [
            {
                "id": "QA001",
                "domain": "place",
                "style": "normal",
                "user_utterance": "중앙도서관 위치 알려줘",
                "api_request": {"path": "/places", "params": {"query": "중앙도서관"}},
                "expected_mcp_flow": "prompt_find_place -> tool_search_places -> tool_get_place",
                "truth_mode": "made_up_mode",
                "pass_rule": {"summary_kind": "places_top3"},
                "watch_policy": "none",
                "notes": "",
            }
        ],
    )

    with pytest.raises(ValueError, match="truth_mode"):
        load_eval_rows(corpus_path)


@pytest.mark.parametrize(
    ("query", "expected_code", "source_rows"),
    [
        (
            "데이타베이스",
            "MTH101",
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "MTH101",
                    "title": "데이터베이스활용",
                    "professor": "권보람",
                    "department": "경영학과",
                    "section": "01",
                    "day_of_week": "화",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "M307",
                    "raw_schedule": "화1~2(M307)",
                    "source_tag": "cuk_subject_search",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        ),
        (
            "데 이 터 베 이 스",
            "MTH101",
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "MTH101",
                    "title": "데이터베이스활용",
                    "professor": "권보람",
                    "department": "경영학과",
                    "section": "01",
                    "day_of_week": "화",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "M307",
                    "raw_schedule": "화1~2(M307)",
                    "source_tag": "cuk_subject_search",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        ),
        (
            "cSe 420",
            "CSE420",
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE420",
                    "title": "임베디드시스템",
                    "professor": "박성심",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "목",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "목5~6(N201)",
                    "source_tag": "cuk_subject_search",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        ),
        (
            "CSE-420",
            "CSE420",
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE420",
                    "title": "임베디드시스템",
                    "professor": "박성심",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "목",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "목5~6(N201)",
                    "source_tag": "cuk_subject_search",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        ),
        (
            "박 요 셉",
            "BIO102",
            [
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
                    "source_tag": "cuk_subject_search",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        ),
    ],
)
def test_search_courses_from_source_normalizes_database_alias(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    expected_code: str,
    source_rows: list[dict[str, object]],
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "CQ001",
            "domain": "courses",
            "style": "normal",
            "user_utterance": f"{query} 과목 있어",
            "api_request": {
                "path": "/courses",
                "params": {"query": query, "year": 2026, "semester": 1},
            },
            "expected_mcp_flow": "tool_search_courses",
            "truth_mode": "watch_only",
            "pass_rule": {"summary_kind": "courses_top5"},
            "watch_policy": "course_source_gap",
            "notes": "source-backed direct hit 미확인",
        }
    )
    monkeypatch.setattr(
        qa_eval,
        "_collect_course_snapshot_rows",
        lambda *args, **kwargs: source_rows,
    )

    results = qa_eval._search_courses_from_source(
        row,
        fetched_at="2026-03-20T10:10:00+09:00",
        source_cache={},
    )

    assert [item["code"] for item in results] == [expected_code]


def test_build_truth_rows_uses_database_snapshot_for_academic_support_guides(app_env: str) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "AG001",
            "domain": "academic_support_guides",
            "style": "normal",
            "user_utterance": "휴복학 문의 어디로 해야 해?",
            "api_request": {"path": "/academic-support-guides", "params": {"limit": 3}},
            "expected_mcp_flow": "tool_list_academic_support_guides",
            "truth_mode": "exact_value",
            "pass_rule": {"summary_kind": "academic_support_guides_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    init_db()
    with connection() as conn:
        repo.replace_academic_support_guides(
            conn,
            [
                {
                    "title": "휴·복학",
                    "summary": "휴·복학 관련 업무",
                    "steps": ["휴학 신청", "복학 신청"],
                    "contacts": ["02-2164-4288"],
                    "source_url": "https://www.catholic.ac.kr/ko/support/academic_contact_information.do",
                    "source_tag": "cuk_academic_support_guides",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            ],
        )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-18T10:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="AG001",
            normalized_expected=[
                {
                    "title": "휴·복학",
                    "summary": "휴·복학 관련 업무",
                    "contacts": ["02-2164-4288"],
                }
            ],
            truth_source="database_snapshot",
            captured_at="2026-03-18T10:10:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_uses_database_snapshot_for_dormitory_guides(app_env: str) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "DG001",
            "domain": "dormitory_guides",
            "style": "normal",
            "user_utterance": "기숙사 최신 공지 알려줘",
            "api_request": {
                "path": "/dormitory-guides",
                "params": {"topic": "latest_notices", "limit": 3},
            },
            "expected_mcp_flow": "tool_list_dormitory_guides",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "dormitory_guides_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    init_db()
    with connection() as conn:
        repo.replace_dormitory_guides(
            conn,
            [
                {
                    "topic": "latest_notices",
                    "title": "일반공지(K관/A관)",
                    "summary": "홈 최신 공지",
                    "steps": ["[K관, A관] 3월 청소점호 안내"],
                    "links": [
                        {
                            "label": "공지 보기",
                            "url": "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do?mode=view&articleNo=269375",
                        }
                    ],
                    "source_url": "https://dorm.catholic.ac.kr/",
                    "source_tag": "cuk_dormitory_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-20T10:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="DG001",
            normalized_expected=[
                {
                    "topic": "latest_notices",
                    "title": "일반공지(K관/A관)",
                    "summary": "홈 최신 공지",
                }
            ],
            truth_source="database_snapshot",
            captured_at="2026-03-20T10:10:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_uses_database_snapshot_for_student_exchange_guides(
    app_env: str,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "SEX001",
            "domain": "student_exchange_guides",
            "style": "normal",
            "user_utterance": "교류대학 현황 알려줘",
            "api_request": {
                "path": "/student-exchange-guides",
                "params": {"topic": "domestic_partner_universities", "limit": 3},
            },
            "expected_mcp_flow": "tool_list_student_exchange_guides",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "student_exchange_guides_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    init_db()
    with connection() as conn:
        repo.replace_student_exchange_guides(
            conn,
            [
                {
                    "topic": "domestic_partner_universities",
                    "title": "교류대학 현황",
                    "summary": "국내 교류대학 현황",
                    "steps": ["교류대학 목록"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/support/exchange_domestic2.do",
                    "source_tag": "cuk_student_exchange_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-20T10:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="SEX001",
            normalized_expected=[
                {
                    "topic": "domestic_partner_universities",
                    "title": "교류대학 현황",
                    "summary": "국내 교류대학 현황",
                }
            ],
            truth_source="database_snapshot",
            captured_at="2026-03-20T10:10:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_uses_database_snapshot_for_student_exchange_partners(
    app_env: str,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "SEP001",
            "domain": "student_exchange_partners",
            "style": "normal",
            "user_utterance": "네덜란드 교류대학 알려줘",
            "api_request": {
                "path": "/student-exchange-partners",
                "params": {"query": "네덜란드", "limit": 3},
            },
            "expected_mcp_flow": "tool_search_student_exchange_partners",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "student_exchange_partners_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    init_db()
    with connection() as conn:
        repo.replace_student_exchange_partners(
            conn,
            [
                {
                    "partner_code": "00122",
                    "university_name": "Utrecht University",
                    "country_ko": "네덜란드",
                    "country_en": "NETHERLANDS",
                    "continent": "EUROPE",
                    "location": None,
                    "agreement_date": None,
                    "homepage_url": "https://www.uu.nl",
                    "source_url": "https://www.catholic.ac.kr/ko/support/exchange_oversea1.do",
                    "source_tag": "cuk_student_exchange_partners",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                },
                {
                    "partner_code": "00004",
                    "university_name": "National Central University",
                    "country_ko": "대만",
                    "country_en": "TAIWAN, PROVINCE OF CHINA",
                    "continent": "ASIA",
                    "location": "Taoyuan",
                    "agreement_date": "2008-07-23",
                    "homepage_url": "http://www.ncu.edu.tw",
                    "source_url": "https://www.catholic.ac.kr/ko/support/exchange_oversea1.do",
                    "source_tag": "cuk_student_exchange_partners",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                },
            ],
        )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-20T10:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="SEP001",
            normalized_expected=[
                {
                    "partner_code": "00122",
                    "university_name": "Utrecht University",
                    "country_ko": "네덜란드",
                    "country_en": "NETHERLANDS",
                    "continent": "EUROPE",
                    "location": None,
                    "agreement_date": None,
                    "homepage_url": "https://www.uu.nl",
                }
            ],
            truth_source="database_snapshot",
            captured_at="2026-03-20T10:10:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_prefers_official_source_for_notices_even_with_database(
    app_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "NT001",
            "domain": "notices",
            "style": "normal",
            "user_utterance": "학사 공지 알려줘",
            "api_request": {
                "path": "/notices",
                "params": {"category": "academic", "limit": 3},
            },
            "expected_mcp_flow": "tool_list_latest_notices",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "notices_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    monkeypatch.setattr(
        qa_eval,
        "_payload_from_db",
        lambda *_args, **_kwargs: pytest.fail("notices truth should not use database snapshot"),
    )
    monkeypatch.setattr(
        qa_eval,
        "_payload_from_sources",
        lambda *_args, **_kwargs: [
            {
                "title": "학사 공지 1",
                "category": "academic",
                "published_at": "2026-03-19",
            },
            {
                "title": "학사 공지 2",
                "category": "academic",
                "published_at": "2026-03-18",
            },
        ],
    )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-19T10:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="NT001",
            normalized_expected=[
                {"title": "학사 공지 1", "category": "academic", "published_at": "2026-03-19"},
                {"title": "학사 공지 2", "category": "academic", "published_at": "2026-03-18"},
            ],
            truth_source="official_source",
            captured_at="2026-03-19T10:10:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_marks_watch_only_without_expected() -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "CW001",
            "domain": "courses",
            "style": "normal",
            "user_utterance": "CSE301 과목 뭐야",
            "api_request": {
                "path": "/courses",
                "params": {"query": "CSE301", "year": 2026, "semester": 1},
            },
            "expected_mcp_flow": "tool_search_courses",
            "truth_mode": "watch_only",
            "pass_rule": {"summary_kind": "courses_top5"},
            "watch_policy": "course_source_gap",
            "notes": "",
        }
    )

    truth_rows = build_truth_rows([row], database_url=None, captured_at="2026-03-18T10:10:00+09:00")

    assert truth_rows[0].normalized_expected is None
    assert truth_rows[0].stability == "watch_only"
    assert truth_rows[0].truth_source == "watchlist"


def test_build_truth_rows_builds_facility_host_place_canary_from_sources_without_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PLF001",
            "domain": "place",
            "style": "normal",
            "user_utterance": "복사실이 어디야?",
            "api_request": {"path": "/places", "params": {"query": "복사실이 어디야?", "limit": 5}},
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "places_top1_facility_host"},
            "watch_policy": "facility_search",
            "notes": "",
        }
    )

    monkeypatch.setattr(
        qa_eval.CampusMapSource,
        "fetch_place_list",
        lambda self: "<places></places>",
    )
    monkeypatch.setattr(
        qa_eval.CampusMapSource,
        "parse_place_list",
        lambda self, _html, *, fetched_at: [
            {
                "slug": "sophie-barat-hall",
                "name": "학생미래인재관",
                "category": "building",
                "aliases": ["학생회관", "학생센터", "학생식당"],
                "opening_hours": {},
                "source_tag": "cuk_campus_map",
                "last_synced_at": fetched_at,
            }
        ],
    )
    monkeypatch.setattr(
        qa_eval.CampusFacilitiesSource,
        "fetch",
        lambda self: "<facilities></facilities>",
    )
    monkeypatch.setattr(
        qa_eval.CampusFacilitiesSource,
        "parse",
        lambda self, _html, *, fetched_at: [
            {
                "facility_name": "복사실",
                "category": "복사실",
                "phone": "02-2164-4725",
                "location": "학생회관 1층",
                "hours_text": "평일 08:50~19:00",
                "source_tag": "cuk_facilities",
                "last_synced_at": fetched_at,
            }
        ],
    )

    truth_rows = build_truth_rows([row], database_url=None, captured_at="2026-03-18T10:10:00+09:00")

    assert truth_rows == [
        EvalTruthRow(
            id="PLF001",
            normalized_expected={
                "slug": "sophie-barat-hall",
                "name": "학생회관",
                "canonical_name": "학생미래인재관",
                "category": "building",
                "matched_facility": {
                    "name": "복사실",
                    "location_hint": "학생회관 1층",
                },
            },
            truth_source="official_source",
            captured_at="2026-03-18T10:10:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_uses_database_snapshot_for_composite_facility_host_place(
    app_env: str,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PLC0155",
            "domain": "place",
            "style": "composite",
            "user_utterance": "학생회관 1층 24시간 편의점 어디야?",
            "api_request": {
                "path": "/places",
                "params": {"query": "학생회관 1층 편의점", "limit": 5},
            },
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "places_top1_facility_host"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    init_db()
    with connection() as conn:
        repo.replace_places(
            conn,
            [
                {
                    "slug": "sophie-barat-hall",
                    "name": "학생미래인재관",
                    "category": "building",
                    "aliases": ["학생회관", "학생센터", "학생식당"],
                    "description": "",
                    "latitude": 37.486466,
                    "longitude": 126.801297,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-19T12:00:00+09:00",
                }
            ],
        )
        repo.replace_campus_facilities(
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
                    "last_synced_at": "2026-03-19T12:00:00+09:00",
                }
            ],
        )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-19T12:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="PLC0155",
            normalized_expected={
                "slug": "sophie-barat-hall",
                "name": "학생회관",
                "canonical_name": "학생미래인재관",
                "category": "building",
                "matched_facility": {
                    "name": "CU",
                    "location_hint": "학생회관 1층",
                },
            },
            truth_source="database_snapshot",
            captured_at="2026-03-19T12:10:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_prefers_official_source_for_place_alias_queries_even_with_database(
    app_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PLALIAS001",
            "domain": "place",
            "style": "alias",
            "user_utterance": "학생회관 어디야?",
            "api_request": {"path": "/places", "params": {"query": "학생회관", "limit": 5}},
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "exact_value",
            "pass_rule": {"summary_kind": "places_top1_alias_display"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    monkeypatch.setattr(
        qa_eval,
        "_payload_from_db",
        lambda *_args, **_kwargs: pytest.fail("place alias truth should not use database snapshot"),
    )
    monkeypatch.setattr(
        qa_eval,
        "_payload_from_sources",
        lambda *_args, **_kwargs: [
            {
                "slug": "sophie-barat-hall",
                "name": "학생회관",
                "canonical_name": "학생미래인재관",
                "category": "building",
                "aliases": ["학생회관", "학생센터", "학생식당"],
                "matched_facility": None,
            }
        ],
    )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-19T12:20:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="PLALIAS001",
            normalized_expected={
                "slug": "sophie-barat-hall",
                "name": "학생회관",
                "canonical_name": "학생미래인재관",
                "category": "building",
                "matched_facility": None,
            },
            truth_source="official_source",
            captured_at="2026-03-19T12:20:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_falls_back_to_official_source_for_facility_host_when_db_is_empty(
    app_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PLF002",
            "domain": "place",
            "style": "normal",
            "user_utterance": "우리은행 전화번호 알려줘",
            "api_request": {
                "path": "/places",
                "params": {"query": "우리은행 전화번호 알려줘", "limit": 5},
            },
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "places_top1_facility_host"},
            "watch_policy": "facility_search",
            "notes": "",
        }
    )

    monkeypatch.setattr(qa_eval, "_payload_from_db", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        qa_eval,
        "_payload_from_sources",
        lambda *_args, **_kwargs: [
            {
                "slug": "sophie-barat-hall",
                "name": "학생회관",
                "canonical_name": "학생미래인재관",
                "category": "building",
                "matched_facility": {
                    "name": "우리은행",
                    "location_hint": "학생회관 1층",
                },
            }
        ],
    )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-19T12:30:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="PLF002",
            normalized_expected={
                "slug": "sophie-barat-hall",
                "name": "학생회관",
                "canonical_name": "학생미래인재관",
                "category": "building",
                "matched_facility": {
                    "name": "우리은행",
                    "location_hint": "학생회관 1층",
                },
            },
            truth_source="official_source",
            captured_at="2026-03-19T12:30:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_uses_official_source_for_place_query_without_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PL001",
            "domain": "place",
            "style": "normal",
            "user_utterance": "중앙도서관 위치 알려줘",
            "api_request": {"path": "/places", "params": {"query": "중앙도서관", "limit": 3}},
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "exact_value",
            "pass_rule": {"summary_kind": "places_top3"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    monkeypatch.setattr(
        qa_eval.CampusMapSource,
        "fetch_place_list",
        lambda self: "<places></places>",
    )
    monkeypatch.setattr(
        qa_eval.CampusMapSource,
        "parse_place_list",
        lambda self, _html, *, fetched_at: [
            {
                "slug": "central-library",
                "name": "베리타스관",
                "category": "library",
                "aliases": ["중앙도서관", "중도"],
                "opening_hours": {},
                "source_tag": "cuk_campus_map",
                "last_synced_at": fetched_at,
            }
        ],
    )

    truth_rows = build_truth_rows([row], database_url=None, captured_at="2026-03-19T10:00:00+09:00")

    assert truth_rows == [
        EvalTruthRow(
            id="PL001",
            normalized_expected=[
                {
                    "slug": "central-library",
                    "name": "중앙도서관",
                    "category": "library",
                }
            ],
            truth_source="official_source",
            captured_at="2026-03-19T10:00:00+09:00",
            stability="stable",
        )
    ]


def test_build_truth_rows_falls_back_to_official_source_for_unsupported_db_path(
    app_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "RST001",
            "domain": "restaurants",
            "style": "normal",
            "user_utterance": "중앙도서관 근처 한식집 찾아줘",
            "api_request": {
                "path": "/restaurants/nearby",
                "params": {"origin": "central-library", "limit": 3},
            },
            "expected_mcp_flow": "tool_find_nearby_restaurants",
            "truth_mode": "invariant_only",
            "pass_rule": {
                "summary_kind": "restaurants_nearby",
                "allow_empty": True,
                "required_fields": ["name", "origin"],
            },
            "watch_policy": "none",
            "notes": "",
        }
    )

    monkeypatch.setattr(
        qa_eval,
        "_payload_from_sources",
        lambda *_args, **_kwargs: [
            {
                "name": "학생식당 옆 한식집",
                "origin": "central-library",
                "category": "korean",
                "open_now": True,
            }
        ],
    )

    truth_rows = build_truth_rows(
        [row],
        database_url=app_env,
        captured_at="2026-03-19T10:30:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="RST001",
            normalized_expected=[
                {
                    "name": "학생식당 옆 한식집",
                    "origin": "central-library",
                    "category": "korean",
                    "open_now": True,
                }
            ],
            truth_source="official_source",
            captured_at="2026-03-19T10:30:00+09:00",
            stability="stable",
        )
    ]


def test_payload_from_sources_prioritizes_songsim_academic_calendar_events() -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "AC001",
            "domain": "academic_calendar",
            "style": "normal",
            "user_utterance": "4월 학사일정 보여줘",
            "api_request": {
                "path": "/academic-calendar",
                "params": {"academic_year": 2026, "month": 4, "limit": 5},
            },
            "expected_mcp_flow": "tool_list_academic_calendar",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "academic_calendar_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    start_date, end_date = qa_eval._current_academic_year_bounds()
    source_cache = {
        f"academic_calendar:{start_date}:{end_date}": [
            {
                "academic_year": 2026,
                "title": "성신-only 일정",
                "start_date": "2026-04-02",
                "end_date": "2026-04-02",
                "campuses": ["성신"],
            },
            {
                "academic_year": 2026,
                "title": "성심 일정",
                "start_date": "2026-04-10",
                "end_date": "2026-04-10",
                "campuses": ["성심"],
            },
            {
                "academic_year": 2026,
                "title": "공통 일정",
                "start_date": "2026-04-05",
                "end_date": "2026-04-05",
                "campuses": ["성심", "성의", "성신"],
            },
        ]
    }

    payload = qa_eval._payload_from_sources(
        row,
        captured_at="2026-03-18T10:10:00+09:00",
        source_cache=source_cache,
    )
    summary = qa_eval._normalize_truth_payload(row, payload)

    assert summary == [
        {
            "title": "공통 일정",
            "start_date": "2026-04-05",
            "end_date": "2026-04-05",
            "campuses": ["성심", "성의", "성신"],
        },
        {
            "title": "성심 일정",
            "start_date": "2026-04-10",
            "end_date": "2026-04-10",
            "campuses": ["성심"],
        },
        {
            "title": "성신-only 일정",
            "start_date": "2026-04-02",
            "end_date": "2026-04-02",
            "campuses": ["성신"],
        },
    ]


def test_payload_from_sources_normalizes_notice_public_category_and_sorting() -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "NT001",
            "domain": "notices",
            "style": "normal",
            "user_utterance": "장학 공지 알려줘",
            "api_request": {
                "path": "/notices",
                "params": {"category": "scholarship", "limit": 3},
            },
            "expected_mcp_flow": "tool_list_latest_notices",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "notices_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    source_cache = {
        "notices_latest_30": [
            {
                "article_no": "101",
                "title": "older scholarship",
                "published_at": "2026-03-10",
                "summary": "",
                "labels": ["장학"],
                "raw_category": "scholarship",
                "category": "scholarship",
                "source_url": "https://example.com/101",
            },
            {
                "article_no": "103",
                "title": "newer scholarship",
                "published_at": "2026-03-17",
                "summary": "",
                "labels": ["장학"],
                "raw_category": "scholarship",
                "category": "scholarship",
                "source_url": "https://example.com/103",
            },
            {
                "article_no": "102",
                "title": "place-like notice",
                "published_at": "2026-03-16",
                "summary": "",
                "labels": ["일반"],
                "raw_category": "place",
                "category": "general",
                "source_url": "https://example.com/102",
            },
            {
                "article_no": "104",
                "title": "second scholarship",
                "published_at": "2026-03-17",
                "summary": "",
                "labels": ["장학"],
                "raw_category": "scholarship",
                "category": "scholarship",
                "source_url": "https://example.com/104",
            },
        ]
    }

    scholarship_payload = qa_eval._payload_from_sources(
        row,
        captured_at="2026-03-18T10:10:00+09:00",
        source_cache=source_cache,
    )
    scholarship_summary = qa_eval._normalize_truth_payload(row, scholarship_payload)

    assert scholarship_summary == [
        {"title": "second scholarship", "category": "scholarship", "published_at": "2026-03-17"},
        {"title": "newer scholarship", "category": "scholarship", "published_at": "2026-03-17"},
        {"title": "older scholarship", "category": "scholarship", "published_at": "2026-03-10"},
    ]

    place_row = EvalCorpusRow.model_validate(
        {
            "id": "NT002",
            "domain": "notices",
            "style": "normal",
            "user_utterance": "place 공지 알려줘",
            "api_request": {
                "path": "/notices",
                "params": {"category": "place", "limit": 1},
            },
            "expected_mcp_flow": "tool_list_latest_notices",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "notices_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    place_payload = qa_eval._payload_from_sources(
        place_row,
        captured_at="2026-03-18T10:10:00+09:00",
        source_cache=source_cache,
    )
    place_summary = qa_eval._normalize_truth_payload(place_row, place_payload)

    assert place_summary == [
        {"title": "place-like notice", "category": "general", "published_at": "2026-03-16"}
    ]


def test_summarize_payload_places_alias_display_ignores_aliases() -> None:
    payload = [
        {
            "slug": "student-center",
            "name": "학생회관",
            "canonical_name": "학생미래인재관",
            "category": "facility",
            "aliases": ["학생회관", "student center"],
            "matched_facility": None,
        }
    ]
    summary = qa_eval._summarize_payload(payload, summary_kind="places_top1_alias_display")

    assert summary == {
        "slug": "student-center",
        "name": "학생회관",
        "canonical_name": "학생미래인재관",
        "category": "facility",
        "matched_facility": None,
    }


def test_run_row_evaluation_supports_exact_set_contains_invariant_and_watch() -> None:
    exact_row = EvalCorpusRow.model_validate(
        {
            "id": "PL001",
            "domain": "place",
            "style": "normal",
            "user_utterance": "중앙도서관 위치 알려줘",
            "api_request": {"path": "/places", "params": {"query": "중앙도서관"}},
            "expected_mcp_flow": "prompt_find_place -> tool_search_places -> tool_get_place",
            "truth_mode": "exact_value",
            "pass_rule": {"summary_kind": "places_top3"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    contains_row = EvalCorpusRow.model_validate(
        {
            "id": "NT001",
            "domain": "notices",
            "style": "normal",
            "user_utterance": "최신 장학 공지 3개 보여줘",
            "api_request": {"path": "/notices", "params": {"category": "scholarship", "limit": 3}},
            "expected_mcp_flow": "prompt_latest_notices -> tool_list_latest_notices",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "notices_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    invariant_row = EvalCorpusRow.model_validate(
        {
            "id": "RS001",
            "domain": "restaurants",
            "style": "composite",
            "user_utterance": "중앙도서관 근처 1만원 이하 밥집",
            "api_request": {
                "path": "/restaurants/nearby",
                "params": {"origin": "중앙도서관", "budget_max": 10000, "limit": 2},
            },
            "expected_mcp_flow": "prompt_find_nearby_restaurants -> tool_find_nearby_restaurants",
            "truth_mode": "invariant_only",
            "pass_rule": {
                "summary_kind": "restaurants_nearby",
                "allow_empty": True,
                "required_fields": ["name", "origin"],
            },
            "watch_policy": "none",
            "notes": "",
        }
    )
    watch_row = EvalCorpusRow.model_validate(
        {
            "id": "CW001",
            "domain": "courses",
            "style": "normal",
            "user_utterance": "CSE301 과목 뭐야",
            "api_request": {
                "path": "/courses",
                "params": {"query": "CSE301", "year": 2026, "semester": 1},
            },
            "expected_mcp_flow": "tool_search_courses",
            "truth_mode": "watch_only",
            "pass_rule": {"summary_kind": "courses_top5"},
            "watch_policy": "course_source_gap",
            "notes": "",
        }
    )

    exact_truth = EvalTruthRow(
        id="PL001",
        normalized_expected=[
            {"slug": "central-library", "name": "베리타스관", "category": "library"}
        ],
        truth_source="database_snapshot",
        captured_at="2026-03-18T10:10:00+09:00",
        stability="stable",
    )
    contains_truth = EvalTruthRow(
        id="NT001",
        normalized_expected=[{"title": "장학 공지", "category": "scholarship"}],
        truth_source="database_snapshot",
        captured_at="2026-03-18T10:10:00+09:00",
        stability="stable",
    )
    watch_truth = EvalTruthRow(
        id="CW001",
        normalized_expected=None,
        truth_source="watchlist",
        captured_at="2026-03-18T10:10:00+09:00",
        stability="watch_only",
    )

    exact_result = run_row_evaluation(
        exact_row,
        actual_payload=[{"slug": "central-library", "name": "베리타스관", "category": "library"}],
        truth=exact_truth,
        checked_at="2026-03-18T10:20:00+09:00",
    )
    contains_result = run_row_evaluation(
        contains_row,
        actual_payload=[
            {"title": "장학 공지", "category": "scholarship"},
            {"title": "장학 공지 2", "category": "scholarship"},
        ],
        truth=contains_truth,
        checked_at="2026-03-18T10:20:00+09:00",
    )
    invariant_result = run_row_evaluation(
        invariant_row,
        actual_payload=[{"name": "꼬밥", "origin": "central-library"}],
        truth=None,
        checked_at="2026-03-18T10:20:00+09:00",
    )
    watch_result = run_row_evaluation(
        watch_row,
        actual_payload=[
            {
                "code": "CSE300",
                "title": "데이터베이스활용",
                "professor": "김가톨",
                "year": 2026,
                "semester": 1,
            }
        ],
        truth=watch_truth,
        checked_at="2026-03-18T10:20:00+09:00",
    )

    assert exact_result.verdict == "pass"
    assert contains_result.verdict == "pass"
    assert invariant_result.verdict == "pass"
    assert watch_result.verdict == "watch"
    assert watch_result.actual_summary == [
        {
            "code": "CSE300",
            "title": "데이터베이스활용",
            "professor": "김가톨",
            "year": 2026,
            "semester": 1,
            "period_start": None,
        }
    ]


def test_run_row_evaluation_supports_place_top1_facility_host_summary() -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PLF001",
            "domain": "place",
            "style": "normal",
            "user_utterance": "트러스트짐 어디야?",
            "api_request": {
                "path": "/places",
                "params": {"query": "트러스트짐 어디야?", "limit": 5},
            },
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "places_top1_facility_host"},
            "watch_policy": "facility_search",
            "notes": "",
        }
    )
    truth = EvalTruthRow(
        id="PLF001",
        normalized_expected={
            "slug": "kim-sou-hwan-hall",
            "name": "K관",
            "canonical_name": "김수환관",
            "matched_facility": {
                "name": "트러스트짐",
                "location_hint": "K관 1층",
            },
        },
        truth_source="database_snapshot",
        captured_at="2026-03-18T10:10:00+09:00",
        stability="stable",
    )

    result = run_row_evaluation(
        row,
        actual_payload=[
            {
                "slug": "kim-sou-hwan-hall",
                "name": "K관",
                "canonical_name": "김수환관",
                "category": "building",
                "matched_facility": {
                    "name": "트러스트짐",
                    "location_hint": "K관 1층",
                    "opening_hours": "평일 07:00~22:30",
                },
            }
        ],
        truth=truth,
        checked_at="2026-03-18T10:20:00+09:00",
    )

    assert result.verdict == "pass"
    assert result.actual_summary == {
        "slug": "kim-sou-hwan-hall",
        "name": "K관",
        "canonical_name": "김수환관",
        "category": "building",
        "matched_facility": {
            "name": "트러스트짐",
            "location_hint": "K관 1층",
        },
    }


def test_render_validation_report_separates_watchlist() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "PL001",
                "domain": "place",
                "style": "normal",
                "user_utterance": "중앙도서관 위치 알려줘",
                "api_request": {"path": "/places", "params": {"query": "중앙도서관"}},
                "expected_mcp_flow": "prompt_find_place -> tool_search_places -> tool_get_place",
                "truth_mode": "exact_value",
                "pass_rule": {"summary_kind": "places_top3"},
                "watch_policy": "none",
                "notes": "",
            }
        ),
        EvalCorpusRow.model_validate(
            {
                "id": "CW001",
                "domain": "courses",
                "style": "normal",
                "user_utterance": "CSE301 과목 뭐야",
                "api_request": {
                    "path": "/courses",
                    "params": {"query": "CSE301", "year": 2026, "semester": 1},
                },
                "expected_mcp_flow": "tool_search_courses",
                "truth_mode": "watch_only",
                "pass_rule": {"summary_kind": "courses_top5"},
                "watch_policy": "course_source_gap",
                "notes": "source-backed direct hit 미확인",
            }
        ),
    ]
    results = [
        {
            "id": "PL001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [{"slug": "central-library"}],
            "comparison": "exact_match",
            "truth_source": "database_snapshot",
            "checked_at": "2026-03-18T10:20:00+09:00",
        },
        {
            "id": "CW001",
            "status": "completed",
            "verdict": "watch",
            "actual_summary": [{"code": "CSE300", "title": "데이터베이스활용"}],
            "comparison": "watch_only",
            "truth_source": "watchlist",
            "checked_at": "2026-03-18T10:20:00+09:00",
        },
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-18T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "hard fail 0" in report.lower()
    assert "corpus_size: `1`" in report
    assert "executed: `2`" in report
    assert "Watchlist (hard fail 제외)" in report
    assert "CW001" in report
    assert "course_source_gap" in report
    assert "source-backed direct hit 미확인" in report
    assert "데이터베이스활용" in report


def test_render_validation_report_includes_registration_guides_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "RG001",
                "domain": "registration_guides",
                "style": "normal",
                "user_utterance": "등록금 반환기준 알려줘",
                "api_request": {
                    "path": "/registration-guides",
                    "params": {"topic": "payment_and_return", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_registration_guides",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "registration_guides_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "RG001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [{"title": "등록금 반환기준"}],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-19T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-19T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| registration_guides | 1 | 1 |") == 2


def test_render_validation_report_includes_class_guides_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "CG001",
                "domain": "class_guides",
                "style": "normal",
                "user_utterance": "수업평가 기간 알려줘",
                "api_request": {
                    "path": "/class-guides",
                    "params": {"topic": "course_evaluation", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_class_guides",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "class_guides_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "CG001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [{"title": "수업평가 기간"}],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-19T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-19T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| class_guides | 1 | 1 |") == 2


def test_render_validation_report_includes_seasonal_semester_guides_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "SG001",
                "domain": "seasonal_semester_guides",
                "style": "normal",
                "user_utterance": "계절학기 신청 시기 알려줘",
                "api_request": {
                    "path": "/seasonal-semester-guides",
                    "params": {"topic": "seasonal_semester", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_seasonal_semester_guides",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "seasonal_semester_guides_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "SG001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [{"title": "신청 시기"}],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-19T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-19T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| seasonal_semester_guides | 1 | 1 |") == 2


def test_render_validation_report_includes_academic_milestone_guides_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "MG001",
                "domain": "academic_milestone_guides",
                "style": "normal",
                "user_utterance": "성적평가 방법 알려줘",
                "api_request": {
                    "path": "/academic-milestone-guides",
                    "params": {"topic": "grade_evaluation", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_academic_milestone_guides",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "academic_milestone_guides_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "MG001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [{"title": "성적평가 방법"}],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-20T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-20T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| academic_milestone_guides | 1 | 1 |") == 2


def test_render_validation_report_includes_student_activity_guides_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "SAG001",
                "domain": "student_activity_guides",
                "style": "normal",
                "user_utterance": "총학생회 안내해줘",
                "api_request": {
                    "path": "/student-activity-guides",
                    "params": {"topic": "student_government", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_student_activity_guides",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "student_activity_guides_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "SAG001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [
                {
                    "topic": "student_government",
                    "title": "총학생회",
                    "summary": "학생 자치 대표 기구",
                }
            ],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-21T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-21T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| student_activity_guides | 1 | 1 |") == 2


def test_render_validation_report_includes_phone_book_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "PB001",
                "domain": "phone_book",
                "style": "normal",
                "user_utterance": "보건실 전화번호 알려줘",
                "api_request": {
                    "path": "/phone-book",
                    "params": {"query": "보건실", "limit": 5},
                },
                "expected_mcp_flow": "tool_search_phone_book",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "phone_book_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "PB001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [{"department": "보건실", "phone": "4126"}],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-20T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-20T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| phone_book | 1 | 1 |") == 2


def test_render_validation_report_includes_affiliated_notices_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "AN001",
                "domain": "affiliated_notices",
                "style": "normal",
                "user_utterance": "국제학부 최신 공지 알려줘",
                "api_request": {
                    "path": "/affiliated-notices",
                    "params": {"topic": "international_studies", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_affiliated_notices",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "affiliated_notices_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "AN001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [
                {
                    "topic": "international_studies",
                    "title": "국제학부 공지",
                    "published_at": "2026-03-20",
                }
            ],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-20T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-20T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| affiliated_notices | 1 | 1 |") == 2


def test_render_validation_report_includes_campus_life_notices_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "CLN001",
                "domain": "campus_life_notices",
                "style": "normal",
                "user_utterance": "외부기관공지 알려줘",
                "api_request": {
                    "path": "/campus-life-notices",
                    "params": {"topic": "outside_agencies", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_campus_life_notices",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "campus_life_notices_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "CLN001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [
                {
                    "topic": "outside_agencies",
                    "title": "대외 프로그램 공지",
                    "published_at": "2026-03-20",
                }
            ],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-20T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-20T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| campus_life_notices | 1 | 1 |") == 2


def test_render_validation_report_includes_campus_life_notices_events_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "CLN002",
                "domain": "campus_life_notices",
                "style": "normal",
                "user_utterance": "행사안내 알려줘",
                "api_request": {
                    "path": "/campus-life-notices",
                    "params": {"topic": "events", "limit": 5},
                },
                "expected_mcp_flow": "tool_list_campus_life_notices",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "campus_life_notices_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "CLN002",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [
                {
                    "topic": "events",
                    "title": "성심 오케스트라 연주회",
                    "published_at": "2025-11-28",
                }
            ],
            "comparison": "set_contains",
            "truth_source": "official_source",
            "checked_at": "2026-03-20T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-20T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| campus_life_notices | 1 | 1 |") == 2


def test_build_truth_rows_dedupes_affiliated_notices_by_topic_first_seen(app_env, monkeypatch):
    row_international = EvalCorpusRow.model_validate(
        {
            "id": "AN101",
            "domain": "affiliated_notices",
            "style": "normal",
            "user_utterance": "국제학부 최신 공지 알려줘",
            "api_request": {
                "path": "/affiliated-notices",
                "params": {"topic": "international_studies", "limit": 5},
            },
            "expected_mcp_flow": "tool_list_affiliated_notices",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "affiliated_notices_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )
    row_dorm = EvalCorpusRow.model_validate(
        {
            "id": "AN102",
            "domain": "affiliated_notices",
            "style": "normal",
            "user_utterance": "기숙사 일반공지 알려줘",
            "api_request": {
                "path": "/affiliated-notices",
                "params": {"topic": "dorm_k_a_general", "limit": 5},
            },
            "expected_mcp_flow": "tool_list_affiliated_notices",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "affiliated_notices_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    class FakeNoticeSource:
        def __init__(self, url: str):
            self.url = url

        def fetch_list(self, offset: int = 0, limit: int = 10):
            return self.url

        def parse_list(self, _html: str):
            rows_by_url = {
                "https://is.catholic.ac.kr/is/community/notice.do": [
                    {
                        "article_no": "1",
                        "title": "중복 공지",
                        "published_at": "2026-03-19",
                        "summary": "",
                        "source_url": f"{self.url}?articleNo=1",
                        "board_category": "",
                    },
                    {
                        "article_no": "1",
                        "title": "중복 공지",
                        "published_at": "2026-03-19",
                        "summary": "",
                        "source_url": f"{self.url}?articleNo=1",
                        "board_category": "",
                    },
                ],
                "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do": [
                    {
                        "article_no": "10",
                        "title": "중복 공지",
                        "published_at": "2026-03-17",
                        "summary": "",
                        "source_url": f"{self.url}?articleNo=10",
                        "board_category": "",
                    },
                ],
                "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice1.do": [],
                "https://dorm.catholic.ac.kr/dormitory/board/comm_notice3.do": [],
                "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice.do": [],
            }
            return rows_by_url[self.url]

        def fetch_detail(self, article_no: str, offset: int = 0, limit: int = 10):
            return article_no

        def parse_detail(
            self,
            article_no: str,
            *,
            default_title: str = "",
            default_category: str = "",
        ):
            detail_by_url = {
                "https://is.catholic.ac.kr/is/community/notice.do": {
                    "1": {
                        "title": default_title,
                        "published_at": "2026-03-19",
                        "summary": "국제학부 첫 번째 공지",
                    },
                },
                "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do": {
                    "10": {
                        "title": default_title,
                        "published_at": "2026-03-17",
                        "summary": "기숙사 첫 번째 공지",
                    },
                },
            }
            return detail_by_url[self.url][article_no]

    monkeypatch.setattr(qa_eval, "NoticeSource", FakeNoticeSource)

    truth_rows = build_truth_rows(
        [row_international, row_dorm],
        database_url=None,
        captured_at="2026-03-20T10:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="AN101",
            normalized_expected=[
                {
                    "topic": "international_studies",
                    "title": "중복 공지",
                    "published_at": "2026-03-19",
                }
            ],
            truth_source="official_source",
            captured_at="2026-03-20T10:10:00+09:00",
            stability="stable",
        ),
        EvalTruthRow(
            id="AN102",
            normalized_expected=[
                {
                    "topic": "dorm_k_a_general",
                    "title": "중복 공지",
                    "published_at": "2026-03-17",
                }
            ],
            truth_source="official_source",
            captured_at="2026-03-20T10:10:00+09:00",
            stability="stable",
        ),
    ]


def test_build_truth_rows_uses_student_activity_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "SAG101",
            "domain": "student_activity_guides",
            "style": "normal",
            "user_utterance": "총학생회 안내해줘",
            "api_request": {
                "path": "/student-activity-guides",
                "params": {"topic": "student_government", "limit": 5},
            },
            "expected_mcp_flow": "tool_list_student_activity_guides",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "student_activity_guides_top5"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    class FakeStudentGovernmentSource:
        def __init__(self, url: str):
            self.url = url

        def fetch(self) -> str:
            return "ignored"

        def parse(self, _html: str, *, fetched_at: str) -> list[dict[str, object]]:
            return [
                {
                    "topic": "student_government",
                    "title": "총학생회",
                    "summary": "학생 자치 대표 기구",
                    "steps": ["안내"],
                    "links": [],
                    "source_url": self.url,
                    "source_tag": "cuk_student_activity_guides",
                    "last_synced_at": fetched_at,
                }
            ]

    class EmptySource:
        def __init__(self, url: str):
            self.url = url

        def fetch(self) -> str:
            return "ignored"

        def parse(self, _html: str, *, fetched_at: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(qa_eval, "StudentGovernmentGuideSource", FakeStudentGovernmentSource)
    monkeypatch.setattr(qa_eval, "CampusMediaGuideSource", EmptySource)
    monkeypatch.setattr(qa_eval, "SocialVolunteeringGuideSource", EmptySource)
    monkeypatch.setattr(qa_eval, "RotcGuideSource", EmptySource)

    truth_rows = build_truth_rows(
        [row],
        database_url=None,
        captured_at="2026-03-21T10:10:00+09:00",
    )

    assert truth_rows == [
        EvalTruthRow(
            id="SAG101",
            normalized_expected=[
                {
                    "topic": "student_government",
                    "title": "총학생회",
                    "summary": "학생 자치 대표 기구",
                }
            ],
            truth_source="official_source",
            captured_at="2026-03-21T10:10:00+09:00",
            stability="stable",
        )
    ]


def test_render_validation_report_includes_student_exchange_partners_coverage() -> None:
    rows = [
        EvalCorpusRow.model_validate(
            {
                "id": "SEP001",
                "domain": "student_exchange_partners",
                "style": "normal",
                "user_utterance": "네덜란드 협정대학 알려줘",
                "api_request": {
                    "path": "/student-exchange-partners",
                    "params": {"query": "네덜란드", "limit": 5},
                },
                "expected_mcp_flow": "tool_search_student_exchange_partners",
                "truth_mode": "set_contains",
                "pass_rule": {"summary_kind": "student_exchange_partners_top5"},
                "watch_policy": "none",
                "notes": "",
            }
        )
    ]
    results = [
        {
            "id": "SEP001",
            "status": "completed",
            "verdict": "pass",
            "actual_summary": [
                {
                    "university_name": "Utrecht University",
                    "country_ko": "네덜란드",
                    "continent": "EUROPE",
                    "homepage_url": "http://www.uu.nl",
                }
            ],
            "comparison": "set_contains",
            "truth_source": "database_snapshot",
            "checked_at": "2026-03-20T10:20:00+09:00",
        }
    ]

    report = render_validation_report(
        rows=rows,
        results=results,
        checked_at="2026-03-20T10:20:00+09:00",
        base_url="https://songsim-public-api.onrender.com",
    )

    assert "Guide-Domain Coverage" in report
    assert report.count("| student_exchange_partners | 1 | 1 |") == 2


def test_run_evaluation_records_http_errors_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PL001",
            "domain": "place",
            "style": "normal",
            "user_utterance": "중앙도서관 위치 알려줘",
            "api_request": {"path": "/places", "params": {"query": "중앙도서관"}},
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "exact_value",
            "pass_rule": {"summary_kind": "places_top3"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    def _raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("boom")

    monkeypatch.setattr(qa_eval, "_load_actual_payload", _raise_timeout)

    results = run_evaluation(
        base_url="https://songsim-public-api.onrender.com",
        rows=[row],
        truth_rows=[],
        checked_at="2026-03-18T10:20:00+09:00",
    )

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].verdict == "fail"
    assert results[0].comparison == "http_error:ReadTimeout"


def test_load_actual_payload_retries_read_timeout_until_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = EvalCorpusRow.model_validate(
        {
            "id": "PL001",
            "domain": "place",
            "style": "normal",
            "user_utterance": "중앙도서관 위치 알려줘",
            "api_request": {"path": "/places", "params": {"query": "중앙도서관", "limit": 5}},
            "expected_mcp_flow": "tool_search_places -> tool_get_place",
            "truth_mode": "set_contains",
            "pass_rule": {"summary_kind": "places_top3"},
            "watch_policy": "none",
            "notes": "",
        }
    )

    calls = {"count": 0}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[str]]:
            return {"items": ["ok"]}

    def _fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.ReadTimeout("boom")
        return _Response()

    monkeypatch.setattr(qa_eval.httpx, "get", _fake_get)
    monkeypatch.setattr(qa_eval.time, "sleep", lambda *_args, **_kwargs: None)

    payload = qa_eval._load_actual_payload(
        "https://songsim-public-api.onrender.com",
        row,
    )

    assert payload == {"items": ["ok"]}
    assert calls["count"] == 3


def test_default_eval_assets_match_distribution_plan() -> None:
    rows = load_eval_rows(DEFAULT_CORPUS_PATH)
    watchlist_rows = load_eval_rows(DEFAULT_WATCHLIST_PATH)

    assert len(rows) == 1000
    assert len(watchlist_rows) == 5
    assert {row.domain for row in watchlist_rows} == {"courses"}
    assert {row.truth_mode for row in watchlist_rows} == {"watch_only"}
    assert {row.watch_policy for row in watchlist_rows} == {"course_source_gap"}
    assert len({row.id for row in rows}) == 1000
    assert len({row.user_utterance for row in rows}) == 1000
    assert {row.truth_mode for row in rows}.issubset(
        {"set_contains", "invariant_only", "exact_value"}
    )

    by_domain: dict[str, int] = {}
    by_style: dict[str, int] = {}
    by_truth_mode: dict[str, int] = {}
    for row in rows:
        by_domain[row.domain] = by_domain.get(row.domain, 0) + 1
        by_style[row.style] = by_style.get(row.style, 0) + 1
        by_truth_mode[row.truth_mode] = by_truth_mode.get(row.truth_mode, 0) + 1

    assert by_domain == DOMAIN_QUOTAS
    assert by_style == STYLE_QUOTAS
    assert by_truth_mode == TRUTH_MODE_QUOTAS

    coarse_counts: dict[str, dict[tuple[str | None, str | None, str], int]] = {}
    for row in rows:
        key = coarse_request_key_from_payload(
            {
                "path": row.api_request.path,
                "policy": row.api_request.policy,
                "params": row.api_request.params,
            },
            truth_mode=row.truth_mode,
        )
        domain_counts = coarse_counts.setdefault(row.domain, {})
        domain_counts[key] = domain_counts.get(key, 0) + 1

    for domain in COARSE_CAP_ENFORCED_DOMAINS:
        assert domain in coarse_counts
        assert max(coarse_counts[domain].values()) <= 4

    registration_rows = [row for row in rows if row.domain == "registration_guides"]

    assert len(registration_rows) == DOMAIN_QUOTAS["registration_guides"]
    assert {row.api_request.path for row in registration_rows} == {"/registration-guides"}
    assert {row.expected_mcp_flow for row in registration_rows} == {"tool_list_registration_guides"}
    assert {row.pass_rule["summary_kind"] for row in registration_rows} == {
        "registration_guides_top5"
    }
    assert {row.api_request.params["topic"] for row in registration_rows} == {
        "bill_lookup",
        "payment_and_return",
        "payment_by_student",
    }

    class_rows = [row for row in rows if row.domain == "class_guides"]

    assert len(class_rows) == DOMAIN_QUOTAS["class_guides"]
    assert {row.api_request.path for row in class_rows} == {"/class-guides"}
    assert {row.expected_mcp_flow for row in class_rows} == {"tool_list_class_guides"}
    assert {row.pass_rule["summary_kind"] for row in class_rows} == {"class_guides_top5"}
    assert {row.api_request.params["topic"] for row in class_rows} == {
        "registration_change",
        "retake",
        "course_evaluation",
        "excused_absence",
        "foreign_language_requirement",
    }

    seasonal_rows = [row for row in rows if row.domain == "seasonal_semester_guides"]

    assert len(seasonal_rows) == DOMAIN_QUOTAS["seasonal_semester_guides"]
    assert {row.api_request.path for row in seasonal_rows} == {"/seasonal-semester-guides"}
    assert {row.expected_mcp_flow for row in seasonal_rows} == {
        "tool_list_seasonal_semester_guides"
    }
    assert {row.pass_rule["summary_kind"] for row in seasonal_rows} == {
        "seasonal_semester_guides_top5"
    }
    assert {row.api_request.params["topic"] for row in seasonal_rows} == {"seasonal_semester"}

    milestone_rows = [row for row in rows if row.domain == "academic_milestone_guides"]

    assert len(milestone_rows) == DOMAIN_QUOTAS["academic_milestone_guides"]
    assert {row.api_request.path for row in milestone_rows} == {"/academic-milestone-guides"}
    assert {row.expected_mcp_flow for row in milestone_rows} == {
        "tool_list_academic_milestone_guides"
    }
    assert {row.pass_rule["summary_kind"] for row in milestone_rows} == {
        "academic_milestone_guides_top5"
    }
    assert {row.api_request.params["topic"] for row in milestone_rows} == {
        "grade_evaluation",
        "graduation_requirement",
    }

    exchange_rows = [row for row in rows if row.domain == "student_exchange_guides"]

    assert len(exchange_rows) == DOMAIN_QUOTAS["student_exchange_guides"]
    assert {row.api_request.path for row in exchange_rows} == {"/student-exchange-guides"}
    assert {row.expected_mcp_flow for row in exchange_rows} == {"tool_list_student_exchange_guides"}
    assert {row.pass_rule["summary_kind"] for row in exchange_rows} == {
        "student_exchange_guides_top5"
    }
    assert {row.api_request.params["topic"] for row in exchange_rows} == {
        "domestic_credit_exchange",
        "domestic_partner_universities",
        "exchange_student",
        "exchange_programs",
    }

    student_activity_rows = [row for row in rows if row.domain == "student_activity_guides"]

    assert len(student_activity_rows) == DOMAIN_QUOTAS["student_activity_guides"]
    assert {row.api_request.path for row in student_activity_rows} == {"/student-activity-guides"}
    assert {row.expected_mcp_flow for row in student_activity_rows} == {
        "tool_list_student_activity_guides"
    }
    assert {row.pass_rule["summary_kind"] for row in student_activity_rows} == {
        "student_activity_guides_top5"
    }
    assert {row.api_request.params["topic"] for row in student_activity_rows} == {
        "student_government",
        "campus_media",
        "social_volunteering",
        "rotc",
    }

    service_policy_rows = [row for row in rows if row.domain == "service_policy_guides"]

    assert len(service_policy_rows) == DOMAIN_QUOTAS["service_policy_guides"]
    assert {row.api_request.path for row in service_policy_rows} == {"/service-policy-guides"}
    assert {row.expected_mcp_flow for row in service_policy_rows} == {
        "tool_list_service_policy_guides"
    }
    assert {row.pass_rule["summary_kind"] for row in service_policy_rows} == {
        "service_policy_guides_top5"
    }
    assert {row.api_request.params["topic"] for row in service_policy_rows} == {
        "bidding",
        "job_posting",
        "privacy_policy",
        "cctv_policy",
        "anti_graft",
    }

    partner_rows = [row for row in rows if row.domain == "student_exchange_partners"]

    assert len(partner_rows) == DOMAIN_QUOTAS["student_exchange_partners"]
    assert {row.api_request.path for row in partner_rows} == {"/student-exchange-partners"}
    assert {row.expected_mcp_flow for row in partner_rows} == {
        "tool_search_student_exchange_partners"
    }
    assert {row.pass_rule["summary_kind"] for row in partner_rows} == {
        "student_exchange_partners_top5"
    }
    partner_queries = {row.api_request.params["query"] for row in partner_rows}
    assert partner_queries == {
        "ASIA",
        "National Taiwan University",
        "Utrecht University",
        "네덜란드",
        "대만",
        "미국",
        "유럽",
        "일본",
    }

    phone_rows = [row for row in rows if row.domain == "phone_book"]

    assert len(phone_rows) == DOMAIN_QUOTAS["phone_book"]
    assert {row.api_request.path for row in phone_rows} == {"/phone-book"}
    assert {row.expected_mcp_flow for row in phone_rows} == {"tool_search_phone_book"}
    assert {row.pass_rule["summary_kind"] for row in phone_rows} == {"phone_book_top5"}

    affiliated_rows = [row for row in rows if row.domain == "affiliated_notices"]

    assert len(affiliated_rows) == DOMAIN_QUOTAS["affiliated_notices"]
    assert {row.api_request.path for row in affiliated_rows} == {"/affiliated-notices"}
    assert {row.expected_mcp_flow for row in affiliated_rows} == {"tool_list_affiliated_notices"}
    assert {row.pass_rule["summary_kind"] for row in affiliated_rows} == {"affiliated_notices_top5"}
    assert {row.api_request.params["topic"] for row in affiliated_rows} == {
        "international_studies",
        "dorm_k_a_general",
        "dorm_k_a_checkin_out",
        "dorm_francis_general",
        "dorm_francis_checkin_out",
    }

    campus_life_notice_rows = [row for row in rows if row.domain == "campus_life_notices"]

    assert len(campus_life_notice_rows) == DOMAIN_QUOTAS["campus_life_notices"]
    assert {row.api_request.path for row in campus_life_notice_rows} == {"/campus-life-notices"}
    assert {row.expected_mcp_flow for row in campus_life_notice_rows} == {
        "tool_list_campus_life_notices"
    }
    assert {row.pass_rule["summary_kind"] for row in campus_life_notice_rows} == {
        "campus_life_notices_top5"
    }
    assert {row.api_request.params["topic"] for row in campus_life_notice_rows} == {
        "outside_agencies",
        "events",
    }

    campus_life_support_rows = [row for row in rows if row.domain == "campus_life_support_guides"]

    assert len(campus_life_support_rows) == DOMAIN_QUOTAS["campus_life_support_guides"]
    assert {row.api_request.path for row in campus_life_support_rows} == {
        "/campus-life-support-guides"
    }
    assert {row.expected_mcp_flow for row in campus_life_support_rows} == {
        "tool_list_campus_life_support_guides"
    }
    assert {row.pass_rule["summary_kind"] for row in campus_life_support_rows} == {
        "campus_life_support_guides_top5"
    }
    assert {row.api_request.params["topic"] for row in campus_life_support_rows} == {
        "health_center",
        "lost_found",
        "parking",
        "facility_rental",
        "mobility_safety",
        "student_counseling",
        "disability_support",
        "student_reservist",
        "hospital_use",
        "career_counseling",
    }


def test_default_eval_corpus_snapshot_matches_builder() -> None:
    committed_rows = qa_eval._read_jsonl(DEFAULT_CORPUS_PATH)

    assert build_public_api_eval_corpus(seed_rows=committed_rows) == committed_rows
