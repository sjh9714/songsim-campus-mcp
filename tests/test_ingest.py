from __future__ import annotations

import json
from pathlib import Path

from songsim_campus.ingest.kakao_places import parse_place_detail_opening_hours
from songsim_campus.ingest.official_sources import (
    AcademicCalendarSource,
    AcademicSupportGuideSource,
    CampusFacilitiesSource,
    CampusMapSource,
    CertificateGuideSource,
    CourseCatalogSource,
    DropoutGuideSource,
    LeaveOfAbsenceGuideSource,
    LibraryHoursSource,
    LibrarySeatStatusXmlSource,
    NoticeSource,
    ReAdmissionGuideSource,
    ReturnFromLeaveOfAbsenceGuideSource,
    ScholarshipGuideSource,
    TransportGuideSource,
    WifiGuideSource,
    classify_notice_category,
)

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _fixture_json(name: str) -> dict:
    return json.loads(_fixture(name))


def test_campus_map_discovers_place_list_endpoint():
    source = CampusMapSource("https://www.catholic.ac.kr/ko/about/campus-map.do")

    url = source.discover_place_list_url(_fixture("campus_map_page.html"), campus="1")

    assert url == "https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1"


def test_campus_map_parser_normalizes_aliases_and_missing_coordinates():
    source = CampusMapSource("https://www.catholic.ac.kr/ko/about/campus-map.do")

    rows = source.parse_place_list(
        _fixture("campus_map_places.json"),
        fetched_at="2026-03-13T09:00:00+09:00",
    )

    assert rows[0]["slug"] == "main-gate"
    assert rows[0]["category"] == "gate"

    library = next(item for item in rows if item["slug"] == "central-library")
    assert library["category"] == "library"
    assert "베리타스관" in library["aliases"]
    assert "중앙도서관" in library["aliases"]
    assert "L관" in library["aliases"]

    trail = next(item for item in rows if item["name"] == "산책로")
    assert trail["latitude"] is None
    assert trail["longitude"] is None


def test_course_parser_extracts_single_schedule_fields():
    source = CourseCatalogSource("https://www.catholic.ac.kr/ko/support/subject.do")

    rows = source.parse(
        _fixture("subject_results.html"),
        fetched_at="2026-03-13T09:00:00+09:00",
    )

    first = rows[0]
    assert first["year"] == 2026
    assert first["semester"] == 1
    assert first["code"] == "03149"
    assert first["title"] == "자료구조"
    assert first["professor"] == "박정흠"
    assert first["day_of_week"] == "화"
    assert first["period_start"] == 2
    assert first["period_end"] == 3
    assert first["room"] == "BA203"
    assert first["raw_schedule"] == "화2~3(BA203)"


def test_course_parser_preserves_raw_schedule_for_multi_slot_rows():
    source = CourseCatalogSource("https://www.catholic.ac.kr/ko/support/subject.do")

    rows = source.parse(
        _fixture("subject_results.html"),
        fetched_at="2026-03-13T09:00:00+09:00",
    )

    second = rows[1]
    assert second["raw_schedule"] == "화2~3(BA203), 목3(BA203)"
    assert second["day_of_week"] is None
    assert second["period_start"] is None
    assert second["period_end"] is None
    assert second["room"] is None


def test_course_parser_handles_schedule_without_room():
    source = CourseCatalogSource("https://www.catholic.ac.kr/ko/support/subject.do")

    rows = source.parse(
        _fixture("subject_results.html"),
        fetched_at="2026-03-13T09:00:00+09:00",
    )

    third = rows[2]
    assert third["day_of_week"] == "금"
    assert third["period_start"] == 5
    assert third["period_end"] == 6
    assert third["room"] is None


def test_notice_list_parser_extracts_dates_and_absolute_urls():
    source = NoticeSource("https://www.catholic.ac.kr/ko/campuslife/notice.do")

    rows = source.parse_list(_fixture("notice_list.html"))

    assert rows[0]["title"] == "2026학년도 1학기 가족장학금 신청 안내"
    assert rows[0]["published_at"] == "2026-03-12"
    assert rows[0]["source_url"] == "https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=1001&article.offset=0&articleLimit=10"


def test_notice_detail_parser_builds_summary_and_classifies_rules():
    source = NoticeSource("https://www.catholic.ac.kr/ko/campuslife/notice.do")

    parsed = source.parse_detail(
        _fixture("notice_detail_scholarship.html"),
        default_title="2026학년도 1학기 가족장학금 신청 안내",
        default_category="학사",
    )

    assert parsed["published_at"] == "2026-03-12"
    assert parsed["summary"].startswith("2026학년도 1학기 가족장학금 신청을 원하는 학생은")
    assert parsed["category"] == "scholarship"


def test_notice_detail_parser_prefers_explicit_list_category_over_generic_detail_label():
    source = NoticeSource("https://www.catholic.ac.kr/ko/campuslife/notice.do")

    parsed = source.parse_detail(
        """
        <div class="b-title-box">
          <span class="b-cate">공지</span>
          <h1 class="b-title">2026학년도 1학기 Major Discovery Week 특강 신청 마감 안내</h1>
        </div>
        <ul class="b-etc-box">
          <li><span class="title">등록일</span><span>:</span><span>2026.03.14</span></li>
        </ul>
        <div class="b-content-box">
          <div class="b-con-box">
            학사 일정과 특강 신청 마감 일정을 안내합니다.
          </div>
        </div>
        """,
        default_title="2026학년도 1학기 Major Discovery Week 특강 신청 마감 안내",
        default_category="학사",
    )

    assert parsed["published_at"] == "2026-03-14"
    assert parsed["labels"] == ["학사"]
    assert parsed["category"] == "academic"


def test_notice_category_rules_cover_cafeteria_keywords():
    assert (
        classify_notice_category(
            title="천원의 아침밥 운영 일정 안내",
            body="학생식당 조식 이용 방법과 운영 시간을 안내합니다.",
            board_category="생활",
        )
        == "cafeteria"
    )


def test_notice_category_rules_normalize_career_keywords_to_employment():
    assert (
        classify_notice_category(
            title="커리어상담센터 진로취업상담 안내",
            body="채용 준비와 진로 상담을 지원합니다.",
            board_category="취창업",
        )
        == "employment"
    )


def test_notice_category_rules_prioritize_academic_board_category_over_urgent_keywords():
    assert (
        classify_notice_category(
            title="2026학년도 1학기 수강신청 변경 마감 안내",
            body="학사 일정과 수강 정정 마감 일정을 안내합니다.",
            board_category="학사",
        )
        == "academic"
    )


def test_return_from_leave_parser_extracts_sections_and_links():
    source = ReturnFromLeaveOfAbsenceGuideSource()

    rows = source.parse(
        _fixture("return_from_leave_of_absence.html"),
        fetched_at="2026-03-15T00:00:00+09:00",
    )

    titles = {row["title"] for row in rows}
    assert titles == {"신청방법", "참고사항"}
    main = next(row for row in rows if row["title"] == "신청방법")
    assert main["status"] == "return_from_leave"
    assert any("복학신청" in step for step in main["steps"])
    assert main["links"] and main["links"][0]["label"] == "복귀일정"
    assert main["source_tag"] == "cuk_academic_status_guides"


def test_dropout_parser_keeps_required_sections_and_alert_notes():
    source = DropoutGuideSource()

    rows = source.parse(
        _fixture("dropout.html"),
        fetched_at="2026-03-15T00:00:00+09:00",
    )

    titles = {row["title"] for row in rows}
    assert {"자퇴원서 제출", "자퇴 신청 방법", "등록금 반환기준"} <= titles
    alert_row = next(row for row in rows if row["title"] == "등록금 반환기준")
    assert any("자퇴이전 등록금" in step for step in alert_row["steps"])
    assert alert_row["status"] == "dropout"


def test_readmission_parser_keeps_required_sections():
    source = ReAdmissionGuideSource()

    rows = source.parse(
        _fixture("re_admission.html"),
        fetched_at="2026-03-15T00:00:00+09:00",
    )

    titles = {row["title"] for row in rows}
    assert {"지원자격", "선발일정", "선발기준"} <= titles
    schedule_row = next(row for row in rows if row["title"] == "선발일정")
    assert schedule_row["summary"] == "매 학기(6월 초, 12월 초) 홈페이지를 통해 공지"
    criteria_row = next(row for row in rows if row["title"] == "선발기준")
    assert criteria_row["status"] == "re_admission"
    assert any("이수학기가 많은 자" in step for step in criteria_row["steps"])


def test_library_hours_parser_extracts_room_labels_and_schedules():
    source = LibraryHoursSource("https://library.catholic.ac.kr/webcontent/info/45")
    shared_room_hours = (
        "학기중 평일 09:00-21:00 / 토요일 09:00-13:00 | "
        "방학중 평일 09:00-17:00 / 토요일 휴 실 | 공휴일 휴실"
    )

    rows = source.parse(
        _fixture("library_hours.html"),
        fetched_at="2026-03-13T09:00:00+09:00",
    )

    assert rows == [
        {
            "place_name": "중앙도서관",
            "opening_hours": {
                "대출반납실": shared_room_hours,
                "제1,2자료실": shared_room_hours,
                "리서치커먼스": shared_room_hours,
                "제1자유열람실": "24시간 개방 | 연중 무휴",
                "제2자유열람실": "08:00 ~ 23:00 | 연중 무휴",
            },
            "source_tag": "cuk_library_hours",
            "last_synced_at": "2026-03-13T09:00:00+09:00",
        }
    ]


SEAT_XML_URL = "https://mlibrary.catholic.ac.kr/mobile/PA/roomStatusListXML.php"


def test_library_seat_status_parser_reads_every_reading_room():
    """예전 소스(203.229.203.240)는 서버가 사라져 몇 주째 빈 화면만 나왔다.

    학교가 옮겨 간 mlibrary 는 좌석 수를 XML 로 준다. 페이지 자체는 표를
    자바스크립트로 채우므로 HTML 을 긁으면 빈 표만 나오고, XML 을 직접 써야 한다.
    """
    source = LibrarySeatStatusXmlSource(SEAT_XML_URL)

    rows = source.parse(
        _fixture("library_seat_status.xml"),
        fetched_at="2026-08-09T05:00:00+09:00",
    )

    assert [row["room_name"] for row in rows] == [
        "제1자유열람실A",
        "제1자유열람실B",
        "대학원 열람실",
        "제2자유열람실A",
        "제2자유열람실B",
        "메인스퀘어",
    ]
    assert rows[0] == {
        "room_name": "제1자유열람실A",
        "remaining_seats": 158,
        "occupied_seats": 0,
        "total_seats": 158,
        "source_url": SEAT_XML_URL,
        "source_tag": "cuk_library_seat_status",
        "last_synced_at": "2026-08-09T05:00:00+09:00",
    }
    # 사용 중인 좌석이 있는 방도 제대로 읽는다.
    occupied = next(row for row in rows if row["room_name"] == "제1자유열람실B")
    assert (occupied["total_seats"], occupied["occupied_seats"], occupied["remaining_seats"]) == (
        132,
        1,
        131,
    )


def test_library_seat_status_parser_survives_a_broken_payload():
    """학교 서버가 XML 이 아닌 것을 돌려줘도 빈 결과일 뿐 터지지 않아야 한다."""
    source = LibrarySeatStatusXmlSource(SEAT_XML_URL)

    assert source.parse("<html>maintenance</html>", fetched_at="2026-08-09T05:00:00+09:00") == []
    assert source.parse("", fetched_at="2026-08-09T05:00:00+09:00") == []

def test_facility_hours_parser_extracts_cards_and_table_rows():
    source = CampusFacilitiesSource("https://www.catholic.ac.kr/ko/campuslife/restaurant.do")

    rows = source.parse(
        _fixture("facility_hours.html"),
        fetched_at="2026-03-13T09:00:00+09:00",
    )

    assert rows[0]["facility_name"] == "Buon Pranzo 부온 프란조"
    assert rows[0]["location"] == "학생미래인재관 2층"
    assert rows[0]["hours_text"] == "중식 11:30 ~ 14:00"
    assert rows[0]["phone"] == "02-2164-4736"
    assert rows[0]["category"] == "식당안내"
    assert rows[0]["menu_week_label"] == "3월 3주차 메뉴표 확인하기"
    assert rows[0]["menu_source_url"].startswith(
        "https://www.catholic.ac.kr/cms/etcResourceDown.do"
    )

    cafe = next(item for item in rows if item["facility_name"] == "카페드림")
    assert cafe["location"] == "중앙도서관 2층"
    assert cafe["phone"] == "010-9517-9417"
    assert cafe["hours_text"] == "평일 08:00~19:00 토 10:00~16:00 (일/공휴일휴무)"

    mensa = next(item for item in rows if item["facility_name"] == "Café Mensa 카페 멘사")
    assert mensa["location"] == "김수환관 1층"
    assert mensa["phone"] is None
    assert mensa["menu_week_label"] == "3월 3주차 메뉴표 확인하기"
    assert mensa["menu_source_url"].startswith(
        "https://www.catholic.ac.kr/cms/etcResourceOpen.do"
    )

    market = next(item for item in rows if item["facility_name"] == "CU")
    assert market["category"] == "편의점"
    assert market["phone"] == "032-343-3424"
    assert market["hours_text"].endswith("(야간 무인으로 24시간 운영)")


def test_facility_parser_handles_table_rows_with_missing_phone():
    source = CampusFacilitiesSource("https://www.catholic.ac.kr/ko/campuslife/restaurant.do")

    html = """
    <div class="content-box restaurant">
      <div class="table-wrap">
        <table>
          <tr>
            <th>업종</th>
            <th>매장명</th>
            <th>전화번호</th>
            <th>위치</th>
            <th>운영시간</th>
          </tr>
          <tr>
            <td class="txt-center">편의점</td>
            <td class="txt-center">시범시설</td>
            <td class="txt-center"></td>
            <td class="txt-center">학생회관 2층</td>
            <td>평일 09:00~18:00</td>
          </tr>
        </table>
      </div>
    </div>
    """

    rows = source.parse(html, fetched_at="2026-03-13T09:00:00+09:00")

    assert rows[0]["facility_name"] == "시범시설"
    assert rows[0]["phone"] is None
    assert rows[0]["location"] == "학생회관 2층"
    assert rows[0]["hours_text"] == "평일 09:00~18:00"


def test_transport_parser_extracts_modes_summaries_and_steps():
    source = TransportGuideSource("https://www.catholic.ac.kr/ko/about/location_songsim.do")

    rows = source.parse(
        _fixture("transport_page.html"),
        fetched_at="2026-03-13T09:00:00+09:00",
    )

    assert rows[0]["mode"] == "campus"
    assert rows[0]["title"] == "성심교정"
    assert rows[0]["summary"] == "14662 경기도 부천시 원미구 지봉로 43 / 02-2164-4114"

    subway = next(item for item in rows if item["title"] == "1호선")
    assert subway["mode"] == "subway"
    assert "역곡역 2번 출구" in subway["summary"]
    assert subway["steps"] == ["인천역 ↔ 역곡역 : 35분 소요", "서울역 ↔ 역곡역 : 30분 소요"]

    bus = next(item for item in rows if item["title"] == "시내버스")
    assert bus["mode"] == "bus"
    assert bus["steps"][-1] == "후문 기준 : [금강맨션] 정류장 하차"


def test_certificate_parser_extracts_guides_summaries_and_steps():
    source = CertificateGuideSource("https://www.catholic.ac.kr/ko/support/certificate.do")

    rows = source.parse(
        _fixture("certificate_page.html"),
        fetched_at="2026-03-17T15:00:00+09:00",
    )

    issued = next(item for item in rows if item["title"] == "발급증명")
    assert "재학" in issued["summary"]
    assert issued["steps"] == []

    kiosk = next(item for item in rows if item["title"] == "무인발급(자동증명발급기)")
    assert kiosk["summary"] == "학생지원팀(니콜스관 N109호) 앞 / 24시간"
    assert "수수료: 국문 / 영문 1,000원(1매) * 신용카드, 체크카드 가능" in kiosk["steps"]
    assert "학부 92학번 이전 입학생은 영문증명서 발급이 불가합니다." in kiosk["steps"]

    internet = next(item for item in rows if item["title"] == "인터넷 증명발급")
    assert "인터넷 증명신청 및 발급" in internet["summary"]
    assert internet["source_url"] == "https://catholic.certpia.com/"
    assert any("유의사항:" in step for step in internet["steps"])

    stopped_mail = next(
        item for item in rows if item["title"] == "우편(국내·외) 증명 발송 업무 중단 안내"
    )
    assert "업무를 중단" in stopped_mail["summary"]
    assert stopped_mail["steps"][-1] == "문의: 학생지원팀 02-2164-4732"


def test_leave_of_absence_parser_extracts_sections_steps_and_links():
    source = LeaveOfAbsenceGuideSource("https://www.catholic.ac.kr/ko/support/leave_of_absence.do")

    rows = source.parse(
        _fixture("leave_of_absence.html"),
        fetched_at="2026-03-17T20:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "신청방법",
        "휴학상담 안내",
        "다음의 경우 학사지원팀에 직접 방문 제출",
        "휴학 시기에 따른 등록금 반환 기준",
    ]

    application = rows[0]
    assert (
        application["summary"]
        == "Trinity 신청 (학사정보 → 학적/졸업) → 휴학상담 → 휴학신청 승인 → 휴학최종 승인"
    )
    assert application["steps"] == [
        "STEP 1: Trinity 신청 (학사정보 → 학적/졸업) (학생)",
        "STEP 2: 휴학상담 (지도교수)",
        "STEP 3: 휴학신청 승인 (학과장)",
        "STEP 4: 휴학최종 승인 (학사지원팀)",
    ]
    assert application["links"] == [
        {
            "label": "휴복학 FAQ (다운로드)",
            "url": "https://www.catholic.ac.kr/cms/etcResourceDown.do?site=fake&key=fake",
        }
    ]

    consultation = rows[1]
    assert (
        consultation["summary"]
        == "상담을 위한 지도교수 확인과 상담일정 조율 후 휴학관련 문의처를 확인합니다."
    )
    assert consultation["steps"] == [
        "상담을 위한 지도교수 확인 : 트리니티 → AI코디 → 통합상담 → 교수상담",
        "상담일정 조율 안내 : 트리니티 → 학사정보에서 휴학 신청 후 지도교수에게 메일 발송",
        "휴학관련 주요 문의처",
        "휴학관련 주요 문의처: 지도교수 상담 : 소속 학과/학부 사무실 문의",
        "휴학관련 주요 문의처: 휴학관련 상담 : 학사지원팀 문의(02-2164-4288)",
    ]

    direct_visit = rows[2]
    assert (
        direct_visit["summary"]
        == "군 휴학, 질병 휴학 등 예외적인 경우에는 학사지원팀 방문 제출이 필요합니다."
    )
    assert direct_visit["steps"] == [
        "군 휴학: 입대 1주일 전, 입영통지서를 지참하여 방문 제출",
        (
            "군 휴학: 전역 후 일반휴학을 계속할 경우, 전역증과 일반휴학원을 지참하여 "
            "학사지원팀 방문 제출"
        ),
        "질병 휴학: 일반휴학원 및 4주 이상 진단서 지참하여 방문 신청",
        "질병 휴학: 첫 학기에도 신청 가능하며, 학기 중 질병휴학 시 등록금 이월 가능",
        "모든 휴학원은(군휴학 제외) 지도교수님 상담 및 교수님 서명 필수",
    ]
    assert direct_visit["links"] == [
        {
            "label": "각종서식",
            "url": "https://www.catholic.ac.kr/ko/about/various-forms.do",
        }
    ]

    refund = rows[3]
    assert (
        refund["summary"]
        == "휴학 시점에 따라 수업료 전액, 5/6, 2/3 또는 미반환 기준이 적용됩니다."
    )
    assert (
        refund["steps"][0]
        == "휴학시점: 추가등록기간 / 반환금액: 수업료 전액 / 대상 휴학: 일반, 군, 질병, 육아"
    )
    assert (
        refund["steps"][-1]
        == "휴학시점: 학기개시일 부터 90일 초과 / 반환금액: 없음 / 대상 휴학: 군, 질병, 육아"
    )
    assert all(row["source_tag"] == "cuk_leave_of_absence_guides" for row in rows)


def test_academic_support_parser_extracts_contacts_steps_and_title():
    source = AcademicSupportGuideSource(
        "https://www.catholic.ac.kr/ko/support/academic_contact_information.do"
    )

    rows = source.parse(
        _fixture("academic_contact_information.html"),
        fetched_at="2026-03-18T12:00:00+09:00",
    )

    assert any("교육과정" in row["title"] for row in rows)
    credits = next(row for row in rows if "학점교류" in row["title"])
    assert credits["title"] == "수업 / 학점교류"
    assert credits["summary"] == "타 대학 학점교류 신청 · 관리 업무"
    assert credits["contacts"] == ["02-2164-4510", "02-2164-4048"]
    leave = next(row for row in rows if row["title"] == "휴·복학")
    assert leave["contacts"] == ["02-2164-4288"]
    academic = next(row for row in rows if row["title"].startswith("학적"))
    assert academic["steps"][0].startswith("전공배정")
    assert all(row["source_tag"] == "cuk_academic_support_guides" for row in rows)


def test_academic_calendar_parser_normalizes_kst_dates_and_campuses():
    source = AcademicCalendarSource("https://www.catholic.ac.kr/ko/support/calendar2024_list.do")

    rows = source.parse(
        _fixture("academic_calendar_feed.json"),
        fetched_at="2026-03-17T15:00:00+09:00",
    )

    opening = next(item for item in rows if item["title"] == "1학기 개시일 / 신입생 입학미사")
    assert opening["academic_year"] == 2026
    assert opening["start_date"] == "2026-03-03"
    assert opening["end_date"] == "2026-03-03"
    assert opening["campuses"] == ["성심", "성의", "성신"]
    assert opening["source_url"] == "https://www.catholic.ac.kr/ko/support/calendar2024_list.do"
    assert opening["source_tag"] == "cuk_academic_calendar"

    registration = next(item for item in rows if item["title"] == "추가 등록기간")
    assert registration["start_date"] == "2026-03-10"
    assert registration["end_date"] == "2026-03-13"

    winter = next(item for item in rows if item["title"] == "동계 계절학기 등록")
    assert winter["academic_year"] == 2026
    assert winter["start_date"] == "2027-01-05"
    assert winter["end_date"] == "2027-01-07"


def test_scholarship_guide_parser_extracts_sections_and_official_links():
    source = ScholarshipGuideSource("https://www.catholic.ac.kr/ko/support/scholarship_songsim.do")

    rows = source.parse(
        _fixture("scholarship_songsim.html"),
        fetched_at="2026-03-17T17:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "장학생 자격",
        "장학생 종류",
        "장학금 신청",
        "장학금 지급",
        "공식 장학 문서",
    ]

    qualification = rows[0]
    assert qualification["summary"] == (
        "당해학기 정규학기 재학생으로, 각 장학금별 선발 기준에 부합하는 자"
    )
    assert qualification["steps"] == []
    assert qualification["links"] == []

    scholarship_types = rows[1]
    assert scholarship_types["summary"] == "장학금 재원, 지급 목적, 비고로 구성된 표"
    assert scholarship_types["steps"][0].startswith("장학금 재원: 교내 / 지급 목적: 등록금성")
    assert scholarship_types["steps"][-1] == "생활비성 장학 : 등록금 범위와 관계없이 수혜 가능"

    application = rows[2]
    assert application["summary"] == "홈페이지 공지사항 수시 게재하므로 장학별 해당 기간 내에 신청"
    assert any(
        "구분: 교내 / 장학금 종류: 근로(A/B/C) 및 인턴십" in step
        for step in application["steps"]
    )
    assert any("상기 외 교내장학금" in step for step in application["steps"])

    payout = rows[3]
    assert payout["summary"].startswith("등록금 고지서 감면의 원칙")
    assert payout["steps"] == [
        (
            "장학금 수령 계좌 등록 : 학생 본인 명의의 계좌정보 등록"
            "(트리니티-학사정보-학적-신상정보수정-기타<은행명/계좌번호/예금주>)"
        )
    ]

    documents = rows[4]
    assert documents["summary"] == "장학금 지급 규정과 신입생/재학생 장학제도 공식 문서 링크"
    assert documents["steps"] == []
    assert documents["links"] == [
        {
            "label": "장학금 지급 규정 보기",
            "url": "http://rule.catholic.ac.kr:8080/lmxsrv/law/lawFullView.srv?SEQ=176&SEQ_HISTORY=2307",
        },
        {
            "label": "신입생(내국인) 장학제도",
            "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/scholarship_songsim_251226-2pdf.pdf",
        },
        {
            "label": "신입생(외국인) 장학제도",
            "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/scholarship_songsim_251226-3pdf.pdf",
        },
        {
            "label": "재학생 장학제도",
            "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/scholarship_songsim_251226-4pdf.pdf",
        },
    ]
    assert all(row["source_tag"] == "cuk_scholarship_guides" for row in rows)


def test_wifi_guide_parser_extracts_buildings_ssids_and_shared_steps():
    source = WifiGuideSource("https://www.catholic.ac.kr/ko/campuslife/wifi.do")

    rows = source.parse(
        _fixture("wifi.html"),
        fetched_at="2026-03-17T19:00:00+09:00",
    )

    assert [row["building_name"] for row in rows] == [
        "니콜스관",
        "미카엘관",
        "베리타스관(중앙도서관)",
        "그 외 건물",
    ]

    first = rows[0]
    assert first["ssids"] == ["catholic_univ", "강의실 호실명 (ex: N301)"]
    assert first["steps"] == [
        "무선랜 안테나 검색 후 신호가 강한 SSID 선택 (최초 접속 시 보안키 입력)",
        "K관, A관(안드레아관) 보안키 : catholic!!(교내 동일)",
        "그외 건물 보안키 : 1234567890 (교내 동일)",
    ]
    assert first["source_url"] == "https://www.catholic.ac.kr/ko/campuslife/wifi.do"
    assert first["source_tag"] == "cuk_wifi_guides"

    annex = rows[1]
    assert annex["ssids"] == ["catholic_mica"]
    assert annex["steps"] == first["steps"]

    fallback = rows[-1]
    assert fallback["building_name"] == "그 외 건물"
    assert fallback["ssids"] == ["catholic_univ", "catholic_건물명", "사무실 호실명"]
    assert fallback["steps"] == first["steps"]


def test_kakao_place_detail_parser_normalizes_weekdays_breaks_and_holidays():
    opening_hours = parse_place_detail_opening_hours(_fixture_json("kakao_place_detail.json"))

    assert opening_hours["mon"] == "08:00 ~ 21:00"
    assert opening_hours["fri"] == "08:00 ~ 21:00"
    assert opening_hours["sat"] == "10:00 ~ 18:00"
    assert opening_hours["sun"] == "휴무"
    assert opening_hours["mon_break"] == "14:00 ~ 15:00"
    assert opening_hours["holiday_notice"] == "매주 일요일, 공휴일"


def test_kakao_place_detail_parser_preserves_24_hour_days():
    opening_hours = parse_place_detail_opening_hours(
        {
            "open_hours": {
                "all": {
                    "periods": [
                        {
                            "period_title": "기본 영업시간",
                            "days": [
                                {
                                    "day_of_the_week": day,
                                    "on_days": {"start_end_time_desc": "24시간 운영"},
                                }
                                for day in ("월", "화", "수", "목", "금", "토", "일")
                            ],
                        }
                    ]
                }
            }
        }
    )

    assert opening_hours["mon"] == "24시간 운영"
    assert opening_hours["sun"] == "24시간 운영"
