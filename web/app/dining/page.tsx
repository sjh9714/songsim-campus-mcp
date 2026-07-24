import EmptyState from '@/components/EmptyState';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getDiningMenus } from '@/lib/api';
import { formatAgo } from '@/lib/format';

export const revalidate = 3600;

export default async function DiningPage() {
  const dining = await getDiningMenus(20);

  return (
    <>
      <TopBar title="학식" subtitle="교내 식당 주간 메뉴" />

      {dining.data.length === 0 ? (
        <section className="card">
          <EmptyState degraded={dining.degraded} message="올라온 메뉴가 없어요." />
        </section>
      ) : (
        dining.data.map((menu) => (
          <section className="card" key={menu.venue_slug}>
            <div className="card__head">
              <h2 className="card__title">{menu.venue_name}</h2>
              <StaleBadge state={dining} />
            </div>

            {menu.week_label ? <div className="row__sub">{menu.week_label}</div> : null}

            {menu.menu_text ? (
              <p className="menu-text" style={{ marginTop: 10 }}>
                {menu.menu_text}
              </p>
            ) : (
              <EmptyState message="이번 주 메뉴가 아직 올라오지 않았어요." />
            )}

            {menu.source_url ? (
              <a className="linkout" href={menu.source_url} target="_blank" rel="noreferrer">
                학교 원문 보기 ›
              </a>
            ) : null}

            <p className="card__note">{formatAgo(menu.last_synced_at)} 갱신</p>
          </section>
        ))
      )}
    </>
  );
}
