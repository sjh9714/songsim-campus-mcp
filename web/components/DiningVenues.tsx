'use client';

import { useId, useRef, useState } from 'react';

import EmptyState from './EmptyState';
import FreshnessBadge from './FreshnessBadge';
import StaleBadge from './StaleBadge';
import VenueDays from './VenueDays';
import type { Fetched } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { FRESHNESS_LIMIT } from '@/lib/live-state';
import type { CampusDiningMenu } from '@/lib/types';

export default function DiningVenues({ dining }: { dining: Fetched<CampusDiningMenu[]> }) {
  const [selected, setSelected] = useState(dining.data[0]?.venue_slug);
  const id = useId();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const active = dining.data.some((menu) => menu.venue_slug === selected) ? selected : dining.data[0]?.venue_slug;

  return (
    <>
      <div className="venue-tabs" role="tablist" aria-label="교내 식당 선택">
        {dining.data.map((menu, index) => (
          <button
            key={menu.venue_slug}
            ref={(element) => { tabs.current[index] = element; }}
            type="button"
            role="tab"
            id={`${id}-tab-${index}`}
            aria-controls={`${id}-panel-${index}`}
            aria-selected={menu.venue_slug === active}
            aria-label={menu.venue_name}
            tabIndex={menu.venue_slug === active ? 0 : -1}
            onClick={() => setSelected(menu.venue_slug)}
            onKeyDown={(event) => {
              let next: number;
              if (event.key === 'ArrowRight') next = (index + 1) % dining.data.length;
              else if (event.key === 'ArrowLeft') next = (index - 1 + dining.data.length) % dining.data.length;
              else if (event.key === 'Home') next = 0;
              else if (event.key === 'End') next = dining.data.length - 1;
              else return;
              event.preventDefault();
              setSelected(dining.data[next].venue_slug);
              tabs.current[next]?.focus();
            }}
          >
            {/* 한글·영문 병기 이름은 탭에서만 짧게, 제목과 접근성 이름에는 원문을 남긴다. */}
            {menu.venue_name.match(/^([가-힣\s]+)\s+[A-Za-z]/)?.[1].trim() ?? menu.venue_name}
          </button>
        ))}
      </div>

      {dining.data.map((menu, index) => {
        const location = menu.location_text ?? menu.place_name;
        return (
          // Keep inactive panels mounted so each restaurant retains its selected day.
          <section
            key={menu.venue_slug}
            className="card dining-panel"
            role="tabpanel"
            id={`${id}-panel-${index}`}
            aria-labelledby={`${id}-tab-${index}`}
            hidden={menu.venue_slug !== active}
            tabIndex={0}
          >
            <div className="card__head">
              <h2 className="card__title dining-venue">
                <span>{menu.venue_name}</span>
                {location ? <span className="dining-venue__location" aria-label={`위치 ${location}`}>{location}</span> : null}
              </h2>
            </div>
            <div className="dining-meta">
              {dining.servedFromSnapshot ? <StaleBadge state={dining} /> : <FreshnessBadge syncedAt={menu.last_synced_at} maxAgeHours={FRESHNESS_LIMIT.dining} />}
            </div>

            {menu.days.length > 0 ? (
              <VenueDays days={menu.days} />
            ) : menu.menu_text ? (
              // Non-weekly, restricted vendor PDFs are never copied into this screen.
              <EmptyState message="주간 메뉴표 형태가 아니라 여기서는 정리해 드릴 수 없어요." hint="아래 학교 원문에서 확인해 주세요." />
            ) : (
              <EmptyState message="정리된 메뉴 정보가 없어요. 학교 원문에서 확인해 주세요." />
            )}

            <div className="dining-footer">
              {menu.opening_hours || menu.week_label || (menu.week_start && menu.week_end) ? (
                <details className="dining-info">
                  <summary>운영시간·주간 안내</summary>
                  {menu.opening_hours ? <p className="row__sub">공식 운영 안내 · {menu.opening_hours}</p> : null}
                  {menu.week_start && menu.week_end ? (
                    <p className="row__sub">{formatDate(menu.week_start)} ~ {formatDate(menu.week_end)}</p>
                  ) : menu.week_label ? <p className="row__sub">{menu.week_label}</p> : null}
                </details>
              ) : null}
              {menu.source_url ? <a className="linkout dining-source" href={menu.source_url} target="_blank" rel="noreferrer">학교 원문 보기 ›</a> : null}
            </div>
          </section>
        );
      })}
    </>
  );
}
