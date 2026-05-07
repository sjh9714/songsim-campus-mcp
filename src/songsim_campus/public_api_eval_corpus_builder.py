from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path
from typing import Any, Literal

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
    "student_activity_notices",
    "service_policy_guides",
    "student_exchange_partners",
    "campus_life_support_guides",
    "pc_software_entries",
    "phone_book",
    "dormitory_guides",
    "out_of_scope",
]
EvalStyle = Literal["normal", "alias", "composite", "typo", "ambiguous", "out_of_scope"]
TruthMode = Literal["exact_value", "set_contains", "invariant_only", "watch_only"]

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_PATH = ROOT_DIR / "data" / "qa" / "public_api_eval_corpus_1000.jsonl"

DOMAIN_ORDER: tuple[EvalDomain, ...] = (
    "place",
    "courses",
    "restaurants",
    "notices",
    "academic_calendar",
    "classrooms",
    "transport",
    "certificate_guides",
    "scholarship_guides",
    "wifi_guides",
    "leave_of_absence_guides",
    "academic_support_guides",
    "registration_guides",
    "class_guides",
    "seasonal_semester_guides",
    "academic_milestone_guides",
    "phone_book",
    "affiliated_notices",
    "campus_life_notices",
    "campus_life_support_guides",
    "dormitory_guides",
    "pc_software_entries",
    "student_exchange_guides",
    "student_exchange_partners",
    "student_activity_guides",
    "student_activity_notices",
    "service_policy_guides",
    "out_of_scope",
)
STYLE_ORDER: tuple[EvalStyle, ...] = (
    "normal",
    "composite",
    "alias",
    "typo",
    "ambiguous",
    "out_of_scope",
)
TRUTH_ORDER: tuple[TruthMode, ...] = ("set_contains", "invariant_only", "exact_value")

DOMAIN_QUOTAS: dict[EvalDomain, int] = {
    "place": 140,
    "courses": 140,
    "restaurants": 100,
    "notices": 80,
    "academic_calendar": 55,
    "classrooms": 40,
    "transport": 25,
    "certificate_guides": 12,
    "scholarship_guides": 12,
    "wifi_guides": 10,
    "leave_of_absence_guides": 12,
    "academic_support_guides": 12,
    "registration_guides": 25,
    "class_guides": 35,
    "seasonal_semester_guides": 10,
    "academic_milestone_guides": 25,
    "phone_book": 35,
    "affiliated_notices": 35,
    "campus_life_notices": 25,
    "campus_life_support_guides": 30,
    "dormitory_guides": 20,
    "pc_software_entries": 20,
    "student_exchange_guides": 25,
    "student_exchange_partners": 32,
    "student_activity_guides": 15,
    "student_activity_notices": 5,
    "service_policy_guides": 5,
    "out_of_scope": 20,
}

STYLE_QUOTAS: dict[EvalStyle, int] = {
    "normal": 620,
    "composite": 150,
    "alias": 90,
    "typo": 80,
    "ambiguous": 40,
    "out_of_scope": 20,
}

TRUTH_MODE_QUOTAS: dict[TruthMode, int] = {
    "set_contains": 610,
    "invariant_only": 300,
    "exact_value": 90,
}

DOMAIN_TRUTH_COUNTS: dict[EvalDomain, dict[TruthMode, int]] = {
    "place": {"set_contains": 140},
    "courses": {"set_contains": 140},
    "restaurants": {"set_contains": 100},
    "notices": {"set_contains": 80},
    "academic_calendar": {"invariant_only": 55},
    "classrooms": {"invariant_only": 40},
    "transport": {"invariant_only": 25},
    "certificate_guides": {"exact_value": 12},
    "scholarship_guides": {"exact_value": 12},
    "wifi_guides": {"exact_value": 10},
    "leave_of_absence_guides": {"exact_value": 12},
    "academic_support_guides": {"exact_value": 12},
    "registration_guides": {"invariant_only": 25},
    "class_guides": {"invariant_only": 35},
    "seasonal_semester_guides": {"exact_value": 10},
    "academic_milestone_guides": {"exact_value": 22, "invariant_only": 3},
    "phone_book": {"set_contains": 35},
    "affiliated_notices": {"set_contains": 35},
    "campus_life_notices": {"set_contains": 25},
    "campus_life_support_guides": {"invariant_only": 30},
    "dormitory_guides": {"invariant_only": 20},
    "pc_software_entries": {"invariant_only": 20},
    "student_exchange_guides": {"set_contains": 23, "invariant_only": 2},
    "student_exchange_partners": {"set_contains": 32},
    "student_activity_guides": {"invariant_only": 15},
    "student_activity_notices": {"invariant_only": 5},
    "service_policy_guides": {"invariant_only": 5},
    "out_of_scope": {"invariant_only": 20},
}

ID_PREFIXES: dict[EvalDomain, str] = {
    "place": "PLC-",
    "courses": "CRS-",
    "restaurants": "RST-",
    "notices": "NTC-",
    "academic_calendar": "ACD-",
    "classrooms": "CLR-",
    "transport": "TRN-",
    "certificate_guides": "CTG-",
    "scholarship_guides": "SCG-",
    "wifi_guides": "WFG-",
    "leave_of_absence_guides": "LOG-",
    "academic_support_guides": "ASG-",
    "registration_guides": "RG-",
    "class_guides": "CG-",
    "seasonal_semester_guides": "SSG-",
    "academic_milestone_guides": "AMG-",
    "phone_book": "PB-",
    "affiliated_notices": "AFN-",
    "campus_life_notices": "CLN-",
    "campus_life_support_guides": "CLS-CANARY-",
    "dormitory_guides": "DG-",
    "pc_software_entries": "PCS-CANARY-",
    "student_exchange_guides": "SEX-",
    "student_exchange_partners": "SEP-",
    "student_activity_guides": "SAV-",
    "student_activity_notices": "SAN-",
    "service_policy_guides": "SPG-",
    "out_of_scope": "OOS-",
}

ID_WIDTHS: dict[EvalDomain, int] = {
    "campus_life_support_guides": 3,
    "pc_software_entries": 3,
}

HIGH_REPEAT_STYLE_COUNTS: dict[EvalDomain, dict[EvalStyle, int]] = {
    "place": {"normal": 82, "composite": 20, "alias": 15, "typo": 15, "ambiguous": 8},
    "courses": {"normal": 82, "composite": 20, "alias": 15, "typo": 15, "ambiguous": 8},
    "restaurants": {"normal": 59, "composite": 16, "alias": 10, "typo": 10, "ambiguous": 5},
    "notices": {"normal": 47, "composite": 12, "alias": 8, "typo": 8, "ambiguous": 5},
    "academic_calendar": {"normal": 33, "composite": 8, "alias": 5, "typo": 5, "ambiguous": 4},
    "classrooms": {"normal": 24, "composite": 6, "alias": 4, "typo": 4, "ambiguous": 2},
    "transport": {"normal": 15, "composite": 4, "alias": 3, "typo": 2, "ambiguous": 1},
    "phone_book": {"normal": 20, "composite": 5, "alias": 4, "typo": 4, "ambiguous": 2},
    "affiliated_notices": {"normal": 20, "composite": 5, "alias": 4, "typo": 4, "ambiguous": 2},
    "campus_life_notices": {"normal": 15, "composite": 4, "alias": 3, "typo": 2, "ambiguous": 1},
    "student_exchange_partners": {
        "normal": 18,
        "composite": 5,
        "alias": 4,
        "typo": 3,
        "ambiguous": 2,
    },
    "out_of_scope": {"out_of_scope": 20},
}

LOW_KEY_COMPOSITE_ORDER: tuple[EvalDomain, ...] = (
    "registration_guides",
    "class_guides",
    "academic_milestone_guides",
    "campus_life_support_guides",
    "student_exchange_guides",
    "student_activity_guides",
    "dormitory_guides",
    "pc_software_entries",
    "certificate_guides",
    "scholarship_guides",
    "wifi_guides",
    "leave_of_absence_guides",
    "academic_support_guides",
    "seasonal_semester_guides",
)
LOW_KEY_ALIAS_ORDER: tuple[EvalDomain, ...] = (
    "certificate_guides",
    "scholarship_guides",
    "wifi_guides",
    "leave_of_absence_guides",
    "academic_support_guides",
    "registration_guides",
    "class_guides",
    "seasonal_semester_guides",
    "academic_milestone_guides",
    "campus_life_support_guides",
    "dormitory_guides",
    "pc_software_entries",
    "student_exchange_guides",
    "student_activity_guides",
)
LOW_KEY_TYPO_ORDER: tuple[EvalDomain, ...] = (
    "leave_of_absence_guides",
    "academic_support_guides",
    "registration_guides",
    "class_guides",
    "academic_milestone_guides",
    "campus_life_support_guides",
    "pc_software_entries",
    "student_exchange_guides",
)

# `notices` was originally considered repeat-heavy, but the supported public request matrix
# is category-only and cannot satisfy 80 rows under a strict coarse-key <= 4 cap.
COARSE_CAP_ENFORCED_DOMAINS: tuple[EvalDomain, ...] = (
    "place",
    "courses",
    "restaurants",
    "academic_calendar",
    "classrooms",
    "transport",
    "phone_book",
    "affiliated_notices",
    "campus_life_notices",
    "student_exchange_partners",
)
COARSE_CAP_MAX = 4

STUDENT_ACTIVITY_GUIDE_CANARY_UTTERANCES: dict[str, str] = {
    "campus_media": "교내미디어 뭐 있어?",
    "rotc": "학생군사교육단 안내해줘",
    "social_volunteering": "사회봉사 활동 알려줘",
    "student_government": "총학생회 안내해줘",
}

STYLE_PRIORITY: dict[str, int] = {
    "normal": 0,
    "alias": 1,
    "typo": 2,
    "ambiguous": 3,
    "composite": 4,
    "out_of_scope": 5,
}
ENDING_VARIANTS: tuple[str, ...] = ("알려줘", "보여줘", "안내해줘", "정리해줘", "찾아줘")
COMPOSITE_SUFFIXES: tuple[str, ...] = (
    "먼저 알려주고 핵심만 같이 정리해줘",
    "가능하면 바로 확인할 정보도 같이 알려줘",
    "최신 기준으로 간단히 요약해줘",
    "필요한 포인트만 짧게 알려줘",
    "관련 정보가 있으면 함께 묶어서 알려줘",
)
AMBIGUOUS_SUFFIXES: tuple[str, ...] = (
    "관련해서 뭐 보면 돼?",
    "쪽 정보가 필요해",
    "관련된 거 확인하고 싶어",
    "어느 정보부터 보면 돼?",
)
FALLBACK_QUALIFIERS: tuple[str, ...] = (
    "지금 기준으로",
    "학교 공식 기준으로",
    "간단히",
    "핵심만",
    "바로 확인하려고",
    "짧게",
)


@dataclass(frozen=True)
class RequestSeed:
    domain: EvalDomain
    canonical_utterance: str
    api_request: dict[str, Any]
    expected_mcp_flow: str
    pass_rule: dict[str, Any]
    notes: str


def coarse_request_key_from_payload(
    api_request: dict[str, Any], *, truth_mode: str | None = None
) -> tuple[str | None, str | None, str]:
    normalized_params = dict(api_request.get("params") or {})
    if truth_mode != "exact_value":
        normalized_params.pop("limit", None)
    return (
        api_request.get("path"),
        api_request.get("policy"),
        json.dumps(
            normalized_params,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ),
    )


def normalize_utterance_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"[!?.,]{2,}", lambda match: match.group(0)[0], normalized)
    return normalized


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(json.loads(stripped))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _seed_sort_key(seed: RequestSeed) -> tuple[str, str | None, str | None, str, str]:
    return (
        seed.api_request.get("path") or "",
        seed.api_request.get("policy"),
        json.dumps(
            seed.api_request.get("params") or {},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ),
        seed.notes,
        seed.canonical_utterance,
    )


def _representative_seed_rows(
    seed_rows: list[dict[str, Any]],
) -> dict[EvalDomain, list[RequestSeed]]:
    grouped: dict[tuple[EvalDomain, tuple[str | None, str | None, str]], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for item in seed_rows:
        domain = item.get("domain")
        if not domain:
            continue
        grouped[
            (
                domain,
                coarse_request_key_from_payload(
                    item.get("api_request") or {}, truth_mode=item.get("truth_mode")
                ),
            )
        ].append(item)

    representative_rows: dict[EvalDomain, list[RequestSeed]] = defaultdict(list)
    for (domain, _), candidates in grouped.items():
        candidates.sort(
            key=lambda row: (
                STYLE_PRIORITY.get(str(row.get("style") or "normal"), 99),
                len(str(row.get("user_utterance") or "")),
                normalize_utterance_key(str(row.get("user_utterance") or "")),
                str(row.get("id") or ""),
            )
        )
        chosen = candidates[0]
        representative_rows[domain].append(
            RequestSeed(
                domain=domain,
                canonical_utterance=str(chosen.get("user_utterance") or "").strip(),
                api_request=dict(chosen.get("api_request") or {}),
                expected_mcp_flow=str(chosen.get("expected_mcp_flow") or ""),
                pass_rule=dict(chosen.get("pass_rule") or {}),
                notes=str(chosen.get("notes") or ""),
            )
        )

    for domain in representative_rows:
        representative_rows[domain].sort(key=_seed_sort_key)
    return representative_rows


def _seed(
    domain: EvalDomain,
    utterance: str,
    api_request: dict[str, Any],
    expected_mcp_flow: str,
    pass_rule: dict[str, Any],
    notes: str,
) -> RequestSeed:
    return RequestSeed(
        domain=domain,
        canonical_utterance=utterance,
        api_request=api_request,
        expected_mcp_flow=expected_mcp_flow,
        pass_rule=pass_rule,
        notes=notes,
    )


def _place_seed(
    query: str,
    utterance: str,
    *,
    summary_kind: str = "places_top3",
    notes: str,
) -> RequestSeed:
    return _seed(
        "place",
        utterance,
        {"path": "/places", "params": {"query": query, "limit": 5}},
        "tool_search_places -> tool_get_place",
        {"summary_kind": summary_kind},
        notes,
    )


def _course_seed(query: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "courses",
        utterance,
        {"path": "/courses", "params": {"query": query, "year": 2026, "semester": 1, "limit": 5}},
        "tool_search_courses",
        {"summary_kind": "courses_top5"},
        notes,
    )


def _restaurant_nearby_seed(
    utterance: str,
    *,
    origin: str,
    notes: str,
    walk_minutes: int | None = None,
    budget_max: int | None = None,
    open_now: bool | None = None,
    category: str | None = None,
) -> RequestSeed:
    params: dict[str, Any] = {"origin": origin, "limit": 5}
    if walk_minutes is not None:
        params["walk_minutes"] = walk_minutes
    if budget_max is not None:
        params["budget_max"] = budget_max
    if open_now is not None:
        params["open_now"] = open_now
    if category is not None:
        params["category"] = category
    return _seed(
        "restaurants",
        utterance,
        {"path": "/restaurants/nearby", "params": params},
        "tool_find_nearby_restaurants",
        {
            "summary_kind": "restaurants_nearby",
            "allow_empty": True,
            "required_fields": ["name", "origin"],
        },
        notes,
    )


def _restaurant_search_seed(
    query: str,
    utterance: str,
    *,
    notes: str,
    origin: str | None = None,
    category: str | None = None,
) -> RequestSeed:
    params: dict[str, Any] = {"query": query, "limit": 5}
    if origin is not None:
        params["origin"] = origin
    if category is not None:
        params["category"] = category
    return _seed(
        "restaurants",
        utterance,
        {"path": "/restaurants/search", "params": params},
        "tool_search_restaurants",
        {"summary_kind": "restaurants_search_top5", "allow_empty": True},
        notes,
    )


def _notice_seed(category: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "notices",
        utterance,
        {"path": "/notices", "params": {"category": category, "limit": 5}},
        "tool_list_latest_notices",
        {"summary_kind": "notices_top5"},
        notes,
    )


def _calendar_month_seed(month: int, utterance: str) -> RequestSeed:
    return _seed(
        "academic_calendar",
        utterance,
        {
            "path": "/academic-calendar",
            "params": {"academic_year": 2026, "month": month, "limit": 5},
        },
        "tool_list_academic_calendar",
        {"summary_kind": "academic_calendar_top5"},
        str(month),
    )


def _calendar_query_seed(query: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "academic_calendar",
        utterance,
        {
            "path": "/academic-calendar",
            "params": {"academic_year": 2026, "query": query, "limit": 5},
        },
        "tool_list_academic_calendar",
        {"summary_kind": "academic_calendar_top5"},
        notes,
    )


def _classroom_seed(building: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "classrooms",
        utterance,
        {
            "path": "/classrooms/empty",
            "params": {"building": building, "at": "2026-03-16T10:15:00+09:00", "limit": 5},
        },
        "tool_list_estimated_empty_classrooms",
        {"summary_kind": "classrooms_empty", "allow_empty": True},
        notes,
    )


def _transport_seed(
    utterance: str,
    *,
    mode: str,
    notes: str,
    query: str | None = None,
) -> RequestSeed:
    params: dict[str, Any] = {"mode": mode, "limit": 5}
    if query is not None:
        params["query"] = query
    return _seed(
        "transport",
        utterance,
        {"path": "/transport", "params": params},
        "tool_list_transport_guides",
        {"summary_kind": "transport_top5"},
        notes,
    )


def _phone_book_seed(query: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "phone_book",
        utterance,
        {"path": "/phone-book", "params": {"query": query, "limit": 5}},
        "tool_search_phone_book",
        {"summary_kind": "phone_book_top5"},
        notes,
    )


def _affiliated_notice_seed(
    topic: str,
    utterance: str,
    *,
    notes: str,
    query: str | None = None,
) -> RequestSeed:
    params: dict[str, Any] = {"topic": topic, "limit": 5}
    if query is not None:
        params["query"] = query
    return _seed(
        "affiliated_notices",
        utterance,
        {"path": "/affiliated-notices", "params": params},
        "tool_list_affiliated_notices",
        {"summary_kind": "affiliated_notices_top5"},
        notes,
    )


def _campus_life_notice_seed(
    topic: str,
    utterance: str,
    *,
    notes: str,
    query: str | None = None,
) -> RequestSeed:
    params: dict[str, Any] = {"topic": topic, "limit": 5}
    if query is not None:
        params["query"] = query
    return _seed(
        "campus_life_notices",
        utterance,
        {"path": "/campus-life-notices", "params": params},
        "tool_list_campus_life_notices",
        {"summary_kind": "campus_life_notices_top5"},
        notes,
    )


def _partner_seed(query: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "student_exchange_partners",
        utterance,
        {"path": "/student-exchange-partners", "params": {"query": query, "limit": 5}},
        "tool_search_student_exchange_partners",
        {"summary_kind": "student_exchange_partners_top5"},
        notes,
    )


def _service_policy_seed(topic: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "service_policy_guides",
        utterance,
        {"path": "/service-policy-guides", "params": {"topic": topic, "limit": 5}},
        "tool_list_service_policy_guides",
        {"summary_kind": "service_policy_guides_top5"},
        notes,
    )


def _student_activity_notice_seed(topic: str, utterance: str, *, notes: str) -> RequestSeed:
    return _seed(
        "student_activity_notices",
        utterance,
        {"path": "/student-activity-notices", "params": {"topic": topic, "limit": 5}},
        "tool_list_student_activity_notices",
        {"summary_kind": "student_activity_notices_top5", "allow_empty": True},
        notes,
    )


def _manual_extra_seeds() -> list[RequestSeed]:
    return [
        _place_seed("남문", "남문 어디야?", notes="south-gate"),
        _place_seed("미카엘홀", "미카엘홀 위치 알려줘", notes="michael-hall"),
        _place_seed("콘서트홀", "콘서트홀 어디야?", notes="concert-hall"),
        _place_seed("성당", "성당 어디야?", notes="chapel"),
        _place_seed("운동장", "운동장 위치 알려줘", notes="playground"),
        _place_seed("프란치스코관", "프란치스코관 어디야?", notes="francis-hall"),
        _place_seed(
            "보건실",
            "보건실 어디야?",
            summary_kind="places_top1_facility_host",
            notes="health-center-facility",
        ),
        _place_seed(
            "ATM", "ATM 어디야?", summary_kind="places_top1_facility_host", notes="atm-facility"
        ),
        _place_seed(
            "세탁소",
            "세탁소 어디야?",
            summary_kind="places_top1_facility_host",
            notes="laundry-facility",
        ),
        _place_seed(
            "헬스장",
            "헬스장 어디야?",
            summary_kind="places_top1_facility_host",
            notes="gym-facility",
        ),
        _place_seed(
            "우리은행",
            "우리은행 어디야?",
            summary_kind="places_top1_facility_host",
            notes="woori-bank-facility",
        ),
        _place_seed(
            "교내복사실",
            "교내복사실 어디야?",
            summary_kind="places_top1_facility_host",
            notes="copy-room-facility",
        ),
        _place_seed(
            "카페멘사",
            "카페멘사 어디야?",
            summary_kind="places_top1_facility_host",
            notes="cafe-mensa-facility",
        ),
        _place_seed(
            "편의점",
            "편의점 어디야?",
            summary_kind="places_top1_facility_host",
            notes="convenience-store-facility",
        ),
        _course_seed("데이터베이스", "데이터베이스 과목 있어?", notes="database"),
        _course_seed("데이타베이스", "데이타베이스 과목 있어?", notes="database-typo"),
        _course_seed("데 이 터 베 이 스", "데 이 터 베 이 스 과목 있어?", notes="database-spaced"),
        _course_seed("CSE420", "CSE420 과목 뭐야?", notes="cse420"),
        _course_seed("CSE 420", "CSE 420 과목 뭐야?", notes="cse420-spaced"),
        _course_seed("CSE-420", "CSE-420 과목 뭐야?", notes="cse420-hyphen"),
        _course_seed("CSE301", "CSE301 과목 뭐야?", notes="cse301"),
        _course_seed("김가톨", "김가톨 교수 수업 있어?", notes="kim-gatol"),
        _course_seed("박요셉", "박요셉 교수 수업 있어?", notes="park-yosep"),
        _course_seed("권보람", "권보람 교수 수업 있어?", notes="kwon-boram"),
        _course_seed("박성심", "박성심 교수 수업 있어?", notes="park-seongsim"),
        _course_seed("운영체제", "운영체제 과목 알려줘", notes="operating-systems"),
        _course_seed("자료구조", "자료구조 과목 알려줘", notes="data-structures"),
        _course_seed("알고리즘", "알고리즘 과목 알려줘", notes="algorithms"),
        _course_seed("웹프로그래밍", "웹프로그래밍 과목 알려줘", notes="web-programming"),
        _course_seed("인공지능", "인공지능 과목 알려줘", notes="artificial-intelligence"),
        _course_seed("머신러닝", "머신러닝 과목 알려줘", notes="machine-learning"),
        _course_seed("선형대수", "선형대수 과목 알려줘", notes="linear-algebra"),
        _course_seed("미적분", "미적분 과목 알려줘", notes="calculus"),
        _course_seed("회계원리", "회계원리 과목 알려줘", notes="accounting"),
        _course_seed("마케팅", "마케팅 과목 알려줘", notes="marketing"),
        _course_seed("경영학원론", "경영학원론 과목 알려줘", notes="business-intro"),
        _course_seed("철학", "철학 과목 알려줘", notes="philosophy"),
        _course_seed("심리학", "심리학 과목 알려줘", notes="psychology"),
        _course_seed("글쓰기", "글쓰기 과목 알려줘", notes="writing"),
        _restaurant_nearby_seed(
            "학생회관 근처 밥집 추천해줘",
            origin="학생회관",
            walk_minutes=10,
            notes="student-center-nearby",
        ),
        _restaurant_nearby_seed(
            "중앙도서관 근처 카페 추천해줘",
            origin="중앙도서관",
            walk_minutes=10,
            category="cafe",
            notes="central-library-cafe",
        ),
        _restaurant_nearby_seed(
            "니콜스관 근처 카페 추천해줘",
            origin="니콜스관",
            walk_minutes=10,
            category="cafe",
            notes="nicholls-cafe",
        ),
        _restaurant_nearby_seed(
            "정문 근처 1만원 이하 밥집 추천해줘",
            origin="정문",
            walk_minutes=10,
            budget_max=10000,
            notes="gate-budget",
        ),
        _restaurant_nearby_seed(
            "K관 근처 카페 추천해줘",
            origin="K관",
            walk_minutes=5,
            category="cafe",
            notes="k-building-cafe",
        ),
        _restaurant_nearby_seed(
            "학생식당 근처 한식집 추천해줘",
            origin="학생식당",
            walk_minutes=10,
            budget_max=10000,
            category="korean",
            notes="student-cafeteria-korean",
        ),
        _restaurant_nearby_seed(
            "니콜스관 근처 지금 여는 밥집 추천해줘",
            origin="니콜스관",
            walk_minutes=10,
            open_now=True,
            notes="nicholls-open-now",
        ),
        _restaurant_search_seed("매머드커피", "매머드커피 검색해줘", notes="mammoth-coffee"),
        _restaurant_search_seed("컴포즈커피", "컴포즈커피 검색해줘", notes="compose-coffee"),
        _restaurant_search_seed("커피빈", "커피빈 검색해줘", notes="coffee-bean"),
        _restaurant_search_seed("버거킹", "버거킹 검색해줘", notes="burger-king"),
        _restaurant_search_seed("분식", "분식집 검색해줘", notes="snack-food"),
        _restaurant_search_seed("치킨", "치킨집 검색해줘", notes="chicken"),
        _restaurant_search_seed(
            "메가커피", "K관 근처 메가커피 검색해줘", origin="K관", notes="mega-k-building"
        ),
        _restaurant_search_seed(
            "스타벅스",
            "중앙도서관 근처 스타벅스 검색해줘",
            origin="중앙도서관",
            notes="starbucks-central-library",
        ),
        _notice_seed("career", "career 공지 알려줘", notes="career"),
        _notice_seed("event", "event 공지 알려줘", notes="event"),
        _notice_seed("facility", "facility 공지 알려줘", notes="facility"),
        _calendar_month_seed(8, "학사일정 8월 일정 보여줘"),
        _calendar_month_seed(9, "학사일정 9월 일정 보여줘"),
        _calendar_month_seed(10, "학사일정 10월 일정 보여줘"),
        _calendar_query_seed("등록", "등록 일정 알려줘", notes="registration"),
        _classroom_seed("베리타스관", "베리타스관 지금 빈 강의실 있어?", notes="veritas-hall"),
        _classroom_seed("마리아관", "마리아관 지금 빈 강의실 있어?", notes="maria-hall"),
        _classroom_seed("다솔관", "다솔관 지금 빈 강의실 있어?", notes="dasol-hall"),
        _classroom_seed("비르투스관", "비르투스관 지금 빈 강의실 있어?", notes="virtus-hall"),
        _transport_seed(
            "소사역에서 오는 법 알려줘", mode="subway", query="소사역", notes="sosa-station"
        ),
        _transport_seed("버스 노선 안내해줘", mode="bus", query="버스 노선", notes="bus-route"),
        _phone_book_seed("보안실", "보안실 전화번호 알려줘", notes="security-office-phone"),
        _phone_book_seed(
            "시설관재팀", "시설관재팀 전화번호 알려줘", notes="facility-management-phone"
        ),
        _phone_book_seed(
            "장애학생지원센터", "장애학생지원센터 전화번호 알려줘", notes="disability-support-phone"
        ),
        _phone_book_seed("예비군대대", "예비군대대 전화번호 알려줘", notes="rotc-phone"),
        _affiliated_notice_seed(
            "dorm_k_a_checkin_out",
            "기숙사 입퇴사공지 최신 글 알려줘",
            notes="dorm_k_a_checkin_out-latest",
        ),
        _affiliated_notice_seed(
            "dorm_francis_checkin_out",
            "프란치스코관 입퇴사공지 최신 글 알려줘",
            notes="dorm_francis_checkin_out-latest",
        ),
        _affiliated_notice_seed(
            "dorm_k_a_general",
            "기숙사 일반공지 중 장학 관련 공지 있어?",
            query="장학",
            notes="dorm_k_a_general-scholarship",
        ),
        _affiliated_notice_seed(
            "dorm_k_a_general",
            "기숙사 점호 일반공지 알려줘",
            query="점호",
            notes="dorm_k_a_general-body-search",
        ),
        _campus_life_notice_seed(
            "outside_agencies",
            "외부기관 모집 공지 있어?",
            query="모집",
            notes="outside_agencies-recruitment",
        ),
        _campus_life_notice_seed(
            "events", "행사안내 중 축제 공지 있어?", query="축제", notes="events-festival"
        ),
        _campus_life_notice_seed(
            "events", "행사안내 중 특강 공지 있어?", query="특강", notes="events-special-lecture"
        ),
        _partner_seed("일본", "일본 협정대학 알려줘", notes="country-japan"),
        _partner_seed("미국", "미국 협정대학 알려줘", notes="country-us"),
        _partner_seed("ASIA", "아시아 협정대학 알려줘", notes="continent-asia"),
        _partner_seed(
            "National Taiwan University", "National Taiwan University 있어?", notes="university-ntu"
        ),
        _student_activity_notice_seed(
            "club_recruitment",
            "동아리 모집 공지 알려줘",
            notes="club_recruitment-current-snapshot",
        ),
        _student_activity_notice_seed(
            "student_government",
            "학생회 공지 알려줘",
            notes="student_government-current-snapshot",
        ),
        _student_activity_notice_seed(
            "volunteering",
            "봉사활동 공지 알려줘",
            notes="volunteering-current-snapshot",
        ),
        _student_activity_notice_seed(
            "rotc",
            "학군단 공지 알려줘",
            notes="rotc-current-snapshot",
        ),
        _student_activity_notice_seed(
            "campus_event",
            "학생 행사 공지 알려줘",
            notes="campus_event-current-snapshot",
        ),
        _service_policy_seed("bidding", "입찰공고 어디서 확인해?", notes="bidding"),
        _service_policy_seed("job_posting", "채용공고 알려줘", notes="job-posting"),
        _service_policy_seed(
            "privacy_policy",
            "개인정보처리방침 어디서 봐?",
            notes="privacy-policy",
        ),
        _service_policy_seed(
            "cctv_policy",
            "영상정보처리기기 방침 어디서 봐?",
            notes="cctv-policy",
        ),
        _service_policy_seed("anti_graft", "청탁금지법 문의 어디야?", notes="anti-graft"),
    ]


def _assert_truth_quota_shape() -> None:
    totals = Counter()
    for domain, counts in DOMAIN_TRUTH_COUNTS.items():
        if sum(counts.values()) != DOMAIN_QUOTAS[domain]:
            raise ValueError(f"Truth mode count mismatch for {domain}")
        totals.update(counts)
    if dict(totals) != TRUTH_MODE_QUOTAS:
        raise ValueError(f"Global truth mode quotas mismatch: {totals!r}")


def _build_domain_style_counts() -> dict[EvalDomain, dict[EvalStyle, int]]:
    counts: dict[EvalDomain, dict[EvalStyle, int]] = {}
    for domain in DOMAIN_ORDER:
        counts[domain] = {style: 0 for style in STYLE_ORDER}
        counts[domain]["normal"] = DOMAIN_QUOTAS[domain]
    for domain, fixed in HIGH_REPEAT_STYLE_COUNTS.items():
        counts[domain] = {style: 0 for style in STYLE_ORDER}
        for style, amount in fixed.items():
            counts[domain][style] = amount

    def remaining(style: EvalStyle) -> int:
        return STYLE_QUOTAS[style] - sum(domain_counts[style] for domain_counts in counts.values())

    for style, order in (
        ("composite", LOW_KEY_COMPOSITE_ORDER),
        ("alias", LOW_KEY_ALIAS_ORDER),
        ("typo", LOW_KEY_TYPO_ORDER),
    ):
        needed = remaining(style)
        if needed < 0:
            raise ValueError(f"Negative remaining style quota for {style}")
        iterator = cycle(order)
        while needed:
            domain = next(iterator)
            if counts[domain]["normal"] <= 1:
                continue
            counts[domain]["normal"] -= 1
            counts[domain][style] += 1
            needed -= 1

    totals = Counter()
    for domain in DOMAIN_ORDER:
        domain_total = sum(counts[domain].values())
        if domain_total != DOMAIN_QUOTAS[domain]:
            raise ValueError(f"Style count mismatch for {domain}: {counts[domain]}")
        totals.update({style: amount for style, amount in counts[domain].items() if amount})
    if dict(totals) != STYLE_QUOTAS:
        raise ValueError(f"Global style quota mismatch: {totals!r}")
    return counts


DOMAIN_STYLE_COUNTS = _build_domain_style_counts()
_assert_truth_quota_shape()


def _build_seed_catalog(
    seed_rows: list[dict[str, Any]] | None = None,
) -> dict[EvalDomain, list[RequestSeed]]:
    resolved_seed_rows = seed_rows if seed_rows is not None else _read_jsonl(DEFAULT_CORPUS_PATH)
    catalog = _representative_seed_rows(resolved_seed_rows)
    seen_keys = {
        (seed.domain, coarse_request_key_from_payload(seed.api_request, truth_mode="set_contains"))
        for seeds in catalog.values()
        for seed in seeds
    }
    for seed in _manual_extra_seeds():
        key = (
            seed.domain,
            coarse_request_key_from_payload(seed.api_request, truth_mode="set_contains"),
        )
        if key in seen_keys:
            continue
        catalog.setdefault(seed.domain, []).append(seed)
        seen_keys.add(key)

    for domain in catalog:
        catalog[domain].sort(key=_seed_sort_key)

    student_activity_seeds = catalog.get("student_activity_guides", [])
    catalog["student_activity_guides"] = [
        RequestSeed(
            domain=seed.domain,
            canonical_utterance=STUDENT_ACTIVITY_GUIDE_CANARY_UTTERANCES.get(
                str(seed.api_request.get("params", {}).get("topic") or ""),
                seed.canonical_utterance,
            ),
            api_request=seed.api_request,
            expected_mcp_flow=seed.expected_mcp_flow,
            pass_rule=seed.pass_rule,
            notes=seed.notes,
        )
        for seed in student_activity_seeds
    ]
    return catalog


def _expand_interleaved(counts: dict[str, int], order: tuple[str, ...]) -> list[str]:
    remaining = dict(counts)
    sequence: list[str] = []
    while sum(remaining.values()):
        made_progress = False
        for item in order:
            if remaining.get(item, 0) <= 0:
                continue
            sequence.append(item)
            remaining[item] -= 1
            made_progress = True
        if not made_progress:
            break
    return sequence


def _clean_terminal(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_terminal_punctuation(text: str) -> str:
    return _clean_terminal(text).rstrip("?!., ")


def _strip_request_suffix(text: str) -> str:
    stem = _strip_terminal_punctuation(text)
    patterns = (
        "알려줘",
        "보여줘",
        "안내해줘",
        "정리해줘",
        "찾아줘",
        "검색해줘",
        "뭐야",
        "어디야",
        "있어",
        "어디서 봐",
        "궁금해",
    )
    for pattern in patterns:
        if stem.endswith(pattern):
            stem = stem[: -len(pattern)].strip()
            break
    return stem or _strip_terminal_punctuation(text)


def _replace_ending(text: str, ending: str) -> str:
    stem = _strip_request_suffix(text)
    return _clean_terminal(f"{stem} {ending}")


def _apply_alias_like_text(text: str) -> str:
    replacements = (
        ("중앙도서관", "중도"),
        ("학생회관", "학관"),
        ("김수환관", "K관"),
        ("정진석추기경약학관", "N관"),
        ("니콜스관", "니콜스"),
        ("보건실", "보건센터"),
        ("전화번호", "연락처"),
        ("안내", "정보"),
        ("장학제도", "장학금"),
        ("학사지원팀", "학사지원"),
        ("기숙사 운영팀", "기숙사 사무실"),
        ("개인형 이동장치", "PM"),
        ("해외협정대학", "교류대학"),
    )
    rendered = text
    for source, target in replacements:
        if source in rendered:
            rendered = rendered.replace(source, target)
            break
    if rendered == text:
        rendered = rendered.replace("알려줘", "뭐야").replace("보여줘", "알 수 있어?")
    return _clean_terminal(rendered)


def _apply_typo_like_text(text: str) -> str:
    rendered = text
    if re.search(r"\b[A-Za-z]{2,}\s?-?\d{3,4}\b", rendered):
        rendered = re.sub(r"\b([A-Za-z]{2,})(?:\s|-)?(\d{3,4})\b", r"\1-\2", rendered)
        return _clean_terminal(rendered)
    typo_map = (
        ("데이터", "데이타"),
        ("와이파이", "와이파이이"),
        ("전화번호", "전화 번호"),
        ("교내미디어", "교내 미디어"),
        ("학생군사교육단", "학생 군사교육단"),
    )
    for source, target in typo_map:
        if source in rendered:
            rendered = rendered.replace(source, target)
            return _clean_terminal(rendered)
    stem = _strip_request_suffix(rendered)
    tokens = stem.split()
    for index, token in enumerate(tokens):
        if re.fullmatch(r"[가-힣]{4,}", token):
            tokens[index] = " ".join(token)
            return _clean_terminal(" ".join(tokens))
    return _clean_terminal(rendered.replace(" ", "  ", 1))


def _render_candidates(seed: RequestSeed, style: EvalStyle) -> list[str]:
    canonical = _clean_terminal(seed.canonical_utterance)
    stem = _strip_request_suffix(canonical)
    if style == "normal":
        return [
            canonical,
            _replace_ending(canonical, "알려줘"),
            _replace_ending(canonical, "보여줘"),
            _replace_ending(canonical, "안내해줘"),
            _replace_ending(canonical, "정리해줘"),
            _clean_terminal(f"{stem} 궁금해"),
        ]
    if style == "composite":
        return [_clean_terminal(f"{stem} {suffix}") for suffix in COMPOSITE_SUFFIXES]
    if style == "alias":
        alias_text = _apply_alias_like_text(canonical)
        return [
            alias_text,
            _replace_ending(alias_text, "알려줘"),
            _replace_ending(alias_text, "보여줘"),
            _clean_terminal(f"{_strip_request_suffix(alias_text)} 정보 알려줘"),
        ]
    if style == "typo":
        typo_text = _apply_typo_like_text(canonical)
        return [
            typo_text,
            _replace_ending(typo_text, "알려줘"),
            _clean_terminal(f"{_strip_request_suffix(typo_text)} 뭐야"),
            _clean_terminal(f"{_strip_request_suffix(typo_text)} 검색해줘"),
        ]
    if style == "ambiguous":
        return [_clean_terminal(f"{stem} {suffix}") for suffix in AMBIGUOUS_SUFFIXES]
    if style == "out_of_scope":
        return [
            canonical,
            _clean_terminal(f"{stem} 접근할 수 있어?"),
            _clean_terminal(f"{stem} 지금 확인 가능해?"),
        ]
    raise ValueError(f"Unknown style: {style}")


def _unique_utterance_for_seed(
    seed: RequestSeed,
    *,
    style: EvalStyle,
    occurrence: int,
    used: set[str],
) -> str:
    candidates = _render_candidates(seed, style)
    if occurrence < len(candidates):
        rendered = candidates[occurrence]
        key = normalize_utterance_key(rendered)
        if key not in used:
            used.add(key)
            return rendered
    for candidate in candidates:
        for qualifier in FALLBACK_QUALIFIERS:
            rendered = _clean_terminal(f"{_strip_terminal_punctuation(candidate)} {qualifier}")
            key = normalize_utterance_key(rendered)
            if key not in used:
                used.add(key)
                return rendered
    raise ValueError(f"Unable to generate unique utterance for {seed.domain}:{seed.notes}:{style}")


def _format_id(domain: EvalDomain, index: int) -> str:
    prefix = ID_PREFIXES[domain]
    width = ID_WIDTHS.get(domain, 4)
    return f"{prefix}{index:0{width}d}"


def _seed_identifier(seed: RequestSeed) -> tuple[str | None, str | None, str]:
    return coarse_request_key_from_payload(seed.api_request, truth_mode="set_contains")


def build_public_api_eval_corpus(
    *, seed_rows: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    if seed_rows is not None:
        try:
            validate_corpus_rows(seed_rows)
        except ValueError:
            pass
        else:
            return list(seed_rows)

    catalog = _build_seed_catalog(seed_rows)
    rows: list[dict[str, Any]] = []
    used_utterances: set[str] = set()

    for domain in DOMAIN_ORDER:
        seeds = catalog.get(domain, [])
        if not seeds:
            raise ValueError(f"No seeds available for domain {domain}")

        style_sequence = _expand_interleaved(DOMAIN_STYLE_COUNTS[domain], STYLE_ORDER)
        truth_sequence = _expand_interleaved(DOMAIN_TRUTH_COUNTS[domain], TRUTH_ORDER)
        if len(style_sequence) != DOMAIN_QUOTAS[domain]:
            raise ValueError(f"Style sequence length mismatch for {domain}")
        if len(truth_sequence) != DOMAIN_QUOTAS[domain]:
            raise ValueError(f"Truth sequence length mismatch for {domain}")

        seed_style_usage: dict[tuple[tuple[str | None, str | None, str], EvalStyle], int] = (
            defaultdict(int)
        )
        seed_total_usage: dict[tuple[str | None, str | None, str], int] = defaultdict(int)
        seed_cursor = 0

        for row_index, (style, truth_mode) in enumerate(
            zip(style_sequence, truth_sequence, strict=True), start=1
        ):
            attempts = 0
            while True:
                seed = seeds[seed_cursor % len(seeds)]
                seed_cursor += 1
                attempts += 1
                seed_key = _seed_identifier(seed)
                if (
                    domain in COARSE_CAP_ENFORCED_DOMAINS
                    and seed_total_usage[seed_key] >= COARSE_CAP_MAX
                ):
                    if attempts > len(seeds) * (COARSE_CAP_MAX + 1):
                        raise ValueError(f"Unable to satisfy coarse cap for {domain}")
                    continue
                break

            style_occurrence = seed_style_usage[(seed_key, style)]
            utterance = _unique_utterance_for_seed(
                seed,
                style=style,
                occurrence=style_occurrence,
                used=used_utterances,
            )
            seed_style_usage[(seed_key, style)] += 1
            seed_total_usage[seed_key] += 1
            rows.append(
                {
                    "id": _format_id(domain, row_index),
                    "domain": domain,
                    "style": style,
                    "user_utterance": utterance,
                    "api_request": seed.api_request,
                    "expected_mcp_flow": seed.expected_mcp_flow,
                    "truth_mode": truth_mode,
                    "pass_rule": seed.pass_rule,
                    "watch_policy": "none",
                    "notes": seed.notes,
                }
            )

    validate_corpus_rows(rows)
    return rows


def validate_corpus_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 1000:
        raise ValueError(f"Expected 1000 rows, found {len(rows)}")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate ids detected")
    if len({normalize_utterance_key(str(row["user_utterance"])) for row in rows}) != len(rows):
        raise ValueError("Duplicate utterances detected")
    if any(row["truth_mode"] == "watch_only" for row in rows):
        raise ValueError("Main corpus cannot contain watch_only rows")

    domain_counts = Counter(row["domain"] for row in rows)
    style_counts = Counter(row["style"] for row in rows)
    truth_counts = Counter(row["truth_mode"] for row in rows)
    if dict(domain_counts) != DOMAIN_QUOTAS:
        raise ValueError(f"Domain quota mismatch: {domain_counts!r}")
    if dict(style_counts) != STYLE_QUOTAS:
        raise ValueError(f"Style quota mismatch: {style_counts!r}")
    if dict(truth_counts) != TRUTH_MODE_QUOTAS:
        raise ValueError(f"Truth mode quota mismatch: {truth_counts!r}")

    coarse_counts: dict[str, Counter[tuple[str | None, str | None, str]]] = defaultdict(Counter)
    for row in rows:
        key = coarse_request_key_from_payload(row["api_request"], truth_mode=str(row["truth_mode"]))
        coarse_counts[str(row["domain"])][key] += 1
    for domain in COARSE_CAP_ENFORCED_DOMAINS:
        if coarse_counts[domain] and max(coarse_counts[domain].values()) > COARSE_CAP_MAX:
            raise ValueError(f"Coarse key cap violated for {domain}")


def write_default_corpus(output_path: Path = DEFAULT_CORPUS_PATH) -> list[dict[str, Any]]:
    rows = build_public_api_eval_corpus(seed_rows=_read_jsonl(output_path))
    _write_jsonl(output_path, rows)
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the committed public API eval corpus")
    parser.add_argument("--output", default=str(DEFAULT_CORPUS_PATH))
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    output_path = Path(args.output)
    rows = write_default_corpus(output_path)
    print(json.dumps({"rows": len(rows), "output": str(output_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
