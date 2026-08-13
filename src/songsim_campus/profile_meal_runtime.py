from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from . import clock
from .schemas import Course, MealRecommendation, MealRecommendationResponse, NearbyRestaurant, Place


@dataclass(frozen=True, slots=True)
class ProfileMealContext:
    next_course: Course | None
    next_place: Place | None
    available_minutes: int | None
    walk_limit: int
    reason: str | None = None


def _day_label_from_datetime(value: datetime) -> str:
    return ["월", "화", "수", "목", "금", "토", "일"][value.weekday()]


def _period_start_minutes(period: int | None) -> int | None:
    if period is None:
        return None
    class_periods = [
        (1, "09:00"),
        (2, "10:00"),
        (3, "11:00"),
        (4, "12:00"),
        (5, "13:00"),
        (6, "14:00"),
        (7, "15:00"),
        (8, "16:00"),
        (9, "17:00"),
        (10, "18:00"),
    ]
    for item_period, start in class_periods:
        if item_period == period:
            hour, minute = start.split(":")
            return int(hour) * 60 + int(minute)
    return None


def _coerce_datetime(value: datetime) -> datetime:
    return clock.coerce_datetime(value)


def compute_profile_meal_context(
    timetable: Sequence[Course],
    *,
    now: datetime,
    resolve_place_from_room: Callable[[str | None], Place | None],
) -> ProfileMealContext:
    current = _coerce_datetime(now)
    day_label = _day_label_from_datetime(current)
    same_day_courses = [
        course
        for course in timetable
        if course.day_of_week == day_label
        and _period_start_minutes(course.period_start) is not None
    ]
    same_day_courses.sort(key=lambda item: _period_start_minutes(item.period_start) or 9999)

    current_minutes = current.hour * 60 + current.minute
    next_course = None
    for course in same_day_courses:
        start_minutes = _period_start_minutes(course.period_start)
        if start_minutes is not None and start_minutes > current_minutes:
            next_course = course
            break

    next_place = resolve_place_from_room(next_course.room) if next_course else None
    available_minutes = None
    if next_course and next_course.period_start is not None:
        start_minutes = _period_start_minutes(next_course.period_start)
        if start_minutes is not None:
            available_minutes = start_minutes - current_minutes - 10

    walk_limit = 15 if available_minutes is None else max(1, min(available_minutes, 60))
    reason = (
        "Not enough time before the next class."
        if available_minutes is not None and available_minutes < 20
        else None
    )
    return ProfileMealContext(
        next_course=next_course,
        next_place=next_place,
        available_minutes=available_minutes,
        walk_limit=walk_limit,
        reason=reason,
    )


def build_profile_meal_response(
    restaurants: Sequence[NearbyRestaurant],
    *,
    context: ProfileMealContext,
    estimate_restaurant_to_place_walk_minutes: Callable[[NearbyRestaurant, Place], int],
    open_now: bool = False,
    limit: int = 10,
) -> MealRecommendationResponse:
    if context.reason is not None:
        return MealRecommendationResponse(
            items=[],
            next_course=context.next_course,
            next_place=context.next_place,
            available_minutes=context.available_minutes,
            reason=context.reason,
        )

    items: list[MealRecommendation] = []
    for restaurant in restaurants:
        total_walk_minutes = restaurant.estimated_walk_minutes
        if (
            context.next_place is not None
            and context.next_place.latitude is not None
            and context.next_place.longitude is not None
        ):
            second_leg = estimate_restaurant_to_place_walk_minutes(restaurant, context.next_place)
            total_walk_minutes = (restaurant.estimated_walk_minutes or 0) + second_leg
            exceeds_available_minutes = (
                context.available_minutes is not None
                and total_walk_minutes + 10 > context.available_minutes
            )
            if exceeds_available_minutes:
                continue
        items.append(
            MealRecommendation(
                restaurant=restaurant,
                next_course=context.next_course,
                next_place=context.next_place,
                total_estimated_walk_minutes=total_walk_minutes,
            )
        )

    items.sort(
        key=lambda item: (
            item.total_estimated_walk_minutes or 999,
            item.restaurant.min_price or 0,
            item.restaurant.name,
        )
    )
    normalized_limit = max(1, limit)
    return MealRecommendationResponse(
        items=items[:normalized_limit],
        next_course=context.next_course,
        next_place=context.next_place,
        available_minutes=context.available_minutes,
        reason=(
            "No currently open restaurants matched the filters."
            if open_now and not items
            else None
        ),
    )
