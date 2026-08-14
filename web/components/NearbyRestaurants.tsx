import EmptyState from './EmptyState';
import type { NearbyRestaurant } from '@/lib/types';

/**
 * 학교 밖 식당 목록.
 *
 * 가격(min_price, max_price)과 영업 여부(open_now)는 응답에 자리는 있지만
 * Kakao Local 이 채워 주지 않아 지금은 전부 null 이다. 없는 값을 "정보 없음"
 * 으로 줄 세우면 화면만 길어지므로 싣지 않는다. 값이 실제로 들어오기
 * 시작하면 그때 붙인다.
 */
export default function NearbyRestaurants({
  restaurants,
  degraded,
}: {
  restaurants: NearbyRestaurant[];
  degraded: boolean;
}) {
  if (restaurants.length === 0) {
    return <EmptyState degraded={degraded} message="주변 식당을 찾지 못했어요." />;
  }

  return (
    <ul className="list">
      {restaurants.map((restaurant) => (
        <li key={restaurant.slug} className="row--split">
          <span>
            <span className="row__title">{restaurant.name}</span>
            <span className="row__sub">{tagLabel(restaurant) ?? restaurant.description}</span>
          </span>
          <span className="row__sub">{walkLabel(restaurant)}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * 태그 한 줄. 없으면 null 을 주고 부르는 쪽이 주소로 대신한다.
 *
 * Kakao 가 주는 태그 하나 안에 이미 쉼표가 들어 있다("육류,고기"). 그대로 이으면
 * "육류,고기, 삼겹살" 처럼 간격이 들쭉날쭉해 오타로 보인다. 쉼표로 한 번 더 풀어서
 * 같은 간격으로 맞춘다.
 */
function tagLabel(restaurant: NearbyRestaurant): string | null {
  const tags = restaurant.tags
    .flatMap((tag) => tag.split(','))
    .map((tag) => tag.trim())
    .filter(Boolean);
  return tags.length > 0 ? [...new Set(tags)].join(', ') : null;
}

/** 도보 시간이 없으면 거리라도 준다. 둘 다 없으면 아무 말도 하지 않는다. */
function walkLabel(restaurant: NearbyRestaurant): string | null {
  if (restaurant.estimated_walk_minutes !== null) {
    return `도보 ${restaurant.estimated_walk_minutes}분`;
  }
  if (restaurant.distance_meters !== null) {
    return `${restaurant.distance_meters}m`;
  }
  return null;
}
