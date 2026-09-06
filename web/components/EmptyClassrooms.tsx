'use client';

import { useEffect, useMemo, useState } from 'react';
import { useLiveData } from '@/lib/use-live-data';
import { isRecent, LIVE_MAX_AGE_MS } from '@/lib/live-state';

import EmptyState from './EmptyState';
import {
  CLASSROOM_USE_WINDOW_LABEL,
  isWithinClassroomUseWindow,
} from '@/lib/classrooms';
import { formatTime } from '@/lib/format';
import { getPreferredBuilding, setPreferredBuilding } from '@/lib/prefs';
import type {
  EstimatedEmptyClassroom,
  EstimatedEmptyClassroomResponse,
} from '@/lib/types';

export interface BuildingClassrooms {
  slug: string;
  name: string;
  data: EstimatedEmptyClassroomResponse | null;
  degraded: boolean;
}

function roomAvailabilityLabel(item: EstimatedEmptyClassroom): string {
  const nextOccupiedAt = formatTime(item.next_occupied_at);
  if (nextOccupiedAt) return `${nextOccupiedAt}까지`;
  if (item.availability_mode === 'realtime') return '실시간 공실';
  return '오늘 남은 수업 없음';
}

function availabilityNote(data: EstimatedEmptyClassroomResponse): string {
  if (data.availability_mode === 'realtime') {
    return '학교 실시간 사용 현황 기준입니다.';
  }
  if (data.availability_mode === 'mixed') {
    return '일부 강의실은 실시간 현황, 나머지는 공식 시간표를 기준으로 표시합니다.';
  }
  return '공식 시간표에서 현재 수업이 없는 강의실입니다. 행사·대여·실제 점유는 반영되지 않습니다.';
}

/**
 * 빈 강의실 목록과 건물 선택.
 *
 * 건물 목록은 캐시하고 선택한 한 건물만 새로 확인한다.
 * 오래된 평가 시각이나 다음 수업 시작 시각을 넘긴 결과는 현재 공실로 표시하지 않는다.
 */
export default function EmptyClassrooms({ buildings }: { buildings: BuildingClassrooms[] }) {
  const [selected, setSelected] = useState(buildings[0]?.slug);
  const [currentTime, setCurrentTime] = useState<string | null>(null);

  // 지난번에 봤던 건물로 한 번 되돌린다. 첫 렌더는 서버와 같은 값이어야 하므로
  // 마운트 후에 바꾼다. 실패하면 그냥 기본값으로 둔다.
  useEffect(() => {
    const preferred = getPreferredBuilding();
    if (!preferred) return;
    if (!buildings.some((building) => building.slug === preferred)) return;
    setSelected(preferred);
  }, [buildings]);

  // 이 화면은 ISR 캐시에 오래 남을 수 있으므로 API 응답의 evaluated_at으로
  // 현재 이용 시간을 판정하면 안 된다. 첫 렌더는 서버 HTML과 맞춘 뒤,
  // 브라우저가 실제 현재 시각을 넣고 15초마다 경계를 다시 확인한다.
  useEffect(() => {
    const updateCurrentTime = () => setCurrentTime(new Date().toISOString());
    updateCurrentTime();
    const interval = window.setInterval(updateCurrentTime, 15_000);
    return () => window.clearInterval(interval);
  }, []);

  const building = buildings.find((building) => building.slug === selected) ?? buildings[0];
  const initial = useMemo(() => ({ data: building?.data ?? null, degraded: building?.degraded ?? false, servedFromSnapshot: false, snapshotAt: null }), [building]);
  const live = useLiveData(`kind=classrooms&building=${encodeURIComponent(building?.slug ?? '')}`, initial);
  const current = building ? { ...building, data: live.state.data, degraded: live.state.degraded } : null;
  const now = currentTime ? Date.parse(currentTime) : null;
  const recent = isRecent(current?.data?.evaluated_at, now, LIVE_MAX_AGE_MS) && !live.state.degraded;
  const withinUseWindow = currentTime ? isWithinClassroomUseWindow(currentTime) : true;
  const visibleItems = current?.data?.items.filter((item) => !item.next_occupied_at || Date.parse(item.next_occupied_at) > (now ?? 0)) ?? [];

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

      <div className="live-controls"><button className="chip" type="button" disabled={live.loading} onClick={live.refresh}>{live.loading ? '확인 중…' : '새로고침'}</button>
        <span className="row__sub">실제 점유가 아닌 시간표 기준 예상입니다.</span></div>

      {!recent || !currentTime ? <EmptyState message={live.loading || !currentTime ? '현재 시간표를 확인하고 있어요.' : '현재 시각 기준 시간표를 확인하지 못했어요.'} hint="이전 조회 결과를 현재 빈 강의실로 표시하지 않아요." /> : current?.data ? (
        !withinUseWindow ? (
          <div style={{ marginTop: 12 }}>
            <EmptyState
              message="지금은 공식 강의실 대여 시간 밖이에요."
              hint={`공식 대여 안내 기준 기본 이용 시간은 ${CLASSROOM_USE_WINDOW_LABEL}입니다. 학교 일정과 실제 개방 여부는 다를 수 있어요.`}
            />
          </div>
        ) : visibleItems.length > 0 ? (
          <>
            <ul className="list" style={{ marginTop: 12 }}>
              {visibleItems.map((item) => (
                <li key={item.room} className="row--split">
                  <span>
                    <span className="row__title">{item.room}</span>
                    {item.next_course_summary ? (
                      <span className="row__sub">다음 수업 {item.next_course_summary}</span>
                    ) : null}
                  </span>
                  <span className="row__sub">{roomAvailabilityLabel(item)}</span>
                </li>
              ))}
            </ul>

            <p className="card__note">{availabilityNote(current.data)}</p>
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
