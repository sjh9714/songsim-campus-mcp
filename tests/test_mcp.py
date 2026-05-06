from __future__ import annotations

import asyncio
import json
from datetime import datetime

import pytest

from songsim_campus.db import connection, init_db
from songsim_campus.mcp_server import build_mcp
from songsim_campus.repo import (
    replace_about_resource_guides,
    replace_campus_dining_menus,
    replace_campus_facilities,
    replace_courses,
    replace_dormitory_guides,
    replace_notices,
    replace_places,
    replace_restaurant_cache_snapshot,
    replace_restaurants,
    replace_student_activity_guides,
    replace_student_exchange_guides,
    replace_student_exchange_partners,
    replace_transport_guides,
    update_place_opening_hours,
)
from songsim_campus.schemas import CampusLifeNotice
from songsim_campus.seed import seed_demo
from songsim_campus.services import (
    refresh_academic_calendar_from_source,
    refresh_academic_status_guides_from_source,
    refresh_academic_support_guides_from_source,
    refresh_affiliated_notices_from_sources,
    refresh_certificate_guides_from_certificate_page,
    refresh_leave_of_absence_guides_from_source,
    refresh_scholarship_guides_from_source,
    refresh_transport_guides_from_location_page,
    refresh_wifi_guides_from_source,
)
from songsim_campus.settings import clear_settings_cache


class McpTransportSource:
    def fetch(self):
        return '<transport></transport>'

    def parse(self, html: str, *, fetched_at: str):
        assert html == '<transport></transport>'
        return [
            {
                'mode': 'subway',
                'title': '1호선',
                'summary': '역곡역 2번 출구에서 도보 10분',
                'steps': ['인천역 ↔ 역곡역 : 35분 소요'],
                'source_url': 'https://www.catholic.ac.kr/ko/about/location_songsim.do',
                'source_tag': 'cuk_transport',
                'last_synced_at': fetched_at,
            }
        ]


class McpCertificateSource:
    def fetch(self):
        return "<certificate></certificate>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<certificate></certificate>"
        return [
            {
                "title": "인터넷 증명발급",
                "summary": "인터넷 증명신청 및 발급",
                "steps": [
                    "수수료: 발급 : 국문 / 영문 1,000원(1매)",
                    "유의사항: 영문증명서의 경우 영문 성명이 없으면 증명 발급이 되지 않음",
                ],
                "source_url": "https://catholic.certpia.com/",
                "source_tag": "cuk_certificate_guides",
                "last_synced_at": fetched_at,
            }
        ]


class McpLeaveOfAbsenceSource:
    def fetch(self):
        return "<leave></leave>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<leave></leave>"
        return [
            {
                "title": "신청방법",
                "summary": "Trinity 신청 → 휴학상담 → 휴학신청 승인 → 휴학최종 승인",
                "steps": ["STEP 1: Trinity 신청 (학생)"],
                "links": [
                    {
                        "label": "휴복학 FAQ (다운로드)",
                        "url": "https://www.catholic.ac.kr/cms/etcResourceDown.do?site=fake&key=fake",
                    }
                ],
                "source_url": "https://www.catholic.ac.kr/ko/support/leave_of_absence.do",
                "source_tag": "cuk_leave_of_absence_guides",
                "last_synced_at": fetched_at,
            }
        ]


class McpAcademicCalendarSource:
    def fetch_range(self, *, start_date: str, end_date: str):
        assert start_date == "2026-03-01"
        assert end_date == "2027-02-28"
        return '{"data":[]}'

    def parse(self, payload: str, *, fetched_at: str):
        assert payload == '{"data":[]}'
        return [
            {
                "academic_year": 2026,
                "title": "1학기 개시일",
                "start_date": "2026-03-03",
                "end_date": "2026-03-03",
                "campuses": ["성심", "성의", "성신"],
                "source_url": "https://www.catholic.ac.kr/ko/support/calendar2024_list.do",
                "source_tag": "cuk_academic_calendar",
                "last_synced_at": fetched_at,
            }
        ]


class McpScholarshipSource:
    def fetch(self):
        return "<scholarship></scholarship>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<scholarship></scholarship>"
        return [
            {
                "title": "공식 장학 문서",
                "summary": "장학금 지급 규정과 신입생/재학생 장학제도 공식 문서 링크",
                "steps": [],
                "links": [
                    {
                        "label": "신입생(내국인) 장학제도",
                        "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/scholarship_songsim_251226-2pdf.pdf",
                    }
                ],
                "source_url": "https://www.catholic.ac.kr/ko/support/scholarship_songsim.do",
                "source_tag": "cuk_scholarship_guides",
                "last_synced_at": fetched_at,
            }
        ]


class McpWifiGuideSource:
    def fetch(self):
        return "<wifi></wifi>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<wifi></wifi>"
        return [
            {
                "building_name": "니콜스관",
                "ssids": ["catholic_univ", "강의실 호실명 (ex: N301)"],
                "steps": [
                    "무선랜 안테나 검색 후 신호가 강한 SSID 선택 (최초 접속 시 보안키 입력)",
                    "K관, A관(안드레아관) 보안키 : catholic!!(교내 동일)",
                ],
                "source_url": "https://www.catholic.ac.kr/ko/campuslife/wifi.do",
                "source_tag": "cuk_wifi_guides",
                "last_synced_at": fetched_at,
            }
        ]


class McpAcademicSupportSource:
    def fetch(self):
        return "<academic-support></academic-support>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == "<academic-support></academic-support>"
        return [
            {
                "title": "휴·복학",
                "summary": "학적변동 업무(휴학, 복학, 군휴학, 자퇴 등)",
                "steps": ["학적변동 업무(휴학, 복학, 군휴학, 자퇴 등)"],
                "contacts": ["02-2164-4288"],
                "source_url": "https://www.catholic.ac.kr/ko/support/academic_contact_information.do",
                "source_tag": "cuk_academic_support_guides",
                "last_synced_at": fetched_at,
            }
        ]


class McpAcademicStatusSource:
    def __init__(self, status: str, rows: list[dict[str, object]]):
        self.status = status
        self.rows = rows

    def fetch(self):
        return f"<{self.status}></{self.status}>"

    def parse(self, html: str, *, fetched_at: str):
        assert html == f"<{self.status}></{self.status}>"
        source_urls = {
            "return_from_leave": "https://www.catholic.ac.kr/ko/support/return_from_leave_of_absence.do",
            "dropout": "https://www.catholic.ac.kr/ko/support/dropout.do",
            "re_admission": "https://www.catholic.ac.kr/ko/support/re_admission.do",
        }
        return [
            {
                **row,
                "status": self.status,
                "source_url": source_urls[self.status],
                "source_tag": "cuk_academic_status_guides",
                "last_synced_at": fetched_at,
            }
            for row in self.rows
        ]


def _tool_payloads(result) -> list[dict[str, object]]:
    return [json.loads(item.text) for item in result]


def test_mcp_transport_tool_and_resource_share_service_data(app_env):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_transport_guides_from_location_page(conn, source=McpTransportSource())

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool('tool_list_transport_guides', {'limit': 10})
        resource_result = await mcp.read_resource('songsim://transport-guide')
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload['title'] == '1호선'
    assert resource_payload[0]['title'] == '1호선'


def test_mcp_certificate_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_certificate_guides_from_certificate_page(conn, source=McpCertificateSource())

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool("tool_list_certificate_guides", {"limit": 10})
        resource_result = await mcp.read_resource("songsim://certificate-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "인터넷 증명발급"
    assert resource_payload[0]["title"] == "인터넷 증명발급"


def test_mcp_leave_of_absence_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_leave_of_absence_guides_from_source(conn, source=McpLeaveOfAbsenceSource())

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool("tool_list_leave_of_absence_guides", {"limit": 10})
        resource_result = await mcp.read_resource("songsim://leave-of-absence-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "신청방법"
    assert resource_payload[0]["title"] == "신청방법"


def test_mcp_academic_calendar_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_academic_calendar_from_source(
            conn,
            source=McpAcademicCalendarSource(),
            academic_year=2026,
        )

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_academic_calendar",
            {"academic_year": 2026, "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://academic-calendar")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "1학기 개시일"
    assert resource_payload[0]["title"] == "1학기 개시일"


def test_mcp_scholarship_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_scholarship_guides_from_source(conn, source=McpScholarshipSource())

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool("tool_list_scholarship_guides", {"limit": 10})
        resource_result = await mcp.read_resource("songsim://scholarship-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "공식 장학 문서"
    assert resource_payload[0]["title"] == "공식 장학 문서"


def test_mcp_wifi_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_wifi_guides_from_source(conn, source=McpWifiGuideSource())

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool("tool_list_wifi_guides", {"limit": 10})
        resource_result = await mcp.read_resource("songsim://wifi-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["building_name"] == "니콜스관"
    assert resource_payload[0]["building_name"] == "니콜스관"


def test_mcp_academic_support_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_academic_support_guides_from_source(conn, source=McpAcademicSupportSource())

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool("tool_list_academic_support_guides", {"limit": 10})
        resource_result = await mcp.read_resource("songsim://academic-support-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "휴·복학"
    assert tool_payload["contacts"] == ["02-2164-4288"]
    assert resource_payload[0]["title"] == "휴·복학"


def test_mcp_academic_status_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        refresh_academic_status_guides_from_source(
            conn,
            sources=[
                McpAcademicStatusSource(
                    "return_from_leave",
                    [
                        {
                            "title": "신청방법",
                            "summary": "TRINITY 복학신청",
                            "steps": ["TRINITY ⇒ 학적/졸업 ⇒ 복학신청"],
                            "links": [],
                        }
                    ],
                ),
                McpAcademicStatusSource(
                    "dropout",
                    [
                        {
                            "title": "자퇴 신청 방법",
                            "summary": "방문신청",
                            "steps": ["학사지원팀에 자퇴원 제출"],
                            "links": [],
                        }
                    ],
                ),
                McpAcademicStatusSource(
                    "re_admission",
                    [
                        {
                            "title": "지원자격",
                            "summary": "제적 후 1년 경과",
                            "steps": ["제적, 자퇴 후 1년이 경과한 자"],
                            "links": [],
                        }
                    ],
                ),
            ],
        )

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_academic_status_guides",
            {"status": "dropout", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://academic-status-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["status"] == "dropout"
    assert tool_payload["title"] == "자퇴 신청 방법"
    assert tool_payload["links"] == []
    assert resource_payload[0]["source_tag"] == "cuk_academic_status_guides"


def test_mcp_dormitory_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_dormitory_guides(
            conn,
            [
                {
                    "topic": "hall_info",
                    "title": "스테파노관",
                    "summary": "성심교정 기숙사",
                    "steps": ["수용인원", "편의시설", "연락처"],
                    "links": [],
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/dormitory_songsim.do",
                    "source_tag": "cuk_dormitory_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                },
            ],
        )

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_dormitory_guides",
            {"topic": "hall_info", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://dormitory-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "스테파노관"
    assert tool_payload["topic"] == "hall_info"
    assert resource_payload[0]["source_tag"] == "cuk_dormitory_guides"


def test_mcp_student_activity_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_student_activity_guides(
            conn,
            [
                {
                    "topic": "student_government",
                    "title": "총학생회",
                    "summary": "학생 자치 대표 기구",
                    "steps": ["학생 의견 수렴"],
                    "links": [],
                    "source_url": "https://example.com/student-activity",
                    "source_tag": "cuk_student_activity_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        )

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_student_activity_guides",
            {"topic": "student_government", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://student-activity-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "총학생회"
    assert tool_payload["topic"] == "student_government"
    assert resource_payload[0]["source_tag"] == "cuk_student_activity_guides"


def test_mcp_about_resource_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_about_resource_guides(
            conn,
            [
                {
                    "topic": "rules",
                    "title": "규정",
                    "summary": "규정정보시스템 안내",
                    "steps": ["공식 규정정보시스템에서 원문을 확인합니다."],
                    "links": [
                        {
                            "label": "규정정보시스템 바로가기",
                            "url": "http://rule.catholic.ac.kr:8080/lmxsrv/main/main.srv",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/about/rule.do",
                    "source_tag": "cuk_about_resource_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        )

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_about_resource_guides",
            {"topic": "rules", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://about-resource-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "규정"
    assert tool_payload["topic"] == "rules"
    assert resource_payload[0]["source_tag"] == "cuk_about_resource_guides"


def test_mcp_student_exchange_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_student_exchange_guides(
            conn,
            [
                {
                    "topic": "exchange_student",
                    "title": "상호교환 프로그램",
                    "summary": "해외 교환학생 프로그램 안내",
                    "steps": ["학기당 최대 19학점"],
                    "links": [
                        {
                            "label": "교환학생 프로그램 알아보기",
                            "url": "https://oia.catholic.ac.kr/oia/admission/exchange-student.do",
                        }
                    ],
                    "source_url": "https://www.catholic.ac.kr/ko/support/exchange_oversea2.do",
                    "source_tag": "cuk_student_exchange_guides",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        )

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_list_student_exchange_guides",
            {"topic": "exchange_student", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://student-exchange-guide")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["title"] == "상호교환 프로그램"
    assert tool_payload["topic"] == "exchange_student"
    assert resource_payload[0]["source_tag"] == "cuk_student_exchange_guides"


def test_mcp_student_exchange_partner_tool_and_resource_share_service_data(app_env):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_student_exchange_partners(
            conn,
            [
                {
                    "partner_code": "001",
                    "university_name": "Utrecht University",
                    "country_ko": "네덜란드",
                    "country_en": "Netherlands",
                    "continent": "EUROPE",
                    "location": "Utrecht",
                    "agreement_date": "2024-01-01",
                    "homepage_url": "https://www.uu.nl/",
                    "source_url": "https://www.catholic.ac.kr/ko/support/exchange_oversea1.do",
                    "source_tag": "cuk_student_exchange_partners",
                    "last_synced_at": "2026-03-20T10:00:00+09:00",
                }
            ],
        )

    async def main():
        mcp = build_mcp()
        tool_result = await mcp.call_tool(
            "tool_search_student_exchange_partners",
            {"query": "Utrecht", "limit": 10},
        )
        resource_result = await mcp.read_resource("songsim://student-exchange-partners")
        return tool_result, list(resource_result)

    tool_result, resource_result = asyncio.run(main())

    tool_payload = json.loads(tool_result[0].text)
    resource_payload = json.loads(resource_result[0].content)

    assert tool_payload["university_name"] == "Utrecht University"
    assert tool_payload["partner_code"] == "001"
    assert resource_payload[0]["source_tag"] == "cuk_student_exchange_partners"


def test_mcp_transport_tool_accepts_query_and_mode_precedence(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_transport_guides(
            conn,
            [
                {
                    "mode": "bus",
                    "title": "마을버스",
                    "summary": "51번, 51-1번, 51-2번 버스",
                    "steps": ["[가톨릭대학교, 역곡도서관] 정류장 하차"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "mode": "subway",
                    "title": "1호선",
                    "summary": "역곡역 2번 출구 또는 소사역 3번 출구에서 도보 10분",
                    "steps": ["인천역 ↔ 역곡역 : 35분 소요"],
                    "source_url": "https://www.catholic.ac.kr/ko/about/location_songsim.do",
                    "source_tag": "cuk_transport",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        subway = await mcp.call_tool("tool_list_transport_guides", {"query": "지하철"})
        shuttle = await mcp.call_tool("tool_list_transport_guides", {"query": "셔틀"})
        explicit_bus = await mcp.call_tool(
            "tool_list_transport_guides",
            {"mode": "bus", "query": "지하철"},
        )
        return subway, shuttle, explicit_bus

    subway_result, shuttle_result, explicit_bus_result = asyncio.run(main())

    assert _tool_payloads(subway_result)[0]["mode"] == "subway"
    assert _tool_payloads(shuttle_result) == []
    assert _tool_payloads(explicit_bus_result)[0]["mode"] == "bus"

    clear_settings_cache()


def test_mcp_profile_tools_share_timetable_service_data(app_env):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE101",
                    "title": "자료구조",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 7,
                    "period_end": 8,
                    "room": "K201",
                    "raw_schedule": "월7~8(K201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE201",
                    "title": "컴정 1학년 프로젝트입문",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "02",
                    "day_of_week": "수",
                    "period_start": 4,
                    "period_end": 5,
                    "room": "K202",
                    "raw_schedule": "수4~5(K202)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE201",
                    "title": "컴정 1학년 프로젝트입문",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "02",
                    "day_of_week": "수",
                    "period_start": 4,
                    "period_end": 5,
                    "room": "K202",
                    "raw_schedule": "수4~5(K202)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    async def main():
        mcp = build_mcp()
        created = await mcp.call_tool('tool_create_profile', {'display_name': '성심학생'})
        profile = json.loads(created[0].text)
        await mcp.call_tool(
            'tool_set_profile_timetable',
            {
                'profile_id': profile['id'],
                'courses': [
                    {'year': 2026, 'semester': 1, 'code': 'CSE101', 'section': '01'}
                ],
            },
        )
        timetable = await mcp.call_tool(
            'tool_get_profile_timetable',
            {'profile_id': profile['id'], 'year': 2026, 'semester': 1},
        )
        return json.loads(timetable[0].text)

    timetable_payload = asyncio.run(main())

    assert timetable_payload['title'] == '자료구조'


def test_mcp_profile_personalization_tools_share_service_data(app_env):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE101",
                    "title": "자료구조",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 7,
                    "period_end": 8,
                    "room": "K201",
                    "raw_schedule": "월7~8(K201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE201",
                    "title": "1학년 프로젝트입문",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "화",
                    "period_start": 3,
                    "period_end": 4,
                    "room": "K201",
                    "raw_schedule": "화3~4(K201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE201",
                    "title": "컴정 1학년 프로젝트입문",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "02",
                    "day_of_week": "수",
                    "period_start": 4,
                    "period_end": 5,
                    "room": "K202",
                    "raw_schedule": "수4~5(K202)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )

    async def main():
        mcp = build_mcp()
        created = await mcp.call_tool('tool_create_profile', {'display_name': '성심학생'})
        profile = json.loads(created[0].text)
        updated = await mcp.call_tool(
            'tool_update_profile',
            {
                'profile_id': profile['id'],
                'department': '컴퓨터정보공학부',
                'student_year': 1,
                'admission_type': 'freshman',
            },
        )
        timetable = await mcp.call_tool(
            'tool_set_profile_timetable',
            {
                'profile_id': profile['id'],
                'courses': [{'year': 2026, 'semester': 1, 'code': 'CSE101', 'section': '01'}],
            },
        )
        interests = await mcp.call_tool(
            'tool_set_profile_interests',
            {'profile_id': profile['id'], 'tags': ['scholarship', 'language']},
        )
        courses = await mcp.call_tool(
            'tool_get_profile_course_recommendations',
            {'profile_id': profile['id'], 'year': 2026, 'semester': 1},
        )
        meals = await mcp.call_tool(
            'tool_get_profile_meal_recommendations',
            {
                'profile_id': profile['id'],
                'origin': 'central-library',
                'at': '2026-03-16T12:00:00+09:00',
                'year': 2026,
                'semester': 1,
            },
        )
        return (
            json.loads(updated[0].text),
            json.loads(timetable[0].text),
            json.loads(interests[0].text),
            json.loads(courses[0].text),
            json.loads(meals[0].text),
        )

    (
        updated_payload,
        timetable_payload,
        interests_payload,
        course_payload,
        meal_payload,
    ) = asyncio.run(main())

    assert updated_payload['department'] == '컴퓨터정보공학부'
    assert timetable_payload['title'] == '자료구조'
    assert interests_payload['tags'] == ['scholarship', 'language']
    assert course_payload['course']['code'] == 'CSE201'
    assert course_payload['course']['section'] == '02'
    assert course_payload['matched_reasons'] == ['department:컴퓨터정보공학부', 'student_year:1']
    assert meal_payload['next_place']['slug'] == 'kim-sou-hwan-hall'
    assert meal_payload['items']


def test_mcp_nearby_restaurant_tool_supports_open_now_filter(app_env):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "cafe-dream",
                    "name": "카페드림",
                    "category": "cafe",
                    "min_price": 4000,
                    "max_price": 6500,
                    "latitude": 37.48695,
                    "longitude": 126.79995,
                    "tags": ["카페"],
                    "description": "테스트 카페",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "unknown-bap",
                    "name": "알수없음식당",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.4869,
                    "longitude": 126.7999,
                    "tags": ["한식"],
                    "description": "테스트 식당",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"카페드림": "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)"},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {
                'origin': 'central-library',
                'open_now': True,
                'at': '2026-03-15T11:00:00+09:00',
            },
        )
        if not result:
            return []
        return json.loads(result[0].text)

    payload = asyncio.run(main())

    assert payload == []


def test_mcp_nearby_restaurant_tool_reuses_kakao_cache(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class McpCacheKakaoClient:
        calls = 0

        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            type(self).calls += 1
            from songsim_campus.services import KakaoPlace

            return [
                KakaoPlace(
                    name="가톨릭백반",
                    category="음식점 > 한식",
                    address="경기 부천시 원미구",
                    latitude=37.48674,
                    longitude=126.80182,
                    place_id="1",
                    place_url="https://place.map.kakao.com/1",
                )
            ]

    monkeypatch.setattr('songsim_campus.services.KakaoLocalClient', McpCacheKakaoClient)

    async def main():
        mcp = build_mcp()
        first = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': 'central-library', 'category': 'korean', 'walk_minutes': 15},
        )
        second = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': 'central-library', 'category': 'korean', 'walk_minutes': 15},
        )
        return json.loads(first[0].text), json.loads(second[0].text)

    first_payload, second_payload = asyncio.run(main())

    assert McpCacheKakaoClient.calls == 1
    assert first_payload['source_tag'] == 'kakao_local'
    assert second_payload['source_tag'] == 'kakao_local_cache'


def test_mcp_public_readonly_mode_registers_only_read_only_tools(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        return [tool.name for tool in tools], [str(resource.uri) for resource in resources]

    tool_names, resource_uris = asyncio.run(main())

    assert set(tool_names) == {
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
        "tool_search_dining_menus",
        "tool_search_restaurants",
        "tool_find_nearby_restaurants",
        "tool_list_affiliated_notices",
        "tool_list_latest_notices",
        "tool_list_transport_guides",
    }
    assert "tool_create_profile" not in tool_names
    assert "tool_get_profile_notices" not in tool_names
    assert "songsim://source-registry" in resource_uris
    assert "songsim://academic-calendar" in resource_uris
    assert "songsim://academic-support-guide" in resource_uris
    assert "songsim://academic-status-guide" in resource_uris
    assert "songsim://registration-guide" in resource_uris
    assert "songsim://class-guide" in resource_uris
    assert "songsim://seasonal-semester-guide" in resource_uris
    assert "songsim://academic-milestone-guide" in resource_uris
    assert "songsim://student-activity-guide" in resource_uris
    assert "songsim://about-resource-guide" in resource_uris
    assert "songsim://student-exchange-guide" in resource_uris
    assert "songsim://student-exchange-partners" in resource_uris
    assert "songsim://phone-book" in resource_uris
    assert "songsim://campus-life-support-guide" in resource_uris
    assert "songsim://campus-life-notices" in resource_uris
    assert "songsim://pc-software" in resource_uris
    assert "songsim://affiliated-notices" in resource_uris
    assert "songsim://dormitory-guide" in resource_uris
    assert "songsim://certificate-guide" in resource_uris
    assert "songsim://leave-of-absence-guide" in resource_uris
    assert "songsim://scholarship-guide" in resource_uris
    assert "songsim://wifi-guide" in resource_uris
    assert "songsim://transport-guide" in resource_uris

    clear_settings_cache()


def test_mcp_public_readonly_mode_registers_prompts_and_extended_resources(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompts = await mcp.list_prompts()
        resources = await mcp.list_resources()
        return [prompt.name for prompt in prompts], [str(resource.uri) for resource in resources]

    prompt_names, resource_uris = asyncio.run(main())

    assert set(prompt_names) == {
        "prompt_find_place",
        "prompt_search_courses",
        "prompt_academic_calendar",
        "prompt_notice_categories",
        "prompt_latest_notices",
        "prompt_class_periods",
        "prompt_library_seat_status",
        "prompt_find_empty_classrooms",
        "prompt_search_dining_menus",
        "prompt_search_restaurants",
        "prompt_find_nearby_restaurants",
        "prompt_transport_guide",
    }
    assert set(resource_uris) >= {
        "songsim://source-registry",
        "songsim://academic-calendar",
        "songsim://academic-support-guide",
        "songsim://academic-status-guide",
        "songsim://registration-guide",
        "songsim://class-guide",
        "songsim://seasonal-semester-guide",
        "songsim://academic-milestone-guide",
        "songsim://student-activity-guide",
        "songsim://about-resource-guide",
        "songsim://student-exchange-guide",
        "songsim://student-exchange-partners",
        "songsim://phone-book",
        "songsim://campus-life-support-guide",
        "songsim://campus-life-notices",
        "songsim://pc-software",
        "songsim://affiliated-notices",
        "songsim://dormitory-guide",
        "songsim://certificate-guide",
        "songsim://leave-of-absence-guide",
        "songsim://scholarship-guide",
        "songsim://wifi-guide",
        "songsim://transport-guide",
        "songsim://usage-guide",
        "songsim://place-categories",
        "songsim://notice-categories",
        "songsim://class-periods",
    }

    clear_settings_cache()


def test_mcp_local_full_mode_does_not_register_public_prompts(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.delenv("SONGSIM_APP_MODE", raising=False)
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompts = await mcp.list_prompts()
        return [prompt.name for prompt in prompts]

    prompt_names = asyncio.run(main())

    assert prompt_names == []

    clear_settings_cache()


def test_mcp_public_readonly_mode_exposes_agent_friendly_tool_metadata(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tools = await mcp.list_tools()
        return {tool.name: tool.model_dump(by_alias=True) for tool in tools}

    tools = asyncio.run(main())

    assert "건물명" in tools["tool_search_places"]["description"]
    assert "별칭" in tools["tool_search_places"]["description"]
    assert "tool_get_place" in tools["tool_search_places"]["description"]
    assert "교내 입점명" in tools["tool_search_places"]["description"]
    assert "slug" in tools["tool_get_place"]["description"]
    assert "과목명" in tools["tool_search_courses"]["description"]
    assert "교수" in tools["tool_search_courses"]["description"]
    assert "학사일정" in tools["tool_list_academic_calendar"]["description"]
    assert "academic_year" in tools["tool_list_academic_calendar"]["description"]
    assert "휴복학" in tools["tool_list_academic_support_guides"]["description"]
    assert "학점교류" in tools["tool_list_academic_support_guides"]["description"]
    assert "문의처" in tools["tool_list_academic_support_guides"]["description"]
    assert "학적변동" in tools["tool_list_academic_status_guides"]["description"]
    assert "자퇴" in tools["tool_list_academic_status_guides"]["description"]
    assert "등록금 고지서" in tools["tool_list_registration_guides"]["description"]
    assert "등록금 반환 기준" in tools["tool_list_registration_guides"]["description"]
    assert "수업평가" in tools["tool_list_class_guides"]["description"]
    assert "공결" in tools["tool_list_class_guides"]["description"]
    assert "계절학기" in tools["tool_list_seasonal_semester_guides"]["description"]
    assert "학점 제한" in tools["tool_list_seasonal_semester_guides"]["description"]
    assert "성적평가" in tools["tool_list_academic_milestone_guides"]["description"]
    assert "졸업요건" in tools["tool_list_academic_milestone_guides"]["description"]
    assert "학생회" in tools["tool_list_student_activity_guides"]["description"]
    assert "중앙동아리" in tools["tool_list_student_activity_guides"]["description"]
    assert "기관동아리" in tools["tool_list_student_activity_guides"]["description"]
    assert "사회봉사" in tools["tool_list_student_activity_guides"]["description"]
    assert "student_government" in (
        tools["tool_list_student_activity_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "central_clubs" in (
        tools["tool_list_student_activity_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "규정" in tools["tool_list_about_resource_guides"]["description"]
    assert "요람" in tools["tool_list_about_resource_guides"]["description"]
    assert "학사제도안내책자" in tools["tool_list_about_resource_guides"]["description"]
    assert "rules" in (
        tools["tool_list_about_resource_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "academic_handbook" in (
        tools["tool_list_about_resource_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "학생교류" in tools["tool_list_student_exchange_guides"]["description"]
    assert "국내 학점교류" in tools["tool_list_student_exchange_guides"]["description"]
    assert "교환학생 프로그램" in tools["tool_list_student_exchange_guides"]["description"]
    assert "해외협정대학" in tools["tool_search_student_exchange_partners"]["description"]
    assert "Utrecht" in tools["tool_search_student_exchange_partners"]["description"]
    assert "EUROPE" in tools["tool_search_student_exchange_partners"]["description"]
    assert "주요전화번호" in tools["tool_search_phone_book"]["description"]
    assert "기숙사 운영팀" in tools["tool_search_phone_book"]["description"]
    assert "보건실" in tools["tool_list_campus_life_support_guides"]["description"]
    assert "주차요금" in tools["tool_list_campus_life_support_guides"]["description"]
    assert "학생상담" in tools["tool_list_campus_life_support_guides"]["description"]
    assert "장애학생지원센터" in tools["tool_list_campus_life_support_guides"]["description"]
    assert "예비군" in tools["tool_list_campus_life_support_guides"]["description"]
    assert "부속병원" in tools["tool_list_campus_life_support_guides"]["description"]
    assert "대관안내" in tools["tool_list_campus_life_support_guides"]["description"]
    assert "개인형 이동장치 안전교육" in (
        tools["tool_list_campus_life_support_guides"]["description"]
    )
    assert "SPSS" in tools["tool_search_pc_software"]["description"]
    assert "Visual Studio" in tools["tool_search_pc_software"]["description"]
    assert "기숙사" in tools["tool_list_dormitory_guides"]["description"]
    assert "스테파노관" in tools["tool_list_dormitory_guides"]["description"]
    assert "장학제도" in tools["tool_list_scholarship_guides"]["description"]
    assert "공식 문서" in tools["tool_list_scholarship_guides"]["description"]
    assert "무선랜" in tools["tool_list_wifi_guides"]["description"]
    assert "SSID" in tools["tool_list_wifi_guides"]["description"]
    assert "브랜드" in tools["tool_search_restaurants"]["description"]
    assert "매머드커피" in tools["tool_search_restaurants"]["description"]
    assert "학생식당 메뉴" in tools["tool_search_dining_menus"]["description"]
    assert "카페 보나" in tools["tool_search_dining_menus"]["description"]
    assert "열람실" in tools["tool_get_library_seat_status"]["description"]
    assert "남은 좌석" in tools["tool_get_library_seat_status"]["description"]
    assert "실시간" in tools["tool_list_estimated_empty_classrooms"]["description"]
    assert "예상 공실" in tools["tool_list_estimated_empty_classrooms"]["description"]
    assert "니콜스관" in tools["tool_list_estimated_empty_classrooms"]["description"]
    assert "김수환관" in tools["tool_list_estimated_empty_classrooms"]["description"]
    assert "출발지" in tools["tool_find_nearby_restaurants"]["description"]
    assert "alias" in tools["tool_find_nearby_restaurants"]["description"]
    assert "학생식당" in tools["tool_find_nearby_restaurants"]["description"]
    assert "예산" in tools["tool_find_nearby_restaurants"]["description"]
    assert "가격 정보가 없는" in tools["tool_find_nearby_restaurants"]["description"]
    assert "open_now" in tools["tool_find_nearby_restaurants"]["description"]
    assert "walk_minutes" in tools["tool_find_nearby_restaurants"]["description"]
    assert "카테고리" in tools["tool_list_latest_notices"]["description"]
    assert "optional" in tools["tool_list_latest_notices"]["description"]
    assert "증명서" in tools["tool_list_certificate_guides"]["description"]
    assert "발급 안내" in tools["tool_list_certificate_guides"]["description"]
    assert "지하철" in tools["tool_list_transport_guides"]["description"]
    assert "버스" in tools["tool_list_transport_guides"]["description"]

    place_query_description = (
        tools["tool_search_places"]["inputSchema"]["properties"]["query"]["description"]
    )
    assert "건물명" in place_query_description
    assert "트러스트짐" in place_query_description
    assert "헬스장" in place_query_description
    assert "편의점" in place_query_description
    assert "K관" in place_query_description
    assert "정문" in place_query_description
    assert "브랜드 상호" in (
        tools["tool_search_restaurants"]["inputSchema"]["properties"]["query"]["description"]
    )
    assert "학생식당 메뉴" in (
        tools["tool_search_dining_menus"]["inputSchema"]["properties"]["query"]["description"]
    )
    assert "부온 프란조" in (
        tools["tool_search_dining_menus"]["inputSchema"]["properties"]["query"]["description"]
    )
    assert "제1자유열람실" in (
        tools["tool_get_library_seat_status"]["inputSchema"]["properties"]["query"]["description"]
    )
    assert "출발 장소" in (
        tools["tool_find_nearby_restaurants"]["inputSchema"]["properties"]["origin"]["description"]
    )
    assert "중도" in (
        tools["tool_find_nearby_restaurants"]["inputSchema"]["properties"]["origin"]["description"]
    )
    assert "김수환관" in (
        tools["tool_list_estimated_empty_classrooms"]["inputSchema"]["properties"]["building"]["description"]
    )
    assert "역곡역" in (
        tools["tool_list_transport_guides"]["inputSchema"]["properties"]["query"]["description"]
    )
    assert "1-12" in (
        tools["tool_list_academic_calendar"]["inputSchema"]["properties"]["month"]["description"]
    )
    assert "return_from_leave" in (
        tools["tool_list_academic_status_guides"]["inputSchema"]["properties"]["status"]["description"]
    )
    assert "bill_lookup" in (
        tools["tool_list_registration_guides"]["inputSchema"]["properties"]["topic"]["description"]
    )
    assert "course_evaluation" in (
        tools["tool_list_class_guides"]["inputSchema"]["properties"]["topic"]["description"]
    )
    assert "seasonal_semester" in (
        tools["tool_list_seasonal_semester_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "grade_evaluation" in (
        tools["tool_list_academic_milestone_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "domestic_credit_exchange" in (
        tools["tool_list_student_exchange_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "exchange_programs" in (
        tools["tool_list_student_exchange_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "latest_notices" in (
        tools["tool_list_dormitory_guides"]["inputSchema"]["properties"]["topic"]["description"]
    )
    assert "유실물" in (
        tools["tool_search_phone_book"]["inputSchema"]["properties"]["query"]["description"]
    )
    assert "student_counseling" in (
        tools["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "disability_support" in (
        tools["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "student_reservist" in (
        tools["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "mobility_safety" in (
        tools["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "facility_rental" in (
        tools["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "hospital_use" in (
        tools["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "최대 결과 수" in (
        tools["tool_list_academic_support_guides"]["inputSchema"]["properties"]["limit"]["description"]
    )
    assert "최대 결과 수" in (
        tools["tool_list_academic_status_guides"]["inputSchema"]["properties"]["limit"]["description"]
    )
    assert "최대 결과 수" in (
        tools["tool_list_registration_guides"]["inputSchema"]["properties"]["limit"]["description"]
    )
    assert "최대 결과 수" in (
        tools["tool_list_class_guides"]["inputSchema"]["properties"]["limit"]["description"]
    )
    assert "최대 결과 수" in (
        tools["tool_list_seasonal_semester_guides"]["inputSchema"]["properties"]["limit"][
            "description"
        ]
    )
    assert "최대 결과 수" in (
        tools["tool_list_academic_milestone_guides"]["inputSchema"]["properties"]["limit"][
            "description"
        ]
    )
    assert "최대 결과 수" in (
        tools["tool_list_certificate_guides"]["inputSchema"]["properties"]["limit"]["description"]
    )
    assert "최대 결과 수" in (
        tools["tool_list_scholarship_guides"]["inputSchema"]["properties"]["limit"]["description"]
    )
    assert "최대 결과 수" in (
        tools["tool_list_wifi_guides"]["inputSchema"]["properties"]["limit"]["description"]
    )
    assert "셔틀" in tools["tool_list_transport_guides"]["description"]

    clear_settings_cache()


def test_mcp_public_prompts_explain_tool_selection_flow(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompt = await mcp.get_prompt(
            "prompt_find_place",
            {"query": "K관"},
        )
        return prompt

    prompt = asyncio.run(main())
    message = prompt.messages[0].content.text

    assert "tool_search_places" in message
    assert "query=K관" in message
    assert "tool_get_place" in message
    assert "songsim://place-categories" in message

    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompt = await mcp.get_prompt(
            "prompt_academic_calendar",
            {"academic_year": 2026, "month": 3, "query": "등록"},
        )
        return prompt

    prompt = asyncio.run(main())
    message = prompt.messages[0].content.text

    assert "tool_list_academic_calendar" in message
    assert "academic_year=2026" in message
    assert "month=3" in message
    assert "query=등록" in message

    clear_settings_cache()


def test_mcp_public_empty_classroom_prompt_explains_estimate_flow(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompt = await mcp.get_prompt(
            "prompt_find_empty_classrooms",
            {"building": "니콜스관"},
        )
        return prompt

    prompt = asyncio.run(main())
    message = prompt.messages[0].content.text

    assert "tool_list_estimated_empty_classrooms" in message
    assert "building=니콜스관" in message
    assert "실시간" in message
    assert "예상 공실" in message
    assert "tool_search_places" in message

    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompt = await mcp.get_prompt(
            "prompt_find_nearby_restaurants",
            {"origin": "central-library", "category": "korean"},
        )
        return prompt

    prompt = asyncio.run(main())
    message = prompt.messages[0].content.text

    assert "tool_find_nearby_restaurants" in message
    assert "origin=central-library" in message
    assert "category=korean" in message
    assert "songsim://usage-guide" in message
    assert "alias" in message

    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompt = await mcp.get_prompt(
            "prompt_search_restaurants",
            {"query": "매머드커피"},
        )
        return prompt

    prompt = asyncio.run(main())
    message = prompt.messages[0].content.text

    assert "tool_search_restaurants" in message
    assert "query=매머드커피" in message
    assert "campus-nearest matches first" in message
    assert "tool_find_nearby_restaurants" not in message

    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        prompt = await mcp.get_prompt(
            "prompt_transport_guide",
            {"query": "지하철", "mode": "subway"},
        )
        return prompt

    prompt = asyncio.run(main())
    message = prompt.messages[0].content.text

    assert "tool_list_transport_guides" in message
    assert "query=지하철" in message
    assert "mode=subway" in message
    assert "셔틀" in message
    assert "빈 결과" in message

    clear_settings_cache()


def test_mcp_public_usage_and_class_period_resources_are_readable(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        usage = list(await mcp.read_resource('songsim://usage-guide'))
        periods = list(await mcp.read_resource('songsim://class-periods'))
        return usage[0].content, periods[0].content

    usage_content, periods_content = asyncio.run(main())
    periods_payload = json.loads(periods_content)

    assert "read-only" in usage_content
    assert "tool_search_places" in usage_content
    assert "tool_search_restaurants" in usage_content
    assert "tool_list_academic_calendar" in usage_content
    assert "tool_list_academic_support_guides" in usage_content
    assert "tool_list_academic_status_guides" in usage_content
    assert "tool_list_registration_guides" in usage_content
    assert "tool_list_class_guides" in usage_content
    assert "tool_list_seasonal_semester_guides" in usage_content
    assert "tool_list_academic_milestone_guides" in usage_content
    assert "tool_list_student_activity_guides" in usage_content
    assert "tool_list_about_resource_guides" in usage_content
    assert "tool_list_student_exchange_guides" in usage_content
    assert "tool_search_student_exchange_partners" in usage_content
    assert "tool_search_phone_book" in usage_content
    assert "tool_list_campus_life_support_guides" in usage_content
    assert "tool_search_pc_software" in usage_content
    assert "tool_list_dormitory_guides" in usage_content
    assert "tool_list_scholarship_guides" in usage_content
    assert "tool_list_leave_of_absence_guides" in usage_content
    assert "tool_list_wifi_guides" in usage_content
    assert "tool_list_estimated_empty_classrooms" in usage_content
    assert "실시간" in usage_content
    assert "tool_find_nearby_restaurants" in usage_content
    assert "예상 공실" in usage_content
    assert "student information questions first" in usage_content
    assert "중도" in usage_content
    assert "가까운 후보를 먼저" in usage_content
    assert "매머드커피" in usage_content
    assert "학점교류 담당 전화번호" in usage_content
    assert "보건실 위치와 운영시간" in usage_content
    assert "학생상담 어디서 받아?" in usage_content
    assert "장애학생지원센터 뭐 해줘?" in usage_content
    assert "예비군 신고 시기 알려줘" in usage_content
    assert "부속병원 이용 안내해줘" in usage_content
    assert "성심교정 대관안내 알려줘" in usage_content
    assert "개인형 이동장치 안전교육 알려줘" in usage_content
    assert "SPSS 설치된 컴퓨터실" in usage_content
    assert "휴복학 문의" in usage_content
    assert "복학 신청 방법" in usage_content
    assert "재입학 지원자격" in usage_content
    assert "학교 규정 어디서 봐?" in usage_content
    assert "학사제도안내책자 보여줘" in usage_content
    assert "등록금 납부 방법" in usage_content
    assert "수업평가 기간" in usage_content
    assert "계절학기 신청 시기" in usage_content
    assert "국내 학점교류 신청대상" in usage_content
    assert "학점교류 신청시기" in usage_content
    assert "교류대학 현황" in usage_content
    assert "교환학생 프로그램" in usage_content
    assert "해외 교류프로그램" in usage_content
    assert "해외협정대학 알려줘" in usage_content
    assert "네덜란드 협정대학 알려줘" in usage_content
    assert "Utrecht University 있어?" in usage_content
    assert "유럽 교류대학 알려줘" in usage_content
    assert "대만 해외협정대학 홈페이지 알려줘" in usage_content
    assert "성심교정 기숙사 안내해줘" in usage_content
    assert "기숙사 입사안내 어디서 봐?" in usage_content
    assert "기숙사 최신 공지 알려줘" in usage_content
    assert "헬스장" in usage_content
    assert "편의점" in usage_content
    assert "/gpt/" not in usage_content
    assert periods_payload[0]["period"] == 1
    assert {"period", "start", "end"} <= set(periods_payload[0].keys())

    clear_settings_cache()


def test_mcp_public_notice_category_resource_returns_canonical_metadata(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        categories = list(await mcp.read_resource('songsim://notice-categories'))
        return categories[0].content

    payload = json.loads(asyncio.run(main()))

    assert payload == [
        {"category": "academic", "category_display": "학사", "aliases": []},
        {"category": "scholarship", "category_display": "장학", "aliases": []},
        {"category": "employment", "category_display": "취업", "aliases": ["career"]},
        {"category": "general", "category_display": "일반", "aliases": ["place"]},
    ]

    clear_settings_cache()


def test_mcp_public_metadata_prompts_explain_direct_metadata_flow(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        categories_prompt = await mcp.get_prompt("prompt_notice_categories", {})
        periods_prompt = await mcp.get_prompt("prompt_class_periods", {})
        seats_prompt = await mcp.get_prompt("prompt_library_seat_status", {})
        notices_prompt = await mcp.get_prompt(
            "prompt_latest_notices",
            {"limit": 5},
        )
        courses_prompt = await mcp.get_prompt(
            "prompt_search_courses",
            {"query": "7교시"},
        )
        dining_prompt = await mcp.get_prompt(
            "prompt_search_dining_menus",
            {"query": "학생식당 메뉴"},
        )
        return (
            categories_prompt.messages[0].content.text,
            periods_prompt.messages[0].content.text,
            seats_prompt.messages[0].content.text,
            notices_prompt.messages[0].content.text,
            courses_prompt.messages[0].content.text,
            dining_prompt.messages[0].content.text,
        )

    (
        categories_message,
        periods_message,
        seats_message,
        notices_message,
        courses_message,
        dining_message,
    ) = asyncio.run(main())

    assert "songsim://notice-categories" in categories_message
    assert "/notice-categories" in categories_message
    assert "employment" in categories_message
    assert "career" in categories_message
    assert "songsim://class-periods" in periods_message
    assert "tool_get_class_periods" in periods_message
    assert "/periods" in periods_message
    assert "tool_get_library_seat_status" in seats_message
    assert "/library-seats" in seats_message
    assert "songsim://notice-categories" in notices_message
    assert "/notice-categories" in notices_message
    assert "songsim://class-periods" in courses_message
    assert "period_start" in courses_message
    assert "/periods" in courses_message
    assert "tool_search_dining_menus" in dining_message
    assert "학생식당 메뉴" in dining_message
    assert "카페 보나" in dining_message

    clear_settings_cache()


def test_mcp_public_search_places_returns_condensed_place_payload(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool('tool_search_places', {'query': '중앙도서관', 'limit': 1})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["slug"] == "central-library"
    assert payload["name"] == "중앙도서관"
    assert payload["canonical_name"] == "중앙도서관"
    assert payload["aliases"] == ["도서관", "중도"]
    assert payload["coordinates"] == {"latitude": 37.48643, "longitude": 126.80164}
    assert payload["short_location"] == "자료 열람과 시험기간 공부에 쓰는 중심 공간"
    assert payload["highlights"][0] == "별칭: 도서관, 중도"
    assert "description" not in payload
    assert "opening_hours" not in payload

    clear_settings_cache()


def test_mcp_public_search_courses_tool_accepts_period_start(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_search_courses',
            {'year': 2026, 'semester': 1, 'period_start': 7, 'limit': 5},
        )
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert [item["code"] for item in payload] == ["CSE401"]
    assert all(item["period_start"] == 7 for item in payload)

    clear_settings_cache()


def test_mcp_search_courses_recovers_alias_and_keeps_watchlist_empty(
    app_env,
    monkeypatch,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE420",
                    "title": "임베디드시스템",
                    "professor": "담당교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 7,
                    "period_end": 8,
                    "room": "N401",
                    "raw_schedule": "월7~8(N401)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "MTH101",
                    "title": "데이터베이스활용",
                    "professor": "담당교수",
                    "department": "테스트학과",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 3,
                    "period_end": 4,
                    "room": "M101",
                    "raw_schedule": "월3~4(M101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "BIO102",
                    "title": "분자생물학개론",
                    "professor": "박요셉",
                    "department": "자연과학계열",
                    "section": "01",
                    "day_of_week": "화",
                    "period_start": 1,
                    "period_end": 2,
                    "room": "S201",
                    "raw_schedule": "화1~2(S201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        return {
            "typo": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "데이타베이스", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
            "spaced_title": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "데 이 터 베 이 스", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
            "spaced_code": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "CSE 420", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
            "dashed_code": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "CSE-420", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
            "mixed_case_code": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "cSe 420", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
            "spaced_professor": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "박 요 셉", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
            "source_gap_code": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "CSE301", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
            "source_gap_professor": _tool_payloads(
                await mcp.call_tool(
                    "tool_search_courses",
                    {"query": "김가톨", "year": 2026, "semester": 1, "limit": 5},
                )
            ),
        }

    payload = asyncio.run(main())

    assert [item["code"] for item in payload["typo"]] == ["MTH101"]
    assert [item["code"] for item in payload["spaced_title"]] == ["MTH101"]
    assert [item["code"] for item in payload["spaced_code"]] == ["CSE420"]
    assert [item["code"] for item in payload["dashed_code"]] == ["CSE420"]
    assert [item["code"] for item in payload["mixed_case_code"]] == ["CSE420"]
    assert [item["code"] for item in payload["spaced_professor"]] == ["BIO102"]
    assert payload["source_gap_code"] == []
    assert payload["source_gap_professor"] == []

    clear_settings_cache()


def test_mcp_public_library_seat_tool_returns_live_room_payload(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    class McpLibrarySeatStatusSource:
        def fetch(self):
            return "<seat-status></seat-status>"

        def parse(self, html: str, *, fetched_at: str):
            assert html == "<seat-status></seat-status>"
            return [
                {
                    "room_name": "제1자유열람실",
                    "remaining_seats": 28,
                    "occupied_seats": 72,
                    "total_seats": 100,
                    "source_url": "http://203.229.203.240/8080/Domian5.asp",
                    "source_tag": "cuk_library_seat_status",
                    "last_synced_at": fetched_at,
                }
            ]

    monkeypatch.setattr(
        "songsim_campus.services.LibrarySeatStatusSource",
        McpLibrarySeatStatusSource,
    )

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            "tool_get_library_seat_status",
            {"query": "제1자유열람실 남은 좌석"},
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["availability_mode"] == "live"
    assert payload["rooms"][0]["room_name"] == "제1자유열람실"
    assert payload["rooms"][0]["remaining_seats"] == 28

    clear_settings_cache()


def test_mcp_public_search_dining_menus_returns_weekly_menu_payload(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_campus_dining_menus(
            conn,
            [
                {
                    "venue_slug": "cafe-bona",
                    "venue_name": "Café Bona 카페 보나",
                    "place_slug": "student-center",
                    "place_name": "학생회관",
                    "week_label": "3월 3주차 메뉴표 확인하기",
                    "week_start": "2026-03-16",
                    "week_end": "2026-03-20",
                    "menu_text": "Weekly Menu 2026.03.16 - 03.20\nBulgogi Rice Bowl\nLemon Tea",
                    "source_url": "https://www.catholic.ac.kr/menu/bona.pdf",
                    "source_tag": "cuk_facilities_menu",
                    "last_synced_at": "2026-03-16T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool('tool_search_dining_menus', {'query': '카페 보나 메뉴'})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["venue_name"] == "Café Bona 카페 보나"
    assert payload["place_name"] == "학생회관"
    assert payload["week_label"] == "3월 3주차 메뉴표 확인하기"
    assert payload["source_url"] == "https://www.catholic.ac.kr/menu/bona.pdf"
    assert "Bulgogi Rice Bowl" in payload["menu_text"]

    clear_settings_cache()


def test_mcp_public_search_places_supports_facility_tenant_alias(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool('tool_search_places', {'query': '트러스트짐', 'limit': 1})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["slug"] == "student-center"
    assert payload["name"] == "학생회관"

    clear_settings_cache()


def test_mcp_public_search_places_supports_generic_facility_nouns(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학회관"],
                    "description": "학생 편의시설이 많은 건물",
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "opening_hours": {
                        "트러스트짐": "평일 07:00~22:30",
                        "편의점": "상시 07:00~24:00",
                        "교내복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                    },
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {
                        "이마트24 K관점": "상시 07:00~24:00",
                    },
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "복사실",
                    "category": "복사실",
                    "phone": "02-2164-4725",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:50~19:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 09:00~16:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "카페드림",
                    "category": "카페",
                    "phone": "010-9517-9417",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~22:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 07:00~22:30",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "복사실",
                    "category": "복사실",
                    "phone": "02-2164-4725",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:50~19:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 09:00~16:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "카페드림",
                    "category": "카페",
                    "phone": "010-9517-9417",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~22:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 07:00~22:30",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "복사실",
                    "category": "복사실",
                    "phone": "02-2164-4725",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:50~19:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 09:00~16:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "카페드림",
                    "category": "카페",
                    "phone": "010-9517-9417",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~22:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 07:00~22:30",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()


def test_mcp_public_search_places_returns_matched_facility_metadata(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학회관", "트러스트짐"],
                    "description": "학생 편의시설과 복사/은행/카페가 있는 공간",
                    "opening_hours": {
                        "복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                        "카페드림": "평일 08:00~22:00",
                        "트러스트짐": "평일 07:00~22:30",
                    },
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "central-library",
                    "name": "중앙도서관",
                    "category": "library",
                    "aliases": ["중도"],
                    "description": "자료 열람과 시험 준비를 위한 핵심 공간",
                    "latitude": 37.48643,
                    "longitude": 126.80164,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "복사실",
                    "category": "복사실",
                    "phone": "02-2164-4725",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:50~19:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 09:00~16:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "카페드림",
                    "category": "카페",
                    "phone": "010-9517-9417",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~22:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 07:00~22:30",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "CU",
                    "category": "편의점",
                    "phone": "032-343-3424",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~21:30 토,일 08:00~16:00 (야간 무인으로 24시간 운영)",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "facility_name": "이마트24",
                    "category": "편의점",
                    "phone": "070-8808-1315",
                    "location_text": "K관 1층",
                    "hours_text": "상시 07:00~24:00",
                    "place_slug": "dormitory-stephen",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    facility_queries = [
        "복사실이 어디야?",
        "우리은행 전화번호 알려줘",
        "카페드림 어디야?",
        "트러스트짐 어디야?",
    ]

    async def main():
        mcp = build_mcp()
        facility_payloads = []
        for query in facility_queries:
            payload = await mcp.call_tool('tool_search_places', {'query': query, 'limit': 1})
            facility_payloads.append(_tool_payloads(payload)[0])
        library_payload = _tool_payloads(
            await mcp.call_tool('tool_search_places', {'query': '중앙도서관이 어디야?', 'limit': 1})
        )[0]
        return facility_payloads, library_payload

    facility_payloads, library_payload = asyncio.run(main())

    assert all(item['slug'] == 'student-center' for item in facility_payloads)
    assert all('matched_facility' in item for item in facility_payloads)
    assert [item['matched_facility'].get('name') for item in facility_payloads] == [
        '복사실',
        '우리은행',
        '카페드림',
        '트러스트짐',
    ]
    assert facility_payloads[1]['matched_facility'].get('phone') == '032-342-2641'
    assert facility_payloads[2]['matched_facility'].get('location_hint') == '학생회관 1층'
    assert 'matched_facility' not in library_payload

    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        gym = await mcp.call_tool('tool_search_places', {'query': '헬스장', 'limit': 5})
        store = await mcp.call_tool('tool_search_places', {'query': '편의점', 'limit': 5})
        copy_room = await mcp.call_tool('tool_search_places', {'query': '복사실', 'limit': 5})
        atm = await mcp.call_tool('tool_search_places', {'query': 'ATM', 'limit': 5})
        return (
            _tool_payloads(gym),
            _tool_payloads(store),
            _tool_payloads(copy_room),
            _tool_payloads(atm),
        )

    gym_payloads, store_payloads, copy_payloads, atm_payloads = asyncio.run(main())

    assert [item["slug"] for item in gym_payloads] == ["student-center"]
    assert [item["slug"] for item in store_payloads[:2]] == ["student-center", "dormitory-stephen"]
    assert [item["slug"] for item in copy_payloads] == ["student-center"]
    assert [item["slug"] for item in atm_payloads] == ["student-center"]
    assert gym_payloads[0]["matched_facility"]["location_hint"] == "학생회관 1층"
    assert store_payloads[0]["matched_facility"]["location_hint"] == "학생회관 1층"
    assert copy_payloads[0]["matched_facility"]["location_hint"] == "학생회관 1층"
    assert atm_payloads[0]["matched_facility"]["location_hint"] == "학생회관 1층"

    clear_settings_cache()


def test_mcp_places_tool_populates_generic_facility_metadata_when_place_alias_matches(
    app_env,
    monkeypatch,
):
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["편의점"],
                    "description": "학생 편의시설과 복사/은행/카페가 있는 공간",
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "학생회관 편의점",
                    "category": None,
                    "phone": None,
                    "location_text": "학생회관 1층",
                    "hours_text": "상시 07:00~24:00",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        payload = await mcp.call_tool("tool_search_places", {"query": "편의점", "limit": 1})
        return _tool_payloads(payload)[0]

    payload = asyncio.run(main())

    assert payload["slug"] == "student-center"
    assert payload["matched_facility"]["name"] == "학생회관 편의점"
    assert payload["matched_facility"]["location_hint"] == "학생회관 1층"
    assert payload["matched_facility"]["opening_hours"] == "상시 07:00~24:00"

    clear_settings_cache()


def test_mcp_public_search_places_matches_student_center_composite_facility_queries(
    app_env,
    monkeypatch,
):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학회관", "트러스트짐"],
                    "description": "학생 편의시설과 복사/은행/카페가 있는 공간",
                    "opening_hours": {
                        "복사실": "평일 08:50~19:00",
                        "우리은행": "평일 09:00~16:00",
                        "카페드림": "평일 08:00~22:00",
                        "트러스트짐": "평일 07:00~22:30",
                    },
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "CU",
                    "category": "편의점",
                    "phone": "032-343-3424",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~21:30 토,일 08:00~16:00 (야간 무인으로 24시간 운영)",
                    "place_slug": "student-center",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        results = []
        for query in ("학생회관 1층 편의점 어디야?", "학생회관 1층 24시간 편의점 어디야?"):
            payload = await mcp.call_tool("tool_search_places", {"query": query, "limit": 1})
            results.append(_tool_payloads(payload)[0])
        return results

    payloads = asyncio.run(main())

    assert all(item["slug"] == "student-center" for item in payloads)
    assert all(item["name"] == "학생회관" for item in payloads)
    assert all(item["canonical_name"] == "학생회관" for item in payloads)
    assert all(item["matched_facility"]["name"] == "CU" for item in payloads)
    assert all(item["matched_facility"]["location_hint"] == "학생회관 1층" for item in payloads)

    clear_settings_cache()


def test_mcp_public_search_places_laundry_generic_query_ordering(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    shared_hours = {
        "이마트24": "상시 07:00~24:00",
        "교내복사실": "평일 08:50~19:00",
        "우리은행": "평일 09:00~16:00",
        "트러스트짐": "평일 07:00~22:30",
        "세탁소": "평일 09:00~18:00",
    }
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "opening_hours": shared_hours,
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["K관"],
                    "description": "강의동과 생활편의시설이 함께 있는 건물",
                    "opening_hours": shared_hours,
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "student-center",
                    "name": "학생회관",
                    "category": "facility",
                    "aliases": ["학생센터"],
                    "description": "학생 편의시설이 많은 건물",
                    "opening_hours": shared_hours,
                    "latitude": 37.48652,
                    "longitude": 126.80216,
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        payload = await mcp.call_tool("tool_search_places", {"query": "세탁소", "limit": 5})
        return _tool_payloads(payload)

    payloads = asyncio.run(main())

    assert [item["slug"] for item in payloads[:3]] == [
        "kim-sou-hwan-hall",
        "student-center",
        "dormitory-stephen",
    ]
    assert payloads[0]["matched_facility"]["name"] == "세탁소"
    assert payloads[0]["matched_facility"]["location_hint"] == "김수환관"
    assert payloads[0]["matched_facility"]["opening_hours"] == "평일 09:00~18:00"

    clear_settings_cache()


def test_mcp_public_search_places_prefers_short_query_place_preference_for_k_hall(
    app_env,
    monkeypatch,
):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool("tool_search_places", {"query": "K관", "limit": 10})
        return _tool_payloads(result)

    payloads = asyncio.run(main())

    assert [item["slug"] for item in payloads] == ["kim-sou-hwan-hall"]
    assert payloads[0]["name"] == "K관"
    assert payloads[0]["canonical_name"] == "김수환관"

    clear_settings_cache()


@pytest.mark.parametrize(
    "query,expected_slug,expected_name,expected_canonical_name",
    [
        ("학생회관 어디야?", "sophie-barat-hall", "학생회관", "학생미래인재관"),
        ("K관 어디야?", "kim-sou-hwan-hall", "K관", "김수환관"),
        ("김수환관 어디야?", "kim-sou-hwan-hall", "김수환관", "김수환관"),
    ],
)
def test_mcp_public_search_places_exposes_alias_friendly_display_for_strong_alias_queries(
    app_env,
    monkeypatch,
    query,
    expected_slug,
    expected_name,
    expected_canonical_name,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "sophie-barat-hall",
                    "name": "학생미래인재관",
                    "category": "building",
                    "aliases": ["학생회관", "학생센터"],
                    "description": "학생식당과 생활 편의시설이 있는 건물",
                    "latitude": 37.486466,
                    "longitude": 126.801297,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 생활 편의시설이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool("tool_search_places", {"query": query, "limit": 1})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["slug"] == expected_slug
    assert payload["name"] == expected_name
    assert payload["canonical_name"] == expected_canonical_name

    clear_settings_cache()


def test_mcp_public_search_places_uses_alias_friendly_parent_place_for_facility_hits(
    app_env,
    monkeypatch,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "sophie-barat-hall",
                    "name": "학생미래인재관",
                    "category": "building",
                    "aliases": ["학생회관", "학생센터"],
                    "description": "학생식당과 생활 편의시설이 있는 건물",
                    "latitude": 37.486466,
                    "longitude": 126.801297,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "CU",
                    "category": "편의점",
                    "phone": "032-343-3424",
                    "location_text": "학생회관 1층",
                    "hours_text": "평일 08:00~21:30 토,일 08:00~16:00 (야간 무인으로 24시간 운영)",
                    "place_slug": "sophie-barat-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool("tool_search_places", {"query": "CU 어디야?", "limit": 1})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["slug"] == "sophie-barat-hall"
    assert payload["name"] == "학생회관"
    assert payload["canonical_name"] == "학생미래인재관"
    assert payload["matched_facility"]["name"] == "CU"
    assert payload["matched_facility"]["location_hint"] == "학생회관 1층"

    clear_settings_cache()


def test_mcp_public_search_places_promotes_canonical_parent_place_for_k_hall_facilities(
    app_env,
    monkeypatch,
):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_campus_facilities(
            conn,
            [
                {
                    "facility_name": "교내복사실",
                    "category": "복사실",
                    "phone": "02-2164-4725",
                    "location_text": "K관 1층",
                    "hours_text": "평일 08:50~19:00 (토/일/공휴일휴무)",
                    "place_slug": "kim-sou-hwan-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "facility_name": "우리은행",
                    "category": "은행",
                    "phone": "032-342-2641",
                    "location_text": "K관 1층",
                    "hours_text": "평일 09:00~16:00 (토,일/공휴일휴무)",
                    "place_slug": "kim-sou-hwan-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
                {
                    "facility_name": "트러스트짐",
                    "category": "피트니스센터",
                    "phone": "032-342-5406",
                    "location_text": "K관 1층",
                    "hours_text": "평일 07:00~22:30 토 09:30~18:00 (일/공휴일휴무)",
                    "place_slug": "kim-sou-hwan-hall",
                    "source_url": "https://www.catholic.ac.kr/ko/campuslife/restaurant.do",
                    "source_tag": "cuk_facilities",
                    "last_synced_at": "2026-03-18T10:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        copy_room = _tool_payloads(
            await mcp.call_tool("tool_search_places", {"query": "복사실이 어디야?", "limit": 1})
        )[0]
        bank = _tool_payloads(
            await mcp.call_tool(
                "tool_search_places",
                {"query": "우리은행 전화번호 알려줘", "limit": 1},
            )
        )[0]
        gym = _tool_payloads(
            await mcp.call_tool("tool_search_places", {"query": "트러스트짐 어디야?", "limit": 1})
        )[0]
        hall = _tool_payloads(
            await mcp.call_tool("tool_search_places", {"query": "K관 어디야?", "limit": 1})
        )[0]
        return copy_room, bank, gym, hall

    copy_room_payload, bank_payload, gym_payload, hall_payload = asyncio.run(main())

    assert copy_room_payload["slug"] == "kim-sou-hwan-hall"
    assert copy_room_payload["name"] == "K관"
    assert copy_room_payload["canonical_name"] == "김수환관"
    assert copy_room_payload["matched_facility"]["name"] == "교내복사실"
    assert copy_room_payload["matched_facility"]["location_hint"] == "K관 1층"

    assert bank_payload["slug"] == "kim-sou-hwan-hall"
    assert bank_payload["name"] == "K관"
    assert bank_payload["canonical_name"] == "김수환관"
    assert bank_payload["matched_facility"]["name"] == "우리은행"
    assert bank_payload["matched_facility"]["phone"] == "032-342-2641"

    assert gym_payload["slug"] == "kim-sou-hwan-hall"
    assert gym_payload["name"] == "K관"
    assert gym_payload["canonical_name"] == "김수환관"
    assert gym_payload["matched_facility"]["name"] == "트러스트짐"

    assert hall_payload["slug"] == "kim-sou-hwan-hall"
    assert hall_payload["name"] == "K관"
    assert hall_payload["canonical_name"] == "김수환관"
    assert "matched_facility" not in hall_payload

    clear_settings_cache()


def test_mcp_public_search_restaurants_returns_compact_brand_match(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "mammoth",
                    "name": "매머드익스프레스 부천가톨릭대학교점",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48556,
                    "longitude": 126.80379,
                    "tags": ["커피전문점", "매머드익스프레스"],
                    "description": "경기 부천시 원미구 지봉로 43",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-15T01:19:14+00:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool('tool_search_restaurants', {'query': '매머드커피', 'limit': 5})
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert payload == [
        {
            "name": "매머드익스프레스 부천가톨릭대학교점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 지봉로 43",
        }
    ]

    clear_settings_cache()


def test_mcp_public_search_restaurants_uses_live_fallback(app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class McpBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "매머드익스프레스"
            from songsim_campus.services import KakaoPlace

            return [
                KakaoPlace(
                    name="매머드익스프레스 가상의외부점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 소사구 경인옛로 37",
                    latitude=37.48186,
                    longitude=126.79612,
                    place_id="201",
                    place_url="https://place.map.kakao.com/201",
                ),
                KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", McpBrandKakaoClient)

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool("tool_search_restaurants", {"query": "매머드커피", "limit": 5})
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert payload[:2] == [
        {
            "name": "매머드익스프레스 부천가톨릭대학교점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 지봉로 43",
        },
        {
            "name": "매머드익스프레스 가상의외부점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 소사구 경인옛로 37",
        }
    ]

    clear_settings_cache()


def test_mcp_public_search_restaurants_with_origin_returns_distance_fields(
    app_env,
    monkeypatch,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class McpOriginAwareBrandClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "매머드익스프레스"
            assert x is not None and y is not None
            assert radius == 15 * 75
            from songsim_campus.services import KakaoPlace

            return [
                KakaoPlace(
                    name="매머드익스프레스 부천가톨릭대학교점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 43",
                    latitude=37.48556,
                    longitude=126.80379,
                    place_id="101",
                    place_url="https://place.map.kakao.com/101",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", McpOriginAwareBrandClient)

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            "tool_search_restaurants",
            {"query": "매머드커피", "origin": "중도", "limit": 5},
        )
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert payload == [
        {
            "name": "매머드익스프레스 부천가톨릭대학교점",
            "category_display": "카페",
            "distance_meters": payload[0]["distance_meters"],
            "estimated_walk_minutes": payload[0]["estimated_walk_minutes"],
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 지봉로 43",
        }
    ]
    assert payload[0]["distance_meters"] is not None
    assert payload[0]["estimated_walk_minutes"] is not None

    clear_settings_cache()


def test_mcp_public_search_restaurants_expands_radius_for_long_tail_brand(
    app_env,
    monkeypatch,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()
    calls: list[int] = []

    class McpBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "커피빈"
            assert x is not None and y is not None
            calls.append(radius)
            from songsim_campus.services import KakaoPlace

            if radius == 15 * 75:
                return []
            assert radius == 5000
            return [
                KakaoPlace(
                    name="커피빈 역곡점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 원미구 지봉로 70",
                    latitude=37.48621,
                    longitude=126.80491,
                    place_id="904",
                    place_url="https://place.map.kakao.com/904",
                )
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", McpBrandKakaoClient)

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool("tool_search_restaurants", {"query": "커피빈", "limit": 5})
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert calls == [15 * 75, 5000]
    assert payload == [
        {
            "name": "커피빈 역곡점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 원미구 지봉로 70",
        }
    ]

    clear_settings_cache()


def test_mcp_public_search_restaurants_filters_brand_noise_candidates(app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    monkeypatch.setenv("SONGSIM_KAKAO_REST_API_KEY", "test-key")
    clear_settings_cache()

    class McpBrandKakaoClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search_sync(self, query: str, *, x=None, y=None, radius: int = 1000):
            assert query == "스타벅스"
            from songsim_campus.services import KakaoPlace

            return [
                KakaoPlace(
                    name="스타벅스 역곡역DT점 주차장",
                    category="교통시설 > 주차장",
                    address="경기 부천시 소사구 괴안동 112-25",
                    latitude=37.48345,
                    longitude=126.80935,
                    place_id="902",
                    place_url="https://place.map.kakao.com/902",
                ),
                KakaoPlace(
                    name="스타벅스 역곡역DT점",
                    category="음식점 > 카페 > 커피전문점",
                    address="경기 부천시 소사구 경인로 485",
                    latitude=37.48354,
                    longitude=126.80929,
                    place_id="903",
                    place_url="https://place.map.kakao.com/903",
                ),
            ]

    monkeypatch.setattr("songsim_campus.services.KakaoLocalClient", McpBrandKakaoClient)

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool("tool_search_restaurants", {"query": "스타벅스", "limit": 5})
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert payload == [
        {
            "name": "스타벅스 역곡역DT점",
            "category_display": "카페",
            "distance_meters": None,
            "estimated_walk_minutes": None,
            "price_hint": None,
            "location_hint": "경기 부천시 소사구 경인로 485",
        }
    ]

    clear_settings_cache()


def test_mcp_public_notices_return_category_display_and_summary_preview(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_notices(
            conn,
            [
                {
                    "title": "2026학년도 1학기 장학 신청 안내",
                    "category": "scholarship",
                    "published_at": "2026-03-13",
                    "summary": "장학 신청 대상, 제출 서류, 신청 기한을 자세히 안내합니다. " * 10,
                    "labels": ["장학", "학부"],
                    "source_url": "https://example.com/notices/1",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool('tool_list_latest_notices', {'limit': 1})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["title"] == "2026학년도 1학기 장학 신청 안내"
    assert payload["category_display"] == "장학"
    assert payload["source_url"] == "https://example.com/notices/1"
    assert len(payload["summary"]) <= 160
    assert payload["summary"].endswith("...")
    assert "category" not in payload
    assert "labels" not in payload

    clear_settings_cache()


def test_mcp_public_affiliated_notices_return_topic_and_summary_preview(
    app_env,
    monkeypatch,
):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    class DuplicateAffiliatedNoticeSource:
        topic = "international_studies"
        source_tag = "cuk_affiliated_notice_boards"

        def fetch_list(self, offset: int = 0, limit: int = 10):
            return "<list></list>"

        def parse_list(self, _html: str):
            return [
                {
                    "topic": self.topic,
                    "article_no": "100",
                    "title": "국제학부 공지",
                    "published_at": "2026-03-20",
                    "summary": "국제학부 학사 공지 " * 20,
                    "source_url": "https://is.catholic.ac.kr/is/community/notice.do?mode=view&articleNo=100",
                    "source_tag": self.source_tag,
                },
                {
                    "topic": self.topic,
                    "article_no": "100",
                    "title": "국제학부 공지",
                    "published_at": "2026-03-20",
                    "summary": "중복 공지",
                    "source_url": "https://is.catholic.ac.kr/is/community/notice.do?mode=view&articleNo=100",
                    "source_tag": self.source_tag,
                },
                {
                    "topic": self.topic,
                    "article_no": "101",
                    "title": "국제학부 공결 신청 안내",
                    "published_at": "2026-03-19",
                    "summary": "국제학부 공결 신청 안내 " * 20,
                    "source_url": "https://is.catholic.ac.kr/is/community/notice.do?mode=view&articleNo=101",
                    "source_tag": self.source_tag,
                },
            ]

        def fetch_detail(self, article_no: str, offset: int = 0, limit: int = 10):
            return article_no

        def parse_detail(
            self,
            article_no: str,
            *,
            default_title: str = "",
            default_category: str = "",
            default_summary: str = "",
            default_published_at: str = "",
            default_source_url: str | None = None,
        ):
            return {
                "topic": self.topic,
                "title": default_title,
                "published_at": default_published_at,
                "summary": default_summary,
                "source_url": default_source_url,
                "source_tag": self.source_tag,
            }

    with connection() as conn:
        refresh_affiliated_notices_from_sources(
            conn,
            sources=[DuplicateAffiliatedNoticeSource()],
            fetched_at="2026-03-20T10:00:00+09:00",
        )

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            "tool_list_affiliated_notices",
            {"topic": "international_studies", "limit": 5},
        )
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert len(payload) == 2
    titles = [item["title"] for item in payload]
    assert titles == ["국제학부 공지", "국제학부 공결 신청 안내"]
    assert len(titles) == len(set(titles)) == 2
    assert payload[0]["topic"] == "international_studies"
    assert payload[0]["source_tag"] == "cuk_affiliated_notice_boards"
    assert len(payload[0]["summary"]) <= 160
    assert payload[0]["summary"].endswith("...")

    clear_settings_cache()


def test_mcp_public_campus_life_notices_return_outside_agency_topic(
    app_env,
    monkeypatch,
):
    pytest.importorskip('mcp.server.fastmcp')
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    def stub(conn=None, topic=None, query=None, limit=20):  # noqa: ANN001
        outside_agency = CampusLifeNotice(
            id=269665,
            topic="outside_agencies",
            title="[인천병무지청] 2026년 4월 각 군 모집일정 안내",
            published_at="2026-03-20",
            summary=(
                "접수기간: 2026.3.27.(금) 14시 ~ 2026.4.2.(목) 14시 "
                "지원방법: 병무청 누리집"
            ),
            source_url="https://www.catholic.ac.kr/ko/campuslife/notice_outside.do?mode=view&articleNo=269665&article.offset=0&articleLimit=10",
            source_tag="cuk_campus_life_notices",
            last_synced_at="2026-03-20T10:00:00+09:00",
        )
        event = CampusLifeNotice(
            id=266521,
            topic="events",
            title="[음악과] 『개교 170주년 기념』성심 오케스트라 연주회",
            published_at="2025-11-28",
            summary=(
                "음악과에서 『개교 170주년 기념』성심 오케스트라 연주회를 개최하오니 "
                "많은 관심과 참여 부탁드립니다."
            ),
            source_url="https://www.catholic.ac.kr/ko/campuslife/notice_event.do?mode=view&articleNo=266521&article.offset=0&articleLimit=16",
            source_tag="cuk_campus_life_notices",
            last_synced_at="2026-03-20T10:00:00+09:00",
        )
        if topic == "events":
            return [event]
        if topic is None:
            return [outside_agency, event]
        return [outside_agency]
    monkeypatch.setattr("songsim_campus.mcp_public_catalog.list_campus_life_notices", stub)
    monkeypatch.setattr("songsim_campus.mcp_tool_catalog.list_campus_life_notices", stub)

    async def main():
        mcp = build_mcp()
        resource = await mcp.read_resource("songsim://campus-life-notices")
        result = await mcp.call_tool(
            "tool_list_campus_life_notices",
            {"query": "외부기관공지", "limit": 5},
        )
        return list(resource), _tool_payloads(result)

    resource_payload, tool_payload = asyncio.run(main())
    resource_payload = json.loads(resource_payload[0].content)

    assert resource_payload[0]["topic"] == "outside_agencies"
    assert resource_payload[0]["source_tag"] == "cuk_campus_life_notices"
    assert resource_payload[1]["topic"] == "events"
    assert tool_payload[0]["topic"] == "outside_agencies"
    assert tool_payload[0]["source_tag"] == "cuk_campus_life_notices"
    assert tool_payload[0]["title"] == "[인천병무지청] 2026년 4월 각 군 모집일정 안내"

    async def events_main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            "tool_list_campus_life_notices",
            {"topic": "events", "limit": 5},
        )
        return _tool_payloads(result)

    event_tool_payload = asyncio.run(events_main())

    assert event_tool_payload[0]["topic"] == "events"
    assert event_tool_payload[0]["source_tag"] == "cuk_campus_life_notices"
    assert event_tool_payload[0]["title"] == "[음악과] 『개교 170주년 기념』성심 오케스트라 연주회"

    clear_settings_cache()


def test_mcp_public_notices_display_legacy_career_as_employment(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_notices(
            conn,
            [
                {
                    "title": "진로취업상담 안내",
                    "category": "career",
                    "published_at": "2026-03-13",
                    "summary": "취업 상담 일정",
                    "labels": ["취업"],
                    "source_url": "https://example.com/notices/career",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_list_latest_notices',
            {'category': 'employment', 'limit': 1},
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["title"] == "진로취업상담 안내"
    assert payload["category_display"] == "취업"

    clear_settings_cache()


def test_mcp_public_notices_display_place_as_general(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_notices(
            conn,
            [
                {
                    "title": "중앙도서관 자리 안내",
                    "category": "place",
                    "published_at": "2026-03-13",
                    "summary": "도서관 좌석 안내",
                    "labels": ["도서관"],
                    "source_url": "https://example.com/notices/place",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool('tool_list_latest_notices', {'limit': 1})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["title"] == "중앙도서관 자리 안내"
    assert payload["category_display"] == "일반"

    clear_settings_cache()


def test_mcp_public_search_places_normalizes_spacing_variants(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool('tool_search_places', {'query': '중앙 도서관', 'limit': 1})
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["slug"] == "central-library"
    assert payload["name"] == "중앙도서관"

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_return_condensed_payload(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': 'central-library', 'limit': 1},
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert isinstance(payload["category_display"], str)
    assert payload["category_display"]
    assert "distance_meters" in payload
    assert "estimated_walk_minutes" in payload
    assert "open_now" in payload
    assert "location_hint" in payload
    assert "description" not in payload
    assert "tags" not in payload

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_accept_origin_alias(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        alias_result = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': '중도', 'limit': 1},
        )
        slug_result = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': 'central-library', 'limit': 1},
        )
        return _tool_payloads(alias_result)[0], _tool_payloads(slug_result)[0]

    alias_payload, slug_payload = asyncio.run(main())

    assert alias_payload["name"] == slug_payload["name"]
    assert alias_payload["category_display"] == slug_payload["category_display"]

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_accept_facility_alias_origin(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        alias_result = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': '학생식당', 'limit': 1},
        )
        slug_result = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': 'student-center', 'limit': 1},
        )
        return _tool_payloads(alias_result)[0], _tool_payloads(slug_result)[0]

    alias_payload, slug_payload = asyncio.run(main())

    assert alias_payload["name"] == slug_payload["name"]
    assert alias_payload["category_display"] == slug_payload["category_display"]

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_prefers_short_query_origin_preference_for_k_hall(
    app_env,
    monkeypatch,
):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "dormitory-stephen",
                    "name": "스테파노기숙사",
                    "category": "dormitory",
                    "aliases": ["K관"],
                    "description": "기숙사 생활시설 건물",
                    "latitude": 37.48516,
                    "longitude": 126.80323,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "kim-sou-hwan-hall",
                    "name": "김수환관",
                    "category": "building",
                    "aliases": ["김수환", "K관"],
                    "description": "강의실과 연구실이 있는 건물",
                    "latitude": 37.48630,
                    "longitude": 126.80120,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
        replace_restaurants(
            conn,
            [
                {
                    "slug": "k-hall-cafe",
                    "name": "K관카페",
                    "category": "cafe",
                    "min_price": 5000,
                    "max_price": 6000,
                    "latitude": 37.48631,
                    "longitude": 126.80121,
                    "tags": ["카페"],
                    "description": "김수환관 앞",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            "tool_find_nearby_restaurants",
            {"origin": "K관", "walk_minutes": 5, "limit": 3},
        )
        return _tool_payloads(result)

    payloads = asyncio.run(main())

    assert [item["name"] for item in payloads] == ["K관카페"]

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_budget_max_requires_price_evidence(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "budget-kimbap",
                    "name": "버짓김밥",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.48653,
                    "longitude": 126.80174,
                    "tags": ["한식"],
                    "description": "가격 정보가 있는 김밥집",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "slug": "mystery-price-cafe",
                    "name": "가격미상카페",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48663,
                    "longitude": 126.80184,
                    "tags": ["카페"],
                    "description": "가격 정보가 없는 후보",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': 'central-library', 'budget_max': 10000, 'walk_minutes': 15},
        )
        return _tool_payloads(result)

    payload = asyncio.run(main())

    assert [item["name"] for item in payload] == ["버짓김밥"]

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_can_filter_open_now_for_late_night_hours(
    app_env,
    monkeypatch,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "night-snack",
                    "name": "야식분식",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.4869,
                    "longitude": 126.7999,
                    "tags": ["한식"],
                    "description": "야간 운영 테스트 식당",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"야식분식": "23:00~02:00"},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            "tool_find_nearby_restaurants",
            {
                "origin": "central-library",
                "open_now": True,
                "at": "2026-03-16T23:30:00+09:00",
            },
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["name"] == "야식분식"
    assert payload["open_now"] is True

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_return_structured_error_for_missing_origin(
    app_env,
    monkeypatch,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_restaurants(
            conn,
            [
                {
                    "slug": "test-bap",
                    "name": "테스트백반",
                    "category": "korean",
                    "min_price": 7000,
                    "max_price": 9000,
                    "latitude": 37.4866,
                    "longitude": 126.8018,
                    "tags": ["한식"],
                    "description": "테스트 식당",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        missing_origin = await mcp.call_tool(
            "tool_find_nearby_restaurants",
            {"origin": "does-not-exist", "limit": 1},
        )
        return _tool_payloads(missing_origin)[0]

    missing_origin_payload = asyncio.run(main())

    assert missing_origin_payload["type"] == "not_found"
    assert missing_origin_payload["error"] == missing_origin_payload["message"]
    assert "Origin place not found" in missing_origin_payload["message"]

    clear_settings_cache()


def test_mcp_public_nearby_restaurants_prefer_official_facility_hours_before_kakao_detail(
    app_env,
    monkeypatch,
):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()
    calls = {"detail": 0}
    monkeypatch.setattr(
        "songsim_campus.services._now",
        lambda: datetime.fromisoformat("2026-03-14T12:00:00+09:00"),
    )

    class ExplodingDetailClient:
        def fetch_sync(self, place_id: str):
            calls["detail"] += 1
            raise AssertionError("detail client should not be used for official facility matches")

    monkeypatch.setattr("songsim_campus.services.KakaoPlaceDetailClient", ExplodingDetailClient)
    with connection() as conn:
        replace_places(
            conn,
            [
                {
                    "slug": "central-library",
                    "name": "중앙도서관",
                    "category": "library",
                    "aliases": ["도서관", "중도"],
                    "description": "테스트 도서관",
                    "latitude": 37.48685,
                    "longitude": 126.80164,
                    "opening_hours": {},
                    "source_tag": "test",
                    "last_synced_at": "2026-03-14T10:00:00+09:00",
                }
            ],
        )
        replace_restaurant_cache_snapshot(
            conn,
            origin_slug="central-library",
            kakao_query="카페",
            radius_meters=15 * 75,
            fetched_at="2026-03-14T10:00:00+09:00",
            rows=[
                {
                    "id": -1,
                    "slug": "kakao-cafe-dream",
                    "name": "카페드림",
                    "category": "cafe",
                    "min_price": None,
                    "max_price": None,
                    "latitude": 37.48695,
                    "longitude": 126.79995,
                    "tags": ["카페"],
                    "description": "테스트 카페",
                    "source_tag": "kakao_local_cache",
                    "last_synced_at": "2026-03-14T10:00:00+09:00",
                    "kakao_place_id": "242731511",
                    "source_url": "https://place.map.kakao.com/242731511",
                }
            ],
        )
        update_place_opening_hours(
            conn,
            "central-library",
            {"카페드림": "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)"},
            last_synced_at="2026-03-13T09:00:00+09:00",
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            "tool_find_nearby_restaurants",
            {
                "origin": "central-library",
                "category": "cafe",
                "limit": 1,
                "at": "2026-03-15T11:00:00+09:00",
            },
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["name"] == "카페드림"
    assert payload["open_now"] is False
    assert calls["detail"] == 0

    clear_settings_cache()


def test_mcp_public_empty_classrooms_tool_supports_building_alias(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE332",
                    "title": "데이터베이스",
                    "professor": "김가톨",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "월5~6(N201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                }
            ],
        )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_list_estimated_empty_classrooms',
            {'building': 'N관', 'at': '2026-03-16T10:15:00+09:00'},
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["building"]["slug"] == "nichols-hall"
    assert payload["availability_mode"] == "estimated"
    assert payload["estimate_note"].startswith("공식 시간표 기준 예상 공실입니다.")
    assert payload["items"][0]["room"] == "N201"
    assert payload["items"][0]["availability_mode"] == "estimated"
    assert payload["items"][0]["next_occupied_at"] == "2026-03-16T13:00:00+09:00"

    clear_settings_cache()


def test_mcp_public_empty_classrooms_tool_accepts_kim_sou_hwan_hall(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_list_estimated_empty_classrooms',
            {'building': '김수환관', 'at': '2026-03-16T10:15:00+09:00'},
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["building"]["slug"] == "kim-sou-hwan-hall"
    assert payload["availability_mode"] == "estimated"
    assert payload["items"]
    assert all(item["room"].startswith("K") for item in payload["items"])

    clear_settings_cache()


def test_mcp_public_empty_classrooms_tool_prefers_official_realtime_when_available(
    app_env,
    monkeypatch,
):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    with connection() as conn:
        replace_courses(
            conn,
            [
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE110",
                    "title": "컴퓨팅사고",
                    "professor": "테스트교수",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 2,
                    "period_end": 3,
                    "room": "N101",
                    "raw_schedule": "월2~3(N101)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
                {
                    "year": 2026,
                    "semester": 1,
                    "code": "CSE332",
                    "title": "데이터베이스",
                    "professor": "김가톨",
                    "department": "컴퓨터정보공학부",
                    "section": "01",
                    "day_of_week": "월",
                    "period_start": 5,
                    "period_end": 6,
                    "room": "N201",
                    "raw_schedule": "월5~6(N201)",
                    "source_tag": "test",
                    "last_synced_at": "2026-03-13T09:00:00+09:00",
                },
            ],
        )

    class RealtimeSource:
        def fetch_availability(self, *, building, at, year, semester):
            return [
                {
                    "room": "N101",
                    "available_now": True,
                    "source_observed_at": "2026-03-16T10:10:00+09:00",
                },
                {
                    "room": "N201",
                    "available_now": False,
                    "source_observed_at": "2026-03-16T10:10:00+09:00",
                },
            ]

    monkeypatch.setattr(
        "songsim_campus.services._get_official_classroom_availability_source",
        lambda: RealtimeSource(),
    )
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        result = await mcp.call_tool(
            'tool_list_estimated_empty_classrooms',
            {'building': '니콜스관', 'at': '2026-03-16T10:15:00+09:00'},
        )
        return _tool_payloads(result)[0]

    payload = asyncio.run(main())

    assert payload["availability_mode"] == "realtime"
    assert payload["observed_at"] == "2026-03-16T10:10:00+09:00"
    assert "공식 실시간 공실" in payload["estimate_note"]
    assert [item["room"] for item in payload["items"]] == ["N101"]
    assert payload["items"][0]["availability_mode"] == "realtime"
    assert payload["items"][0]["source_observed_at"] == "2026-03-16T10:10:00+09:00"

    clear_settings_cache()


def test_mcp_public_readonly_tools_return_structured_errors(app_env, monkeypatch):
    pytest.importorskip('mcp.server.fastmcp')
    init_db()
    seed_demo(force=True)
    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        missing_place = await mcp.call_tool('tool_get_place', {'identifier': 'missing-place'})
        invalid_timestamp = await mcp.call_tool(
            'tool_find_nearby_restaurants',
            {'origin': 'central-library', 'at': 'not-a-timestamp'},
        )
        return _tool_payloads(missing_place)[0], _tool_payloads(invalid_timestamp)[0]

    missing_place_payload, invalid_timestamp_payload = asyncio.run(main())

    assert missing_place_payload["type"] == "not_found"
    assert missing_place_payload["error"] == missing_place_payload["message"]
    assert "missing-place" in missing_place_payload["message"]

    assert invalid_timestamp_payload["type"] == "invalid_request"
    assert invalid_timestamp_payload["error"] == invalid_timestamp_payload["message"]
    assert "ISO 8601" in invalid_timestamp_payload["message"]

    clear_settings_cache()
