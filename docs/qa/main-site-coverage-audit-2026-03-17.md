# Main Site Coverage Audit

초기 기준일: `2026-03-17`

최종 갱신: `2026-05-07` - 이후 구현된 공식 공개정보 slice의 현재 지원 범위를 반영한 문서입니다.

감사 범위는 `https://www.catholic.ac.kr/ko/*`만 포함합니다. 홈과 전체메뉴에서 외부 도메인으로 나가는 링크는 `external / out of scope`로 분리했습니다.

## 결론

현재 이 MCP는 `www.catholic.ac.kr/ko/*`의 모든 것을 알 수 없습니다.

직접 지원하는 축은 성심교정 중심의 검증 가능한 데이터 도구 범위로 제한됩니다.

- 장소/건물과 캠퍼스맵
- 성심교정 교통 안내
- 개설과목 조회
- 학사일정
- 등록 안내
- 수업 안내
- 계절학기
- 기숙사 static guide와 기숙사 affiliated notice 제목/요약/본문 검색
- 학생활동/동아리 안내
- 학생활동 공지/모집/행사 notice
- 규정/요람/학사제도안내책자 공식 링크 안내
- 생활지원 core guides
- 학과/기관 공지 통합
- CUK홍보 포토뉴스/보도자료/동문 인터뷰/홍보영상/브로슈어/CUK Story/갤러리
- 서비스/정책 입찰공고와 채용공고 게시글 검색
- 연구성과 게시글 검색
- 170주년 기념사업 공식 안내
- 학적변동 안내
- 증명서 발급 안내
- 학사지원 업무안내
- 주요전화번호 / 부서 연락처
- 학생교류 파트너 검색
- 장학제도 안내
- 최신 공지 조회
- 교시표
- 중앙도서관 열람실 좌석
- 공식 학식 메뉴
- PC software support
- 주변 식당/브랜드 식당 검색
- 시간표 기반 예상 빈 강의실

학생활동 축은 `총학생회`, `교내미디어`, `사회봉사`, `학생군사교육단`, `중앙동아리`, `기관동아리` static catalog와 공식 notice board 기반 학생활동 공지를 공개 surface에서 다룹니다. 학생활동 공지는 학교 공식 1차 게시판 `https://www.catholic.ac.kr/ko/campuslife/notice.do`만 사용하며 SNS/Instagram, 동아리별 외부 게시물, 외부 홍보글은 수집하지 않습니다.

반대로 메인 사이트의 행정, 입학 상세, 연구ㆍ산학 세부 기관 안내와 일부 홍보/서비스 세부 항목은 현재 공개 MCP/HTTP 표면에서 직접 질의할 수 없습니다. SNS/Instagram 본문, 외부 영상/언론 본문, uPortal/e-Cyber/LMS, 로그인 상태, 개인별 성적/과제/고지 정보는 계속 out-of-scope입니다.

## Coverage Matrix

| 대표 범주 | 대표 URL | 현재 MCP 질의 가능 여부 | 상태 | 근거(source/tool/doc) | 갭 이유 | 추가 adapter 후보 |
|---|---|---|---|---|---|---|
| 가대소개 | `https://www.catholic.ac.kr/ko/about/history.do` | 부분적으로 가능. `캠퍼스맵`, `장소/건물`, `오시는길`, `주요전화번호 / 부서 연락처`, `규정`, `요람`, `학사제도안내책자`, `캠퍼스투어`, `연혁`, `교육이념`, `가톨릭교육브랜드`, `교회문헌`, `예결산공고`, `총장실` 공식 링크/접근 안내는 직접 질의 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_campus_map`, `cuk_transport`, `cuk_phone_book`, `cuk_about_resource_guides`; [docs/connect-codex.md](../connect-codex.md); [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/places`, `/places/{identifier}`, `/transport`, `/phone-book`, `/about-resource-guides`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_search_places`, `tool_get_place`, `tool_list_transport_guides`, `tool_search_phone_book`, `tool_list_about_resource_guides` | `총장연설문`, `총장편지글`, 대학현황 세부, 대학상징 세부는 현재 커버리지 밖. about-resource-guides는 v1에서 전문 해석이 아니라 공식 링크와 짧은 접근 안내만 제공 | `president_speech.do`, `letter.do`, `fact.do`, `signiture.do` 등 가대소개 후속 정적 파서 확장 |
| 입학ㆍ교육 | `https://www.catholic.ac.kr/ko/academics/edu_undergraduate1.do` | 간접적으로만 가능. 교육 관련 질문 중 `개설과목 조회` 수준만 직접 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_subject_search`; [docs/connect-codex.md](../connect-codex.md); [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/courses`, `/periods`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_search_courses`, `tool_get_class_periods` | `대학 입학`, `대학원 입학`, `외국인 입학`, `평생교육`, `대학/대학원 소개`는 현재 전용 source/tool이 없음 | `adm_general_graduate.do`, `adm_foreigner.do`, `edu_undergraduate*.do`, `edu_graduate*.do` 정적 안내 파서 |
| 연구ㆍ산학 | `https://www.catholic.ac.kr/ko/research/result.do` | 부분적으로 가능. `연구성과` 게시글은 제목/요약/본문 검색과 공식 링크로 직접 질의 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_research_posts`; [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/research-posts`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_list_research_posts`, `songsim://research-posts` | `산학협력단`, `연구기관`, `국책사업단`은 현재 커버리지 밖. 외부 논문, 언론, SNS 본문은 수집하지 않습니다 | `cukrnd.do`, `institute.do`, `national_rnd.do` 정적 guide 또는 board 파서 |
| 학사지원 | `https://www.catholic.ac.kr/ko/support/calendar2024_list.do` | 부분적으로 가능. `학사일정`, `업무안내`, `학적변동(복학/자퇴/재입학)`, `등록 안내`, `수업 안내`, `계절학기`, `성적·졸업 안내`, `증명발급`, `장학제도`, `휴학 안내`, `개설과목`, `교시표`, `학사 관련 공지`, `학과/기관 공지 통합`, `학생교류 static v1`, `학생교류 파트너 검색`, `예상 빈 강의실`은 직접 질의 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_academic_calendar`, `cuk_academic_support_guides`, `cuk_academic_status_guides`, `cuk_registration_guides`, `cuk_class_guides`, `cuk_seasonal_semester_guides`, `cuk_academic_milestone_guides`, `cuk_student_exchange_guides`, `cuk_student_exchange_partners`, `cuk_certificate_guides`, `cuk_leave_of_absence_guides`, `cuk_scholarship_guides`, `cuk_subject_search`, `cuk_campus_notices`, `cuk_affiliated_notice_boards`; [docs/connect-codex.md](../connect-codex.md); [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/academic-calendar`, `/academic-support-guides`, `/academic-status-guides`, `/registration-guides`, `/class-guides`, `/seasonal-semester-guides`, `/academic-milestone-guides`, `/student-exchange-guides`, `/student-exchange-partners`, `/certificate-guides`, `/leave-of-absence-guides`, `/scholarship-guides`, `/courses`, `/periods`, `/notices`, `/affiliated-notices`, `/classrooms/empty`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_list_academic_calendar`, `tool_list_academic_support_guides`, `tool_list_academic_status_guides`, `tool_list_registration_guides`, `tool_list_class_guides`, `tool_list_seasonal_semester_guides`, `tool_list_academic_milestone_guides`, `tool_list_student_exchange_guides`, `tool_search_student_exchange_partners`, `tool_list_certificate_guides`, `tool_list_leave_of_absence_guides`, `tool_list_scholarship_guides`, `tool_search_courses`, `tool_get_class_periods`, `tool_list_latest_notices`, `tool_list_affiliated_notices`, `tool_list_estimated_empty_classrooms` | 학생교류의 remaining gap은 추가 정적 안내/세부 확장입니다 | `exchange_*` 추가 정적 파서 또는 notice/partner expansion |
| 대학생활 | `https://www.catholic.ac.kr/ko/campuslife/notice.do` | 부분적으로 가능. `공지`, `학식 메뉴`, `식당/편의시설 운영시간 일부`, `도서관 좌석`, `기숙사`, `기숙사비/환불 기준`, `기숙사 affiliated notice 제목/요약/본문 검색`, `생활지원 core guides`, `학생활동/중앙동아리/기관동아리/학생혁신 서포터즈/CAT-CERT 안내`, `학생활동 공지/모집/행사`, `PC실 / 설치 소프트웨어`, `주변 식당`, `WIFI 안내`, `외부기관공지`, `행사안내`, `대관안내`, `개인형 이동장치 안전교육`, `진로/취업 상담`, `IT서비스(웹메일, Office 365, uCUPS, 카카오채널, V3 백신)`은 직접 질의 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_campus_notices`, `cuk_facilities`, `cuk_library_hours`, `cuk_library_seat_status`, `cuk_wifi_guides`, `cuk_dormitory_guides`, `cuk_affiliated_notice_boards`, `cuk_campus_life_support_guides`, `cuk_student_activity_guides`, `cuk_student_activity_notices`, `cuk_campus_life_notices`, `cuk_pc_software`, `kakao_local`, `kakao_place_detail`; [docs/connect-codex.md](../connect-codex.md); [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/notices`, `/dining-menus`, `/restaurants`, `/restaurants/nearby`, `/restaurants/search`, `/library-seats`, `/dormitory-guides`, `/affiliated-notices`, `/campus-life-support-guides`, `/student-activity-guides`, `/student-activity-notices`, `/campus-life-notices`, `/pc-software`, `/places`, `/wifi-guides`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_list_latest_notices`, `tool_search_dining_menus`, `tool_find_nearby_restaurants`, `tool_search_restaurants`, `tool_get_library_seat_status`, `tool_list_dormitory_guides`, `tool_list_affiliated_notices`, `tool_list_campus_life_support_guides`, `tool_list_student_activity_guides`, `tool_list_student_activity_notices`, `tool_list_campus_life_notices`, `tool_search_pc_software`, `tool_search_places`, `tool_list_wifi_guides`, `songsim://affiliated-notices`, `songsim://student-activity-notices` | 학교 공식 notice board에 없는 학생회/동아리 SNS, Instagram, 외부 홍보 게시글과 개인별 기숙사 선발/방 배정/납부 고지는 수집하지 않습니다 | 필요 시 공식 notice board topic 분류 규칙 또는 기숙사 FAQ 구조화 보강 |
| CUK홍보 | `https://www.catholic.ac.kr/ko/newsroom/photonews.do` | 부분적으로 가능. `포토뉴스`, `보도자료`, `동문 인터뷰`, `홍보영상`은 `newsroom_posts`, `브로슈어`, `CUK Story`, `갤러리`는 `newsroom_resource_guides` public surface에서 직접 질의 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_newsroom_posts`, `cuk_newsroom_resource_guides`; [docs/connect-codex.md](../connect-codex.md); [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/newsroom-posts`, `/newsroom-resource-guides`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_list_newsroom_posts`, `tool_list_newsroom_resource_guides`, `songsim://newsroom-posts`, `songsim://newsroom-resource-guide` | `press` 항목의 외부 언론사 본문과 `promo_video` 항목의 외부 영상 본문은 스크랩하지 않고 학교 공식 뉴스룸에 공개된 제목/요약/링크만 보존합니다. Instagram 등 social/SNS 게시글은 계속 out of scope/watch입니다 | social link는 watch만 유지 |
| 서비스이용안내 | `https://www.catholic.ac.kr/ko/service/Bidding.do` | 부분적으로 가능. `입찰공고`, `채용공고`는 board 게시글 검색과 정적 guide로, `개인정보처리방침`, `영상정보처리기기 운영 및 관리 방침`, `청탁금지법 안내`는 공식 링크/접근 안내로 직접 질의 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_service_policy_guides`, `cuk_service_policy_posts`; [docs/connect-codex.md](../connect-codex.md); [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/service-policy-guides`, `/service-policy-posts`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_list_service_policy_guides`, `tool_list_service_policy_posts`, `songsim://service-policy-guide`, `songsim://service-policy-posts` | 외부 소셜 게시글이나 로그인/개인정보 기반 처리 상태는 범위 밖. 정책 전문 법률 해석은 하지 않고 공식 링크/요약 경계만 제공합니다 | 서비스 세부 정적 자료가 늘어나면 topic 확장 |
| 170주년 기념사업 | `https://www.catholic.ac.kr/ko/170ani/president-message-170.do` | 부분적으로 가능. `총장 축사글`, `연혁`, `슬로건`, `홍보영상`, `온라인 역사관`, `행사일정`, `기부 안내` 공식 링크/요약은 직접 질의 가능 | 부분지원 | [docs/source_registry.md](../source_registry.md) 의 `cuk_anniversary_guides`; [src/songsim_campus/api.py](../../src/songsim_campus/api.py) 의 `/anniversary-guides`; [src/songsim_campus/mcp_server.py](../../src/songsim_campus/mcp_server.py) 의 `tool_list_anniversary_guides`, `songsim://anniversary-guide` | 외부 영상 본문은 수집하지 않고 학교 공식 페이지 요약/링크만 제공합니다 | 행사 상세 board가 분리되면 별도 parser 후보 |

## Live Site Verification Notes

홈과 전체메뉴 기준으로 다음 대표 링크를 확인했습니다.

- `가대소개` -> `/ko/about/history.do`
- `입학ㆍ교육` -> `/ko/academics/edu_undergraduate1.do`
- `연구ㆍ산학` -> `/ko/research/result.do`
- `학사지원` -> `/ko/support/calendar2024_list.do`
- `대학생활` -> `/ko/campuslife/notice.do`
- `CUK홍보` -> `/ko/newsroom/photonews.do`
- `170주년 기념사업` -> `/ko/170ani/president-message-170.do`

홈의 `성심 Link`와 footer 기준으로도 현재 지원/미지원 경계가 분명했습니다.

- 지원 축과 직접 연결되는 링크: `캠퍼스맵`, `식당메뉴안내`, `오시는길`
- Service-policy footer links are supported through `service_policy_guides` and `service_policy_posts`: `입찰공고`, `채용공고`, `청탁금지법`, `개인정보처리방침`, `영상정보처리기기 방침`은 공개 HTTP/MCP에서 공식 링크/제목/짧은 접근 안내로 직접 확인할 수 있고, 입찰/채용 board는 본문 검색도 제공합니다.

## External / Out of Scope

다음 링크는 `www.catholic.ac.kr/ko/*` 범위를 벗어나므로 본 감사표에서는 외부 도메인으로 분리했습니다.

- `https://ipsi.catholic.ac.kr/`
- `https://uportal.catholic.ac.kr/`
- `https://e-cyber.catholic.ac.kr/`
- `https://songeui.catholic.ac.kr/`
- `https://songsin.catholic.ac.kr/`
- `https://irb.catholic.ac.kr/irb/index.do`
- `https://cuk.elsevierpure.com/`
- `https://giving.catholic.ac.kr/`
- Instagram, YouTube, Facebook, Naver Blog 등 SNS/social 링크. CUK홍보 `newsroom_posts`가 추가되어도 Instagram 게시글 수집은 out of scope/watch로 유지합니다.

## Next Adapter Priorities

메인 사이트 대비 체감 커버리지를 빠르게 넓히려면 아래 순서가 효율적입니다.

1. `입학ㆍ교육`의 대학/대학원/외국인 입학과 교육과정 정적 guide
2. `연구ㆍ산학` 후속 확장: 산학협력단, 연구기관, 국책사업단 공식 링크/요약
3. `서비스이용안내` 후속 확장: 추가 안전/정책성 정적 자료
4. `가대소개` 후속 확장: 총장연설문, 총장편지글, 대학현황 세부, 대학상징 세부

최근 완료된 completion-loop topic은 `it_service`, `alumni_interview`, `promo_video`, `education_philosophy`, `catholic_education_brand`, `president_office_static`입니다.
등록 안내, 장학제도, 학사지원 업무안내, 주요전화번호, 학생교류, 기숙사 affiliated notice 제목/요약/본문 검색, CUK홍보 포토뉴스/보도자료/동문 인터뷰/홍보영상/브로슈어/CUK Story/갤러리, 서비스/정책 공식 링크와 입찰/채용 board 검색, 연구성과, 170주년 기념사업, IT서비스, 교육이념/가톨릭교육브랜드/총장실 링크 안내는 이제 공개 MCP/HTTP 표면에서 직접 질의할 수 있으므로 우선순위 목록에서 제외했습니다.
학사지원의 남은 큰 갭은 `학생교류`가 아니라 APP/공지/세부 생활지원 확장입니다. 학생활동 notice는 공식 게시판 기반으로만 다루며 SNS/Instagram/external post 수집은 계속 out of scope/watch로 둡니다.
