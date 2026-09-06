'use client';

import { FRESHNESS_LIMIT } from '@/lib/live-state';
import Card from './Card';
import DayMenu from './DayMenu';
import EmptyState from './EmptyState';
import FreshnessBadge from './FreshnessBadge';
import type { Fetched } from '@/lib/api';
import { formatDate, todayInSeoul } from '@/lib/format';
import { useNow } from '@/lib/use-now';
import type { CampusDiningMenuResponse } from '@/lib/types';

export default function HomeDining({ dining }: { dining: Fetched<CampusDiningMenuResponse[]> }) {
  const now = useNow();
  const today = now === null ? null : todayInSeoul(new Date(now));
  const next = today ? dining.data.flatMap((menu) => (menu.days ?? [])
    .filter((day) => day.date >= today).map((day) => ({ menu, day })))
    .sort((a, b) => a.day.date.localeCompare(b.day.date))[0] : null;
  const menu = next?.menu ?? dining.data[0];
  return <Card title={next ? (next.day.date === today ? '오늘의 학식' : '다음 학식') : '학식'} href="/dining"
    note={menu ? <FreshnessBadge syncedAt={menu.last_synced_at} maxAgeHours={FRESHNESS_LIMIT.dining} /> : null}>
    {menu ? <>
      <div className="row__title dining-venue"><span>{menu.venue_name}</span>
        <span className="dining-venue__location">{menu.location_text ?? menu.place_name}</span></div>
      {next ? <><div className="row__sub">{next.day.date === today ? '오늘 · ' : ''}{formatDate(next.day.date)} ({next.day.weekday})</div>
        <DayMenu day={next.day} compact /></> :
        <EmptyState message={now === null ? '메뉴 날짜를 확인하고 있어요.' : '오늘 이후로 정리된 메뉴가 없어요.'} hint="학식 화면에서 날짜별 메뉴와 학교 원문을 확인해 주세요." />}
    </> : <EmptyState degraded={dining.degraded} message="지금 받은 메뉴 정보가 없어요." />}
  </Card>;
}
