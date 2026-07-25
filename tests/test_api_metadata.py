from __future__ import annotations

from starlette.requests import Request

from songsim_campus.api import create_app
from songsim_campus.api_docs import GPT_ACTION_PATHS, build_filtered_openapi
from songsim_campus.api_pages import (
    render_admin_observability_page,
    render_landing_page,
    render_privacy_page,
)
from songsim_campus.settings import clear_settings_cache, get_settings


def _request_for(app, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("songsim-api.onrender.com", 443),
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "app": app,
        }
    )


def test_build_filtered_openapi_keeps_declared_paths_and_public_server(app_env, monkeypatch):
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-api.onrender.com")
    clear_settings_cache()

    app = create_app()
    request = _request_for(app, "/gpt-actions-openapi.json")
    spec = build_filtered_openapi(
        app=app,
        request=request,
        settings=get_settings(),
        title="Test GPT Actions",
        description="test",
        path_metadata=GPT_ACTION_PATHS,
    )

    clear_settings_cache()

    assert set(spec["paths"]) == set(GPT_ACTION_PATHS)
    assert spec["servers"] == [{"url": "https://songsim-api.onrender.com"}]
    assert (
        spec["paths"]["/places"]["get"]["operationId"]
        == GPT_ACTION_PATHS["/places"]["operationId"]
    )
    assert "/profiles" not in spec["paths"]


def test_render_landing_page_keeps_public_readonly_student_surface():
    html = render_landing_page(
        public_http_url="https://songsim-api.onrender.com",
        mcp_url="https://songsim-mcp.onrender.com/mcp",
        public_readonly=True,
        oauth_enabled=False,
        admin_link_html="",
        gpt_actions_links_html="",
    )

    assert "Songsim Campus MCP" in html
    assert "https://songsim-api.onrender.com" in html
    assert "https://songsim-mcp.onrender.com/mcp" in html
    assert "/academic-support-guides" in html
    assert "/academic-status-guides" in html
    assert "/registration-guides" in html
    assert "/class-guides" in html
    assert "/seasonal-semester-guides" in html
    assert "/phone-book" in html
    assert "/dormitory-guides" in html
    assert "/campus-life-notices" in html
    assert "Kakao Local external public API" in html
    assert "separate from official" in html
    assert "configured without OAuth" in html
    assert "GPT Actions OpenAPI" not in html
    assert "Admin Sync" not in html


def test_render_privacy_page_uses_public_http_url():
    html = render_privacy_page(public_http_url="https://songsim-api.onrender.com")

    assert "Songsim Campus Privacy Policy" in html
    assert "https://songsim-api.onrender.com" in html


def test_render_admin_observability_page_keeps_expected_sections():
    state = {
        "readiness": {
            "ok": True,
            "database": {"ok": True, "error": None},
            "tables": {
                "places": {
                    "ok": True,
                    "row_count": 1,
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            },
        },
        "observability": {
            "process_started_at": "2026-03-18T09:00:00+09:00",
            "cache": {
                "fresh_hit": 0,
                "stale_hit": 0,
                "live_fetch_success": 0,
                "live_fetch_error": 0,
                "local_fallback": 0,
                "restaurant_hours_fresh_hit": 0,
                "restaurant_hours_stale_hit": 0,
                "restaurant_hours_live_fetch_success": 0,
                "restaurant_hours_live_fetch_error": 0,
                "recent_events": [],
            },
            "sync": {
                "recent_events": [],
                "last_failure_at": None,
                "last_failure_message": None,
            },
            "automation": {
                "enabled": True,
                "leader": False,
                "jobs": [],
            },
            "datasets": [
                {
                    "name": "places",
                    "row_count": 1,
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            ],
            "recent_sync_runs": [],
        },
    }

    html = render_admin_observability_page(state=state)

    assert "Songsim Observability" in html
    assert "readyz: ok" in html
    assert "places" in html
    assert "No cache events yet." in html
