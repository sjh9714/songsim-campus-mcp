# Public Synthetic Smoke

공개 배포 직후 학생용 핵심 경로를 빠르게 확인하는 최소 runbook입니다.

## 목적

- Render health check가 가리키는 `/healthz`가 정상인지 확인
- `registration_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `class_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `seasonal_semester_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `phone_book_entries`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `campus_life_support_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `campus_life_notices`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `newsroom_posts`의 `photo_news`와 `press`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `pc_software_entries`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `dormitory_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `affiliated_notices`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `student_exchange_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `student_exchange_partners`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `about_resource_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `service_policy_guides`가 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- `notices`의 `academic` 최신 3건이 공개 HTTP와 MCP 양쪽에서 보이는지 확인
- nearby restaurants의 대표 alias origin과 strict `open_now` 경로가 공개 HTTP/MCP에서 유지되는지 확인
- 대표 `courses` watchlist query가 500/timeout 없이 처리되는지 확인
- 공개 MCP의 registration resource/tool contract가 깨지지 않았는지 확인

## 준비

아래 값을 실제 공개 배포 URL로 치환합니다.

```bash
export PUBLIC_HTTP_URL="https://your-public-api.onrender.com"
export PUBLIC_MCP_URL="https://your-public-mcp.onrender.com/mcp"
```

`jq`가 있으면 확인이 편하지만 필수는 아닙니다.

## 1. HTTP liveness

```bash
curl -fsS "$PUBLIC_HTTP_URL/healthz"
```

기대값:

- HTTP `200`
- body는 `{"ok":true}` 또는 공백 없는 동등 JSON

## 2. Registration guides HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/registration-guides?topic=payment_and_return&limit=3"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"payment_and_return"`
- `"source_tag":"cuk_registration_guides"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/registration-guides?topic=payment_and_return&limit=3" \
  | jq '.[0] | {topic, title, source_tag}'
```

## 3. Representative courses watchlist query

recovery canary는 `데이타베이스`처럼 오타/표기 변형을 near match로 복구해야 하는 케이스를 기준으로 둡니다. watchlist canary는 현재 [public_api_eval_watchlist.jsonl](../../data/qa/public_api_eval_watchlist.jsonl)의 `CW02`, `CW05`를 기준으로 둡니다.

```bash
curl -fsS "$PUBLIC_HTTP_URL/courses?query=%EB%8D%B0%EC%9D%B4%ED%83%80%EB%B2%A0%EC%9D%B4%EC%8A%A4&year=2026&semester=1&limit=5"
curl -fsS "$PUBLIC_HTTP_URL/courses?query=CSE%20420&year=2026&semester=1&limit=5"
curl -fsS "$PUBLIC_HTTP_URL/courses?query=CSE-420&year=2026&semester=1&limit=5"
curl -fsS "$PUBLIC_HTTP_URL/courses?query=CSE301&year=2026&semester=1&limit=5"
```

기대값:

- HTTP `200`
- JSON array
- `데이타베이스`는 near match 결과를 안정적으로 반환해야 함
- `CSE 420`, `CSE-420`은 `CSE420` query group과 같은 결과군으로 정렬되되, source-backed hit가 없으면 계속 빈 결과여도 됨
- `CSE301`은 비어 있어도 괜찮음
- 중요한 것은 `500`, HTML error page, timeout 없이 응답하는 것

이 쿼리는 학생-facing smoke라기보다 source-gap watchlist canary입니다. 결과 유무보다 응답 안정성을 봅니다.

## 4. Class guides HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/class-guides?topic=course_evaluation&limit=3"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"course_evaluation"`
- `"source_tag":"cuk_class_guides"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/class-guides?topic=course_evaluation&limit=3" \
  | jq '.[0] | {topic, title, source_tag}'
```

## 5. Academic notices HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/notices?category=academic&limit=3"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"category":"academic"`
- `"source_tag":"cuk_campus_notices"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/notices?category=academic&limit=3" \
  | jq '.[0] | {title, category, source_tag}'
```

## 5.5 Affiliated notices HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/affiliated-notices?topic=international_studies&limit=3"
curl -fsS "$PUBLIC_HTTP_URL/affiliated-notices?topic=dorm_k_a_checkin_out&query=입퇴사&limit=3"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"international_studies"` 또는 `"topic":"dorm_k_a_checkin_out"`
- `"source_tag":"cuk_affiliated_notice_boards"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/affiliated-notices?topic=international_studies&limit=3" \
  | jq '.[0] | {topic, title, published_at, source_tag}'
```

### 5.5.1 Unique latest international_studies notices

```bash
curl -fsS "$PUBLIC_HTTP_URL/affiliated-notices?topic=international_studies&limit=5"
```

기대값:

- HTTP `200`
- JSON array
- 최신 `international_studies` 결과의 `title` 값이 중복되지 않아야 한다
- `"source_tag":"cuk_affiliated_notice_boards"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/affiliated-notices?topic=international_studies&limit=5" \
  | jq 'map(.title) as $titles | ($titles | length) == ($titles | unique | length)'
```

## 5.6 Campus life notices HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/campus-life-notices?query=%EC%99%B8%EB%B6%80%EA%B8%B0%EA%B4%80%EA%B3%B5%EC%A7%80&limit=3"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-notices?topic=events&limit=3"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"outside_agencies"`
- `topic=events` 요청에서는 `"topic":"events"`가 보임
- `"source_tag":"cuk_campus_life_notices"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/campus-life-notices?query=%EC%99%B8%EB%B6%80%EA%B8%B0%EA%B4%80%EA%B3%B5%EC%A7%80&limit=3" \
  | jq '.[0] | {topic, title, published_at, source_tag}'
```

## 5.7 Newsroom posts HTTP smoke

CUK홍보 뉴스룸은 학교 공식 뉴스룸의 포토뉴스와 보도자료만 다룹니다. 보도자료가 외부 언론 보도 링크를 포함하더라도 외부 매체 본문은 스크랩하지 않습니다. Instagram 등 SNS/social 게시글은 여전히 out of scope/watch입니다.

surface names:

- `GET /newsroom-posts`
- `songsim://newsroom-posts`
- `tool_list_newsroom_posts`

topics:

- `photo_news`
- `press`

```bash
curl -fsS "$PUBLIC_HTTP_URL/newsroom-posts?topic=photo_news&limit=3"
curl -fsS "$PUBLIC_HTTP_URL/newsroom-posts?topic=press&limit=3"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"photo_news"` 또는 `"topic":"press"`가 보임
- `"source_tag":"cuk_newsroom_posts"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/newsroom-posts?topic=photo_news&limit=3" \
  | jq '.[0] | {topic, title, published_at, source_tag}'
```

## 6. Seasonal semester guides HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/seasonal-semester-guides?topic=seasonal_semester&limit=2"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"seasonal_semester"`
- `"source_tag":"cuk_seasonal_semester_guides"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/seasonal-semester-guides?topic=seasonal_semester&limit=2" \
  | jq '.[0] | {topic, title, source_tag}'
```

## 7. Phone book HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/phone-book?query=%EB%B3%B4%EA%B1%B4%EC%8B%A4&limit=1"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 안에 `"department":"보건실"`
- `"source_tag":"cuk_phone_book"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/phone-book?query=%EB%B3%B4%EA%B1%B4%EC%8B%A4&limit=1" \
  | jq '.[0] | {department, phone, source_tag}'
```

## 8. Nearby restaurants HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/restaurants/nearby?origin=%EC%A4%91%EB%8F%84&limit=3"
curl -fsS "$PUBLIC_HTTP_URL/restaurants/nearby?origin=%ED%95%99%EC%83%9D%EC%8B%9D%EB%8B%B9&open_now=true&category=cafe&limit=3"
```

기대값:

- 두 요청 모두 HTTP `200`
- `origin=중도` 응답은 빈 배열이 아니고, 상위 결과들의 `"origin"`이 `"central-library"`로 정규화됨
- `origin=학생식당&open_now=true&category=cafe` 응답은 현재 contract상 빈 배열이어도 괜찮음
- 중요한 회귀 기준은 `open_now=true` 응답에 `open_now=null` item이 섞이지 않는 것

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/restaurants/nearby?origin=%EC%A4%91%EB%8F%84&limit=3" \
  | jq '.[0] | {name, origin, estimated_walk_minutes, source_tag}'
```

## 9. Campus-life support guides HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=health_center&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=parking&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=facility_rental&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=mobility_safety&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=student_counseling&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=student_reservist&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=hospital_use&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/campus-life-support-guides?topic=career_counseling&limit=2"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"health_center"`, `"topic":"parking"`, `"topic":"facility_rental"`, `"topic":"mobility_safety"`, 또는 `"topic":"career_counseling"`
- `"source_tag":"cuk_campus_life_support_guides"`가 보임

## 10. PC software HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/pc-software?query=SPSS&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/pc-software?query=Photoshop&limit=2"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"room"`과 `"software_list"`가 보임
- `"source_tag":"cuk_pc_software"`가 보임

## 11. Student exchange guides HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/student-exchange-guides?topic=exchange_student&limit=2"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"topic":"exchange_student"` 또는 `"topic":"domestic_partner_universities"`
- `"source_tag":"cuk_student_exchange_guides"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/student-exchange-guides?topic=exchange_student&limit=2" \
  | jq '.[0] | {topic, title, source_tag}'
```

## 12. Student exchange partners HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/student-exchange-partners?query=%EB%84%A4%EB%8D%9C%EB%9E%80%EB%93%9C&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/student-exchange-partners?query=University&limit=2"
```

기대값:

- HTTP `200`
- JSON array
- 첫 결과 또는 상위 결과 안에 `"university_name":"Utrecht University"` 또는 `"country_ko":"네덜란드"`
- `"source_tag":"cuk_student_exchange_partners"`가 보임

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/student-exchange-partners?query=%EB%84%A4%EB%8D%9C%EB%9E%80%EB%93%9C&limit=2" \
  | jq '.[0] | {partner_code, university_name, country_ko, continent, source_tag}'
```

## 13. Dormitory guides HTTP smoke

```bash
curl -fsS "$PUBLIC_HTTP_URL/dormitory-guides?topic=hall_info&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/dormitory-guides?topic=fees&limit=2"
curl -fsS "$PUBLIC_HTTP_URL/dormitory-guides?topic=latest_notices&limit=2"
```

기대값:

- HTTP `200`
- JSON array
- `topic=hall_info` 결과는 `스테파노관` 또는 `안드레아관` 같은 기숙사 동을 포함
- `topic=fees` 결과는 기숙사비 또는 환불 기준 안내를 포함
- `topic=latest_notices` 결과는 홈 최신 공지 카드를 반환
- `"source_tag":"cuk_dormitory_guides"`가 보임

## 14. Student activity guide family smoke

학생활동 정적 페이지 family는 현재 공개 HTTP/MCP surface에서 바로 읽을 수 있습니다.

- `총학생회 안내해줘`
- `중앙동아리 뭐 있어?`
- `기관동아리 CUK프렌즈 알려줘`
- `교내미디어 뭐 있어?`
- `사회봉사 활동 알려줘`
- `학생군사교육단 안내해줘`

surface names:

- `GET /student-activity-guides`
- `songsim://student-activity-guide`
- `tool_list_student_activity_guides`

topics:

- `student_government`
- `central_clubs`
- `institutional_clubs`
- `campus_media`
- `social_volunteering`
- `rotc`

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/student-activity-guides?topic=campus_media&limit=2" \
  | jq '.[0] | {topic, title, source_tag}'
```

기대값:

- HTTP `200`
- JSON array
- `topic=student_government` 결과는 `조직구성`, `총학생회`, `총동아리연합회` 중 하나를 포함
- `topic=central_clubs` 결과는 `중앙동아리 분과 안내` 또는 개별 중앙동아리를 포함
- `topic=institutional_clubs` 결과는 `CUK프렌즈`, `가홍이`, `날아가대`, `가대사랑`, `COz`, `스타티스트` 중 하나를 포함
- `topic=campus_media` 결과는 `가톨릭대학보` 또는 `영자신문사(The CUK Forum)`를 포함
- `"source_tag":"cuk_student_activity_guides"`가 보임

## 14.5 About resource guide family smoke

가대소개 주요 정적 자료는 v1에서 원문 해석이 아니라 공식 링크, 제목, 짧은 요약, 접근 안내를 제공합니다.

- `학교 규정 어디서 봐?`
- `요람 링크 알려줘`
- `학사제도안내책자 보여줘`
- `캠퍼스투어 신청 어디서 해?`

surface names:

- `GET /about-resource-guides`
- `songsim://about-resource-guide`
- `tool_list_about_resource_guides`

topics:

- `rules`
- `university_bulletin`
- `academic_handbook`
- `campus_tour`
- `history`
- `church_literature`
- `budget_account`

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/about-resource-guides?topic=rules&limit=2" \
  | jq '.[0] | {topic, title, source_tag}'
```

기대값:

- HTTP `200`
- JSON array
- `topic=rules` 결과는 `규정`과 공식 규정정보시스템 링크를 포함
- `topic=university_bulletin` 결과는 `요람` 관련 공식 링크를 포함
- `topic=academic_handbook` 결과는 `학사제도안내책자` 관련 공식 링크를 포함
- `topic=campus_tour` 결과는 `캠퍼스투어`와 신청 링크를 포함
- `topic=history` 결과는 `연혁` 관련 안내를 포함
- `topic=church_literature` 결과는 `교회문헌` 관련 공식 링크를 포함
- `topic=budget_account` 결과는 `예결산공고` 관련 공식 링크를 포함
- `"source_tag":"cuk_about_resource_guides"`가 보임

## 14.6 Service policy guide family smoke

서비스/정책 자료는 v1에서 원문 해석이 아니라 공식 링크, 제목, 짧은 요약, 접근 안내를 제공합니다.

- `개인정보처리방침 어디서 봐?`
- `채용공고 알려줘`
- `입찰공고 어디서 확인해?`
- `청탁금지법 문의 어디야?`

surface names:

- `GET /service-policy-guides`
- `songsim://service-policy-guide`
- `tool_list_service_policy_guides`

topics:

- `bidding`
- `job_posting`
- `privacy_policy`
- `cctv_policy`
- `anti_graft`

`jq` 예시:

```bash
curl -fsS "$PUBLIC_HTTP_URL/service-policy-guides?topic=privacy_policy&limit=2" \
  | jq '.[0] | {topic, title, source_tag}'
```

기대값:

- HTTP `200`
- JSON array
- `topic=privacy_policy` 결과는 `개인정보처리방침`과 공식 링크를 포함
- `topic=cctv_policy` 결과는 영상정보처리기기 방침 공식 링크를 포함
- `topic=anti_graft` 결과는 청탁금지법 주요내용/문의처 링크를 포함
- `"source_tag":"cuk_service_policy_guides"`가 보임

## 15. MCP initialize + guide checks

아래 Python smoke는 live에서 검증한 payload 형태를 그대로 사용합니다.

```bash
./.venv/bin/python - <<'PY'
import httpx
from mcp.types import LATEST_PROTOCOL_VERSION

base = "https://songsim-public-mcp.onrender.com/mcp"
headers = {"accept": "application/json", "content-type": "application/json"}

with httpx.Client(timeout=20.0) as client:
    initialize = client.post(
        base,
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "synthetic-smoke", "version": "1.0"},
            },
        },
    )
    print("initialize", initialize.status_code)
    session_id = initialize.headers["mcp-session-id"]

    call_headers = {
        **headers,
        "mcp-session-id": session_id,
        "mcp-protocol-version": LATEST_PROTOCOL_VERSION,
    }

    tool_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "tool_list_registration_guides",
                "arguments": {"topic": "payment_and_return", "limit": 2},
            },
        },
    )
    print("tool_list_registration_guides", tool_call.status_code)

    class_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "tool_list_class_guides",
                "arguments": {"topic": "course_evaluation", "limit": 2},
            },
        },
    )
    print("tool_list_class_guides", class_call.status_code)

    seasonal_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {
                "name": "tool_list_seasonal_semester_guides",
                "arguments": {"topic": "seasonal_semester", "limit": 2},
            },
        },
    )
    print("tool_list_seasonal_semester_guides", seasonal_call.status_code)

    milestone_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {
                "name": "tool_list_academic_milestone_guides",
                "arguments": {"topic": "grade_evaluation", "limit": 2},
            },
        },
    )
    print("tool_list_academic_milestone_guides", milestone_call.status_code)

    phone_book_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 24,
            "method": "tools/call",
            "params": {
                "name": "tool_search_phone_book",
                "arguments": {"query": "보건실", "limit": 1},
            },
        },
    )
    print("tool_search_phone_book", phone_book_call.status_code)

    notices_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "tool_list_latest_notices",
                "arguments": {"category": "academic", "limit": 3},
            },
        },
    )
    print("tool_list_latest_notices", notices_call.status_code)

    affiliated_notices_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": "tool_list_affiliated_notices",
                "arguments": {"topic": "international_studies", "limit": 3},
            },
        },
    )
    print("tool_list_affiliated_notices", affiliated_notices_call.status_code)

    newsroom_posts_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": "tool_list_newsroom_posts",
                "arguments": {"topic": "photo_news", "limit": 3},
            },
        },
    )
    print("tool_list_newsroom_posts", newsroom_posts_call.status_code)

    nearby_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "tool_find_nearby_restaurants",
                "arguments": {"origin": "중도", "limit": 3},
            },
        },
    )
    print("tool_find_nearby_restaurants", nearby_call.status_code)

    resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "songsim://registration-guide"},
        },
    )
    print("registration resource", resource_read.status_code)

    class_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "resources/read",
            "params": {"uri": "songsim://class-guide"},
        },
    )
    print("class resource", class_resource_read.status_code)

    seasonal_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "resources/read",
            "params": {"uri": "songsim://seasonal-semester-guide"},
        },
    )
    print("seasonal semester resource", seasonal_resource_read.status_code)

    milestone_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "resources/read",
            "params": {"uri": "songsim://academic-milestone-guide"},
        },
    )
    print("academic milestone resource", milestone_resource_read.status_code)

    phone_book_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "resources/read",
            "params": {"uri": "songsim://phone-book"},
        },
    )
    print("phone book resource", phone_book_resource_read.status_code)

    campus_life_support_tool_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 30,
            "method": "tools/call",
            "params": {
                "name": "tool_list_campus_life_support_guides",
                "arguments": {"topic": "facility_rental", "limit": 2},
            },
        },
    )
    print(
        "tool_list_campus_life_support_guides",
        campus_life_support_tool_call.status_code,
    )

    campus_life_support_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 31,
            "method": "resources/read",
            "params": {"uri": "songsim://campus-life-support-guide"},
        },
    )
    print(
        "campus life support resource",
        campus_life_support_resource_read.status_code,
    )

    pc_software_tool_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {
                "name": "tool_search_pc_software",
                "arguments": {"query": "SPSS", "limit": 2},
            },
        },
    )
    print("tool_search_pc_software", pc_software_tool_call.status_code)

    pc_software_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 33,
            "method": "resources/read",
            "params": {"uri": "songsim://pc-software"},
        },
    )
    print("pc software resource", pc_software_resource_read.status_code)

    student_exchange_tool_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 34,
            "method": "tools/call",
            "params": {
                "name": "tool_list_student_exchange_guides",
                "arguments": {"topic": "exchange_student", "limit": 2},
            },
        },
    )
    print("tool_list_student_exchange_guides", student_exchange_tool_call.status_code)

    student_exchange_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 35,
            "method": "resources/read",
            "params": {"uri": "songsim://student-exchange-guide"},
        },
    )
    print("student exchange resource", student_exchange_resource_read.status_code)

    student_exchange_partners_tool_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 36,
            "method": "tools/call",
            "params": {
                "name": "tool_search_student_exchange_partners",
                "arguments": {"query": "네덜란드", "limit": 2},
            },
        },
    )
    print(
        "tool_search_student_exchange_partners",
        student_exchange_partners_tool_call.status_code,
    )

    student_exchange_partners_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 37,
            "method": "resources/read",
            "params": {"uri": "songsim://student-exchange-partners"},
        },
    )
    print(
        "student exchange partners resource",
        student_exchange_partners_resource_read.status_code,
    )

    affiliated_notices_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 38,
            "method": "resources/read",
            "params": {"uri": "songsim://affiliated-notices"},
        },
    )
    print("affiliated notices resource", affiliated_notices_resource_read.status_code)

    newsroom_posts_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 42,
            "method": "resources/read",
            "params": {"uri": "songsim://newsroom-posts"},
        },
    )
    print("newsroom posts resource", newsroom_posts_resource_read.status_code)

    dormitory_tool_call = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {
                "name": "tool_list_dormitory_guides",
                "arguments": {"topic": "latest_notices", "limit": 2},
            },
        },
    )
    print("tool_list_dormitory_guides", dormitory_tool_call.status_code)

    dormitory_resource_read = client.post(
        base,
        headers=call_headers,
        json={
            "jsonrpc": "2.0",
            "id": 44,
            "method": "resources/read",
            "params": {"uri": "songsim://dormitory-guide"},
        },
    )
    print("dormitory resource", dormitory_resource_read.status_code)
PY
```

기대값:

- `initialize 200`
- `tool_list_registration_guides 200`
- `tool_list_class_guides 200`
- `tool_list_seasonal_semester_guides 200`
- `tool_list_academic_milestone_guides 200`
- `tool_list_campus_life_support_guides 200`
- `tool_search_pc_software 200`
- `tool_list_student_exchange_guides 200`
- `tool_search_student_exchange_partners 200`
- `tool_list_service_policy_guides 200`
- `tool_search_phone_book 200`
- `tool_list_campus_life_notices 200`
- `tool_list_newsroom_posts 200`
- `tool_list_affiliated_notices 200`
- `tool_list_latest_notices 200`
- `tool_find_nearby_restaurants 200`
- `registration resource 200`
- `class resource 200`
- `seasonal semester resource 200`
- `academic milestone resource 200`
- `campus life support resource 200`
- `pc software resource 200`
- `student exchange resource 200`
- `student exchange partners resource 200`
- `service policy resource 200`
- `phone book resource 200`
- `campus life notices resource 200`
- `newsroom posts resource 200`
- `affiliated notices resource 200`
- `tool_list_dormitory_guides 200`
- `dormitory resource 200`
- `initialize` 응답의 `instructions`에 `registration` 문구가 포함됨
- `tool_list_registration_guides` payload가 빈 결과가 아님
- `tool_list_class_guides` payload가 빈 결과가 아니고 `course_evaluation` 항목을 포함함
- `tool_list_seasonal_semester_guides` payload가 빈 결과가 아니고 `seasonal_semester` 항목을 포함함
- `tool_list_academic_milestone_guides` payload가 빈 결과가 아니고 `grade_evaluation` 항목을 포함함
- `tool_list_campus_life_support_guides` payload가 빈 결과가 아니고 `health_center`, `parking`, `facility_rental`, `mobility_safety`, `student_counseling`, `student_reservist`, `hospital_use`, 또는 `career_counseling` 항목을 포함함
- `tool_search_pc_software` payload가 빈 결과가 아니고 `SPSS` 또는 `Photoshop` 항목을 포함함
- `tool_list_student_exchange_guides` payload가 빈 결과가 아니고 `exchange_student` 또는 `domestic_partner_universities` 항목을 포함함
- `tool_search_student_exchange_partners` payload가 빈 결과가 아니고 `네덜란드` 또는 `Utrecht University` 항목을 포함함
- `tool_list_service_policy_guides` payload가 빈 결과가 아니고 `privacy_policy`, `cctv_policy`, 또는 `anti_graft` 항목을 포함함
- `tool_search_phone_book` payload가 빈 결과가 아니고 `보건실` 항목을 포함함
- `tool_list_campus_life_notices` payload가 빈 결과가 아니고 `outside_agencies` 또는 `events` 항목을 포함함
- `tool_list_newsroom_posts` payload가 빈 결과가 아니고 `photo_news` 또는 `press` 항목을 포함함
- `tool_list_affiliated_notices` payload가 빈 결과가 아니고 `international_studies` 또는 dorm topic 항목을 포함함
- `tool_list_dormitory_guides` payload가 빈 결과가 아니고 `latest_notices`, `hall_info`, 또는 `fees` 항목을 포함함
- `tool_list_latest_notices` payload가 빈 결과가 아니고 academic 항목을 포함함
- `tool_find_nearby_restaurants` payload가 빈 결과가 아니고 nearby 식당 요약 payload를 반환함
- `resources/read` 결과의 첫 항목에 `source_tag=cuk_registration_guides`가 포함됨
- `class` resource 결과의 첫 항목에 `source_tag=cuk_class_guides`가 포함됨
- `seasonal semester` resource 결과의 첫 항목에 `source_tag=cuk_seasonal_semester_guides`가 포함됨
- `academic milestone` resource 결과의 첫 항목에 `source_tag=cuk_academic_milestone_guides`가 포함됨
- `campus life support` resource 결과의 첫 항목에 `source_tag=cuk_campus_life_support_guides`가 포함됨
- `pc software` resource 결과의 첫 항목에 `source_tag=cuk_pc_software`가 포함됨
- `student exchange` resource 결과의 첫 항목에 `source_tag=cuk_student_exchange_guides`가 포함됨
- `student exchange partners` resource 결과의 첫 항목에 `source_tag=cuk_student_exchange_partners`가 포함됨
- `phone book` resource 결과의 첫 항목에 `source_tag=cuk_phone_book`가 포함됨
- `campus life notices` resource 결과의 첫 항목에 `source_tag=cuk_campus_life_notices`가 포함됨
- `newsroom posts` resource 결과의 첫 항목에 `source_tag=cuk_newsroom_posts`가 포함됨
- `affiliated notices` resource 결과의 첫 항목에 `source_tag=cuk_affiliated_notice_boards`가 포함됨
- `dormitory resource` 결과의 첫 항목에 `source_tag=cuk_dormitory_guides`가 포함됨

## Pass 기준

- `/healthz`가 `200`과 `{"ok":true}`를 반환
- `/registration-guides`가 `payment_and_return` topic과 `cuk_registration_guides` source tag를 반환
- `/class-guides`가 `course_evaluation` topic과 `cuk_class_guides` source tag를 반환
- `/seasonal-semester-guides`가 `seasonal_semester` topic과 `cuk_seasonal_semester_guides` source tag를 반환
- `/academic-milestone-guides`가 `grade_evaluation` topic과 `cuk_academic_milestone_guides` source tag를 반환
- `/campus-life-support-guides`가 `health_center`, `parking`, `facility_rental`, `mobility_safety`, `student_counseling`, `student_reservist`, `hospital_use`, 또는 `career_counseling` topic과 `cuk_campus_life_support_guides` source tag를 반환
- `/pc-software`가 `SPSS` 또는 `Photoshop` query에 대해 `cuk_pc_software` source tag를 반환
- `/student-exchange-guides`가 `exchange_student` 또는 `domestic_partner_universities` topic과 `cuk_student_exchange_guides` source tag를 반환
- `/student-exchange-partners`가 `네덜란드` 같은 query에 대해 `country_ko`, `university_name`, `homepage_url`, `cuk_student_exchange_partners`를 반환
- `/about-resource-guides`가 `rules`, `university_bulletin`, `academic_handbook`, `campus_tour`, `history`, `church_literature`, 또는 `budget_account` topic과 `cuk_about_resource_guides` source tag를 반환
- `/service-policy-guides`가 `bidding`, `job_posting`, `privacy_policy`, `cctv_policy`, 또는 `anti_graft` topic과 `cuk_service_policy_guides` source tag를 반환
- `/phone-book`가 `보건실` 또는 질의한 부서의 `cuk_phone_book` source tag를 반환
- `/affiliated-notices`가 `international_studies` 또는 질의한 dorm/topic의 `cuk_affiliated_notice_boards` source tag를 반환
- `/newsroom-posts`가 `photo_news` 또는 `press` topic과 `cuk_newsroom_posts` source tag를 반환
- `/notices?category=academic&limit=3`가 `academic` notice와 `cuk_campus_notices` source tag를 반환
- `/restaurants/nearby?origin=중도`가 `central-library` origin으로 nearby 결과를 반환
- `/restaurants/nearby?origin=학생식당&open_now=true&category=cafe&limit=3`가 `200`으로 안정 응답하고, 빈 배열이어도 `open_now` strict contract와 일치
- `/courses?query=CSE301...`가 빈 배열이어도 좋으니 `200`으로 안정 응답
- MCP initialize가 성공하고 `tool_list_registration_guides`, `tool_list_class_guides`, `tool_list_seasonal_semester_guides`, `tool_list_academic_milestone_guides`, `tool_list_campus_life_support_guides`, `tool_list_campus_life_notices`, `tool_list_newsroom_posts`, `tool_search_pc_software`, `tool_list_student_exchange_guides`, `tool_search_student_exchange_partners`, `tool_list_about_resource_guides`, `tool_list_service_policy_guides`, `tool_search_phone_book`, `tool_list_affiliated_notices`, `tool_list_dormitory_guides`, `tool_list_latest_notices`, `tool_find_nearby_restaurants`, `songsim://registration-guide`, `songsim://class-guide`, `songsim://seasonal-semester-guide`, `songsim://academic-milestone-guide`, `songsim://campus-life-support-guide`, `songsim://campus-life-notices`, `songsim://newsroom-posts`, `songsim://pc-software`, `songsim://student-exchange-guide`, `songsim://student-exchange-partners`, `songsim://about-resource-guide`, `songsim://service-policy-guide`, `songsim://phone-book`, `songsim://affiliated-notices`, `songsim://dormitory-guide`가 모두 노출
- MCP registration/exchange-partner/affiliated/nearby tool call이 에러 없이 응답

이 기준이 통과하면 class-guides + registration-guides + seasonal-semester-guides + academic-milestone-guides + 생활지원 core guides + campus life notices + newsroom posts + PC software + student-exchange + exchange partner search + about/service policy resources + phone-book + affiliated notices + dormitory + nearby restaurant 공개 smoke는 충분합니다.
