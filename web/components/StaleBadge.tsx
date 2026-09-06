'use client';

import { formatAgo } from '@/lib/format';
import type { Fetched } from '@/lib/api';
import { useNow } from '@/lib/use-now';

/**
 * 지금 보고 있는 값이 언제 기준인지 학생에게 알린다.
 * 백엔드가 잠들어 있어 직전 성공값을 대신 보여주는 중이면 그 사실을 숨기지 않는다.
 */
export default function StaleBadge({ state }: { state: Pick<Fetched<unknown>, 'servedFromSnapshot' | 'snapshotAt'> }) {
  const now = useNow();
  if (!state.servedFromSnapshot) return null;

  const ago = now === null ? null : formatAgo(state.snapshotAt, now);
  return (
    <span className="badge badge--warn">{ago ? `${ago} 기준` : '이전에 받아둔 정보'}</span>
  );
}
