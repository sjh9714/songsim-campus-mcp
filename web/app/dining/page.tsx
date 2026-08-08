import Link from 'next/link';

import DayMenu from '@/components/DayMenu';
import EmptyState from '@/components/EmptyState';
import FreshnessBadge, { FRESHNESS_LIMIT } from '@/components/FreshnessBadge';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getDiningMenus } from '@/lib/api';
import { formatDate, todayInSeoul } from '@/lib/format';

export const revalidate = 3600;

export default async function DiningPage({
  searchParams,
}: {
  searchParams: Promise<{ day?: string }>;
}) {
  const { day: requestedDay } = await searchParams;
  const dining = await getDiningMenus(20);
  const today = todayInSeoul();

  return (
    <>
      <TopBar title="학식" subtitle="교내 식당 메뉴" />

      {dining.data.length === 0 ? (
        <section className="card">
          <EmptyState degraded={dining.degraded} message="올라온 메뉴가 없어요." />
        </section>
      ) : (
        dining.data.map((menu) => {
          // 주말이면 오늘이 주간 표에 없다. 그때는 다가오는 첫날을 보여준다.
          const selected =
            menu.days.find((item) => item.date === requestedDay) ??
            menu.days.find((item) => item.date >= today) ??
            menu.days[0] ??
            null;

          return (
            <section className="card" key={menu.venue_slug}>
              <div className="card__head">
                <h2 className="card__title">{menu.venue_name}</h2>
                <StaleBadge state={dining} />
              </div>
              <FreshnessBadge syncedAt={menu.last_synced_at} maxAgeHours={FRESHNESS_LIMIT.dining} />

              {menu.week_label ? <div className="row__sub">{menu.week_label}</div> : null}

              {selected ? (
                <>
                  <div className="daypicker">
                    {menu.days.map((item) => (
                      <Link
                        key={item.date}
                        className="chip"
                        href={`/dining?day=${item.date}#${menu.venue_slug}`}
                        aria-pressed={item.date === selected.date}
                      >
                        {item.weekday}
                        {item.date === today ? ' · 오늘' : ''}
                      </Link>
                    ))}
                  </div>
                  <div className="row__sub" style={{ marginTop: 10 }}>
                    {formatDate(selected.date)} ({selected.weekday})
                  </div>
                  <DayMenu day={selected} />
                </>
              ) : menu.menu_text ? (
                // 주간 표가 아닌 PDF 는 원문을 싣지 않는다. 카페 멘사는 입점 업체의
                // 가격표인데, 문서 안에 "무단 복제, 배포, 공개를 엄격히 금지합니다" 와
                // 제3자 저작권 표기가 들어 있다. 학교 공개 자료가 아니므로 링크만 건다.
                <EmptyState
                  message="주간 메뉴표 형태가 아니라 여기서는 정리해 드릴 수 없어요."
                  hint="아래 학교 원문에서 확인해 주세요."
                />
              ) : (
                <EmptyState message="이번 주 메뉴가 아직 올라오지 않았어요." />
              )}

              {menu.source_url ? (
                <a className="linkout" href={menu.source_url} target="_blank" rel="noreferrer">
                  학교 원문 보기 ›
                </a>
              ) : null}
            </section>
          );
        })
      )}
    </>
  );
}
