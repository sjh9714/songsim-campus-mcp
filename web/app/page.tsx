import Link from 'next/link';
import { FRESHNESS_LIMIT } from '@/lib/live-state';
import { Suspense } from 'react';

import Card from '@/components/Card';
import CardSkeleton from '@/components/CardSkeleton';
import HomeDining from '@/components/HomeDining';
import EmptyState from '@/components/EmptyState';
import FreshnessBadge from '@/components/FreshnessBadge';
import LibrarySeatsCard from '@/components/LibrarySeatsCard';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getDiningMenus, getNotices, requireFreshOrKeepLastPage } from '@/lib/api';
import { formatDate, truncate } from '@/lib/format';

export const revalidate = 60;

// 이 화면은 도서관 좌석 실시간 조회(최대 15초)를 안고 있다. 재검증이 도중에
// 잘리면 좌석 카드가 영영 갱신되지 않으므로 넉넉히 둔다. 학생이 아니라
// 백그라운드 재생성이 쓰는 시간이다.
export const maxDuration = 60;

const QUICK_FINDS = ['복사실', '보건실', '학생회관', '중앙도서관', '학사지원팀'];
const SCHOOL_NOTICE_URL = 'https://www.catholic.ac.kr/ko/campuslife/notice.do';

export default async function HomePage() {
  const [dining, notices] = await Promise.all([getDiningMenus(3), getNotices({ limit: 3 })]);
  requireFreshOrKeepLastPage(dining, '학식');

  return (
    <>
      <TopBar title="성심교정 도우미" subtitle="학교에서 헤매지 않게" />

      <HomeDining dining={dining} />

      {/* --- 도서관 좌석 (실시간 조회라 느리므로 나머지 화면과 분리해서 그린다) --- */}
      <Suspense fallback={<CardSkeleton title="도서관 좌석" />}>
        <LibrarySeatsCard compact />
      </Suspense>

      {/* --- 최신 공지 ---
           공지 화면은 두지 않는다. 학교가 이미 카톡·메일로 보내고, 전체 목록은
           학교 공지사항이 원본이다. 여기서는 "새로 올라온 게 있나" 만 보여준다. */}
      <Card
        title="최신 공지"
        href={SCHOOL_NOTICE_URL}
        moreLabel="학교 공지 전체"
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
                  <div className="row__sub">{formatDate(notice.published_at)}</div>
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
