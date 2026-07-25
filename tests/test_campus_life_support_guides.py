from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from songsim_campus import services
from songsim_campus.db import connection, init_db
from songsim_campus.ingest import campus_life_support_guides as campus_life_support_guides_ingest
from songsim_campus.ingest.campus_life_support_guides import (
    DisabilitySupportGuideSource,
    FacilityRentalGuideSource,
    HealthCenterGuideSource,
    HospitalUseGuideSource,
    ITServiceGuideSource,
    LostFoundGuideSource,
    MobilitySafetyGuideSource,
    ParkingGuideSource,
    StudentCounselingGuideSource,
    StudentReservistGuideSource,
)
from songsim_campus.mcp_server import build_mcp
from songsim_campus.services import (
    list_campus_life_support_guides,
    refresh_campus_life_support_guides_from_source,
    run_admin_sync,
    sync_official_snapshot,
)
from songsim_campus.settings import clear_settings_cache

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _guide_row(
    *,
    topic: str,
    title: str,
    summary: str,
    steps: list[str],
    links: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "topic": topic,
        "title": title,
        "summary": summary,
        "steps": steps,
        "links": links or [],
        "source_url": "https://www.catholic.ac.kr/ko/campuslife/health.do",
        "source_tag": "cuk_campus_life_support_guides",
        "last_synced_at": "2026-03-20T00:00:00+09:00",
    }


def test_campus_life_support_source_defaults() -> None:
    health = HealthCenterGuideSource()
    lost_found = LostFoundGuideSource()
    parking = ParkingGuideSource()
    mobility_safety = MobilitySafetyGuideSource()
    facility_rental = FacilityRentalGuideSource()
    student_counseling = StudentCounselingGuideSource()
    disability_support = DisabilitySupportGuideSource()
    student_reservist = StudentReservistGuideSource()
    hospital_use = HospitalUseGuideSource()
    it_service = ITServiceGuideSource()
    career_counseling_source = getattr(
        campus_life_support_guides_ingest,
        "CareerCounselingGuideSource",
        None,
    )

    assert career_counseling_source is not None
    career_counseling = career_counseling_source()
    assert health.topic == "health_center"
    assert lost_found.topic == "lost_found"
    assert parking.topic == "parking"
    assert mobility_safety.topic == "mobility_safety"
    assert facility_rental.topic == "facility_rental"
    assert student_counseling.topic == "student_counseling"
    assert disability_support.topic == "disability_support"
    assert student_reservist.topic == "student_reservist"
    assert hospital_use.topic == "hospital_use"
    assert it_service.topic == "it_service"
    assert career_counseling.topic == "career_counseling"
    assert health.source_tag == "cuk_campus_life_support_guides"
    assert lost_found.source_tag == "cuk_campus_life_support_guides"
    assert parking.source_tag == "cuk_campus_life_support_guides"
    assert mobility_safety.source_tag == "cuk_campus_life_support_guides"
    assert facility_rental.source_tag == "cuk_campus_life_support_guides"
    assert student_counseling.source_tag == "cuk_campus_life_support_guides"
    assert disability_support.source_tag == "cuk_campus_life_support_guides"
    assert student_reservist.source_tag == "cuk_campus_life_support_guides"
    assert hospital_use.source_tag == "cuk_campus_life_support_guides"
    assert it_service.source_tag == "cuk_campus_life_support_guides"
    assert career_counseling.source_tag == "cuk_campus_life_support_guides"
    assert health.url.endswith("/campuslife/health.do")
    assert lost_found.url.endswith("/campuslife/find.do")
    assert parking.url.endswith("/about/location_songsim.do")
    assert mobility_safety.url.endswith("/service/safety.do")
    assert facility_rental.url.endswith("/campuslife/rent_songsim.do")
    assert student_counseling.url.endswith("/campuslife/counsel.do")
    assert disability_support.url.endswith("/campuslife/disability_service.do")
    assert student_reservist.url.endswith("/campuslife/student_reservist.do")
    assert hospital_use.url.endswith("/campuslife/hospital1.do")
    assert it_service.url.endswith("/campuslife/itservice.do")
    assert career_counseling.url == (
        "https://career.catholic.ac.kr/career/job/job_counseling.do"
    )


def test_mobility_safety_guide_parser_extracts_expected_core_details() -> None:
    rows = MobilitySafetyGuideSource().parse(
        _fixture("safety.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["개인형 이동장치 안전관리교육"]
    row = rows[0]
    assert row["topic"] == "mobility_safety"
    assert row["source_tag"] == "cuk_campus_life_support_guides"
    assert row["summary"] == "개인형 이동장치 운행 전 반드시 교육영상을 시청해주시기 바랍니다."
    assert (
        row["steps"][0]
        == "개인형 이동장치 운행 전 반드시 교육영상을 시청해주시기 바랍니다."
    )
    assert any(
        step == "※ '개인형 이동장치 안전관리 교육영상' [서울시교육청]"
        for step in row["steps"]
    )
    assert any(step == "1. 면허(원동기 이상) 소지자만 운전" for step in row["steps"])
    assert any(step == "2. 인명보호 안전장구 착용(헬멧, 보호대) 하기" for step in row["steps"])
    assert any(step == "3. 1인 탑습(동승 금지)" for step in row["steps"])
    assert any(
        step == "4. 주행 중 휴대전화, 이어폰 등 디지털기기 사용 금지"
        for step in row["steps"]
    )
    assert any(
        step == "5. 교통 법규 및 안전 속도(최대속도제한 20km/h) 준수"
        for step in row["steps"]
    )
    assert any(step == "6. 지정 주차구역 이외 주차 금지" for step in row["steps"])
    assert any(
        step == "7. 야간 운행 시 전조등 및 반사장치 등 안전장구 장착"
        for step in row["steps"]
    )
    assert any(
        step == "8. 교차로 진입 시 서행 및 횡당보도 통행 시 탑승 금지"
        for step in row["steps"]
    )
    assert any(step == "9. 음주운전 및 무면허운전 금지" for step in row["steps"])
    assert any(
        step
        == (
            "가톨릭대학교 홈페이지 > 가대소개 > 규정 > 규정정보시스템 > "
            "「가톨릭대학교 개인형 이동장치 안전관리 규정」"
        )
        for step in row["steps"]
    )
    assert not any(step == "주차구역" for step in row["steps"])
    assert row["links"] == [
        {
            "label": "교육영상",
            "url": "https://www.catholic.ac.kr/ko/newsroom/safety01.do?mode=view&articleNo=265485&article.offset=0&articleLimit=16",
        },
        {
            "label": "규정 바로가기",
            "url": "http://rule.catholic.ac.kr:8080/lmxsrv/main/main.srv",
        },
    ]


def test_health_center_guide_parser_extracts_expected_core_details() -> None:
    rows = HealthCenterGuideSource().parse(
        _fixture("health.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["보건실"]
    row = rows[0]
    assert row["topic"] == "health_center"
    assert row["source_tag"] == "cuk_campus_life_support_guides"
    assert row["summary"].startswith("보건실은 학생과 교직원의 건강을 유지ㆍ증진")
    assert any(step == "위치: 비르투스관 1층 104호" for step in row["steps"])
    assert any(
        step == "운영시간: 08:30 ~ 17:30 (점심시간 12시 ~ 13시)"
        for step in row["steps"]
    )
    assert any(
        "트리니티 → 보건실 → 방문시간, 방문목적 접수 후 방문" in step
        for step in row["steps"]
    )
    assert any(step == "응급처치" for step in row["steps"])
    assert any(step == "목발, 휠체어 의료보조기 대여" for step in row["steps"])
    assert row["links"]
    assert row["links"][0]["label"] == "보건실 방문접수 바로가기"


def test_lost_found_guide_parser_extracts_expected_core_details() -> None:
    rows = LostFoundGuideSource().parse(
        _fixture("find.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["유실물 찾기"]
    row = rows[0]
    assert row["topic"] == "lost_found"
    assert row["source_tag"] == "cuk_campus_life_support_guides"
    assert row["summary"] == (
        "유실물을 취득한 자는 관리부서인 학생지원팀(N109)에 유실물을 인계할 수 있습니다."
    )
    assert any("소유자 신분 확인" in step for step in row["steps"])
    assert any("유실물 정보를 게시하고 있습니다" in step for step in row["steps"])
    assert any("6개월 간 학생지원팀에 보관" in step for step in row["steps"])


def test_parking_guide_parser_extracts_expected_core_details() -> None:
    rows = ParkingGuideSource().parse(
        _fixture("location_songsim.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["주차요금안내"]
    row = rows[0]
    assert row["topic"] == "parking"
    assert row["source_tag"] == "cuk_campus_life_support_guides"
    assert row["summary"].startswith("교직원, 학생(학부, 대학원생)")
    assert any("정기권 발급 준비 서류" in step for step in row["steps"])
    assert any("할인권" in step for step in row["steps"])
    assert any("일반차량" in step for step in row["steps"])
    assert any("주차관리실(K102호 / K관 1층 안내데스크 옆)" in step for step in row["steps"])


def test_facility_rental_guide_parser_extracts_expected_core_details() -> None:
    rows = FacilityRentalGuideSource().parse(
        _fixture("rent_songsim.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "콘서트홀",
        "미카엘홀",
        "학생미래인재관(소피이바라관) Hall 1855",
        "김수환관 컨퍼런스룸(K366)",
        "김수환관 계단식 강의실(K267)",
        "김수환관 실내체육관",
        "정진석추기경약학관 계단식 강의실(NP117)",
        "모니카홀(SH304)",
        "PC실습실",
        "강의실 대관료",
    ]

    (
        concert_hall,
        mikael_hall,
        hall1855,
        conference_room,
        k267,
        gym,
        np117,
        monica,
        pc_room,
        lecture_rental,
    ) = rows
    assert concert_hall["topic"] == "facility_rental"
    assert concert_hall["source_tag"] == "cuk_campus_life_support_guides"
    assert concert_hall["summary"] == "1~4시간: 2,000,000 원"
    assert concert_hall["steps"] == [
        "1~4시간: 2,000,000 원",
        "4~8시간: 3,000,000원",
        "※ 전기사용료 : 120,000원 / h, 냉난방사용료 : 200,000원 / h",
        "※ 1,000명 규모",
    ]
    assert concert_hall["links"] == []
    assert mikael_hall["steps"][0] == "1~4시간: 1,000,000 원"
    assert hall1855["steps"][0] == "1~4시간: 400,000 원"
    assert conference_room["steps"][0] == "1~4시간: 1,200,000 원"
    assert k267["steps"][0] == "1~4시간: 600,000 원"
    assert gym["steps"][-1] == "※ 747M² 규모 (226평)"
    assert np117["steps"][-1] == "※ 162명 규모"
    assert monica["steps"][-1] == "※ 204명 규모"
    assert pc_room["steps"] == [
        "1~4시간: 200,000 원",
        "4~8시간: 300,000원",
        "※ 전기사용료 : 20,000원 / h, 냉난방사용료 : 20,000원 / h",
        "※ 50명 이내",
        "1~4시간: 300,000 원",
        "4~8시간: 500,000원",
        "※ 전기사용료 : 30,000원 / h, 냉난방사용료 : 30,000원 / h",
        "※ 50명 이상",
    ]
    assert lecture_rental["summary"] == (
        "건물별 코드 : 니콜스관(N), 다솔관(D), 마리아관(M), 미카엘관(H), "
        "비르투스관(V), 콘서트홀(CH), 김수환관(K), 정진석추기경약학관(NP), "
        "성심관(SH)"
    )
    assert lecture_rental["steps"][0].startswith("건물별 코드 : 니콜스관(N)")
    assert any("문의 : 시설관재팀 02-2164-4146" in step for step in lecture_rental["steps"])
    assert any("15~50명" in step for step in lecture_rental["steps"])


def test_student_counseling_guide_parser_extracts_expected_core_details() -> None:
    rows = StudentCounselingGuideSource().parse(
        _fixture("counsel.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "학생생활상담소",
        "인권센터(성폭력상담소)",
        "일반대학원 대학원상담실",
    ]
    first, second, third = rows
    assert first["topic"] == "student_counseling"
    assert first["summary"].startswith("학생생활상담소는 본교 학생들이 대학생활에 보다 잘 적응")
    assert any("위치 : 니콜스관 N121호" in step for step in first["steps"])
    assert any("전화번호 : 02-2164-4640" in step for step in first["steps"])
    assert first["links"] == [
        {
            "label": "홈페이지 바로가기",
            "url": "https://counseling.catholic.ac.kr/counseling/index.do",
        }
    ]
    assert second["summary"].startswith(
        "인권센터(성폭력상담소)는 모든 구성원(학생·교직원·교원)의 인권침해"
    )
    assert any("위치 : 니콜스관 N118호" in step for step in second["steps"])
    assert any("이메일 : humanrights@catholic.ac.kr" in step for step in second["steps"])
    assert second["links"] == [
        {
            "label": "홈페이지 바로가기",
            "url": "https://humanrights.catholic.ac.kr/humanrights/index.do",
        }
    ]
    assert third["summary"].startswith(
        "대학원상담실은 일반대학원 심리학 전공 수련 기관으로써"
    )
    assert any("위치 : 니콜스관 N314호" in step for step in third["steps"])
    assert any("이용시간 : 10:00 ~ 17:00" in step for step in third["steps"])
    assert third["links"] == [
        {
            "label": "홈페이지 바로가기",
            "url": "https://www.catholic.ac.kr/ko/psychology/graduate/graduate-school.do",
        }
    ]


def test_career_counseling_guide_parser_extracts_expected_core_details() -> None:
    source_cls = getattr(campus_life_support_guides_ingest, "CareerCounselingGuideSource", None)
    assert source_cls is not None

    rows = source_cls().parse(
        _fixture("job_counseling.do.html"),
        fetched_at="2026-05-07T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["진로/취업 상담"]
    row = rows[0]
    assert row["topic"] == "career_counseling"
    assert row["source_tag"] == "cuk_campus_life_support_guides"
    assert row["summary"] == "가톨릭대학교 학부생 및 졸업생"
    assert any(step == "상담대상" for step in row["steps"])
    assert any(step == "가톨릭대학교 학부생 및 졸업생" for step in row["steps"])
    assert any("전공선택, 복수전공 선택" in step for step in row["steps"])
    assert any("전문 취업진로상담사와의 1:1 개인별 맞춤 상담" in step for step in row["steps"])
    assert any(
        "트리니티 → AI코디(aicodi.catholic.ac.kr) → 통합상담 → 진로취업상담 → 상담신청"
        in step
        for step in row["steps"]
    )
    assert row["links"] == [
        {
            "label": "aicodi.catholic.ac.kr",
            "url": "https://aicodi.catholic.ac.kr/",
        }
    ]


def test_it_service_guide_parser_extracts_expected_core_details() -> None:
    rows = ITServiceGuideSource().parse(
        _fixture("itservice.do.html"),
        fetched_at="2026-05-07T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == [
        "uCUPS 서비스",
        "웹메일 서비스",
        "카카오채널 이용안내",
        "Microsoft Office 365 Program",
        "마리아관 실습실 이용안내",
        "바이러스 백신 설치",
    ]
    assert {row["topic"] for row in rows} == {"it_service"}
    assert {row["source_tag"] for row in rows} == {"cuk_campus_life_support_guides"}

    ucups, webmail, kakao_channel, office365, maria_lab, v3 = rows
    assert ucups["summary"] == "출력물 사용관련 오류 해결방법 안내"
    assert any("출력물 조회시 빈페이지만 보이는 경우" in step for step in ucups["steps"])
    assert ucups["links"] == [
        {
            "label": "출력프로그램(Report Designer 5.0 OCX Viewer) 설치",
            "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/ReportDesigner.exe",
        }
    ]

    assert webmail["summary"] == "신청방법"
    assert any("회원가입 신청 후, 관리자의 승인 후 이용 가능" in step for step in webmail["steps"])
    assert any("6개월간 로그인 기록이 없는 ID(계정)" in step for step in webmail["steps"])
    assert any("전화번호: 02 - 740 - 9749" in step for step in webmail["steps"])
    assert webmail["links"] == [
        {
            "label": "웹메일 홈페이지 바로가기",
            "url": "https://zm902.mailplug.com/member/login?host_domain=catholic.ac.kr&",
        },
        {
            "label": "웹메일 공지사항 바로가기",
            "url": "https://www.catholic.ac.kr/ko/service/webmail_notice.do",
        },
    ]

    assert kakao_channel["summary"].startswith("‘가톨릭대학교 성심교정’ 카카오채널")
    assert any("가톨릭대학교성심교정" in step for step in kakao_channel["steps"])
    assert kakao_channel["links"] == [
        {"label": "홈페이지 바로가기", "url": "http://pf.kakao.com/_xeYxgan"}
    ]

    assert office365["summary"].startswith("Microsoft에서는 학생과 교직원에게 무상")
    assert any("트리니티 접속" in step for step in office365["steps"])
    assert any("졸업생, 수료생은 이용 불가" in step for step in office365["steps"])

    assert maria_lab["summary"].startswith("교내 모든 알림 사항은 가대톡")
    assert any("명칭: 제1실습실" in step and "장소: M307" in step for step in maria_lab["steps"])
    assert any("사용가능한 S/W: 한글, MS-OFFICE, SPSS" in step for step in maria_lab["steps"])

    assert v3["summary"] == (
        "교내 사용자들을 위한 컴퓨터 바이러스 백신입니다. (교내에서만 설치 가능합니다.)"
    )
    assert any("V3백신 Agent 파일" in step for step in v3["steps"])
    assert v3["links"] == [
        {"label": "V3 백신 설치페이지 바로가기", "url": "http://mypc.catholic.ac.kr:8810/"}
    ]


def test_disability_support_guide_parser_extracts_expected_core_details() -> None:
    rows = DisabilitySupportGuideSource().parse(
        _fixture("disability_service.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["장애학생지원센터"]
    row = rows[0]
    assert row["topic"] == "disability_support"
    assert row["summary"].startswith("장애학생지원센터에서는 장애학생이 학내에서 원만하게 학습")
    assert any("학습지원 선수강신청제도" in step for step in row["steps"])
    assert any("도우미지원" in step for step in row["steps"])
    assert any("장애학생 도우미" in step for step in row["steps"])
    assert any("유관부서 및 동아리 안내" in step for step in row["steps"])
    assert any("위치 : 니콜스관 N109호" in step for step in row["steps"])
    assert any("장애인식개선 가이드 북" in step for step in row["steps"])
    assert row["links"] == [
        {
            "label": "장애인식개선 가이드 북",
            "url": "https://www.catholic.ac.kr/_res/cuk/ko/etc/disability_guidebook.pdf",
        },
        {
            "label": "캠퍼스배리어프리 온라인 가이드북",
            "url": "https://sites.google.com/view/cukcampable/홈",
        },
    ]


def test_student_reservist_guide_parser_extracts_expected_core_details() -> None:
    rows = StudentReservistGuideSource().parse(
        _fixture("student_reservist.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["직장예비군 가톨릭대학교 대대"]
    row = rows[0]
    assert row["topic"] == "student_reservist"
    assert row["summary"].startswith("직장예비군 가톨릭대학교 대대")
    assert any("예비군 민원상담실 전화번호" in step for step in row["steps"])
    assert any("신고시기 및 방법" in step for step in row["steps"])
    assert any("훈련안내" in step for step in row["steps"])
    assert any("부천 예비군훈련장" in step for step in row["steps"])
    assert row["links"] == [
        {
            "label": "예비군대대 홈페이지 바로가기",
            "url": "https://yebigun.catholic.ac.kr/yebigun/index.do",
        }
    ]


def test_hospital_use_guide_parser_extracts_expected_core_details() -> None:
    rows = HospitalUseGuideSource().parse(
        _fixture("hospital1.do.html"),
        fetched_at="2026-03-20T00:00:00+09:00",
    )

    assert [row["title"] for row in rows] == ["부속병원이용"]
    row = rows[0]
    assert row["topic"] == "hospital_use"
    assert row["summary"].startswith("가톨릭중앙의료원 CATHOLIC MEDICAL CENTER")
    assert any("주소 : 서울시 서초구 반포대로 222" in step for step in row["steps"])
    assert any("전화번호 : 1588-1511" in step for step in row["steps"])
    assert row["links"] == [
        {
            "label": "서울성모병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital2.do",
        },
        {
            "label": "여의도성모병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital3.do",
        },
        {
            "label": "의정부성모병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital4.do",
        },
        {
            "label": "부천성모병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital5.do",
        },
        {
            "label": "은평성모병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital6.do",
        },
        {
            "label": "인천성모병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital7.do",
        },
        {
            "label": "성빈센트병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital8.do",
        },
        {
            "label": "대전성모병원",
            "url": "https://www.catholic.ac.kr/ko/campuslife/hospital9.do",
        },
    ]


def test_campus_life_support_guides_refresh_replace_and_list(app_env) -> None:
    init_db()

    class FakeGuideSource:
        def __init__(self, row: dict[str, object]):
            self.row = row

        def fetch(self) -> str:
            return "<guide />"

        def parse(self, html: str, *, fetched_at: str):
            assert html == "<guide />"
            return [{**self.row, "last_synced_at": fetched_at}]

    with connection() as conn:
        refresh_campus_life_support_guides_from_source(
            conn,
            sources=[
                FakeGuideSource(
                    _guide_row(
                        topic="health_center",
                        title="보건실",
                        summary="보건실은 학생과 교직원의 건강을 유지ㆍ증진합니다.",
                        steps=["위치: 비르투스관 1층 104호"],
                    )
                ),
                FakeGuideSource(
                    _guide_row(
                        topic="lost_found",
                        title="유실물 찾기",
                        summary="유실물을 취득한 자는 학생지원팀에 인계할 수 있습니다.",
                        steps=["6개월 간 학생지원팀에 보관"],
                    )
                ),
                FakeGuideSource(
                    _guide_row(
                        topic="parking",
                        title="주차요금안내",
                        summary="교직원, 학생(학부, 대학원생) 정기권 안내",
                        steps=["일반차량: 10분당 500원"],
                    )
                ),
                FakeGuideSource(
                    _guide_row(
                        topic="mobility_safety",
                        title="개인형 이동장치 안전관리교육",
                        summary="개인형 이동장치 운행 전 반드시 교육영상을 시청해주시기 바랍니다.",
                        steps=["개인형 이동장치 운행 전 반드시 교육영상을 시청해주시기 바랍니다."],
                        links=[
                            {
                                "label": "교육영상",
                                "url": "https://www.catholic.ac.kr/ko/newsroom/safety01.do?mode=view&articleNo=265485&article.offset=0&articleLimit=16",
                            },
                            {
                                "label": "규정 바로가기",
                                "url": "http://rule.catholic.ac.kr:8080/lmxsrv/main/main.srv",
                            },
                        ],
                    )
                ),
            ],
        )
        all_guides = list_campus_life_support_guides(conn, limit=20)
        parking = list_campus_life_support_guides(conn, topic="parking", limit=20)
        mobility_safety = list_campus_life_support_guides(conn, topic="mobility_safety", limit=20)

        refresh_campus_life_support_guides_from_source(
            conn,
            sources=[
                FakeGuideSource(
                    _guide_row(
                        topic="health_center",
                        title="보건실",
                        summary="보건실은 학생과 교직원의 건강을 유지ㆍ증진합니다.",
                        steps=["운영시간: 08:30 ~ 17:30"],
                    )
                )
            ],
        )
        replaced = list_campus_life_support_guides(conn, limit=20)

    assert [(item.topic, item.title) for item in all_guides] == [
        ("health_center", "보건실"),
        ("lost_found", "유실물 찾기"),
        ("mobility_safety", "개인형 이동장치 안전관리교육"),
        ("parking", "주차요금안내"),
    ]
    assert [(item.topic, item.title) for item in parking] == [("parking", "주차요금안내")]
    assert [(item.topic, item.title) for item in mobility_safety] == [
        ("mobility_safety", "개인형 이동장치 안전관리교육")
    ]
    assert [(item.topic, item.title) for item in replaced] == [("health_center", "보건실")]


def test_campus_life_support_dataset_is_wired_into_sync_and_readiness(app_env, monkeypatch):
    init_db()

    assert "campus_life_support_guides" in services.SYNC_DATASET_TABLES
    assert services.PUBLIC_READY_DATASET_POLICIES["campus_life_support_guides"] == "core"
    assert "campus_life_support_guides" in services.PUBLIC_READY_CORE_DATASETS
    assert "campus_life_support_guides" in services.ADMIN_SYNC_TARGETS

    monkeypatch.setattr(
        "songsim_campus.services.refresh_campus_life_support_guides_from_source",
        lambda conn, sources=None, fetched_at=None: [],
    )

    with connection():
        run = run_admin_sync(target="campus_life_support_guides")

    assert run.status == "success"
    assert run.summary == {"campus_life_support_guides": 0}


def test_campus_life_support_guides_accepts_newer_topics(app_env) -> None:
    init_db()

    with connection() as conn:
        mobility_guides = list_campus_life_support_guides(
            conn,
            topic="mobility_safety",
            limit=5,
        )
        career_guides = list_campus_life_support_guides(
            conn,
            topic="career_counseling",
            limit=5,
        )
        it_guides = list_campus_life_support_guides(
            conn,
            topic="it_service",
            limit=5,
        )

    assert mobility_guides == []
    assert career_guides == []
    assert it_guides == []


def test_campus_life_support_http_and_mcp_surfaces(client, app_env, monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    init_db()

    class FakeGuideSource:
        def __init__(self, row: dict[str, object]):
            self.row = row

        def fetch(self) -> str:
            return "<guide />"

        def parse(self, html: str, *, fetched_at: str):
            assert html == "<guide />"
            return [{**self.row, "last_synced_at": fetched_at}]

    with connection() as conn:
        refresh_campus_life_support_guides_from_source(
            conn,
            sources=[
                FakeGuideSource(
                    _guide_row(
                        topic="health_center",
                        title="보건실",
                        summary="보건실은 학생과 교직원의 건강을 유지ㆍ증진합니다.",
                        steps=["위치: 비르투스관 1층 104호", "운영시간: 08:30 ~ 17:30"],
                    )
                ),
                FakeGuideSource(
                    _guide_row(
                        topic="parking",
                        title="주차요금안내",
                        summary="교직원, 학생(학부, 대학원생) 정기권 안내",
                        steps=["일반차량: 10분당 500원"],
                    )
                ),
                FakeGuideSource(
                    _guide_row(
                        topic="career_counseling",
                        title="진로/취업 상담",
                        summary="가톨릭대학교 학부생 및 졸업생",
                        steps=[
                            "가톨릭대학교 학부생 및 졸업생",
                            (
                                "트리니티 → AI코디(aicodi.catholic.ac.kr) → 통합상담 "
                                "→ 진로취업상담 → 상담신청"
                            ),
                        ],
                    )
                ),
                FakeGuideSource(
                    _guide_row(
                        topic="it_service",
                        title="웹메일 서비스",
                        summary="웹메일 홈페이지로 접속하여 회원가입 메뉴를 통해 등록합니다.",
                        steps=[
                            "웹메일 홈페이지로 접속하여 회원가입 메뉴를 통해 등록합니다.",
                            "Microsoft Office 365 Program",
                        ],
                    )
                ),
            ],
        )

    response = client.get("/campus-life-support-guides", params={"topic": "parking", "limit": 5})
    career_response = client.get(
        "/campus-life-support-guides",
        params={"topic": "career_counseling", "limit": 5},
    )
    it_response = client.get(
        "/campus-life-support-guides",
        params={"topic": "it_service", "limit": 5},
    )
    assert response.status_code == 200
    http_payload = response.json()
    assert http_payload[0]["topic"] == "parking"
    assert http_payload[0]["source_tag"] == "cuk_campus_life_support_guides"
    assert career_response.status_code == 200
    assert career_response.json()[0]["topic"] == "career_counseling"
    assert it_response.status_code == 200
    assert it_response.json()[0]["topic"] == "it_service"

    monkeypatch.setenv("SONGSIM_APP_MODE", "public_readonly")
    clear_settings_cache()

    async def main():
        mcp = build_mcp()
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        tool_result = await mcp.call_tool(
            "tool_list_campus_life_support_guides",
            {"topic": "health_center", "limit": 5},
        )
        resource_result = await mcp.read_resource("songsim://campus-life-support-guide")
        return (
            {tool.name: tool.model_dump(by_alias=True) for tool in tools},
            {str(resource.uri) for resource in resources},
            json.loads(tool_result[0].text),
            json.loads(list(resource_result)[0].content),
        )

    tool_payloads, resource_uris, tool_payload, resource_payload = asyncio.run(main())
    clear_settings_cache()

    assert "tool_list_campus_life_support_guides" in tool_payloads
    assert "songsim://campus-life-support-guide" in resource_uris
    assert "보건실" in tool_payloads["tool_list_campus_life_support_guides"]["description"]
    assert "진로/취업 상담" in tool_payloads["tool_list_campus_life_support_guides"]["description"]
    assert "IT서비스" in tool_payloads["tool_list_campus_life_support_guides"]["description"]
    assert "parking" in (
        tool_payloads["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "career_counseling" in (
        tool_payloads["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert "it_service" in (
        tool_payloads["tool_list_campus_life_support_guides"]["inputSchema"]["properties"]["topic"][
            "description"
        ]
    )
    assert tool_payload["topic"] == "health_center"
    assert tool_payload["guide_summary"].startswith("보건실은 학생과 교직원의 건강")
    assert {item["topic"] for item in resource_payload} == {
        "career_counseling",
        "health_center",
        "it_service",
        "parking",
    }


def test_sync_official_snapshot_includes_campus_life_support_and_pc_software(app_env, monkeypatch):
    init_db()
    call_order: list[str] = []

    def stub(name: str):
        def inner(*_args, **_kwargs):
            call_order.append(name)
            return []

        return inner

    stubs = {
        "refresh_places_from_campus_map": "places",
        "refresh_campus_facilities_from_source": "campus_facilities",
        "refresh_library_hours_from_library_page": "library_hours",
        "refresh_facility_hours_from_facilities_page": "facility_hours",
        "refresh_campus_dining_menus_from_facilities_page": "dining_menus",
        "refresh_courses_from_subject_search": "courses",
        "refresh_notices_from_notice_board": "notices",
        "refresh_affiliated_notices_from_sources": "affiliated_notices",
        "refresh_academic_calendar_from_source": "academic_calendar",
        "refresh_certificate_guides_from_certificate_page": "certificate_guides",
        "refresh_leave_of_absence_guides_from_source": "leave_of_absence_guides",
        "refresh_academic_status_guides_from_source": "academic_status_guides",
        "refresh_registration_guides_from_source": "registration_guides",
        "refresh_class_guides_from_source": "class_guides",
        "refresh_seasonal_semester_guides_from_source": "seasonal_semester_guides",
        "refresh_academic_milestone_guides_from_source": "academic_milestone_guides",
        "refresh_student_activity_guides_from_source": "student_activity_guides",
        "refresh_student_activity_notices_from_source": "student_activity_notices",
        "refresh_student_exchange_guides_from_source": "student_exchange_guides",
        "refresh_student_exchange_partners_from_source": "student_exchange_partners",
        "refresh_about_resource_guides_from_source": "about_resource_guides",
        "refresh_service_policy_guides_from_source": "service_policy_guides",
        "refresh_newsroom_posts_from_source": "newsroom_posts",
        "refresh_dormitory_guides_from_source": "dormitory_guides",
        "refresh_phone_book_entries_from_source": "phone_book_entries",
        "refresh_campus_life_support_guides_from_source": "campus_life_support_guides",
        "refresh_pc_software_entries_from_source": "pc_software_entries",
        "refresh_scholarship_guides_from_source": "scholarship_guides",
        "refresh_academic_support_guides_from_source": "academic_support_guides",
        "refresh_wifi_guides_from_source": "wifi_guides",
        "refresh_transport_guides_from_location_page": "transport_guides",
    }
    for attr, name in stubs.items():
        monkeypatch.setattr(f"songsim_campus.services.{attr}", stub(name))

    with connection() as conn:
        summary = sync_official_snapshot(conn)

    assert "campus_life_support_guides" in summary
    assert "student_activity_notices" in summary
    assert "about_resource_guides" in summary
    assert "service_policy_guides" in summary
    assert "newsroom_posts" in summary
    assert "pc_software_entries" in summary
    assert "campus_life_support_guides" in call_order
    assert "about_resource_guides" in call_order
    assert "service_policy_guides" in call_order
    assert "newsroom_posts" in call_order
    assert "pc_software_entries" in call_order
