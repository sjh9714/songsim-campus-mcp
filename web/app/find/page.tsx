import Link from 'next/link';

import EmptyState from '@/components/EmptyState';
import PlaceIdentity from '@/components/PlaceIdentity';
import PhoneLinks from '@/components/PhoneLinks';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getPhoneBook, getPlaces, requireFreshOrKeepLastPage } from '@/lib/api';
import { placeDetailHref } from '@/lib/places';
import type { Place } from '@/lib/types';

// 데이터 캐시(TTL.places, TTL.phoneBook)가 1시간이다. 화면만 하루씩 붙잡아 두면
// 학교가 전화번호를 고쳐도 학생은 하루 동안 옛 번호를 본다. 같은 주기로 맞춘다.
export const revalidate = 3600;

function PlaceList({ places }: { places: Place[] }) {
  return (
    <ul className="list place-list">
      {places.map((place) => (
        <li key={place.id}>
          <Link
            className="place-link"
            href={placeDetailHref(place)}
            aria-label={`${place.canonical_name ?? place.name} 위치 보기`}
          >
            <PlaceIdentity place={place} />
            <span className="place-link__action">위치 보기</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default async function FindPage() {
  const [places, phones] = await Promise.all([
    getPlaces({ limit: 50 }),
    getPhoneBook({ limit: 50 }),
  ]);
  requireFreshOrKeepLastPage(places, '캠퍼스 장소 목록');

  const buildings = places.data.filter((place) => place.category === 'building');
  const otherPlaces = places.data.filter((place) => place.category !== 'building');

  return (
    <>
      <TopBar title="찾기" subtitle="건물, 시설, 부서 전화번호" />

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">건물</h2>
          <StaleBadge state={places} />
        </div>
        {buildings.length === 0 ? (
          <EmptyState degraded={places.degraded} message="등록된 건물이 없어요." />
        ) : (
          <PlaceList places={buildings} />
        )}
      </section>

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">다른 캠퍼스 장소</h2>
        </div>
        {otherPlaces.length === 0 ? (
          <EmptyState degraded={places.degraded} message="등록된 장소가 없어요." />
        ) : (
          <PlaceList places={otherPlaces} />
        )}
      </section>

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">부서 전화번호</h2>
          <StaleBadge state={phones} />
        </div>
        {phones.data.length === 0 ? (
          <EmptyState degraded={phones.degraded} message="등록된 전화번호가 없어요." />
        ) : (
          <ul className="list">
            {phones.data.map((entry) => (
              <li key={entry.id} className="row--split phone-row">
                <span>
                  <span className="row__title">{entry.department}</span>
                  {entry.tasks ? <span className="row__sub">{entry.tasks}</span> : null}
                </span>
                <PhoneLinks phone={entry.phone} contacts={entry.phone_contacts} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
