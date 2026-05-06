from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, ValidationError

from . import place_search_runtime, services
from .ingest.campus_life_support_guides import (
    HealthCenterGuideSource,
    LostFoundGuideSource,
    ParkingGuideSource,
)
from .ingest.official_sources import (
    AcademicCalendarSource,
    AcademicSupportGuideSource,
    CampusFacilitiesSource,
    CampusLifeEventsNoticeBoardSource,
    CampusLifeOutsideAgenciesNoticeBoardSource,
    CampusMapSource,
    CertificateGuideSource,
    ClassCourseCancellationGuideSource,
    ClassCourseEvaluationGuideSource,
    ClassExcusedAbsenceGuideSource,
    ClassForeignLanguageRequirementGuideSource,
    ClassRegistrationChangeGuideSource,
    ClassRetakeGuideSource,
    CourseCatalogSource,
    GradeEvaluationGuideSource,
    GraduationRequirementGuideSource,
    LeaveOfAbsenceGuideSource,
    NoticeSource,
    PhoneBookSource,
    RegistrationBillLookupGuideSource,
    RegistrationPaymentAndReturnGuideSource,
    RegistrationPaymentByStudentGuideSource,
    ScholarshipGuideSource,
    SeasonalSemesterGuideSource,
    StudentExchangeDomesticCreditExchangeGuideSource,
    StudentExchangeDomesticPartnerUniversitiesGuideSource,
    StudentExchangeExchangeProgramsGuideSource,
    StudentExchangeExchangeStudentGuideSource,
    StudentExchangePartnerSource,
    TransportGuideSource,
    WifiGuideSource,
)
from .ingest.pc_software import (
    PCSoftwareSource,
)
from .ingest.pc_software import (
    search_pc_software_entries as rank_pc_software_rows,
)
from .ingest.student_activity_guides import (
    CampusMediaGuideSource,
    RotcGuideSource,
    SocialVolunteeringGuideSource,
    StudentGovernmentGuideSource,
)

try:
    from . import course_search_runtime as course_search_runtime
except ImportError:
    course_search_runtime = services

_current_academic_year = getattr(
    course_search_runtime,
    "_current_academic_year",
    services._current_academic_year,
)
_collect_course_snapshot_rows = getattr(
    course_search_runtime,
    "_collect_course_snapshot_rows",
    services._collect_course_snapshot_rows,
)
_course_query_candidates = getattr(
    course_search_runtime,
    "course_query_candidates",
    services._course_query_candidates,
)
_normalize_course_query_text = getattr(
    course_search_runtime,
    "normalize_course_query_text",
    services._normalize_course_query_text,
)
_course_row_matches_queries = getattr(
    course_search_runtime,
    "course_row_matches_queries",
    services._course_row_matches_queries,
)
_rank_course_search_candidate = getattr(
    course_search_runtime,
    "rank_course_search_candidate",
    services._rank_course_search_candidate,
)
_search_course_rows = getattr(
    course_search_runtime,
    "search_course_rows",
    None,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_PATH = ROOT_DIR / "data" / "qa" / "public_api_eval_corpus_1000.jsonl"
DEFAULT_WATCHLIST_PATH = ROOT_DIR / "data" / "qa" / "public_api_eval_watchlist.jsonl"
DEFAULT_REPORT_PATH = ROOT_DIR / "docs" / "qa" / "public-api-live-validation-1000.md"
PUBLIC_EVAL_HTTP_TIMEOUT_SECONDS = 20.0
PUBLIC_EVAL_HTTP_RETRIES = 2
PUBLIC_EVAL_MAX_WORKERS = 4

EvalDomain = Literal[
    "place",
    "courses",
    "notices",
    "affiliated_notices",
    "campus_life_notices",
    "restaurants",
    "transport",
    "classrooms",
    "academic_calendar",
    "certificate_guides",
    "scholarship_guides",
    "wifi_guides",
    "leave_of_absence_guides",
    "academic_support_guides",
    "registration_guides",
    "class_guides",
    "seasonal_semester_guides",
    "academic_milestone_guides",
    "student_exchange_guides",
    "student_activity_guides",
    "student_exchange_partners",
    "campus_life_support_guides",
    "pc_software_entries",
    "phone_book",
    "dormitory_guides",
    "out_of_scope",
]
EvalStyle = Literal["normal", "alias", "composite", "typo", "ambiguous", "out_of_scope"]
TruthMode = Literal["exact_value", "set_contains", "invariant_only", "watch_only"]
EvalVerdict = Literal["pass", "soft_pass", "soft_fail", "fail", "watch", "skip"]

POLICY_SUMMARIES: dict[str, dict[str, Any]] = {
    "public_readonly_profile_timetable_admin": {
        "mode": "public_readonly",
        "blocked_features": ["profile", "timetable", "admin", "personalization"],
    }
}


class EvalApiRequest(BaseModel):
    path: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    method: Literal["GET"] = "GET"
    policy: str | None = None


class EvalCorpusRow(BaseModel):
    id: str
    domain: EvalDomain
    style: EvalStyle
    user_utterance: str
    api_request: EvalApiRequest
    expected_mcp_flow: str
    truth_mode: TruthMode
    pass_rule: dict[str, Any] = Field(default_factory=dict)
    watch_policy: str = "none"
    notes: str = ""


class EvalTruthRow(BaseModel):
    id: str
    normalized_expected: Any | None = None
    truth_source: str
    captured_at: str
    stability: str


class EvalResultRow(BaseModel):
    id: str
    status: str
    verdict: EvalVerdict
    actual_summary: Any | None = None
    comparison: str
    truth_source: str | None = None
    checked_at: str


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _request_cache_key(row: EvalCorpusRow) -> tuple[str | None, str | None, str]:
    return (
        row.api_request.path,
        row.api_request.policy,
        json.dumps(row.api_request.params, sort_keys=True, ensure_ascii=False, default=str),
    )


def _coarse_request_cache_key(row: EvalCorpusRow) -> tuple[str | None, str | None, str]:
    if row.truth_mode == "exact_value":
        return _request_cache_key(row)
    normalized_params = dict(row.api_request.params)
    normalized_params.pop("limit", None)
    return (
        row.api_request.path,
        row.api_request.policy,
        json.dumps(normalized_params, sort_keys=True, ensure_ascii=False, default=str),
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))
    return rows


def _write_jsonl(path: Path, rows: Iterable[BaseModel | dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    for row in rows:
        payload = row.model_dump() if isinstance(row, BaseModel) else row
        rendered.append(json.dumps(payload, ensure_ascii=False))
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def load_eval_rows(path: Path | str) -> list[EvalCorpusRow]:
    resolved = Path(path)
    rows: list[EvalCorpusRow] = []
    seen_ids: set[str] = set()
    for item in _read_jsonl(resolved):
        try:
            row = EvalCorpusRow.model_validate(item)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        if row.id in seen_ids:
            raise ValueError(f"Duplicate evaluation id: {row.id}")
        seen_ids.add(row.id)
        rows.append(row)
    return rows


def load_truth_rows(path: Path | str) -> list[EvalTruthRow]:
    return [EvalTruthRow.model_validate(item) for item in _read_jsonl(Path(path))]


def _truth_lookup(rows: Iterable[EvalTruthRow]) -> dict[str, EvalTruthRow]:
    return {row.id: row for row in rows}


def _limit_from_row(row: EvalCorpusRow, default: int = 5) -> int:
    raw_limit = row.api_request.params.get("limit", default)
    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 50))


def _summarize_payload(payload: Any, *, summary_kind: str) -> Any:
    if summary_kind == "places_top3":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "slug": item.get("slug"),
                "name": item.get("name"),
                "category": item.get("category"),
            }
            for item in rows[:3]
        ]
    if summary_kind == "places_top1_facility_host":
        rows = payload if isinstance(payload, list) else []
        if not rows:
            return None
        item = rows[0]
        facility = item.get("matched_facility") if isinstance(item, dict) else None
        return {
            "slug": item.get("slug"),
            "name": item.get("name"),
            "canonical_name": item.get("canonical_name"),
            "category": item.get("category"),
            "matched_facility": (
                {
                    "name": facility.get("name"),
                    "location_hint": facility.get("location_hint"),
                }
                if isinstance(facility, dict)
                else None
            ),
        }
    if summary_kind == "places_top1_alias_display":
        rows = payload if isinstance(payload, list) else []
        if not rows:
            return None
        item = rows[0]
        return {
            "slug": item.get("slug"),
            "name": item.get("name"),
            "canonical_name": item.get("canonical_name"),
            "category": item.get("category"),
            "matched_facility": item.get("matched_facility"),
        }
    if summary_kind == "courses_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "code": item.get("code"),
                "title": item.get("title"),
                "professor": item.get("professor"),
                "year": item.get("year"),
                "semester": item.get("semester"),
                "period_start": item.get("period_start"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "notices_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "title": item.get("title"),
                "category": item.get("category"),
                "published_at": item.get("published_at"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "affiliated_notices_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "published_at": item.get("published_at"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "campus_life_notices_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "published_at": item.get("published_at"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "transport_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "mode": item.get("mode"),
                "title": item.get("title"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "academic_calendar_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "title": item.get("title"),
                "start_date": item.get("start_date"),
                "end_date": item.get("end_date"),
                "campuses": item.get("campuses", []),
            }
            for item in rows[:5]
        ]
    if summary_kind == "certificate_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [{"title": item.get("title"), "summary": item.get("summary")} for item in rows[:5]]
    if summary_kind == "leave_of_absence_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [{"title": item.get("title"), "summary": item.get("summary")} for item in rows[:5]]
    if summary_kind == "registration_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "class_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "seasonal_semester_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "academic_milestone_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "student_exchange_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "student_activity_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "student_exchange_partners_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "partner_code": item.get("partner_code"),
                "university_name": item.get("university_name"),
                "country_ko": item.get("country_ko"),
                "country_en": item.get("country_en"),
                "continent": item.get("continent"),
                "location": item.get("location"),
                "agreement_date": item.get("agreement_date"),
                "homepage_url": item.get("homepage_url"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "dormitory_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "campus_life_support_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "topic": item.get("topic"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "pc_software_entries_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "room": item.get("room"),
                "pc_count": item.get("pc_count"),
                "software_summary": ", ".join((item.get("software_list") or [])[:4]),
            }
            for item in rows[:5]
        ]
    if summary_kind == "phone_book_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "department": item.get("department"),
                "tasks": item.get("tasks"),
                "phone": item.get("phone"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "scholarship_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [{"title": item.get("title"), "summary": item.get("summary")} for item in rows[:5]]
    if summary_kind == "wifi_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "building_name": item.get("building_name"),
                "ssids": item.get("ssids", []),
            }
            for item in rows[:5]
        ]
    if summary_kind == "academic_support_guides_top5":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "title": item.get("title"),
                "summary": item.get("summary"),
                "contacts": item.get("contacts", []),
            }
            for item in rows[:5]
        ]
    if summary_kind == "restaurants_nearby":
        rows = payload if isinstance(payload, list) else []
        return [
            {
                "name": item.get("name"),
                "origin": item.get("origin"),
                "category": item.get("category"),
                "open_now": item.get("open_now"),
            }
            for item in rows[:5]
        ]
    if summary_kind == "restaurants_search_top5":
        rows = payload if isinstance(payload, list) else []
        return [{"name": item.get("name"), "category": item.get("category")} for item in rows[:5]]
    if summary_kind == "classrooms_empty":
        payload = payload if isinstance(payload, dict) else {}
        return {
            "building": {
                "slug": payload.get("building", {}).get("slug"),
                "name": payload.get("building", {}).get("name"),
            },
            "availability_mode": payload.get("availability_mode"),
            "items": [item.get("room") for item in payload.get("items", [])[:5]],
        }
    if summary_kind == "policy_reference":
        payload = payload if isinstance(payload, dict) else {}
        return {
            "mode": payload.get("mode"),
            "blocked_features": payload.get("blocked_features", []),
        }
    return payload


def _build_policy_summary(row: EvalCorpusRow) -> dict[str, Any]:
    if row.api_request.policy:
        fallback = {"mode": "unknown", "blocked_features": []}
        return dict(POLICY_SUMMARIES.get(row.api_request.policy, fallback))
    return {"mode": "unknown", "blocked_features": []}


def _search_phone_book_rows(
    rows: list[dict[str, Any]],
    *,
    query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(limit, 50))
    sorted_rows = sorted(
        rows,
        key=lambda item: (
            str(item.get("department") or ""),
            str(item.get("phone") or ""),
        ),
    )
    normalized_query = (query or "").strip()
    if not normalized_query:
        return sorted_rows[:normalized_limit]

    collapsed_query = normalized_query.casefold()
    compact_query = re.sub(r"\s+", "", normalized_query).casefold()
    ranked: list[tuple[int, str, int, dict[str, Any]]] = []
    for index, item in enumerate(sorted_rows):
        department = str(item.get("department") or "")
        tasks = str(item.get("tasks") or "")
        phone = str(item.get("phone") or "")

        department_folded = department.casefold()
        tasks_folded = tasks.casefold()
        phone_folded = phone.casefold()
        department_compact = re.sub(r"\s+", "", department).casefold()
        tasks_compact = re.sub(r"\s+", "", tasks).casefold()
        phone_compact = re.sub(r"\s+", "", phone).casefold()

        rank: int | None = None
        if department_folded == collapsed_query or department_compact == compact_query:
            rank = 0
        elif collapsed_query in tasks_folded or compact_query in tasks_compact:
            rank = 1
        elif collapsed_query in phone_folded or compact_query in phone_compact:
            rank = 2
        if rank is None:
            continue
        ranked.append((rank, department, index, item))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in ranked[:normalized_limit]]


def _search_student_exchange_partner_rows(
    rows: list[dict[str, Any]],
    *,
    query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(limit, 50))
    sorted_rows = sorted(
        rows,
        key=lambda item: (
            item.get("country_ko") is None,
            str(item.get("country_ko") or ""),
            str(item.get("university_name") or ""),
            str(item.get("partner_code") or ""),
        ),
    )
    normalized_query = (query or "").strip()
    if not normalized_query:
        return sorted_rows[:normalized_limit]

    collapsed_query = normalized_query.casefold()
    compact_query = re.sub(r"\s+", "", normalized_query).casefold()
    continent_query = services.STUDENT_EXCHANGE_PARTNER_CONTINENT_ALIASES.get(
        normalized_query,
        normalized_query,
    )
    collapsed_continent_query = continent_query.casefold()
    compact_continent_query = re.sub(r"\s+", "", continent_query).casefold()

    ranked: list[tuple[int, str, str, str, dict[str, Any]]] = []
    for item in sorted_rows:
        university_name = str(item.get("university_name") or "").casefold()
        country_ko = str(item.get("country_ko") or "").casefold()
        continent = str(item.get("continent") or "").casefold()
        country_en = str(item.get("country_en") or "").casefold()
        location = str(item.get("location") or "").casefold()
        university_compact = re.sub(r"\s+", "", str(item.get("university_name") or "")).casefold()
        country_ko_compact = re.sub(r"\s+", "", str(item.get("country_ko") or "")).casefold()
        country_en_compact = re.sub(r"\s+", "", str(item.get("country_en") or "")).casefold()
        continent_compact = re.sub(r"\s+", "", str(item.get("continent") or "")).casefold()
        location_compact = re.sub(r"\s+", "", str(item.get("location") or "")).casefold()

        rank: int | None = None
        if university_name == collapsed_query or university_compact == compact_query:
            rank = 0
        elif country_ko == collapsed_query or country_ko_compact == compact_query:
            rank = 1
        elif (
            continent == collapsed_query
            or continent_compact == compact_query
            or continent == collapsed_continent_query
            or continent_compact == compact_continent_query
        ):
            rank = 2
        elif (
            collapsed_query in university_name
            or compact_query in university_compact
            or collapsed_query in country_ko
            or compact_query in country_ko_compact
            or collapsed_query in country_en
            or compact_query in country_en_compact
            or collapsed_query in continent
            or compact_query in continent_compact
            or collapsed_continent_query in continent
            or compact_continent_query in continent_compact
            or collapsed_query in location
            or compact_query in location_compact
        ):
            rank = 3

        if rank is None:
            continue
        ranked.append(
            (
                rank,
                str(item.get("country_ko") or ""),
                str(item.get("university_name") or ""),
                str(item.get("partner_code") or ""),
                item,
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [item[4] for item in ranked[:normalized_limit]]


def _dedupe_topic_local_first_seen_rows(
    rows: list[dict[str, Any]],
    *,
    topic_key: str = "topic",
    article_no_key: str = "article_no",
    source_url_key: str = "source_url",
    title_key: str = "title",
    published_at_key: str = "published_at",
) -> list[dict[str, Any]]:
    seen_article_nos: set[tuple[str, str]] = set()
    seen_source_urls: set[tuple[str, str]] = set()
    seen_title_published: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in rows:
        topic = str(item.get(topic_key) or "").strip()
        if not topic:
            deduped.append(item)
            continue
        normalized_topic = topic.casefold()
        article_no = str(item.get(article_no_key) or "").strip()
        if article_no:
            article_no_pair = (normalized_topic, re.sub(r"\s+", "", article_no).casefold())
            if article_no_pair in seen_article_nos:
                continue
            seen_article_nos.add(article_no_pair)
        source_url = str(item.get(source_url_key) or "").strip()
        if source_url:
            source_url_pair = (normalized_topic, re.sub(r"\s+", "", source_url).casefold())
            if source_url_pair in seen_source_urls:
                continue
            seen_source_urls.add(source_url_pair)
        title = str(item.get(title_key) or "").strip()
        published_at = str(item.get(published_at_key) or "").strip()
        if title and published_at:
            title_published_triplet = (
                normalized_topic,
                re.sub(r"\s+", "", title).casefold(),
                re.sub(r"\s+", "", published_at).casefold(),
            )
            if title_published_triplet in seen_title_published:
                continue
            seen_title_published.add(title_published_triplet)
        deduped.append(item)
    return deduped


def _subset_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list) and isinstance(actual, list):
        for expected_item in expected:
            if not any(_subset_match(expected_item, actual_item) for actual_item in actual):
                return False
        return True
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(
            key in actual and _subset_match(value, actual.get(key))
            for key, value in expected.items()
        )
    return expected == actual


def _evaluate_invariants(row: EvalCorpusRow, actual_summary: Any) -> tuple[EvalVerdict, str]:
    rule = row.pass_rule
    summary_kind = str(rule.get("summary_kind") or "")
    if summary_kind == "restaurants_nearby":
        if not isinstance(actual_summary, list):
            return "fail", "restaurants_payload_not_list"
        if actual_summary:
            for item in actual_summary:
                for field in rule.get("required_fields", []):
                    if item.get(field) in (None, "", []):
                        return "fail", f"missing_field:{field}"
        elif not rule.get("allow_empty", False):
            return "fail", "empty_not_allowed"
        return "pass", "invariants_hold"
    if summary_kind == "classrooms_empty":
        if not isinstance(actual_summary, dict):
            return "fail", "classrooms_payload_not_object"
        building = actual_summary.get("building") or {}
        if not building.get("slug"):
            return "fail", "missing_building_slug"
        if actual_summary.get("availability_mode") is None:
            return "fail", "missing_availability_mode"
        return "pass", "invariants_hold"
    if summary_kind == "policy_reference":
        blocked = (
            set(actual_summary.get("blocked_features", []))
            if isinstance(actual_summary, dict)
            else set()
        )
        required = set(rule.get("required_blocked_features", []))
        if required and not required.issubset(blocked):
            return "fail", "policy_gap"
        return "pass", "policy_invariants_hold"
    if isinstance(actual_summary, list):
        if actual_summary or rule.get("allow_empty", False):
            return "pass", "invariants_hold"
        return "fail", "empty_not_allowed"
    if actual_summary:
        return "pass", "invariants_hold"
    return "fail", "empty_payload"


def _normalize_truth_payload(row: EvalCorpusRow, payload: Any) -> Any:
    summary_kind = str(row.pass_rule.get("summary_kind") or "")
    return _summarize_payload(payload, summary_kind=summary_kind)


def _payload_from_db(conn: psycopg.Connection, row: EvalCorpusRow) -> Any:
    params = row.api_request.params
    path = row.api_request.path
    if path == "/places":
        return [
            item.model_dump()
            for item in services.search_places(
                conn,
                query=str(params.get("query", "")),
                category=params.get("category"),
                limit=_limit_from_row(row, 10),
            )
        ]
    if path == "/courses":
        return [
            item.model_dump()
            for item in services.search_courses(
                conn,
                query=str(params.get("query", "")),
                year=params.get("year"),
                semester=params.get("semester"),
                period_start=params.get("period_start"),
                limit=_limit_from_row(row, 20),
            )
        ]
    if path == "/notices":
        return [
            item.model_dump()
            for item in services.list_latest_notices(
                conn,
                category=params.get("category"),
                limit=_limit_from_row(row, 10),
            )
        ]
    if path == "/affiliated-notices":
        return [
            item.model_dump()
            for item in services.list_affiliated_notices(
                conn,
                topic=params.get("topic"),
                query=params.get("query"),
                limit=_limit_from_row(row, 20),
            )
        ]
    if path == "/campus-life-notices":
        return [
            item.model_dump()
            for item in services.list_campus_life_notices(
                conn,
                topic=params.get("topic"),
                query=params.get("query"),
                limit=_limit_from_row(row, 20),
            )
        ]
    if path == "/transport":
        return [
            item.model_dump()
            for item in services.list_transport_guides(
                conn,
                mode=params.get("mode"),
                query=params.get("query"),
                limit=_limit_from_row(row, 20),
            )
        ]
    if path == "/academic-calendar":
        return [
            item.model_dump()
            for item in services.list_academic_calendar(
                conn,
                academic_year=params.get("academic_year"),
                month=params.get("month"),
                query=params.get("query"),
                limit=_limit_from_row(row, 20),
            )
        ]
    if path == "/certificate-guides":
        items = services.list_certificate_guides(conn, limit=_limit_from_row(row, 20))
        return [item.model_dump() for item in items]
    if path == "/leave-of-absence-guides":
        items = services.list_leave_of_absence_guides(
            conn,
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/scholarship-guides":
        items = services.list_scholarship_guides(conn, limit=_limit_from_row(row, 20))
        return [item.model_dump() for item in items]
    if path == "/wifi-guides":
        items = services.list_wifi_guides(conn, limit=_limit_from_row(row, 20))
        return [item.model_dump() for item in items]
    if path == "/academic-support-guides":
        items = services.list_academic_support_guides(
            conn,
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/registration-guides":
        items = services.list_registration_guides(
            conn,
            topic=row.api_request.params.get("topic"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/class-guides":
        items = services.list_class_guides(
            conn,
            topic=row.api_request.params.get("topic"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/seasonal-semester-guides":
        items = services.list_seasonal_semester_guides(
            conn,
            topic=row.api_request.params.get("topic"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/academic-milestone-guides":
        items = services.list_academic_milestone_guides(
            conn,
            topic=row.api_request.params.get("topic"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/student-exchange-guides":
        items = services.list_student_exchange_guides(
            conn,
            topic=row.api_request.params.get("topic"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/student-exchange-partners":
        items = services.search_student_exchange_partners(
            conn,
            query=row.api_request.params.get("query"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/dormitory-guides":
        items = services.list_dormitory_guides(
            conn,
            topic=row.api_request.params.get("topic"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/campus-life-support-guides":
        items = services.list_campus_life_support_guides(
            conn,
            topic=row.api_request.params.get("topic"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/pc-software":
        items = services.search_pc_software_entries(
            conn,
            query=row.api_request.params.get("query"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    if path == "/phone-book":
        items = services.search_phone_book_entries(
            conn,
            query=row.api_request.params.get("query"),
            limit=_limit_from_row(row, 20),
        )
        return [item.model_dump() for item in items]
    raise ValueError(f"Unsupported DB truth path: {path}")


def _search_places_from_source(
    row: EvalCorpusRow,
    *,
    fetched_at: str,
    source_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    cache_key = "places_snapshot"
    if cache_key not in source_cache:
        source = CampusMapSource(services.CAMPUS_MAP_SOURCE_URL)
        source_cache[cache_key] = services.apply_place_alias_overrides(
            source.parse_place_list(
                source.fetch_place_list(),
                fetched_at=fetched_at,
            )
        )
    places = list(source_cache[cache_key])
    category = row.api_request.params.get("category")
    if category is not None:
        places = [item for item in places if item.get("category") == category]

    query = str(row.api_request.params.get("query") or "")
    collapsed_query, compact_query = place_search_runtime._normalize_place_search_query(query)
    if collapsed_query is None:
        return places[: _limit_from_row(row, 10)]

    facility_index = place_search_runtime._build_place_search_facility_index(places)
    preferred_slugs = place_search_runtime._preferred_place_slugs_for_query(
        query,
        context="place_search",
    )
    preferred_slug_set = set(preferred_slugs)
    ranked: list[tuple[int, int, int, dict[str, Any]]] = []
    for index, item in enumerate(places):
        rank = place_search_runtime._rank_place_search_candidate(
            item,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
            facility_tokens=facility_index[index]["facility_tokens"],
            generic_keywords=facility_index[index]["generic_keywords"],
        )
        if rank is None:
            continue
        canonical_name = str(item.get("name") or "")
        payload = {
            **item,
            "name": place_search_runtime._display_name_for_place_result(
                str(item.get("slug") or ""),
                canonical_name,
                collapsed_query=collapsed_query,
                compact_query=compact_query,
                aliases=[str(alias) for alias in item.get("aliases", [])],
            ),
            "canonical_name": canonical_name,
        }
        preference_rank = 0 if str(item.get("slug") or "").strip() in preferred_slug_set else 1
        ranked.append((rank, preference_rank, index, payload))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    if preferred_slugs:
        ranked = [
            item for item in ranked if str(item[3].get("slug") or "").strip() in preferred_slug_set
        ]
    return [item for _, _, _, item in ranked[: _limit_from_row(row, 10)]]


def _load_source_place_rows(
    *,
    fetched_at: str,
    source_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    cache_key = "places_snapshot"
    if cache_key not in source_cache:
        source = CampusMapSource(services.CAMPUS_MAP_SOURCE_URL)
        source_cache[cache_key] = services.apply_place_alias_overrides(
            source.parse_place_list(
                source.fetch_place_list(),
                fetched_at=fetched_at,
            )
        )
    return list(source_cache[cache_key])


def _load_source_facility_rows(
    *,
    fetched_at: str,
    source_cache: dict[str, Any],
    place_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cache_key = "campus_facilities_snapshot"
    if cache_key not in source_cache:
        source = CampusFacilitiesSource(services.FACILITIES_SOURCE_URL)
        raw_rows = source.parse(source.fetch(), fetched_at=fetched_at)
        normalized_rows: list[dict[str, Any]] = []
        for row in raw_rows:
            location_text = place_search_runtime._normalize_campus_facility_location(
                row.get("location_text") or row.get("location")
            )
            normalized_rows.append(
                {
                    "facility_name": str(row.get("facility_name") or ""),
                    "category": place_search_runtime._normalize_optional_text(row.get("category")),
                    "phone": place_search_runtime._normalize_campus_facility_phone(
                        row.get("phone") or row.get("contact")
                    ),
                    "location_text": location_text,
                    "hours_text": place_search_runtime._normalize_optional_text(
                        row.get("hours_text")
                    ),
                    "place_slug": place_search_runtime._resolve_campus_facility_place_slug(
                        location_text,
                        place_rows=place_rows,
                    ),
                    "source_url": row.get("source_url") or services.FACILITIES_SOURCE_URL,
                    "source_tag": row.get("source_tag", "cuk_facilities"),
                    "last_synced_at": row.get("last_synced_at"),
                }
            )
        source_cache[cache_key] = normalized_rows
    return list(source_cache[cache_key])


def _search_facility_host_places_from_source(
    row: EvalCorpusRow,
    *,
    fetched_at: str,
    source_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    places = _load_source_place_rows(fetched_at=fetched_at, source_cache=source_cache)
    collapsed_query, compact_query = place_search_runtime._normalize_place_search_query(
        str(row.api_request.params.get("query") or "")
    )
    if collapsed_query is None:
        return []

    facility_index = place_search_runtime._build_place_search_facility_index(places)
    searchable_facilities = _load_source_facility_rows(
        fetched_at=fetched_at,
        source_cache=source_cache,
        place_rows=places,
    )
    preferred_slugs = place_search_runtime._preferred_place_slugs_for_query(
        collapsed_query,
        context="place_search",
    )
    preferred_slug_set = set(preferred_slugs)
    place_alias_lists: dict[str, list[str]] = {}
    for place in places:
        slug = str(place.get("slug") or "").strip()
        if slug:
            place_alias_lists[slug] = [str(alias) for alias in place.get("aliases", [])]

    facility_best_by_slug: dict[str, tuple[int, int, dict[str, Any]]] = {}
    for facility_index_value, facility in enumerate(searchable_facilities):
        place_slug = str(facility.get("place_slug") or "").strip()
        if not place_slug:
            continue
        rank = place_search_runtime._rank_campus_facility_candidate(
            facility,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        if rank is None:
            continue
        existing = facility_best_by_slug.get(place_slug)
        if existing is None or (rank, facility_index_value) < (existing[0], existing[1]):
            facility_best_by_slug[place_slug] = (rank, facility_index_value, facility)

    ranked: list[tuple[int, int, int, int, dict[str, Any]]] = []
    for index, place in enumerate(places):
        place_rank = place_search_runtime._rank_place_search_candidate(
            place,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
            facility_tokens=facility_index[index]["facility_tokens"],
            generic_keywords=facility_index[index]["generic_keywords"],
        )
        slug = str(place.get("slug") or "").strip()
        facility_match = facility_best_by_slug.get(slug)
        if place_rank is None and facility_match is None:
            continue

        facility_sort = (
            place_search_runtime._facility_phase_for_rank(facility_match[0])
            if facility_match is not None
            else None
        )
        place_sort = (
            place_search_runtime._place_phase_for_rank(place_rank)
            if place_rank is not None
            else None
        )
        aliases = place_alias_lists.get(slug, [])
        canonical_name = str(place.get("name") or "")
        display_name = place_search_runtime._display_name_for_place_result(
            slug,
            canonical_name,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
            aliases=aliases,
        )
        if facility_sort is not None and (place_sort is None or facility_sort < place_sort):
            phase, subrank = facility_sort
            display_name = place_search_runtime._display_name_for_place_result(
                slug,
                canonical_name,
                collapsed_query=collapsed_query,
                compact_query=compact_query,
                aliases=aliases,
                has_matched_facility=True,
            )
            payload = {
                **place,
                "name": display_name,
                "canonical_name": canonical_name,
                "matched_facility": place_search_runtime._matched_facility_from_row(
                    facility_match[2]
                ).model_dump(exclude_none=True),
            }
        else:
            if place_sort is None:
                continue
            phase, subrank = place_sort
            payload = {
                **place,
                "name": display_name,
                "canonical_name": canonical_name,
            }
        preference_rank = 0 if slug in preferred_slug_set else 1
        ranked.append((phase, subrank, preference_rank, index, payload))

    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    if preferred_slugs:
        ranked = [
            item for item in ranked if str(item[4].get("slug") or "").strip() in preferred_slug_set
        ]
    return [item[4] for item in ranked[: _limit_from_row(row, 10)]]


def _search_courses_from_source(
    row: EvalCorpusRow,
    *,
    fetched_at: str,
    source_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    params = row.api_request.params
    year = int(params.get("year") or _current_academic_year())
    semester = int(params.get("semester") or 1)
    period_start = params.get("period_start")
    limit = _limit_from_row(row, 20)

    source = CourseCatalogSource(services.COURSE_SOURCE_URL)
    cache_key = f"courses_snapshot:{year}:{semester}"
    if cache_key not in source_cache:
        source_cache[cache_key] = _collect_course_snapshot_rows(
            source,
            year=year,
            semester=semester,
            fetched_at=fetched_at,
        )
    snapshot_rows = list(source_cache[cache_key])
    query = str(params.get("query") or "")
    if _search_course_rows is not None:
        return _search_course_rows(
            snapshot_rows,
            query=query,
            period_start=period_start,
            limit=limit,
        )

    query_candidates = _course_query_candidates(query)
    normalized_query = _normalize_course_query_text(query)
    if normalized_query is None:
        rows = snapshot_rows
        if period_start is not None:
            rows = [
                item for item in rows if int(item.get("period_start") or 0) == int(period_start)
            ]
        return rows[:limit]

    queries = query_candidates

    ranked_items: list[tuple[int, int, int, str, str, str, int, dict[str, Any]]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    order_index = 0
    for candidate_query in queries:
        rows = [
            item
            for item in snapshot_rows
            if _course_row_matches_queries(item, [candidate_query])
        ]
        for item in rows:
            if period_start is not None and int(item.get("period_start") or 0) != int(period_start):
                continue
            item_key = (
                item.get("code"),
                item.get("title"),
                item.get("professor"),
                item.get("section"),
            )
            if item_key in seen_keys:
                continue
            seen_keys.add(item_key)
            rank = _rank_course_search_candidate(
                item,
                queries=queries,
            )
            if rank is None:
                continue
            ranked_items.append(
                (
                    rank,
                    -int(item.get("year") or 0),
                    -int(item.get("semester") or 0),
                    str(item.get("title") or "").lower(),
                    str(item.get("code") or "").lower(),
                    str(item.get("section") or "").lower(),
                    order_index,
                    item,
                )
            )
            order_index += 1
    ranked_items.sort(key=lambda item: item[:-1])
    return [item[-1] for item in ranked_items[:limit]]


def _current_academic_year_bounds() -> tuple[str, str]:
    academic_year = _current_academic_year()
    return f"{academic_year}-03-01", f"{academic_year + 1}-02-28"


def _payload_from_sources(
    row: EvalCorpusRow,
    *,
    captured_at: str,
    source_cache: dict[str, Any],
) -> Any | None:
    path = row.api_request.path
    limit = _limit_from_row(row, 20)
    if path == "/places":
        if str(row.pass_rule.get("summary_kind") or "") == "places_top1_facility_host":
            return _search_facility_host_places_from_source(
                row,
                fetched_at=captured_at,
                source_cache=source_cache,
            )
        return _search_places_from_source(row, fetched_at=captured_at, source_cache=source_cache)
    if path == "/courses":
        return _search_courses_from_source(row, fetched_at=captured_at, source_cache=source_cache)
    if path == "/transport":
        cache_key = "transport_guides"
        if cache_key not in source_cache:
            source = TransportGuideSource(services.TRANSPORT_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        rows = list(source_cache[cache_key])
        if mode := row.api_request.params.get("mode"):
            rows = [item for item in rows if item.get("mode") == mode]
        return rows[:limit]
    if path == "/certificate-guides":
        cache_key = "certificate_guides"
        if cache_key not in source_cache:
            source = CertificateGuideSource(services.CERTIFICATE_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        return list(source_cache[cache_key])[:limit]
    if path == "/leave-of-absence-guides":
        cache_key = "leave_of_absence_guides"
        if cache_key not in source_cache:
            source = LeaveOfAbsenceGuideSource(services.LEAVE_OF_ABSENCE_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        return list(source_cache[cache_key])[:limit]
    if path == "/scholarship-guides":
        cache_key = "scholarship_guides"
        if cache_key not in source_cache:
            source = ScholarshipGuideSource(services.SCHOLARSHIP_GUIDE_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        return list(source_cache[cache_key])[:limit]
    if path == "/wifi-guides":
        cache_key = "wifi_guides"
        if cache_key not in source_cache:
            source = WifiGuideSource(services.WIFI_GUIDE_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        return list(source_cache[cache_key])[:limit]
    if path == "/academic-support-guides":
        cache_key = "academic_support_guides"
        if cache_key not in source_cache:
            source = AcademicSupportGuideSource(services.ACADEMIC_SUPPORT_GUIDE_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        return list(source_cache[cache_key])[:limit]
    if path == "/registration-guides":
        cache_key = "registration_guides"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            for source in (
                RegistrationBillLookupGuideSource(services.REGISTRATION_BILL_LOOKUP_SOURCE_URL),
                RegistrationPaymentAndReturnGuideSource(
                    services.REGISTRATION_PAYMENT_AND_RETURN_SOURCE_URL
                ),
                RegistrationPaymentByStudentGuideSource(
                    services.REGISTRATION_PAYMENT_BY_STUDENT_SOURCE_URL
                ),
            ):
                rows.extend(source.parse(source.fetch(), fetched_at=captured_at))
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/class-guides":
        cache_key = "class_guides"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            for source in (
                ClassRegistrationChangeGuideSource(
                    services.CLASS_GUIDE_SOURCE_URLS["registration_change"]
                ),
                ClassRetakeGuideSource(services.CLASS_GUIDE_SOURCE_URLS["retake"]),
                ClassCourseCancellationGuideSource(
                    services.CLASS_GUIDE_SOURCE_URLS["course_cancellation"]
                ),
                ClassCourseEvaluationGuideSource(
                    services.CLASS_GUIDE_SOURCE_URLS["course_evaluation"]
                ),
                ClassExcusedAbsenceGuideSource(
                    services.CLASS_GUIDE_SOURCE_URLS["excused_absence"]
                ),
                ClassForeignLanguageRequirementGuideSource(
                    services.CLASS_GUIDE_SOURCE_URLS["foreign_language_requirement"]
                ),
            ):
                rows.extend(source.parse(source.fetch(), fetched_at=captured_at))
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/seasonal-semester-guides":
        cache_key = "seasonal_semester_guides"
        if cache_key not in source_cache:
            source = SeasonalSemesterGuideSource(services.SEASONAL_SEMESTER_GUIDE_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/academic-milestone-guides":
        cache_key = "academic_milestone_guides"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            for source in (
                GradeEvaluationGuideSource(
                    services.ACADEMIC_MILESTONE_GUIDE_SOURCE_URLS["grade_evaluation"]
                ),
                GraduationRequirementGuideSource(
                    services.ACADEMIC_MILESTONE_GUIDE_SOURCE_URLS["graduation_requirement"]
                ),
                ):
                    rows.extend(source.parse(source.fetch(), fetched_at=captured_at))
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/student-exchange-guides":
        cache_key = "student_exchange_guides"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            for source in (
                StudentExchangeDomesticCreditExchangeGuideSource(
                    services.STUDENT_EXCHANGE_GUIDE_SOURCE_URLS["domestic_credit_exchange"]
                ),
                StudentExchangeDomesticPartnerUniversitiesGuideSource(
                    services.STUDENT_EXCHANGE_GUIDE_SOURCE_URLS["domestic_partner_universities"]
                ),
                StudentExchangeExchangeStudentGuideSource(
                    services.STUDENT_EXCHANGE_GUIDE_SOURCE_URLS["exchange_student"]
                ),
                StudentExchangeExchangeProgramsGuideSource(
                    services.STUDENT_EXCHANGE_GUIDE_SOURCE_URLS["exchange_programs"]
                ),
            ):
                rows.extend(source.parse(source.fetch(), fetched_at=captured_at))
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/student-activity-guides":
        cache_key = "student_activity_guides"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            for source in (
                StudentGovernmentGuideSource(
                    services.STUDENT_ACTIVITY_GUIDE_SOURCE_URLS["student_government"]
                ),
                CampusMediaGuideSource(services.STUDENT_ACTIVITY_GUIDE_SOURCE_URLS["campus_media"]),
                SocialVolunteeringGuideSource(
                    services.STUDENT_ACTIVITY_GUIDE_SOURCE_URLS["social_volunteering"]
                ),
                RotcGuideSource(services.STUDENT_ACTIVITY_GUIDE_SOURCE_URLS["rotc"]),
            ):
                rows.extend(source.parse(source.fetch(), fetched_at=captured_at))
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/student-exchange-partners":
        cache_key = "student_exchange_partners"
        if cache_key not in source_cache:
            source = StudentExchangePartnerSource(
                landing_url=services.STUDENT_EXCHANGE_PARTNER_SOURCE_URL,
                list_url=services.STUDENT_EXCHANGE_PARTNER_LIST_URL,
            )
            source_cache[cache_key] = source.parse(
                source.fetch(),
                fetched_at=captured_at,
            )
        return _search_student_exchange_partner_rows(
            list(source_cache[cache_key]),
            query=row.api_request.params.get("query"),
            limit=limit,
        )
    if path == "/dormitory-guides":
        cache_key = "dormitory_guides"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            try:
                from .ingest.official_sources import (
                    DormitoryHomepageGuideSource,
                    DormitorySongsimGuideSource,
                )

                for source in (
                    DormitorySongsimGuideSource(services.DORMITORY_SONGSIM_SOURCE_URL),
                    DormitoryHomepageGuideSource(services.DORMITORY_HOME_SOURCE_URL),
                ):
                    rows.extend(source.parse(source.fetch(), fetched_at=captured_at))
            except Exception:
                rows = []
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/campus-life-support-guides":
        cache_key = "campus_life_support_guides"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            for source in (
                HealthCenterGuideSource(services.HEALTH_CENTER_GUIDE_SOURCE_URL),
                LostFoundGuideSource(services.LOST_FOUND_GUIDE_SOURCE_URL),
                ParkingGuideSource(services.CAMPUS_PARKING_GUIDE_SOURCE_URL),
            ):
                rows.extend(source.parse(source.fetch(), fetched_at=captured_at))
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if topic := row.api_request.params.get("topic"):
            rows = [item for item in rows if item.get("topic") == topic]
        return rows[:limit]
    if path == "/pc-software":
        cache_key = "pc_software_entries"
        if cache_key not in source_cache:
            source = PCSoftwareSource(services.OFFICIAL_PC_SOFTWARE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        rows = list(source_cache[cache_key])
        return rank_pc_software_rows(rows, query=row.api_request.params.get("query"), limit=limit)
    if path == "/phone-book":
        cache_key = "phone_book_entries"
        if cache_key not in source_cache:
            source = PhoneBookSource(services.PHONE_BOOK_SOURCE_URL)
            source_cache[cache_key] = source.parse(source.fetch(), fetched_at=captured_at)
        return _search_phone_book_rows(
            list(source_cache[cache_key]),
            query=row.api_request.params.get("query"),
            limit=limit,
        )
    if path == "/campus-life-notices":
        topic_filter = str(row.api_request.params.get("topic") or "").strip() or "all_topics"
        cache_key = f"campus_life_notices:{topic_filter}"
        if cache_key not in source_cache:
            rows: list[dict[str, Any]] = []
            sources = [
                CampusLifeOutsideAgenciesNoticeBoardSource(),
                CampusLifeEventsNoticeBoardSource(),
            ]
            for source in sources:
                default_category = (
                    "행사안내"
                    if getattr(source, "topic", "") == "events"
                    else "외부기관공지"
                )
                for item in source.parse_list(source.fetch_list(limit=50)):
                    article_no = str(item.get("article_no") or "").strip()
                    if not article_no:
                        continue
                    detail = source.parse_detail(
                        source.fetch_detail(article_no, limit=50),
                        default_title=item.get("title", ""),
                        default_category=default_category,
                        default_summary=item.get("summary", ""),
                        default_published_at=item.get("published_at", ""),
                        default_source_url=item.get("source_url"),
                    )
                    rows.append(
                        {
                            "topic": detail.get("topic")
                            or item.get("topic")
                            or getattr(source, "topic", None)
                            or "outside_agencies",
                            "title": detail.get("title") or item.get("title") or "",
                            "published_at": detail.get("published_at") or item.get("published_at"),
                            "summary": detail.get("summary") or item.get("summary") or "",
                            "source_url": detail.get("source_url") or item.get("source_url"),
                            "source_tag": detail.get("source_tag") or source.source_tag,
                            "last_synced_at": captured_at,
                        }
                    )
            rows = _dedupe_topic_local_first_seen_rows(rows)
            rows.sort(
                key=lambda item: (
                    str(item.get("published_at") or ""),
                    str(item.get("title") or ""),
                ),
                reverse=True,
            )
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        topic = row.api_request.params.get("topic")
        if topic:
            rows = [item for item in rows if item.get("topic") == topic]
        query = str(row.api_request.params.get("query") or "").strip()
        if query:
            lowered = query.casefold()
            title_hits = [
                item for item in rows if lowered in str(item.get("title") or "").casefold()
            ]
            summary_hits = [
                item
                for item in rows
                if item not in title_hits
                and lowered in str(item.get("summary") or "").casefold()
            ]
            rows = title_hits + summary_hits
        return rows[:limit]
    if path == "/academic-calendar":
        start_date, end_date = _current_academic_year_bounds()
        cache_key = f"academic_calendar:{start_date}:{end_date}"
        if cache_key not in source_cache:
            source = AcademicCalendarSource(services.ACADEMIC_CALENDAR_SOURCE_URL)
            source_cache[cache_key] = source.parse(
                source.fetch_range(start_date=start_date, end_date=end_date),
                fetched_at=captured_at,
            )
        indexed_rows = list(enumerate(source_cache[cache_key]))
        if academic_year := row.api_request.params.get("academic_year"):
            indexed_rows = [
                (index, item)
                for index, item in indexed_rows
                if item.get("academic_year") == academic_year
            ]
        if month := row.api_request.params.get("month"):
            start_date, end_date = services._academic_month_bounds(
                row.api_request.params.get("academic_year") or _current_academic_year(),
                int(month),
            )
            indexed_rows = [
                (index, item)
                for index, item in indexed_rows
                if (
                    str(item.get("end_date", "")) >= start_date
                    and str(item.get("start_date", "")) <= end_date
                )
            ]
        if query := row.api_request.params.get("query"):
            indexed_rows = [
                (index, item)
                for index, item in indexed_rows
                if str(query).lower() in str(item.get("title", "")).lower()
            ]
        indexed_rows.sort(
            key=lambda pair: (
                0 if "성심" in pair[1].get("campuses", []) else 1,
                pair[1].get("start_date"),
                pair[1].get("end_date"),
                pair[1].get("title"),
                pair[0],
            )
        )
        return [item for _, item in indexed_rows[:limit]]
    if path == "/notices":
        cache_key = "notices_latest_30"
        if cache_key not in source_cache:
            source = NoticeSource(services.NOTICE_SOURCE_URL)
            rows: list[dict[str, Any]] = []
            seen_articles: set[str] = set()
            for offset in (0, 10, 20):
                list_html = source.fetch_list(offset=offset, limit=10)
                for item in source.parse_list(list_html):
                    article_no = str(item.get("article_no") or "").strip()
                    if not article_no or article_no in seen_articles:
                        continue
                    seen_articles.add(article_no)
                    detail_html = source.fetch_detail(article_no, offset=offset, limit=10)
                    detail = source.parse_detail(
                        detail_html,
                        default_title=item.get("title", ""),
                        default_category=item.get("board_category", ""),
                    )
                    detail = services._canonicalize_notice_detail(item=item, detail=detail)
                    rows.append(
                        {
                            "article_no": article_no,
                            "title": detail.get("title") or item.get("title"),
                            "published_at": detail.get("published_at") or item.get("published_at"),
                            "summary": detail.get("summary", ""),
                            "labels": detail.get("labels", []),
                            "raw_category": detail.get("category"),
                            "category": services._normalize_notice_public_category(
                                detail.get("category")
                            ),
                            "source_url": item.get("source_url"),
                        }
                    )
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        if category := row.api_request.params.get("category"):
            normalized = services._normalize_notice_category_filter(category)
            rows = [item for item in rows if item.get("raw_category") in normalized]
        rows.sort(
            key=lambda item: (
                str(item.get("published_at") or ""),
                (
                    int(str(item.get("article_no") or "0"))
                    if str(item.get("article_no") or "").isdigit()
                    else 0
                ),
            ),
            reverse=True,
        )
        return rows[:limit]
    if path == "/affiliated-notices":
        topic_filter = str(row.api_request.params.get("topic") or "").strip() or "all_topics"
        cache_key = f"affiliated_notices:{topic_filter}"
        if cache_key not in source_cache:
            board_specs = [
                (
                    "international_studies",
                    "https://is.catholic.ac.kr/is/community/notice.do",
                ),
                (
                    "dorm_k_a_general",
                    "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do",
                ),
                (
                    "dorm_k_a_checkin_out",
                    "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice1.do",
                ),
                (
                    "dorm_francis_general",
                    "https://dorm.catholic.ac.kr/dormitory/board/comm_notice3.do",
                ),
                (
                    "dorm_francis_checkin_out",
                    "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice.do",
                ),
            ]
            rows: list[dict[str, Any]] = []
            for topic, url in board_specs:
                if topic_filter != "all_topics" and topic_filter != topic:
                    continue
                source = NoticeSource(url)
                list_html = source.fetch_list(limit=50)
                for item in source.parse_list(list_html):
                    article_no = str(item.get("article_no") or "").strip()
                    if not article_no:
                        continue
                    detail_html = source.fetch_detail(article_no, limit=50)
                    detail = source.parse_detail(
                        detail_html,
                        default_title=item.get("title", ""),
                        default_category=item.get("board_category", ""),
                    )
                    payload = {
                        "article_no": article_no,
                        "topic": topic,
                        "title": detail.get("title") or item.get("title") or "",
                        "published_at": detail.get("published_at") or item.get("published_at"),
                        "summary": detail.get("summary") or "",
                        "source_url": item.get("source_url"),
                        "source_tag": "cuk_affiliated_notice_boards",
                        "last_synced_at": captured_at,
                    }
                    rows.append(payload)
            rows = _dedupe_topic_local_first_seen_rows(rows)
            rows.sort(
                key=lambda item: (
                    str(item.get("published_at") or ""),
                    str(item.get("title") or ""),
                ),
                reverse=True,
            )
            source_cache[cache_key] = rows
        rows = list(source_cache[cache_key])
        topic = row.api_request.params.get("topic")
        if topic:
            rows = [item for item in rows if item.get("topic") == topic]
        query = str(row.api_request.params.get("query") or "").strip()
        if query:
            lowered = " ".join(query.split()).casefold()
            matched_rows = [
                item
                for item in rows
                if lowered in f"{item.get('title', '')} {item.get('summary', '')}".casefold()
            ]
            if matched_rows:
                rows = matched_rows
        return rows[:limit]
    return None


def build_truth_rows(
    rows: list[EvalCorpusRow],
    *,
    database_url: str | None,
    captured_at: str | None = None,
) -> list[EvalTruthRow]:
    resolved_captured_at = captured_at or _now_iso()
    results: list[EvalTruthRow] = []
    payload_cache: dict[tuple[str | None, str | None, str], tuple[Any | None, str, str]] = {}
    source_cache: dict[str, Any] = {}

    conn: psycopg.Connection | None = None
    if database_url:
        conn = psycopg.connect(database_url, row_factory=dict_row)

    try:
        for row in rows:
            if row.truth_mode == "watch_only":
                results.append(
                    EvalTruthRow(
                        id=row.id,
                        normalized_expected=None,
                        truth_source="watchlist",
                        captured_at=resolved_captured_at,
                        stability="watch_only",
                    )
                )
                continue

            cache_key = _request_cache_key(row)
            cached_payload = payload_cache.get(cache_key)
            if cached_payload is None:
                payload: Any | None = None
                summary_kind = str(row.pass_rule.get("summary_kind") or "")
                prefer_official_source = row.api_request.path == "/notices" or (
                    row.api_request.path == "/places"
                    and summary_kind == "places_top1_alias_display"
                )
                use_official_source = prefer_official_source or conn is None
                truth_source = "official_source" if use_official_source else "database_snapshot"
                stability = "stable"
                if not prefer_official_source and conn is not None:
                    try:
                        payload = _payload_from_db(conn, row)
                    except ValueError:
                        payload = _payload_from_sources(
                            row,
                            captured_at=resolved_captured_at,
                            source_cache=source_cache,
                        )
                        truth_source = "official_source"
                        stability = "stable" if payload is not None else "degraded_skip"
                    else:
                        if (
                            row.api_request.path == "/places"
                            and summary_kind == "places_top1_facility_host"
                            and _normalize_truth_payload(row, payload) is None
                        ):
                            payload = _payload_from_sources(
                                row,
                                captured_at=resolved_captured_at,
                                source_cache=source_cache,
                            )
                            truth_source = "official_source"
                            stability = "stable" if payload is not None else "degraded_skip"
                else:
                    payload = _payload_from_sources(
                        row,
                        captured_at=resolved_captured_at,
                        source_cache=source_cache,
                    )
                    truth_source = "official_source"
                    stability = "stable" if payload is not None else "degraded_skip"
                payload_cache[cache_key] = (payload, truth_source, stability)
            else:
                payload, truth_source, stability = cached_payload

            normalized_expected = (
                _normalize_truth_payload(row, payload) if payload is not None else None
            )
            results.append(
                EvalTruthRow(
                    id=row.id,
                    normalized_expected=normalized_expected,
                    truth_source=truth_source if payload is not None else "unavailable",
                    captured_at=resolved_captured_at,
                    stability=stability,
                )
            )
    finally:
        if conn is not None:
            conn.close()

    return results


def run_row_evaluation(
    row: EvalCorpusRow,
    *,
    actual_payload: Any,
    truth: EvalTruthRow | None,
    checked_at: str | None = None,
) -> EvalResultRow:
    resolved_checked_at = checked_at or _now_iso()
    actual_summary = _summarize_payload(
        actual_payload if row.api_request.policy is None else _build_policy_summary(row),
        summary_kind=str(row.pass_rule.get("summary_kind") or ""),
    )

    if row.truth_mode == "watch_only":
        return EvalResultRow(
            id=row.id,
            status="completed",
            verdict="watch",
            actual_summary=actual_summary,
            comparison="watch_only",
            truth_source=truth.truth_source if truth else "watchlist",
            checked_at=resolved_checked_at,
        )

    if row.truth_mode == "invariant_only":
        verdict, comparison = _evaluate_invariants(row, actual_summary)
        return EvalResultRow(
            id=row.id,
            status="completed",
            verdict=verdict,
            actual_summary=actual_summary,
            comparison=comparison,
            truth_source=truth.truth_source if truth else None,
            checked_at=resolved_checked_at,
        )

    if truth is None or truth.normalized_expected is None:
        return EvalResultRow(
            id=row.id,
            status="skipped",
            verdict="skip",
            actual_summary=actual_summary,
            comparison="missing_truth",
            truth_source=truth.truth_source if truth else None,
            checked_at=resolved_checked_at,
        )

    if row.truth_mode == "exact_value":
        verdict = "pass" if actual_summary == truth.normalized_expected else "fail"
        comparison = "exact_match" if verdict == "pass" else "exact_mismatch"
        return EvalResultRow(
            id=row.id,
            status="completed",
            verdict=verdict,
            actual_summary=actual_summary,
            comparison=comparison,
            truth_source=truth.truth_source,
            checked_at=resolved_checked_at,
        )

    verdict = "pass" if _subset_match(truth.normalized_expected, actual_summary) else "fail"
    comparison = "set_contains" if verdict == "pass" else "set_mismatch"
    return EvalResultRow(
        id=row.id,
        status="completed",
        verdict=verdict,
        actual_summary=actual_summary,
        comparison=comparison,
        truth_source=truth.truth_source,
        checked_at=resolved_checked_at,
    )


def _load_actual_payload(
    base_url: str,
    row: EvalCorpusRow,
    *,
    params_override: dict[str, Any] | None = None,
) -> Any:
    if row.api_request.policy and row.api_request.path is None:
        return _build_policy_summary(row)
    if row.api_request.path is None:
        return None
    request_url = f"{base_url.rstrip('/')}{row.api_request.path}"
    request_params = params_override or row.api_request.params
    last_error: httpx.HTTPError | None = None
    for attempt in range(PUBLIC_EVAL_HTTP_RETRIES + 1):
        try:
            response = httpx.get(
                request_url,
                params=request_params,
                timeout=PUBLIC_EVAL_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            last_error = exc
            if attempt >= PUBLIC_EVAL_HTTP_RETRIES:
                raise
            time.sleep(0.25 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("unreachable")


def run_evaluation(
    *,
    base_url: str,
    rows: list[EvalCorpusRow],
    truth_rows: list[EvalTruthRow],
    checked_at: str | None = None,
) -> list[EvalResultRow]:
    resolved_checked_at = checked_at or _now_iso()
    truth_by_id = _truth_lookup(truth_rows)
    results: list[EvalResultRow] = []
    payload_cache: dict[tuple[str | None, str | None, str], Any] = {}
    error_cache: dict[tuple[str | None, str | None, str], httpx.HTTPError] = {}
    max_limit_by_key: dict[tuple[str | None, str | None, str], int] = {}
    params_by_key: dict[tuple[str | None, str | None, str], dict[str, Any]] = {}
    representative_row_by_key: dict[tuple[str | None, str | None, str], EvalCorpusRow] = {}
    for row in rows:
        coarse_key = _coarse_request_cache_key(row)
        representative_row_by_key.setdefault(coarse_key, row)
        params = dict(row.api_request.params)
        raw_limit = params.get("limit")
        if raw_limit is None:
            params_by_key.setdefault(coarse_key, params)
            continue
        try:
            limit_value = int(raw_limit)
        except (TypeError, ValueError):
            limit_value = 0
        current_limit = max_limit_by_key.get(coarse_key, 0)
        if limit_value >= current_limit:
            max_limit_by_key[coarse_key] = limit_value
            params_by_key[coarse_key] = params

    unique_requests = [
        (cache_key, representative_row_by_key[cache_key], params_by_key.get(cache_key))
        for cache_key in representative_row_by_key
    ]
    max_workers = min(PUBLIC_EVAL_MAX_WORKERS, max(1, len(unique_requests)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_key = {
            executor.submit(
                _load_actual_payload,
                base_url,
                request_row,
                params_override=params_override,
            ): cache_key
            for cache_key, request_row, params_override in unique_requests
        }
        for future in as_completed(future_by_key):
            cache_key = future_by_key[future]
            try:
                payload_cache[cache_key] = future.result()
            except httpx.HTTPError as exc:
                error_cache[cache_key] = exc

    for row in rows:
        cache_key = _coarse_request_cache_key(row)
        truth = truth_by_id.get(row.id)
        if cache_key in error_cache:
            exc = error_cache[cache_key]
            results.append(
                EvalResultRow(
                    id=row.id,
                    status="error",
                    verdict="fail",
                    actual_summary=None,
                    comparison=f"http_error:{exc.__class__.__name__}",
                    truth_source=truth.truth_source if truth else None,
                    checked_at=resolved_checked_at,
                )
            )
            continue
        results.append(
            run_row_evaluation(
                row,
                actual_payload=payload_cache.get(cache_key),
                truth=truth,
                checked_at=resolved_checked_at,
            )
        )
    return results


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _render_report_cell(value: Any, *, max_length: int = 240) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        text = f"{text[: max_length - 3]}..."
    return text.replace("|", "\\|")


def render_validation_report(
    *,
    rows: list[EvalCorpusRow],
    results: list[EvalResultRow | dict[str, Any]],
    checked_at: str,
    base_url: str,
) -> str:
    normalized_results = [
        item if isinstance(item, EvalResultRow) else EvalResultRow.model_validate(item)
        for item in results
    ]
    main_corpus_rows = [row for row in rows if row.truth_mode != "watch_only"]
    row_by_id = {row.id: row for row in rows}
    result_by_id = {result.id: result for result in normalized_results}
    pass_like_verdicts = {"pass", "soft_pass"}

    verdict_counter = Counter(result.verdict for result in normalized_results)
    corpus_counter = Counter(row.domain for row in rows if row.truth_mode != "watch_only")
    guide_domains = [
        "academic_calendar",
        "affiliated_notices",
        "campus_life_notices",
        "certificate_guides",
        "dormitory_guides",
        "campus_life_support_guides",
        "pc_software_entries",
        "registration_guides",
        "class_guides",
        "seasonal_semester_guides",
        "academic_milestone_guides",
        "student_activity_guides",
        "phone_book",
        "scholarship_guides",
        "wifi_guides",
        "leave_of_absence_guides",
        "academic_support_guides",
        "student_exchange_partners",
    ]
    missing_result = EvalResultRow(
        id="",
        status="missing",
        verdict="skip",
        comparison="missing_result",
        checked_at=checked_at,
    )

    domain_rows = [
        [
            domain,
            str(count),
            str(
                sum(
                    1
                    for row in rows
                    if row.domain == domain
                    and result_by_id.get(row.id, missing_result).verdict in pass_like_verdicts
                )
            ),
        ]
        for domain, count in sorted(corpus_counter.items())
    ]
    guide_rows = [
        [
            domain,
            str(sum(1 for row in rows if row.domain == domain)),
            str(
                sum(
                    1
                    for result in normalized_results
                    if row_by_id.get(result.id)
                    and row_by_id[result.id].domain == domain
                    and result.verdict in pass_like_verdicts
                )
            ),
        ]
        for domain in guide_domains
    ]
    watch_rows = [
        [
            result.id,
            _render_report_cell(row_by_id[result.id].user_utterance),
            result.verdict,
            row_by_id[result.id].watch_policy,
            result.comparison,
            _render_report_cell(row_by_id[result.id].notes),
            _render_report_cell(result.actual_summary),
        ]
        for result in normalized_results
        if result.verdict == "watch" and result.id in row_by_id
    ]
    issue_rows = [
        [
            result.id,
            row_by_id[result.id].domain,
            row_by_id[result.id].user_utterance,
            result.verdict,
            result.comparison,
        ]
        for result in normalized_results
        if result.verdict in {"soft_fail", "fail", "skip"} and result.id in row_by_id
    ]
    verdict_order = ["pass", "soft_pass", "soft_fail", "fail", "watch", "skip"]
    verdict_rows = [[key, str(verdict_counter.get(key, 0))] for key in verdict_order]
    watch_table = _render_table(
        ["ID", "User utterance", "Verdict", "Watch policy", "Comparison", "Notes", "Actual"],
        watch_rows,
    )
    issue_table = _render_table(
        ["ID", "Domain", "User utterance", "Verdict", "Comparison"],
        issue_rows[:50],
    )

    return (
        "\n".join(
            [
                "# Public API Live Validation Baseline",
                "",
                "API-first public student surface baseline with live-synced truth.",
                "",
                "## 실행 기준",
                "",
                f"- base_url: `{base_url}`",
                "- evaluation mode: public API first",
                "- truth mode: live-synced normalized truth",
                "- shared GPT / `/gpt/*` / UI flows are excluded from this baseline",
                "",
                "## 실행 메타",
                "",
                f"- checked_at: `{checked_at}`",
                f"- corpus_size: `{len(main_corpus_rows)}`",
                f"- executed: `{len(normalized_results)}`",
                f"  - includes `{len(rows) - len(main_corpus_rows)}` watchlist rows",
                f"- hard fail {verdict_counter.get('fail', 0)}",
                "",
                "## 판정 레벨",
                "",
                "- `pass`: normalized truth or invariant matched",
                "- `soft_pass`: reserved for future manual review overlay",
                "- `soft_fail`: reserved for future manual review overlay",
                "- `fail`: hard mismatch against normalized truth or invariants",
                "- `watch`: source-gap watchlist item",
                "- `skip`: truth unavailable in degraded mode",
                "",
                "## 집계",
                "",
                _render_table(["Verdict", "Count"], verdict_rows),
                "",
                "## 도메인 요약",
                "",
                _render_table(["Domain", "Cases", "Pass-like"], domain_rows),
                "",
                "## Guide-Domain Coverage",
                "",
                _render_table(["Domain", "Cases", "Pass-like"], guide_rows),
                "",
                "## Watchlist (hard fail 제외)",
                "",
                watch_table or "_No watch items._",
                "",
                "## 주요 이슈",
                "",
                issue_table or "_No hard issues._",
                "",
                "## 다음 액션",
                "",
                "- Keep the course source-gap watchlist separate from hard fail counts.",
                "- Re-run `songsim-eval-public sync-truth` before large public releases.",
                "- Promote only stable canaries into the 50-question release gate.",
                "",
            ]
        ).strip()
        + "\n"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run public API-first Songsim evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync-truth")
    sync_parser.add_argument("--base-url", default="https://songsim-public-api.onrender.com")
    sync_parser.add_argument("--database-url", default=os.environ.get("SONGSIM_DATABASE_URL"))
    sync_parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_PATH))
    sync_parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST_PATH))
    sync_parser.add_argument("--output", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--base-url", default="https://songsim-public-api.onrender.com")
    run_parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_PATH))
    run_parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST_PATH))
    run_parser.add_argument("--truth", required=True)
    run_parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH))
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "sync-truth":
        corpus_rows = load_eval_rows(args.corpus)
        watchlist_rows = load_eval_rows(args.watchlist)
        truth_rows = build_truth_rows(
            corpus_rows + watchlist_rows,
            database_url=args.database_url,
            captured_at=_now_iso(),
        )
        _write_jsonl(Path(args.output), truth_rows)
        print(
            json.dumps(
                {"truth_rows": len(truth_rows), "output": args.output},
                ensure_ascii=False,
            )
        )
        return

    corpus_rows = load_eval_rows(args.corpus)
    watchlist_rows = load_eval_rows(args.watchlist)
    truth_rows = load_truth_rows(args.truth)
    results = run_evaluation(
        base_url=args.base_url,
        rows=corpus_rows + watchlist_rows,
        truth_rows=truth_rows,
        checked_at=_now_iso(),
    )
    report = render_validation_report(
        rows=corpus_rows + watchlist_rows,
        results=results,
        checked_at=_now_iso(),
        base_url=args.base_url,
    )
    Path(args.report).write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "results": len(results),
                "report": args.report,
                "fail": sum(1 for item in results if item.verdict == "fail"),
                "watch": sum(1 for item in results if item.verdict == "watch"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
