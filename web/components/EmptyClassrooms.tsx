'use client';

import { useEffect, useState } from 'react';

import EmptyState from './EmptyState';
import { formatTime } from '@/lib/format';
import { getPreferredBuilding, setPreferredBuilding } from '@/lib/prefs';
import type { EstimatedEmptyClassroomResponse } from '@/lib/types';

export interface BuildingClassrooms {
  slug: string;
  name: string;
  data: EstimatedEmptyClassroomResponse | null;
  degraded: boolean;
}

/**
 * 빈 강의실 목록과 건물 선택.
 *
 * 건물 열 곳치를 서버에서 미리 받아 두고 전환은 여기서만 한다.
 * 예전에는 건물을 누를 때마다 /study?building= 로 이동했는데, 그러면 이 화면이
 * searchParams 를 읽는 동적 라우트가 되어 ISR 캐시가 붙지 않았다.
 * 백엔드가 잠들어 있으면 학생이 타임아웃을 그대로 기다려야 했다(실측 20초).
 */
export default function EmptyClassrooms({ buildings }: { buildings: BuildingClassrooms[] }) {
  const [selected, setSelected] = useState(buildings[0]?.slug);

  // 지난번에 봤던 건물로 한 번 되돌린다. 첫 렌더는 서버와 같은 값이어야 하므로
  // 마운트 후에 바꾼다. 실패하면 그냥 기본값으로 둔다.
  useEffect(() => {
    const preferred = getPreferredBuilding();
    if (!preferred) return;
    if (!buildings.some((building) => building.slug === preferred)) return;
    setSelected(preferred);
  }, [buildings]);

  const current = buildings.find((building) => building.slug === selected) ?? buildings[0];

  return (
    <>
      <div className="chips">
        {buildings.map((building) => (
          <button
            key={building.slug}
            type="button"
            className="chip"
            aria-pressed={building.slug === current?.slug}
            onClick={() => {
              setPreferredBuilding(building.slug);
              setSelected(building.slug);
            }}
          >
            {building.name}
          </button>
        ))}
      </div>

      {current?.data ? (
        current.data.items.length > 0 ? (
          <>
            <ul className="list" style={{ marginTop: 12 }}>
              {current.data.items.map((item) => (
                <li key={item.room} className="row--split">
                  <span>
                    <span className="row__title">{item.room}</span>
                    {item.next_course_summary ? (
                      <span className="row__sub">다음 수업 {item.next_course_summary}</span>
                    ) : null}
                  </span>
                  <span className="row__sub">
                    {item.next_occupied_at
                      ? `${formatTime(item.next_occupied_at)}까지`
                      : item.availability_mode === 'realtime'
                        ? '실시간'
                        : '예상'}
                  </span>
                </li>
              ))}
            </ul>

            <p className="card__note">
              {current.data.availability_mode === 'realtime'
                ? '실시간 사용 현황 기준이에요.'
                : '시간표 기준 예상이라 실제로는 사용 중일 수 있어요.'}
              {current.data.estimate_note ? ` ${current.data.estimate_note}` : null}
            </p>
          </>
        ) : (
          <div style={{ marginTop: 12 }}>
            {/* 시간표 자체가 없는 것과 정말 빈 강의실이 없는 것은 다른 말이다.
                방학이라 시간표가 없을 때 "없어요" 라고 하면 학생은 "꽉 찼구나" 로
                읽는다. 백엔드가 estimate_note 로 알려주니 그대로 갈라 쓴다. */}
            {current.data.estimate_note?.includes('찾지 못했') ? (
              <EmptyState
                degraded={current.degraded}
                message="이 건물의 강의실 시간표를 아직 받아오지 못했어요."
                hint="방학 중이거나 시간표가 아직 공개되지 않았을 수 있어요."
              />
            ) : (
              <EmptyState
                degraded={current.degraded}
                message="지금 이 건물에 비어 있을 것으로 보이는 강의실이 없어요."
                hint="다른 건물을 눌러보세요."
              />
            )}
          </div>
        )
      ) : (
        <div style={{ marginTop: 12 }}>
          <EmptyState degraded />
        </div>
      )}
    </>
  );
}
