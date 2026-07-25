from __future__ import annotations

from fastapi.testclient import TestClient

from songsim_campus.api import create_app
from songsim_campus.settings import clear_settings_cache


def test_public_readonly_mode_exposes_gpt_actions_openapi_v3_hybrid_schema(monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-api.onrender.com")
    monkeypatch.setenv("SONGSIM_SYNC_OFFICIAL_ON_START", "false")
    monkeypatch.setenv("SONGSIM_SEED_DEMO_ON_START", "false")
    monkeypatch.setenv("SONGSIM_ADMIN_ENABLED", "false")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_ENABLED", "false")
    monkeypatch.setattr("songsim_campus.api.init_db", lambda: None)
    clear_settings_cache()

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get("/gpt-actions-openapi-v3.json")

    clear_settings_cache()

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "Songsim Campus GPT Actions v3"
    assert payload["servers"] == [{"url": "https://songsim-api.onrender.com"}]
    assert set(payload["paths"]) == {
        "/academic-calendar",
        "/academic-milestone-guides",
        "/academic-status-guides",
        "/academic-support-guides",
        "/about-resource-guides",
        "/affiliated-notices",
        "/campus-life-notices",
        "/campus-life-support-guides",
        "/certificate-guides",
        "/class-guides",
        "/courses",
        "/dormitory-guides",
        "/gpt/notice-categories",
        "/gpt/classrooms/empty",
        "/gpt/dining-menus",
        "/gpt/library-seats",
        "/gpt/notices",
        "/gpt/periods",
        "/gpt/places",
        "/gpt/restaurants/nearby",
        "/gpt/restaurants/search",
        "/leave-of-absence-guides",
        "/anniversary-guides",
        "/newsroom-posts",
        "/newsroom-resource-guides",
        "/pc-software",
        "/phone-book",
        "/registration-guides",
        "/research-posts",
        "/service-policy-guides",
        "/service-policy-posts",
        "/scholarship-guides",
        "/seasonal-semester-guides",
        "/student-activity-guides",
        "/student-activity-notices",
        "/student-exchange-guides",
        "/student-exchange-partners",
        "/transport",
        "/wifi-guides",
    }
    assert payload["paths"]["/wifi-guides"]["get"]["operationId"] == "listWifiGuides"
    assert (
        payload["paths"]["/phone-book"]["get"]["operationId"]
        == "searchPhoneBookEntries"
    )
    assert (
        payload["paths"]["/registration-guides"]["get"]["operationId"]
        == "listRegistrationGuides"
    )
    assert (
        payload["paths"]["/campus-life-notices"]["get"]["operationId"]
        == "listCampusLifeNotices"
    )
    assert (
        payload["paths"]["/student-exchange-guides"]["get"]["operationId"]
        == "listStudentExchangeGuides"
    )
    assert (
        payload["paths"]["/student-activity-guides"]["get"]["operationId"]
        == "listStudentActivityGuides"
    )
    assert (
        payload["paths"]["/student-activity-notices"]["get"]["operationId"]
        == "listStudentActivityNotices"
    )
    assert payload["paths"]["/newsroom-posts"]["get"]["operationId"] == "listNewsroomPosts"
    assert (
        payload["paths"]["/service-policy-posts"]["get"]["operationId"]
        == "listServicePolicyPosts"
    )
    assert payload["paths"]["/research-posts"]["get"]["operationId"] == "listResearchPosts"
    assert (
        payload["paths"]["/newsroom-resource-guides"]["get"]["operationId"]
        == "listNewsroomResourceGuides"
    )
    assert (
        payload["paths"]["/anniversary-guides"]["get"]["operationId"]
        == "listAnniversaryGuides"
    )
    assert (
        payload["paths"]["/service-policy-guides"]["get"]["operationId"]
        == "listServicePolicyGuides"
    )
    assert (
        payload["paths"]["/about-resource-guides"]["get"]["operationId"]
        == "listAboutResourceGuides"
    )
    nearby_restaurant_description = payload["paths"]["/gpt/restaurants/nearby"]["get"][
        "description"
    ]
    restaurant_search_description = payload["paths"]["/gpt/restaurants/search"]["get"][
        "description"
    ]
    assert "Kakao Local external public API" in nearby_restaurant_description
    assert "Kakao Local external public API" in restaurant_search_description
    assert "first-party university source coverage" in restaurant_search_description
    assert (
        payload["paths"]["/gpt/notice-categories"]["get"]["operationId"]
        == "listNoticeCategoriesForGpt"
    )
    about_description = payload["paths"]["/about-resource-guides"]["get"]["description"]
    assert "연혁" in about_description
    assert "교회문헌" in about_description
    assert "예결산공고" in about_description
    student_activity_description = payload["paths"]["/student-activity-guides"]["get"][
        "description"
    ]
    assert "student innovation supporters" in student_activity_description
    assert "CAT-CERT" in student_activity_description


def test_public_readonly_mode_keeps_gpt_actions_v2_slim(monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-api.onrender.com")
    monkeypatch.setenv("SONGSIM_SYNC_OFFICIAL_ON_START", "false")
    monkeypatch.setenv("SONGSIM_SEED_DEMO_ON_START", "false")
    monkeypatch.setenv("SONGSIM_ADMIN_ENABLED", "false")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_ENABLED", "false")
    monkeypatch.setattr("songsim_campus.api.init_db", lambda: None)
    clear_settings_cache()

    app = create_app()
    with TestClient(app) as public_client:
        response = public_client.get("/gpt-actions-openapi-v2.json")

    clear_settings_cache()

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "Songsim Campus GPT Actions v2"
    assert set(payload["paths"]) == {
        "/gpt/classrooms/empty",
        "/gpt/dining-menus",
        "/gpt/library-seats",
        "/gpt/notice-categories",
        "/gpt/notices",
        "/gpt/periods",
        "/gpt/places",
        "/gpt/restaurants/nearby",
        "/gpt/restaurants/search",
    }
    assert "/wifi-guides" not in payload["paths"]
    assert "/phone-book" not in payload["paths"]
    assert "/registration-guides" not in payload["paths"]
    assert "/student-activity-guides" not in payload["paths"]
