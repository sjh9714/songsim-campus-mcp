from __future__ import annotations

from pathlib import Path

import pytest

from songsim_campus.services import (
    _extract_campus_dining_menu_days,
    _extract_campus_dining_menu_text,
    _extract_campus_dining_menu_week_range,
    _parse_campus_dining_menu_layout,
)

FIXTURE = Path(__file__).parent / "fixtures" / "campus_dining_weekly_menu.pdf"


def _pdf_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_weekly_menu_pdf_is_split_back_into_weekdays():
    days = _extract_campus_dining_menu_days(_pdf_bytes(), year=2026)

    assert [day["date"] for day in days] == [
        "2026-08-10",
        "2026-08-11",
        "2026-08-12",
        "2026-08-13",
        "2026-08-14",
    ]
    assert [day["weekday"] for day in days] == ["월", "화", "수", "목", "금"]


def test_each_weekday_keeps_its_own_dishes():
    """열이 섞이면 학생이 다른 날 메뉴를 보게 된다.

    기본 extract_text() 로는 표가 y 좌표 기준 줄로만 펴져서 목요일 석식의
    "멕시칸샐러드" 가 각주 뒤 별도 줄로 밀려났고, 어느 요일 것인지 알 수 없었다.
    """
    days = {day["date"]: day for day in _extract_campus_dining_menu_days(_pdf_bytes(), year=2026)}

    monday_lunch = days["2026-08-10"]["meals"]["중식"]
    # 첫 글자가 잘리면 안 된다. 라벨 열 경계를 잘못 잡으면 "순" 이 사라졌었다.
    assert monday_lunch["items"][0] == "순살등심돈까스&소스"
    assert monday_lunch["kcal"] == 920

    thursday_dinner = days["2026-08-13"]["meals"]["석식"]
    assert "멕시칸샐러드" in thursday_dinner["items"]
    assert thursday_dinner["kcal"] == 836

    # 다른 요일로 새지 않는다.
    friday_dinner = days["2026-08-14"]["meals"]["석식"]
    assert "멕시칸샐러드" not in friday_dinner["items"]
    assert "양배추샐러드&오리엔탈D" in friday_dinner["items"]


def test_footnotes_do_not_become_menu_items():
    days = _extract_campus_dining_menu_days(_pdf_bytes(), year=2026)

    for day in days:
        for meal in day["meals"].values():
            for item in meal["items"]:
                assert not item.startswith("*")
                assert "재사용하지" not in item


def test_menu_text_is_still_kept_as_the_original():
    """구조화에 실패하는 PDF(가격표 등)도 있어서 원문은 계속 남긴다."""
    text = _extract_campus_dining_menu_text(_pdf_bytes())

    assert text
    assert "가톨릭대 학생식당" in text


def test_days_are_empty_when_the_pdf_is_not_a_weekly_table():
    """주간 표가 아닌 PDF 는 빈 목록이어야 한다. 없는 구조를 지어내지 않는다."""
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)

    assert _extract_campus_dining_menu_days(buffer.getvalue(), year=2026) == []


def test_semester_menu_keeps_breakfast_corners_and_real_dinner():
    layout = FIXTURE.with_name("campus_dining_semester_layout.txt").read_text()
    days = _parse_campus_dining_menu_layout(layout, year=2026)
    monday = days[0]["meals"]
    assert list(monday) == ["천원의 아침", "한식", "누들", "플러스코너", "석식"]
    assert monday["천원의 아침"]["items"][0] == "아쿠아치킨까스"
    assert monday["한식"]["items"][0] == "(탕)돼지고기김치찌개"
    assert monday["누들"]["items"][0] == "우삼겹쌀국수"
    assert monday["플러스코너"]["items"] == ["청양소스크림함박&감자튀김"]
    assert monday["석식"]["items"][0] == "단호박카레라이스"
    assert monday["석식"]["kcal"] == 824
    assert "천원의 아침" not in days[-1]["meals"]


def test_unknown_menu_sections_are_not_guessed_as_lunch_or_dinner():
    layout = FIXTURE.with_name("campus_dining_semester_layout.txt").read_text()
    for label in ("천원의아침", "한식", "누들", "플러스코너", "석식"):
        layout = layout.replace(label, " " * len(label))
    assert _parse_campus_dining_menu_layout(layout, year=2026) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026.08.31 - 09.04", ("2026-08-31", "2026-09-04")),
        ("2026.12.28 - 01.01", ("2026-12-28", "2027-01-01")),
        ("2026.12.28 - 2027.01.01", ("2026-12-28", "2027-01-01")),
        ("2026.09.07 - 09.11", ("2026-09-07", "2026-09-11")),
        ("2026.09.07 - 09.01", (None, None)),
        ("2026.02.30 - 03.04", (None, None)),
    ],
)
def test_week_range_handles_month_and_year_boundaries(text, expected):
    assert _extract_campus_dining_menu_week_range(text) == expected


def test_menu_columns_handle_new_year_and_reject_invalid_dates():
    layout = ("구분          12/31(목)          01/01(금)\n"
              "중식          쌀밥                떡국\n"
              "              800kcal            900kcal")
    days = _parse_campus_dining_menu_layout(layout, year=2026)
    assert [day["date"] for day in days] == ["2026-12-31", "2027-01-01"]
    assert _parse_campus_dining_menu_layout(layout.replace("12/31", "12/32"), year=2026) == []
