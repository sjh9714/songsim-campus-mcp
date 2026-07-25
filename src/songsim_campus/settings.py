from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SONGSIM_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "Songsim Campus Assistant"
    database_url: str = "postgresql://songsim:songsim@127.0.0.1:55432/songsim"
    database_path: str | None = None
    seed_demo_on_start: bool = True
    sync_official_on_start: bool = False
    admin_enabled: bool = False
    app_mode: Literal["local_full", "public_readonly"] = "local_full"
    public_http_url: str | None = None
    public_mcp_url: str | None = None
    # 학생용 모바일 웹 주소. 설정하면 랜딩 페이지가 학생을 먼저 이쪽으로 보낸다.
    student_web_url: str | None = None
    public_mcp_auth_mode: Literal["anonymous", "oauth"] = "anonymous"
    mcp_oauth_enabled: bool = False
    mcp_oauth_issuer: str | None = None
    mcp_oauth_audience: str | None = None
    mcp_oauth_scopes: Annotated[list[str], NoDecode] = ["songsim.read"]
    automation_enabled: bool = False
    automation_tick_seconds: int = 60
    automation_snapshot_interval_minutes: int = 360
    automation_cache_cleanup_interval_minutes: int = 720
    library_seat_prewarm_interval_minutes: int = 5
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    kakao_rest_api_key: str | None = None
    restaurant_cache_ttl_minutes: int = 360
    restaurant_cache_stale_ttl_minutes: int = 1440
    restaurant_hours_cache_ttl_minutes: int = 1440
    restaurant_hours_cache_stale_ttl_minutes: int = 10080
    library_seat_cache_ttl_minutes: int = 2
    library_seat_cache_stale_ttl_minutes: int = 15
    official_campus_id: str = "1"
    official_notice_pages: int = 3
    official_course_year: int | None = None
    official_course_semester: int | None = None

    @field_validator(
        "public_http_url",
        "public_mcp_url",
        "student_web_url",
        "kakao_rest_api_key",
        "mcp_oauth_issuer",
        "mcp_oauth_audience",
        "official_course_year",
        "official_course_semester",
        mode="before",
    )
    @classmethod
    def blank_values_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("mcp_oauth_scopes", mode="before")
    @classmethod
    def parse_mcp_oauth_scopes(cls, value: object) -> object:
        if value is None or value == "":
            return ["songsim.read"]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def resolved_mcp_oauth_audience(self) -> str | None:
        return self.mcp_oauth_audience or self.public_mcp_url

    @property
    def automation_runtime_enabled(self) -> bool:
        return self.automation_enabled and self.app_mode != "public_readonly"

    @property
    def startup_sync_enabled(self) -> bool:
        return self.sync_official_on_start and self.app_mode != "public_readonly"

    @model_validator(mode="after")
    def reject_legacy_database_path(self) -> Settings:
        if self.database_path or os.environ.get("SONGSIM_DATABASE_PATH"):
            raise ValueError(
                "SONGSIM_DATABASE_PATH is no longer supported. "
                "Use SONGSIM_DATABASE_URL instead."
            )
        if self.app_mode == "public_readonly" and self.public_mcp_auth_mode == "oauth":
            if not self.mcp_oauth_issuer:
                raise ValueError(
                    "SONGSIM_MCP_OAUTH_ISSUER is required when "
                    "SONGSIM_PUBLIC_MCP_AUTH_MODE=oauth."
                )
            if not self.resolved_mcp_oauth_audience:
                raise ValueError(
                    "SONGSIM_MCP_OAUTH_AUDIENCE or SONGSIM_PUBLIC_MCP_URL is required "
                    "when SONGSIM_PUBLIC_MCP_AUTH_MODE=oauth."
                )
            if not self.mcp_oauth_scopes:
                raise ValueError(
                    "SONGSIM_MCP_OAUTH_SCOPES must include at least one scope "
                    "when SONGSIM_PUBLIC_MCP_AUTH_MODE=oauth."
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
