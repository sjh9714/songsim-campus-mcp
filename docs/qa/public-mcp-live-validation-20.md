# Public MCP Live Validation 20

> Historical/superseded: measured results below are preserved as the 2026-03-15 KST run. Current release-gate docs are superseded by `public-mcp-release-pack-50.md`, `public-mcp-live-validation-50.md`, and the `student_activity_notices` canary addendum; do not rewrite the verdicts in this historical report when adding new public surface coverage.

배포된 공개 `read-only` surface를 2026-03-15 KST 기준으로 점검한 실측 검증 기록입니다.

## 실행 기준

- 대상
  - public API: `https://songsim-public-api.onrender.com`
  - public MCP: `https://songsim-public-mcp.onrender.com/mcp`
- 실제 호출 방식
  - 공개 MCP는 OAuth-protected tool call이 필요하므로, 이 문서의 실측 값은 같은 배포 데이터를 보는 public API raw endpoint로 실행했습니다.
  - `expected_mcp_flow`는 ChatGPT/Codex에서 이상적으로 밟아야 하는 prompt/resource/tool 경로를 기록합니다.
- 판정 레벨
  - `pass`: 핵심 사실과 표현이 실제값과 일치
  - `soft_pass`: 핵심 사실은 맞지만 naming, 정렬, 표현이 다소 어색
  - `soft_fail`: 큰 거짓은 아니지만 alias, 분류, 제약 해석이 실제 사용 기대에 못 미침
  - `fail`: 잘못된 사실, 잘못된 거절, 필수 제약 실패
- ground truth 기준
  - 장소: [가톨릭대 공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1)
  - 빈 강의실: 공식 실시간 source 부재 여부와 `estimated` fallback 표현, 시간표 기반 모순 여부
  - 공지: notice item의 공식 `source_url`
  - 식당: Kakao Maps public place listing by venue name
  - 교통: [가톨릭대 성심교정 오시는 길](https://www.catholic.ac.kr/ko/about/location_songsim.do)

## 판정 요약

| Verdict | Count |
| --- | ---: |
| pass | 10 |
| soft_pass | 3 |
| soft_fail | 2 |
| fail | 5 |

## 판정표

| ID | User utterance | Domain | Expected MCP flow | Verdict |
| --- | --- | --- | --- | --- |
| PL01 | 성심교정 중앙도서관 위치 알려줘 | place | `prompt_find_place -> tool_search_places -> tool_get_place` | pass |
| PL02 | 중도 어디야? | place | `prompt_find_place -> tool_search_places` | soft_fail |
| PL03 | 학생식당 있는 건물 뭐야? | place | `prompt_find_place -> tool_search_places -> tool_get_place` | pass |
| PL04 | 니콜스관 위치 알려줘 | place | `prompt_find_place -> tool_search_places -> tool_get_place` | pass |
| PL05 | 정문 어디야? | place | `prompt_find_place -> tool_search_places -> tool_get_place` | soft_pass |
| CR01 | 니콜스관인데 2026-03-16 오전 10시 15분 기준 비어 있는 강의실 있어? | classrooms | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | pass |
| CR02 | N관에서 2026-03-16 오후 1시 30분 기준 비어 있는 강의실 보여줘 | classrooms | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | pass |
| CR03 | 니콜스에서 지금 비어 있는 강의실 있어? | classrooms | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | fail |
| CR04 | 정문 기준 빈 강의실 보여줘 | classrooms | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | pass |
| CR05 | 김수환관도 같은 기준으로 빈 강의실 있어? | classrooms | `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms` | fail |
| NO01 | 최신 공지 3개 보여줘 | notices | `prompt_latest_notices -> tool_list_latest_notices` | soft_pass |
| NO02 | 최신 장학 공지 3개 보여줘 | notices | `prompt_latest_notices -> tool_list_latest_notices` | pass |
| NO03 | 취업 공지 보여줘 | notices | `prompt_latest_notices -> tool_list_latest_notices` | fail |
| NO04 | 직무 인턴 장학생 공지 보여줘 | notices | `prompt_latest_notices -> tool_list_latest_notices` | pass |
| RE01 | 중도 근처 밥집 추천해줘 | restaurants | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | fail |
| RE02 | 중앙도서관 근처 한식집 찾아줘 | restaurants | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | soft_pass |
| RE03 | 중앙도서관에서 10분 안쪽에 1만원 이하 식당 보여줘 | restaurants | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | soft_fail |
| RE04 | 학생식당 근처 지금 여는 카페 있어? | restaurants | `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants` | fail |
| TR01 | 성심교정 지하철 오는 길 알려줘 | transport | `prompt_transport_guide -> tool_list_transport_guides` | pass |
| TR02 | 성심교정 버스로 가는 법 알려줘 | transport | `prompt_transport_guide -> tool_list_transport_guides` | pass |

## 케이스 상세

### PL01
- `id`: `PL01`
- `user_utterance`: `성심교정 중앙도서관 위치 알려줘`
- `domain`: `place`
- `expected_mcp_flow`: `prompt_find_place -> tool_search_places -> tool_get_place`
- `deployed_response_summary`: `/places?query=중앙도서관` first hit = `central-library`, name `베리타스관`, aliases `베리타스관/중앙도서관/L관`, coordinates `37.486853, 126.799802`
- `ground_truth_source`: [공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1) `베리타스관(중앙도서관)`, `L관`
- `comparison_result`: 대표 건물명과 좌표가 공식값과 일치합니다.
- `verdict`: `pass`
- `notes`: 사용자 답변에서는 `베리타스관(중앙도서관, L관)`으로 풀어주면 가장 자연스럽습니다.

### PL02
- `id`: `PL02`
- `user_utterance`: `중도 어디야?`
- `domain`: `place`
- `expected_mcp_flow`: `prompt_find_place -> tool_search_places`
- `deployed_response_summary`: `/places?query=중도` -> `[]`
- `ground_truth_source`: [공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1)에는 `중도` 별칭이 직접 나오지 않음
- `comparison_result`: 공식값과 직접 모순되지는 않지만, 학생들이 실제로 쓰는 colloquial alias를 받지 못합니다.
- `verdict`: `soft_fail`
- `notes`: 제품 대표 질문 예시에 들어갈 정도의 alias라 live 배포에서도 받는 편이 좋습니다.

### PL03
- `id`: `PL03`
- `user_utterance`: `학생식당 있는 건물 뭐야?`
- `domain`: `place`
- `expected_mcp_flow`: `prompt_find_place -> tool_search_places -> tool_get_place`
- `deployed_response_summary`: `/places?query=학생식당` first hit = `sophie-barat-hall`, name `학생미래인재관`, description에 `교직원식당과 학생식당` 포함
- `ground_truth_source`: [공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1) `학생미래인재관(B관)` 설명
- `comparison_result`: 건물명과 식당 포함 설명이 공식값과 일치합니다.
- `verdict`: `pass`
- `notes`: `학생식당`은 place search에서는 잘 풀리지만 nearby restaurant origin alias로는 아직 실패합니다.

### PL04
- `id`: `PL04`
- `user_utterance`: `니콜스관 위치 알려줘`
- `domain`: `place`
- `expected_mcp_flow`: `prompt_find_place -> tool_search_places -> tool_get_place`
- `deployed_response_summary`: `/places?query=니콜스관` first hit = `nicholls-hall`, aliases `N관`, coordinates `37.48587, 126.802323`
- `ground_truth_source`: [공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1) `니콜스관(N관)`
- `comparison_result`: 건물명, 약칭, 좌표가 공식값과 일치합니다.
- `verdict`: `pass`
- `notes`: `니콜스관` 정식 명칭 경로는 안정적입니다.

### PL05
- `id`: `PL05`
- `user_utterance`: `정문 어디야?`
- `domain`: `place`
- `expected_mcp_flow`: `prompt_find_place -> tool_search_places -> tool_get_place`
- `deployed_response_summary`: `/places?query=정문` first hit = `main-gate`, second hit로 `창업보육센터`까지 같이 반환
- `ground_truth_source`: [공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1) `정문`
- `comparison_result`: 첫 결과는 정확하지만 짧은 질의에서 잡음 결과가 함께 섞입니다.
- `verdict`: `soft_pass`
- `notes`: 검색 상위 1건만 쓰는 MCP/GPT 응답이면 문제는 작지만, raw API 소비자는 노이즈를 볼 수 있습니다.

### CR01
- `id`: `CR01`
- `user_utterance`: `니콜스관인데 2026-03-16 오전 10시 15분 기준 비어 있는 강의실 있어?`
- `domain`: `classrooms`
- `expected_mcp_flow`: `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms`
- `deployed_response_summary`: `/classrooms/empty?building=니콜스관&at=2026-03-16T10:15:00+09:00` -> building `nicholls-hall`, `availability_mode=estimated`, note `공식 시간표 기준 예상 공실`, items `N308`, `N319`
- `ground_truth_source`: 공식 public realtime source 미확인. `estimated` fallback label과 시간표 기반 결과의 자기일관성을 기준으로 판정
- `comparison_result`: 실시간처럼 단정하지 않고 `estimated` fallback을 명시해 현재 정책과 일치합니다.
- `verdict`: `pass`
- `notes`: 실시간 소스가 추가되기 전까지는 이런 응답이 목표 동작입니다.

### CR02
- `id`: `CR02`
- `user_utterance`: `N관에서 2026-03-16 오후 1시 30분 기준 비어 있는 강의실 보여줘`
- `domain`: `classrooms`
- `expected_mcp_flow`: `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms`
- `deployed_response_summary`: `/classrooms/empty?building=N관&at=2026-03-16T13:30:00+09:00` -> `availability_mode=estimated`, items `N110`, `N208`, `N209`, `N210`, `N211`
- `ground_truth_source`: 공식 public realtime source 미확인. `estimated` fallback semantics 기준
- `comparison_result`: `N관` alias는 정상 해석되고, fallback note도 정확합니다.
- `verdict`: `pass`
- `notes`: `니콜스관`과 `N관`은 classroom lookup에서 같은 건물로 처리됩니다.

### CR03
- `id`: `CR03`
- `user_utterance`: `니콜스에서 지금 비어 있는 강의실 있어?`
- `domain`: `classrooms`
- `expected_mcp_flow`: `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms`
- `deployed_response_summary`: `/classrooms/empty?building=니콜스...` -> `{"detail":"Building not found: 니콜스"}`
- `ground_truth_source`: 제품 계획상 `니콜스관`, `니콜스`, `N관`은 같은 building alias로 수용하는 것이 목표
- `comparison_result`: 정식 명칭과 약칭은 되는데 대표 colloquial alias는 classroom resolver에 아직 안 붙었습니다.
- `verdict`: `fail`
- `notes`: nearby origin alias 보강과 달리 classroom building alias는 live 배포에서 덜 완성된 상태입니다.

### CR04
- `id`: `CR04`
- `user_utterance`: `정문 기준 빈 강의실 보여줘`
- `domain`: `classrooms`
- `expected_mcp_flow`: `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms`
- `deployed_response_summary`: `/classrooms/empty?building=정문...` -> `400`, `선택한 장소는 강의실 기반 건물이 아닙니다`
- `ground_truth_source`: [공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1) `정문`은 gate
- `comparison_result`: 강의실 기반 건물이 아닌 입력을 명확히 거절해 정책과 일치합니다.
- `verdict`: `pass`
- `notes`: 이 케이스는 거절이 정답입니다.

### CR05
- `id`: `CR05`
- `user_utterance`: `김수환관도 같은 기준으로 빈 강의실 있어?`
- `domain`: `classrooms`
- `expected_mcp_flow`: `prompt_find_empty_classrooms -> tool_list_estimated_empty_classrooms`
- `deployed_response_summary`: `/classrooms/empty?building=김수환관...` -> `400`, `선택한 장소는 강의실 기반 건물이 아닙니다`
- `ground_truth_source`: [공식 캠퍼스맵 JSON](https://www.catholic.ac.kr/ko/about/campus-map.do?mode=getPlaceListByCondition&campus=1) `김수환관(K관)` 설명에 `강의실과 연구실` 명시
- `comparison_result`: 공식 설명상 강의실이 있는 건물인데 live 분류는 비강의동으로 막고 있습니다.
- `verdict`: `fail`
- `notes`: place category 또는 room-to-building mapping 보정이 필요합니다.

### NO01
- `id`: `NO01`
- `user_utterance`: `최신 공지 3개 보여줘`
- `domain`: `notices`
- `expected_mcp_flow`: `prompt_latest_notices -> tool_list_latest_notices`
- `deployed_response_summary`: latest 3 = `[대외협력팀] 홍보 콘텐츠 제작 기관동아리 19기 합격자 발표`, `[학생지원팀] 2026학년도 1학기 <직무 인턴> 장학생 선발 안내`, `[커리어상담센터] 가대생 맞춤 '진로취업상담' 안내`
- `ground_truth_source`: 각 item의 공식 `source_url`
  - [269422](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269422&article.offset=0&articleLimit=10)
  - [269425](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269425&article.offset=0&articleLimit=10)
  - [269365](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269365&article.offset=0&articleLimit=10)
- `comparison_result`: 최신순 자체는 맞지만 첫 공지의 title이 공식 제목보다 짧고 category가 `place`로 내려와 표시 품질이 떨어집니다.
- `verdict`: `soft_pass`
- `notes`: retrieval은 맞지만 category normalization이 거칠어 후속 답변 품질이 흔들릴 수 있습니다.

### NO02
- `id`: `NO02`
- `user_utterance`: `최신 장학 공지 3개 보여줘`
- `domain`: `notices`
- `expected_mcp_flow`: `prompt_latest_notices -> tool_list_latest_notices`
- `deployed_response_summary`: scholarship latest 3 = `직무 인턴 장학생`, `YP 그랜드 피스투어 장학생`, `대구동구교육재단 장학생`
- `ground_truth_source`:
  - [269425](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269425&article.offset=0&articleLimit=10)
  - [269316](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269316&article.offset=0&articleLimit=10)
  - [269333](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269333&article.offset=0&articleLimit=10)
- `comparison_result`: title, date, scholarship grouping이 공식값과 잘 맞습니다.
- `verdict`: `pass`
- `notes`: notice category filtering 중 가장 안정적인 축입니다.

### NO03
- `id`: `NO03`
- `user_utterance`: `취업 공지 보여줘`
- `domain`: `notices`
- `expected_mcp_flow`: `prompt_latest_notices -> tool_list_latest_notices`
- `deployed_response_summary`: `/notices?category=employment&limit=3` -> `[]`
- `ground_truth_source`: [269365](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269365&article.offset=0&articleLimit=10) `[커리어상담센터] 가대생 맞춤 '진로취업상담' 안내`
- `comparison_result`: 취업/커리어 성격의 공지가 존재하는데 `employment` filter가 빈 결과를 돌려줍니다.
- `verdict`: `fail`
- `notes`: `career`와 `employment` taxonomy 정규화가 live 배포에서 아직 안 맞습니다.

### NO04
- `id`: `NO04`
- `user_utterance`: `직무 인턴 장학생 공지 보여줘`
- `domain`: `notices`
- `expected_mcp_flow`: `prompt_latest_notices -> tool_list_latest_notices`
- `deployed_response_summary`: scholarship latest first hit가 `[학생지원팀] 2026학년도 1학기 <직무 인턴> 장학생 선발 안내`
- `ground_truth_source`: [269425](https://www.catholic.ac.kr/ko/campuslife/notice.do?mode=view&articleNo=269425&article.offset=0&articleLimit=10)
- `comparison_result`: title과 date가 공식값과 일치하고, 장학 latest 조회 안에서 바로 찾을 수 있습니다.
- `verdict`: `pass`
- `notes`: keyword search endpoint는 없지만 latest+category 조합으로는 충분히 도달 가능합니다.

### RE01
- `id`: `RE01`
- `user_utterance`: `중도 근처 밥집 추천해줘`
- `domain`: `restaurants`
- `expected_mcp_flow`: `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants`
- `deployed_response_summary`: `/restaurants/nearby?origin=중도...` -> `{"detail":"Origin place not found: 중도"}`
- `ground_truth_source`: Kakao Maps public place listings near 가톨릭대/중앙도서관 area
- `comparison_result`: origin alias를 nearby tool에 직접 넣는 흐름이 live 배포에서는 아직 깨집니다.
- `verdict`: `fail`
- `notes`: place search alias와 restaurant origin alias coverage가 아직 분리돼 있습니다.

### RE02
- `id`: `RE02`
- `user_utterance`: `중앙도서관 근처 한식집 찾아줘`
- `domain`: `restaurants`
- `expected_mcp_flow`: `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants`
- `deployed_response_summary`: `/restaurants/nearby?origin=중앙도서관&category=korean&walk_minutes=10` -> `새우식탁`, `울엄마손칼국시`, `홍천식당`
- `ground_truth_source`: Kakao Maps public listing by venue name `새우식탁`, `울엄마손칼국시`, `홍천식당`
- `comparison_result`: venue existence와 한식 분류는 자연스럽지만, 정렬과 거리 근거를 외부에서 완전히 재현하긴 어렵습니다.
- `verdict`: `soft_pass`
- `notes`: category filter는 무난하지만 off-campus ranking은 Kakao index 변화에 영향을 받습니다.

### RE03
- `id`: `RE03`
- `user_utterance`: `중앙도서관에서 10분 안쪽에 1만원 이하 식당 보여줘`
- `domain`: `restaurants`
- `expected_mcp_flow`: `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants`
- `deployed_response_summary`: `/restaurants/nearby?origin=central-library&budget_max=10000&walk_minutes=10` -> `꼬밥`, `새우식탁`, `이디야커피 가톨릭대점`, 모든 item의 price fields는 `null`
- `ground_truth_source`: Kakao Maps public listing by venue name `꼬밥`, `새우식탁`, `이디야커피 가톨릭대점`
- `comparison_result`: 10분 제약은 plausible하지만, `budget_max` 근거가 payload에 없고 카페가 같이 섞여 예산 제약의 신뢰도가 낮습니다.
- `verdict`: `soft_fail`
- `notes`: 가격 데이터 coverage가 부족해 budget filter를 강하게 믿기 어렵습니다.

### RE04
- `id`: `RE04`
- `user_utterance`: `학생식당 근처 지금 여는 카페 있어?`
- `domain`: `restaurants`
- `expected_mcp_flow`: `prompt_find_nearby_restaurants -> tool_find_nearby_restaurants`
- `deployed_response_summary`: `/restaurants/nearby?origin=학생식당&category=cafe&open_now=true...` -> `{"detail":"Origin place not found: 학생식당"}`
- `ground_truth_source`: Kakao Maps public cafe listings near 학생미래인재관/가톨릭대 area
- `comparison_result`: place search에서는 통하는 표현인데 restaurant origin alias로는 실패합니다.
- `verdict`: `fail`
- `notes`: `학생식당 -> 학생미래인재관(B관)` alias bridge가 restaurant origin resolver에 아직 없습니다.

### TR01
- `id`: `TR01`
- `user_utterance`: `성심교정 지하철 오는 길 알려줘`
- `domain`: `transport`
- `expected_mcp_flow`: `prompt_transport_guide -> tool_list_transport_guides`
- `deployed_response_summary`: `1호선 역곡역 2번 출구`, `소사역 3번 출구`, `서해선 소사역 7번 출구`, `도보 10분`
- `ground_truth_source`: [가톨릭대 성심교정 오시는 길](https://www.catholic.ac.kr/ko/about/location_songsim.do)
- `comparison_result`: 역명, 출구, 도보 시간 요약이 공식 안내와 일치합니다.
- `verdict`: `pass`
- `notes`: 정적 guide surface로 충분히 신뢰 가능합니다.

### TR02
- `id`: `TR02`
- `user_utterance`: `성심교정 버스로 가는 법 알려줘`
- `domain`: `transport`
- `expected_mcp_flow`: `prompt_transport_guide -> tool_list_transport_guides`
- `deployed_response_summary`: `마을버스 51/51-1/51-2`, `시내버스 20/5/12/52`, 주요 하차 정류장 포함
- `ground_truth_source`: [가톨릭대 성심교정 오시는 길](https://www.catholic.ac.kr/ko/about/location_songsim.do)
- `comparison_result`: 버스 번호와 주요 하차 정류장이 공식 안내와 일치합니다.
- `verdict`: `pass`
- `notes`: bus guide도 현재는 큰 품질 이슈가 보이지 않습니다.
