from __future__ import annotations

from pathlib import Path

from songsim_campus.services import (
    _extract_campus_dining_menu_days,
    _extract_campus_dining_menu_text,
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
