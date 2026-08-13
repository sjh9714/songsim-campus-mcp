from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx

from songsim_campus import repo
from songsim_campus import restaurant_nearby_runtime as runtime
from songsim_campus.db import connection, init_db
from songsim_campus.seed import seed_demo
from songsim_campus.services import get_place

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture_json(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _restaurant_row(
    *,
    slug: str,
    name: str,
    latitude: float,
    longitude: float,
    category: str = "korean",
    min_price: int | None = 7000,
    max_price: int | None = 9000,
    source_tag: str = "test",
    source_url: str | None = None,
    kakao_place_id: str | None = None,
) -> dict[str, object]:
    return {
        "id": -1,
        "slug": slug,
        "name": name,
        "category": category,
        "min_price": min_price,
        "max_price": max_price,
        "latitude": latitude,
        "longitude": longitude,
        "kakao_place_id": kakao_place_id,
        "source_url": source_url,
        "tags": ["한식"] if category == "korean" else ["카페"],
        "description": "테스트 식당",
        "source_tag": source_tag,
        "last_synced_at": "2026-03-18T10:00:00+09:00",
    }


def _place_row(
    *,
    slug: str,
    name: str,
    category: str = "building",
    latitude: float = 37.48590,
    longitude: float = 126.80282,
) -> dict[str, object]:
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "aliases": [],
        "description": "",
        "latitude": latitude,
        "longitude": longitude,
        "opening_hours": {},
        "source_tag": "test",
        "last_synced_at": "2026-03-18T10:00:00+09:00",
    }


def test_restaurant_nearby_runtime_module_exists():
    assert runtime is not None


def test_nearby_runtime_cache_status_transitions_cover_fresh_stale_and_expired(app_env):
    now = datetime.fromisoformat("2026-03-19T12:00:00+09:00")

    assert runtime._cache_status("2026-03-19T06:00:00+09:00", now) == "fresh"
    assert runtime._cache_status("2026-03-19T05:59:00+09:00", now) == "stale"
    assert runtime._cache_status("2026-03-18T11:59:00+09:00", now) == "expired"


def test_nearby_runtime_hours_cache_status_transitions_cover_fresh_stale_and_expired(app_env):
    now = datetime.fromisoformat("2026-03-19T12:00:00+09:00")

    assert runtime._hours_cache_status("2026-03-18T12:00:00+09:00", now) == "fresh"
    assert runtime._hours_cache_status("2026-03-18T11:59:00+09:00", now) == "stale"
    assert runtime._hours_cache_status("2026-03-12T11:59:00+09:00", now) == "expired"


def test_load_nearby_restaurant_rows_prefers_fresh_cache_before_live_fetch(app_env, monkeypatch):
    init_db()
    seed_demo(force=True)
    decisions: list[dict[str, str | int | None]] = []

    class ExplodingKakaoClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            raise AssertionError("fresh cache should be returned before live fetch")

    monkeypatch.setattr(
        runtime,
        "_record_cache_decision",
        lambda **payload: decisions.append(payload),
    )

    with connection() as conn:
        origin_place = get_place(conn, "central-library").model_dump()
        repo.replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="한식",
            radius_meters=15 * runtime.WALKING_METERS_PER_MINUTE,
            fetched_at="2026-03-18T10:00:00+09:00",
            rows=[
                _restaurant_row(
                    slug="kakao-gatolic-bap",
                    name="가톨릭백반",
                    latitude=37.48674,
                    longitude=126.80182,
                    source_tag="kakao_local_cache",
                    source_url="https://place.map.kakao.com/1",
                    kakao_place_id="1",
                )
            ],
        )

        rows = runtime.load_nearby_restaurant_rows(
            conn,
            place=origin_place,
            category="korean",
            walk_minutes=15,
            kakao_client=ExplodingKakaoClient(),
            cache_now=datetime.fromisoformat("2026-03-18T10:10:00+09:00"),
        )

    assert [row["name"] for row in rows] == ["가톨릭백반"]
    assert rows[0]["source_tag"] == "kakao_local_cache"
    assert decisions and decisions[-1]["decision"] == "fresh_hit"


def test_load_nearby_restaurant_rows_prefers_stale_cache_without_live_fetch(app_env, monkeypatch):
    init_db()
    seed_demo(force=True)
    decisions: list[dict[str, str | int | None]] = []

    class ShouldNotBeCalledKakaoClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            raise AssertionError("stale cache should be returned before live fetch")

    monkeypatch.setattr(
        runtime,
        "_record_cache_decision",
        lambda **payload: decisions.append(payload),
    )

    with connection() as conn:
        origin_place = get_place(conn, "central-library").model_dump()
        repo.replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="한식",
            radius_meters=15 * runtime.WALKING_METERS_PER_MINUTE,
            fetched_at="2026-03-18T04:00:00+09:00",
            rows=[
                _restaurant_row(
                    slug="kakao-gatolic-bap",
                    name="가톨릭백반",
                    latitude=37.48674,
                    longitude=126.80182,
                    source_tag="kakao_local_cache",
                    source_url="https://place.map.kakao.com/1",
                    kakao_place_id="1",
                )
            ],
        )

        rows = runtime.load_nearby_restaurant_rows(
            conn,
            place=origin_place,
            category="korean",
            walk_minutes=15,
            kakao_client=ShouldNotBeCalledKakaoClient(),
            cache_now=datetime.fromisoformat("2026-03-18T12:10:00+09:00"),
        )

    assert [row["name"] for row in rows] == ["가톨릭백반"]
    assert rows[0]["source_tag"] == "kakao_local_cache"
    assert decisions and decisions[-1]["decision"] == "stale_hit"


def test_load_nearby_restaurant_rows_uses_local_fallback_when_cache_expired_and_live_fails(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    decisions: list[dict[str, str | int | None]] = []

    class ExplodingKakaoClient:
        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(
        runtime,
        "_record_cache_decision",
        lambda **payload: decisions.append(payload),
    )

    with connection() as conn:
        origin_place = get_place(conn, "central-library").model_dump()
        repo.replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="한식",
            radius_meters=15 * runtime.WALKING_METERS_PER_MINUTE,
            fetched_at="2026-03-10T10:00:00+09:00",
            rows=[
                _restaurant_row(
                    slug="stale-kakao-row",
                    name="오래된외부식당",
                    latitude=37.48674,
                    longitude=126.80182,
                    source_tag="kakao_local_cache",
                    source_url="https://place.map.kakao.com/9",
                    kakao_place_id="9",
                )
            ],
        )

        rows = runtime.load_nearby_restaurant_rows(
            conn,
            place=origin_place,
            category="korean",
            walk_minutes=15,
            kakao_client=ExplodingKakaoClient(),
            cache_now=datetime.fromisoformat("2026-03-18T10:10:00+09:00"),
        )

    assert rows
    assert all(row["source_tag"] != "kakao_local_cache" for row in rows)
    assert [payload["decision"] for payload in decisions][-1] == "local_fallback"


def test_estimate_walk_minutes_uses_direct_distance_when_origin_is_not_in_graph(
    app_env,
):
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        existing_places = repo.list_places(conn)
        repo.replace_places(
            conn,
            [
                *existing_places,
                _place_row(
                    slug="annex-lobby",
                    name="별관로비",
                    category="facility",
                ),
            ],
        )
        origin_place = {
            "slug": "annex-lobby",
            "latitude": 37.48590,
            "longitude": 126.80282,
        }
        restaurant_row = _restaurant_row(
            slug="gate-bap",
            name="정문백반",
            latitude=37.48590,
            longitude=126.80282,
            source_tag="kakao_local",
        )
        minutes = runtime._estimate_place_to_restaurant_walk_minutes(
            conn,
            origin_place=origin_place,
            restaurant_row=restaurant_row,
        )

    assert minutes == runtime._direct_walk_minutes_from_coords(
        origin_place["latitude"],
        origin_place["longitude"],
        restaurant_row["latitude"],
        restaurant_row["longitude"],
    )


def test_build_nearby_restaurants_prefers_official_facility_hours_before_kakao_detail(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    hours_decisions: list[dict[str, str | None]] = []

    class ExplodingDetailClient:
        def fetch_sync(self, place_id: str):
            raise AssertionError("detail client should not be used for official facility matches")

    monkeypatch.setattr(
        runtime,
        "_record_hours_cache_decision",
        lambda **payload: hours_decisions.append(payload),
    )

    with connection() as conn:
        origin_place = get_place(conn, "central-library").model_dump()
        rows = [
            _restaurant_row(
                slug="kakao-cafe-dream",
                name="카페드림",
                latitude=37.48695,
                longitude=126.79995,
                category="cafe",
                source_tag="kakao_local_cache",
                source_url="https://place.map.kakao.com/242731511",
                kakao_place_id="242731511",
            )
        ]

        items = runtime.build_nearby_restaurants(
            conn,
            place=origin_place,
            raw_restaurants=rows,
            category="cafe",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-15T11:00:00+09:00"),
            facility_hours={
                runtime._normalize_facility_name("카페드림"): (
                    "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)"
                )
            },
            kakao_place_detail_client=ExplodingDetailClient(),
        )

    assert items[0].open_now is False
    assert hours_decisions == []


def test_build_nearby_restaurants_reuses_fresh_kakao_hours_cache(app_env, monkeypatch):
    init_db()
    seed_demo(force=True)
    now = datetime.fromisoformat("2026-03-18T10:00:00+09:00")
    hours_decisions: list[dict[str, str | None]] = []

    class ExplodingDetailClient:
        def fetch_sync(self, place_id: str):
            raise AssertionError("fresh hours cache should be used before detail fetch")

    monkeypatch.setattr(runtime, "_now", lambda: now)
    monkeypatch.setattr(
        runtime,
        "_record_hours_cache_decision",
        lambda **payload: hours_decisions.append(payload),
    )

    with connection() as conn:
        origin_place = get_place(conn, "central-library").model_dump()
        repo.upsert_restaurant_hours_cache(
            conn,
            kakao_place_id="242731511",
            source_url="https://place.map.kakao.com/242731511",
            raw_payload=_fixture_json("kakao_place_detail.json"),
            opening_hours={
                "mon": "08:00 ~ 21:00",
                "tue": "08:00 ~ 21:00",
                "wed": "08:00 ~ 21:00",
                "thu": "08:00 ~ 21:00",
                "fri": "08:00 ~ 21:00",
                "sat": "10:00 ~ 18:00",
                "sun": "휴무",
            },
            fetched_at="2026-03-18T09:00:00+09:00",
        )
        rows = [
            _restaurant_row(
                slug="kakao-gatolic-bap",
                name="가톨릭백반",
                latitude=37.48674,
                longitude=126.80182,
                source_tag="kakao_local_cache",
                source_url="https://place.map.kakao.com/242731511",
                kakao_place_id="242731511",
            )
        ]

        items = runtime.build_nearby_restaurants(
            conn,
            place=origin_place,
            raw_restaurants=rows,
            category="korean",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-16T09:00:00+09:00"),
            kakao_place_detail_client=ExplodingDetailClient(),
            facility_hours={},
        )

    assert items[0].open_now is True
    assert [payload["decision"] for payload in hours_decisions] == ["restaurant_hours_fresh_hit"]


def test_build_nearby_restaurants_uses_stale_kakao_hours_cache_when_detail_fetch_fails(
    app_env,
    monkeypatch,
):
    init_db()
    seed_demo(force=True)
    now = datetime.fromisoformat("2026-03-18T10:00:00+09:00")
    hours_decisions: list[dict[str, str | None]] = []

    class BrokenDetailClient:
        def fetch_sync(self, place_id: str):
            raise httpx.HTTPError("detail fetch failed")

    monkeypatch.setattr(runtime, "_now", lambda: now)
    monkeypatch.setattr(
        runtime,
        "_record_hours_cache_decision",
        lambda **payload: hours_decisions.append(payload),
    )

    with connection() as conn:
        origin_place = get_place(conn, "central-library").model_dump()
        repo.upsert_restaurant_hours_cache(
            conn,
            kakao_place_id="242731511",
            source_url="https://place.map.kakao.com/242731511",
            raw_payload=_fixture_json("kakao_place_detail.json"),
            opening_hours={"wed": "08:00 ~ 21:00"},
            fetched_at="2026-03-15T10:00:00+09:00",
        )
        rows = [
            _restaurant_row(
                slug="kakao-gatolic-bap",
                name="가톨릭백반",
                latitude=37.48674,
                longitude=126.80182,
                source_tag="kakao_local_cache",
                source_url="https://place.map.kakao.com/242731511",
                kakao_place_id="242731511",
            )
        ]

        items = runtime.build_nearby_restaurants(
            conn,
            place=origin_place,
            raw_restaurants=rows,
            category="korean",
            walk_minutes=15,
            at=datetime.fromisoformat("2026-03-18T10:00:00+09:00"),
            kakao_place_detail_client=BrokenDetailClient(),
            facility_hours={},
        )

    assert items[0].open_now is True
    assert [payload["decision"] for payload in hours_decisions] == [
        "restaurant_hours_live_fetch_error",
        "restaurant_hours_stale_hit",
    ]


def test_evaluate_open_now_reads_the_clock_in_seoul():
    """영업중 판정은 학교 시계로 한다.

    at.hour 와 at.weekday() 를 그대로 쓰기 때문에, UTC 로 도는 서버에서는
    아홉 시간 어긋난 시각으로 "지금 문 열었나" 를 답했다.
    """
    hours = "11:00 ~ 21:00"

    def open_at(iso: str) -> bool | None:
        return runtime._evaluate_open_now(hours, datetime.fromisoformat(iso))

    # 2026-03-16 12:00 KST 는 영업 중. 같은 순간을 UTC 로 적어도 같아야 한다.
    assert open_at("2026-03-16T12:00:00+09:00") is True
    assert open_at("2026-03-16T03:00:00+00:00") is True

    # 2026-03-16 22:00 KST 는 영업 종료.
    assert open_at("2026-03-16T22:00:00+09:00") is False
    assert open_at("2026-03-16T13:00:00+00:00") is False
