# Connect From ChatGPT

## 연결 정보

- 이름 예시: `Songsim Campus MCP`
- URL: `https://your-public-mcp-url/mcp`
- 모드: read-only public server
- 기본 입구: student-facing primary surface는 Remote MCP, HTTP API는 companion layer
- 로그인: 현재 공개 배포 기본값은 익명 read-only, 운영자가 OAuth 모드로 바꾸면 로그인 필요

## 이 공개 MCP를 먼저 어디에 쓰나

- 오늘 할 일: 최신 공지, 소속기관 공지, 행사/대외 프로그램, 학사일정
- 어디 / 연락처: 건물, 별칭, 편의시설, 전화번호, 운영시간, 교통, Wi-Fi
- 절차 / 제도: 등록, 증명, 휴학, 수업, 계절학기, 성적·졸업, 학생교류, 장학
- 공부공간 / 자원: 과목, 교시, 도서관 좌석, 예상 빈 강의실, 학식, 주변 식당, PC 소프트웨어
- 특수 경로: 기숙사, 생활지원, 상담·예비군·병원, 소속기관 공지

공개 서버는 read-only라서 profile, timetable, admin 기능은 제공하지 않습니다.

## 추천 사용 흐름

1. `songsim://usage-guide` resource를 먼저 읽어 공개 MCP 범위를 확인
2. 질문이 어느 학생 여정에 속하는지 먼저 정한 뒤, 맞는 prompt / resource / tool을 고름
3. 같은 결과를 직접 검증하거나 외부 앱에 붙이고 싶을 때만 HTTP companion을 함께 사용

운영상 알아둘 점:

- 강의실 공실은 공식 실시간 source가 있으면 그 결과를 우선 쓰고, 없으면 시간표 기준 예상 공실로 자동 폴백합니다.
- 중앙도서관 좌석은 best-effort 실시간 조회이고, source가 불안정하면 stale cache 또는 unavailable note가 함께 내려올 수 있습니다.
- 식당 조회에서 `budget_max`를 주면 가격 정보가 확인된 후보만 남습니다.
- 주변 식당은 학교 공식 source가 아니라 Kakao Local 외부 공개 API 기반 편의 기능입니다.
- 공개 데이터 신뢰 상태는 HTTP `/status` 또는 MCP `songsim://status`에서 확인할 수 있습니다.

## 연결 후 바로 해볼 질문

처음 연결한 학생 기준 30초 테스트:

- `최신 학사 공지 2개 보여줘`
- `학생회관 어디야?`
- `중앙도서관 열람실 남은 좌석 알려줘`
- `내 시간표 저장해줘`

마지막 질문은 공개 read-only 범위 밖이므로 저장을 거절하고 Local Full Mode나 개인 시스템 범위를 안내하는 것이 정상입니다.

### 오늘 할 일

- `최신 학사 공지 2개 보여줘`
- `국제학부 최신 공지 알려줘`
- `행사안내 보여줘`
- `2026학년도 3월 학사일정 보여줘`

### 어디 / 연락처

- `학생회관 어디야?`
- `복사실이 어디야?`
- `보건실 전화번호 알려줘`
- `니콜스관 WIFI 안내 알려줘`

### 절차 / 제도

- `등록금 반환 기준 알려줘`
- `재학증명서 발급 안내 알려줘`
- `공결 신청 방법 알려줘`
- `계절학기 신청 시기 알려줘`
- `졸업요건 알려줘`
- `국내 학점교류 신청대상 알려줘`

### 공부공간 / 자원

- `7교시에 시작하는 과목 찾고 싶어`
- `중앙도서관 열람실 남은 좌석 알려줘`
- `K관 지금 빈 강의실 있어?`
- `학생식당 메뉴 보여줘`
- `중앙도서관 근처 한식집 찾아줘`
- `SPSS 설치된 컴퓨터실 어디야`

### 특수 경로

- `성심교정 기숙사 안내해줘`
- `학생상담 어디서 받아?`
- `예비군 신고 시기 알려줘`
- `부속병원 이용 안내해줘`
- `프란치스코관 입퇴사공지 알려줘`

## GPT 링크로 공개하고 싶을 때

ChatGPT의 `chatgpt.com/g/...` 링크를 만들고 싶다면 MCP connector 대신 GPT Builder의 `Actions`를 사용할 수 있습니다. 다만 학생용 기본 입구는 MCP connector이고, GPT Actions는 선택적 포장층입니다.

- Shared GPT schema URL: `https://your-public-api-url/gpt-actions-openapi-v3.json`
- Slim demo / legacy schema URL: `https://your-public-api-url/gpt-actions-openapi-v2.json`
- Privacy Policy URL: `https://your-public-api-url/privacy`
- 인증: `None`
- shared GPT는 `v3`를 쓰고, `v2`는 슬림 데모나 레거시 호환용으로만 둡니다.
- 일반 학생 사용 기준으로는 MCP connector를 먼저 권장합니다.
- 기존 `gpt-actions-openapi.json`은 회귀용으로 남아 있지만, 학생-facing 기본 문서에서는 전면에 두지 않습니다.

Builder에 넣을 수 있는 최소 Instructions 예시:

```text
You are a read-only student assistant for Songsim Campus.
Use the connected action first for any campus question.
Prefer the action over memory or web search.
Do not invent school data.
If the action cannot verify something, say so briefly and suggest the closest verifiable alternative.
Keep answers short, practical, and campus-specific.
```

## 공개 서버 제한

- 현재 공개 기본 배포는 익명 read-only라서 바로 연결되는 것이 정상입니다.
- 운영자가 OAuth 모드로 바꾸면 로그인 화면이 다시 나타날 수 있습니다.
- 프로필 생성, 시간표 저장, meal personalization, admin 기능은 공개 서버에서 제공하지 않습니다.
- Local Full Mode는 운영과 개인화용 별도 모드입니다.

## 검증 자산

전체 검증 자산은 `docs/qa/` 아래에서 운영합니다. ChatGPT 연결 문서는 MCP를 학생용 기본 입구로 보고, GPT Actions는 선택적 포장층으로만 다룹니다.

- [공개 MCP 500문장 코퍼스](qa/public-mcp-corpus-500.md)
- [공개 MCP 릴리즈팩 50](qa/public-mcp-release-pack-50.md)
- [공개 MCP 라이브 판정표 50](qa/public-mcp-live-validation-50.md)
- [공개 MCP 라이브 판정 요약](qa/public-mcp-live-validation-summary.md)
- [공개 API 1000문장 라이브 검증](qa/public-api-live-validation-1000.md)
