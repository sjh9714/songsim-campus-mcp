from __future__ import annotations

import argparse
from pathlib import Path
from types import MethodType

from starlette.responses import JSONResponse

from .db import connection, init_db
from .mcp_oauth import (
    Auth0TokenVerifier,
    attach_optional_bearer_auth,
    build_mcp_tool_meta,
    build_protected_resource_metadata,
    build_protected_resource_metadata_path,
    ensure_authenticated_tool_access,
    is_public_mcp_oauth_enabled,
)
from .mcp_public_catalog import (
    register_public_prompts,
    register_public_resources,
    register_shared_resources,
)
from .mcp_tool_catalog import register_local_profile_tools, register_shared_tools
from .seed import seed_demo
from .services import sync_official_snapshot
from .settings import get_settings

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


def build_mcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise SystemExit(
            "MCP dependency is not installed. "
            "Run `uv sync --extra mcp` or `pip install -e '.[mcp]'`."
        ) from exc

    settings = get_settings()
    public_readonly = settings.app_mode == "public_readonly"
    tool_meta = build_mcp_tool_meta(settings)
    public_mcp_oauth_enabled = is_public_mcp_oauth_enabled(settings)
    token_verifier = None
    if public_mcp_oauth_enabled and settings.resolved_mcp_oauth_audience is not None:
        token_verifier = Auth0TokenVerifier(
            issuer_url=settings.mcp_oauth_issuer or "",
            audience=settings.resolved_mcp_oauth_audience,
            required_scopes=settings.mcp_oauth_scopes,
        )
    mcp = FastMCP(
        "Songsim Campus MCP",
        instructions=(
            "Use this read-only Songsim campus info server to answer student questions "
            "about places, courses, academic calendar, academic support, academic status, "
            "registration, class, seasonal semester, academic milestone, phone book, "
            "dormitory, notices, affiliated notices, certificate, leave-of-absence, "
            "scholarship guides, about resource guides, service policy guides, "
            "service policy posts, newsroom posts, research posts, newsroom resources, "
            "anniversary guides, student activity notices, wifi guides, "
            "dining, nearby restaurants, library seats, empty classrooms, and transport."
        ),
        website_url=settings.public_http_url or None,
        host=settings.app_host,
        port=settings.app_port,
        streamable_http_path="/mcp",
        json_response=True,
    )

    protected_resource_metadata = build_protected_resource_metadata(settings)
    if protected_resource_metadata is not None:
        @mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
        async def oauth_protected_resource_alias(_request):
            return JSONResponse(protected_resource_metadata)

        protected_resource_metadata_path = build_protected_resource_metadata_path(settings)
        if (
            protected_resource_metadata_path is not None
            and protected_resource_metadata_path != "/.well-known/oauth-protected-resource"
        ):
            @mcp.custom_route(protected_resource_metadata_path, methods=["GET"])
            async def oauth_protected_resource(_request):
                return JSONResponse(protected_resource_metadata)

    register_shared_resources(mcp, connection, DOCS_DIR)

    if public_readonly:
        register_public_resources(mcp, connection)
        register_public_prompts(mcp)
    register_shared_tools(
        mcp,
        connection,
        public_readonly=public_readonly,
        tool_meta=tool_meta,
    )

    if not public_readonly:
        register_local_profile_tools(mcp, connection)

    if public_mcp_oauth_enabled and token_verifier is not None:
        original_streamable_http_app = mcp.streamable_http_app
        original_call_tool = mcp.call_tool

        def streamable_http_app_with_optional_auth(self):
            app = original_streamable_http_app()
            return attach_optional_bearer_auth(app, token_verifier)

        async def call_tool_with_mixed_auth(self, name: str, arguments: dict[str, object]):
            try:
                request_context = self.get_context().request_context
            except ValueError:
                request_context = None
            if request_context is not None and request_context.request is not None:
                ensure_authenticated_tool_access(settings)
            return await original_call_tool(name, arguments)

        mcp.streamable_http_app = MethodType(streamable_http_app_with_optional_auth, mcp)
        mcp.call_tool = MethodType(call_tool_with_mixed_auth, mcp)
        mcp._mcp_server.call_tool(validate_input=False)(mcp.call_tool)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Songsim MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    if settings.startup_sync_enabled:
        with connection() as conn:
            sync_official_snapshot(conn)
    elif settings.seed_demo_on_start:
        seed_demo(force=False)

    mcp = build_mcp()
    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
