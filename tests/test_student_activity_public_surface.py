from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_student_activity_docs_mark_static_v1_as_implemented_with_remaining_gaps() -> None:
    registry = _read("docs/source_registry.md")
    audit = _read("docs/qa/main-site-coverage-audit-2026-03-17.md")

    assert "cuk_student_activity_guides" in registry
    assert "student_government.do" in registry
    assert "media.do" in registry
    assert "volunteer.do" in registry
    assert "rotc.do" in registry
    assert "club.do" in registry
    assert "institutional_club1.do" in registry
    assert "institutional_club6.do" in registry
    assert "implemented" in registry
    assert "student_activity_guides" in registry
    assert "중앙동아리, 기관동아리" in registry

    assert "/student-activity-guides" in audit
    assert "총학생회" in audit
    assert "교내미디어" in audit
    assert "사회봉사" in audit
    assert "학생군사교육단" in audit
    assert "중앙동아리" in audit
    assert "기관동아리" in audit
    assert "학생활동 공지/모집/행사" in audit
    assert "공식 notice board 기반 학생활동 공지" in audit


def test_student_activity_notice_docs_mark_first_party_public_surface() -> None:
    readme = _read("README.md")
    registry = _read("docs/source_registry.md")
    audit = _read("docs/qa/main-site-coverage-audit-2026-03-17.md")
    smoke = _read("docs/qa/public-synthetic-smoke.md")

    for document in (readme, registry, audit, smoke):
        assert "/student-activity-notices" in document
        assert "tool_list_student_activity_notices" in document
        assert "songsim://student-activity-notices" in document

    assert "cuk_student_activity_notices" in registry
    assert "https://www.catholic.ac.kr/ko/campuslife/notice.do" in registry
    assert "club_recruitment" in registry
    assert "student_government" in registry
    assert "volunteering" in registry
    assert "rotc" in registry
    assert "campus_event" in registry

    assert "SNS/Instagram" in registry
    assert "SNS/Instagram" in audit
    assert "SNS/Instagram" in smoke
    assert "동아리별 외부 게시물" in smoke


def test_student_activity_notice_smoke_has_explicit_mcp_tool_and_resource_checks() -> None:
    smoke = _read("docs/qa/public-synthetic-smoke.md")

    assert '"method": "tools/call"' in smoke
    assert '"name": "tool_list_student_activity_notices"' in smoke
    assert '"arguments": {"topic": "club_recruitment", "limit": 3}' in smoke
    assert '"method": "resources/read"' in smoke
    assert '"params": {"uri": "songsim://student-activity-notices"}' in smoke
    assert "tool_list_student_activity_notices 200" in smoke
    assert "student activity notices resource 200" in smoke
    assert "source_tag=cuk_student_activity_notices" in smoke
    assert "official notice board scope" in smoke


def test_student_activity_notice_release_pack_has_canary_addendum() -> None:
    release_pack = _read("docs/qa/public-mcp-release-pack-50.md")

    assert "Student activity notice release canary addendum" in release_pack
    assert "SRN01" in release_pack
    assert "SRN02" in release_pack
    assert "SRN03" in release_pack
    assert "SRN04" in release_pack
    assert "club_recruitment" in release_pack
    assert "volunteering" in release_pack
    assert "student_government" in release_pack
    assert "SNS/Instagram" in release_pack
    assert "out_of_scope" in release_pack
    assert "tool_list_student_activity_notices" in release_pack
    assert "songsim://student-activity-notices" in release_pack


def test_student_activity_notice_docs_mark_stale_validation_reports_as_historical() -> None:
    for path in (
        "docs/qa/public-mcp-live-validation-20.md",
        "docs/qa/public-mcp-rehearsal.md",
    ):
        document = _read(path)

        assert "Historical/superseded" in document
        assert "measured results below are preserved" in document
        assert "student_activity_notices" in document


def test_main_site_audit_resolves_service_policy_unsupported_contradiction() -> None:
    audit = _read("docs/qa/main-site-coverage-audit-2026-03-17.md")

    assert (
        "Service-policy footer links are supported through `service_policy_guides`"
        in audit
    )
    assert "현재 비지원 축으로 남는 링크: `입찰공고`" not in audit
    assert "서비스이용안내`의 `입찰공고`, `채용공고` 목록 파서" not in audit


def test_student_activity_smoke_doc_matches_live_contract() -> None:
    smoke = _read("docs/qa/public-synthetic-smoke.md")

    assert "Student activity guide family smoke" in smoke
    assert "총학생회 안내해줘" in smoke
    assert "중앙동아리 뭐 있어?" in smoke
    assert "기관동아리 CUK프렌즈 알려줘" in smoke
    assert "교내미디어 뭐 있어?" in smoke
    assert "사회봉사 활동 알려줘" in smoke
    assert "학생군사교육단 안내해줘" in smoke
    assert "tool_list_student_activity_guides" in smoke
    assert "GET /student-activity-guides" in smoke
    assert "topic=central_clubs" in smoke
    assert "topic=institutional_clubs" in smoke
    assert "topic=campus_media" in smoke
    assert "cuk_student_activity_guides" in smoke


def test_student_activity_release_docs_contain_static_guide_canaries() -> None:
    smoke = _read("docs/qa/public-synthetic-smoke.md")

    for utterance in (
        "총학생회 안내해줘",
        "교내미디어 뭐 있어?",
        "사회봉사 활동 알려줘",
        "학생군사교육단 안내해줘",
    ):
        assert utterance in smoke

    assert "/student-activity-guides" in smoke
    assert "tool_list_student_activity_guides" in smoke
    assert "songsim://student-activity-guide" in smoke
    assert "cuk_student_activity_guides" in smoke
