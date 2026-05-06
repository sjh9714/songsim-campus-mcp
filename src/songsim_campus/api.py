from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import parse_qs

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .api_docs import (
    build_gpt_actions_openapi,
    build_gpt_actions_openapi_v2,
    build_gpt_actions_openapi_v3,
)
from .api_pages import (
    render_admin_observability_page,
    render_admin_sync_page,
    render_landing_page,
    render_privacy_page,
)
from .db import connection, get_connection, init_db
from .schemas import (
    AboutResourceGuide,
    AcademicCalendarEvent,
    AcademicMilestoneGuide,
    AcademicStatusGuide,
    AcademicSupportGuide,
    AffiliatedNotice,
    CampusDiningMenu,
    CampusLifeNotice,
    CampusLifeSupportGuide,
    CertificateGuide,
    ClassGuide,
    Course,
    DormitoryGuide,
    EstimatedEmptyClassroomResponse,
    GptCampusDiningMenuResult,
    GptLibrarySeatStatusResponse,
    GptLibrarySeatStatusResult,
    GptNearbyRestaurantResult,
    GptNoticeCategoryInfo,
    GptNoticeResult,
    GptPlaceResult,
    GptRestaurantSearchResult,
    LeaveOfAbsenceGuide,
    LibrarySeatStatusResponse,
    MatchedCourse,
    MatchedNotice,
    McpCoordinates,
    MealRecommendationResponse,
    NearbyRestaurant,
    NewsroomPost,
    Notice,
    NoticeCategoryInfo,
    PCSoftwareEntry,
    Period,
    PhoneBookEntry,
    Place,
    Profile,
    ProfileCourseRef,
    ProfileCreateRequest,
    ProfileInterests,
    ProfileNoticePreferences,
    ProfileUpdateRequest,
    RegistrationGuide,
    Restaurant,
    RestaurantSearchResult,
    ScholarshipGuide,
    SeasonalSemesterGuide,
    ServicePolicyGuide,
    StudentActivityGuide,
    StudentExchangeGuide,
    StudentExchangePartner,
    TransportGuide,
    WifiGuide,
)
from .seed import seed_demo
from .services import (
    InvalidRequestError,
    NotFoundError,
    _campus_dining_menu_preview,
    create_profile,
    find_nearby_restaurants,
    get_class_periods,
    get_library_seat_status,
    get_notice_categories,
    get_observability_snapshot,
    get_place,
    get_profile_course_recommendations,
    get_profile_interests,
    get_profile_meal_recommendations,
    get_profile_timetable,
    get_readiness_snapshot,
    get_sync_dashboard_state,
    list_about_resource_guides,
    list_academic_calendar,
    list_academic_milestone_guides,
    list_academic_status_guides,
    list_academic_support_guides,
    list_campus_life_notices,
    list_campus_life_support_guides,
    list_certificate_guides,
    list_class_guides,
    list_dormitory_guides,
    list_estimated_empty_classrooms,
    list_latest_notices,
    list_leave_of_absence_guides,
    list_newsroom_posts,
    list_profile_notices,
    list_registration_guides,
    list_restaurants,
    list_scholarship_guides,
    list_seasonal_semester_guides,
    list_service_policy_guides,
    list_student_activity_guides,
    list_student_exchange_guides,
    list_transport_guides,
    list_wifi_guides,
    release_automation_leader,
    run_admin_sync,
    run_automation_tick,
    search_campus_dining_menus,
    search_courses,
    search_pc_software_entries,
    search_phone_book_entries,
    search_places,
    search_restaurants,
    search_student_exchange_partners,
    set_automation_leader,
    set_profile_interests,
    set_profile_notice_preferences,
    set_profile_timetable,
    sync_official_snapshot,
    try_acquire_automation_leader,
    update_profile,
)
from .settings import get_settings

logger = logging.getLogger(__name__)

GPT_NOTICE_CATEGORY_DISPLAY = {
    "academic": "academic",
    "scholarship": "scholarship",
    "employment": "employment",
    "career": "employment",
    "event": "event",
    "facility": "facility",
    "library": "library",
    "general": "general",
    "place": "general",
}

GPT_RESTAURANT_CATEGORY_DISPLAY = {
    "korean": "한식",
    "western": "양식",
    "japanese": "일식",
    "chinese": "중식",
    "cafe": "카페",
}
@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings = get_settings()
    stop_event = asyncio.Event()
    automation_task: asyncio.Task[None] | None = None
    if settings.startup_sync_enabled:
        with connection() as conn:
            sync_official_snapshot(conn)
    elif settings.seed_demo_on_start:
        seed_demo(force=False)
    if settings.automation_runtime_enabled:
        set_automation_leader(False)

        async def automation_loop() -> None:
            lock_conn = get_connection()
            leader = False
            try:
                while not stop_event.is_set():
                    if not leader:
                        leader = await asyncio.to_thread(try_acquire_automation_leader, lock_conn)
                        if not leader:
                            logger.info("event=automation_lock_skipped")
                    if leader:
                        await asyncio.to_thread(run_automation_tick)
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=settings.automation_tick_seconds,
                        )
                    except TimeoutError:
                        continue
            finally:
                if leader:
                    await asyncio.to_thread(release_automation_leader, lock_conn)
                lock_conn.close()
                set_automation_leader(False)

        automation_task = asyncio.create_task(automation_loop(), name="songsim-automation")
    try:
        yield
    finally:
        stop_event.set()
        if automation_task is not None:
            await automation_task


def create_app() -> FastAPI:
    settings = get_settings()
    public_readonly = settings.app_mode == "public_readonly"
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    def _truncate_preview(text: str, *, limit: int) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 3)].rstrip() + "..."

    def _format_opening_hours_preview(opening_hours: dict[str, str]) -> str | None:
        if not opening_hours:
            return None
        preview_items = []
        for key, value in sorted(opening_hours.items()):
            preview_items.append(f"{key}: {value}")
            if len(preview_items) == 2:
                break
        return " / ".join(preview_items)

    def _restaurant_price_hint(restaurant: NearbyRestaurant) -> str | None:
        if restaurant.min_price is not None and restaurant.max_price is not None:
            if restaurant.min_price == restaurant.max_price:
                return f"{restaurant.min_price:,}원"
            return f"{restaurant.min_price:,}~{restaurant.max_price:,}원"
        if restaurant.min_price is not None:
            return f"{restaurant.min_price:,}원부터"
        if restaurant.max_price is not None:
            return f"{restaurant.max_price:,}원 이하"
        return None

    def _serialize_gpt_notice_category(
        item: NoticeCategoryInfo,
    ) -> GptNoticeCategoryInfo:
        return GptNoticeCategoryInfo(
            category=item.category,
            category_display=GPT_NOTICE_CATEGORY_DISPLAY.get(item.category, item.category),
            aliases=item.aliases,
        )

    def _gpt_restaurant_category_label(restaurant: NearbyRestaurant) -> str:
        return GPT_RESTAURANT_CATEGORY_DISPLAY.get(
            restaurant.category,
            restaurant.tags[0] if restaurant.tags else "식당",
        )

    def _serialize_gpt_place(place: Place) -> dict[str, object]:
        highlights: list[str] = []
        if place.aliases:
            highlights.append(f"별칭: {', '.join(place.aliases[:3])}")
        if place.description:
            highlights.append(_truncate_preview(place.description, limit=80))
        opening_preview = _format_opening_hours_preview(place.opening_hours)
        if opening_preview:
            highlights.append(f"운영: {opening_preview}")
        coordinates = None
        if place.latitude is not None and place.longitude is not None:
            coordinates = McpCoordinates(latitude=place.latitude, longitude=place.longitude)
        return GptPlaceResult(
            name=place.name,
            canonical_name=place.canonical_name or place.name,
            aliases=place.aliases,
            category=place.category,
            short_location=place.description or None,
            coordinates=coordinates,
            highlights=highlights,
        ).model_dump(exclude_none=True)

    def _serialize_gpt_notice(notice: Notice) -> dict[str, object]:
        return GptNoticeResult(
            title=notice.title,
            category_display=GPT_NOTICE_CATEGORY_DISPLAY.get(notice.category, "general"),
            published_at=notice.published_at,
            summary=_truncate_preview(notice.summary, limit=120),
            source_url=notice.source_url,
        ).model_dump(exclude_none=True)

    def _serialize_gpt_nearby_restaurant(restaurant: NearbyRestaurant) -> dict[str, object]:
        return GptNearbyRestaurantResult(
            name=restaurant.name,
            category_display=_gpt_restaurant_category_label(restaurant),
            distance_meters=restaurant.distance_meters,
            estimated_walk_minutes=restaurant.estimated_walk_minutes,
            price_hint=_restaurant_price_hint(restaurant),
            open_now=restaurant.open_now,
            location_hint=(
                _truncate_preview(restaurant.description, limit=80)
                if restaurant.description
                else None
            ),
        ).model_dump()

    def _serialize_gpt_restaurant_search(
        restaurant: RestaurantSearchResult,
    ) -> dict[str, object]:
        return GptRestaurantSearchResult(
            name=restaurant.name,
            category_display=GPT_RESTAURANT_CATEGORY_DISPLAY.get(
                restaurant.category,
                restaurant.tags[0] if restaurant.tags else "식당",
            ),
            distance_meters=restaurant.distance_meters,
            estimated_walk_minutes=restaurant.estimated_walk_minutes,
            price_hint=_restaurant_price_hint(restaurant),
            location_hint=(
                _truncate_preview(restaurant.description, limit=80)
                if restaurant.description
                else None
            ),
        ).model_dump()

    def _serialize_gpt_dining_menu(menu: CampusDiningMenu) -> dict[str, object]:
        return GptCampusDiningMenuResult(
            venue_name=menu.venue_name,
            place_name=menu.place_name,
            week_label=menu.week_label,
            menu_preview=_campus_dining_menu_preview(menu.menu_text),
            source_url=menu.source_url,
        ).model_dump(exclude_none=True)

    def _serialize_gpt_library_seat_status(
        response: LibrarySeatStatusResponse,
    ) -> dict[str, object]:
        return GptLibrarySeatStatusResponse(
            availability_mode=response.availability_mode,
            checked_at=response.checked_at,
            note=response.note,
            source_url=response.source_url,
            rooms=[
                GptLibrarySeatStatusResult(
                    room_name=item.room_name,
                    remaining_seats=item.remaining_seats,
                    total_seats=item.total_seats,
                    availability_mode=response.availability_mode,
                    checked_at=response.checked_at,
                )
                for item in response.rooms
            ],
        ).model_dump(exclude_none=True)

    def ensure_admin_request_allowed(request: Request) -> None:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(
                status_code=403,
                detail="Admin dashboard is only available from loopback clients.",
            )

    @app.get("/healthz")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request) -> HTMLResponse:
        public_http_url = settings.public_http_url or str(request.base_url).rstrip("/")
        mcp_url = (
            settings.public_mcp_url
            or "Set SONGSIM_PUBLIC_MCP_URL to show the public MCP URL."
        )
        oauth_enabled = (
            settings.app_mode == "public_readonly"
            and settings.public_mcp_auth_mode == "oauth"
        )
        admin_link = (
            '<a class="pill" href="/admin/sync">Admin Sync</a>'
            if settings.admin_enabled and not public_readonly
            else ""
        )
        gpt_actions_links = (
            ""
            if public_readonly
            else (
                '<a class="pill" href="/gpt-actions-openapi-v3.json">GPT Actions OpenAPI v3</a>'
                '<a class="pill" href="/gpt-actions-openapi-v2.json">GPT Actions OpenAPI v2</a>'
                '<a class="pill" href="/gpt-actions-openapi.json">GPT Actions OpenAPI v1</a>'
            )
        )
        return HTMLResponse(
            render_landing_page(
                public_http_url=public_http_url,
                mcp_url=mcp_url,
                public_readonly=public_readonly,
                oauth_enabled=oauth_enabled,
                admin_link_html=admin_link,
                gpt_actions_links_html=gpt_actions_links,
            )
        )

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy(request: Request) -> HTMLResponse:
        public_http_url = settings.public_http_url or str(request.base_url).rstrip("/")
        return HTMLResponse(render_privacy_page(public_http_url=public_http_url))

    @app.get("/readyz")
    def ready() -> dict[str, object]:
        return get_readiness_snapshot()

    @app.get("/gpt-actions-openapi.json")
    def gpt_actions_openapi(request: Request) -> JSONResponse:
        return JSONResponse(build_gpt_actions_openapi(app, request, settings=settings))

    @app.get("/gpt-actions-openapi-v2.json")
    def gpt_actions_openapi_v2(request: Request) -> JSONResponse:
        return JSONResponse(build_gpt_actions_openapi_v2(app, request, settings=settings))

    @app.get("/gpt-actions-openapi-v3.json")
    def gpt_actions_openapi_v3(request: Request) -> JSONResponse:
        return JSONResponse(build_gpt_actions_openapi_v3(app, request, settings=settings))

    @app.get("/periods", response_model=list[Period])
    def periods() -> list[Period]:
        return get_class_periods()

    @app.get("/academic-calendar", response_model=list[AcademicCalendarEvent])
    def academic_calendar(
        academic_year: int | None = Query(default=None),
        month: int | None = Query(default=None, ge=1, le=12),
        query: str | None = Query(default=None, description="학사일정 제목 부분 검색어"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[AcademicCalendarEvent]:
        with connection() as conn:
            try:
                return list_academic_calendar(
                    conn,
                    academic_year=academic_year,
                    month=month,
                    query=query,
                    limit=limit,
                )
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/certificate-guides", response_model=list[CertificateGuide])
    def certificate_guides(
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[CertificateGuide]:
        with connection() as conn:
            return list_certificate_guides(conn, limit=limit)

    @app.get("/academic-support-guides", response_model=list[AcademicSupportGuide])
    def academic_support_guides(
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[AcademicSupportGuide]:
        with connection() as conn:
            return list_academic_support_guides(conn, limit=limit)

    @app.get("/academic-status-guides", response_model=list[AcademicStatusGuide])
    def academic_status_guides(
        status: str | None = Query(default=None, description="학적변동 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[AcademicStatusGuide]:
        with connection() as conn:
            try:
                return list_academic_status_guides(conn, status=status, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/registration-guides", response_model=list[RegistrationGuide])
    def registration_guides(
        topic: str | None = Query(default=None, description="등록 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[RegistrationGuide]:
        with connection() as conn:
            try:
                return list_registration_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/class-guides", response_model=list[ClassGuide])
    def class_guides(
        topic: str | None = Query(default=None, description="수업 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[ClassGuide]:
        with connection() as conn:
            try:
                return list_class_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/seasonal-semester-guides", response_model=list[SeasonalSemesterGuide])
    def seasonal_semester_guides(
        topic: str | None = Query(default=None, description="계절학기 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[SeasonalSemesterGuide]:
        with connection() as conn:
            try:
                return list_seasonal_semester_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/academic-milestone-guides", response_model=list[AcademicMilestoneGuide])
    def academic_milestone_guides(
        topic: str | None = Query(default=None, description="성적·졸업 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[AcademicMilestoneGuide]:
        with connection() as conn:
            try:
                return list_academic_milestone_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/student-exchange-guides", response_model=list[StudentExchangeGuide])
    def student_exchange_guides(
        topic: str | None = Query(default=None, description="학생교류 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[StudentExchangeGuide]:
        with connection() as conn:
            try:
                return list_student_exchange_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/student-activity-guides", response_model=list[StudentActivityGuide])
    def student_activity_guides(
        topic: str | None = Query(default=None, description="학생활동 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[StudentActivityGuide]:
        with connection() as conn:
            try:
                return list_student_activity_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/about-resource-guides", response_model=list[AboutResourceGuide])
    def about_resource_guides(
        topic: str | None = Query(default=None, description="가대소개 정적 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[AboutResourceGuide]:
        with connection() as conn:
            try:
                return list_about_resource_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/service-policy-guides", response_model=list[ServicePolicyGuide])
    def service_policy_guides(
        topic: str | None = Query(default=None, description="서비스/정책 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[ServicePolicyGuide]:
        with connection() as conn:
            try:
                return list_service_policy_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/newsroom-posts", response_model=list[NewsroomPost])
    def newsroom_posts(
        topic: str | None = Query(default=None, description="뉴스룸 유형 필터"),
        query: str | None = Query(default=None, description="제목/요약 검색어"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[NewsroomPost]:
        with connection() as conn:
            try:
                return list_newsroom_posts(conn, topic=topic, query=query, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/student-exchange-partners", response_model=list[StudentExchangePartner])
    def student_exchange_partners(
        query: str | None = Query(
            default=None,
            description="국가, 대륙, 대학명 검색어. 예: 네덜란드, Utrecht, EUROPE, 대만",
        ),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[StudentExchangePartner]:
        with connection() as conn:
            return search_student_exchange_partners(conn, query=query, limit=limit)

    @app.get("/phone-book", response_model=list[PhoneBookEntry])
    def phone_book(
        query: str | None = Query(default=None, description="부서명, 업무, 내선번호 검색어"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[PhoneBookEntry]:
        with connection() as conn:
            return search_phone_book_entries(conn, query=query, limit=limit)

    @app.get("/campus-life-support-guides", response_model=list[CampusLifeSupportGuide])
    def campus_life_support_guides(
        topic: str | None = Query(default=None, description="생활지원 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[CampusLifeSupportGuide]:
        with connection() as conn:
            try:
                return list_campus_life_support_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/pc-software", response_model=list[PCSoftwareEntry])
    def pc_software(
        query: str | None = Query(
            default=None,
            description=(
                "소프트웨어 또는 실습실 검색어. "
                "예: SPSS, Photoshop, Visual Studio, 마리아관"
            ),
        ),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[PCSoftwareEntry]:
        with connection() as conn:
            return search_pc_software_entries(conn, query=query, limit=limit)

    @app.get("/dormitory-guides", response_model=list[DormitoryGuide])
    def dormitory_guides(
        topic: str | None = Query(default=None, description="기숙사 안내 유형 필터"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[DormitoryGuide]:
        with connection() as conn:
            try:
                return list_dormitory_guides(conn, topic=topic, limit=limit)
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/leave-of-absence-guides", response_model=list[LeaveOfAbsenceGuide])
    def leave_of_absence_guides(
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[LeaveOfAbsenceGuide]:
        with connection() as conn:
            return list_leave_of_absence_guides(conn, limit=limit)

    @app.get("/scholarship-guides", response_model=list[ScholarshipGuide])
    def scholarship_guides(
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[ScholarshipGuide]:
        with connection() as conn:
            return list_scholarship_guides(conn, limit=limit)

    @app.get("/wifi-guides", response_model=list[WifiGuide])
    def wifi_guides(
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[WifiGuide]:
        with connection() as conn:
            return list_wifi_guides(conn, limit=limit)

    @app.get("/library-seats", response_model=LibrarySeatStatusResponse)
    def library_seats(
        query: str | None = Query(default=None, description="열람실 또는 좌석 관련 검색어"),
    ) -> LibrarySeatStatusResponse:
        with connection() as conn:
            return get_library_seat_status(conn, query=query)

    @app.get("/notice-categories", response_model=list[NoticeCategoryInfo])
    def notice_categories() -> list[NoticeCategoryInfo]:
        return get_notice_categories()

    @app.get("/gpt/notice-categories", response_model=list[GptNoticeCategoryInfo])
    def gpt_notice_categories() -> list[GptNoticeCategoryInfo]:
        return [_serialize_gpt_notice_category(item) for item in get_notice_categories()]

    @app.get("/gpt/periods", response_model=list[Period])
    def gpt_periods() -> list[Period]:
        return get_class_periods()

    @app.get("/gpt/library-seats", response_model=GptLibrarySeatStatusResponse)
    def gpt_library_seats(
        query: str | None = Query(default=None, description="열람실 또는 좌석 관련 검색어"),
    ) -> GptLibrarySeatStatusResponse:
        with connection() as conn:
            response = get_library_seat_status(conn, query=query)
        return GptLibrarySeatStatusResponse.model_validate(
            _serialize_gpt_library_seat_status(response)
        )

    @app.get("/gpt/dining-menus", response_model=list[GptCampusDiningMenuResult])
    def gpt_dining_menus(
        query: str | None = Query(default=None, description="교내 식당 메뉴 검색어"),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[GptCampusDiningMenuResult]:
        with connection() as conn:
            menus = search_campus_dining_menus(conn, query=query, limit=limit)
        return [
            GptCampusDiningMenuResult.model_validate(_serialize_gpt_dining_menu(menu))
            for menu in menus
        ]

    @app.get("/gpt/places", response_model=list[GptPlaceResult])
    def gpt_places(
        query: str = Query(default="", description="건물/시설/도서관 검색어"),
        category: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[GptPlaceResult]:
        with connection() as conn:
            places = search_places(conn, query=query, category=category, limit=limit)
        return [GptPlaceResult.model_validate(_serialize_gpt_place(place)) for place in places]

    @app.get("/gpt/notices", response_model=list[GptNoticeResult])
    def gpt_notices(
        category: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[GptNoticeResult]:
        with connection() as conn:
            notices = list_latest_notices(conn, category=category, limit=limit)
        return [GptNoticeResult.model_validate(_serialize_gpt_notice(notice)) for notice in notices]

    @app.get("/gpt/restaurants/nearby", response_model=list[GptNearbyRestaurantResult])
    def gpt_restaurants_nearby(
        origin: str = Query(description="출발 건물 slug 또는 이름"),
        at: datetime | None = Query(default=None),
        category: str | None = Query(default=None),
        budget_max: int | None = Query(
            default=None,
            ge=0,
            description="최대 예산(원). 가격 정보가 확인된 후보만 남깁니다.",
        ),
        open_now: bool = Query(default=False),
        walk_minutes: int = Query(default=15, ge=1, le=60),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[GptNearbyRestaurantResult]:
        with connection() as conn:
            try:
                restaurants = find_nearby_restaurants(
                    conn,
                    origin=origin,
                    at=at,
                    category=category,
                    budget_max=budget_max,
                    open_now=open_now,
                    walk_minutes=walk_minutes,
                    limit=limit,
                )
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return [
            GptNearbyRestaurantResult.model_validate(
                _serialize_gpt_nearby_restaurant(restaurant)
            )
            for restaurant in restaurants
        ]

    @app.get("/gpt/restaurants/search", response_model=list[GptRestaurantSearchResult])
    def gpt_restaurants_search(
        query: str = Query(default="", description="브랜드 또는 상호 직접 검색어"),
        origin: str | None = Query(
            default=None,
            description="거리 정렬 보조용 캠퍼스 출발지 slug, 대표 이름, 또는 alias",
        ),
        category: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[GptRestaurantSearchResult]:
        with connection() as conn:
            try:
                restaurants = search_restaurants(
                    conn,
                    query=query,
                    origin=origin,
                    category=category,
                    limit=limit,
                )
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return [
            GptRestaurantSearchResult.model_validate(
                _serialize_gpt_restaurant_search(restaurant)
            )
            for restaurant in restaurants
        ]

    @app.get("/gpt/classrooms/empty", response_model=EstimatedEmptyClassroomResponse)
    def gpt_empty_classrooms(
        building: str = Query(description="강의실을 확인할 건물 slug, 대표 이름, 또는 alias"),
        at: datetime | None = Query(default=None),
        year: int | None = Query(default=None),
        semester: int | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> EstimatedEmptyClassroomResponse:
        with connection() as conn:
            try:
                return list_estimated_empty_classrooms(
                    conn,
                    building=building,
                    at=at,
                    year=year,
                    semester=semester,
                    limit=limit,
                )
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/places", response_model=list[Place])
    def places(
        query: str = Query(default="", description="건물/시설/도서관 검색어"),
        category: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[Place]:
        with connection() as conn:
            return search_places(conn, query=query, category=category, limit=limit)

    @app.get("/places/{identifier}", response_model=Place)
    def place_detail(identifier: str) -> Place:
        with connection() as conn:
            try:
                return get_place(conn, identifier)
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/courses", response_model=list[Course])
    def courses(
        query: str = Query(default=""),
        year: int | None = Query(default=None),
        semester: int | None = Query(default=None),
        period_start: int | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[Course]:
        with connection() as conn:
            return search_courses(
                conn,
                query=query,
                year=year,
                semester=semester,
                period_start=period_start,
                limit=limit,
            )

    @app.get("/dining-menus", response_model=list[CampusDiningMenu])
    def dining_menus(
        query: str | None = Query(default=None, description="교내 식당 메뉴 검색어"),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[CampusDiningMenu]:
        with connection() as conn:
            return search_campus_dining_menus(conn, query=query, limit=limit)

    @app.get("/restaurants", response_model=list[Restaurant])
    def restaurants() -> list[Restaurant]:
        with connection() as conn:
            return list_restaurants(conn)

    @app.get("/restaurants/nearby", response_model=list[NearbyRestaurant])
    def restaurants_nearby(
        origin: str = Query(description="출발 건물 slug 또는 이름"),
        at: datetime | None = Query(default=None),
        category: str | None = Query(default=None),
        budget_max: int | None = Query(
            default=None,
            ge=0,
            description="최대 예산(원). 가격 정보가 확인된 후보만 남깁니다.",
        ),
        open_now: bool = Query(default=False),
        walk_minutes: int = Query(default=15, ge=1, le=60),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[NearbyRestaurant]:
        with connection() as conn:
            try:
                return find_nearby_restaurants(
                    conn,
                    origin=origin,
                    at=at,
                    category=category,
                    budget_max=budget_max,
                    open_now=open_now,
                    walk_minutes=walk_minutes,
                    limit=limit,
                )
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/restaurants/search", response_model=list[RestaurantSearchResult])
    def restaurants_search(
        query: str = Query(default="", description="브랜드 또는 상호 직접 검색어"),
        origin: str | None = Query(
            default=None,
            description="거리 정렬 보조용 캠퍼스 출발지 slug, 대표 이름, 또는 alias",
        ),
        category: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[RestaurantSearchResult]:
        with connection() as conn:
            try:
                return search_restaurants(
                    conn,
                    query=query,
                    origin=origin,
                    category=category,
                    limit=limit,
                )
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/classrooms/empty", response_model=EstimatedEmptyClassroomResponse)
    def classrooms_empty(
        building: str = Query(description="강의실을 확인할 건물 slug, 대표 이름, 또는 alias"),
        at: datetime | None = Query(default=None),
        year: int | None = Query(default=None),
        semester: int | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> EstimatedEmptyClassroomResponse:
        with connection() as conn:
            try:
                return list_estimated_empty_classrooms(
                    conn,
                    building=building,
                    at=at,
                    year=year,
                    semester=semester,
                    limit=limit,
                )
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/notices", response_model=list[Notice])
    def notices(
        category: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[Notice]:
        with connection() as conn:
            return list_latest_notices(conn, category=category, limit=limit)

    @app.get("/affiliated-notices", response_model=list[AffiliatedNotice])
    def affiliated_notices(
        topic: str | None = Query(default=None, description="공지 번들 유형 필터"),
        query: str | None = Query(default=None, description="공지 제목, 요약 또는 본문 검색어"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[dict[str, object]]:
        from . import services as _services

        with connection() as conn:
            return _services.list_affiliated_notices(conn, topic=topic, query=query, limit=limit)

    @app.get("/campus-life-notices", response_model=list[CampusLifeNotice])
    def campus_life_notices(
        topic: str | None = Query(default=None, description="공지 번들 유형 필터"),
        query: str | None = Query(default=None, description="공지 제목 또는 요약 검색어"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[CampusLifeNotice]:
        with connection() as conn:
            return list_campus_life_notices(conn, topic=topic, query=query, limit=limit)

    @app.get("/transport", response_model=list[TransportGuide])
    def transport(
        mode: str | None = Query(default=None),
        query: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[TransportGuide]:
        with connection() as conn:
            return list_transport_guides(conn, mode=mode, query=query, limit=limit)

    if not public_readonly:
        @app.post("/profiles", response_model=Profile)
        def create_profile_endpoint(payload: ProfileCreateRequest | None = None) -> Profile:
            with connection() as conn:
                return create_profile(
                    conn,
                    display_name=(payload.display_name if payload else ""),
                )

        @app.patch("/profiles/{profile_id}", response_model=Profile)
        def update_profile_endpoint(
            profile_id: str,
            payload: ProfileUpdateRequest,
        ) -> Profile:
            with connection() as conn:
                try:
                    return update_profile(conn, profile_id, payload)
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except InvalidRequestError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        @app.put("/profiles/{profile_id}/timetable", response_model=list[Course])
        def set_profile_timetable_endpoint(
            profile_id: str,
            courses: list[ProfileCourseRef],
        ) -> list[Course]:
            with connection() as conn:
                try:
                    return set_profile_timetable(conn, profile_id, courses)
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except InvalidRequestError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        @app.get("/profiles/{profile_id}/timetable", response_model=list[Course])
        def get_profile_timetable_endpoint(
            profile_id: str,
            year: int | None = Query(default=None),
            semester: int | None = Query(default=None),
        ) -> list[Course]:
            with connection() as conn:
                try:
                    return get_profile_timetable(conn, profile_id, year=year, semester=semester)
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.put(
            "/profiles/{profile_id}/notice-preferences",
            response_model=ProfileNoticePreferences,
        )
        def set_profile_notice_preferences_endpoint(
            profile_id: str,
            preferences: ProfileNoticePreferences,
        ) -> ProfileNoticePreferences:
            with connection() as conn:
                try:
                    return set_profile_notice_preferences(conn, profile_id, preferences)
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except InvalidRequestError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        @app.put("/profiles/{profile_id}/interests", response_model=ProfileInterests)
        def set_profile_interests_endpoint(
            profile_id: str,
            interests: ProfileInterests,
        ) -> ProfileInterests:
            with connection() as conn:
                try:
                    return set_profile_interests(conn, profile_id, interests)
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except InvalidRequestError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        @app.get("/profiles/{profile_id}/interests", response_model=ProfileInterests)
        def get_profile_interests_endpoint(profile_id: str) -> ProfileInterests:
            with connection() as conn:
                try:
                    return get_profile_interests(conn, profile_id)
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.get("/profiles/{profile_id}/notices", response_model=list[MatchedNotice])
        def get_profile_notices_endpoint(
            profile_id: str,
            limit: int = Query(default=10, ge=1, le=50),
        ) -> list[MatchedNotice]:
            with connection() as conn:
                try:
                    return list_profile_notices(conn, profile_id, limit=limit)
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except InvalidRequestError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        @app.get(
            "/profiles/{profile_id}/courses/recommended",
            response_model=list[MatchedCourse],
        )
        def get_profile_course_recommendations_endpoint(
            profile_id: str,
            year: int | None = Query(default=None),
            semester: int | None = Query(default=None),
            query: str = Query(default=""),
            limit: int = Query(default=10, ge=1, le=50),
        ) -> list[MatchedCourse]:
            with connection() as conn:
                try:
                    return get_profile_course_recommendations(
                        conn,
                        profile_id,
                        year=year,
                        semester=semester,
                        query=query,
                        limit=limit,
                    )
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except InvalidRequestError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        @app.get(
            "/profiles/{profile_id}/meal-recommendations",
            response_model=MealRecommendationResponse,
        )
        def get_profile_meal_recommendations_endpoint(
            profile_id: str,
            origin: str = Query(description="출발 건물 slug 또는 이름"),
            at: datetime | None = Query(default=None),
            year: int | None = Query(default=None),
            semester: int | None = Query(default=None),
            budget_max: int | None = Query(default=None, ge=0),
            category: str | None = Query(default=None),
            open_now: bool = Query(default=False),
            limit: int = Query(default=10, ge=1, le=50),
        ) -> MealRecommendationResponse:
            with connection() as conn:
                try:
                    return get_profile_meal_recommendations(
                        conn,
                        profile_id,
                        origin=origin,
                        at=at,
                        year=year,
                        semester=semester,
                        budget_max=budget_max,
                        category=category,
                        limit=limit,
                        open_now=open_now,
                    )
                except NotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except InvalidRequestError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings.admin_enabled and not public_readonly:
        @app.get("/admin/sync", response_class=HTMLResponse)
        def admin_sync_dashboard(request: Request) -> HTMLResponse:
            ensure_admin_request_allowed(request)
            with connection() as conn:
                state = get_sync_dashboard_state(conn)
            return HTMLResponse(
                render_admin_sync_page(
                    state=state,
                    official_campus_id=settings.official_campus_id,
                    official_course_year=settings.official_course_year,
                    official_course_semester=settings.official_course_semester,
                    official_notice_pages=settings.official_notice_pages,
                )
            )

        @app.post("/admin/sync/run")
        async def admin_sync_run(request: Request) -> RedirectResponse:
            ensure_admin_request_allowed(request)
            form_values = {
                key: values[-1] if values else ""
                for key, values in parse_qs(
                    (await request.body()).decode("utf-8"),
                    keep_blank_values=True,
                ).items()
            }

            def parse_optional_int(name: str) -> int | None:
                raw_value = form_values.get(name, "").strip()
                if not raw_value:
                    return None
                try:
                    return int(raw_value)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid integer for {name}: {raw_value}",
                    ) from exc

            target = form_values.get("target", "").strip()
            try:
                run_admin_sync(
                    target=target or "snapshot",
                    campus=form_values.get("campus", "").strip() or None,
                    year=parse_optional_int("year"),
                    semester=parse_optional_int("semester"),
                    notice_pages=parse_optional_int("notice_pages"),
                )
            except InvalidRequestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return RedirectResponse("/admin/sync", status_code=303)

        @app.get("/admin/observability", response_class=HTMLResponse)
        def admin_observability_dashboard(request: Request) -> HTMLResponse:
            ensure_admin_request_allowed(request)
            readiness = get_readiness_snapshot()
            with connection() as conn:
                observability = get_observability_snapshot(conn).model_dump()
            return HTMLResponse(
                render_admin_observability_page(
                    state={"readiness": readiness, "observability": observability}
                )
            )

        @app.get("/admin/observability.json")
        def admin_observability_json(request: Request) -> dict[str, object]:
            ensure_admin_request_allowed(request)
            readiness = get_readiness_snapshot()
            with connection() as conn:
                observability = get_observability_snapshot(conn).model_dump()
            return {
                "health": {"ok": True},
                "readiness": readiness,
                **observability,
            }

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "songsim_campus.api:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
