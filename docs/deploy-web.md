# 학생용 웹 배포 (Vercel)

`web/`의 Next.js 앱을 Vercel에 올리는 방법입니다. 백엔드(Render)는 그대로 두고 프론트만 올립니다.

## 왜 Vercel인가

Render 무료 플랜 백엔드는 15분간 요청이 없으면 잠들고, 다시 깨우는 데 수십 초가 걸립니다.
학생이 "밥 뭐 나와?" 하고 링크를 눌렀을 때 40초짜리 빈 화면을 보면 다시 오지 않습니다.

Vercel의 ISR 캐시가 이걸 흡수합니다. 백엔드가 자고 있어도 학생은 마지막으로 받아둔 화면을
즉시 보고, 새 값은 백그라운드에서 채워집니다. `web/lib/api.ts`가 이 캐시 수명과 타임아웃,
실패 처리를 전부 담당합니다.

단, ISR은 오래된 응답을 한 번 먼저 줄 수 있어 **현재성의 보장 수단이 아닙니다**.
‘오늘’·상대 시각은 브라우저의 한국 시각으로 계산하고, 좌석과 선택 건물의 강의실은
`/api/live`의 no-store 요청으로 확인합니다. 60초를 넘긴 관측은 현재 숫자로 노출하지 않습니다
(표시 재판정 간격 15초). 백엔드 깨우기는 최대 50초, 브라우저 요청은 최대 55초로 제한하고
실패하면 새로고침과 원문 링크를 제공합니다. 백그라운드 탭에서는 정기 조회하지 않습니다.
프로세스별 마지막 성공값도 최대 200개·엔드포인트 TTL까지만 보존합니다.

## 배포 절차

### 1. Vercel 로그인

```bash
cd web
npx vercel login
```

브라우저가 열리면 GitHub 등으로 로그인합니다.

### 2. 프로젝트 연결

```bash
npx vercel link
```

- Framework는 Next.js로 자동 인식됩니다.
- Git 저장소 전체를 연결할 때 Root Directory는 `web`입니다.
  현재 `web/`에서 CLI로 올리는 `songsim-web` 프로젝트의 Root Directory는 `.`입니다.
  두 방식을 섞어 `web/web`을 찾게 하지 마세요.

### 3. 환경변수 설정

```bash
npx vercel env add SONGSIM_API_BASE production
# 값: https://songsim-api-sg.onrender.com

npx vercel env add NEXT_PUBLIC_KAKAO_MAP_JS_KEY production
# 값: Kakao Developers > 플랫폼 키 > JavaScript 키
```

Kakao Developers의 해당 JavaScript 키에는 다음 웹 도메인을 등록합니다.

- 로컬 확인: `http://localhost:3000`
- 운영: `https://songsim-web.vercel.app`

JavaScript 키는 브라우저에 포함되는 공개 키이므로 REST API 키를 대신 넣지 않습니다. 허용
도메인을 제한하고, 값을 바꾼 뒤에는 Next.js가 새 키를 빌드에 포함하도록 다시 배포합니다.

선택 항목 (기본값으로 충분합니다)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SONGSIM_API_BASE` | `http://127.0.0.1:8000` | 백엔드 HTTP API 주소 |
| `SONGSIM_API_TIMEOUT_MS` | `5000` | 일반 엔드포인트 제한시간 |
| `SONGSIM_API_LIVE_TIMEOUT_MS` | `15000` | `/library-seats` 처럼 외부 실시간 조회를 하는 엔드포인트용 |
| `NEXT_PUBLIC_KAKAO_MAP_JS_KEY` | 없음 | 장소 상세의 Kakao 미니 지도용 JavaScript 키. 없거나 로드에 실패해도 외부 지도·길찾기 링크는 유지 |

### 4. 배포

```bash
npx vercel --prod
```

### 5. 백엔드 랜딩 페이지에 학생용 링크 걸기

배포된 주소를 Render 환경변수에 넣으면, API 랜딩 페이지(`/`) 맨 위에
"학생이신가요?" 배너가 뜨면서 학생을 웹으로 보냅니다.

```
SONGSIM_STUDENT_WEB_URL=https://<배포된-주소>
```

`README.md`의 학생용 주소 자리에도 같은 값을 적어 주세요.

## 배포 후 확인할 것

`cd web`에서 `npm run lint`, `npm run typecheck`, `npm test`, `npm run test:e2e`를 실행합니다.
E2E 명령은 외부 API 대신 `data/qa/web-fixture.json`으로 프로덕션 빌드 후 390px에서 검증합니다.
`TEST_MAP_KEY=qa-sdk-failure-test npm run test:e2e`로 SDK 차단 경로도 검사합니다.
실제 운영 검증은 `npx playwright test --config playwright.production.config.ts`입니다.
GitHub의 `Check production student journeys`는 공식 동기화 종료 후 같은 검증을 실행합니다.
실패 trace는 Actions artifact에서 확인하며, 200 응답뿐 아니라 식단 수집 시각·검색·지도·전화 링크를 검사합니다.

1. **콜드 스타트** — Render 서비스를 15분 이상 놔둬서 잠들게 한 뒤 웹을 엽니다.
   화면이 즉시 떠야 합니다. 빈 화면이 오래 보이면 캐시 전략을 다시 봐야 합니다.
2. **백엔드 장애** — 각 카드가 "지금 학교 정보를 불러오지 못했어요"를 보여주는지.
   무한 로딩이나 에러 화면이 뜨면 안 됩니다.
3. **실기기** — 저사양 안드로이드 + 느린 회선에서 첫 화면.
4. **홈 화면에 추가** — 아이콘과 이름이 제대로 나오는지.
5. **장소 위치** — `/find/kim-sou-hwan-hall`에서 미니 지도와 `카카오맵 길찾기`가 열리는지.

## 알아둘 것

- **Vercel Hobby 플랜은 상업적 이용을 금지합니다.** 학생 대상 무료 서비스면 문제없지만,
  학교와 공식 연계하거나 광고가 붙으면 Pro 전환이 필요합니다.
- **Render 무료 Postgres는 만료됩니다.** 학생이 실제로 붙기 시작한 뒤 DB가 사라지면
  콜드 스타트보다 훨씬 큰 사고입니다. 배포 전에 DB 플랜과 만료일을 확인하세요.
- **Render 무료 웹 서비스는 월 750 인스턴스 시간**을 공유합니다. API와 MCP 두 개를
  24시간 켜두면 (2 × 730 = 1460시간) 한도를 넘겨 월말에 서비스가 정지됩니다.
