import Link from 'next/link';

import EmptyState from '@/components/EmptyState';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getNoticeCategories, getNotices } from '@/lib/api';
import { formatAgo, truncate } from '@/lib/format';

export const revalidate = 600;

export default async function NoticesPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string }>;
}) {
  const { category } = await searchParams;

  const [categories, notices] = await Promise.all([
    getNoticeCategories(),
    getNotices({ category, limit: 30 }),
  ]);

  return (
    <>
      <TopBar title="공지" subtitle="학사·행사·장학 공지 모아보기" />

      {categories.data.length > 0 ? (
        <div className="chips" style={{ marginTop: 12 }}>
          <Link className="chip" href="/notices" aria-pressed={!category}>
            전체
          </Link>
          {categories.data.map((item) => (
            <Link
              key={item.category}
              className="chip"
              href={`/notices?category=${encodeURIComponent(item.category)}`}
              aria-pressed={category === item.category}
            >
              {item.category_display}
            </Link>
          ))}
        </div>
      ) : null}

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">
            {categories.data.find((item) => item.category === category)?.category_display ??
              '최신 공지'}
          </h2>
          <StaleBadge state={notices} />
        </div>

        {notices.data.length === 0 ? (
          <EmptyState
            degraded={notices.degraded}
            message="이 분류에 올라온 공지가 없어요."
            hint="다른 분류를 눌러보세요."
          />
        ) : (
          <ul className="list">
            {notices.data.map((notice) => (
              <li key={notice.id}>
                <a href={notice.source_url ?? '#'} target="_blank" rel="noreferrer">
                  <div className="row__title">{notice.title}</div>
                  {notice.summary ? (
                    <div className="row__sub">{truncate(notice.summary, 90)}</div>
                  ) : null}
                  <div className="row__sub">{formatAgo(notice.published_at)}</div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
