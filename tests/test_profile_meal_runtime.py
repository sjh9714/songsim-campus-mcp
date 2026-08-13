from __future__ import annotations

from datetime import datetime

from songsim_campus import profile_meal_runtime as runtime
from songsim_campus.schemas import Course, NearbyRestaurant, Place


def _course(
    *,
    code: str,
    day: str,
    period_start: int,
    period_end: int,
    room: str,
    title: str = "테스트수업",
) -> Course:
    return Course.model_validate(
        {
            "id": 1,
            "year": 2026,
            "semester": 1,
            "code": code,
            "title": title,
            "professor": "테스트교수",
            "department": "컴퓨터정보공학부",
            "section": "01",
            "day_of_week": day,
            "period_start": period_start,
            "period_end": period_end,
            "room": room,
            "raw_schedule": f"{day}{period_start}~{period_end}({room})",
            "source_tag": "test",
            "last_synced_at": "2026-03-19T10:00:00+09:00",
        }
    )


def _place(
    *,
    slug: str,
    name: str,
    latitude: float = 37.4867,
    longitude: float = 126.8018,
) -> Place:
    return Place.model_validate(
        {
            "id": 1,
            "slug": slug,
            "name": name,
            "canonical_name": name,
            "category": "building",
            "aliases": [],
            "description": "",
            "latitude": latitude,
            "longitude": longitude,
            "opening_hours": {},
            "source_tag": "test",
            "last_synced_at": "2026-03-19T10:00:00+09:00",
        }
    )


def _nearby(
    *,
    slug: str,
    name: str,
    estimated_walk_minutes: int | None,
    min_price: int | None = 7000,
    source_tag: str = "test",
) -> NearbyRestaurant:
    return NearbyRestaurant.model_validate(
        {
            "id": 1,
            "slug": slug,
            "name": name,
            "category": "korean",
            "min_price": min_price,
            "max_price": 9000,
            "latitude": 37.4867,
            "longitude": 126.8018,
            "tags": ["한식"],
            "description": "테스트 식당",
            "source_tag": source_tag,
            "last_synced_at": "2026-03-19T10:00:00+09:00",
            "distance_meters": 300,
            "estimated_walk_minutes": estimated_walk_minutes,
            "origin": "central-library",
            "open_now": True,
        }
    )


def test_compute_profile_meal_context_selects_next_course_after_sorting_same_day_timetable():
    now = datetime.fromisoformat("2026-03-16T12:00:00+09:00")
    calls: list[str] = []

    context = runtime.compute_profile_meal_context(
        timetable=[
            _course(code="CSE300", day="화", period_start=7, period_end=8, room="K201"),
            _course(code="CSE200", day="월", period_start=8, period_end=9, room="K202"),
            _course(code="CSE100", day="월", period_start=7, period_end=8, room="K201"),
        ],
        now=now,
        resolve_place_from_room=lambda room: calls.append(room or "") or _place(
            slug="kim-sou-hwan-hall",
            name="K관",
        ),
    )

    assert context.next_course is not None
    assert context.next_course.code == "CSE100"
    assert context.next_place is not None
    assert context.next_place.slug == "kim-sou-hwan-hall"
    assert context.available_minutes == 170
    assert context.walk_limit == 60
    assert context.reason is None
    assert calls == ["K201"]


def test_compute_profile_meal_context_keeps_next_place_none_when_room_cannot_map():
    now = datetime.fromisoformat("2026-03-16T12:00:00+09:00")

    context = runtime.compute_profile_meal_context(
        timetable=[_course(code="CSE100", day="월", period_start=7, period_end=8, room="ZZ101")],
        now=now,
        resolve_place_from_room=lambda room: None,
    )

    assert context.next_course is not None
    assert context.next_place is None
    assert context.reason is None


def test_compute_profile_meal_context_returns_exact_short_gap_reason():
    now = datetime.fromisoformat("2026-03-16T13:45:00+09:00")

    context = runtime.compute_profile_meal_context(
        timetable=[_course(code="CSE100", day="월", period_start=6, period_end=6, room="K201")],
        now=now,
        resolve_place_from_room=lambda room: _place(slug="kim-sou-hwan-hall", name="K관"),
    )

    assert context.available_minutes == 5
    assert context.reason == "Not enough time before the next class."


def test_build_profile_meal_response_filters_candidates_that_exceed_available_minutes():
    next_place = _place(slug="kim-sou-hwan-hall", name="K관")
    context = runtime.ProfileMealContext(
        next_course=_course(code="CSE100", day="월", period_start=7, period_end=8, room="K201"),
        next_place=next_place,
        available_minutes=20,
        walk_limit=20,
        reason=None,
    )

    response = runtime.build_profile_meal_response(
        [
            _nearby(slug="slow-bap", name="느린백반", estimated_walk_minutes=8),
            _nearby(slug="fast-bap", name="빠른백반", estimated_walk_minutes=4),
        ],
        context=context,
        limit=10,
        open_now=False,
        estimate_restaurant_to_place_walk_minutes=lambda restaurant, place: (
            9 if restaurant.slug == "slow-bap" else 5
        ),
    )

    assert [item.restaurant.name for item in response.items] == ["빠른백반"]
    assert response.items[0].total_estimated_walk_minutes == 9


def test_build_profile_meal_response_sorts_by_total_walk_then_price_then_name():
    next_place = _place(slug="kim-sou-hwan-hall", name="K관")
    context = runtime.ProfileMealContext(
        next_course=_course(code="CSE100", day="월", period_start=8, period_end=9, room="K201"),
        next_place=next_place,
        available_minutes=60,
        walk_limit=60,
        reason=None,
    )
    alpha = _nearby(slug="alpha", name="알파식당", estimated_walk_minutes=5, min_price=7000)
    beta = _nearby(slug="beta", name="베타식당", estimated_walk_minutes=5, min_price=6000)
    gamma = _nearby(slug="gamma", name="감마식당", estimated_walk_minutes=4, min_price=9000)

    response = runtime.build_profile_meal_response(
        [alpha, beta, gamma],
        context=context,
        limit=10,
        open_now=False,
        estimate_restaurant_to_place_walk_minutes=lambda restaurant, place: (
            2 if restaurant.slug == "gamma" else 2
        ),
    )

    assert [item.restaurant.name for item in response.items] == ["감마식당", "베타식당", "알파식당"]
    assert [item.total_estimated_walk_minutes for item in response.items] == [6, 7, 7]


def test_build_profile_meal_response_returns_exact_open_now_reason_when_no_items_remain():
    context = runtime.ProfileMealContext(
        next_course=None,
        next_place=None,
        available_minutes=None,
        walk_limit=15,
        reason=None,
    )

    response = runtime.build_profile_meal_response(
        [],
        context=context,
        limit=10,
        open_now=True,
        estimate_restaurant_to_place_walk_minutes=lambda restaurant, place: 0,
    )

    assert response.items == []
    assert response.reason == "No currently open restaurants matched the filters."


def test_compute_profile_meal_context_reads_the_clock_in_seoul():
    """같은 순간을 UTC 로 적어 넘겨도 학교 시계로 읽어야 한다.

    끼니 판정은 current.hour 를 그대로 쓴다. 예전에는 시간대가 붙어 있어도
    환산하지 않아서, UTC 로 도는 서버에서는 아홉 시간 어긋난 시각으로
    "다음 수업까지 몇 분 남았나" 를 계산했다.
    """
    # 2026-03-16 12:00 KST 와 같은 순간.
    in_utc = datetime.fromisoformat("2026-03-16T03:00:00+00:00")

    context = runtime.compute_profile_meal_context(
        timetable=[
            _course(code="CSE100", day="월", period_start=7, period_end=8, room="K201"),
        ],
        now=in_utc,
        resolve_place_from_room=lambda room: _place(
            slug="kim-sou-hwan-hall",
            name="K관",
        ),
    )

    assert context.next_course is not None
    assert context.next_course.code == "CSE100"
    assert context.available_minutes == 170
