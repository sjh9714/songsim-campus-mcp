from __future__ import annotations

import heapq
import json
import logging
import math
import re
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from . import clock, ops_runtime, place_search_runtime, repo
from .db import DBConnection
from .ingest.kakao_places import (
    KakaoLocalClient,
    KakaoPlace,
    KakaoPlaceDetailClient,
    extract_kakao_place_id,
    parse_place_detail_opening_hours,
)
from .schemas import NearbyRestaurant, Place
from .settings import get_settings

logger = logging.getLogger(__name__)

WALKING_METERS_PER_MINUTE = 75
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CAMPUS_WALK_GRAPH_PATH = DATA_DIR / "campus_walk_graph.json"


def _now() -> datetime:
    return clock.now()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _coerce_datetime(value: datetime | None = None) -> datetime:
    return clock.coerce_datetime(value if value is not None else _now())


def _record_cache_decision(
    *,
    decision: str,
    origin_slug: str,
    kakao_query: str,
    radius_meters: int,
    error_text: str | None = None,
) -> None:
    ops_runtime.record_cache_decision(
        decision=decision,
        origin_slug=origin_slug,
        kakao_query=kakao_query,
        radius_meters=radius_meters,
        occurred_at=_now_iso(),
        logger=logger,
        error_text=error_text,
    )


def _record_hours_cache_decision(
    *,
    decision: str,
    kakao_place_id: str,
    source_url: str | None,
    error_text: str | None = None,
) -> None:
    ops_runtime.record_hours_cache_decision(
        decision=decision,
        kakao_place_id=kakao_place_id,
        source_url=source_url,
        occurred_at=_now_iso(),
        logger=logger,
        error_text=error_text,
    )


def _normalize_facility_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    for token in ("가톨릭대학교", "가톨릭대", "성심교정"):
        normalized = normalized.replace(token, "")
    normalized = "".join(char for char in normalized if not char.isspace())
    if normalized.endswith("점"):
        normalized = normalized[:-1]
    return normalized


def _minutes_from_time_string(value: str) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if minute > 59:
        return None
    if hour == 24:
        return 24 * 60 if minute == 0 else None
    if hour > 23:
        return None
    return hour * 60 + minute


def _extract_time_range(value: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2}:\d{2})\s*[~\\-]\s*(\d{1,2}:\d{2})", value)
    if not match:
        return None
    start = _minutes_from_time_string(match.group(1))
    end = _minutes_from_time_string(match.group(2))
    if start is None or end is None:
        return None
    return start, end


def _is_in_time_range(current_minutes: int, time_range: tuple[int, int]) -> bool:
    start, end = time_range
    if end == start:
        return False
    if end < start:
        return current_minutes >= start or current_minutes < end
    return start <= current_minutes < end


def _is_explicitly_closed_for_day(value: str, weekday: int) -> bool:
    compact = value.strip().lower().replace(" ", "")
    if compact == "휴무":
        return True
    if "휴무" not in compact:
        return False
    if weekday == 6 and any(
        token in compact
        for token in ("일/공휴일휴무", "일휴무", "일요일휴무", "토/일휴무", "주말휴무")
    ):
        return True
    if weekday == 5 and any(
        token in compact for token in ("토휴무", "토요일휴무", "토/일휴무", "주말휴무")
    ):
        return True
    if weekday < 5 and any(
        token in compact for token in ("평일휴무", "주중휴무", "weekdayclosed")
    ):
        return True
    return False


def _find_day_specific_time_ranges(value: str, weekday: int) -> tuple[bool, list[tuple[int, int]]]:
    time_pattern = r"(\d{1,2}:\d{2}\s*[~\\-]\s*\d{1,2}:\d{2})"
    patterns = [
        (
            (0, 1, 2, 3, 4),
            [
                rf"평일\s*{time_pattern}",
                rf"mon-fri\s*{time_pattern}",
                rf"weekday\s*{time_pattern}",
            ],
        ),
        (
            (5,),
            [
                rf"(?:토요일|토)\s*{time_pattern}",
                rf"sat\s*{time_pattern}",
            ],
        ),
        (
            (6,),
            [
                rf"(?:일요일|일)\s*{time_pattern}",
                rf"sun\s*{time_pattern}",
            ],
        ),
    ]
    found_any = False
    matches: list[tuple[int, int]] = []
    for days, options in patterns:
        for option in options:
            match = re.search(option, value, flags=re.IGNORECASE)
            if not match:
                continue
            found_any = True
            time_range = _extract_time_range(match.group(1))
            if time_range:
                start, end = time_range
                if end > start:
                    if weekday in days:
                        matches.append(time_range)
                else:
                    if weekday in days:
                        matches.append((start, 24 * 60))
                    spillover_days = {((day + 1) % 7) for day in days}
                    if weekday in spillover_days:
                        matches.append((0, end))
            break
    return found_any, matches


def _evaluate_open_now(hours_text: str, at: datetime) -> bool | None:
    if not hours_text.strip():
        return None

    # 영업시간은 한국 시간으로 적힌 값이라 시/분/요일을 학교 시계로 읽어야 한다.
    at = clock.coerce_datetime(at)

    compact = hours_text.strip().lower().replace(" ", "")
    if "24시간" in compact or "24hours" in compact:
        return True

    weekday = at.weekday()
    current_minutes = at.hour * 60 + at.minute

    if _is_explicitly_closed_for_day(hours_text, weekday):
        return False

    found_day_rules, day_ranges = _find_day_specific_time_ranges(hours_text, weekday)
    if day_ranges:
        return any(_is_in_time_range(current_minutes, item) for item in day_ranges)
    if found_day_rules:
        return False

    generic_range = _extract_time_range(hours_text)
    if generic_range:
        return _is_in_time_range(current_minutes, generic_range)
    if "휴무" in compact:
        return False
    return None


def _hours_cache_status(fetched_at: str, now: datetime) -> str:
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except ValueError:
        return "expired"
    if fetched.tzinfo is None:
        # 저장된 시각은 학교 기준으로 적힌 값이다. 호스트 시간대로 읽으면 안 된다.
        fetched = clock.coerce_datetime(fetched)
    age_minutes = (now - fetched).total_seconds() / 60
    settings = get_settings()
    if age_minutes <= settings.restaurant_hours_cache_ttl_minutes:
        return "fresh"
    if age_minutes <= settings.restaurant_hours_cache_stale_ttl_minutes:
        return "stale"
    return "expired"


def _evaluate_open_now_from_map(
    opening_hours: dict[str, str],
    at: datetime,
    *,
    evaluate_open_now: Callable[[str, datetime], bool | None] | None = None,
) -> bool | None:
    if not opening_hours:
        return None
    evaluator = evaluate_open_now or _evaluate_open_now
    day_keys = {
        0: "mon",
        1: "tue",
        2: "wed",
        3: "thu",
        4: "fri",
        5: "sat",
        6: "sun",
    }
    day_key = day_keys[at.weekday()]
    hours_text = opening_hours.get(day_key)
    if not hours_text and at.weekday() < 5:
        hours_text = opening_hours.get("weekday")
    if not hours_text:
        return None

    is_open = evaluator(hours_text, at)
    if is_open is not True:
        return is_open

    break_text = opening_hours.get(f"{day_key}_break")
    if break_text and evaluator(break_text, at):
        return False
    return True


def _restaurant_open_now(
    conn: DBConnection,
    restaurant_row: dict[str, Any],
    facility_hours: dict[str, str],
    at: datetime,
    *,
    evaluate_open_now: Callable[[str, datetime], bool | None] | None = None,
    kakao_place_detail_client: KakaoPlaceDetailClient | Any | None = None,
    detail_client_factory: Callable[[], KakaoPlaceDetailClient | Any] = KakaoPlaceDetailClient,
    now_fn: Callable[[], datetime] | None = None,
    now_iso: Callable[[], str] | None = None,
    record_hours_cache_decision: Callable[..., None] | None = None,
) -> bool | None:
    evaluator = evaluate_open_now or _evaluate_open_now
    resolve_now = now_fn or _now
    resolve_now_iso = now_iso or _now_iso
    record_decision = record_hours_cache_decision or _record_hours_cache_decision
    restaurant_name = str(restaurant_row.get("name") or "")
    hours_text = facility_hours.get(_normalize_facility_name(restaurant_name))
    if hours_text:
        return evaluator(hours_text, at)

    if not _is_external_restaurant_route(restaurant_row.get("source_tag")):
        return None

    place_id = restaurant_row.get("kakao_place_id") or extract_kakao_place_id(
        str(restaurant_row.get("source_url") or "")
    )
    if not place_id:
        return None

    current = resolve_now()
    cached = repo.get_restaurant_hours_cache(conn, kakao_place_id=place_id)
    cache_state = (
        _hours_cache_status(str(cached["fetched_at"]), current)
        if cached is not None
        else "expired"
    )
    if cached is not None and cache_state == "fresh":
        record_decision(
            decision="restaurant_hours_fresh_hit",
            kakao_place_id=place_id,
            source_url=restaurant_row.get("source_url"),
        )
        return _evaluate_open_now_from_map(
            cached.get("opening_hours", {}),
            at,
            evaluate_open_now=evaluator,
        )

    if kakao_place_detail_client is None:
        kakao_place_detail_client = detail_client_factory()

    try:
        payload = kakao_place_detail_client.fetch_sync(place_id)
        opening_hours = parse_place_detail_opening_hours(payload)
        repo.upsert_restaurant_hours_cache(
            conn,
            kakao_place_id=place_id,
            source_url=restaurant_row.get("source_url"),
            raw_payload=payload,
            opening_hours=opening_hours,
            fetched_at=resolve_now_iso(),
        )
        record_decision(
            decision="restaurant_hours_live_fetch_success",
            kakao_place_id=place_id,
            source_url=restaurant_row.get("source_url"),
        )
        return _evaluate_open_now_from_map(
            opening_hours,
            at,
            evaluate_open_now=evaluator,
        )
    except (httpx.HTTPError, ValueError) as exc:
        record_decision(
            decision="restaurant_hours_live_fetch_error",
            kakao_place_id=place_id,
            source_url=restaurant_row.get("source_url"),
            error_text=str(exc),
        )
        if cached is not None and cache_state == "stale":
            record_decision(
                decision="restaurant_hours_stale_hit",
                kakao_place_id=place_id,
                source_url=restaurant_row.get("source_url"),
            )
            return _evaluate_open_now_from_map(
                cached.get("opening_hours", {}),
                at,
                evaluate_open_now=evaluator,
            )
        return None


def _parse_campus_walk_graph(payload: dict[str, Any]) -> dict[str, Any]:
    nodes_raw = payload.get("nodes")
    edges_raw = payload.get("edges")
    if not isinstance(nodes_raw, list):
        raise ValueError("campus walk graph nodes must be a list")
    if not isinstance(edges_raw, list):
        raise ValueError("campus walk graph edges must be a list")

    nodes: list[str] = []
    for item in nodes_raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("campus walk graph nodes must be non-empty strings")
        slug = item.strip()
        if slug not in nodes:
            nodes.append(slug)

    adjacency: dict[str, list[tuple[str, int]]] = {slug: [] for slug in nodes}
    node_set = set(nodes)
    for edge in edges_raw:
        if not isinstance(edge, dict):
            raise ValueError("campus walk graph edges must be objects")
        start = str(edge.get("from", "")).strip()
        end = str(edge.get("to", "")).strip()
        if start not in node_set or end not in node_set:
            raise ValueError("campus walk graph edge references unknown node")
        walk_minutes = edge.get("walk_minutes")
        if not isinstance(walk_minutes, int) or isinstance(walk_minutes, bool) or walk_minutes <= 0:
            raise ValueError("campus walk graph edges must use positive walk_minutes")
        adjacency[start].append((end, walk_minutes))

    return {"nodes": frozenset(node_set), "adjacency": adjacency}


@lru_cache(maxsize=1)
def _load_campus_walk_graph() -> dict[str, Any]:
    payload = json.loads(CAMPUS_WALK_GRAPH_PATH.read_text(encoding="utf-8"))
    return _parse_campus_walk_graph(payload)


def _campus_walk_minutes(start_slug: str, end_slug: str) -> int | None:
    if start_slug == end_slug:
        return 0
    graph = _load_campus_walk_graph()
    nodes: frozenset[str] = graph["nodes"]
    if start_slug not in nodes or end_slug not in nodes:
        return None
    adjacency: dict[str, list[tuple[str, int]]] = graph["adjacency"]
    queue: list[tuple[int, str]] = [(0, start_slug)]
    seen: dict[str, int] = {start_slug: 0}
    while queue:
        cost, slug = heapq.heappop(queue)
        if slug == end_slug:
            return cost
        if cost > seen.get(slug, cost):
            continue
        for neighbor, weight in adjacency.get(slug, []):
            next_cost = cost + weight
            if next_cost >= seen.get(neighbor, next_cost + 1):
                continue
            seen[neighbor] = next_cost
            heapq.heappush(queue, (next_cost, neighbor))
    return None


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return int(2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _direct_walk_minutes_from_coords(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> int:
    return max(1, round(_haversine_meters(lat1, lon1, lat2, lon2) / WALKING_METERS_PER_MINUTE))


def _campus_gate_places(conn: DBConnection) -> list[dict[str, Any]]:
    graph_nodes: frozenset[str] = _load_campus_walk_graph()["nodes"]
    return [
        place
        for place in repo.list_places(conn)
        if place["slug"] in graph_nodes
        and place["category"] == "gate"
        and place.get("latitude") is not None
        and place.get("longitude") is not None
    ]


def _is_external_restaurant_route(source_tag: str | None) -> bool:
    return (source_tag or "").startswith("kakao_local")


def _estimate_place_to_restaurant_walk_minutes(
    conn: DBConnection,
    *,
    origin_place: dict[str, Any],
    restaurant_row: dict[str, Any],
) -> int:
    direct_minutes = _direct_walk_minutes_from_coords(
        origin_place["latitude"],
        origin_place["longitude"],
        restaurant_row["latitude"],
        restaurant_row["longitude"],
    )
    if not _is_external_restaurant_route(restaurant_row.get("source_tag")):
        return direct_minutes

    best_minutes: int | None = None
    for gate in _campus_gate_places(conn):
        internal_minutes = _campus_walk_minutes(origin_place["slug"], gate["slug"])
        if internal_minutes is None:
            continue
        external_minutes = _direct_walk_minutes_from_coords(
            gate["latitude"],
            gate["longitude"],
            restaurant_row["latitude"],
            restaurant_row["longitude"],
        )
        total_minutes = internal_minutes + external_minutes
        if best_minutes is None or total_minutes < best_minutes:
            best_minutes = total_minutes
    return best_minutes or direct_minutes


def _estimate_restaurant_to_place_walk_minutes(
    conn: DBConnection,
    *,
    restaurant_latitude: float,
    restaurant_longitude: float,
    restaurant_source_tag: str | None,
    next_place: Place,
) -> int:
    direct_minutes = _direct_walk_minutes_from_coords(
        restaurant_latitude,
        restaurant_longitude,
        next_place.latitude,
        next_place.longitude,
    )
    if not _is_external_restaurant_route(restaurant_source_tag):
        return direct_minutes

    best_minutes: int | None = None
    for gate in _campus_gate_places(conn):
        internal_minutes = _campus_walk_minutes(gate["slug"], next_place.slug)
        if internal_minutes is None:
            continue
        external_minutes = _direct_walk_minutes_from_coords(
            restaurant_latitude,
            restaurant_longitude,
            gate["latitude"],
            gate["longitude"],
        )
        total_minutes = external_minutes + internal_minutes
        if best_minutes is None or total_minutes < best_minutes:
            best_minutes = total_minutes
    return best_minutes or direct_minutes


def _infer_kakao_category(category_name: str) -> str:
    normalized = category_name.lower()
    if "카페" in category_name or "cafe" in normalized:
        return "cafe"
    if "일식" in category_name or "japanese" in normalized:
        return "japanese"
    if "양식" in category_name or "western" in normalized:
        return "western"
    if "중식" in category_name or "chinese" in normalized:
        return "chinese"
    return "korean"


def _normalize_kakao_restaurant(place: KakaoPlace, *, fetched_at: str) -> dict[str, Any]:
    slug = f"kakao-{place.name}-{place.latitude:.5f}-{place.longitude:.5f}".lower()
    slug = "".join(char if char.isalnum() else "-" for char in slug).strip("-")
    return {
        "slug": slug,
        "name": place.name,
        "category": _infer_kakao_category(place.category),
        "min_price": None,
        "max_price": None,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "kakao_place_id": place.place_id or extract_kakao_place_id(place.place_url),
        "source_url": place.place_url or None,
        "tags": [segment.strip() for segment in place.category.split(">") if segment.strip()][-2:],
        "description": place.address,
        "source_tag": "kakao_local",
        "last_synced_at": fetched_at,
    }


def _cached_kakao_restaurant_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "source_tag": "kakao_local_cache"} for row in rows]


def _category_to_kakao_query(category: str | None) -> str:
    mapping = {
        "korean": "한식",
        "japanese": "일식",
        "western": "양식",
        "chinese": "중식",
        "cafe": "카페",
    }
    return mapping.get(category or "", "식당")


def _restaurant_cache_key(
    origin_slug: str,
    category: str | None,
    walk_minutes: int,
) -> tuple[str, str, int]:
    return (
        origin_slug,
        _category_to_kakao_query(category),
        walk_minutes * WALKING_METERS_PER_MINUTE,
    )


def _cache_status(fetched_at: str, now: datetime) -> str:
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except ValueError:
        return "expired"
    if fetched.tzinfo is None:
        # 저장된 시각은 학교 기준으로 적힌 값이다. 호스트 시간대로 읽으면 안 된다.
        fetched = clock.coerce_datetime(fetched)
    age_minutes = (now - fetched).total_seconds() / 60
    settings = get_settings()
    if age_minutes <= settings.restaurant_cache_ttl_minutes:
        return "fresh"
    if age_minutes <= settings.restaurant_cache_stale_ttl_minutes:
        return "stale"
    return "expired"


def _cache_rows_for_key(
    conn: DBConnection,
    *,
    origin_slug: str,
    kakao_query: str,
    radius_meters: int,
    latitude: float,
    longitude: float,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    snapshot = repo.get_restaurant_cache_snapshot(
        conn,
        origin_slug=origin_slug,
        kakao_query=kakao_query,
        radius_meters=radius_meters,
    )
    if not snapshot:
        return None, []
    return snapshot, repo.list_restaurant_cache_items(
        conn,
        int(snapshot["id"]),
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
    )


def _live_restaurant_rows(
    *,
    place: dict[str, Any],
    kakao_query: str,
    radius_meters: int,
    kakao_client: KakaoLocalClient | Any,
    now_iso: Callable[[], str] | None = None,
) -> list[dict[str, Any]]:
    resolve_now_iso = now_iso or _now_iso
    fetched_at = resolve_now_iso()
    items = kakao_client.search_sync(
        kakao_query,
        x=place["longitude"],
        y=place["latitude"],
        radius=radius_meters,
    )
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        row = _normalize_kakao_restaurant(item, fetched_at=fetched_at)
        row["id"] = -index
        rows.append(row)
    return rows


def load_nearby_restaurant_rows(
    conn: DBConnection,
    *,
    place: dict[str, Any],
    category: str | None = None,
    walk_minutes: int = 15,
    cache_now: datetime | None = None,
    now: datetime | None = None,
    now_iso: Callable[[], str] | None = None,
    kakao_client: KakaoLocalClient | Any | None = None,
    record_cache_decision: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    resolved_cache_now = cache_now or now or _now()
    resolve_now_iso = now_iso or _now_iso
    record_decision = record_cache_decision or _record_cache_decision
    origin_slug, kakao_query, radius_meters = _restaurant_cache_key(
        place["slug"],
        category,
        walk_minutes,
    )
    snapshot, cached_rows = _cache_rows_for_key(
        conn,
        origin_slug=origin_slug,
        kakao_query=kakao_query,
        radius_meters=radius_meters,
        latitude=place["latitude"],
        longitude=place["longitude"],
    )
    cache_state = (
        _cache_status(str(snapshot["fetched_at"]), resolved_cache_now)
        if snapshot is not None
        else "expired"
    )

    if snapshot is not None and cache_state == "fresh":
        record_decision(
            decision="fresh_hit",
            origin_slug=origin_slug,
            kakao_query=kakao_query,
            radius_meters=radius_meters,
        )
        return cached_rows

    if snapshot is not None and cache_state == "stale":
        record_decision(
            decision="stale_hit",
            origin_slug=origin_slug,
            kakao_query=kakao_query,
            radius_meters=radius_meters,
        )
        return cached_rows

    if kakao_client is not None:
        try:
            live_rows = _live_restaurant_rows(
                place=place,
                kakao_query=kakao_query,
                radius_meters=radius_meters,
                kakao_client=kakao_client,
                now_iso=resolve_now_iso,
            )
            snapshot_id = repo.replace_restaurant_cache_snapshot(
                conn,
                origin_slug=origin_slug,
                kakao_query=kakao_query,
                radius_meters=radius_meters,
                fetched_at=live_rows[0]["last_synced_at"] if live_rows else resolve_now_iso(),
                rows=_cached_kakao_restaurant_rows(live_rows),
            )
            record_decision(
                decision="live_fetch_success",
                origin_slug=origin_slug,
                kakao_query=kakao_query,
                radius_meters=radius_meters,
            )
            return [
                {**row, "source_tag": "kakao_local"}
                for row in repo.list_restaurant_cache_items(
                    conn,
                    snapshot_id,
                    latitude=place["latitude"],
                    longitude=place["longitude"],
                    radius_meters=radius_meters,
                )
            ]
        except httpx.HTTPError:
            record_decision(
                decision="live_fetch_error",
                origin_slug=origin_slug,
                kakao_query=kakao_query,
                radius_meters=radius_meters,
                error_text="kakao_fetch_failed",
            )

    record_decision(
        decision="local_fallback",
        origin_slug=origin_slug,
        kakao_query=kakao_query,
        radius_meters=radius_meters,
    )
    return repo.list_restaurants_nearby(
        conn,
        latitude=place["latitude"],
        longitude=place["longitude"],
        radius_meters=radius_meters,
    )


def build_nearby_restaurants(
    conn: DBConnection,
    *,
    raw_restaurants: list[dict[str, Any]],
    place: dict[str, Any],
    category: str | None = None,
    budget_max: int | None = None,
    walk_minutes: int = 15,
    limit: int = 10,
    at: datetime | None = None,
    current: datetime | None = None,
    open_now: bool = False,
    kakao_place_detail_client: KakaoPlaceDetailClient | Any | None = None,
    facility_hours: dict[str, str] | None = None,
    evaluate_open_now: Callable[[str, datetime], bool | None] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    now_iso: Callable[[], str] | None = None,
    record_hours_cache_decision: Callable[..., None] | None = None,
) -> list[NearbyRestaurant]:
    resolved_current = _coerce_datetime(current or at)
    hours_index = (
        facility_hours
        if facility_hours is not None
        else place_search_runtime._facility_hours_index(conn)
    )

    results: list[NearbyRestaurant] = []
    for raw in raw_restaurants:
        if category and raw["category"] != category:
            continue
        if budget_max is not None:
            min_price = raw.get("min_price")
            max_price = raw.get("max_price")
            if min_price is not None:
                if min_price > budget_max:
                    continue
            elif max_price is not None:
                if max_price > budget_max:
                    continue
            else:
                continue
        if raw.get("latitude") is None or raw.get("longitude") is None:
            continue

        distance = raw.get("distance_meters") or _haversine_meters(
            place["latitude"],
            place["longitude"],
            raw["latitude"],
            raw["longitude"],
        )
        estimated_walk_minutes = _estimate_place_to_restaurant_walk_minutes(
            conn,
            origin_place=place,
            restaurant_row=raw,
        )
        if estimated_walk_minutes > walk_minutes:
            continue
        current_open_now = _restaurant_open_now(
            conn,
            raw,
            hours_index,
            resolved_current,
            evaluate_open_now=evaluate_open_now,
            kakao_place_detail_client=kakao_place_detail_client,
            now_fn=now_fn,
            now_iso=now_iso,
            record_hours_cache_decision=record_hours_cache_decision,
        )
        if open_now and current_open_now is not True:
            continue

        results.append(
            NearbyRestaurant.model_validate(
                {
                    **raw,
                    "distance_meters": distance,
                    "estimated_walk_minutes": estimated_walk_minutes,
                    "origin": place["slug"],
                    "open_now": current_open_now,
                }
            )
        )

    results.sort(
        key=lambda item: (
            item.estimated_walk_minutes or 999,
            item.min_price or 0,
            item.name,
        )
    )
    return results[:limit]


def estimate_place_to_restaurant_walk_minutes(
    conn: DBConnection,
    *,
    origin_place: dict[str, Any],
    restaurant_row: dict[str, Any],
) -> int:
    return _estimate_place_to_restaurant_walk_minutes(
        conn,
        origin_place=origin_place,
        restaurant_row=restaurant_row,
    )


def estimate_restaurant_to_place_walk_minutes(
    conn: DBConnection,
    *,
    restaurant_latitude: float,
    restaurant_longitude: float,
    restaurant_source_tag: str | None,
    next_place: Place,
) -> int:
    return _estimate_restaurant_to_place_walk_minutes(
        conn,
        restaurant_latitude=restaurant_latitude,
        restaurant_longitude=restaurant_longitude,
        restaurant_source_tag=restaurant_source_tag,
        next_place=next_place,
    )
