import { Suspense } from 'react';

import BuildingPicker from '@/components/BuildingPicker';
import CardSkeleton from '@/components/CardSkeleton';
import EmptyState from '@/components/EmptyState';
import LibrarySeatsCard from '@/components/LibrarySeatsCard';
import TopBar from '@/components/TopBar';
import { getBuildings, getEmptyClassrooms } from '@/lib/api';
import { formatTime } from '@/lib/format';

export const revalidate = 60;

export default async function StudyPage({
  searchParams,
}: {
  searchParams: Promise<{ building?: string }>;
}) {
  const { building } = await searchParams;

  const buildings = await getBuildings();

  const selected = building ?? buildings.data[0]?.slug;
  const classrooms = selected ? await getEmptyClassrooms(selected) : null;

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

        {buildings.data.length === 0 ? (
          <EmptyState degraded={buildings.degraded} message="등록된 건물이 없어요." />
        ) : (
          <>
            <BuildingPicker
              buildings={buildings.data.map((place) => ({ slug: place.slug, name: place.name }))}
              selected={selected}
              hasExplicitSelection={Boolean(building)}
            />

            {classrooms?.data ? (
              classrooms.data.items.length > 0 ? (
                <>
                  <ul className="list" style={{ marginTop: 12 }}>
                    {classrooms.data.items.map((item) => (
                      <li key={item.room} className="row--split">
                        <span>
                          <span className="row__title">{item.room}</span>
                          {item.next_course_summary ? (
                            <span className="row__sub">다음 수업 {item.next_course_summary}</span>
                          ) : null}
                        </span>
                        <span className="row__sub">
                          {item.next_occupied_at
                            ? `${formatTime(item.next_occupied_at)}까지`
                            : item.availability_mode === 'realtime'
                              ? '실시간'
                              : '예상'}
                        </span>
                      </li>
                    ))}
                  </ul>

                  <p className="card__note">
                    {classrooms.data.availability_mode === 'realtime'
                      ? '실시간 사용 현황 기준이에요.'
                      : '시간표 기준 예상이라 실제로는 사용 중일 수 있어요.'}
                    {classrooms.data.estimate_note ? ` ${classrooms.data.estimate_note}` : null}
                  </p>
                </>
              ) : (
                <div style={{ marginTop: 12 }}>
                  {/* 시간표 자체가 없는 것과 정말 빈 강의실이 없는 것은 다른 말이다.
                      방학이라 시간표가 없을 때 "없어요" 라고 하면 학생은 "꽉 찼구나" 로
                      읽는다. 백엔드가 estimate_note 로 알려주니 그대로 갈라 쓴다. */}
                  {classrooms.data.estimate_note?.includes('찾지 못했') ? (
                    <EmptyState
                      degraded={classrooms.degraded}
                      message="이 건물의 강의실 시간표를 아직 받아오지 못했어요."
                      hint="방학 중이거나 시간표가 아직 공개되지 않았을 수 있어요."
                    />
                  ) : (
                    <EmptyState
                      degraded={classrooms.degraded}
                      message="지금 이 건물에 비어 있을 것으로 보이는 강의실이 없어요."
                      hint="다른 건물을 눌러보세요."
                    />
                  )}
                </div>
              )
            ) : (
              <div style={{ marginTop: 12 }}>
                <EmptyState degraded />
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
