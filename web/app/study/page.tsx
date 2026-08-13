import { Suspense } from 'react';

import CardSkeleton from '@/components/CardSkeleton';
import EmptyClassrooms, { type BuildingClassrooms } from '@/components/EmptyClassrooms';
import EmptyState from '@/components/EmptyState';
import LibrarySeatsCard from '@/components/LibrarySeatsCard';
import TopBar from '@/components/TopBar';
import { getBuildings, getEmptyClassrooms, requireFreshOrKeepLastPage } from '@/lib/api';

export const revalidate = 60;

// 아래 건물별 조회가 백엔드 사정에 따라 길어질 수 있다. 이 시간은 학생이 아니라
// 백그라운드 재생성이 쓰는 것이고, 학생은 그동안 직전 화면을 받는다.
export const maxDuration = 60;

/** 건물을 한 번에 몇 개씩 조회할지. 백엔드가 감당할 수 있는 만큼만 보낸다. */
const FETCH_CONCURRENCY = 5;

export default async function StudyPage() {
  const buildings = await getBuildings();
  requireFreshOrKeepLastPage(buildings, '건물 목록');

  // 건물 열 곳치를 미리 받아 둔다. searchParams 를 읽지 않으므로 이 화면은
  // 프리렌더되고, 백엔드가 잠들어 있어도 학생은 직전 화면을 그대로 받는다.
  //
  // 열 곳을 한꺼번에 요청했더니 무료 플랜 백엔드가 밀려서 두 곳이 5초 제한에
  // 걸렸다. 단독으로는 2초면 끝나는 요청이다. 그래서 몇 개씩 끊어서 보낸다.
  const withClassrooms: BuildingClassrooms[] = [];
  for (let index = 0; index < buildings.data.length; index += FETCH_CONCURRENCY) {
    const batch = await Promise.all(
      buildings.data.slice(index, index + FETCH_CONCURRENCY).map(async (place) => {
        const classrooms = await getEmptyClassrooms(place.slug);
        return {
          slug: place.slug,
          name: place.name,
          data: classrooms.data,
          degraded: classrooms.degraded,
        };
      }),
    );
    withClassrooms.push(...batch);
  }

  return (
    <>
      <TopBar title="공부할 곳" subtitle="도서관 좌석과 빈 강의실" />

      {/* --- 도서관 좌석 (실시간 조회라 느리므로 나머지 화면과 분리해서 그린다) --- */}
      <Suspense fallback={<CardSkeleton title="도서관 좌석" />}>
        <LibrarySeatsCard />
      </Suspense>

      {/* --- 빈 강의실 --- */}
      <section className="card">
        <div className="card__head">
          <h2 className="card__title">지금 빈 강의실</h2>
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
