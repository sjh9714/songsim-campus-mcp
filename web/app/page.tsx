import Link from 'next/link';
import { Suspense } from 'react';

import Card from '@/components/Card';
import CardSkeleton from '@/components/CardSkeleton';
import DayMenu from '@/components/DayMenu';
import EmptyState from '@/components/EmptyState';
import FreshnessBadge, { FRESHNESS_LIMIT } from '@/components/FreshnessBadge';
import LibrarySeatsCard from '@/components/LibrarySeatsCard';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getDiningMenus, getNotices } from '@/lib/api';
import { formatAgo, formatDate, todayInSeoul, truncate } from '@/lib/format';

export const revalidate = 60;

const QUICK_FINDS = ['복사실', '보건실', '학생회관', '중앙도서관', '학사지원팀'];

export default async function HomePage() {
  const [dining, notices] = await Promise.all([getDiningMenus(3), getNotices({ limit: 3 })]);

  // 주간 표가 있는 식당을 먼저 고른다. 어떤 곳은 가격표 PDF 라 요일 구조가 없다.
  const today = todayInSeoul();
  const withDay = dining.data
    .map((menu) => ({
      menu,
      // 주말에는 이번 주 표에 오늘이 없다. 그때는 다가오는 첫날을 보여준다.
      // 학생이 궁금한 건 "그럼 내일은?" 이지 지난 주 표가 아니다.
      day: menu.days.find((item) => item.date >= today) ?? null,
    }))
    .find((entry) => entry.day);
  const topMenu = withDay?.menu ?? dining.data[0] ?? null;
  const todayMenu = withDay?.day ?? null;

  return (
    <>
      <TopBar title="성심교정 도우미" subtitle="학교에서 헤매지 않게" />

      {/* --- 오늘의 학식 --- */}
      <Card
        title="오늘의 학식"
        href="/dining"
        note={
          topMenu ? (
            <FreshnessBadge syncedAt={topMenu.last_synced_at} maxAgeHours={FRESHNESS_LIMIT.dining} />
          ) : null
        }
      >
        {topMenu ? (
          <>
            <div className="row__title">{topMenu.venue_name}</div>
            {todayMenu ? (
              <>
                <div className="row__sub">
                  {todayMenu.date === today ? '오늘 · ' : ''}
                  {formatDate(todayMenu.date)} ({todayMenu.weekday})
                </div>
                <DayMenu day={todayMenu} />
              </>
            ) : (
              <>
                {topMenu.week_label ? <div className="row__sub">{topMenu.week_label}</div> : null}
                <p className="menu-text" style={{ marginTop: 8 }}>
                  {truncate(topMenu.menu_text, 160) || '이번 주 메뉴가 아직 올라오지 않았어요.'}
                </p>
              </>
            )}
          </>
        ) : (
          <EmptyState degraded={dining.degraded} message="지금 올라온 학식 메뉴가 없어요." />
        )}
      </Card>

      {/* --- 도서관 좌석 (실시간 조회라 느리므로 나머지 화면과 분리해서 그린다) --- */}
      <Suspense fallback={<CardSkeleton title="도서관 좌석" />}>
        <LibrarySeatsCard compact />
      </Suspense>

      {/* --- 최신 공지 --- */}
      <Card
        title="최신 공지"
        href="/notices"
        note={
          <>
            <StaleBadge state={notices} />{' '}
            {notices.data[0] ? (
              <FreshnessBadge
                syncedAt={notices.data[0].last_synced_at}
                maxAgeHours={FRESHNESS_LIMIT.notices}
              />
            ) : null}
          </>
        }
      >
        {notices.data.length > 0 ? (
          <ul className="list">
            {notices.data.map((notice) => (
              <li key={notice.id}>
                <a href={notice.source_url ?? '#'} target="_blank" rel="noreferrer">
                  <div className="row__title">{truncate(notice.title, 60)}</div>
                  <div className="row__sub">{formatAgo(notice.published_at)}</div>
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState degraded={notices.degraded} message="올라온 공지가 없어요." />
        )}
      </Card>

      {/* --- 찾기 --- */}
      <Card title="어디야? 몇 번이야?" href="/find" moreLabel="전체 보기">
        <div className="row__sub">건물, 시설, 부서 전화번호를 이름으로 찾을 수 있어요.</div>
        <div className="chips">
          {QUICK_FINDS.map((keyword) => (
            <Link key={keyword} className="chip" href={`/search?q=${encodeURIComponent(keyword)}`}>
              {keyword}
            </Link>
          ))}
        </div>
      </Card>
    </>
  );
}
