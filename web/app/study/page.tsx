import { Suspense } from 'react';

import CardSkeleton from '@/components/CardSkeleton';
import EmptyClassrooms from '@/components/EmptyClassrooms';
import EmptyState from '@/components/EmptyState';
import LibrarySeatsCard from '@/components/LibrarySeatsCard';
import TopBar from '@/components/TopBar';
import { getBuildings, requireFreshOrKeepLastPage } from '@/lib/api';

export const revalidate = 60;

// 아래 건물별 조회가 백엔드 사정에 따라 길어질 수 있다. 이 시간은 학생이 아니라
// 백그라운드 재생성이 쓰는 것이고, 학생은 그동안 직전 화면을 받는다.
export const maxDuration = 60;


export default async function StudyPage() {
  const buildings = await getBuildings();
  requireFreshOrKeepLastPage(buildings, '건물 목록');

  // Stable building navigation is cached; only the selected building is queried live.
  const withClassrooms = buildings.data.map((place) => ({
    slug: place.slug, name: place.name, data: null, degraded: false,
  }));

  return (
    <>
      <TopBar title="공부할 곳" subtitle="도서관 좌석과 강의실 시간표" />

      {/* --- 도서관 좌석 (실시간 조회라 느리므로 나머지 화면과 분리해서 그린다) --- */}
      <Suspense fallback={<CardSkeleton title="도서관 좌석" />}>
        <LibrarySeatsCard />
      </Suspense>

      {/* --- 빈 강의실 --- */}
      <section className="card">
        <div className="card__head">
          <h2 className="card__title">시간표상 빈 강의실</h2>
        </div>

        {withClassrooms.length === 0 ? (
          <EmptyState degraded={buildings.degraded} message="등록된 건물이 없어요." />
        ) : (
          <EmptyClassrooms buildings={withClassrooms} />
        )}
      </section>
    </>
  );
}
