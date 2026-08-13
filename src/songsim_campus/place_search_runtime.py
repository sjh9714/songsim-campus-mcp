from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import clock, repo
from .db import DBConnection
from .ingest.official_sources import CampusFacilitiesSource
from .schemas import MatchedFacility, Place
from .settings import get_settings

FACILITIES_SOURCE_URL = "https://www.catholic.ac.kr/ko/campuslife/restaurant.do"
DEFAULT_RESTAURANT_SEARCH_ORIGIN = "central-library"
CLASSROOM_BUILDING_CATEGORIES = {"building", "library"}

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PLACE_ALIAS_OVERRIDES_PATH = DATA_DIR / "place_alias_overrides.json"
PLACE_FACILITY_KEYWORDS_PATH = DATA_DIR / "place_facility_keywords.json"
PLACE_SHORT_QUERY_PREFERENCES_PATH = DATA_DIR / "place_short_query_preferences.json"
PLACE_QUERY_FILLER_PATTERNS = (
    r"[?？!！]+",
    r"(전화번호|연락처)\s*(알려\s*줘|알려줘|좀|부탁해)?",
    r"운영\s*시간\s*(알려\s*줘|알려줘|좀|부탁해)?",
    r"몇\s*시(까지)?",
    r"위치\s*(알려\s*줘|알려줘|좀|부탁해)?",
    r"어디\s*(야|에요|예요|지|인지|있어|있어요|있나|있나요)?",
    r"(알려\s*줘|알려줘|말해\s*줘|말해줘|보여\s*줘|보여줘)",
)
_EXTRA_PLAIN_GENERIC_FACILITY_QUERIES = {"세탁소"}


class NotFoundError(ValueError):
    """Raised when requested data cannot be found."""


class InvalidRequestError(ValueError):
    """Raised when the request is invalid or ambiguous."""


def _now_iso() -> str:
    return clock.now_iso()


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


def _matches_composite_text_candidate(
    text: str | None,
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> bool:
    cleaned = _normalize_optional_text(text)
    if cleaned is None:
        return False
    collapsed_text = _collapse_whitespace(cleaned).lower()
    query_text = collapsed_query.lower()
    if collapsed_text in query_text or query_text in collapsed_text:
        return True
    if compact_query is None:
        return False
    compact_text = _compact_text(cleaned).lower()
    query_compact = compact_query.lower()
    return compact_text in query_compact or query_compact in compact_text


def _unique_stripped(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _normalize_place_key(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.split(",")[0]
    normalized = normalized.replace("가톨릭대학교", "")
    normalized = normalized.replace("성심교정", "")
    normalized = normalized.replace("중앙도서관", "중앙도서관")
    normalized = "".join(char for char in normalized if not char.isspace())
    normalized = "".join(char for char in normalized if char not in "()")
    for marker in ["지하", "층", "호", "동"]:
        if marker == "층":
            normalized = normalized.split(marker)[0]
    normalized = normalized.rstrip("0123456789")
    return normalized


def _build_place_slug_lookup(place_rows: list[dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for place in place_rows:
        keys = [place["name"], *place.get("aliases", [])]
        for key in keys:
            normalized = _normalize_place_key(key)
            if normalized:
                index[normalized] = place["slug"]
    return index


def _build_place_slug_candidates_lookup(place_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for place in place_rows:
        keys = [place["name"], *place.get("aliases", [])]
        for key in keys:
            normalized = _normalize_place_key(key)
            if not normalized:
                continue
            index.setdefault(normalized, [])
            slug = str(place["slug"])
            if slug not in index[normalized]:
                index[normalized].append(slug)
    return index


def _build_place_model_lookup(place_rows: list[dict[str, Any]]) -> dict[str, Place]:
    return {row["slug"]: Place.model_validate(row) for row in place_rows}


def _location_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    for item in value.replace("/", ",").split(","):
        token = item.strip()
        if not token:
            continue
        token = token.replace("가톨릭대학교", "")
        token = token.replace("성심교정", "")
        token = token.split()[0] if " " in token else token
        token = token.split("층")[0]
        token = token.split("호")[0]
        token = token.strip()
        if token:
            candidates.append(token)
    return candidates


def _facility_host_place_category_rank(category: str | None) -> int:
    normalized = _normalize_optional_text(category)
    if normalized in {"building", "library", "gate"}:
        return 0
    if normalized == "facility":
        return 1
    if normalized == "dormitory":
        return 2
    return 3


def _parse_place_alias_overrides(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("place alias overrides must be a JSON object keyed by slug")

    overrides: dict[str, dict[str, Any]] = {}
    for raw_slug, raw_value in payload.items():
        if not isinstance(raw_slug, str) or not raw_slug.strip():
            raise ValueError("place alias override slug must be a non-empty string")
        if not isinstance(raw_value, dict):
            raise ValueError("place alias override entries must be objects")
        unknown_keys = set(raw_value) - {"aliases", "category", "display_name"}
        if unknown_keys:
            raise ValueError(
                "place alias override entries only support aliases, category, and display_name keys"
            )
        aliases = raw_value.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(item, str) for item in aliases):
            raise ValueError("place alias override aliases must be a list of strings")
        category = raw_value.get("category")
        if category is not None and (not isinstance(category, str) or not category.strip()):
            raise ValueError("place alias override category must be a non-empty string")
        display_name = raw_value.get("display_name")
        if display_name is not None and (
            not isinstance(display_name, str) or not display_name.strip()
        ):
            raise ValueError("place alias override display_name must be a non-empty string")
        override_payload: dict[str, Any] = {"aliases": _unique_stripped(list(aliases))}
        if category is not None:
            override_payload["category"] = category.strip()
        if display_name is not None:
            override_payload["display_name"] = display_name.strip()
        overrides[raw_slug.strip()] = override_payload
    return overrides


@lru_cache(maxsize=1)
def _load_place_alias_overrides() -> dict[str, dict[str, Any]]:
    payload = json.loads(PLACE_ALIAS_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return _parse_place_alias_overrides(payload)


def _parse_place_facility_keywords(payload: Any) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("place facility keywords must be a JSON object keyed by noun")

    keywords: dict[str, list[str]] = {}
    for raw_keyword, raw_tokens in payload.items():
        if not isinstance(raw_keyword, str) or not raw_keyword.strip():
            raise ValueError("place facility keyword key must be a non-empty string")
        if not isinstance(raw_tokens, list) or any(
            not isinstance(item, str) for item in raw_tokens
        ):
            raise ValueError("place facility keyword entries must be a list of strings")
        keywords[raw_keyword.strip()] = _unique_stripped(list(raw_tokens))
    return keywords


@lru_cache(maxsize=1)
def _load_place_facility_keywords() -> dict[str, list[str]]:
    payload = json.loads(PLACE_FACILITY_KEYWORDS_PATH.read_text(encoding="utf-8"))
    return _parse_place_facility_keywords(payload)


def _parse_place_short_query_preferences(payload: Any) -> dict[str, dict[str, list[str]]]:
    if not isinstance(payload, dict):
        raise ValueError("place short query preferences must be a JSON object keyed by query")

    preferences: dict[str, dict[str, list[str]]] = {}
    allowed_contexts = {"place_search", "origin", "building"}
    for raw_query, raw_contexts in payload.items():
        if not isinstance(raw_query, str) or not raw_query.strip():
            raise ValueError("place short query preference key must be a non-empty string")
        if not isinstance(raw_contexts, dict):
            raise ValueError("place short query preference entries must be objects")
        unknown_contexts = set(raw_contexts) - allowed_contexts
        if unknown_contexts:
            raise ValueError(
                "place short query preference entries only support "
                "place_search, origin, and building contexts"
            )
        parsed_contexts: dict[str, list[str]] = {}
        for context in allowed_contexts:
            raw_slugs = raw_contexts.get(context, [])
            if not isinstance(raw_slugs, list) or any(
                not isinstance(item, str) for item in raw_slugs
            ):
                raise ValueError(
                    f"place short query preference {raw_query}.{context} must be a list of strings"
                )
            parsed_contexts[context] = _unique_stripped(list(raw_slugs))
        preferences[raw_query.strip()] = parsed_contexts
    return preferences


@lru_cache(maxsize=1)
def _load_place_short_query_preferences() -> dict[str, dict[str, list[str]]]:
    payload = json.loads(PLACE_SHORT_QUERY_PREFERENCES_PATH.read_text(encoding="utf-8"))
    return _parse_place_short_query_preferences(payload)


def _preferred_place_slugs_for_query(query: str, *, context: str) -> list[str]:
    collapsed_query, compact_query = _normalized_query_variants(query)
    if collapsed_query is None:
        return []
    for preferred_query, context_map in _load_place_short_query_preferences().items():
        if _matches_exact_text_candidate(
            preferred_query,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        ):
            return list(context_map.get(context, []))
    return []


def _preferred_place_display_name(slug: str) -> str | None:
    cleaned_slug = slug.strip()
    if not cleaned_slug:
        return None
    override = _load_place_alias_overrides().get(cleaned_slug)
    display_name = override.get("display_name") if override is not None else None
    return _normalize_optional_text(display_name)


def _display_name_for_place_result(
    slug: str,
    default_name: str,
    *,
    collapsed_query: str,
    compact_query: str | None,
    aliases: list[str],
    has_matched_facility: bool = False,
) -> str:
    preferred_display_name = _preferred_place_display_name(slug)
    if preferred_display_name is None:
        return default_name
    if slug.lower() == collapsed_query.lower():
        return default_name
    if _matches_exact_text_candidate(
        default_name,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return default_name
    if has_matched_facility:
        return preferred_display_name
    if any(
        _matches_exact_text_candidate(
            alias,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for alias in aliases
    ):
        return preferred_display_name
    return default_name


def _resolve_campus_facility_place_slug(
    location_text: str | None,
    *,
    place_rows: list[dict[str, Any]],
) -> str | None:
    place_lookup = {str(row.get("slug") or "").strip(): row for row in place_rows}
    candidates_lookup = _build_place_slug_candidates_lookup(place_rows)

    for candidate in _location_candidates(str(location_text or "")):
        preferred_slugs = _preferred_place_slugs_for_query(candidate, context="place_search")
        for preferred_slug in preferred_slugs:
            if preferred_slug in place_lookup:
                return preferred_slug

        normalized_candidate = _normalize_place_key(candidate)
        if not normalized_candidate:
            continue
        matching_slugs = candidates_lookup.get(normalized_candidate, [])
        if not matching_slugs:
            continue
        if len(matching_slugs) == 1:
            return matching_slugs[0]

        ranked_slugs = sorted(
            matching_slugs,
            key=lambda slug: (
                _facility_host_place_category_rank(place_lookup.get(slug, {}).get("category")),
                slug,
            ),
        )
        if ranked_slugs:
            return ranked_slugs[0]
    return None


def _strip_terminal_query_particles(value: str) -> str:
    cleaned = value.strip()
    while len(cleaned) > 1 and cleaned[-1] in {"이", "가", "은", "는", "을", "를"}:
        cleaned = cleaned[:-1].strip()
    return cleaned


def _normalize_place_search_query(value: str | None) -> tuple[str | None, str | None]:
    collapsed, compacted = _normalized_query_variants(value)
    if collapsed is None:
        return None, None
    normalized = collapsed
    for pattern in PLACE_QUERY_FILLER_PATTERNS:
        normalized = re.sub(pattern, " ", normalized)
    normalized = _collapse_whitespace(normalized)
    normalized = _strip_terminal_query_particles(normalized)
    if not normalized:
        normalized = collapsed
    return _normalized_query_variants(normalized)


def _rank_place_search_candidate(
    item: dict[str, Any],
    *,
    collapsed_query: str,
    compact_query: str | None,
    facility_tokens: list[str] | None = None,
    generic_keywords: list[str] | None = None,
) -> int | None:
    slug = str(item.get("slug") or "").strip()
    name = str(item.get("name") or "")
    aliases = [str(alias) for alias in item.get("aliases", [])]
    description = str(item.get("description") or "")
    facility_tokens = facility_tokens or []
    generic_keywords = generic_keywords or []
    lowered_query = collapsed_query.lower()
    if slug.lower() == lowered_query:
        return 0
    if _matches_exact_text_candidate(
        name,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 1
    if any(
        _matches_exact_text_candidate(
            alias,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for alias in aliases
    ):
        return 2
    if any(
        _matches_exact_text_candidate(
            token,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for token in facility_tokens
    ):
        return 3
    if any(
        _matches_exact_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in generic_keywords
    ):
        return 4
    if _matches_partial_text_candidate(
        name,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 5
    if any(
        _matches_partial_text_candidate(
            alias,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for alias in aliases
    ):
        return 6
    if any(
        _matches_partial_text_candidate(
            token,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for token in facility_tokens
    ):
        return 7
    if _matches_partial_text_candidate(
        description,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 8
    return None


def _normalize_facility_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    for token in ("가톨릭대학교", "가톨릭대", "성심교정"):
        normalized = normalized.replace(token, "")
    normalized = "".join(char for char in normalized if not char.isspace())
    if normalized.endswith("점"):
        normalized = normalized[:-1]
    return normalized


def _is_generic_opening_hours_key(value: str) -> bool:
    normalized = _normalize_facility_name(value)
    return normalized in {
        "",
        "운영시간",
        "평일",
        "주말",
        "공휴일",
        "휴무",
        "월",
        "월요일",
        "화",
        "화요일",
        "수",
        "수요일",
        "목",
        "목요일",
        "금",
        "금요일",
        "주중",
        "토",
        "토요일",
        "일",
        "일요일",
        "월-금",
    }


def _facility_hours_index(conn: DBConnection) -> dict[str, str]:
    index: dict[str, str] = {}
    for place in repo.list_places(conn):
        for name, hours_text in place.get("opening_hours", {}).items():
            if _is_generic_opening_hours_key(name):
                continue
            key = _normalize_facility_name(name)
            if key and key not in index:
                index[key] = hours_text
    return index


def _place_facility_tokens(item: dict[str, Any]) -> list[str]:
    return _unique_stripped(
        [
            str(name)
            for name in item.get("opening_hours", {})
            if not _is_generic_opening_hours_key(str(name))
        ]
    )


def _place_search_targets(item: dict[str, Any], *, facility_tokens: list[str]) -> list[str]:
    return _unique_stripped(
        [
            str(item.get("name") or ""),
            *[str(alias) for alias in item.get("aliases", [])],
            *facility_tokens,
        ]
    )


def _generic_facility_keywords_for_targets(targets: list[str]) -> list[str]:
    normalized_targets = {
        _normalize_facility_name(target)
        for target in targets
        if _normalize_facility_name(target)
    }
    keywords: list[str] = []
    for generic_keyword, tokens in _load_place_facility_keywords().items():
        normalized_tokens = [
            _normalize_facility_name(token)
            for token in tokens
            if _normalize_facility_name(token)
        ]
        if any(
            token == target or token in target
            for token in normalized_tokens
            for target in normalized_targets
        ):
            keywords.append(generic_keyword)
    return _unique_stripped(keywords)


def _place_generic_facility_keywords(
    item: dict[str, Any],
    *,
    facility_tokens: list[str],
) -> list[str]:
    return _generic_facility_keywords_for_targets(
        _place_search_targets(item, facility_tokens=facility_tokens)
    )


def _build_place_search_facility_index(
    places: list[dict[str, Any]],
) -> list[dict[str, list[str]]]:
    index: list[dict[str, list[str]]] = []
    for item in places:
        facility_tokens = _place_facility_tokens(item)
        generic_keywords = _place_generic_facility_keywords(item, facility_tokens=facility_tokens)
        index.append(
            {
                "facility_tokens": facility_tokens,
                "generic_keywords": generic_keywords,
            }
        )
    return index


def _normalize_campus_facility_phone(value: str | None) -> str | None:
    cleaned = _normalize_optional_text(value)
    if cleaned in {None, "-"}:
        return None
    return cleaned


def _normalize_campus_facility_location(value: str | None) -> str | None:
    cleaned = _normalize_optional_text(value)
    if cleaned in {None, "-"}:
        return None
    return cleaned


def _matched_facility_from_row(row: dict[str, Any]) -> MatchedFacility:
    return MatchedFacility(
        name=str(row.get("facility_name") or ""),
        category=_normalize_optional_text(row.get("category")),
        phone=_normalize_campus_facility_phone(row.get("phone")),
        location_hint=_normalize_campus_facility_location(row.get("location_text")),
        opening_hours=_normalize_optional_text(row.get("hours_text")),
    )


def _with_matched_facility_location_fallback(
    matched_facility: MatchedFacility,
    *,
    place: dict[str, Any],
) -> MatchedFacility:
    if matched_facility.location_hint is not None:
        return matched_facility
    fallback_location_hint = _normalize_optional_text(
        place.get("canonical_name") or place.get("name")
    )
    if fallback_location_hint is None:
        return matched_facility
    return matched_facility.model_copy(update={"location_hint": fallback_location_hint})


def _rank_campus_facility_composite_candidate(
    row: dict[str, Any],
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> int | None:
    location_text = str(row.get("location_text") or "")
    hours_text = str(row.get("hours_text") or "")
    category = str(row.get("category") or "")
    facility_name = str(row.get("facility_name") or "")
    generic_keywords = _generic_facility_keywords_for_targets([facility_name, category])

    location_match = _matches_composite_text_candidate(
        location_text,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    )
    if not location_match:
        return None

    if _matches_composite_text_candidate(
        category,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 2
    if any(
        _matches_composite_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in generic_keywords
    ):
        return 2
    if _matches_composite_text_candidate(
        hours_text,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 2
    return None


def _rank_campus_facility_candidate(
    row: dict[str, Any],
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> int | None:
    name = str(row.get("facility_name") or "")
    category = str(row.get("category") or "")
    location_text = str(row.get("location_text") or "")
    phone = str(row.get("phone") or "")
    generic_keywords = _generic_facility_keywords_for_targets([name, category])
    if _matches_exact_text_candidate(
        name,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 0
    if _matches_exact_text_candidate(
        category,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 1
    if any(
        _matches_exact_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in generic_keywords
    ):
        return 2
    if _matches_exact_text_candidate(
        phone,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 3
    composite_rank = _rank_campus_facility_composite_candidate(
        row,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    )
    if composite_rank is not None:
        return composite_rank
    if _matches_partial_text_candidate(
        name,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 4
    if _matches_partial_text_candidate(
        category,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 5
    if any(
        _matches_partial_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in generic_keywords
    ):
        return 6
    if _matches_partial_text_candidate(
        location_text,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 7
    if _matches_partial_text_candidate(
        phone,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return 8
    return None


def _is_plain_generic_facility_query(
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> bool:
    return any(
        _matches_exact_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in _load_place_facility_keywords()
    ) or any(
        _matches_exact_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in _EXTRA_PLAIN_GENERIC_FACILITY_QUERIES
    )


def _is_generic_place_facility_match(
    *,
    collapsed_query: str,
    compact_query: str | None,
    facility_tokens: list[str],
    generic_keywords: list[str],
) -> bool:
    return any(
        _matches_exact_text_candidate(
            token,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for token in facility_tokens
    ) or any(
        _matches_exact_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in generic_keywords
    )


def _is_generic_or_category_facility_match(
    row: dict[str, Any],
    *,
    collapsed_query: str,
    compact_query: str | None,
) -> bool:
    name = str(row.get("facility_name") or "")
    category = str(row.get("category") or "")
    phone = str(row.get("phone") or "")
    if _matches_exact_text_candidate(
        name,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return False
    if _matches_exact_text_candidate(
        phone,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return False
    if (
        _rank_campus_facility_composite_candidate(
            row,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        is not None
    ):
        return False
    if _matches_exact_text_candidate(
        category,
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    ):
        return True
    generic_keywords = _generic_facility_keywords_for_targets([name, category])
    return any(
        _matches_exact_text_candidate(
            keyword,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        for keyword in generic_keywords
    )


def _facility_phase_for_rank(rank: int) -> tuple[int, int]:
    if rank == 0:
        return 0, rank
    if rank <= 3:
        return 1, rank
    return 3, rank


def _place_phase_for_rank(rank: int) -> tuple[int, int]:
    if rank <= 2:
        return 2, rank
    return 3, rank


def _should_use_live_campus_facility_fallback() -> bool:
    database_url = get_settings().database_url.lower()
    local_markers = ("127.0.0.1", "localhost", "songsim_test", "sqlite")
    return not any(marker in database_url for marker in local_markers)


def _load_source_backed_campus_facilities(
    place_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _should_use_live_campus_facility_fallback():
        return []

    try:
        source = CampusFacilitiesSource(FACILITIES_SOURCE_URL)
        rows = source.parse(source.fetch(), fetched_at=_now_iso())
    except Exception:
        return []

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        location_text = _normalize_campus_facility_location(
            row.get("location_text") or row.get("location")
        )
        place_slug = _resolve_campus_facility_place_slug(location_text, place_rows=place_rows)
        normalized_rows.append(
            {
                "facility_name": str(row.get("facility_name") or ""),
                "category": _normalize_optional_text(row.get("category")),
                "phone": _normalize_campus_facility_phone(row.get("phone") or row.get("contact")),
                "location_text": location_text,
                "hours_text": _normalize_optional_text(row.get("hours_text")),
                "place_slug": place_slug,
                "source_url": row.get("source_url") or FACILITIES_SOURCE_URL,
                "source_tag": row.get("source_tag", "cuk_facilities"),
                "last_synced_at": row.get("last_synced_at"),
            }
        )
    return normalized_rows


def _build_searchable_campus_facilities(
    conn: DBConnection,
    *,
    place_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = repo.list_campus_facilities(conn)
    if not rows:
        rows = _load_source_backed_campus_facilities(place_rows)
    seen: set[tuple[str, str]] = set()
    searchable: list[dict[str, Any]] = []

    for row in rows:
        facility_name = str(row.get("facility_name") or "").strip()
        if not facility_name:
            continue
        place_slug = _normalize_optional_text(row.get("place_slug"))
        if place_slug is None:
            place_slug = _resolve_campus_facility_place_slug(
                str(row.get("location_text") or ""),
                place_rows=place_rows,
            )
        key = (place_slug or "", _normalize_facility_name(facility_name))
        if key in seen:
            continue
        seen.add(key)
        searchable.append(
            {
                "facility_name": facility_name,
                "category": _normalize_optional_text(row.get("category")),
                "phone": _normalize_campus_facility_phone(row.get("phone")),
                "location_text": _normalize_campus_facility_location(row.get("location_text")),
                "hours_text": _normalize_optional_text(row.get("hours_text")),
                "place_slug": place_slug,
                "source_url": row.get("source_url"),
                "source_tag": row.get("source_tag", "demo"),
                "last_synced_at": row.get("last_synced_at"),
            }
        )

    for place in place_rows:
        place_slug = str(place.get("slug") or "").strip()
        for facility_name, hours_text in place.get("opening_hours", {}).items():
            facility_name = str(facility_name)
            if _is_generic_opening_hours_key(facility_name):
                continue
            key = (place_slug, _normalize_facility_name(facility_name))
            if key in seen:
                continue
            seen.add(key)
            searchable.append(
                {
                    "facility_name": facility_name,
                    "category": None,
                    "phone": None,
                    "location_text": None,
                    "hours_text": str(hours_text) if hours_text is not None else None,
                    "place_slug": place_slug,
                    "source_url": None,
                    "source_tag": place.get("source_tag", "demo"),
                    "last_synced_at": place.get("last_synced_at"),
                }
            )

    return searchable


def search_places(
    conn: DBConnection,
    *,
    query: str = "",
    category: str | None = None,
    limit: int = 10,
) -> list[Place]:
    places = repo.list_places(conn)
    if category is not None:
        places = [item for item in places if item["category"] == category]
    collapsed_query, compact_query = _normalize_place_search_query(query)
    if collapsed_query is None:
        return [Place.model_validate(item) for item in places[:limit]]

    facility_index = _build_place_search_facility_index(places)
    searchable_facilities = _build_searchable_campus_facilities(conn, place_rows=places)
    preferred_slugs = _preferred_place_slugs_for_query(collapsed_query, context="place_search")
    preferred_slug_set = set(preferred_slugs)
    query_is_plain_generic_facility = _is_plain_generic_facility_query(
        collapsed_query=collapsed_query,
        compact_query=compact_query,
    )
    place_alias_lists: dict[str, list[str]] = {}
    for place in places:
        slug = str(place.get("slug") or "").strip()
        if not slug:
            continue
        place_alias_lists[slug] = [alias for alias in place.get("aliases", [])]
    facility_best_by_slug: dict[str, tuple[int, int, dict[str, Any]]] = {}
    for facility_index_value, row in enumerate(searchable_facilities):
        place_slug = str(row.get("place_slug") or "").strip()
        if not place_slug:
            continue
        rank = _rank_campus_facility_candidate(
            row,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
        )
        if rank is None:
            continue
        existing = facility_best_by_slug.get(place_slug)
        if existing is None or (rank, facility_index_value) < (existing[0], existing[1]):
            facility_best_by_slug[place_slug] = (rank, facility_index_value, row)

    ranked: list[tuple[int, int, int, int, dict[str, Any]]] = []
    for index, item in enumerate(places):
        place_rank = _rank_place_search_candidate(
            item,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
            facility_tokens=facility_index[index]["facility_tokens"],
            generic_keywords=facility_index[index]["generic_keywords"],
        )
        slug = str(item.get("slug") or "").strip()
        facility_match = facility_best_by_slug.get(slug)
        if place_rank is None and facility_match is None:
            continue
        facility_sort = (
            _facility_phase_for_rank(facility_match[0]) if facility_match is not None else None
        )
        place_sort = _place_phase_for_rank(place_rank) if place_rank is not None else None
        aliases = place_alias_lists.get(slug, [])
        canonical_name = str(item.get("name") or "")
        display_name = _display_name_for_place_result(
            slug,
            canonical_name,
            collapsed_query=collapsed_query,
            compact_query=compact_query,
            aliases=aliases,
        )
        if facility_sort is not None and (place_sort is None or facility_sort < place_sort):
            phase, subrank = facility_sort
            display_name = _display_name_for_place_result(
                slug,
                canonical_name,
                collapsed_query=collapsed_query,
                compact_query=compact_query,
                aliases=aliases,
                has_matched_facility=True,
            )
            matched_facility = _with_matched_facility_location_fallback(
                _matched_facility_from_row(facility_match[2]),
                place=item,
            )
            payload = {
                **item,
                "name": display_name,
                "canonical_name": canonical_name,
                "matched_facility": matched_facility.model_dump(exclude_none=True),
            }
        else:
            assert place_sort is not None
            phase, subrank = place_sort
            payload = {
                **item,
                "name": display_name,
                "canonical_name": canonical_name,
            }
            if query_is_plain_generic_facility and facility_match is not None:
                matched_facility = _with_matched_facility_location_fallback(
                    _matched_facility_from_row(facility_match[2]),
                    place=item,
                ).model_dump(exclude_none=True)
                payload["matched_facility"] = matched_facility
        preference_rank = 0 if slug in preferred_slug_set else 1
        generic_host_bias = 0
        if query_is_plain_generic_facility:
            if facility_match is not None and _is_generic_or_category_facility_match(
                facility_match[2],
                collapsed_query=collapsed_query,
                compact_query=compact_query,
            ):
                generic_host_bias = _facility_host_place_category_rank(item.get("category"))
            elif place_sort is not None and _is_generic_place_facility_match(
                collapsed_query=collapsed_query,
                compact_query=compact_query,
                facility_tokens=facility_index[index]["facility_tokens"],
                generic_keywords=facility_index[index]["generic_keywords"],
            ):
                generic_host_bias = _facility_host_place_category_rank(item.get("category"))
        ranked.append((generic_host_bias, phase, subrank, preference_rank, index, payload))
    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
    if preferred_slugs:
        ranked = [
            item for item in ranked if str(item[5].get("slug") or "").strip() in preferred_slug_set
        ]
    return [Place.model_validate(item) for _, _, _, _, _, item in ranked[:limit]]


def _format_ambiguous_place_error(
    identifier: str,
    matches: list[dict[str, Any]],
    *,
    label: str,
) -> str:
    candidates = ", ".join(f"{item['name']} ({item['slug']})" for item in matches[:3])
    return f"Ambiguous {label}: {identifier}. Try one of: {candidates}."


def _resolve_place_reference(
    conn: DBConnection,
    identifier: str,
    *,
    label: str,
    not_found_prefix: str,
    context: str | None = None,
) -> dict[str, Any]:
    cleaned_identifier = _normalize_optional_text(identifier)
    if cleaned_identifier is None:
        raise NotFoundError(f"{not_found_prefix}: {identifier}")

    place = repo.get_place_by_slug(conn, cleaned_identifier)
    if place is not None:
        return place

    collapsed_identifier, compact_identifier = _normalized_query_variants(cleaned_identifier)
    assert collapsed_identifier is not None
    places = repo.list_places(conn)

    if context is not None:
        preferred_slugs = _preferred_place_slugs_for_query(cleaned_identifier, context=context)
        preferred_matches = [
            item
            for item in places
            if str(item.get("slug") or "").strip() in preferred_slugs
        ]
        if len(preferred_matches) == 1:
            return preferred_matches[0]

    name_matches = [
        item
        for item in places
        if _matches_exact_text_candidate(
            item.get("name"),
            collapsed_query=collapsed_identifier,
            compact_query=compact_identifier,
        )
    ]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        raise InvalidRequestError(
            _format_ambiguous_place_error(cleaned_identifier, name_matches, label=label)
        )

    alias_matches = [
        item
        for item in places
        if any(
            _matches_exact_text_candidate(
                alias,
                collapsed_query=collapsed_identifier,
                compact_query=compact_identifier,
            )
            for alias in item.get("aliases", [])
        )
    ]
    if len(alias_matches) == 1:
        return alias_matches[0]
    if len(alias_matches) > 1:
        raise InvalidRequestError(
            _format_ambiguous_place_error(cleaned_identifier, alias_matches, label=label)
        )

    raise NotFoundError(f"{not_found_prefix}: {cleaned_identifier}")


def resolve_origin_place(conn: DBConnection, origin: str) -> dict[str, Any]:
    return _resolve_place_reference(
        conn,
        origin,
        label="origin",
        not_found_prefix="Origin place not found",
        context="origin",
    )


def default_restaurant_search_origin(
    conn: DBConnection,
    *,
    collapsed_query: str | None,
) -> dict[str, Any] | None:
    if collapsed_query is None:
        return None
    try:
        place = resolve_origin_place(conn, DEFAULT_RESTAURANT_SEARCH_ORIGIN)
    except NotFoundError:
        return None
    if place.get("latitude") is None or place.get("longitude") is None:
        return None
    return place


def resolve_building_place(conn: DBConnection, building: str) -> Place:
    row = _resolve_place_reference(
        conn,
        building,
        label="building",
        not_found_prefix="Building not found",
        context="building",
    )
    if row["category"] not in CLASSROOM_BUILDING_CATEGORIES:
        raise InvalidRequestError(
            "선택한 장소는 강의실 기반 건물이 아닙니다. "
            "니콜스관이나 김수환관 같은 강의동을 입력해 주세요."
        )
    return Place.model_validate(row)
