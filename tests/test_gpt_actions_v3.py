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
        "/gpt/classrooms/empty",
        "/gpt/dining-menus",
        "/gpt/library-seats",
        "/gpt/notices",
        "/gpt/periods",
        "/gpt/places",
        "/gpt/restaurants/nearby",
        "/gpt/restaurants/search",
        "/leave-of-absence-guides",
        "/pc-software",
        "/phone-book",
        "/registration-guides",
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
    assert (
        payload["paths"]["/about-resource-guides"]["get"]["operationId"]
        == "listAboutResourceGuides"
    )


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
