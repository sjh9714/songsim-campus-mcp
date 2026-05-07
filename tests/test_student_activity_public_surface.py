from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _read_jsonl(path: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in _read(path).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))
    return rows


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


def test_student_activity_eval_corpus_contains_live_canaries() -> None:
    rows = _read_jsonl("data/qa/public_api_eval_corpus_1000.jsonl")
    student_activity_rows = [row for row in rows if str(row.get("id") or "").startswith("SAV-")]

    utterances = {row["user_utterance"] for row in student_activity_rows}

    assert {
        "총학생회 안내해줘",
        "교내미디어 뭐 있어?",
        "사회봉사 활동 알려줘",
        "학생군사교육단 안내해줘",
    }.issubset(utterances)
    assert {row["domain"] for row in student_activity_rows} == {"student_activity_guides"}
    assert {row["expected_mcp_flow"] for row in student_activity_rows} == {
        "tool_list_student_activity_guides"
    }
    assert {row["watch_policy"] for row in student_activity_rows} == {"none"}
    assert {row["api_request"]["path"] for row in student_activity_rows} == {
        "/student-activity-guides"
    }
    assert {row["pass_rule"]["summary_kind"] for row in student_activity_rows} == {
        "student_activity_guides_top5"
    }
    assert len(student_activity_rows) >= 4
