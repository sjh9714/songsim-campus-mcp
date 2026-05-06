from __future__ import annotations

import asyncio
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from mcp.types import LATEST_PROTOCOL_VERSION

from songsim_campus.mcp_server import build_mcp
from songsim_campus.settings import clear_settings_cache


def _set_public_oauth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-public-api.onrender.com")
    monkeypatch.setenv("SONGSIM_PUBLIC_MCP_URL", "https://songsim-public-mcp.onrender.com/mcp")
    monkeypatch.setenv("SONGSIM_PUBLIC_MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_ISSUER", "https://songsim.us.auth0.com/")
    monkeypatch.setenv(
        "SONGSIM_MCP_OAUTH_AUDIENCE",
        "https://songsim-public-mcp.onrender.com/mcp",
    )
    monkeypatch.setenv("SONGSIM_MCP_OAUTH_SCOPES", "songsim.read")
    clear_settings_cache()


def _set_public_anonymous_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_PUBLIC_HTTP_URL", "https://songsim-public-api.onrender.com")
    monkeypatch.setenv("SONGSIM_PUBLIC_MCP_URL", "https://songsim-public-mcp.onrender.com/mcp")
    monkeypatch.setenv("SONGSIM_PUBLIC_MCP_AUTH_MODE", "anonymous")
    monkeypatch.delenv("SONGSIM_MCP_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("SONGSIM_MCP_OAUTH_ISSUER", raising=False)
    monkeypatch.delenv("SONGSIM_MCP_OAUTH_AUDIENCE", raising=False)
    monkeypatch.delenv("SONGSIM_MCP_OAUTH_SCOPES", raising=False)
    clear_settings_cache()


def _json_rpc_headers(*, session_id: str | None = None) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "host": "127.0.0.1:8000",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
        headers["mcp-protocol-version"] = LATEST_PROTOCOL_VERSION
    return headers


def test_mcp_oauth_metadata_and_initialize_flow(app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    _set_public_oauth_env(monkeypatch)

    mcp = build_mcp()
    with TestClient(mcp.streamable_http_app()) as client:
        root_metadata = client.get("/.well-known/oauth-protected-resource")
        scoped_metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        initialize = client.post(
            "/mcp",
            headers=_json_rpc_headers(),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            },
        )
        session_id = initialize.headers["mcp-session-id"]
        list_tools = client.post(
            "/mcp",
            headers=_json_rpc_headers(session_id=session_id),
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )

    clear_settings_cache()

    assert root_metadata.status_code == 200
    assert scoped_metadata.status_code == 200
    assert root_metadata.json()["resource"] == "https://songsim-public-mcp.onrender.com/mcp"
    assert root_metadata.json()["authorization_servers"] == ["https://songsim.us.auth0.com/"]
    assert root_metadata.json()["scopes_supported"] == ["songsim.read"]
    assert scoped_metadata.json() == root_metadata.json()
    assert initialize.status_code == 200
    assert initialize.json()["result"]["serverInfo"]["name"] == "Songsim Campus MCP"
    assert "read-only Songsim campus info server" in initialize.json()["result"]["instructions"]
    assert "academic calendar" in initialize.json()["result"]["instructions"]
    assert "academic support" in initialize.json()["result"]["instructions"]
    assert "academic status" in initialize.json()["result"]["instructions"]
    assert "registration" in initialize.json()["result"]["instructions"]
    assert "class" in initialize.json()["result"]["instructions"]
    assert "seasonal semester" in initialize.json()["result"]["instructions"]
    assert "academic milestone" in initialize.json()["result"]["instructions"]
    assert "about resource guides" in initialize.json()["result"]["instructions"]
    assert "service policy guides" in initialize.json()["result"]["instructions"]
    assert "newsroom posts" in initialize.json()["result"]["instructions"]
    assert "phone book" in initialize.json()["result"]["instructions"]
    assert "affiliated notices" in initialize.json()["result"]["instructions"]
    assert "wifi guides" in initialize.json()["result"]["instructions"]
    assert session_id
    assert list_tools.status_code == 200
    assert {tool["name"] for tool in list_tools.json()["result"]["tools"]} == {
        "tool_search_places",
        "tool_get_place",
        "tool_search_courses",
        "tool_list_academic_calendar",
        "tool_list_academic_support_guides",
        "tool_list_academic_status_guides",
        "tool_list_registration_guides",
        "tool_list_class_guides",
        "tool_list_seasonal_semester_guides",
        "tool_list_academic_milestone_guides",
        "tool_list_student_activity_guides",
        "tool_list_about_resource_guides",
        "tool_list_service_policy_guides",
        "tool_list_newsroom_posts",
        "tool_list_student_exchange_guides",
        "tool_search_student_exchange_partners",
        "tool_search_phone_book",
        "tool_list_campus_life_support_guides",
        "tool_list_campus_life_notices",
        "tool_search_pc_software",
        "tool_list_dormitory_guides",
        "tool_list_certificate_guides",
        "tool_list_leave_of_absence_guides",
        "tool_list_scholarship_guides",
        "tool_list_wifi_guides",
        "tool_get_class_periods",
        "tool_get_library_seat_status",
        "tool_list_estimated_empty_classrooms",
        "tool_find_nearby_restaurants",
        "tool_search_restaurants",
        "tool_search_dining_menus",
        "tool_list_affiliated_notices",
        "tool_list_latest_notices",
        "tool_list_transport_guides",
    }


def test_mcp_oauth_tool_calls_require_auth_after_initialize(app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    _set_public_oauth_env(monkeypatch)

    mcp = build_mcp()
    with TestClient(mcp.streamable_http_app()) as client:
        initialize = client.post(
            "/mcp",
            headers=_json_rpc_headers(),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            },
        )
        session_id = initialize.headers["mcp-session-id"]
        tool_call = client.post(
            "/mcp",
            headers=_json_rpc_headers(session_id=session_id),
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "tool_search_places",
                    "arguments": {"query": "도서관"},
                },
            },
        )

    clear_settings_cache()

    assert initialize.status_code == 200
    assert tool_call.status_code == 200
    payload = tool_call.json()["result"]
    assert payload["isError"] is True
    assert payload["content"][0]["text"] == "Authentication required for Songsim MCP tools."


def test_mcp_public_anonymous_mode_hides_oauth_metadata_and_allows_tool_calls(
    app_env, monkeypatch
):
    pytest.importorskip("mcp.server.fastmcp")
    _set_public_anonymous_env(monkeypatch)

    mcp = build_mcp()
    with TestClient(mcp.streamable_http_app()) as client:
        root_metadata = client.get("/.well-known/oauth-protected-resource")
        scoped_metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        initialize = client.post(
            "/mcp",
            headers=_json_rpc_headers(),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            },
        )
        session_id = initialize.headers["mcp-session-id"]
        tool_call = client.post(
            "/mcp",
            headers=_json_rpc_headers(session_id=session_id),
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "tool_get_class_periods",
                    "arguments": {},
                },
            },
        )
        list_tools = client.post(
            "/mcp",
            headers=_json_rpc_headers(session_id=session_id),
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/list",
                "params": {},
            },
        )

    clear_settings_cache()

    assert root_metadata.status_code == 404
    assert scoped_metadata.status_code == 404
    assert initialize.status_code == 200
    assert tool_call.status_code == 200
    payload = tool_call.json()["result"]
    assert payload["isError"] is False
    assert '"period":1' in payload["content"][0]["text"].replace(" ", "")
    tools = list_tools.json()["result"]["tools"]
    assert tools
    assert all(
        "securitySchemes" not in tool.get("_meta", {})  # nosec: test assertion
        for tool in tools
    )


def test_mcp_public_tools_include_oauth_security_metadata(app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    _set_public_oauth_env(monkeypatch)

    async def main():
        mcp = build_mcp()
        return [tool.model_dump(by_alias=True) for tool in await mcp.list_tools()]

    tools = asyncio.run(main())
    clear_settings_cache()

    assert tools
    assert "tool_create_profile" not in {tool["name"] for tool in tools}
    assert all(tool["_meta"]["securitySchemes"][0]["type"] == "oauth2" for tool in tools)
    assert all(tool["_meta"]["securitySchemes"][0]["scopes"] == ["songsim.read"] for tool in tools)


def test_auth0_token_verifier_accepts_valid_jwt(monkeypatch):
    from songsim_campus.mcp_oauth import Auth0TokenVerifier

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test-kid"
    verifier = Auth0TokenVerifier(
        issuer_url="https://songsim.us.auth0.com/",
        audience="https://songsim-public-mcp.onrender.com/mcp",
        required_scopes=["songsim.read"],
    )

    async def fake_jwks_document():
        return {"keys": [public_jwk]}

    monkeypatch.setattr(verifier, "_get_jwks_document", fake_jwks_document)
    token = jwt.encode(
        {
            "iss": "https://songsim.us.auth0.com/",
            "aud": "https://songsim-public-mcp.onrender.com/mcp",
            "sub": "google-oauth2|songsim-user",
            "scope": "openid profile songsim.read",
            "exp": int(time.time()) + 600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )

    result = asyncio.run(verifier.verify_token(token))

    assert result is not None
    assert result.client_id == "google-oauth2|songsim-user"
    assert "songsim.read" in result.scopes


@pytest.mark.parametrize(
    ("payload", "required_scopes"),
    [
        (
            {
                "iss": "https://wrong-issuer.example.com/",
                "aud": "https://songsim-public-mcp.onrender.com/mcp",
                "scope": "songsim.read",
            },
            ["songsim.read"],
        ),
        (
            {
                "iss": "https://songsim.us.auth0.com/",
                "aud": "https://wrong-resource.example.com/mcp",
                "scope": "songsim.read",
            },
            ["songsim.read"],
        ),
        (
            {
                "iss": "https://songsim.us.auth0.com/",
                "aud": "https://songsim-public-mcp.onrender.com/mcp",
                "scope": "openid profile",
            },
            ["songsim.read"],
        ),
        (
            {
                "iss": "https://songsim.us.auth0.com/",
                "aud": "https://songsim-public-mcp.onrender.com/mcp",
                "scope": "songsim.read",
                "exp": int(time.time()) - 60,
            },
            ["songsim.read"],
        ),
    ],
)
def test_auth0_token_verifier_rejects_invalid_jwt(monkeypatch, payload, required_scopes):
    from songsim_campus.mcp_oauth import Auth0TokenVerifier

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test-kid"
    verifier = Auth0TokenVerifier(
        issuer_url="https://songsim.us.auth0.com/",
        audience="https://songsim-public-mcp.onrender.com/mcp",
        required_scopes=required_scopes,
    )

    async def fake_jwks_document():
        return {"keys": [public_jwk]}

    monkeypatch.setattr(verifier, "_get_jwks_document", fake_jwks_document)
    merged_payload = {
        "sub": "google-oauth2|songsim-user",
        "exp": int(time.time()) + 600,
        **payload,
    }
    token = jwt.encode(
        merged_payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )

    result = asyncio.run(verifier.verify_token(token))

    assert result is None
