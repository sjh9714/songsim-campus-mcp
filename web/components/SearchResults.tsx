import Link from 'next/link';

import EmptyState from './EmptyState';
import { getCourses, getPcSoftware, getPhoneBook, getPlaces } from '@/lib/api';
import { truncate } from '@/lib/format';

// 검색이 빗나갔을 때 보여줄 출발점. 신입생이 첫 주에 가장 많이 찾는 것들이다.
const COMMON_SEARCHES = ['보건실', '복사실', '학사지원팀', '중앙도서관', '학생회관'];

/**
 * 검색 결과.
 *
 * 검색어는 미리 알 수 없어서 이 화면만은 프리렌더할 수 없다. 그래서 결과만
 * Suspense 경계 안에 두고 검색창은 먼저 그린다. 백엔드가 잠들어 있어 네 번의
 * 조회가 제한시간까지 가더라도, 학생은 빈 화면 대신 검색창을 바로 받는다.
 */
export default async function SearchResults({ query }: { query: string }) {
  const [places, phones, courses, software] = await Promise.all([
    getPlaces({ query, limit: 8 }),
    getPhoneBook({ query, limit: 8 }),
    getCourses({ query, limit: 8 }),
    getPcSoftware({ query, limit: 8 }),
  ]);

  const total =
    places.data.length + phones.data.length + courses.data.length + software.data.length;
  const degraded = places.degraded && phones.degraded && courses.degraded && software.degraded;

  if (total === 0) {
    // 안내 두 줄만 남기면 화면이 텅 비어 막다른 길이 된다.
    // 자주 찾는 것들을 같이 놓아 다음 행동을 만들어 준다.
    return (
      <section className="card">
        <EmptyState
          degraded={degraded}
          message={`"${query}"에 해당하는 결과를 못 찾았어요.`}
          hint="건물, 부서, 과목 이름으로 찾을 수 있어요."
        />
        <div className="section__title">이런 걸 많이 찾아요</div>
        <div className="chips">
          {COMMON_SEARCHES.map((keyword) => (
            <Link key={keyword} className="chip" href={`/search?q=${encodeURIComponent(keyword)}`}>
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
    );
  }

  return (
    <>
      <div className="section__title">결과 {total}건</div>

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
