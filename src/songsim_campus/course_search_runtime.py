from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from . import clock, repo
from .db import DBConnection
from .ingest.official_sources import CourseCatalogSource

COURSE_SOURCE_URL = "https://www.catholic.ac.kr/ko/support/subject.do"


def _now() -> datetime:
    return clock.now()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _coerce_datetime(value: datetime | None = None) -> datetime:
    return clock.coerce_datetime(value if value is not None else _now())


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def _normalized_query_variants(value: str | None) -> tuple[str | None, str | None]:
    cleaned = _normalize_optional_text(value)
    if cleaned is None:
        return None, None
    collapsed = _collapse_whitespace(cleaned)
    compacted = _compact_text(cleaned)
    return collapsed, compacted or None


def normalize_course_query_text(value: str | None) -> str | None:
    collapsed, _ = _normalized_query_variants(value)
    if collapsed is None:
        return None
    return collapsed.replace("데이타베이스", "데이터베이스")


def looks_like_course_code_query(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value) and re.search(r"\d", value))


def course_query_candidates(query: str | None) -> list[str]:
    collapsed_query = normalize_course_query_text(query)
    if collapsed_query is None:
        return [""]
    _, compact_query = _normalized_query_variants(collapsed_query)
    queries = [collapsed_query]
    if compact_query is not None and compact_query != queries[0]:
        queries.append(compact_query)
    if looks_like_course_code_query(collapsed_query):
        code_compact_query = re.sub(r"[\s\-_]+", "", collapsed_query)
        if code_compact_query and code_compact_query not in queries:
            queries.append(code_compact_query)
    return queries


def _matches_exact_text_candidate(
    text: str | None,
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> bool:
    cleaned = _normalize_optional_text(text)
    if cleaned is None:
        return False
    collapsed_text = _collapse_whitespace(cleaned).lower()
    if collapsed_text == collapsed_query.lower():
        return True
    if compact_query is None:
        return False
    return _compact_text(cleaned).lower() == compact_query.lower()


def _matches_partial_text_candidate(
    text: str | None,
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> bool:
    cleaned = _normalize_optional_text(text)
    if cleaned is None:
        return False
    collapsed_text = _collapse_whitespace(cleaned).lower()
    if collapsed_query.lower() in collapsed_text:
        return True
    if compact_query is None:
        return False
    compact_text = _compact_text(cleaned).lower()
    return bool(compact_query) and compact_query.lower() in compact_text


def _matches_prefix_text_candidate(
    text: str | None,
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> bool:
    cleaned = _normalize_optional_text(text)
    if cleaned is None:
        return False
    collapsed_text = _collapse_whitespace(cleaned).lower()
    if collapsed_text.startswith(collapsed_query.lower()):
        return True
    if compact_query is None:
        return False
    compact_text = _compact_text(cleaned).lower()
    return bool(compact_query) and compact_text.startswith(compact_query.lower())


def rank_course_search_candidate(
    item: dict[str, Any],
    *,
    queries: list[str],
) -> int | None:
    code = str(item.get("code") or "")
    title = str(item.get("title") or "")
    professor = str(item.get("professor") or "")

    best_rank: int | None = None
    for query in queries:
        collapsed_query, compact_query = _normalized_query_variants(query)
        if collapsed_query is None:
            continue

        rank: int | None = None
        if _matches_exact_text_candidate(
            code,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        ):
            rank = 0
        elif _matches_prefix_text_candidate(
            code,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        ):
            rank = 1
        elif _matches_exact_text_candidate(
            title,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        ):
            rank = 2
        elif _matches_prefix_text_candidate(
            title,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        ):
            rank = 3
        elif _matches_exact_text_candidate(
            professor,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        ):
            rank = 4
        elif _matches_prefix_text_candidate(
            professor,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        ):
            rank = 5
        elif any(
            _matches_partial_text_candidate(
                field,
                collapsed_query=collapsed_query,
                compact_query=compact_query,
            )
            for field in (code, title, professor)
        ):
            rank = 6
        if rank is None:
            continue
        if best_rank is None or rank < best_rank:
            best_rank = rank
    return best_rank


def course_row_matches_queries(row: dict[str, Any], queries: list[str]) -> bool:
    text_fields = [
        _normalize_optional_text(row.get("title")),
        _normalize_optional_text(row.get("code")),
        _normalize_optional_text(row.get("professor")),
    ]
    lowered_fields = [field.lower() for field in text_fields if field]
    compacted_fields = [_compact_text(field).lower() for field in text_fields if field]

    for query in queries:
        lowered_query = query.lower()
        compacted_query = _compact_text(query).lower()
        if any(lowered_query in field for field in lowered_fields):
            return True
        if compacted_query and any(compacted_query in field for field in compacted_fields):
            return True
    return False


def course_match_preview(
    rows: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, str | None]]:
    return [
        {
            "code": row.get("code"),
            "title": row.get("title"),
            "professor": row.get("professor"),
            "department": row.get("department"),
            "section": row.get("section"),
        }
        for row in rows[:limit]
    ]


def _current_year_and_semester(now: datetime | None = None) -> tuple[int, int]:
    # 넘겨받은 시각도 학교 시계로 읽는다. UTC 로 적힌 6월 30일 밤은 이미 7월이다.
    current = _coerce_datetime(now)
    semester = 1 if current.month <= 6 else 2
    return current.year, semester


def _collect_course_snapshot_rows(
    source: CourseCatalogSource | Any,
    *,
    year: int,
    semester: int,
    fetched_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_course_keys: set[tuple[Any, ...]] = set()

    for page_index in range(50):
        offset = page_index * 50
        html = source.fetch(
            year=year,
            semester=semester,
            department="ALL",
            completion_type="ALL",
            query="",
            offset=offset,
        )
        page_rows = source.parse(html, fetched_at=fetched_at)
        if not page_rows:
            break
        for row in page_rows:
            course_key = (
                row.get("code"),
                row.get("section"),
                row.get("raw_schedule"),
                row.get("professor"),
                row.get("title"),
            )
            if course_key in seen_course_keys:
                continue
            seen_course_keys.add(course_key)
            rows.append(row)
        if len(page_rows) < 50:
            break
    return rows


def _search_course_rows_from_rows(
    rows: list[dict[str, Any]],
    query: str = "",
    *,
    period_start: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    normalized_query = normalize_course_query_text(query)
    if normalized_query is None:
        filtered_rows = rows
        if period_start is not None:
            filtered_rows = [
                item
                for item in filtered_rows
                if int(item.get("period_start") or 0) == int(period_start)
            ]
        return filtered_rows[:limit]

    query_candidates = course_query_candidates(query)
    ranked_items: list[tuple[int, int, int, str, str, str, int, dict[str, Any]]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    order_index = 0
    for candidate_query in query_candidates:
        matched_rows = [
            item for item in rows if course_row_matches_queries(item, [candidate_query])
        ]
        for item in matched_rows:
            if period_start is not None and int(item.get("period_start") or 0) != int(period_start):
                continue
            item_key = (
                item.get("id"),
                item.get("year"),
                item.get("semester"),
                item.get("code"),
                item.get("title"),
                item.get("professor"),
                item.get("section"),
            )
            if item_key in seen_keys:
                continue
            seen_keys.add(item_key)
            rank = rank_course_search_candidate(item, queries=query_candidates)
            if rank is None:
                continue
            ranked_items.append(
                (
                    rank,
                    -int(item.get("year") or 0),
                    -int(item.get("semester") or 0),
                    _collapse_whitespace(str(item.get("title") or "")).lower(),
                    str(item.get("code") or "").lower(),
                    str(item.get("section") or "").lower(),
                    order_index,
                    item,
                )
            )
            order_index += 1
    ranked_items.sort(key=lambda item: item[:-1])
    return [item[-1] for item in ranked_items[:limit]]


def search_course_rows(
    rows_or_conn: list[dict[str, Any]] | DBConnection,
    query: str = "",
    *,
    year: int | None = None,
    semester: int | None = None,
    period_start: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if isinstance(rows_or_conn, list):
        return _search_course_rows_from_rows(
            rows_or_conn,
            query=query,
            period_start=period_start,
            limit=limit,
        )

    normalized_query = normalize_course_query_text(query)
    if normalized_query is None:
        return _search_course_rows_from_rows(
            repo.search_courses(
                rows_or_conn,
                "",
                year=year,
                semester=semester,
                period_start=period_start,
                limit=limit,
            ),
            query=query,
            period_start=period_start,
            limit=limit,
        )

    candidate_rows: list[dict[str, Any]] = []
    for candidate_query in course_query_candidates(query):
        candidate_rows.extend(
            repo.search_courses(
                rows_or_conn,
                candidate_query,
                year=year,
                semester=semester,
                period_start=period_start,
                limit=None,
            )
        )

    return _search_course_rows_from_rows(
        candidate_rows,
        query=query,
        period_start=None,
        limit=limit,
    )


def _investigate_course_query_coverage_from_rows(
    *,
    queries: list[str],
    source_rows: list[dict[str, Any]],
    db_rows: list[dict[str, Any]],
    year: int,
    semester: int,
    search_limit: int,
    search_rows_fn: Callable[[str, int], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for query in queries:
        candidate_queries = course_query_candidates(query)
        source_matches = [
            row for row in source_rows if course_row_matches_queries(row, candidate_queries)
        ]
        db_direct_matches = [
            row for row in db_rows if course_row_matches_queries(row, candidate_queries)
        ]
        search_matches = search_rows_fn(query, search_limit)

        if search_matches:
            status = "covered"
        elif db_direct_matches:
            status = "search_gap"
        elif source_matches:
            status = "db_gap"
        else:
            status = "source_gap"

        reports.append(
            {
                "query": query,
                "year": year,
                "semester": semester,
                "status": status,
                "source_match_count": len(source_matches),
                "db_match_count": len(db_direct_matches),
                "search_match_count": len(search_matches),
                "source_matches": course_match_preview(source_matches),
                "db_matches": course_match_preview(db_direct_matches),
                "search_matches": course_match_preview(search_matches),
            }
        )
    return reports


def investigate_course_query_coverage(
    conn: DBConnection | None = None,
    *,
    queries: list[str],
    source: CourseCatalogSource | Any | None = None,
    year: int | None = None,
    semester: int | None = None,
    fetched_at: str | None = None,
    search_limit: int = 20,
    source_rows: list[dict[str, Any]] | None = None,
    db_rows: list[dict[str, Any]] | None = None,
    search_rows_fn: Callable[[str, int], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    resolved_year, resolved_semester = _current_year_and_semester()
    resolved_year = year or resolved_year
    resolved_semester = semester or resolved_semester

    if source_rows is None:
        source = source or CourseCatalogSource(COURSE_SOURCE_URL)
        source_rows = _collect_course_snapshot_rows(
            source,
            year=resolved_year,
            semester=resolved_semester,
            fetched_at=fetched_at or _now_iso(),
        )
    if db_rows is None:
        if conn is None:
            raise TypeError("db_rows is required when conn is not provided")
        db_rows = repo.list_courses_snapshot(
            conn,
            year=resolved_year,
            semester=resolved_semester,
        )
    if search_rows_fn is None:
        if conn is None:
            raise TypeError("search_rows_fn is required when conn is not provided")

        def search_rows_fn(raw_query: str, raw_limit: int) -> list[dict[str, Any]]:
            return search_course_rows(
                conn,
                query=raw_query,
                year=resolved_year,
                semester=resolved_semester,
                limit=raw_limit,
            )

    return _investigate_course_query_coverage_from_rows(
        queries=queries,
        source_rows=source_rows,
        db_rows=db_rows,
        year=resolved_year,
        semester=resolved_semester,
        search_limit=search_limit,
        search_rows_fn=search_rows_fn,
    )
