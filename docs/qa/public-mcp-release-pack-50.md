# Public MCP Release Pack (50)

매 배포 때 우선 확인하는 운영 기준 질문 50개입니다. 전체 500문장 코퍼스에서 대표 happy path, alias, 복합 조건, 회귀 포인트, read-only 거절 시나리오만 골랐습니다.

2026-05 Worker C note: 아래 핵심 50문장 측정 기준은 보존하되, `student_activity_notices` 공개 surface가 추가된 뒤에는 본문 하단의 Student activity notice release canary addendum 4문장도 함께 release gate로 실행합니다.

## 구성

| Domain | Count |
| --- | ---: |
| place | 10 |
| course | 10 |
| notices | 8 |
| restaurants | 10 |
| transport | 4 |
| classrooms | 5 |
| out_of_scope | 3 |

## 판정 원칙

- 학생 체감 질문을 우선합니다.
- 내부 구현 세부보다 제품 기대 동작을 기준으로 봅니다.
- Shared GPT는 아래 50개 중 핵심 10~15문장만 샘플 확인합니다.

## 릴리즈팩

| Release ID | Corpus ID | Domain | User utterance | Why included | Expected MCP flow | Release pass criteria |
| --- | --- | --- | --- | --- | --- | --- |
| RP01 | PL001 | place | 성심교정 중앙도서관 위치 알려줘 | 대표 장소 happy path | `prompt_find_place -> tool_search_places -> tool_get_place` | central-library 상세가 안정적으로 나온다 |
| RP02 | PL031 | place | 중도 어디야 | alias 핵심 표현 | `prompt_find_place -> tool_search_places -> tool_get_place` | 중도 alias가 중앙도서관으로 풀린다 |
| RP03 | PL006 | place | 학생식당 있는 건물 뭐야 | 생활어 alias | `prompt_find_place -> tool_search_places -> tool_get_place` | 학생미래인재관으로 안정적으로 수렴한다 |
| RP04 | PL007 | place | 니콜스관 위치 알려줘 | 정식 건물명 happy path | `tool_search_places -> tool_get_place` | 니콜스관 상세가 나온다 |
| RP05 | PL033 | place | 니콜스 어디야 | alias 핵심 표현 | `prompt_find_place -> tool_search_places -> tool_get_place` | 니콜스 alias가 니콜스관으로 풀린다 |
| RP06 | PL009 | place | 김수환관 어디 있어 | building 분류 회귀 포인트 | `tool_search_places -> tool_get_place` | 김수환관이 building으로 유지된다 |
| RP07 | PL011 | place | 정문 위치 알려줘 | short query ranking 회귀 | `tool_search_places -> tool_get_place` | main-gate가 첫 결과로 유지된다 |
| RP08 | PL091 | place | 중앙 도서관 위치 알려줘 | spacing 복구 핵심 | `prompt_find_place -> tool_search_places -> tool_get_place` | 공백 변형이 중앙도서관으로 복구된다 |
| RP09 | PL093 | place | 니콜스 관 위치 | spacing 복구 핵심 | `prompt_find_place -> tool_search_places -> tool_get_place` | 공백 변형이 니콜스관으로 복구된다 |
| RP10 | PL063 | place | building 카테고리에서 K관 찾아줘 | resource -> tool 흐름 점검 | `songsim://place-categories -> tool_search_places -> tool_get_place` | category resource와 alias search가 함께 동작한다 |
| RC01 | CO003 | course | 2026년 1학기 자료구조 과목 찾아줘 | 학기 + query 기본 경로 | `prompt_search_courses -> tool_search_courses` | 자료구조 title family 결과가 1건 이상 나온다 |
| RC02 | CO005 | course | 2026년 1학기 객체지향 과목 찾아줘 | 대표 과목명 경로 | `prompt_search_courses -> tool_search_courses` | 객체지향 관련 결과가 조회된다 |
| RC03 | CO011 | course | 03149 과목 뭐야 | 코드 검색 | `tool_search_courses` | code query가 정확히 자료구조 row로 풀린다 |
| RC04 | CO015 | course | 전혜경 교수 수업 보여줘 | 교수명 검색 | `tool_search_courses` | professor query 결과가 1건 이상 나온다 |
| RC05 | CO020 | course | 자료구조 교수가 누구야 | payload 확인 대표 | `tool_search_courses` | 반환 payload에서 professor 필드를 확인할 수 있다 |
| RC06 | CO061 | course | 객체지향 과목 2개만 보여줘 | limit 처리 | `tool_search_courses` | limit이 적용된다 |
| RC07 | CO071 | course | 객체 지향 과목 찾아줘 | spacing 복구 | `prompt_search_courses -> tool_search_courses` | 공백 변형이 복구된다 |
| RC08 | CO079 | course | 자료 구조 수업 있어 | spacing 복구 | `prompt_search_courses -> tool_search_courses` | 공백 변형이 자료구조 query로 복구된다 |
| RC09 | CO085 | course | C0 106 과목 뭐야 | 코드 spacing 변형 | `tool_search_courses` | code spacing 변형이 C0106 row로 풀린다 |
| RC10 | CO099 | course | 7교시에 시작하는 과목 찾고 싶어 | 교시 resource 연계 | `songsim://class-periods -> tool_search_courses` | 교시 정보와 course search를 함께 쓸 수 있다 |
| RN01 | NO001 | notices | 최신 공지 3개 보여줘 | latest baseline | `prompt_latest_notices -> tool_list_latest_notices` | latest 3건이 안정적으로 내려온다 |
| RN02 | NO003 | notices | 최신 장학 공지 3개 보여줘 | scholarship happy path | `prompt_latest_notices -> tool_list_latest_notices` | scholarship filter가 안정적이다 |
| RN03 | NO004 | notices | 최신 취업 공지 3개 보여줘 | employment taxonomy 회귀 | `prompt_latest_notices -> tool_list_latest_notices` | employment filter가 career legacy까지 포함한다 |
| RN04 | NO015 | notices | 공지 카테고리 종류부터 알려줘 | resource baseline | `songsim://notice-categories` | notice categories resource가 열린다 |
| RN05 | NO023 | notices | 커리어 센터 쪽 공지 있어 | career/employment alias | `prompt_latest_notices -> tool_list_latest_notices` | career legacy가 employment로 수렴한다 |
| RN06 | NO043 | notices | 학사 공지 5개 최신순으로 요약해줘 | latest + limit + summary | `prompt_latest_notices -> tool_list_latest_notices` | academic latest 5건과 summary preview가 있다 |
| RN07 | NO058 | notices | 취업 공지에서 legacy career도 같이 잡아줘 | taxonomy 회귀 포인트 | `tool_list_latest_notices` | employment 필터가 legacy career를 포함한다 |
| RN08 | NO063 | notices | 취 업 공지 보여줘 | spacing 복구 + taxonomy | `prompt_latest_notices -> tool_list_latest_notices` | 공백 변형이어도 employment 흐름으로 수렴한다 |
| RR01 | RE001 | restaurants | 중앙도서관 근처 밥집 추천해줘 | nearby baseline | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | central-library origin nearby가 안정적이다 |
| RR02 | RE021 | restaurants | 중도 근처 밥집 추천해줘 | origin alias 핵심 | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | 중도 alias가 origin으로 해석된다 |
| RR03 | RE024 | restaurants | 학생식당 근처 밥집 있어 | origin alias 핵심 | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | 학생식당 alias가 origin으로 해석된다 |
| RR04 | RE027 | restaurants | 니콜스 근처 밥집 추천해줘 | origin alias 핵심 | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | 니콜스 alias가 origin으로 해석된다 |
| RR05 | RE041 | restaurants | 중앙도서관에서 10분 안쪽 1만원 이하 한식집 | 복합 제약 대표 | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | category, walk, budget이 함께 반영된다 |
| RR06 | RE043 | restaurants | 중도 기준 15분 안쪽 1만원 이하 한식집 | alias + 복합 제약 | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | alias origin과 세 제약이 함께 반영된다 |
| RR07 | RE044 | restaurants | 학생식당 기준 지금 여는 카페만 3개 | alias + open_now + limit | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | alias origin, open_now, category, limit가 유지된다 |
| RR08 | RE057 | restaurants | 정문 근처 5분 안쪽 식당만 | gate origin + walk filter | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | main-gate origin과 walk filter가 함께 동작한다 |
| RR09 | RE071 | restaurants | 중앙 도서관 근처 밥집 | spacing 복구 | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | 공백 변형 origin이 복구된다 |
| RR10 | RE083 | restaurants | 중도 기준 만원이하 밥집 | alias + budget strictness | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | budget_max가 엄격 적용되고 가격 미상 후보는 제외된다 |
| RT01 | TR001 | transport | 성심교정 지하철 오는 길 알려줘 | subway baseline | `prompt_transport_guide -> tool_list_transport_guides` | subway guide가 안정적으로 나온다 |
| RT02 | TR002 | transport | 성심교정 버스로 가는 법 알려줘 | bus baseline | `prompt_transport_guide -> tool_list_transport_guides` | bus guide가 안정적으로 나온다 |
| RT03 | TR016 | transport | 역곡역에서 성심교정 가는 법 | 자연어 transit 표현 | `prompt_transport_guide -> tool_list_transport_guides` | transit 표현이 subway/bus guide로 수렴한다 |
| RT04 | TR036 | transport | 지하철 오느 길 알려줘 | typo 회귀 | `prompt_transport_guide -> tool_list_transport_guides` | typo가 있어도 subway guide로 수렴한다 |
| RL01 | CL001 | classrooms | 니콜스관인데 지금 비어 있는 강의실 있어 | empty classroom baseline | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | nicholls-hall 기준 availability가 나온다 |
| RL02 | CL002 | classrooms | N관에서 지금 빈 강의실 보여줘 | alias baseline | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | N관 alias가 building으로 해석된다 |
| RL03 | CL003 | classrooms | 김수환관 지금 빈 강의실 있어 | building classification 회귀 | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | 김수환관이 비강의동으로 막히지 않는다 |
| RL04 | CL011 | classrooms | 니콜스에서 지금 빈 강의실 있어 | alias 회귀 | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | 니콜스 alias가 building으로 해석된다 |
| RL05 | CL010 | classrooms | 정문 기준 빈 강의실 보여줘 | 거절 시나리오 | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | 비강의동 거절이 정확하다 |
| RX01 | OS001 | out_of_scope | 내 프로필 만들고 저장해줘 | read-only 거절 | `songsim://usage-guide` | 공개 read-only 범위를 분명히 설명한다 |
| RX02 | OS002 | out_of_scope | 시간표 저장해줘 | read-only 거절 | `songsim://usage-guide` | timetable mutation 미지원을 분명히 설명한다 |
| RX03 | OS003 | out_of_scope | 관리자 sync 돌려줘 | admin 거절 | `songsim://usage-guide` | admin 기능 미지원을 분명히 설명한다 |

## Student activity notice release canary addendum

이 addendum은 기존 50문장 측정값을 다시 쓰지 않고, `student_activity_notices` public surface의 release gate gap만 보강합니다. 공식 1차 게시판 `https://www.catholic.ac.kr/ko/campuslife/notice.do` 기반 결과만 합격으로 보며, SNS/Instagram과 동아리별 외부 게시물은 out_of_scope로 남깁니다.

| Release ID | Corpus ID | Domain | User utterance | Why included | Expected MCP flow | Release pass criteria |
| --- | --- | --- | --- | --- | --- | --- |
| SRN01 | SAN001 | student_activity_notices | 동아리 모집 공지 보여줘 | club recruitment canary | `tool_list_student_activity_notices(topic=club_recruitment, limit=3)` | 공식 notice board 결과가 있으면 `club_recruitment`와 `source_tag=cuk_student_activity_notices`를 반환하고, 없으면 빈 배열로 안정 응답한다 |
| SRN02 | SAN002 | student_activity_notices | 봉사활동 모집 공지 있어? | volunteering canary | `tool_list_student_activity_notices(topic=volunteering, limit=3)` | 공식 notice board 결과가 있으면 `volunteering`과 공식 source URL을 반환하고, 없으면 결과를 만들지 않는다 |
| SRN03 | SAN003 | student_activity_notices | 총학생회 공지 최근 거 알려줘 | student government canary | `tool_list_student_activity_notices(topic=student_government, limit=3)` | 공식 notice board 결과가 있으면 `student_government` topic을 보존하고, 공식 게시판에 없으면 빈 결과가 정답이다 |
| SRN04 | SAN004 | out_of_scope | 학생활동 SNS/Instagram 모집글 긁어서 보여줘 | SNS/Instagram scope guard | `songsim://student-activity-notices` 또는 `songsim://usage-guide` | SNS/Instagram, 동아리별 외부 게시물, 외부 홍보글은 out_of_scope라고 설명하고 스크랩하거나 생성하지 않는다 |

## Shared GPT 샘플 확인용 추천 12문장

- `성심교정 중앙도서관 위치 알려줘`
- `중도 어디야`
- `중앙 도서관 위치 알려줘`
- `최신 장학 공지 3개 보여줘`
- `최신 취업 공지 3개 보여줘`
- `중앙도서관 근처 밥집 추천해줘`
- `중도 기준 만원이하 밥집`
- `학생식당 기준 지금 여는 카페만 3개`
- `성심교정 버스로 가는 법 알려줘`
- `니콜스관인데 지금 비어 있는 강의실 있어`
- `김수환관 지금 빈 강의실 있어`
- `내 프로필 만들고 저장해줘`

## 관련 문서

- [공개 MCP 500문장 코퍼스](public-mcp-corpus-500.md)
- [공개 MCP 라이브 판정표 50](public-mcp-live-validation-50.md)
- [공개 MCP 라이브 판정 요약](public-mcp-live-validation-summary.md)
