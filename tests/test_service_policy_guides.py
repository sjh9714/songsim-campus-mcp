from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from songsim_campus import repo, services
from songsim_campus.api import create_app
from songsim_campus.db import connection, init_db
from songsim_campus.ingest.service_policy_guides import (
    AntiGraftGuideSource,
    BiddingGuideSource,
    CctvPolicyGuideSource,
    JobPostingGuideSource,
    PrivacyPolicyGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_service_policy_guides,
    refresh_service_policy_guides_from_source,
    run_admin_sync,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _tool_payloads(result) -> list[dict[str, object]]:
    return [json.loads(item.text) for item in result]


def test_service_policy_source_defaults() -> None:
    bidding = BiddingGuideSource()
    job_posting = JobPostingGuideSource()
    privacy = PrivacyPolicyGuideSource()
    cctv = CctvPolicyGuideSource()
    anti_graft = AntiGraftGuideSource()

    assert bidding.topic == "bidding"
    assert job_posting.topic == "job_posting"
    assert privacy.topic == "privacy_policy"
    assert cctv.topic == "cctv_policy"
    assert anti_graft.topic == "anti_graft"
    assert bidding.source_tag == "cuk_service_policy_guides"
    assert job_posting.source_tag == "cuk_service_policy_guides"
    assert privacy.source_tag == "cuk_service_policy_guides"
    assert cctv.source_tag == "cuk_service_policy_guides"
    assert anti_graft.source_tag == "cuk_service_policy_guides"
    assert bidding.url.endswith("/service/Bidding.do")
    assert job_posting.url.endswith("/service/Job-posting.do")
    assert privacy.url.endswith("/service/privacy.do")
    assert cctv.url.endswith("/service/notice_cctv_regulation.do")
    assert anti_graft.url.endswith("/service/anti_graft_law1.do")


def test_service_policy_parsers_extract_expected_rows() -> None:
    fetched_at = "2026-03-23T00:00:00+09:00"
    bidding = BiddingGuideSource().parse(_fixture("Bidding.do.html"), fetched_at=fetched_at)
    job_posting = JobPostingGuideSource().parse(
        _fixture("Job-posting.do.html"),
        fetched_at=fetched_at,
    )
    privacy = PrivacyPolicyGuideSource().parse(_fixture("privacy.do.html"), fetched_at=fetched_at)
    cctv = CctvPolicyGuideSource().parse(
        _fixture("notice_cctv_regulation.do.html"),
        fetched_at=fetched_at,
    )
    anti_graft = AntiGraftGuideSource().parse(
        _fixture("anti_graft_law1.do.html"),
        fetched_at=fetched_at,
    )

    assert bidding[0]["topic"] == "bidding"
    assert bidding[0]["title"] == "입찰공고"
    assert bidding[0]["summary"].startswith("가톨릭대학교 공식 입찰공고")
    assert bidding[0]["links"] == [
        {
            "label": "성심교정 시설공사 입찰공고",
            "url": "https://www.catholic.ac.kr/ko/service/Bidding.do?mode=view&articleNo=100",
        }
    ]
    assert job_posting[0]["topic"] == "job_posting"
    assert "공식 채용공고" in job_posting[0]["steps"][0]
    assert job_posting[0]["links"][0]["url"] == (
        "https://www.catholic.ac.kr/ko/service/Job-posting.do?mode=view&articleNo=200"
    )
    assert privacy[0]["topic"] == "privacy_policy"
    assert privacy[0]["title"] == "개인정보처리방침"
    assert "개인정보보호법" in privacy[0]["steps"][0]
    assert cctv[0]["topic"] == "cctv_policy"
    assert cctv[0]["title"] == "영상정보처리기기 운영 및 관리 방침"
    assert "보관기간" in cctv[0]["steps"][0]
    assert anti_graft[0]["topic"] == "anti_graft"
    assert anti_graft[0]["title"] == "청탁금지법 안내"
    assert anti_graft[0]["summary"].startswith("청탁금지법 주요내용")
    assert [item["label"] for item in anti_graft[0]["links"]] == [
        "청탁금지법 주요내용",
        "청탁금지법 법적용대상",
        "청탁금지법 교육/설명자료",
        "청탁방지담당관 및 관련문의",
    ]


def test_service_policy_guides_refresh_replace_and_list(app_env) -> None:
    init_db()

    class BiddingFixtureSource(BiddingGuideSource):
        def fetch(self) -> str:
            return _fixture("Bidding.do.html")

    class JobPostingFixtureSource(JobPostingGuideSource):
        def fetch(self) -> str:
            return _fixture("Job-posting.do.html")

    class PrivacyFixtureSource(PrivacyPolicyGuideSource):
        def fetch(self) -> str:
            return _fixture("privacy.do.html")

    class CctvFixtureSource(CctvPolicyGuideSource):
        def fetch(self) -> str:
            return _fixture("notice_cctv_regulation.do.html")

    class AntiGraftFixtureSource(AntiGraftGuideSource):
        def fetch(self) -> str:
            return _fixture("anti_graft_law1.do.html")

    with connection() as conn:
        refresh_service_policy_guides_from_source(
            conn,
            sources=[
                BiddingFixtureSource(),
                JobPostingFixtureSource(),
                PrivacyFixtureSource(),
                CctvFixtureSource(),
                AntiGraftFixtureSource(),
            ],
            fetched_at="2026-03-23T00:00:00+09:00",
        )
        all_guides = list_service_policy_guides(conn, limit=20)
        filtered = list_service_policy_guides(conn, topic="privacy_policy", limit=20)

        refresh_service_policy_guides_from_source(
            conn,
            sources=[BiddingFixtureSource()],
            fetched_at="2026-03-24T00:00:00+09:00",
        )
        replaced = list_service_policy_guides(conn, limit=20)

    assert [guide.topic for guide in all_guides] == [
        "anti_graft",
        "bidding",
        "cctv_policy",
        "job_posting",
        "privacy_policy",
    ]
    assert [guide.title for guide in filtered] == ["개인정보처리방침"]
    assert [guide.title for guide in replaced] == ["입찰공고"]


def test_service_policy_guides_sync_contract(app_env, monkeypatch) -> None:
    init_db()

    assert "service_policy_guides" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["service_policy_guides"] == "core"
    assert "service_policy_guides" in services.PUBLIC_READY_CORE_DATASETS
    assert "service_policy_guides" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_service_policy_guides_from_source",
        lambda conn: [],
    )

    run = run_admin_sync(target="service_policy_guides")

    assert run.summary == {"service_policy_guides": 0}


def test_service_policy_guides_http_route_filters_and_rejects_invalid_topic(app_env) -> None:
    init_db()
    with connection() as conn:
        repo.replace_service_policy_guides(
            conn,
            [
                {
                    "topic": "privacy_policy",
                    "title": "개인정보처리방침",
                    "summary": "개인정보 공개 방침 안내",
                    "steps": ["공식 개인정보처리방침에서 원문을 확인합니다."],
                    "links": [
                        {
                            "label": "개인정보처리방침",
                            "url": "https://www.catholic.ac.kr/ko/service/privacy.do",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/service/privacy.do",
                    "source_tag": "cuk_service_policy_guides",
                    "last_synced_at": "2026-03-23T00:00:00+09:00",
                },
                {
                    "topic": "anti_graft",
                    "title": "청탁금지법 안내",
                    "summary": "청탁금지법 안내",
                    "steps": ["청탁방지담당관 및 관련 문의를 확인합니다."],
                    "links": [
                        {
                            "label": "청탁금지법 주요내용",
                            "url": "https://www.catholic.ac.kr/ko/service/anti_graft_law1.do",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/service/anti_graft_law1.do",
                    "source_tag": "cuk_service_policy_guides",
                    "last_synced_at": "2026-03-23T00:00:00+09:00",
                },
            ],
        )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/service-policy-guides",
            params={"topic": "privacy_policy", "limit": 5},
        )
        invalid = client.get("/service-policy-guides", params={"topic": "not-a-topic"})

    assert response.status_code == 200
    assert [item["topic"] for item in response.json()] == ["privacy_policy"]
    assert invalid.status_code == 400


def test_service_policy_guides_public_mcp_resource_and_tool_share_service_data(
    app_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        repo.replace_service_policy_guides(
            conn,
            [
                {
                    "topic": "anti_graft",
                    "title": "청탁금지법 안내",
                    "summary": "청탁금지법 주요내용과 문의처 안내",
                    "steps": ["청탁방지담당관 및 관련 문의를 확인합니다."],
                    "links": [
                        {
                            "label": "청탁금지법 주요내용",
                            "url": "https://www.catholic.ac.kr/ko/service/anti_graft_law1.do",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/service/anti_graft_law1.do",
                    "source_tag": "cuk_service_policy_guides",
                    "last_synced_at": "2026-03-23T00:00:00+09:00",
                }
            ],
        )

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_service_policy_guides",
            {"topic": "anti_graft", "limit": 5},
        )
        resource_result = await mcp.read_resource("songsim://service-policy-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())
    tool_payload = _tool_payloads(tool_result)[0]
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["topic"] == "anti_graft"
    assert tool_payload["guide_summary"] == "청탁금지법 주요내용과 문의처 안내"
    assert resource_payload[0]["source_tag"] == "cuk_service_policy_guides"

    clear_settings_cache()
