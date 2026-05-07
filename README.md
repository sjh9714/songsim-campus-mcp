# songsim-campus-mcp

`songsim-campus-mcp`는 가톨릭대학교 성심교정 학생이 자주 묻는 학사·생활 정보를 **공식 source 기반 Remote MCP + HTTP API**로 제공하는 캠퍼스 도우미 서버입니다. 공지, 학사일정, 건물/연락처, 강의, 도서관 좌석, 식당, Wi-Fi, 기숙사와 생활지원 정보를 LLM 클라이언트에서 읽기 전용으로 조회할 수 있게 구성했습니다.

## 문제의식

학생이 필요한 정보는 학교 홈페이지, 공지 게시판, 학사 안내, 시설 안내에 흩어져 있습니다. 이 프로젝트는 "성심교정에서 지금 필요한 답"을 하나의 student-facing surface로 묶고, 공식 source에 없는 값은 만들지 않는 방식으로 신뢰 경계를 드러냅니다.

## 주요 사용 질문

- 최신 학사 공지와 소속기관 공지
- 포토뉴스와 보도자료
- 월별 학사일정과 등록·휴학·복학·증명·장학 안내
- 건물, 시설, 편의시설, 전화번호, 운영시간
- 과목 검색, 교시 정보, 도서관 좌석, 예상 빈 강의실
- 학식, 주변 식당, PC 소프트웨어, Wi-Fi
- 기숙사, 상담, 병원, 예비군, 학생활동 안내

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
- `songsim://newsroom-posts`
- `songsim://phone-book`
- `songsim://dormitory-guide`
- `tool_search_places`
- `tool_search_courses`
- `tool_search_phone_book`
- `tool_list_latest_notices`
- `tool_list_affiliated_notices`
- `tool_list_student_activity_notices`
- `tool_list_service_policy_guides`
- `tool_list_newsroom_posts`
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
- `/scholarship-guides`
- `/notices`
- `/affiliated-notices`
- `/campus-life-notices`
- `/newsroom-posts`
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
uv run songsim-eval-public
```

공개 API와 MCP 검증 기록은 `docs/qa/` 아래의 live validation 문서와 release pack 문서에서 확인할 수 있습니다.
