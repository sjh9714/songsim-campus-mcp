from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .schemas import (
    AboutResourceGuide,
    AcademicMilestoneGuide,
    AcademicStatusGuide,
    AcademicSupportGuide,
    CampusDiningMenu,
    CampusLifeNotice,
    CampusLifeSupportGuide,
    CertificateGuide,
    ClassGuide,
    Course,
    DormitoryGuide,
    LeaveOfAbsenceGuide,
    McpCoordinates,
    McpNearbyRestaurantResult,
    McpNoticeResult,
    McpPlaceResult,
    McpRestaurantSearchResult,
    McpToolError,
    NearbyRestaurant,
    NewsroomPost,
    Notice,
    PCSoftwareEntry,
    Place,
    RegistrationGuide,
    RestaurantSearchResult,
    ScholarshipGuide,
    SeasonalSemesterGuide,
    ServicePolicyGuide,
    StudentActivityGuide,
    StudentActivityNotice,
    StudentExchangeGuide,
    TransportGuide,
    WifiGuide,
)

NOTICE_CATEGORY_DISPLAY = {
    "academic": "학사",
    "scholarship": "장학",
    "employment": "취업",
    "career": "취업",
    "event": "행사",
    "facility": "시설",
    "library": "도서관",
    "general": "일반",
    "place": "일반",
}

RESTAURANT_CATEGORY_DISPLAY = {
    "korean": "한식",
    "western": "양식",
    "japanese": "일식",
    "chinese": "중식",
    "cafe": "카페",
}


def truncate_preview(text: str, limit: int = 140) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def format_opening_hours_preview(opening_hours: Mapping[str, str]) -> str | None:
    if not opening_hours:
        return None
    preview_items: list[str] = []
    for key, value in opening_hours.items():
        preview_items.append(f"{key}: {value}")
        if len(preview_items) == 2:
            break
    return " / ".join(preview_items)


def serialize_public_error(exc: Exception) -> dict[str, str]:
    error_type = "not_found" if exc.__class__.__name__ == "NotFoundError" else "invalid_request"
    message = str(exc)
    return McpToolError(error=message, type=error_type, message=message).model_dump()


def serialize_public_place(place: Place) -> dict[str, object]:
    highlights: list[str] = []
    if place.aliases:
        highlights.append(f"별칭: {', '.join(place.aliases[:3])}")
    if place.description:
        highlights.append(truncate_preview(place.description, limit=80))
    opening_preview = format_opening_hours_preview(place.opening_hours)
    if opening_preview:
        highlights.append(f"운영: {opening_preview}")
    coordinates = None
    if place.latitude is not None and place.longitude is not None:
        coordinates = McpCoordinates(latitude=place.latitude, longitude=place.longitude)
    return McpPlaceResult(
        slug=place.slug,
        name=place.name,
        canonical_name=place.canonical_name or place.name,
        category=place.category,
        aliases=place.aliases,
        short_location=truncate_preview(place.description, limit=80) if place.description else None,
        coordinates=coordinates,
        highlights=highlights,
        matched_facility=place.matched_facility,
    ).model_dump(exclude_none=True)


def serialize_public_notice(notice: Notice) -> dict[str, object]:
    return McpNoticeResult(
        title=notice.title,
        category_display=NOTICE_CATEGORY_DISPLAY.get(notice.category, "일반"),
        published_at=notice.published_at,
        summary=truncate_preview(notice.summary, limit=160),
        source_url=notice.source_url,
    ).model_dump(exclude_none=True)


def serialize_public_affiliated_notice(notice: Any) -> dict[str, object]:
    payload = notice.model_dump()
    if payload.get("summary"):
        payload["summary"] = truncate_preview(str(payload["summary"]), limit=160)
    return payload


def serialize_public_campus_life_notice(notice: CampusLifeNotice | Any) -> dict[str, object]:
    payload = notice.model_dump() if hasattr(notice, "model_dump") else dict(notice)
    if payload.get("summary"):
        payload["summary"] = truncate_preview(str(payload["summary"]), limit=160)
    return payload


def restaurant_price_hint(min_price: int | None, max_price: int | None) -> str | None:
    if min_price is not None and max_price is not None:
        if min_price == max_price:
            return f"{min_price:,}원"
        return f"{min_price:,}~{max_price:,}원"
    if min_price is not None:
        return f"{min_price:,}원부터"
    if max_price is not None:
        return f"{max_price:,}원 이하"
    return None


def restaurant_category_label(category: str, tags: Sequence[str] = ()) -> str:
    if tags:
        return str(tags[-1])
    return RESTAURANT_CATEGORY_DISPLAY.get(category, "식당")


def serialize_public_nearby_restaurant(restaurant: NearbyRestaurant) -> dict[str, object]:
    payload = McpNearbyRestaurantResult(
        name=restaurant.name,
        category_display=restaurant_category_label(restaurant.category, restaurant.tags),
        distance_meters=restaurant.distance_meters,
        estimated_walk_minutes=restaurant.estimated_walk_minutes,
        price_hint=restaurant_price_hint(restaurant.min_price, restaurant.max_price),
        open_now=restaurant.open_now,
        location_hint=(
            truncate_preview(restaurant.description, limit=80)
            if restaurant.description
            else None
        ),
    ).model_dump(exclude_none=True)
    payload["price_hint"] = restaurant_price_hint(restaurant.min_price, restaurant.max_price)
    payload["open_now"] = restaurant.open_now
    return payload


def serialize_public_restaurant_search(restaurant: RestaurantSearchResult) -> dict[str, object]:
    payload = McpRestaurantSearchResult(
        name=restaurant.name,
        category_display=RESTAURANT_CATEGORY_DISPLAY.get(restaurant.category, "식당"),
        distance_meters=restaurant.distance_meters,
        estimated_walk_minutes=restaurant.estimated_walk_minutes,
        price_hint=restaurant_price_hint(restaurant.min_price, restaurant.max_price),
        location_hint=(
            truncate_preview(restaurant.description, limit=80)
            if restaurant.description
            else None
        ),
    ).model_dump(exclude_none=True)
    payload["distance_meters"] = restaurant.distance_meters
    payload["estimated_walk_minutes"] = restaurant.estimated_walk_minutes
    payload["price_hint"] = restaurant_price_hint(restaurant.min_price, restaurant.max_price)
    return payload


def serialize_public_dining_menu(menu: CampusDiningMenu) -> dict[str, object]:
    payload = menu.model_dump()
    if menu.menu_text is not None:
        payload["menu_text"] = menu.menu_text
    return payload


def serialize_public_course(course: Course) -> dict[str, object]:
    payload = course.model_dump()
    summary_parts = [course.title]
    if course.professor:
        summary_parts.append(course.professor)
    if course.raw_schedule:
        summary_parts.append(course.raw_schedule)
    elif course.day_of_week and course.period_start is not None and course.period_end is not None:
        summary_parts.append(f"{course.day_of_week}{course.period_start}~{course.period_end}")
    payload["course_summary"] = " / ".join(summary_parts)
    return payload


def serialize_public_transport_guide(guide: TransportGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_certificate_guide(guide: CertificateGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_leave_of_absence_guide(guide: LeaveOfAbsenceGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_scholarship_guide(guide: ScholarshipGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_wifi_guide(guide: WifiGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = ", ".join(guide.ssids) if guide.ssids else ""
    return payload


def serialize_public_academic_support_guide(guide: AcademicSupportGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_academic_status_guide(guide: AcademicStatusGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_registration_guide(guide: RegistrationGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_class_guide(guide: ClassGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_seasonal_semester_guide(
    guide: SeasonalSemesterGuide,
) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_student_activity_guide(
    guide: StudentActivityGuide,
) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_student_activity_notice(
    notice: StudentActivityNotice,
) -> dict[str, object]:
    payload = notice.model_dump()
    payload["notice_summary"] = notice.summary
    return payload


def serialize_public_about_resource_guide(
    guide: AboutResourceGuide,
) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_service_policy_guide(
    guide: ServicePolicyGuide,
) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_newsroom_post(post: NewsroomPost) -> dict[str, object]:
    payload = post.model_dump()
    payload["post_summary"] = post.summary
    return payload


def serialize_public_academic_milestone_guide(
    guide: AcademicMilestoneGuide,
) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_student_exchange_guide(
    guide: StudentExchangeGuide,
) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_campus_life_support_guide(
    guide: CampusLifeSupportGuide,
) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload


def serialize_public_pc_software_entry(entry: PCSoftwareEntry) -> dict[str, object]:
    payload = entry.model_dump()
    software_preview = ", ".join(entry.software_list[:4])
    payload["software_summary"] = software_preview
    return payload


def serialize_public_dormitory_guide(guide: DormitoryGuide) -> dict[str, object]:
    payload = guide.model_dump()
    payload["guide_summary"] = guide.summary or (guide.steps[0] if guide.steps else "")
    return payload
