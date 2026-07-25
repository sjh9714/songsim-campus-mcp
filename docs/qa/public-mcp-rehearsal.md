# Public MCP Rehearsal

> Historical/superseded: measured results below are preserved as the local public_readonly rehearsal run. Current release-gate docs are superseded by `public-mcp-release-pack-50.md`, `public-synthetic-smoke.md`, and the `student_activity_notices` canary addendum; do not rewrite the verdicts in this historical report when adding new public surface coverage.

대표 질문 20개를 실제 `public_readonly` MCP contract 기준으로 점검한 기록입니다.

## 실행 기준

- 환경: 로컬 임시 PostgreSQL DB
- 모드: `SONGSIM_APP_MODE=public_readonly`
- 기본 데이터: `seed_demo(force=True)`
- 추가 fixture
  - 공지: `academic`, `scholarship`, `employment`, `library` 카테고리 1건씩 주입
  - 교통: `subway`, `bus` guide를 deterministic fixture로 주입
  - 식당 `open_now` 케이스: `카페드림` 운영시간 fixture 사용
- 판정 기준
  - `pass`: 기대한 MCP flow와 핵심 payload가 바로 맞음
  - `soft_fail`: flow는 맞지만 alias/오타/표현 복구가 약함
  - `fail`: 현재 public surface만으로는 그대로 성공시키기 어려움

## 요약

| Verdict | Count |
| --- | ---: |
| pass | 17 |
| soft_fail | 2 |
| fail | 1 |

| Failure type | Count |
| --- | ---: |
| missing_alias | 1 |
| wording_issue | 1 |
| unsupported_scope | 1 |

## 대표 케이스 20

| ID | User utterance | Used MCP flow | Actual returned signal | Verdict | Failure type |
| --- | --- | --- | --- | --- | --- |
| P01 | 성심교정 중앙도서관 위치 알려줘 | `prompt_find_place -> tool_search_places -> tool_get_place` | `central-library`, aliases `도서관/중도`, coordinates 포함 | pass | - |
| P06 | 중도 어디야? | `tool_search_places` | alias `중도`로 `중앙도서관` 1건 반환 | pass | - |
| P08 | 학생식당 있는 건물 뭐야? | `tool_search_places` | `student-center`, aliases `학회관/학생식당` 반환 | pass | - |
| P10 | N관이 뭐였지? | `tool_search_places` | `nichols-hall`, aliases `니콜스/N관` 반환 | pass | - |
| P19 | 중앙 도서 관 위치 | `tool_search_places` | 빈 결과 `[]` | soft_fail | missing_alias |
| C01 | 2026년 1학기 객체지향 과목 찾아줘 | `prompt_search_courses -> tool_search_courses` | `CSE301`, `객체지향프로그래밍설계`, `금1~3(B346)` | pass | - |
| C05 | 김가톨 교수 수업 알려줘 | `tool_search_courses` | `CSE332`, `데이터베이스`, `수4~6(N201)` | pass | - |
| C09 | CSE420 과목 뭐야? | `tool_search_courses` | `CSE420`, `인공지능응용`, `목2~4(B210)` | pass | - |
| C19 | 데이타베이스 과목 있어? | `tool_search_courses` | 빈 결과 `[]` | soft_fail | wording_issue |
| N01 | 최신 학사 공지 2개 보여줘 | `prompt_latest_notices -> tool_list_latest_notices` | `2026-1 수강신청 정정 안내`, `category_display=학사` | pass | - |
| N06 | 장학 공지 최신순으로 3개 | `tool_list_latest_notices` | `2026학년도 장학 신청 안내`, `category_display=장학` | pass | - |
| N11 | 취업 공지 최근 거 알려줘 | `tool_list_latest_notices` | `진로취업센터 채용 설명회`, `category_display=취업` | pass | - |
| N18 | 도서관 관련 공지 있나 | `tool_list_latest_notices` | `중앙도서관 시험기간 연장 운영`, `category_display=도서관` | pass | - |
| R01 | 중앙도서관 근처 밥집 추천해줘 | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | 상위 결과 `퀵토스트`, `성심김밥`, 거리/도보/price_hint 포함 | pass | - |
| R05 | 중앙도서관 근처 한식만 | `tool_find_nearby_restaurants` | `성심김밥`, `버짓덮밥` 반환 | pass | - |
| R09 | 중앙도서관에서 10분 안쪽에 1만원 이하 | `tool_find_nearby_restaurants` | `퀵토스트`, `성심김밥` 반환, budget/walk 조건 유지 | pass | - |
| R14 | 지금 열어있는 카페만 보여줘 | `tool_find_nearby_restaurants` | `카페드림` 1건, `open_now=true` | pass | - |
| R20 | 중도 근처 라멘집 | `tool_find_nearby_restaurants` | `Origin place not found: 중도` 구조화 오류 | fail | unsupported_scope |
| T01 | 성심교정 지하철 오는 길 알려줘 | `prompt_transport_guide -> tool_list_transport_guides` | `1호선`, `역곡역 2번 출구에서 도보 10분` | pass | - |
| X01 | 내 프로필 만들고 시간표 저장해줘 | `songsim://usage-guide` | usage guide에 `read-only`, `Unavailable: profile, timetable...` 명시 | pass | - |

## 리허설 해석

- 장소
  - exact name과 대표 alias(`중도`, `N관`, `학생식당`)는 잘 잡혔습니다.
  - 띄어쓰기 오타 복구는 아직 약합니다.
- 과목
  - title/code/professor 기반 검색은 안정적입니다.
  - 오타 복구(`데이타베이스`)는 현재 public MCP surface에서 보정되지 않습니다.
- 공지
  - category 기반 latest 조회는 잘 동작합니다.
  - `category_display` 요약이 MCP payload에서 바로 쓸 만합니다.
- 식당
  - origin이 정확 name/slug일 때는 예산/거리/open_now 조합이 잘 유지됩니다.
  - origin alias(`중도`)는 바로 `tool_find_nearby_restaurants`로 넘기면 실패합니다.
  - 이 케이스는 반드시 `tool_search_places` 선행 흐름으로 보강해야 합니다.
- 교통
  - `subway`, `bus` 기반 정적 안내 용도는 분명합니다.
- 범위 밖
  - `songsim://usage-guide`가 read-only 제약을 설명하는 1차 방어선으로 충분합니다.

## 다음 보정 우선순위

1. 식당 origin alias 보강
2. 장소/과목 오타 복구 metadata 또는 alias 확장
3. Shared GPT 2차에서 과목/교통 전용 요약 surface 정리
