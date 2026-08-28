import type { Place } from './types';

export const OFFICIAL_CAMPUS_MAP_URL =
  'https://www.catholic.ac.kr/ko/about/campus-map.do';

const BUILDING_CODE_PATTERN = /^[A-Z]{1,3}관$/;

/**
 * 강의실 코드와 같이 쓰는 건물 약어만 고른다.
 *
 * 학생회관, 학생식당 같은 검색용 alias를 목록에 모두 늘어놓지 않고,
 * K관·NP관처럼 행동에 도움이 되는 코드만 노출한다.
 */
export function placeBuildingCode(place: Place): string | null {
  const candidates = [place.name, ...place.aliases];
  return candidates.find((value) => BUILDING_CODE_PATTERN.test(value.trim()))?.trim() ?? null;
}

export function placeCanonicalName(place: Place): string {
  return place.canonical_name?.trim() || place.name.trim();
}

export function placeBuildingLabel(place: Place): string {
  const name = placeCanonicalName(place);
  const code = placeBuildingCode(place);
  return code ? `${name}(${code})` : name;
}

export function placeDetailHref(place: Place, query?: string): string {
  const pathname = `/find/${encodeURIComponent(place.slug)}`;
  const normalizedQuery = query?.trim();
  return normalizedQuery ? `${pathname}?q=${encodeURIComponent(normalizedQuery)}` : pathname;
}

function hasCoordinates(place: Place): place is Place & {
  latitude: number;
  longitude: number;
} {
  return (
    place.latitude !== null &&
    place.longitude !== null &&
    Number.isFinite(place.latitude) &&
    Number.isFinite(place.longitude) &&
    place.latitude >= -90 &&
    place.latitude <= 90 &&
    place.longitude >= -180 &&
    place.longitude <= 180
  );
}

export function kakaoMapHref(place: Place, label = placeCanonicalName(place)): string {
  const encodedLabel = encodeURIComponent(label.trim() || placeCanonicalName(place));
  if (!hasCoordinates(place)) {
    return `https://map.kakao.com/link/search/${encodedLabel}`;
  }
  return `https://map.kakao.com/link/map/${encodedLabel},${place.latitude},${place.longitude}`;
}

export function kakaoDirectionsHref(
  place: Place,
  label = placeCanonicalName(place),
): string | null {
  if (!hasCoordinates(place)) return null;
  const encodedLabel = encodeURIComponent(label.trim() || placeCanonicalName(place));
  return `https://map.kakao.com/link/to/${encodedLabel},${place.latitude},${place.longitude}`;
}

export function placeHasCoordinates(place: Place): place is Place & {
  latitude: number;
  longitude: number;
} {
  return hasCoordinates(place);
}
