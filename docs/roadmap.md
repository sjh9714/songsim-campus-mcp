# Roadmap

## Phase 1 - Searchable campus core
- [x] Place / Course / Restaurant / Notice 스키마 정의
- [x] PostgreSQL/PostGIS 저장소
- [x] HTTP API
- [x] MCP tools scaffold
- [x] 데모 데이터

## Phase 2 - Official data ingestion
- [x] 캠퍼스맵 파서
- [x] 개설과목조회 파서
- [x] 공지 파서
- [x] 도서관 운영시간 파서
- [x] 식당/편의시설 운영시간 파서
- [x] 성심교정 교통 안내 파서

## Phase 3 - Location intelligence
- [x] Kakao Local 연동
- [x] 실제 거리/도보 시간 계산
- [x] 캠퍼스 내부 경로망 기반 이동시간 보정
- [x] 카테고리/예산 필터
- [x] 영업 여부 필터

## Phase 4 - Personalization
- [x] 개인 시간표 import
- [x] 관심 공지 필터링
- [x] 식사/동선 추천
- [x] 학과/학년/관심사 기반 개인화
- [x] 공지 relevance 정렬 + 과목 대표 분반 추천

## Phase 5 - Production hardening
- [x] 식당 캐시 계층
- [x] 식당 영업시간 source 확보
- [x] 관측성
- [x] 관리자 동기화 대시보드
- [x] 앱 내부 운영 자동화
- [x] Postgres/PostGIS 이전
- [x] Public read-only remote MCP mode

## Phase 6 - Student entrance
- [x] 학생용 모바일 웹 (`web/`, Next.js)
- [x] 카드 홈 + 통합 검색
- [x] 잠든 백엔드를 흡수하는 프론트 캐시 계층
- [x] 무로그인 개인화 (마지막 건물 기억)
- [x] PWA manifest / 홈 화면 추가
- [x] 랜딩 페이지 학생용 배너 (`SONGSIM_STUDENT_WEB_URL`)
- [x] Vercel 배포 (https://songsim-web.vercel.app)
- [ ] 공유용 짧은 주소 + QR
- [ ] 학과 선택 기반 공지 필터

## Phase 7 - Keeping it alive
- [x] GitHub Actions 정기 동기화 (`.github/workflows/sync.yml`)
- [x] source 실패를 종료 코드로 노출 (`songsim-sync`)
- [x] 학생 화면 데이터 신선도 배지
- [ ] Supabase 최소 권한 역할로 동기화 접속정보 분리
