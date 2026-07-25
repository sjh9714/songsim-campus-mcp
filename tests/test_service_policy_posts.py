from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.service_policy_posts import (
    BiddingPostSource,
    JobPostingPostSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_service_policy_posts,
    refresh_service_policy_posts_from_source,
    run_admin_sync,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _tool_payloads(result) -> list[dict[str, object]]:
    return list(result)


def _read_resource(mcp, uri: str) -> str:
    async def read() -> str:
        resource = await mcp._resource_manager.get_resource(uri)
        return await resource.read()

    return asyncio.run(read())


def test_service_policy_post_source_defaults() -> None:
    bidding = BiddingPostSource()
    job_posting = JobPostingPostSource()

    assert bidding.topic == "bidding"
    assert job_posting.topic == "job_posting"
    assert bidding.source_tag == "cuk_service_policy_posts"
    assert job_posting.source_tag == "cuk_service_policy_posts"
    assert bidding.url.endswith("/service/Bidding.do")
    assert job_posting.url.endswith("/service/Job-posting.do")


def test_service_policy_post_parsers_extract_list_and_detail_rows() -> None:
    bidding = BiddingPostSource()
    job_posting = JobPostingPostSource()

    bidding_rows = bidding.parse_list(_fixture("service_policy_bidding_list.html"))
    bidding_detail = bidding.parse_detail(
        _fixture("service_policy_bidding_detail.html"),
        default_title=bidding_rows[0]["title"] or "",
        default_published_at=bidding_rows[0]["published_at"],
    )
    job_rows = job_posting.parse_list(_fixture("service_policy_job_posting_list.html"))
    job_detail = job_posting.parse_detail(
        _fixture("service_policy_job_posting_detail.html"),
        default_title=job_rows[0]["title"] or "",
        default_published_at=job_rows[0]["published_at"],
    )

    assert bidding_rows[0]["article_no"] == "700"
    assert bidding_rows[0]["title"] == "성심교정 시설공사 입찰공고"
    assert bidding_rows[0]["published_at"] == "2026-04-01"
    assert bidding_detail["summary"].startswith("입찰 참가 자격과 현장설명회")
    assert bidding_detail["body_text"].startswith("입찰 참가 자격")
    assert job_rows[0]["article_no"] == "800"
    assert job_rows[0]["title"] == "가톨릭대학교 계약직 채용공고"
    assert job_detail["summary"].startswith("지원서 접수 기간과 제출 서류")


def test_service_policy_posts_refresh_replace_list_and_query(app_env) -> None:
    init_db()

    class BiddingFixtureSource(BiddingPostSource):
        def fetch_list(self, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("service_policy_bidding_list.html")

        def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("service_policy_bidding_detail.html")

    class JobFixtureSource(JobPostingPostSource):
        def fetch_list(self, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("service_policy_job_posting_list.html")

        def fetch_detail(self, article_no: str, *, offset: int = 0, limit: int = 16) -> str:
            return _fixture("service_policy_job_posting_detail.html")

    with connection() as conn:
        refresh_service_policy_posts_from_source(
            conn,
            sources=[BiddingFixtureSource(), JobFixtureSource()],
            fetched_at="2026-03-26T00:00:00+09:00",
        )
        all_posts = list_service_policy_posts(conn, limit=20)
        filtered = list_service_policy_posts(conn, topic="bidding", query="현장설명회", limit=20)
        refresh_service_policy_posts_from_source(
            conn,
            sources=[JobFixtureSource()],
            fetched_at="2026-03-27T00:00:00+09:00",
        )
        replaced = list_service_policy_posts(conn, limit=20)

    assert [post.topic for post in all_posts] == ["job_posting", "bidding"]
    assert [post.title for post in filtered] == ["성심교정 시설공사 입찰공고"]
    assert [post.topic for post in replaced] == ["job_posting"]


def test_service_policy_posts_sync_contract(app_env, monkeypatch) -> None:
    init_db()

    assert "service_policy_posts" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["service_policy_posts"] == "best_effort"
    assert "service_policy_posts" in services.PUBLIC_READY_BEST_EFFORT_DATASETS
    assert "service_policy_posts" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_service_policy_posts_from_source",
        lambda conn: [],
    )

    run = run_admin_sync(target="service_policy_posts")

    assert run.summary == {"service_policy_posts": 0}


def test_service_policy_posts_http_route_filters_and_rejects_invalid_topic(app_env) -> None:
    init_db()
    with connection() as conn:
        repo.replace_service_policy_posts(
            conn,
            [
                {
                    "topic": "bidding",
                    "article_no": "700",
                    "title": "성심교정 시설공사 입찰공고",
                    "published_at": "2026-04-01",
                    "summary": "입찰 참가 자격과 현장설명회 안내",
                    "body_text": "입찰 참가 자격과 현장설명회 일정을 확인합니다.",
                    "source_url": "https://www.catholic.ac.kr/ko/service/Bidding.do",
                    "source_tag": "cuk_service_policy_posts",
                    "last_synced_at": "2026-03-26T00:00:00+09:00",
                }
            ],
        )

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/service-policy-posts", params={"topic": "bidding", "query": "현장"})
        invalid = client.get("/service-policy-posts", params={"topic": "not-a-topic"})

    assert response.status_code == 200
    assert response.json()[0]["topic"] == "bidding"
    assert invalid.status_code == 400


def test_service_policy_posts_public_mcp_resource_and_tool_share_service_data(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        repo.replace_service_policy_posts(
            conn,
            [
                {
                    "topic": "job_posting",
                    "article_no": "800",
                    "title": "가톨릭대학교 계약직 채용공고",
                    "published_at": "2026-04-02",
                    "summary": "지원서 접수 기간 안내",
                    "body_text": "지원서 접수 기간과 제출 서류를 확인합니다.",
                    "source_url": "https://www.catholic.ac.kr/ko/service/Job-posting.do",
                    "source_tag": "cuk_service_policy_posts",
                    "last_synced_at": "2026-03-26T00:00:00+09:00",
                }
            ],
        )

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()
    try:
        mcp = build_mcp()
        tool = mcp._tool_manager.get_tool("tool_list_service_policy_posts")
        result = tool.fn(topic="job_posting", query="접수", limit=5)
        payload = _tool_payloads(result)
        resource_text = _read_resource(mcp, "songsim://service-policy-posts")
    finally:
        clear_settings_cache()

    resource_payload = json.loads(resource_text)
    assert payload[0]["topic"] == "job_posting"
    assert payload[0]["post_summary"] == "지원서 접수 기간 안내"
    assert resource_payload[0]["source_tag"] == "cuk_service_policy_posts"
