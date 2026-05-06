from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from .mcp_public_serializers import (
    serialize_public_about_resource_guide,
    serialize_public_academic_milestone_guide,
    serialize_public_academic_status_guide,
    serialize_public_academic_support_guide,
    serialize_public_campus_life_notice,
    serialize_public_campus_life_support_guide,
    serialize_public_certificate_guide,
    serialize_public_class_guide,
    serialize_public_course,
    serialize_public_dining_menu,
    serialize_public_dormitory_guide,
    serialize_public_error,
    serialize_public_leave_of_absence_guide,
    serialize_public_nearby_restaurant,
    serialize_public_notice,
    serialize_public_pc_software_entry,
    serialize_public_place,
    serialize_public_registration_guide,
    serialize_public_restaurant_search,
    serialize_public_scholarship_guide,
    serialize_public_seasonal_semester_guide,
    serialize_public_student_activity_guide,
    serialize_public_student_exchange_guide,
    serialize_public_transport_guide,
    serialize_public_wifi_guide,
)
from .schemas import (
    ProfileCourseRef,
    ProfileInterests,
    ProfileNoticePreferences,
    ProfileUpdateRequest,
)
from .services import (
    InvalidRequestError,
    NotFoundError,
    create_profile,
    find_nearby_restaurants,
    get_class_periods,
    get_library_seat_status,
    get_place,
    get_profile_course_recommendations,
    get_profile_interests,
    get_profile_meal_recommendations,
    get_profile_timetable,
    list_about_resource_guides,
    list_academic_calendar,
    list_academic_milestone_guides,
    list_academic_status_guides,
    list_academic_support_guides,
    list_campus_life_notices,
    list_campus_life_support_guides,
    list_certificate_guides,
    list_class_guides,
    list_dormitory_guides,
    list_estimated_empty_classrooms,
    list_latest_notices,
    list_leave_of_absence_guides,
    list_profile_notices,
    list_registration_guides,
    list_scholarship_guides,
    list_seasonal_semester_guides,
    list_student_activity_guides,
    list_student_exchange_guides,
    list_transport_guides,
    list_wifi_guides,
    search_campus_dining_menus,
    search_courses,
    search_pc_software_entries,
    search_phone_book_entries,
    search_places,
    search_restaurants,
    search_student_exchange_partners,
    set_profile_interests,
    set_profile_notice_preferences,
    set_profile_timetable,
    update_profile,
)


def register_shared_tools(
    mcp: Any,
    connection_factory: Any,
    *,
    public_readonly: bool,
    tool_meta: Any,
) -> None:
    @mcp.tool(
        description=(
            "성심교정 학사일정을 읽을 때 사용합니다. academic_year, month, query로 "
            "개시일, 등록기간, 중간고사 같은 일정을 현재 스냅샷 기준으로 찾습니다."
            if public_readonly
            else "학교 학사일정 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_academic_calendar(
        academic_year: Annotated[int | None, Field(description="학년도 필터. 예: 2026")] = None,
        month: Annotated[
            int | None,
            Field(description="월 필터. 1-12 정수이며 해당 월과 겹치는 일정만 남깁니다."),
        ] = None,
        query: Annotated[
            str | None,
            Field(description="일정 제목 부분 검색. 예: 등록, 개시일, 중간고사"),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            try:
                events = list_academic_calendar(
                    conn,
                    academic_year=academic_year,
                    month=month,
                    query=query,
                    limit=limit,
                )
                return [item.model_dump() for item in events]
            except InvalidRequestError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            "학교 증명서 발급 안내를 읽을 때 사용합니다. "
            "재학증명서, 졸업증명서, 인터넷 증명발급, FAX 민원, 무인발급기 같은 "
            "정적 발급 안내를 현재 스냅샷 기준으로 돌려줍니다."
            if public_readonly
            else "학교 증명서 발급 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_certificate_guides(
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_certificate_guides(conn, limit=limit)
            if public_readonly:
                return [serialize_public_certificate_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 휴학 안내를 읽을 때 사용합니다. 휴학 신청방법, 군휴학, 질병휴학, "
                "직접 방문 제출 대상, 등록금 반환 기준, 휴복학 FAQ 같은 정적 안내를 "
                "current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 휴학 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_leave_of_absence_guides(
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_leave_of_absence_guides(conn, limit=limit)
            if public_readonly:
                return [serialize_public_leave_of_absence_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 장학제도 안내를 읽을 때 사용합니다. 장학생 자격, 장학금 신청, 장학금 지급, "
                "장학금 지급 규정 같은 baseline 안내와 공식 문서 링크를 current snapshot으로 "
                "돌려줍니다."
            )
            if public_readonly
            else "학교 장학제도 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_scholarship_guides(
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_scholarship_guides(conn, limit=limit)
            if public_readonly:
                return [serialize_public_scholarship_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 무선랜서비스 안내를 읽을 때 사용합니다. 건물별 SSID와 무선랜 접속 방법을 "
                "current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 무선랜서비스 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_wifi_guides(
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_wifi_guides(conn, limit=limit)
            if public_readonly:
                return [serialize_public_wifi_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학사지원팀 업무안내를 읽을 때 사용합니다. 휴복학, 학점교류, 성적, 졸업, "
                "교직 같은 업무구분별 담당업무와 문의처 전화번호를 current snapshot으로 "
                "돌려줍니다."
            )
            if public_readonly
            else "학교 학사지원팀 업무안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_academic_support_guides(
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_academic_support_guides(conn, limit=limit)
            if public_readonly:
                return [serialize_public_academic_support_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 학적변동 안내를 읽을 때 사용합니다. 복학, 자퇴, 재입학 같은 "
                "학적변동 절차와 자격 기준을 current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 학적변동 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_academic_status_guides(
        status: Annotated[
            str | None,
            Field(
                description=(
                    "학적변동 유형 필터. "
                    "return_from_leave, dropout, re_admission 중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_academic_status_guides(conn, status=status, limit=limit)
            if public_readonly:
                return [serialize_public_academic_status_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 주요전화번호 / 부서 연락처를 찾을 때 사용합니다. 보건실, 학사지원팀, "
                "트리니티 문의, 유실물 문의, 기숙사 운영팀 같은 campus-wide 연락처를 "
                "current snapshot으로 찾습니다."
            )
            if public_readonly
            else "학교 주요전화번호 / 부서 연락처 current snapshot을 검색합니다."
        ),
        meta=tool_meta,
    )
    def tool_search_phone_book(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "부서명, 업무, 내선번호 검색어. 예: 보건실, 학사지원팀, 트리니티, "
                    "유실물, 기숙사 운영팀"
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            entries = search_phone_book_entries(conn, query=query, limit=limit)
            return [item.model_dump() for item in entries]

    @mcp.tool(
        description=(
            (
                "생활지원 안내를 읽을 때 사용합니다. 보건실, 유실물, 성심교정 주차요금, "
                "학생상담, 장애학생지원센터, 예비군, 부속병원, 대관안내, "
                "개인형 이동장치 안전교육, 진로/취업 상담처럼 학생이 바로 행동에 "
                "옮길 수 있는 정적 안내를 current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 생활지원 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_campus_life_support_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "생활지원 안내 유형 필터. health_center, lost_found, parking, "
                    "mobility_safety, facility_rental, student_counseling, "
                    "disability_support, student_reservist, hospital_use, "
                    "career_counseling 중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            try:
                guides = list_campus_life_support_guides(conn, topic=topic, limit=limit)
                if public_readonly:
                    return [serialize_public_campus_life_support_guide(item) for item in guides]
                return [item.model_dump() for item in guides]
            except InvalidRequestError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            (
                "PC실과 설치 소프트웨어를 검색할 때 사용합니다. SPSS, 포토샵, "
                "Visual Studio, 마리아관 같은 query로 실습실과 소프트웨어 목록을 찾습니다."
            )
            if public_readonly
            else "학교 PC실 / 설치 소프트웨어 current snapshot을 검색합니다."
        ),
        meta=tool_meta,
    )
    def tool_search_pc_software(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "소프트웨어 또는 실습실 검색어. 예: SPSS, Photoshop, Visual Studio, 마리아관"
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            entries = search_pc_software_entries(conn, query=query, limit=limit)
            if public_readonly:
                return [serialize_public_pc_software_entry(item) for item in entries]
            return [item.model_dump() for item in entries]

    @mcp.tool(
        description=(
            (
                "학교 기숙사 안내를 읽을 때 사용합니다. 스테파노관, 안드레아관, "
                "프란치스코관 정보와 기숙사운영팀 연락처, 입사·퇴사 안내, 생활안내, "
                "기숙사비, 그리고 홈에 노출된 최신 공지 카드를 current snapshot으로 "
                "돌려줍니다."
            )
            if public_readonly
            else "학교 기숙사 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_dormitory_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "기숙사 안내 유형 필터. hall_info, quick_links, latest_notices, fees "
                    "중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_dormitory_guides(conn, topic=topic, limit=limit)
            if public_readonly:
                return [serialize_public_dormitory_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 등록 안내를 읽을 때 사용합니다. 등록금 고지서 조회, 등록금 납부 방법, "
                "등록금 반환 기준, 초과학기생/전액장학생 등록 같은 정적 안내를 "
                "current snapshot으로 "
                "돌려줍니다."
            )
            if public_readonly
            else "학교 등록 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_registration_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "등록 안내 유형 필터. bill_lookup, payment_and_return, "
                    "payment_by_student 중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_registration_guides(conn, topic=topic, limit=limit)
            if public_readonly:
                return [serialize_public_registration_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 수업 안내를 읽을 때 사용합니다. 수강신청 변경기간, 재수강 기준, "
                "수강과목취소, 수업평가, 공결 신청, 외국어강의 의무이수 같은 정적 안내를 "
                "current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 수업 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_class_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "수업 안내 유형 필터. registration_change, retake, "
                    "course_cancellation, course_evaluation, excused_absence, "
                    "foreign_language_requirement 중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_class_guides(conn, topic=topic, limit=limit)
            if public_readonly:
                return [serialize_public_class_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 계절학기 안내를 읽을 때 사용합니다. 계절학기 신청대상, 학점 제한, "
                "신청 시기, 신청절차 같은 정적 안내를 current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 계절학기 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_seasonal_semester_guides(
        topic: Annotated[
            str | None,
            Field(description="계절학기 안내 유형 필터. seasonal_semester를 사용합니다."),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_seasonal_semester_guides(conn, topic=topic, limit=limit)
            if public_readonly:
                return [serialize_public_seasonal_semester_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학교 성적·졸업 안내를 읽을 때 사용합니다. 성적평가 방법, 성적확인, "
                "결석이 수업시간의 4분의 1을 넘으면 어떻게 되는지, 졸업요건, "
                "졸업논문 제출 절차 같은 정적 안내를 current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 성적·졸업 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_academic_milestone_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "성적·졸업 안내 유형 필터. grade_evaluation, "
                    "graduation_requirement 중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_academic_milestone_guides(conn, topic=topic, limit=limit)
            if public_readonly:
                return [serialize_public_academic_milestone_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "학생활동 안내를 읽을 때 사용합니다. 학생회, 교지/언론, "
                "중앙동아리, 기관동아리, 사회봉사, ROTC 같은 학생활동 유형별 "
                "정적 안내를 current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학교 학생활동 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_student_activity_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "학생활동 안내 유형 필터. student_government, campus_media, "
                    "social_volunteering, rotc, central_clubs, institutional_clubs "
                    "중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_student_activity_guides(conn, topic=topic, limit=limit)
            if public_readonly:
                return [serialize_public_student_activity_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "가대소개 주요 정적 안내 자료를 읽을 때 사용합니다. 규정, 요람, "
                "학사제도안내책자, 캠퍼스투어, 연혁, 교회문헌, 예결산공고처럼 "
                "공식 링크와 접근 안내가 필요한 about resource를 current snapshot으로 "
                "돌려줍니다."
            )
            if public_readonly
            else "학교 가대소개 주요 정적 안내 자료 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_about_resource_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "가대소개 정적 안내 유형 필터. rules, university_bulletin, "
                    "academic_handbook, campus_tour, history, church_literature, "
                    "budget_account 중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            try:
                guides = list_about_resource_guides(conn, topic=topic, limit=limit)
                if public_readonly:
                    return [serialize_public_about_resource_guide(item) for item in guides]
                return [item.model_dump() for item in guides]
            except InvalidRequestError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            (
                "학생교류 안내를 읽을 때 사용합니다. 국내 학점교류 신청대상, "
                "학점교류 신청시기, 교류대학 현황, 교환학생 프로그램, 해외 교류프로그램 "
                "같은 정적 안내를 current snapshot으로 돌려줍니다."
            )
            if public_readonly
            else "학생교류 안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_student_exchange_guides(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "학생교류 안내 유형 필터. "
                    "domestic_credit_exchange, domestic_partner_universities, "
                    "exchange_student, exchange_programs 중 하나를 사용합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_student_exchange_guides(conn, topic=topic, limit=limit)
            if public_readonly:
                return [serialize_public_student_exchange_guide(item) for item in guides]
            return [item.model_dump() for item in guides]

    @mcp.tool(
        description=(
            (
                "해외협정대학 검색을 읽을 때 사용합니다. 국가/대륙/대학명으로 "
                "교환대학 목록을 current snapshot에서 찾습니다. 예: 네덜란드, "
                "Utrecht, EUROPE, 대만."
            )
            if public_readonly
            else "해외협정대학 current snapshot을 검색합니다."
        ),
        meta=tool_meta,
    )
    def tool_search_student_exchange_partners(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "대학명, 국가명, 대륙명 검색어. 예: 네덜란드, Utrecht, "
                    "EUROPE, 대만"
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            partners = search_student_exchange_partners(conn, query=query, limit=limit)
            return [item.model_dump() for item in partners]

    @mcp.tool(
        description=(
            (
                "사용자가 성심교정 건물명, 별칭, 시설명, "
                "교내 입점명, 생활 시설명으로 장소를 찾을 때 사용합니다. "
                "질문이 모호하면 먼저 이 tool을 쓰고, 단일 slug가 정해지면 "
                "tool_get_place로 넘어갑니다."
            )
            if public_readonly
            else "성심교정 건물, 도서관, 기준 위치를 한국어 이름이나 별칭으로 찾습니다."
        ),
        meta=tool_meta,
    )
    def tool_search_places(
        query: Annotated[
            str,
            Field(
                description=(
                    "찾고 싶은 건물명, 별칭, 시설명, 교내 입점명, 생활 시설명. "
                    "예: 중앙도서관, 중도, K관, 정문, 트러스트짐, 헬스장, 편의점, ATM"
                )
            ),
        ] = "",
        category: Annotated[
            str | None,
            Field(description="장소 카테고리 필터. 예: library, building, facility"),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 10입니다.")] = 10,
    ):
        with connection_factory() as conn:
            places = search_places(conn, query=query, category=category, limit=limit)
            if public_readonly:
                return [serialize_public_place(item) for item in places]
            return [item.model_dump() for item in places]

    @mcp.tool(
        description=(
            (
                "이미 장소 slug 또는 정확한 이름을 알고 있을 때 한 곳의 요약 정보를 가져옵니다. "
                "보통 tool_search_places 다음 단계에서 사용합니다."
            )
            if public_readonly
            else "이미 목적지를 알고 있을 때 장소 slug 또는 정확한 이름으로 한 곳을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_get_place(
        identifier: Annotated[
            str,
            Field(description="장소 slug 또는 정확한 이름. 예: central-library, 중앙도서관"),
        ]
    ):
        with connection_factory() as conn:
            try:
                place = get_place(conn, identifier)
                if public_readonly:
                    return serialize_public_place(place)
                return place.model_dump()
            except NotFoundError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            (
                "과목명, 코드, 교수, 학기, 교시 조건으로 현재 공개된 "
                "성심교정 개설과목을 찾을 때 사용합니다."
            )
            if public_readonly
            else (
                "현재 공개된 성심교정 개설과목을 과목명, 코드, 교수, 학기, "
                "교시 조건으로 찾습니다."
            )
        ),
        meta=tool_meta,
    )
    def tool_search_courses(
        query: Annotated[
            str,
            Field(description="과목명, 과목 코드, 교수명으로 검색할 문자열"),
        ] = "",
        year: Annotated[int | None, Field(description="학년도 필터. 예: 2026")] = None,
        semester: Annotated[int | None, Field(description="학기 필터. 예: 1, 2")] = None,
        period_start: Annotated[
            int | None,
            Field(description="교시 시작 번호 필터. 예: 7"),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            courses = search_courses(
                conn,
                query=query,
                year=year,
                semester=semester,
                period_start=period_start,
                limit=limit,
            )
            if public_readonly:
                return [serialize_public_course(item) for item in courses]
            return [item.model_dump() for item in courses]

    @mcp.tool(
        description=(
            "교시 번호를 실제 수업 시간으로 바꾸고 싶을 때 고정 교시표를 반환합니다."
            if public_readonly
            else "성심교정 교시 번호를 실제 시간으로 바꿀 수 있도록 고정 교시표를 반환합니다."
        ),
        meta=tool_meta,
    )
    def tool_get_class_periods():
        return [item.model_dump() for item in get_class_periods()]

    @mcp.tool(
        description=(
            (
                "중앙도서관 열람실 남은 좌석을 best-effort 실시간으로 확인할 때 사용합니다. "
                "열람실 남은 좌석, 중앙도서관 좌석 현황, 제1자유열람실 남은 좌석처럼 "
                "질문할 수 있고, 실시간 조회 실패 시 stale cache 또는 unavailable note로 "
                "안전하게 응답합니다."
            )
            if public_readonly
            else "중앙도서관 열람실 좌석 현황을 best-effort 실시간으로 조회합니다."
        ),
        meta=tool_meta,
    )
    def tool_get_library_seat_status(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "열람실 또는 좌석 관련 검색어. 예: 열람실 남은 좌석, 중앙도서관 좌석 현황, "
                    "제1자유열람실 남은 좌석"
                )
            ),
        ] = None,
    ):
        with connection_factory() as conn:
            return get_library_seat_status(conn, query=query).model_dump(exclude_none=True)

    @mcp.tool(
        description=(
            (
                "교내 공식 학식 3곳의 이번 주 메뉴를 찾을 때 사용합니다. "
                "학생식당 메뉴, 교내 식당 메뉴, 학식 메뉴처럼 물으면 전체를 돌려주고, "
                "카페 보나, 카페 멘사, 부온 프란조처럼 특정 매장을 물으면 "
                "해당 매장만 좁혀서 메뉴 텍스트와 원본 PDF 링크를 보여줍니다."
            )
            if public_readonly
            else "교내 공식 식당 메뉴를 질의별로 검색합니다."
        ),
        meta=tool_meta,
    )
    def tool_search_dining_menus(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "교내 식당 메뉴 질의. 예: 학생식당 메뉴, 교내 식당 메뉴, "
                    "카페 보나 메뉴, 카페 멘사 메뉴, 부온 프란조 이번 주 메뉴"
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 10입니다.")] = 10,
    ):
        with connection_factory() as conn:
            menus = search_campus_dining_menus(conn, query=query, limit=limit)
            if public_readonly:
                return [serialize_public_dining_menu(item) for item in menus]
            return [item.model_dump() for item in menus]

    @mcp.tool(
        description=(
            (
                "강의동에서 지금 비어 있을 가능성이 높은 강의실을 "
                "찾을 때 사용합니다. "
                "building은 대표 이름과 alias를 받을 수 있습니다. "
                "예: 니콜스관, 니콜스, N관, 김수환관. "
                "공식 실시간 데이터가 있으면 우선 사용하고, "
                "없으면 시간표 기준 예상 공실로 폴백합니다. "
                "결과에는 availability_mode와 다음 점유 시각을 함께 보여줍니다."
            )
            if public_readonly
            else (
                "특정 건물의 현재 공실을 조회하고, 실시간 소스가 없으면 "
                "시간표 기준 예상 공실로 폴백합니다."
            )
        ),
        meta=tool_meta,
    )
    def tool_list_estimated_empty_classrooms(
        building: Annotated[
            str,
            Field(
                description=(
                    "강의실을 확인할 건물 대표 이름 또는 alias. "
                    "예: 니콜스관, 니콜스, N관, K관, 김수환관"
                )
            ),
        ],
        at: Annotated[
            str | None,
            Field(description="기준 시각 ISO 8601 문자열. 없으면 현재 시각을 사용합니다."),
        ] = None,
        year: Annotated[
            int | None,
            Field(description="학년도. 없으면 기준 시각의 현재 학기를 사용합니다."),
        ] = None,
        semester: Annotated[
            int | None,
            Field(description="학기. 없으면 기준 시각의 현재 학기를 사용합니다."),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 10입니다.")] = 10,
    ):
        with connection_factory() as conn:
            try:
                from datetime import datetime

                parsed_at = datetime.fromisoformat(at) if at else None
                payload = list_estimated_empty_classrooms(
                    conn,
                    building=building,
                    at=parsed_at,
                    year=year,
                    semester=semester,
                    limit=limit,
                )
                return payload.model_dump()
            except NotFoundError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}
            except ValueError:
                exc = InvalidRequestError(
                    "Invalid 'at' timestamp. Use ISO 8601, for example 2026-03-16T10:15:00+09:00."
                )
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            (
                "캠퍼스 출발지 기준으로 주변 식당을 찾을 때 사용합니다. "
                "origin, 예산(budget_max), open_now, walk_minutes를 함께 줄 수 있습니다. "
                "origin은 slug, 대표 이름, alias(예: 중도, 학생식당)를 받을 수 있습니다. "
                "출발지가 모호하면 tool_search_places를 먼저 사용합니다. budget_max를 "
                "주면 가격 정보가 없는 후보는 제외합니다. open_now=true면 "
                "영업중이 확인된 후보만 남깁니다."
            )
            if public_readonly
            else (
                "캠퍼스 출발지 기준으로 걸어갈 수 있는 주변 식당을 "
                "예산과 카테고리 조건으로 찾습니다."
            )
        ),
        meta=tool_meta,
    )
    def tool_find_nearby_restaurants(
        origin: Annotated[
            str,
            Field(
                description=(
                    "식당을 찾을 출발 장소 대표 이름 또는 alias. "
                    "예: 중앙도서관, 중도, 학생식당"
                )
            ),
        ],
        at: Annotated[
            str | None,
            Field(description="기준 시각 ISO 8601 문자열. open_now 판단에 사용합니다."),
        ] = None,
        category: Annotated[
            str | None,
            Field(description="식당 카테고리 필터. 예: korean, cafe, western"),
        ] = None,
        budget_max: Annotated[
            int | None,
            Field(description="최대 예산(원). 가격 정보가 확인된 후보만 남깁니다."),
        ] = None,
        open_now: Annotated[
            bool,
            Field(description="지금 영업 중인 후보만 보고 싶으면 true. 확인된 후보만 남깁니다."),
        ] = False,
        walk_minutes: Annotated[
            int,
            Field(description="도보 허용 시간(분). 기본값은 15분입니다."),
        ] = 15,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 10입니다.")] = 10,
    ):
        with connection_factory() as conn:
            try:
                from datetime import datetime

                parsed_at = datetime.fromisoformat(at) if at else None
                restaurants = find_nearby_restaurants(
                    conn,
                    origin=origin,
                    at=parsed_at,
                    category=category,
                    budget_max=budget_max,
                    open_now=open_now,
                    walk_minutes=walk_minutes,
                    limit=limit,
                )
                if public_readonly:
                    return [serialize_public_nearby_restaurant(item) for item in restaurants]
                return [item.model_dump() for item in restaurants]
            except NotFoundError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}
            except ValueError:
                exc = InvalidRequestError(
                    "Invalid 'at' timestamp. Use ISO 8601, for example 2026-03-15T11:00:00+09:00."
                )
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            (
                "브랜드나 상호를 직접 검색할 때 사용합니다. "
                "매머드커피, 메가커피, 이디야, 스타벅스처럼 nearby 추천이 아니라 "
                "이름으로 특정 매장을 찾고 싶을 때 적합합니다."
            )
            if public_readonly
            else (
                "브랜드 또는 상호를 직접 검색해 특정 카페/식당 후보를 찾습니다."
            )
        ),
        meta=tool_meta,
    )
    def tool_search_restaurants(
        query: Annotated[
            str,
            Field(
                description=(
                    "브랜드 상호 또는 직접 검색어. "
                    "예: 매머드커피, 메가커피, 이디야, 스타벅스, 커피빈"
                )
            ),
        ] = "",
        origin: Annotated[
            str | None,
            Field(description="거리 정렬 보조용 출발 장소. 예: 중앙도서관, 중도"),
        ] = None,
        category: Annotated[
            str | None,
            Field(description="식당 카테고리 필터. 예: cafe, korean"),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 10입니다.")] = 10,
    ):
        with connection_factory() as conn:
            try:
                restaurants = search_restaurants(
                    conn,
                    query=query,
                    origin=origin,
                    category=category,
                    limit=limit,
                )
                if public_readonly:
                    return [serialize_public_restaurant_search(item) for item in restaurants]
                return [item.model_dump() for item in restaurants]
            except NotFoundError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}
            except InvalidRequestError as exc:
                if public_readonly:
                    return serialize_public_error(exc)
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            (
                "최신 공지를 최신순으로 가져오거나 카테고리로 좁힐 때 사용합니다. "
                "category filter는 optional입니다."
            )
            if public_readonly
            else (
                "최신 성심교정 공지를 가져오고, 필요하면 academic이나 "
                "scholarship 같은 범주로 좁힙니다."
            )
        ),
        meta=tool_meta,
    )
    def tool_list_latest_notices(
        category: Annotated[
            str | None,
            Field(
                description=(
                    "공지 카테고리 필터. 예: academic, scholarship, employment. "
                    "career도 employment와 동일하게 처리합니다."
                )
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 10입니다.")] = 10,
    ):
        with connection_factory() as conn:
            notices = list_latest_notices(conn, category=category, limit=limit)
            if public_readonly:
                return [serialize_public_notice(item) for item in notices]
            return [item.model_dump() for item in notices]

    @mcp.tool(
        description=(
            (
                "학과/기관 공지 통합 번들을 읽을 때 사용합니다. "
                "국제학부 학과공지와 기숙사 board notice bundle을 topic/query로 "
                "좁힐 수 있습니다."
            )
            if public_readonly
            else "학과/기관 공지 통합 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_affiliated_notices(
        topic: Annotated[
            str | None,
            Field(
                description=(
                    "공지 번들 topic 필터. 예: international_studies, "
                    "dorm_k_a_general, dorm_k_a_checkin_out, dorm_francis_general, "
                    "dorm_francis_checkin_out"
                )
            ),
        ] = None,
        query: Annotated[
            str | None,
            Field(description="제목, 요약 또는 본문 검색어. 예: 공결, 입퇴사, OT"),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        from . import services as _services
        from .mcp_public_serializers import serialize_public_affiliated_notice

        with connection_factory() as conn:
            notices = _services.list_affiliated_notices(conn, topic=topic, query=query, limit=limit)
            if public_readonly:
                return [serialize_public_affiliated_notice(item) for item in notices]
            return [item.model_dump() for item in notices]

    @mcp.tool(
        description=(
            (
                "대학생활 공지 번들(campus life notices)을 읽을 때 사용합니다. "
                "외부기관공지와 행사안내 board를 topic/query로 좁혀서 장학, 모집, "
                "프로그램, 행사 공지를 current snapshot 기준으로 찾습니다."
            )
            if public_readonly
            else "대학생활 외부기관공지/행사안내 current snapshot을 가져옵니다."
        ),
        meta=tool_meta,
    )
    def tool_list_campus_life_notices(
        topic: Annotated[
            str | None,
            Field(description="공지 번들 topic 필터. 예: outside_agencies, events"),
        ] = None,
        query: Annotated[
            str | None,
            Field(
                description="제목 또는 요약 검색어. 예: 외부기관공지, 장학, 모집, 프로그램, 행사",
            ),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            notices = list_campus_life_notices(conn, topic=topic, query=query, limit=limit)
            if public_readonly:
                return [serialize_public_campus_life_notice(item) for item in notices]
            return [item.model_dump() for item in notices]

    @mcp.tool(
        description=(
            "성심교정 지하철·버스 접근 안내를 찾을 때 사용합니다. "
            "정적 subway/bus 안내용이며, query에 지하철·1호선·역곡역·bus 같은 "
            "자연어 cue를 넣을 수 있습니다. 셔틀은 현재 지원하지 않아 빈 결과가 정상입니다."
            if public_readonly
            else "성심교정 지하철·버스 접근 안내를 가져오고, 필요하면 교통수단 모드로 좁힙니다."
        ),
        meta=tool_meta,
    )
    def tool_list_transport_guides(
        mode: Annotated[
            str | None,
            Field(description="교통수단 모드 필터. 예: subway, bus"),
        ] = None,
        query: Annotated[
            str | None,
            Field(description="자연어 교통 cue. 예: 지하철, 1호선, 역곡역, bus, 버스"),
        ] = None,
        limit: Annotated[int, Field(description="최대 결과 수. 기본값은 20입니다.")] = 20,
    ):
        with connection_factory() as conn:
            guides = list_transport_guides(conn, mode=mode, query=query, limit=limit)
            if public_readonly:
                return [serialize_public_transport_guide(item) for item in guides]
            return [item.model_dump() for item in guides]


def register_local_profile_tools(mcp: Any, connection_factory: Any) -> None:
    @mcp.tool(
        description=(
            "Create a local profile id for timetable, notice, "
            "and meal-personalization flows."
        )
    )
    def tool_create_profile(display_name: str = ""):
        with connection_factory() as conn:
            return create_profile(conn, display_name=display_name).model_dump()

    @mcp.tool(
        description=(
            "Update one local profile's display name, department, student year, "
            "or admission type."
        )
    )
    def tool_update_profile(
        profile_id: str,
        display_name: str | None = None,
        department: str | None = None,
        student_year: int | None = None,
        admission_type: str | None = None,
    ):
        with connection_factory() as conn:
            try:
                payload: dict[str, object] = {}
                if display_name is not None:
                    payload["display_name"] = display_name
                if department is not None:
                    payload["department"] = department
                if student_year is not None:
                    payload["student_year"] = student_year
                if admission_type is not None:
                    payload["admission_type"] = admission_type
                return update_profile(
                    conn,
                    profile_id,
                    ProfileUpdateRequest(**payload),
                ).model_dump()
            except (NotFoundError, InvalidRequestError) as exc:
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            "Replace a profile timetable using official course keys: "
            "year, semester, code, section."
        )
    )
    def tool_set_profile_timetable(profile_id: str, courses: list[dict[str, int | str]]):
        with connection_factory() as conn:
            try:
                refs = [ProfileCourseRef.model_validate(item) for item in courses]
                return [item.model_dump() for item in set_profile_timetable(conn, profile_id, refs)]
            except (NotFoundError, InvalidRequestError) as exc:
                return {"error": str(exc)}

    @mcp.tool(description="Get the current stored timetable for one local profile id.")
    def tool_get_profile_timetable(
        profile_id: str,
        year: int | None = None,
        semester: int | None = None,
    ):
        with connection_factory() as conn:
            try:
                return [
                    item.model_dump()
                    for item in get_profile_timetable(
                        conn,
                        profile_id,
                        year=year,
                        semester=semester,
                    )
                ]
            except NotFoundError as exc:
                return {"error": str(exc)}

    @mcp.tool(description="Save notice categories and keywords for one local profile id.")
    def tool_set_profile_notice_preferences(
        profile_id: str,
        categories: list[str] | None = None,
        keywords: list[str] | None = None,
    ):
        with connection_factory() as conn:
            try:
                return set_profile_notice_preferences(
                    conn,
                    profile_id,
                    ProfileNoticePreferences(
                        categories=categories or [],
                        keywords=keywords or [],
                    ),
                ).model_dump()
            except (NotFoundError, InvalidRequestError) as exc:
                return {"error": str(exc)}

    @mcp.tool(description="Save normalized interest tags for one local profile id.")
    def tool_set_profile_interests(profile_id: str, tags: list[str] | None = None):
        with connection_factory() as conn:
            try:
                return set_profile_interests(
                    conn,
                    profile_id,
                    ProfileInterests(tags=tags or []),
                ).model_dump()
            except (NotFoundError, InvalidRequestError) as exc:
                return {"error": str(exc)}

    @mcp.tool(description="Get the current stored interest tags for one local profile id.")
    def tool_get_profile_interests(profile_id: str):
        with connection_factory() as conn:
            try:
                return get_profile_interests(conn, profile_id).model_dump()
            except NotFoundError as exc:
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            "List notices that match one profile's saved preferences "
            "and profile context."
        )
    )
    def tool_get_profile_notices(profile_id: str, limit: int = 10):
        with connection_factory() as conn:
            try:
                return [
                    item.model_dump()
                    for item in list_profile_notices(conn, profile_id, limit=limit)
                ]
            except (NotFoundError, InvalidRequestError) as exc:
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            "Recommend courses for one profile using department and student-year context, "
            "excluding courses already in the timetable."
        )
    )
    def tool_get_profile_course_recommendations(
        profile_id: str,
        year: int | None = None,
        semester: int | None = None,
        query: str = "",
        limit: int = 10,
    ):
        with connection_factory() as conn:
            try:
                return [
                    item.model_dump()
                    for item in get_profile_course_recommendations(
                        conn,
                        profile_id,
                        year=year,
                        semester=semester,
                        query=query,
                        limit=limit,
                    )
                ]
            except (NotFoundError, InvalidRequestError) as exc:
                return {"error": str(exc)}

    @mcp.tool(
        description=(
            "Recommend meals from an origin place using one profile's timetable, budget, "
            "and optional category filters."
        )
    )
    def tool_get_profile_meal_recommendations(
        profile_id: str,
        origin: str,
        at: str | None = None,
        year: int | None = None,
        semester: int | None = None,
        budget_max: int | None = None,
        category: str | None = None,
        open_now: bool = False,
        limit: int = 10,
    ):
        with connection_factory() as conn:
            try:
                from datetime import datetime

                parsed_at = datetime.fromisoformat(at) if at else None
                return get_profile_meal_recommendations(
                    conn,
                    profile_id,
                    origin=origin,
                    at=parsed_at,
                    year=year,
                    semester=semester,
                    budget_max=budget_max,
                    category=category,
                    limit=limit,
                    open_now=open_now,
                ).model_dump()
            except (NotFoundError, InvalidRequestError, ValueError) as exc:
                return {"error": str(exc)}
