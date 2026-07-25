from __future__ import annotations

from pathlib import Path

from songsim_campus.ingest.official_sources import (
    DormitoryFeeGuideSource,
    DormitoryHomepageGuideSource,
    DormitorySongsimGuideSource,
)

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_dormitory_guide_sources_expose_expected_defaults() -> None:
    songsim_source = DormitorySongsimGuideSource()
    home_source = DormitoryHomepageGuideSource()
    fee_source = DormitoryFeeGuideSource()

    assert songsim_source.source_tag == "cuk_dormitory_guides"
    assert home_source.source_tag == "cuk_dormitory_guides"
    assert fee_source.source_tag == "cuk_dormitory_guides"
    assert songsim_source.url.endswith("/dormitory_songsim.do")
    assert home_source.url == "https://dorm.catholic.ac.kr/"
    assert fee_source.url.endswith("/life-guide/stefano-andrea.do")


def test_dormitory_songsim_page_parser_extracts_expected_rows() -> None:
    rows = DormitorySongsimGuideSource().parse(
        _fixture("dormitory_songsim.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "스테파노관",
        "안드레아관",
        "프란치스코관",
        "기숙사운영팀",
    ]

    stephano = next(row for row in rows if row["title"] == "스테파노관")
    assert stephano["topic"] == "hall_info"
    assert stephano["source_tag"] == "cuk_dormitory_guides"
    assert stephano["summary"].startswith("스테파노관은 가톨릭대 개교 150주년")
    assert any("383개(1,167명)" in step for step in stephano["steps"])
    assert any("기숙사운영팀 사무실" in step for step in stephano["steps"])
    assert any("편의점" in step for step in stephano["steps"])

    andrea = next(row for row in rows if row["title"] == "안드레아관")
    assert any("238실(2인실)" in step for step in andrea["steps"])
    assert any("CUK 비교과혁신라운지" in step for step in andrea["steps"])

    francesco = next(row for row in rows if row["title"] == "프란치스코관")
    assert any("도보로 5분 이내" in step for step in francesco["steps"])
    assert any("개별 취사가 가능합니다" in step for step in francesco["steps"])

    staff = next(row for row in rows if row["title"] == "기숙사운영팀")
    assert staff["summary"] == "담당부서: 성심교정 기숙사운영팀"
    assert staff["steps"] == [
        "담당부서: 성심교정 기숙사운영팀",
        "전화: 02-2164-4660, 4661, 4663",
        "메일: dormitory1@catholic.ac.kr",
    ]
    assert staff["links"] == [
        {"label": "02-2164-4660, 4661, 4663", "url": "tel:02-2164-4660, 4661, 4663"},
        {"label": "dormitory1@catholic.ac.kr", "url": "mailto:dormitory1@catholic.ac.kr"},
    ]


def test_dormitory_home_page_parser_extracts_quick_links_and_notices() -> None:
    rows = DormitoryHomepageGuideSource().parse(
        _fixture("dormitory_home.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["topic"] for row in rows] == [
        "quick_links",
        "latest_notices",
        "latest_notices",
        "latest_notices",
        "latest_notices",
    ]

    quick_links = rows[0]
    assert quick_links["title"] == "입사안내 / 퇴사안내 / 생활안내 / 기숙사비 / FAQ"
    assert quick_links["summary"] == "입사안내"
    assert quick_links["steps"] == [
        "입사안내",
        "퇴사안내",
        "생활안내",
        "기숙사비",
        "FAQ",
        "기숙사비 환불신청서",
        "신입생 입사신청",
    ]
    assert [item["label"] for item in quick_links["links"]] == [
        "입사안내",
        "퇴사안내",
        "생활안내",
        "기숙사비",
        "FAQ",
        "기숙사비 환불신청서",
        "신입생 입사신청",
    ]

    general_notice = next(row for row in rows if row["title"] == "일반공지(K관/A관)")
    assert general_notice["summary"] == "[K관, A관] 3월 청소점호 안내"
    assert general_notice["steps"] == [
        "[K관, A관] 3월 청소점호 안내",
        "[K관, A관] 2026-1학기 기숙사 온라인 OT 교육 (필수교육) _미 이수 시, 벌점 부과",
        "[K관] 빨래건조대 호실번호표 부착 안내",
        "[K관] 복도 개인물품, 빨래건조대 적치 금지 & 4인실 사생 짐 보관 안내",
    ]
    assert general_notice["links"][0]["url"].endswith("articleNo=269375")

    francis_notice = next(row for row in rows if row["title"] == "입퇴사공지(프란치스코관)")
    assert francis_notice["steps"][0] == "[F관] 2026-1학기 프란치스코관 입사 안내"
    assert any("정기퇴사 안내" in step for step in francis_notice["steps"])
    assert all(
        link["url"].startswith("https://dorm.catholic.ac.kr/dormitory/board/")
        for link in francis_notice["links"]
    )


def test_dormitory_fee_page_parser_extracts_fee_and_refund_rows() -> None:
    rows = DormitoryFeeGuideSource().parse(
        _fixture("dormitory_fee_stefano_andrea.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert len(rows) == 1
    fee = rows[0]
    assert fee["topic"] == "fees"
    assert fee["title"] == "스테파노관 / 안드레아관 기숙사비"
    assert fee["source_tag"] == "cuk_dormitory_guides"
    assert fee["summary"].startswith("정규학기와 방학 기숙사비")
    assert any("정규학기 스테파노관 기숙사비" in step for step in fee["steps"])
    assert any("2인실" in step and "1,308,000원" in step for step in fee["steps"])
    assert any("추가 선발 시 납부금액" in step and "85% 금액" in step for step in fee["steps"])
    assert any("환불절차: STEP 1" in step for step in fee["steps"])
    assert any("기숙사비 전액 환불" in step for step in fee["steps"])
    assert any("환불금은 실제 퇴사일 기준" in step for step in fee["steps"])
