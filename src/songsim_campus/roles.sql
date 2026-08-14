-- 공개 서비스가 쓰는 데이터베이스 권한을 좁힌다.
--
-- 지금까지는 자격증명 하나가 쓰기 권한을 다 가진 채 네 군데에 퍼져 있었다.
-- GitHub Actions 시크릿, 그리고 인터넷에 열려 있는 Render 서비스 두 곳
-- (songsim-api-sg, songsim-mcp-sg). 저장소가 공개돼 있어서, 그 하나가 새면
-- 데이터베이스 전체를 쓸 수 있게 된다.
--
-- 그래서 역할을 하나 더 만든다.
--
--   기존 자격증명   동기화 전용으로 남긴다. GitHub Actions 만 쓴다
--   songsim_app     서비스 전용. 모든 테이블 읽기 + 캐시 테이블만 쓰기
--                   Render 의 API 와 MCP 가 쓴다
--
-- 동기화용 역할을 따로 만들지 않은 이유가 있다. repo 의 replace_* 34곳이
-- `TRUNCATE ... RESTART IDENTITY` 를 쓰는데, 이건 권한이 아니라 시퀀스
-- **소유권**을 요구한다. 새 역할에 주려면 44개 테이블과 그 시퀀스의 소유권을
-- 넘겨야 하고, Supabase 대시보드가 기대하는 소유자 구조를 흔든다.
-- 보안 이득은 "인터넷에 열린 서비스가 든 자격증명을 좁히는 것" 에서 나오지
-- 동기화 쪽을 쪼개는 데서 나오지 않는다. 그래서 거기까지 하지 않는다.
--
-- "읽기 전용" 이 아니라 "캐시만 쓰기" 인 이유도 있다. 공개 API 는 요청을
-- 처리하면서 캐시를 채운다. 도서관 좌석은 학교 서버를 실시간으로 찌른 결과를
-- 저장하고(services.get_library_seat_status), 주변 식당은 Kakao 응답을
-- 저장한다(restaurant_nearby_runtime). 순수 읽기 전용으로 묶으면 둘 다 죽는다.
--
-- 멱등하다. 여러 번 실행해도 같은 상태가 된다.
--
-- 적용 순서:
--   1) 아래 CREATE ROLE 주석을 풀고 비밀번호를 직접 정해 실행한다.
--      비밀번호는 이 파일에 적지 않는다.
--   2) 나머지를 실행한다.
--   3) Render 두 서비스의 SONGSIM_DATABASE_URL 을 songsim_app 으로 바꾼다.
--      GitHub Actions 시크릿은 기존 값 그대로 둔다.

-- --------------------------------------------------------------------------
-- 1. 역할 (비밀번호는 실행하는 사람이 채운다)
-- --------------------------------------------------------------------------
-- CREATE ROLE songsim_app LOGIN PASSWORD '...';

-- --------------------------------------------------------------------------
-- 2. 읽기 - 전체
-- --------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO songsim_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO songsim_app;

-- 앞으로 생길 테이블에도 적용한다. 없으면 스키마에 테이블이 하나 늘 때마다
-- 조용히 권한이 빠지고, 그 화면만 비어서 나간다.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO songsim_app;

-- --------------------------------------------------------------------------
-- 3. 쓰기 - 캐시 테이블만
-- --------------------------------------------------------------------------
-- library_seat_status_cache 는 TRUNCATE 로 갈아엎는다. Postgres 에서 TRUNCATE 는
-- INSERT/DELETE 와 별개 권한이라 따로 줘야 한다. 빠뜨리면 도서관 좌석이
-- 조용히 실패한다.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON
    library_seat_status_cache,
    restaurant_hours_cache,
    restaurant_cache_items,
    restaurant_cache_snapshots
TO songsim_app;

-- 위 테이블에 INSERT 할 때 nextval 을 부른다.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO songsim_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO songsim_app;

-- --------------------------------------------------------------------------
-- 4. Row Level Security
-- --------------------------------------------------------------------------
-- GRANT 만으로는 부족하다. Supabase 대시보드에서 public 스키마 44개 테이블에
-- RLS 가 켜져 있는데, 그 정책은 전부 PostgREST 용 역할(anon, authenticated)
-- 앞으로만 쓰여 있다. 이 설정은 레포의 schema.sql 에 없다. 대시보드에서
-- 켠 것이라 코드만 읽어서는 보이지 않는다.
--
-- 기존 자격증명이 이걸 못 느낀 이유는 postgres 역할이 rolbypassrls = t 이기
-- 때문이다. songsim_app 은 아니다. 그래서 정책 없이 붙이면 모든 테이블이
-- 0행으로 보이고, 질의는 성공한 채 빈 결과를 준다. 실제로 이 상태로 한 번
-- 배포했다가 /places 가 200 에 빈 배열, 건물 조회가 404, /library-seats 가
-- 500 이 됐다. 권한 오류가 아니라 "데이터가 없는 것처럼" 보이는 실패라
-- 종료 코드만 보면 통과한 것처럼 읽힌다.
--
-- 노출 범위는 늘리지 않는다. public_read 정책이 이미 anon 에게 열어 둔 것과
-- 같은 테이블만 songsim_app 이 읽는다. profiles 계열 4개는 뺀다. 개인 데이터고,
-- public_readonly 모드에서는 해당 엔드포인트가 아예 등록되지 않는다
-- (api.py 의 `if not public_readonly:`).
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND c.relrowsecurity
          AND c.relname NOT IN (
              'profiles',
              'profile_courses',
              'profile_interests',
              'profile_notice_preferences'
          )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS songsim_app_read ON public.%I', t);
        EXECUTE format(
            'CREATE POLICY songsim_app_read ON public.%I FOR SELECT TO songsim_app USING (true)',
            t
        );
    END LOOP;

    -- 캐시 테이블은 읽기만으로 부족하다. 3절에서 준 INSERT/UPDATE/DELETE 도
    -- RLS 아래에서는 정책이 있어야 통과한다. TRUNCATE 는 RLS 적용 대상이
    -- 아니라 3절의 GRANT 만으로 충분하다.
    FOREACH t IN ARRAY ARRAY[
        'library_seat_status_cache',
        'restaurant_hours_cache',
        'restaurant_cache_items',
        'restaurant_cache_snapshots'
    ]
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS songsim_app_write ON public.%I', t);
        EXECUTE format(
            'CREATE POLICY songsim_app_write ON public.%I FOR ALL TO songsim_app '
            'USING (true) WITH CHECK (true)',
            t
        );
    END LOOP;
END $$;

-- 앞으로 테이블이 늘고 거기에 RLS 를 켜면 이 파일을 다시 실행해야 한다.
-- ALTER DEFAULT PRIVILEGES 는 GRANT 만 물려주지 정책까지 만들어 주지 않는다.

-- --------------------------------------------------------------------------
-- 5. 확인
-- --------------------------------------------------------------------------
-- 종료 코드만 보면 안 된다. RLS 로 막히면 질의는 성공하고 행 수만 0이 된다.
-- 반드시 값을 본다.
--
--   SET ROLE songsim_app;
--   SELECT count(*) FROM places;                        -- 0 보다 커야 한다
--   INSERT INTO places (slug, name) VALUES ('x','x');   -- permission denied 여야 한다
--   TRUNCATE TABLE library_seat_status_cache;           -- 되어야 한다
--   RESET ROLE;
--
-- SET ROLE 은 postgres 로 붙었을 때만 된다. 실제 접속정보로 확인하려면
-- songsim_app 으로 직접 붙어야 한다.
