from __future__ import annotations

import asyncio

import pytest


def test_public_usage_guide_text_contains_current_anchor_phrases():
    from songsim_campus.mcp_public_catalog import public_usage_guide_text

    content = public_usage_guide_text()

    assert "read-only" in content
    assert "tool_search_places" in content
    assert "tool_search_restaurants" in content
    assert "tool_list_academic_calendar" in content
    assert "tool_list_academic_support_guides" in content
    assert "tool_list_academic_status_guides" in content
    assert "tool_list_registration_guides" in content
    assert "tool_list_class_guides" in content
    assert "tool_list_seasonal_semester_guides" in content
    assert "tool_list_academic_milestone_guides" in content
    assert "tool_list_student_activity_guides" in content
    assert "tool_list_about_resource_guides" in content
    assert "tool_list_service_policy_guides" in content
    assert "tool_list_newsroom_posts" in content
    assert "tool_list_student_exchange_guides" in content
    assert "tool_search_phone_book" in content
    assert "tool_list_dormitory_guides" in content
    assert "tool_list_campus_life_notices" in content
    assert "tool_list_leave_of_absence_guides" in content
    assert "tool_list_scholarship_guides" in content
    assert "tool_list_wifi_guides" in content
    assert "tool_find_nearby_restaurants" in content
    assert "예상 공실" in content
    assert "등록금 고지서 조회 방법" in content
    assert "수강신청 변경기간" in content
    assert "외국어강의 의무이수 요건" in content
    assert "계절학기 신청 시기" in content
    assert "성적평가 방법" in content
    assert "졸업요건" in content
    assert "국내 학점교류 신청대상" in content
    assert "교류대학 현황" in content
    assert "교환학생 프로그램" in content
    assert "보건실 전화번호" in content
    assert "학점교류 담당 전화번호" in content
    assert "학생상담 어디서 받아?" in content
    assert "장애학생지원센터 뭐 해줘?" in content
    assert "예비군 신고 시기 알려줘" in content
    assert "부속병원 이용 안내해줘" in content
    assert "총학생회 안내해줘" in content
    assert "교내미디어 뭐 있어?" in content
    assert "사회봉사 활동 알려줘" in content
    assert "학생군사교육단 안내해줘" in content
    assert "학교 규정 어디서 봐?" in content
    assert "학사제도안내책자 보여줘" in content
    assert "개인정보처리방침 어디서 봐?" in content
    assert "청탁금지법 문의 어디야" in content
    assert "포토뉴스 최신 글 보여줘" in content
    assert "보도자료 알려줘" in content
    assert "성심교정 대관안내 알려줘" in content
    assert "개인형 이동장치 안전교육 알려줘" in content
    assert "진로/취업 상담 어디서 신청해?" in content
    assert "기숙사 최신 공지" in content
    assert "행사안내" in content
    assert "교내 행사 공지" in content
    assert "재입학 지원자격" in content
    assert "/gpt/" not in content


def test_register_public_resources_and_prompts_exposes_expected_catalog():
    fastmcp = pytest.importorskip("mcp.server.fastmcp")

    from songsim_campus.mcp_public_catalog import (
        register_public_prompts,
        register_public_resources,
    )

    async def main():
        mcp = fastmcp.FastMCP("Catalog Test")
        register_public_resources(mcp, connection_factory=lambda: None)
        register_public_prompts(mcp)
        resources = await mcp.list_resources()
        prompts = await mcp.list_prompts()
        return {str(resource.uri) for resource in resources}, {prompt.name for prompt in prompts}

    resource_uris, prompt_names = asyncio.run(main())

    assert resource_uris == {
        "songsim://usage-guide",
        "songsim://place-categories",
        "songsim://notice-categories",
        "songsim://class-periods",
    }
    assert prompt_names == {
        "prompt_find_place",
        "prompt_search_courses",
        "prompt_academic_calendar",
        "prompt_search_dining_menus",
        "prompt_class_periods",
        "prompt_library_seat_status",
        "prompt_notice_categories",
        "prompt_latest_notices",
        "prompt_find_nearby_restaurants",
        "prompt_search_restaurants",
        "prompt_find_empty_classrooms",
        "prompt_transport_guide",
    }


def test_register_shared_resources_exposes_expected_resource_uris(tmp_path):
    fastmcp = pytest.importorskip("mcp.server.fastmcp")

    from songsim_campus.mcp_public_catalog import register_shared_resources

    async def main():
        mcp = fastmcp.FastMCP("Catalog Test")
        register_shared_resources(
            mcp,
            connection_factory=lambda: None,
            docs_dir=tmp_path,
        )
        resources = await mcp.list_resources()
        return {str(resource.uri) for resource in resources}

    resource_uris = asyncio.run(main())

    assert resource_uris == {
        "songsim://source-registry",
        "songsim://transport-guide",
        "songsim://certificate-guide",
        "songsim://leave-of-absence-guide",
        "songsim://scholarship-guide",
        "songsim://wifi-guide",
        "songsim://academic-support-guide",
        "songsim://academic-status-guide",
        "songsim://registration-guide",
        "songsim://class-guide",
        "songsim://seasonal-semester-guide",
        "songsim://academic-milestone-guide",
        "songsim://student-activity-guide",
        "songsim://about-resource-guide",
        "songsim://service-policy-guide",
        "songsim://newsroom-posts",
        "songsim://student-exchange-guide",
        "songsim://student-exchange-partners",
        "songsim://phone-book",
        "songsim://campus-life-support-guide",
        "songsim://campus-life-notices",
        "songsim://pc-software",
        "songsim://affiliated-notices",
        "songsim://dormitory-guide",
        "songsim://academic-calendar",
    }
