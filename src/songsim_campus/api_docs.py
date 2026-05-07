from __future__ import annotations

import copy
from typing import Any

from fastapi import FastAPI, Request

GPT_ACTION_PATHS: dict[str, dict[str, str]] = {
    "/places": {
        "operationId": "searchPlaces",
        "summary": "Search campus places",
        "description": (
            "Search Songsim campus places by building name, alias, or facility keyword. "
            "Use this for locations such as 중앙도서관, 베리타스관, or student facilities."
        ),
    },
    "/courses": {
        "operationId": "searchCourses",
        "summary": "Search public course offerings",
        "description": (
            "Search public Songsim course offerings by title and optional year, "
            "semester, or exact period_start."
        ),
    },
    "/academic-calendar": {
        "operationId": "listAcademicCalendar",
        "summary": "List academic calendar events",
        "description": (
            "List public academic calendar events by academic year with optional "
            "month overlap and title substring filters."
        ),
    },
    "/notices": {
        "operationId": "listLatestNotices",
        "summary": "List latest public notices",
        "description": "List the latest public Songsim campus notices.",
    },
    "/affiliated-notices": {
        "operationId": "listAffiliatedNotices",
        "summary": "List affiliated department and dormitory notices",
        "description": (
            "List current affiliated department and dormitory notice bundles such as "
            "국제학부 학과공지 and dormitory board notices."
        ),
    },
    "/certificate-guides": {
        "operationId": "listCertificateGuides",
        "summary": "List certificate issuance guides",
        "description": "List the current Songsim certificate issuance guides and notices.",
    },
    "/leave-of-absence-guides": {
        "operationId": "listLeaveOfAbsenceGuides",
        "summary": "List leave-of-absence guides",
        "description": (
            "List the current Songsim leave-of-absence guidance, submission cases, "
            "and official FAQ or forms links."
        ),
    },
    "/scholarship-guides": {
        "operationId": "listScholarshipGuides",
        "summary": "List scholarship baseline guides",
        "description": (
            "List the current Songsim scholarship baseline guides and official scholarship "
            "document links."
        ),
    },
    "/wifi-guides": {
        "operationId": "listWifiGuides",
        "summary": "List campus wifi guides",
        "description": (
            "List the current Songsim campus wifi SSIDs and building-level connection "
            "guidance."
        ),
    },
    "/notice-categories": {
        "operationId": "listNoticeCategories",
        "summary": "List public notice categories",
        "description": (
            "List the canonical public notice categories and compatibility aliases such "
            "as career -> employment."
        ),
    },
    "/periods": {
        "operationId": "listClassPeriods",
        "summary": "List class periods",
        "description": "List the fixed Songsim class period table.",
    },
    "/library-seats": {
        "operationId": "getLibrarySeatStatus",
        "summary": "Get central-library reading-room seat status",
        "description": (
            "Best-effort realtime central-library reading-room seat status with fresh cache "
            "and stale fallback."
        ),
    },
    "/dining-menus": {
        "operationId": "listDiningMenus",
        "summary": "List current official campus dining menus",
        "description": (
            "List the current official campus dining menus for Buon Pranzo, Café Bona, "
            "and Café Mensa with extracted weekly text and the original PDF link."
        ),
    },
    "/restaurants/nearby": {
        "operationId": "findNearbyRestaurants",
        "summary": "Find nearby restaurants",
        "description": ("Find walkable restaurants near a Songsim campus building or landmark."),
    },
    "/restaurants/search": {
        "operationId": "searchRestaurants",
        "summary": "Search restaurant brands or venue names",
        "description": (
            "Search nearby restaurant or cafe brands directly by venue name. "
            "Use this for questions like 매머드커피 어디 있어 or 이디야 있나."
        ),
    },
    "/transport": {
        "operationId": "listTransportGuides",
        "summary": "List transit guides",
        "description": "List public Songsim campus transit and access guides.",
    },
}

GPT_ACTION_V2_PATHS: dict[str, dict[str, str]] = {
    "/gpt/places": {
        "operationId": "searchPlacesForGpt",
        "summary": "Find campus places with concise summaries",
        "description": (
            "Use when the user asks where a Songsim campus building, landmark, or facility is. "
            "Returns concise names, aliases, short location hints, and coordinates "
            "that are easy to summarize."
        ),
    },
    "/gpt/notices": {
        "operationId": "listLatestNoticesForGpt",
        "summary": "List latest public notices with short previews",
        "description": (
            "Use when the user wants the latest Songsim public notices. "
            "Returns normalized notice categories and short summary previews."
        ),
    },
    "/gpt/notice-categories": {
        "operationId": "listNoticeCategoriesForGpt",
        "summary": "List public notice categories with concise labels",
        "description": (
            "Use when the user asks which public notice categories exist or what "
            "employment vs career means."
        ),
    },
    "/gpt/periods": {
        "operationId": "listPeriodsForGpt",
        "summary": "List class periods with concise timing rows",
        "description": (
            "Use when the user asks what a period number means or needs the class "
            "period table before searching courses."
        ),
    },
    "/gpt/library-seats": {
        "operationId": "getLibrarySeatStatusForGpt",
        "summary": "Get concise central-library reading-room seat status",
        "description": (
            "Use when the user asks whether central-library reading rooms have seats "
            "available. Returns live, stale_cache, or unavailable status."
        ),
    },
    "/gpt/dining-menus": {
        "operationId": "listDiningMenusForGpt",
        "summary": "List official campus dining menus with concise previews",
        "description": (
            "Use when the user asks for this week’s official Songsim campus dining menu. "
            "Returns concise venue names, weekly labels, menu previews, and source links."
        ),
    },
    "/gpt/restaurants/nearby": {
        "operationId": "findNearbyRestaurantsForGpt",
        "summary": "Find nearby restaurants with concise hints",
        "description": (
            "Use when the user asks for nearby food around a Songsim campus location. "
            "Returns concise distance, walk time, price, and location hints."
        ),
    },
    "/gpt/restaurants/search": {
        "operationId": "searchRestaurantsForGpt",
        "summary": "Search restaurant brands with concise hints",
        "description": (
            "Use when the user asks whether a specific brand or venue exists nearby. "
            "Returns concise distance, walk time, price, and location hints."
        ),
    },
    "/gpt/classrooms/empty": {
        "operationId": "listEstimatedEmptyClassroomsForGpt",
        "summary": "Find current empty classrooms in a building",
        "description": (
            "Use when the user asks which classrooms are empty right now in a Songsim "
            "lecture building. Returns official realtime classroom availability when an "
            "official source is available, otherwise falls back to timetable-based estimates."
        ),
    },
}

GPT_ACTION_V3_PATHS: dict[str, dict[str, str]] = {
    "/gpt/places": GPT_ACTION_V2_PATHS["/gpt/places"],
    "/gpt/notices": GPT_ACTION_V2_PATHS["/gpt/notices"],
    "/gpt/periods": GPT_ACTION_V2_PATHS["/gpt/periods"],
    "/gpt/library-seats": GPT_ACTION_V2_PATHS["/gpt/library-seats"],
    "/gpt/dining-menus": GPT_ACTION_V2_PATHS["/gpt/dining-menus"],
    "/gpt/restaurants/nearby": GPT_ACTION_V2_PATHS["/gpt/restaurants/nearby"],
    "/gpt/restaurants/search": GPT_ACTION_V2_PATHS["/gpt/restaurants/search"],
    "/gpt/classrooms/empty": GPT_ACTION_V2_PATHS["/gpt/classrooms/empty"],
    "/academic-calendar": GPT_ACTION_PATHS["/academic-calendar"],
    "/affiliated-notices": GPT_ACTION_PATHS["/affiliated-notices"],
    "/campus-life-notices": {
        "operationId": "listCampusLifeNotices",
        "summary": "List campus life notice bundles",
        "description": (
            "List current campus life notice bundles such as 행사안내 and 외부기관공지."
        ),
    },
    "/phone-book": {
        "operationId": "searchPhoneBookEntries",
        "summary": "Search phone book entries",
        "description": (
            "Search the current Songsim campus phone book by office, department, or "
            "contact keyword."
        ),
    },
    "/certificate-guides": GPT_ACTION_PATHS["/certificate-guides"],
    "/leave-of-absence-guides": GPT_ACTION_PATHS["/leave-of-absence-guides"],
    "/scholarship-guides": GPT_ACTION_PATHS["/scholarship-guides"],
    "/wifi-guides": GPT_ACTION_PATHS["/wifi-guides"],
    "/transport": GPT_ACTION_PATHS["/transport"],
    "/courses": GPT_ACTION_PATHS["/courses"],
    "/academic-status-guides": {
        "operationId": "listAcademicStatusGuides",
        "summary": "List academic status guides",
        "description": (
            "List current academic status guidance for leave, dropout, and re-admission."
        ),
    },
    "/registration-guides": {
        "operationId": "listRegistrationGuides",
        "summary": "List registration guides",
        "description": (
            "List the current Songsim registration guidance and official notice links."
        ),
    },
    "/class-guides": {
        "operationId": "listClassGuides",
        "summary": "List class guides",
        "description": (
            "List the current Songsim class guidance such as excused absence and "
            "course cancellation."
        ),
    },
    "/seasonal-semester-guides": {
        "operationId": "listSeasonalSemesterGuides",
        "summary": "List seasonal semester guides",
        "description": (
            "List the current Songsim seasonal semester guidance and eligibility notes."
        ),
    },
    "/academic-milestone-guides": {
        "operationId": "listAcademicMilestoneGuides",
        "summary": "List academic milestone guides",
        "description": (
            "List the current Songsim academic milestone guidance for grades and graduation."
        ),
    },
    "/academic-support-guides": {
        "operationId": "listAcademicSupportGuides",
        "summary": "List academic support guides",
        "description": (
            "List the current Songsim academic support guidance and office contact links."
        ),
    },
    "/campus-life-support-guides": {
        "operationId": "listCampusLifeSupportGuides",
        "summary": "List campus life support guides",
        "description": (
            "List the current Songsim campus life support guidance for counseling, "
            "career counseling, disability support, reservist, and hospital use."
        ),
    },
    "/dormitory-guides": {
        "operationId": "listDormitoryGuides",
        "summary": "List dormitory guides",
        "description": (
            "List the current Songsim dormitory guidance, fees, and notice bundles."
        ),
    },
    "/pc-software": {
        "operationId": "searchPcSoftwareEntries",
        "summary": "Search PC software entries",
        "description": (
            "Search the current Songsim PC software and lab availability entries."
        ),
    },
    "/student-exchange-guides": {
        "operationId": "listStudentExchangeGuides",
        "summary": "List student exchange guides",
        "description": (
            "List the current Songsim student exchange guidance and official links."
        ),
    },
    "/student-exchange-partners": {
        "operationId": "searchStudentExchangePartners",
        "summary": "Search student exchange partners",
        "description": (
            "Search current student exchange partner universities by country, "
            "region, or university name."
        ),
    },
    "/student-activity-guides": {
        "operationId": "listStudentActivityGuides",
        "summary": "List student activity guides",
        "description": (
            "List the current Songsim student activity guidance for government, "
            "central clubs, institutional clubs, media, volunteering, and ROTC."
        ),
    },
    "/student-activity-notices": {
        "operationId": "listStudentActivityNotices",
        "summary": "List student activity notices",
        "description": (
            "List current official notice-board posts related to student activity, "
            "club recruitment, student government, volunteering, ROTC, and campus events."
        ),
    },
    "/about-resource-guides": {
        "operationId": "listAboutResourceGuides",
        "summary": "List about resource guides",
        "description": (
            "List the current Songsim official about-resource guide links for rules, "
            "the university bulletin, the academic handbook, and campus tours."
        ),
    },
}


def build_filtered_openapi(
    app: FastAPI,
    request: Request,
    settings: Any,
    *,
    title: str,
    description: str,
    path_metadata: dict[str, dict[str, str]],
) -> dict[str, object]:
    source_spec = copy.deepcopy(app.openapi())
    public_http_url = settings.public_http_url or str(request.base_url).rstrip("/")
    filtered_paths: dict[str, object] = {}
    for path, metadata in path_metadata.items():
        operation = copy.deepcopy(source_spec["paths"][path]["get"])
        operation["operationId"] = metadata["operationId"]
        operation["summary"] = metadata["summary"]
        operation["description"] = metadata["description"]
        filtered_paths[path] = {"get": operation}
    return {
        "openapi": source_spec["openapi"],
        "info": {
            "title": title,
            "version": source_spec["info"]["version"],
            "description": description,
        },
        "servers": [{"url": public_http_url}],
        "paths": filtered_paths,
        "components": source_spec.get("components", {}),
    }


def build_gpt_actions_openapi(app: FastAPI, request: Request, settings: Any) -> dict[str, object]:
    return build_filtered_openapi(
        app,
        request,
        settings,
        title="Songsim Campus GPT Actions",
        description="Slimmed-down read-only actions schema for ChatGPT GPT Actions.",
        path_metadata=GPT_ACTION_PATHS,
    )


def build_gpt_actions_openapi_v2(
    app: FastAPI,
    request: Request,
    settings: Any,
) -> dict[str, object]:
    return build_filtered_openapi(
        app,
        request,
        settings,
        title="Songsim Campus GPT Actions v2",
        description=(
            "GPT-focused actions schema with concise place, notice, and nearby "
            "restaurant responses."
        ),
        path_metadata=GPT_ACTION_V2_PATHS,
    )


def build_gpt_actions_openapi_v3(
    app: FastAPI,
    request: Request,
    settings: Any,
) -> dict[str, object]:
    return build_filtered_openapi(
        app,
        request,
        settings,
        title="Songsim Campus GPT Actions v3",
        description=(
            "Hybrid actions schema combining concise GPT wrappers with broader public "
            "student-facing endpoints."
        ),
        path_metadata=GPT_ACTION_V3_PATHS,
    )
