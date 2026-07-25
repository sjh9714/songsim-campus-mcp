# Deploy On Render + Supabase

이 프로젝트는 저비용 공개 테스트용으로 `Render web service 2개 + Supabase Postgres 1개` 구성을 기준으로 둡니다.

## 구성

- `songsim-public-api`
  - `songsim-api`
  - 공개 landing page, `/docs`, read-only HTTP API
  - automation `OFF` in `public_readonly`
- `songsim-public-mcp`
  - `songsim-mcp --transport streamable-http`
  - 공개 원격 MCP URL
  - automation `OFF`
- `Supabase`
  - 두 서비스가 함께 쓰는 Postgres

## 1. Supabase 준비

1. Supabase에서 새 프로젝트를 만듭니다.
2. Postgres 연결 문자열을 복사합니다.
3. 필요하면 SSL 옵션을 포함한 연결 문자열을 `SONGSIM_DATABASE_URL`로 사용합니다.

## 2. Render 배포

1. GitHub 저장소를 Render에 연결합니다.
2. 저장소 루트의 [render.yaml](../render.yaml)을 사용해 Blueprint 배포를 만듭니다.
3. 두 서비스 모두에 아래 secret env를 채웁니다.
   - `SONGSIM_DATABASE_URL`
   - `SONGSIM_KAKAO_REST_API_KEY`
   - 공개 MCP를 OAuth로 보호할 때만 `songsim-public-mcp`에 아래 env를 추가합니다.
     - `SONGSIM_PUBLIC_MCP_AUTH_MODE=oauth`
     - `SONGSIM_MCP_OAUTH_ENABLED=true`
     - `SONGSIM_MCP_OAUTH_ISSUER=https://<your-auth0-domain>/`
     - `SONGSIM_MCP_OAUTH_AUDIENCE=https://<your-mcp-render-url>/mcp`
     - `SONGSIM_MCP_OAUTH_SCOPES=songsim.read`
   - `songsim-public-api`는 기본 공개 배포에서 이 OAuth env가 필요하지 않습니다.
   - `songsim-public-api`에 같은 값을 미러링하는 것은 선택 사항이고, API landing page에서 public MCP가 OAuth로 보호된 상태라는 문구를 보여 주는 cosmetic 용도에 가깝습니다.
4. 배포가 생성되면 실제 Render URL을 보고 아래 값을 다시 채웁니다.
   - `songsim-public-api`의 `SONGSIM_PUBLIC_HTTP_URL`
   - `songsim-public-mcp`의 `SONGSIM_PUBLIC_MCP_URL`
5. 두 서비스를 한 번 더 재배포합니다.

## 3. 권장 공개 설정

- `SONGSIM_APP_MODE=public_readonly`
- `SONGSIM_SEED_DEMO_ON_START=false`
- `SONGSIM_SYNC_OFFICIAL_ON_START=false`
- `songsim-public-api`는 `SONGSIM_AUTOMATION_ENABLED=false`
- `songsim-public-api`는 live query/cache 경로를 사용하고, snapshot 동기화는 배포 전 운영자가 별도로 실행합니다.
- `songsim-public-mcp`는 `SONGSIM_AUTOMATION_ENABLED=false`
- `songsim-public-mcp`는 기본적으로 익명 read-only
- 공개 MCP를 보호해야 하면 `SONGSIM_PUBLIC_MCP_AUTH_MODE=oauth`로 전환
- `render.yaml` 기본값도 `songsim-public-mcp` 익명 read-only를 기준으로 둡니다.

## 4. 배포 후 확인

- API landing page: `https://.../`
- API docs: `https://.../docs`
- API liveness: `https://.../healthz`
- API readiness: `https://.../readyz`
- MCP endpoint: `https://.../mcp`

Render Blueprint health check는 `songsim-public-api`에서 `/healthz`를 사용합니다.
`/readyz`는 운영자 수동 확인용 cached readiness로 보고, public data freshness나 DB 연결 상태를 점검할 때 별도로 확인합니다.
steady-state polling이 있어도 DB 부하가 커지지 않도록 readiness snapshot은 프로세스 로컬 stale-while-revalidate cache를 사용합니다.
fresh TTL은 짧게 유지하고, 최근 정상 snapshot은 최대 10분까지 stale fallback으로 재사용합니다.
공개 배포 기준 readiness는 3단계 정책으로 해석합니다.

- `core`: `places`, `notices`, `academic_calendar`, 주요 guide/transport snapshot. 비어 있거나 unsynced면 `/readyz`가 실패합니다.
- `best_effort`: `campus_facilities`, `campus_dining_menus`. 비어 있어도 `/readyz`를 즉시 깨지는 않지만, 운영자가 sync 상태를 함께 봐야 합니다.
- `optional`: `courses`. 공개 제품에 유용하지만 학기 전환 전후 운영자가 대상 연도/학기를 명시하기 전까지는 readiness gate에 직접 묶지 않습니다.

## 5. 주의

- Render free web service는 cold start가 생길 수 있습니다.
- Supabase free project는 장기간 무활동 시 pause될 수 있습니다.
- 공개 배포는 read-only입니다. profile/admin 경로는 숨겨집니다.
- `public_readonly`에서는 automation loop가 실행되지 않습니다. Remote timeout은 `/healthz`, `/readyz`, 핵심 HTTP canary로 배포/DB/외부 source 문제를 분리해서 확인합니다.
- ChatGPT Actions는 HTTP API를 쓰므로 MCP OAuth와 무관합니다. MCP OAuth는 원할 때만 켜면 됩니다.
- `songsim-public-mcp`를 OAuth로 보호해도 `songsim-public-api`는 기본적으로 별도 OAuth env 없이 운영해도 됩니다. API 쪽에 같은 OAuth env를 넣는 경우는 landing status text를 MCP 보호 상태와 맞춰 보여 주고 싶을 때 정도입니다.
- `SONGSIM_OFFICIAL_COURSE_YEAR`, `SONGSIM_OFFICIAL_COURSE_SEMESTER`는 intentionally 비워 두고, 운영 시점의 대상 학기를 명시해서 넣는 편이 안전합니다.

## 6. Public Synthetic Smoke

registration guides 공개 이후에는 배포 직후 최소 smoke를 한 번 돌리는 편이 안전합니다.

- `/healthz`가 `200`과 `{"ok":true}`를 반환하는지 확인
- `/registration-guides?topic=payment_and_return&limit=3`가 `payment_and_return` topic과 `cuk_registration_guides` source tag를 반환하는지 확인
- `/courses?query=CSE301&year=2026&semester=1&limit=5`가 watchlist canary로서 `200`으로 안정 응답하는지 확인
- MCP에서 `tool_list_registration_guides`와 `songsim://registration-guide`가 모두 보이는지 확인

실행 절차와 예시 명령은 [public-synthetic-smoke.md](qa/public-synthetic-smoke.md)에 정리했습니다.
