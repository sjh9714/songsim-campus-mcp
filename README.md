# songsim-campus-mcp

`songsim-campus-mcp`는 가톨릭대학교 성심교정 학생이 자주 묻는 학사·생활 정보를 **공식 source 중심 Remote MCP + HTTP API**로 제공하는 캠퍼스 도우미 서버입니다. 공지, 학사일정, 건물/연락처, 강의, 도서관 좌석, 식당, Wi-Fi, IT서비스, 기숙사와 생활지원 정보를 LLM 클라이언트에서 읽기 전용으로 조회할 수 있게 구성했습니다. 주변 식당 검색은 학교 공식 1차 source가 아니라 Kakao Local 외부 공개 API 기반 편의 기능으로 분리해 표시합니다.

## 문제의식

학생이 필요한 정보는 학교 홈페이지, 공지 게시판, 학사 안내, 시설 안내에 흩어져 있습니다. 이 프로젝트는 "성심교정에서 지금 필요한 답"을 하나의 student-facing surface로 묶고, 공식 source에 없는 값은 만들지 않는 방식으로 신뢰 경계를 드러냅니다.

## 주요 사용 질문

- 최신 학사 공지와 소속기관 공지
- 포토뉴스, 보도자료, 동문 인터뷰, 홍보영상, 브로슈어, CUK Story, 갤러리
- 월별 학사일정과 등록·휴학·복학·증명·장학 안내
- 건물, 시설, 편의시설, 전화번호, 운영시간
- 과목 검색, 교시 정보, 도서관 좌석, 예상 빈 강의실
- 학식, 주변 식당, PC 소프트웨어, Wi-Fi
- 기숙사, 상담, 병원, 예비군, 웹메일/Office 365 같은 IT서비스, 학생활동 안내
- 입찰/채용 게시글, 연구성과, 170주년 기념사업 공식 안내

## 질문과 답변 방식

README의 질문 예시는 `data/qa/public_api_eval_corpus_1000.jsonl`과 `docs/qa/`의 공개 검증 기록을 기준으로 잡았습니다. 질문은 자연어 그대로 들어오지만, 서버는 내부적으로 공식 source를 조회할 수 있는 MCP tool 또는 HTTP endpoint로 바꿔 실행하고, 답변에는 **핵심 결과, 근거 source, 불확실성/fallback 상태**를 함께 담는 것을 목표로 합니다.

| 사용자가 묻는 말 | 조회 흐름 | 답변에 담는 내용 |
| --- | --- | --- |
| `K관 먼저 알려주고 핵심만 같이 정리해줘` | `tool_search_places` -> `tool_get_place` 또는 `/places?query=K관` | `K관`을 `김수환관`으로 정규화하고, 건물/시설 분류, 대표 위치, 연결된 시설 정보를 함께 제공합니다. QA truth 기준으로 ATM 질문은 `김수환관(K관) 1층 우리은행`까지 연결됩니다. |
| `04483 검색해줘` | `tool_search_courses` 또는 `/courses?query=04483&year=2026&semester=1` | 과목 코드, 과목명, 교수명, 연도/학기, 시작 교시를 구조화해서 반환합니다. 공개 QA snapshot에서는 `04483 -> 3D애니메이션1 / 신은하 / 2026-1 / 7교시`가 stable truth로 고정되어 있습니다. |
| `자료구조 과목 뭐야`, `객체지향 과목 2개만` | `tool_search_courses` | 띄어쓰기, 일부 표기 차이, 과목명/교수명/강의실 query를 정규화해 후보를 돌려줍니다. source-backed direct hit가 없으면 임의로 과목을 만들지 않고 watchlist 또는 빈 결과로 분리합니다. |
| `academic 공지 알려줘` | `tool_list_latest_notices` 또는 `/notices?category=academic` | 공지 제목, 카테고리, 게시일, 원문 URL을 반환합니다. 예를 들어 live validation에서는 `멘토 주관 프로그램`, `YBM 온라인 모의 토익/토익스피킹`, `Major Discovery Week` 같은 학사 공지가 `academic`으로 확인됐습니다. |
| `학사일정 10월 일정 보여줘` | `songsim://academic-calendar` 또는 `/academic-calendar?academic_year=2026&month=10` | 일정명, 시작일, 종료일, 해당 캠퍼스를 보여줍니다. 공개 QA 기준 2026년 10월에는 `중간고사`, `수업일수 1/2` 같은 일정이 포함됩니다. |
| `기숙사 운영팀 전화번호 알려줘` | `tool_search_phone_book` 또는 `/phone-book?query=기숙사 운영팀` | 부서명, 담당 업무, 전화번호를 분리해 반환합니다. 공개 QA truth는 `기숙사운영팀 / 기숙사 운영 / 4661`처럼 짧은 연락처도 구조화해 검증합니다. |
| `학생식당 근처 한식집 추천해줘` | `tool_find_nearby_restaurants` 또는 `/restaurants/nearby` | 기준 위치, 음식점명, 카테고리, 거리, 예상 도보 시간, 가격 힌트, 영업 여부를 가능한 범위에서 제공합니다. 가격이나 영업 상태 근거가 없으면 `budget_max`나 `open_now` 필터에서 제외하거나 빈 결과로 답합니다. |
| `K관 지금 빈 강의실 있어?` | `tool_list_estimated_empty_classrooms` 또는 `/classrooms/empty` | 실시간 source를 먼저 확인하고, 없으면 시간표 기반 `estimated` 결과와 fallback note를 붙입니다. 건물은 `K관 -> 김수환관`처럼 alias를 먼저 정규화합니다. |
| `무선랜 안내 보여줘` | `songsim://usage-guide` + `/wifi-guides` | 건물별 SSID와 접속 안내를 반환합니다. 공개 QA truth는 니콜스관 `catholic_univ`, 강의실 호실명 SSID, 미카엘관 `catholic_mica`, 다솔관 `catholic_dasol` 같은 값을 확인합니다. |
| `내 시간표 보여줘`, `관리자 화면 열어줘` | usage guide policy | 공개 read-only surface 범위를 벗어난 요청으로 보고 거절합니다. profile, 개인 시간표, 내부 admin, 쓰기 작업은 기본 공개 답변 대상이 아닙니다. |

답변은 다음 원칙으로 정리합니다.

- 먼저 바로 쓸 수 있는 결론을 1~3개로 보여주고, 이어서 원문 source나 endpoint 근거를 붙입니다.
- 같은 질문이라도 `지금 기준`, `먼저 알려줘`, `핵심만`, 띄어쓰기 오류가 섞인 경우를 QA corpus에 넣어 회귀 테스트합니다.
- source gap은 실패와 분리합니다. 예를 들어 `CSE301`, `김가톨`, `CSE 420`처럼 공식 snapshot에서 direct hit가 확인되지 않은 질문은 릴리즈 fail이 아니라 watchlist로 둡니다.
- 식당, 도서관 좌석, 빈 강의실처럼 live source 의존도가 큰 답변은 stale fallback 또는 estimated 상태를 명시합니다.

## 질문과 답변 방식

README의 질문 예시는 `data/qa/public_api_eval_corpus_1000.jsonl`과 `docs/qa/`의 공개 검증 기록을 기준으로 잡았습니다. 질문은 자연어 그대로 들어오지만, 서버는 내부적으로 공식 source를 조회할 수 있는 MCP tool 또는 HTTP endpoint로 바꿔 실행하고, 답변에는 **핵심 결과, 근거 source, 불확실성/fallback 상태**를 함께 담는 것을 목표로 합니다.

| 사용자가 묻는 말 | 조회 흐름 | 답변에 담는 내용 |
| --- | --- | --- |
| `K관 먼저 알려주고 핵심만 같이 정리해줘` | `tool_search_places` -> `tool_get_place` 또는 `/places?query=K관` | `K관`을 `김수환관`으로 정규화하고, 건물/시설 분류, 대표 위치, 연결된 시설 정보를 함께 제공합니다. QA truth 기준으로 ATM 질문은 `김수환관(K관) 1층 우리은행`까지 연결됩니다. |
| `04483 검색해줘` | `tool_search_courses` 또는 `/courses?query=04483&year=2026&semester=1` | 과목 코드, 과목명, 교수명, 연도/학기, 시작 교시를 구조화해서 반환합니다. 공개 QA snapshot에서는 `04483 -> 3D애니메이션1 / 신은하 / 2026-1 / 7교시`가 stable truth로 고정되어 있습니다. |
| `자료구조 과목 뭐야`, `객체지향 과목 2개만` | `tool_search_courses` | 띄어쓰기, 일부 표기 차이, 과목명/교수명/강의실 query를 정규화해 후보를 돌려줍니다. source-backed direct hit가 없으면 임의로 과목을 만들지 않고 watchlist 또는 빈 결과로 분리합니다. |
| `academic 공지 알려줘` | `tool_list_latest_notices` 또는 `/notices?category=academic` | 공지 제목, 카테고리, 게시일, 원문 URL을 반환합니다. 예를 들어 live validation에서는 `멘토 주관 프로그램`, `YBM 온라인 모의 토익/토익스피킹`, `Major Discovery Week` 같은 학사 공지가 `academic`으로 확인됐습니다. |
| `학사일정 10월 일정 보여줘` | `songsim://academic-calendar` 또는 `/academic-calendar?academic_year=2026&month=10` | 일정명, 시작일, 종료일, 해당 캠퍼스를 보여줍니다. 공개 QA 기준 2026년 10월에는 `중간고사`, `수업일수 1/2` 같은 일정이 포함됩니다. |
| `기숙사 운영팀 전화번호 알려줘` | `tool_search_phone_book` 또는 `/phone-book?query=기숙사 운영팀` | 부서명, 담당 업무, 전화번호를 분리해 반환합니다. 공개 QA truth는 `기숙사운영팀 / 기숙사 운영 / 4661`처럼 짧은 연락처도 구조화해 검증합니다. |
| `학생식당 근처 한식집 추천해줘` | `tool_find_nearby_restaurants` 또는 `/restaurants/nearby` | 기준 위치, 음식점명, 카테고리, 거리, 예상 도보 시간, 가격 힌트, 영업 여부를 가능한 범위에서 제공합니다. 가격이나 영업 상태 근거가 없으면 `budget_max`나 `open_now` 필터에서 제외하거나 빈 결과로 답합니다. |
| `K관 지금 빈 강의실 있어?` | `tool_list_estimated_empty_classrooms` 또는 `/classrooms/empty` | 실시간 source를 먼저 확인하고, 없으면 시간표 기반 `estimated` 결과와 fallback note를 붙입니다. 건물은 `K관 -> 김수환관`처럼 alias를 먼저 정규화합니다. |
| `무선랜 안내 보여줘` | `songsim://usage-guide` + `/wifi-guides` | 건물별 SSID와 접속 안내를 반환합니다. 공개 QA truth는 니콜스관 `catholic_univ`, 강의실 호실명 SSID, 미카엘관 `catholic_mica`, 다솔관 `catholic_dasol` 같은 값을 확인합니다. |
| `내 시간표 보여줘`, `관리자 화면 열어줘` | usage guide policy | 공개 read-only surface 범위를 벗어난 요청으로 보고 거절합니다. profile, 개인 시간표, 내부 admin, 쓰기 작업은 기본 공개 답변 대상이 아닙니다. |

답변은 다음 원칙으로 정리합니다.

- 먼저 바로 쓸 수 있는 결론을 1~3개로 보여주고, 이어서 원문 source나 endpoint 근거를 붙입니다.
- 같은 질문이라도 `지금 기준`, `먼저 알려줘`, `핵심만`, 띄어쓰기 오류가 섞인 경우를 QA corpus에 넣어 회귀 테스트합니다.
- source gap은 실패와 분리합니다. 예를 들어 `CSE301`, `김가톨`, `CSE 420`처럼 공식 snapshot에서 direct hit가 확인되지 않은 질문은 릴리즈 fail이 아니라 watchlist로 둡니다.
- 식당, 도서관 좌석, 빈 강의실처럼 live source 의존도가 큰 답변은 stale fallback 또는 estimated 상태를 명시합니다.

## Surface

Remote MCP는 학생이 LLM 클라이언트에서 직접 쓰는 기본 진입점입니다. HTTP API는 같은 데이터를 직접 확인하거나 외부 앱에서 연결하는 companion layer입니다.

대표 MCP resource/tool:

- `songsim://usage-guide`
- `songsim://academic-calendar`
- `songsim://registration-guide`
- `songsim://class-guide`
- `songsim://student-exchange-guide`
- `songsim://student-activity-guide`
- `songsim://student-activity-notices`
- `songsim://service-policy-guide`
- `songsim://service-policy-posts`
- `songsim://newsroom-posts`
- `songsim://research-posts`
- `songsim://newsroom-resource-guide`
- `songsim://anniversary-guide`
- `songsim://phone-book`
- `songsim://dormitory-guide`
- `tool_search_places`
- `tool_search_courses`
- `tool_search_phone_book`
- `tool_list_latest_notices`
- `tool_list_affiliated_notices`
- `tool_list_student_activity_guides`
- `tool_list_student_activity_notices`
- `tool_list_service_policy_guides`
- `tool_list_service_policy_posts`
- `tool_list_newsroom_posts`
- `tool_list_research_posts`
- `tool_list_newsroom_resource_guides`
- `tool_list_anniversary_guides`
- `tool_search_dining_menus`
- `tool_find_nearby_restaurants`
- `tool_get_library_seat_status`
- `tool_list_estimated_empty_classrooms`

대표 HTTP endpoint:

- `/places`
- `/phone-book`
- `/courses`
- `/academic-calendar`
- `/registration-guides`
- `/class-guides`
- `/student-exchange-guides`
- `/student-activity-guides`
- `/student-activity-notices`
- `/about-resource-guides`
- `/service-policy-guides`
- `/service-policy-posts`
- `/campus-life-support-guides`
- `/scholarship-guides`
- `/notices`
- `/affiliated-notices`
- `/campus-life-notices`
- `/newsroom-posts`
- `/research-posts`
- `/newsroom-resource-guides`
- `/anniversary-guides`
- `/dormitory-guides`
- `/pc-software`
- `/dining-menus`
- `/restaurants/nearby`
- `/library-seats`
- `/classrooms/empty`
- `/transport`
- `/wifi-guides`

## 신뢰 정책

- 학교 공식 source에 없는 값은 만들지 않습니다.
- 없거나 불확실한 값은 `null`, 빈 결과, 또는 명시적인 fallback 상태로 반환합니다.
- 주변 식당/브랜드 검색은 Kakao Local 외부 공개 API 기반 편의 surface이며, 학교 공식 1차 source coverage와 별도 범주로 봅니다.
- 도서관 좌석은 live fetch 후 stale fallback을 사용할 수 있습니다.
- 예상 빈 강의실은 realtime source를 먼저 시도하고, 없으면 시간표 기준 예상 공실로 폴백합니다.
- 기본 공개 surface는 profile 개인화, 내부 admin, observability, GPT Actions packaging layer를 중심 기능으로 두지 않습니다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Runtime | Python 3.12+ |
| API | FastAPI, Uvicorn |
| MCP | MCP optional extra |
| Data | PostgreSQL, psycopg, pydantic |
| Ingest | httpx, BeautifulSoup, pypdf, Playwright optional extra |
| Quality | pytest, ruff, public QA corpus |
| Deployment | Render blueprint (`render.yaml`) |

## 프로젝트 구조

```text
src/songsim_campus/
├── api.py                     # HTTP API entrypoint
├── mcp_server.py              # MCP server entrypoint
├── ingest/                    # 공식 source와 외부 데이터 수집기
├── *_runtime.py               # 검색/메뉴/좌석 등 runtime service
├── repo.py, db.py             # 저장소와 DB 접근
├── schema.sql                 # PostgreSQL schema
└── qa_eval.py                 # 공개 QA 평가 실행
data/                          # 샘플 데이터, alias, QA corpus
docs/                          # 연결 가이드, source registry, QA 문서
tests/                         # API, MCP, ingest, runtime 회귀 테스트
```

## 로컬 실행

```bash
uv sync --extra dev --extra mcp --extra scrape
cp .env.example .env
docker compose up -d postgres
```

데모 데이터:

```bash
uv run songsim-seed-demo --force
```

공식 데이터 동기화:

```bash
uv run songsim-sync --year <year> --semester <1-or-2> --notice-pages 1
```

HTTP API:

```bash
uv run songsim-api
```

MCP 서버:

```bash
uv run songsim-mcp --transport stdio
uv run songsim-mcp --transport streamable-http
```

개발 환경에서 확인할 수 있는 문서:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/gpt-actions-openapi-v3.json`

## 검증

```bash
uv run pytest
uv run ruff check .
uv run songsim-eval-public run \
  --truth data/qa/public_api_eval_truth_1000.jsonl \
  --report /tmp/songsim-public-api-validation.md
```

공개 API와 MCP 검증 기록은 `docs/qa/` 아래의 live validation 문서와 release pack 문서에서 확인할 수 있습니다.
