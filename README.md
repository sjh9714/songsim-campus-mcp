# 성심교정 도우미

가톨릭대학교 성심교정 학생이 **학교에서 헤매지 않도록** 만든 캠퍼스 안내 서비스입니다.  
학식, 도서관 좌석, 빈 강의실, 공지, 건물과 전화번호를 공식 source 기준으로 한 곳에 모았습니다.

[![Official Source](https://img.shields.io/badge/Source-official%20first-2563EB)](docs/source_registry.md)
[![Public QA](https://img.shields.io/badge/Public%20QA-hard%20fail%200-brightgreen)](docs/qa/public-api-live-validation-1000.md)

---

## 학생이라면 — 이것만 열면 됩니다

**설치도, 로그인도, AI 계정도 필요 없습니다.** 폰 브라우저에서 주소만 열면 끝입니다.

> 배포 주소는 준비되는 대로 여기에 적습니다. 아직 호스팅 전이라면
> [학생용 웹 배포 가이드](docs/deploy-web.md)를 따라 올리면 됩니다.

열면 바로 보이는 것

| | |
|---|---|
| 🍚 **학식** | 오늘 교내 식당에 뭐 나오는지 |
| 📚 **공부할 곳** | 도서관 남은 좌석, 지금 빈 강의실 |
| 📢 **공지** | 학사·장학·행사 공지 모아보기 |
| 🔎 **찾기** | "복사실 어디야?", "보건실 몇 번이야?" |

홈 화면에 추가하면 앱처럼 열립니다.

---

## 개발자·AI 앱 연동

학생용 웹 말고 **직접 연동**하려는 경우에만 필요한 내용입니다.

<details>
<summary>Remote MCP / HTTP API / ChatGPT GPT 연결하기</summary>

### ChatGPT

바로 사용할 수 있는 shared GPT가 열려 있습니다.

- **웹 GPT 주소:** `https://chatgpt.com/g/g-69b526a162c48191843a6a7f469f5030-gatolrigdae-seongsimgyojeong-doumi`
- **바로가기:** [가톨릭대 성심교정 도우미](https://chatgpt.com/g/g-69b526a162c48191843a6a7f469f5030-gatolrigdae-seongsimgyojeong-doumi)
- **추천 연결 방식:** MCP connector
- **MCP URL:** `https://songsim-public-mcp.onrender.com/mcp`
- **모드:** read-only public server

공유 GPT를 직접 구성할 때는 아래 값을 사용하면 됩니다.

- **Schema:** `https://songsim-public-api.onrender.com/gpt-actions-openapi-v3.json`
- **Privacy:** `https://songsim-public-api.onrender.com/privacy`
- **Auth:** `None`

자세한 설정은 [Connect ChatGPT](docs/connect-chatgpt.md)에서 볼 수 있습니다.

### Codex

- 가이드: [docs/connect-codex.md](docs/connect-codex.md)

### Claude

- 가이드: [docs/connect-claude.md](docs/connect-claude.md)

</details>

**문서 바로가기**  
[학생용 웹 배포](docs/deploy-web.md) · [Render 배포](docs/deploy-render.md) · [Connect ChatGPT](docs/connect-chatgpt.md) · [Connect Codex](docs/connect-codex.md) · [Connect Claude](docs/connect-claude.md) · [Source Registry](docs/source_registry.md)

---

## 이런 질문을 해결합니다

### 오늘 할 일
- 최신 학사 공지
- 소속기관 공지
- 행사 / 대외 프로그램 공지
- 월별 학사일정

예시

```text
최신 학사 공지 2개 보여줘
국제학부 최신 공지 알려줘
행사안내 보여줘
2026학년도 3월 학사일정 보여줘
```

### 어디 / 연락처
- 건물 / 시설 / 편의시설
- 전화번호 / 운영시간
- 교통 / Wi-Fi

예시

```text
학생회관 어디야?
복사실이 어디야?
보건실 전화번호 알려줘
니콜스관 WIFI 안내 알려줘
```

### 절차 / 제도
- 등록
- 증명
- 휴학 / 복학 / 자퇴 / 재입학
- 수업 / 공결 / 계절학기
- 성적 / 졸업
- 학생교류
- 장학

예시

```text
등록금 반환 기준 알려줘
재학증명서 발급 방법 알려줘
공결 신청 방법 알려줘
계절학기 신청 시기 알려줘
졸업요건 알려줘
국내 학점교류 신청대상 알려줘
```

### 공부공간 / 자원
- 과목 검색
- 교시 정보
- 도서관 좌석
- 예상 빈 강의실
- 학식
- 주변 식당
- PC 소프트웨어

예시

```text
7교시가 몇 시야?
2026년 1학기 객체지향 과목 찾아줘
중앙도서관 열람실 남은 좌석 알려줘
K관 지금 예상 빈 강의실 있어?
학생식당 메뉴 보여줘
SPSS 설치된 컴퓨터실 어디야?
```

### 특수 경로
- 기숙사
- 생활지원
- 상담 / 예비군 / 병원
- 학생활동
- 소속기관 공지

예시

```text
성심교정 기숙사 안내해줘
학생상담 어디서 받아?
예비군 신고 시기 알려줘
부속병원 이용 안내해줘
총학생회 안내해줘
프란치스코관 입퇴사공지 알려줘
```

---

## Student-facing Surface

### 모바일 웹 (`web/`)

학생이 실제로 쓰는 **primary surface**입니다. Next.js로 만들었고 백엔드 HTTP API를 그대로 씁니다.

- 카드 홈: 학식 / 도서관 좌석 / 최신 공지 / 장소·연락처
- 통합 검색: 장소, 부서 전화번호, 과목, PC 소프트웨어
- 무로그인 개인화: 마지막으로 본 건물을 브라우저에만 기억
- 백엔드가 잠들어 있어도 캐시로 즉시 화면을 보여주고, 못 받아온 값은 만들어내지 않습니다

### Remote MCP

학생이 LLM 클라이언트에서 직접 쓰는 surface입니다.

대표 resource / tool

- `songsim://usage-guide`
- `songsim://academic-calendar`
- `songsim://registration-guide`
- `songsim://class-guide`
- `songsim://academic-milestone-guide`
- `songsim://student-exchange-guide`
- `songsim://student-exchange-partners`
- `songsim://student-activity-guide`
- `songsim://phone-book`
- `songsim://campus-life-support-guide`
- `songsim://dormitory-guide`
- `songsim://certificate-guide`
- `songsim://scholarship-guide`
- `songsim://affiliated-notices`
- `songsim://campus-life-notices`
- `songsim://transport-guide`
- `songsim://wifi-guide`
- `tool_search_places`
- `tool_search_courses`
- `tool_search_phone_book`
- `tool_search_pc_software`
- `tool_list_latest_notices`
- `tool_list_affiliated_notices`
- `tool_list_campus_life_notices`
- `tool_list_student_activity_guides`
- `tool_search_dining_menus`
- `tool_find_nearby_restaurants`
- `tool_get_library_seat_status`
- `tool_list_estimated_empty_classrooms`

### HTTP API

같은 데이터를 직접 확인하거나 앱에 붙일 때 쓰는 **companion layer**입니다.

대표 endpoint

- `/places`
- `/phone-book`
- `/courses`
- `/periods`
- `/academic-calendar`
- `/registration-guides`
- `/class-guides`
- `/seasonal-semester-guides`
- `/academic-milestone-guides`
- `/student-exchange-guides`
- `/student-exchange-partners`
- `/student-activity-guides`
- `/certificate-guides`
- `/leave-of-absence-guides`
- `/academic-status-guides`
- `/academic-support-guides`
- `/scholarship-guides`
- `/notices`
- `/affiliated-notices`
- `/campus-life-notices`
- `/dormitory-guides`
- `/campus-life-support-guides`
- `/pc-software`
- `/dining-menus`
- `/restaurants/nearby`
- `/restaurants/search`
- `/library-seats`
- `/classrooms/empty`
- `/transport`
- `/wifi-guides`

---

## 신뢰 정책

이 프로젝트는 **정답을 꾸며내는 대신 신뢰 경계를 드러내는 방식**을 택합니다.

- 학교 공식 source에 없는 값은 만들지 않습니다.
- 없거나 불확실하면 `null` 또는 빈 결과를 반환합니다.
- 일부 동적 도메인은 best-effort / fallback 정책을 명시적으로 사용합니다.

현재 기준

- **도서관 좌석:** `live fetch + stale fallback`
- **예상 빈 강의실:** `realtime` source를 먼저 시도하고, 없으면 시간표 기준 예상 공실로 폴백

---

## 품질 검증

공개 student surface는 설명만이 아니라 **live validation baseline**으로 관리합니다.

### Public API live baseline
- checked_at: `2026-03-21T12:31:05+00:00`
- corpus size: `1000`
- executed: `1005`
- hard fail: `0`
- watch: `5`
- skip: `104`

### Public MCP live summary
- release pack size: `50`
- executed: `50 / 50`
- pass: `43`
- soft_pass: `7`
- fail: `0`

자세한 문서

- [Public API Live Validation Baseline](docs/qa/public-api-live-validation-1000.md)
- [Public MCP Release Pack (50)](docs/qa/public-mcp-release-pack-50.md)
- [Public MCP Live Validation Summary](docs/qa/public-mcp-live-validation-summary.md)

---

## Quick Start

### 1. Install

```bash
uv sync --extra dev --extra mcp --extra scrape
```

또는

```bash
pip install -e '.[dev,mcp,scrape]'
```

### 2. Configure

```bash
cp .env.example .env
```

공개 read-only 배포 예시

```bash
SONGSIM_APP_MODE=public_readonly
SONGSIM_PUBLIC_HTTP_URL=https://your-public-api-url
SONGSIM_PUBLIC_MCP_URL=https://your-public-mcp-url/mcp
SONGSIM_PUBLIC_MCP_AUTH_MODE=anonymous
```

공개 MCP를 OAuth로 보호하려면

```bash
SONGSIM_PUBLIC_MCP_AUTH_MODE=oauth
SONGSIM_MCP_OAUTH_ENABLED=true
SONGSIM_MCP_OAUTH_ISSUER=https://your-tenant.us.auth0.com/
SONGSIM_MCP_OAUTH_AUDIENCE=https://your-public-mcp-url/mcp
SONGSIM_MCP_OAUTH_SCOPES=songsim.read
```

### 3. Run Local Postgres

```bash
docker compose up -d postgres
```

### 4. Seed or Sync

데모 데이터

```bash
uv run songsim-seed-demo --force
```

공식 데이터

```bash
uv run songsim-sync --year <current-year> --semester <1-or-2> --notice-pages 1
```

### 5. Run HTTP API

```bash
uv run songsim-api
```

- docs: `http://127.0.0.1:8000/docs`
- shared GPT schema v3: `http://127.0.0.1:8000/gpt-actions-openapi-v3.json`
- shared GPT schema v2: `http://127.0.0.1:8000/gpt-actions-openapi-v2.json`
- legacy schema v1: `http://127.0.0.1:8000/gpt-actions-openapi.json`

### 6. Run Student Web

```bash
cd web
npm install
cp .env.example .env.local   # SONGSIM_API_BASE 를 위에서 띄운 API 주소로
npm run dev
```

- 웹: `http://localhost:3000`
- 배포 방법은 [학생용 웹 배포 가이드](docs/deploy-web.md) 참고

### 7. Run MCP Server

stdio

```bash
uv run songsim-mcp --transport stdio
```

streamable HTTP

```bash
uv run songsim-mcp --transport streamable-http
```

---

## Example HTTP Calls

```bash
curl 'http://127.0.0.1:8000/places?query=학생회관%20어디야?'
curl 'http://127.0.0.1:8000/phone-book?query=보건실'
curl 'http://127.0.0.1:8000/courses?query=객체지향&year=2026&semester=1'
curl 'http://127.0.0.1:8000/academic-calendar?academic_year=2026&month=3'
curl 'http://127.0.0.1:8000/registration-guides?topic=payment_and_return&limit=2'
curl 'http://127.0.0.1:8000/notices?category=academic&limit=3'
curl 'http://127.0.0.1:8000/dining-menus?query=학생식당'
curl 'http://127.0.0.1:8000/library-seats'
curl 'http://127.0.0.1:8000/classrooms/empty?building=%EB%8B%88%EC%BD%9C%EC%8A%A4%EA%B4%80&at=2026-03-16T10:15:00%2B09:00'
curl 'http://127.0.0.1:8000/wifi-guides'
```

---

## Out of Scope

아래는 기본 공개 surface의 중심은 아닙니다.

- profile 개인화
- 시간표 저장
- 관심사 기반 추천
- `/admin/*`
- `/readyz`
- observability
- 내부 automation
- `/gpt/*` 및 GPT Actions packaging layer
  - 공개 기본 진입면은 아니고, shared GPT 연결용 secondary surface입니다.

---

## 문서

- [Connect ChatGPT](docs/connect-chatgpt.md)
- [Connect Codex](docs/connect-codex.md)
- [Connect Claude](docs/connect-claude.md)
- [Source Registry](docs/source_registry.md)
- [Render Deploy Guide](docs/deploy-render.md)
- [Public API Live Validation Baseline](docs/qa/public-api-live-validation-1000.md)
- [Public MCP Release Pack (50)](docs/qa/public-mcp-release-pack-50.md)
- [Public MCP Live Validation Summary](docs/qa/public-mcp-live-validation-summary.md)

---

## 한 줄 요약

**성심교정 도우미는 학생이 링크 하나만 열면 학교에서 헤매지 않도록, 공식 데이터를 모바일 웹·Remote MCP·HTTP API로 제공하는 프로젝트입니다.**
