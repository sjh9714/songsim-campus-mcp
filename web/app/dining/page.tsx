import { FRESHNESS_LIMIT } from '@/lib/live-state';
import EmptyState from '@/components/EmptyState';
import FreshnessBadge from '@/components/FreshnessBadge';
import NearbyRestaurants from '@/components/NearbyRestaurants';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import VenueDays from '@/components/VenueDays';
import { getDiningMenus, getNearbyRestaurants, requireFreshOrKeepLastPage } from '@/lib/api';
import { formatDate } from '@/lib/format';

// 메뉴 자체는 주 단위로만 바뀌지만(TTL.dining 1시간), "오늘" 표시는 날짜가 넘어가면
// 틀린 말이 된다. 화면은 1분마다 다시 그리고 데이터는 캐시에서 가져다 쓴다.
export const revalidate = 60;

// 주변 식당의 기준점. 캠퍼스 본관이라 어느 건물에서 출발해도 크게 어긋나지 않는다.
// 건물을 고르게 하지 않는 이유는 searchParams 를 읽는 순간 이 화면이 동적이 되어
// ISR 캐시가 사라지기 때문이다. 그러면 백엔드가 잠들었을 때 학생이 그대로 기다린다.
const NEARBY_ORIGIN = 'songsim-hall';

export default async function DiningPage() {
  const [dining, nearby] = await Promise.all([
    getDiningMenus(20),
    getNearbyRestaurants(NEARBY_ORIGIN, 5),
  ]);
  // 주변 식당은 이 화면의 뼈대가 아니다. 못 받으면 그 카드만 비우고 학식은 내보낸다.
  requireFreshOrKeepLastPage(dining, '학식');

  return (
    <>
      <TopBar title="학식" subtitle="교내 식당 메뉴" />

      {dining.data.length === 0 ? (
        <section className="card">
          <EmptyState degraded={dining.degraded} message="올라온 메뉴가 없어요." />
        </section>
      ) : (
        dining.data.map((menu) => {
          const location = menu.location_text ?? menu.place_name;
          return (
            <section className="card" key={menu.venue_slug}>
              <div className="card__head">
                <h2 className="card__title dining-venue">
                  <span>{menu.venue_name}</span>
                  {location ? (
                    <span className="dining-venue__location" aria-label={`위치 ${location}`}>
                      {location}
                    </span>
                  ) : null}
                </h2>
                <StaleBadge state={dining} />
              </div>
              <FreshnessBadge syncedAt={menu.last_synced_at} maxAgeHours={FRESHNESS_LIMIT.dining} />

              {menu.opening_hours ? <p className="row__sub">공식 운영 안내 · {menu.opening_hours}</p> : null}
              {menu.week_start && menu.week_end ? (
                <div className="row__sub">
                  {formatDate(menu.week_start)} ~ {formatDate(menu.week_end)}
                </div>
              ) : menu.week_label ? (
                <div className="row__sub">{menu.week_label}</div>
              ) : null}

              {menu.days.length > 0 ? (
                <VenueDays days={menu.days} />
              ) : menu.menu_text ? (
                // 주간 표가 아닌 PDF 는 원문을 싣지 않는다. 카페 멘사는 입점 업체의
                // 가격표인데, 문서 안에 "무단 복제, 배포, 공개를 엄격히 금지합니다" 와
                // 제3자 저작권 표기가 들어 있다. 학교 공개 자료가 아니므로 링크만 건다.
                <EmptyState
                  message="주간 메뉴표 형태가 아니라 여기서는 정리해 드릴 수 없어요."
                  hint="아래 학교 원문에서 확인해 주세요."
                />
              ) : (
                <EmptyState message="정리된 메뉴 정보가 없어요. 학교 원문에서 확인해 주세요." />
              )}

              {menu.source_url ? (
                <a className="linkout" href={menu.source_url} target="_blank" rel="noreferrer">
                  학교 원문 보기 ›
                </a>
              ) : null}
            </section>
          );
        })
      )}

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">학교 밖 식당</h2>
          <StaleBadge state={nearby} />
        </div>

        <NearbyRestaurants restaurants={nearby.data} degraded={nearby.degraded} />

        <p className="card__note">
          성심관 기준입니다. 학교가 준 자료가 아니라 Kakao Local 검색 결과예요.
        </p>
      </section>
    </>
  );
}
