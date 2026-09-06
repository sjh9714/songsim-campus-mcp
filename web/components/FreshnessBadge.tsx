'use client';

import { formatAgo } from '@/lib/format';
import { useNow } from '@/lib/use-now';

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
  const now = useNow();
  if (!syncedAt) return null;

  const synced = new Date(syncedAt);
  if (Number.isNaN(synced.getTime())) return null;

  const ago = now === null ? null : formatAgo(syncedAt, now);
  if (!ago) return null;

  const ageHours = (now! - synced.getTime()) / 3_600_000;
  const stale = ageHours > maxAgeHours;

  return (
    <span className={stale ? 'badge badge--warn' : 'badge'}>
      {stale ? `${ago} 기준 · 오래됨` : `${ago} 기준`}
    </span>
  );
}
