import { Suspense } from 'react';

import CardSkeleton from '@/components/CardSkeleton';
import EmptyState from '@/components/EmptyState';
import SearchResults from '@/components/SearchResults';
import TopBar from '@/components/TopBar';

export const revalidate = 3600;

/**
 * 통합 검색.
 *
 * 자연어 인텐트 분류를 하지 않는다. 대신 검색어를 "틀려도 학생이 다치지 않는"
 * 네 도메인에 동시에 던지고, 나온 것만 종류별로 묶어서 보여준다.
 * 등록/공결/졸업요건 같은 절차 안내는 여기서 다루지 않는다 —
 * 엉뚱한 절차를 보여주는 쪽이 못 찾는 쪽보다 나쁘기 때문.
 *
 * 검색어를 미리 알 수 없어 이 화면만은 프리렌더가 안 된다. 그래서 조회는
 * SearchResults 안으로 밀어 넣고 검색창부터 내보낸다.
 */
export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q ?? '').trim();

  if (!query) {
    return (
      <>
        <TopBar title="검색" subtitle="건물, 부서, 과목, 프로그램" />
        <section className="card">
          <EmptyState message="찾을 이름을 입력해 주세요." />
        </section>
      </>
    );
  }

  return (
    <>
      <TopBar title="검색" subtitle={`"${query}"`} query={query} />
      {/* key 를 검색어로 두어야 다음 검색에서 이전 결과가 남지 않고
          다시 "찾는 중" 으로 돌아간다. */}
      <Suspense key={query} fallback={<CardSkeleton title="찾는 중" />}>
        <SearchResults query={query} />
      </Suspense>
    </>
  );
}
