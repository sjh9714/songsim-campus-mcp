import { formatAgo } from '@/lib/format';

/**
 * 데이터 자체가 언제 갱신됐는지 보여준다.
 *
 * StaleBadge 와 역할이 다르다.
 *  - StaleBadge:     지금 백엔드 응답을 못 받아 직전 값을 대신 보여주는 중
 *  - FreshnessBadge: 응답은 정상인데 그 데이터가 오래된 것
 *
 * 정기 동기화(.github/workflows/sync.yml)가 조용히 멈추면 백엔드는 멀쩡히
 * 200 을 주고 화면도 정상으로 보인다. 학식이 지난주 메뉴인 걸 학생이 알 방법이
 * 없다. 그래서 임계치를 넘으면 눈에 띄게 바꾼다.
 */
export default function FreshnessBadge({
  syncedAt,
  maxAgeHours,
}: {
  syncedAt: string | null | undefined;
  /** 이 시간을 넘으면 경고로 표시한다. */
  maxAgeHours: number;
}) {
  if (!syncedAt) return null;

  const synced = new Date(syncedAt);
  if (Number.isNaN(synced.getTime())) return null;

  const ago = formatAgo(syncedAt);
  if (!ago) return null;

  const ageHours = (Date.now() - synced.getTime()) / 3_600_000;
  const stale = ageHours > maxAgeHours;

  return (
    <span className={stale ? 'badge badge--warn' : 'badge'}>
      {stale ? `${ago} 기준 · 오래됨` : `${ago} 기준`}
    </span>
  );
}

/** 데이터가 실제로 얼마나 자주 바뀌는지에 맞춘 임계치(시간). */
export const FRESHNESS_LIMIT = {
  /** 주간 메뉴표라 한 주가 지나면 지난주 것이다. */
  dining: 24 * 7,
  /** 공지는 매일 올라온다. 이틀 넘게 그대로면 수집이 멈춘 것으로 본다. */
  notices: 48,
  /** 건물과 전화번호는 거의 바뀌지 않는다. */
  directory: 24 * 30,
} as const;
