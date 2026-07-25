from __future__ import annotations

from pathlib import Path

import pytest

from songsim_campus.ingest.official_sources import (
    DormFrancisCheckinOutAffiliatedNoticeBoardSource,
    DormFrancisGeneralAffiliatedNoticeBoardSource,
    DormKACheckinOutAffiliatedNoticeBoardSource,
    DormKAGeneralAffiliatedNoticeBoardSource,
    InternationalStudiesAffiliatedNoticeBoardSource,
)

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


CASES = [
    (
        InternationalStudiesAffiliatedNoticeBoardSource,
        "affiliated_notice_international_studies_list.html",
        "affiliated_notice_international_studies_detail.html",
        "international_studies",
        "https://is.catholic.ac.kr/is/community/notice.do",
        "269582",
        (
            "[ 국제] 학사지원팀 2026학년도 1학기 공결 신청 안내("
            "재안내 / 학생용 가이드 탑재 / 공결 신청 시 필독)"
        ),
        "2026-03-18",
        "2026학년도 1학기 공결 신청 변경 안내입니다. Trinity 전산에서 신청하세요.",
    ),
    (
        DormKAGeneralAffiliatedNoticeBoardSource,
        "affiliated_notice_dorm_k_a_general_list.html",
        "affiliated_notice_dorm_k_a_general_detail.html",
        "dorm_k_a_general",
        "https://dorm.catholic.ac.kr/dormitory/board/comm_notice.do",
        "269375",
        (
            "[K관, A관] 3월 청소점호 안내 3月卫生检查通知 "
            "Room inspection in March THÔNG TIN ĐIỂM DANH DỌN DẸP THÁNG 3"
        ),
        "2026-03-12",
        "[K관, A관] 3월 청소점호 안내입니다. 호실 정리와 점호 시간을 확인하세요.",
    ),
    (
        DormKACheckinOutAffiliatedNoticeBoardSource,
        "affiliated_notice_dorm_k_a_checkin_out_list.html",
        "affiliated_notice_dorm_k_a_checkin_out_detail.html",
        "dorm_k_a_checkin_out",
        "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice1.do",
        "269132",
        "[A관] 2026학년도 1학기 안드레아관 대학원생 추가 모집 공고(내국인)",
        "2026-03-05",
        "[A관] 2026학년도 1학기 안드레아관 대학원생 추가 모집 공고입니다. 기간 내 신청하세요.",
    ),
    (
        DormFrancisGeneralAffiliatedNoticeBoardSource,
        "affiliated_notice_dorm_francis_general_list.html",
        "affiliated_notice_dorm_francis_general_detail.html",
        "dorm_francis_general",
        "https://dorm.catholic.ac.kr/dormitory/board/comm_notice3.do",
        "269435",
        "[F관] 2026년 3월 기숙사 청소 점호 안내 03月卫生检查通知",
        "2026-03-16",
        "[F관] 2026년 3월 기숙사 청소 점호 안내입니다. 점호 시간을 확인하세요.",
    ),
    (
        DormFrancisCheckinOutAffiliatedNoticeBoardSource,
        "affiliated_notice_dorm_francis_checkin_out_list.html",
        "affiliated_notice_dorm_francis_checkin_out_detail.html",
        "dorm_francis_checkin_out",
        "https://dorm.catholic.ac.kr/dormitory/board/checkin-out_notice.do",
        "268320",
        "[F관] 2026-1학기 프란치스코관 입사 안내 2026-1学期方济各馆入住指南",
        "2026-02-04",
        "[F관] 2026-1학기 프란치스코관 입사 안내입니다. 제출 서류와 일정을 확인하세요.",
    ),
]


@pytest.mark.parametrize(
    ("source_cls", "topic", "board_url"),
    [
        (case[0], case[3], case[4])
        for case in CASES
    ],
)
def test_affiliated_notice_sources_expose_expected_defaults(
    source_cls,
    topic: str,
    board_url: str,
) -> None:
    source = source_cls()

    assert source.topic == topic
    assert source.source_tag == "cuk_affiliated_notice_boards"
    assert source.url == board_url


@pytest.mark.parametrize(
    (
        "source_cls",
        "list_fixture",
        "topic",
        "board_url",
        "article_no",
        "title",
        "published_at",
    ),
    [
        (
            case[0],
            case[1],
            case[3],
            case[4],
            case[5],
            case[6],
            case[7],
        )
        for case in CASES
    ],
)
def test_affiliated_notice_list_parsers_extract_representative_rows(
    source_cls,
    list_fixture: str,
    topic: str,
    board_url: str,
    article_no: str,
    title: str,
    published_at: str,
) -> None:
    rows = source_cls().parse_list(_fixture(list_fixture))
    source_url = (
        f"{board_url}?mode=view&articleNo={article_no}"
        "&article.offset=0&articleLimit=10"
    )

    assert rows == [
        {
            "topic": topic,
            "article_no": article_no,
            "title": title,
            "published_at": published_at,
            "source_url": source_url,
            "source_tag": "cuk_affiliated_notice_boards",
        }
    ]


@pytest.mark.parametrize(
    (
        "source_cls",
        "detail_fixture",
        "topic",
        "board_url",
        "title",
        "published_at",
        "summary",
    ),
    [
        (
            case[0],
            case[2],
            case[3],
            case[4],
            case[6],
            case[7],
            case[8],
        )
        for case in CASES
    ],
)
def test_affiliated_notice_detail_parsers_extract_representative_rows(
    source_cls,
    detail_fixture: str,
    topic: str,
    board_url: str,
    title: str,
    published_at: str,
    summary: str,
) -> None:
    source_url = (
        f"{board_url}?mode=view&articleNo=fixture"
        "&article.offset=0&articleLimit=10"
    )
    parsed = source_cls().parse_detail(
        _fixture(detail_fixture),
        default_title="fallback title",
        default_source_url=source_url,
    )

    assert {
        key: parsed[key]
        for key in ("topic", "title", "published_at", "summary", "source_url", "source_tag")
    } == {
        "topic": topic,
        "title": title,
        "published_at": published_at,
        "summary": summary,
        "source_url": source_url,
        "source_tag": "cuk_affiliated_notice_boards",
    }
    assert parsed["body_text"].startswith(summary)
