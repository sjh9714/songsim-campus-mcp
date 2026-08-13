/**
 * 빌드 전에 백엔드를 깨워 놓는다.
 *
 * 이 사이트는 화면 대부분을 빌드 때 미리 그려 둔다. 그런데 백엔드는 Render
 * 무료 플랜이라 15분이면 잠들고, 잠든 인스턴스를 깨우는 첫 요청은 실측 60~77초가
 * 걸린다. 그동안 fetch 는 제한시간에 걸려 실패하고, 빌드는 "성공" 하면서 내용이
 * 텅 빈 화면을 배포한다. 실제로 오늘 두 번 그렇게 나갔다.
 *
 * 그래서 첫 요청을 여기서 대신 맞는다. 여기서 기다린 시간만큼 학생은 안 기다린다.
 *
 * 끝내 응답이 없어도 빌드를 막지는 않는다. 배포 자체를 세우는 것보다는 낡은
 * 화면이라도 나가는 편이 낫고, 대신 로그에 크게 남긴다.
 */

const BASE = (process.env.SONGSIM_API_BASE ?? 'http://127.0.0.1:8000').replace(/\/+$/, '');
const DEADLINE_MS = 150_000;
const ATTEMPT_TIMEOUT_MS = 20_000;

const started = Date.now();
let attempt = 0;

while (Date.now() - started < DEADLINE_MS) {
  attempt += 1;
  try {
    const response = await fetch(`${BASE}/healthz`, {
      signal: AbortSignal.timeout(ATTEMPT_TIMEOUT_MS),
    });
    if (response.ok) {
      console.log(`[wait-for-api] ${BASE} 준비됨 (${attempt}번째, ${Date.now() - started}ms)`);
      process.exit(0);
    }
    console.log(`[wait-for-api] ${attempt}번째: HTTP ${response.status} — 깨어나는 중`);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    // 연결 자체가 거부되면 잠든 게 아니라 아무것도 없는 것이다. 로컬에서 백엔드
    // 없이 빌드할 때 2분 반을 붙잡고 있을 이유가 없다.
    if (attempt === 1 && /ECONNREFUSED|Connect Timeout|fetch failed/i.test(reason)) {
      console.warn(`[wait-for-api] ${BASE} 에 연결할 수 없습니다 (${reason}). 기다리지 않고 진행합니다.`);
      process.exit(0);
    }
    console.log(`[wait-for-api] ${attempt}번째: ${reason}`);
  }
}

console.warn(
  `[wait-for-api] ${BASE} 가 ${DEADLINE_MS / 1000}초 안에 응답하지 않았습니다.\n` +
    '[wait-for-api] 이대로 빌드하면 화면이 비어 있을 수 있습니다.',
);
process.exit(0);
