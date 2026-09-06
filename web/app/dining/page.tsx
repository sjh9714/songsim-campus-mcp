import DiningVenues from '@/components/DiningVenues';
import EmptyState from '@/components/EmptyState';
import NearbyRestaurants from '@/components/NearbyRestaurants';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getDiningMenus, getNearbyRestaurants, requireFreshOrKeepLastPage } from '@/lib/api';

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
        <DiningVenues dining={dining} />
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
