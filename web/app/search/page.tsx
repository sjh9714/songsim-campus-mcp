import Link from 'next/link';

import EmptyState from '@/components/EmptyState';
import TopBar from '@/components/TopBar';
import { getCourses, getPcSoftware, getPhoneBook, getPlaces } from '@/lib/api';
import { truncate } from '@/lib/format';

export const revalidate = 3600;

// 검색이 빗나갔을 때 보여줄 출발점. 신입생이 첫 주에 가장 많이 찾는 것들이다.
const COMMON_SEARCHES = ['보건실', '복사실', '학사지원팀', '중앙도서관', '학생회관'];

/**
 * 통합 검색.
 *
 * 자연어 인텐트 분류를 하지 않는다. 대신 검색어를 "틀려도 학생이 다치지 않는"
 * 네 도메인에 동시에 던지고, 나온 것만 종류별로 묶어서 보여준다.
 * 등록/공결/졸업요건 같은 절차 안내는 여기서 다루지 않는다 —
 * 엉뚱한 절차를 보여주는 쪽이 못 찾는 쪽보다 나쁘기 때문.
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

  const [places, phones, courses, software] = await Promise.all([
    getPlaces({ query, limit: 8 }),
    getPhoneBook({ query, limit: 8 }),
    getCourses({ query, limit: 8 }),
    getPcSoftware({ query, limit: 8 }),
  ]);

  const total =
    places.data.length + phones.data.length + courses.data.length + software.data.length;
  const degraded = places.degraded && phones.degraded && courses.degraded && software.degraded;

  return (
    <>
      <TopBar title="검색" subtitle={`"${query}" 결과 ${total}건`} query={query} />

      {total === 0 ? (
        // 안내 두 줄만 남기면 화면이 텅 비어 막다른 길이 된다.
        // 자주 찾는 것들을 같이 놓아 다음 행동을 만들어 준다.
        <section className="card">
          <EmptyState
            degraded={degraded}
            message={`"${query}"에 해당하는 결과를 못 찾았어요.`}
            hint="건물, 부서, 과목 이름으로 찾을 수 있어요."
          />
          <div className="section__title">이런 걸 많이 찾아요</div>
          <div className="chips">
            {COMMON_SEARCHES.map((keyword) => (
              <Link
                key={keyword}
                className="chip"
                href={`/search?q=${encodeURIComponent(keyword)}`}
              >
                {keyword}
              </Link>
            ))}
          </div>
          <Link className="linkout" href="/find">
            건물·연락처 목록에서 둘러보기 ›
          </Link>
          {/* 휴학·증명서 같은 절차는 이 앱이 답할 대상이 아니다. 학교로 보내되
              막다른 길로 두지는 않는다. */}
          <a
            className="linkout"
            href="https://www.catholic.ac.kr/ko/index.do"
            target="_blank"
            rel="noreferrer"
            style={{ marginLeft: 14 }}
          >
            학교 홈페이지에서 찾기 ↗
          </a>
        </section>
      ) : null}

      {places.data.length > 0 ? (
        <section className="card">
          <div className="card__head">
            <h2 className="card__title">장소</h2>
          </div>
          <ul className="list">
            {places.data.map((place) => (
              <li key={place.id}>
                <div className="row__title">{place.name}</div>
                {place.matched_facility ? (
                  <div className="row__sub">
                    {place.matched_facility.name}
                    {place.matched_facility.location_hint
                      ? ` · ${place.matched_facility.location_hint}`
                      : ''}
                    {place.matched_facility.phone ? ` · ${place.matched_facility.phone}` : ''}
                  </div>
                ) : place.description ? (
                  <div className="row__sub">{truncate(place.description, 80)}</div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {phones.data.length > 0 ? (
        <section className="card">
          <div className="card__head">
            <h2 className="card__title">전화번호</h2>
          </div>
          <ul className="list">
            {phones.data.map((entry) => (
              <li key={entry.id} className="row--split">
                <span>
                  <span className="row__title">{entry.department}</span>
                  {entry.tasks ? <span className="row__sub">{truncate(entry.tasks, 60)}</span> : null}
                </span>
                <a className="row__value" href={`tel:${entry.phone.replace(/[^0-9+]/g, '')}`}>
                  {entry.phone}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {courses.data.length > 0 ? (
        <section className="card">
          <div className="card__head">
            <h2 className="card__title">과목</h2>
          </div>
          <ul className="list">
            {courses.data.map((course) => (
              <li key={course.id}>
                <div className="row__title">{course.title}</div>
                <div className="row__sub">
                  {[
                    `${course.year}-${course.semester}`,
                    course.professor,
                    course.raw_schedule,
                    course.room,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {software.data.length > 0 ? (
        <section className="card">
          <div className="card__head">
            <h2 className="card__title">설치된 실습실</h2>
          </div>
          <ul className="list">
            {software.data.map((entry) => (
              <li key={entry.id}>
                <div className="row__title">
                  {entry.room}
                  {entry.pc_count ? ` (${entry.pc_count}대)` : ''}
                </div>
                {entry.software_list.length > 0 ? (
                  <div className="row__sub">{truncate(entry.software_list.join(', '), 90)}</div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
