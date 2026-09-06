import Link from 'next/link';
import { notFound } from 'next/navigation';

import EmptyState from '@/components/EmptyState';
import KakaoStaticMap from '@/components/KakaoStaticMap';
import PlaceIdentity from '@/components/PlaceIdentity';
import PhoneLinks from '@/components/PhoneLinks';
import RefreshResults from '@/components/RefreshResults';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getPlace, getPlaces } from '@/lib/api';
import {
  kakaoDirectionsHref,
  kakaoMapHref,
  OFFICIAL_CAMPUS_MAP_URL,
  placeBuildingLabel,
  placeCanonicalName,
  placeHasCoordinates,
} from '@/lib/places';

export const revalidate = 3600;

export default async function PlaceDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ q?: string }>;
}) {
  const [{ slug }, rawSearchParams] = await Promise.all([params, searchParams]);
  const query = rawSearchParams.q?.trim();
  const [placeState, contextualPlaces] = await Promise.all([
    getPlace(slug),
    query ? getPlaces({ query, limit: 8 }) : Promise.resolve(null),
  ]);
  const place = placeState.data;

  if (!place) {
    if (!placeState.degraded) notFound();
    return (
      <>
        <TopBar title="위치 찾기" subtitle="캠퍼스 장소" />
        <section className="card">
          <EmptyState
            degraded={placeState.degraded}
            message="요청한 장소를 찾을 수 없어요."
            hint="찾기 목록이나 검색에서 장소를 다시 선택해 주세요."
          />
          <Link className="linkout" href="/find">
            찾기 목록으로
          </Link>
          <RefreshResults />
          <a className="linkout" href={OFFICIAL_CAMPUS_MAP_URL} target="_blank" rel="noreferrer">학교 전체 캠퍼스맵</a>
        </section>
      </>
    );
  }

  const contextualPlace = contextualPlaces?.data.find((item) => item.slug === place.slug);
  const facility = contextualPlace?.matched_facility ?? null;
  const destinationLabel = facility?.name ?? placeCanonicalName(place);
  const directionsHref = kakaoDirectionsHref(place, destinationLabel);
  const mapHref = kakaoMapHref(place, destinationLabel);
  const buildingLabel = placeBuildingLabel(place);
  const locationLine = facility?.location_hint
    ? `${facility.location_hint} · ${buildingLabel}`
    : null;
  const coordinateNote =
    place.category === 'building' || facility
      ? '학교 공식 캠퍼스맵의 건물 위치 기준입니다. 건물 입구와 실내 위치는 다를 수 있어요.'
      : '학교 공식 캠퍼스맵의 장소 위치 기준입니다. 실제 접근 동선은 다를 수 있어요.';

  return (
    <>
      <TopBar title="위치 찾기" subtitle={destinationLabel} query={query} />

      <section className="card place-detail">
        <div className="place-detail__back-row">
          <Link className="linkout place-detail__back" href="/find">
            찾기 목록으로
          </Link>
          <StaleBadge state={placeState} />
        </div>

        <div className="place-detail__identity">
          {facility ? (
            <h2 className="place-detail__title">{facility.name}</h2>
          ) : (
            <h2 className="place-detail__title">
              <PlaceIdentity place={place} className="place-detail__title-text" />
            </h2>
          )}
          {locationLine ? <p className="place-detail__location">{locationLine}</p> : null}
          {facility?.opening_hours ? (
            <p className="place-detail__meta">
              {facility.opening_hours}
            </p>
          ) : null}
          {facility?.phone ? <PhoneLinks phone={facility.phone} contacts={facility.phone_contacts} /> : null}
          {facility?.source_url ? <a className="linkout" href={facility.source_url} target="_blank" rel="noreferrer">시설 위치·이용 안내 원문 ›</a> : null}
        </div>

        {placeHasCoordinates(place) ? (
          <KakaoStaticMap
            latitude={place.latitude}
            longitude={place.longitude}
            label={destinationLabel}
          />
        ) : (
          <div className="place-map place-map--unavailable">
            학교 공식 좌표가 아직 없어 미니 지도를 표시할 수 없어요.
          </div>
        )}

        <p className="place-detail__note">{coordinateNote}</p>

        <div className="place-actions">
          {directionsHref ? (
            <a
              className="place-action place-action--primary"
              href={directionsHref}
              target="_blank"
              rel="noopener noreferrer"
            >
              카카오맵 길찾기
            </a>
          ) : null}
          <a
            className={`place-action${directionsHref ? '' : ' place-action--primary'}`}
            href={mapHref}
            target="_blank"
            rel="noopener noreferrer"
          >
            {directionsHref ? '카카오맵 크게 보기' : '카카오맵에서 찾기'}
          </a>
        </div>

        <a
          className="linkout"
          href={OFFICIAL_CAMPUS_MAP_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          학교 전체 캠퍼스맵
        </a>
      </section>
    </>
  );
}
