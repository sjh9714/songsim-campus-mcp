import 'server-only';

import type {
  AffiliatedNotice,
  CampusDiningMenu,
  Course,
  EstimatedEmptyClassroomResponse,
  LibrarySeatStatusResponse,
  Notice,
  NoticeCategoryInfo,
  PCSoftwareEntry,
  PhoneBookEntry,
  Place,
} from './types';

const BASE = (process.env.SONGSIM_API_BASE ?? 'http://127.0.0.1:8000').replace(/\/+$/, '');

/** DB만 읽는 엔드포인트의 제한시간. 이보다 오래 걸리면 백엔드가 잠든 것으로 본다. */
const TIMEOUT_MS = Number(process.env.SONGSIM_API_TIMEOUT_MS ?? 5000);

/**
 * 백엔드가 외부 서버로 실시간 조회를 하는 엔드포인트의 제한시간.
 * /library-seats 는 도서관 좌석 서버를 직접 찌르기 때문에 정상 응답에도 8초 안팎이 걸린다.
 * 이런 엔드포인트는 Suspense 로 분리해서 페이지 전체를 붙잡지 않게 한다.
 */
const LIVE_TIMEOUT_MS = Number(process.env.SONGSIM_API_LIVE_TIMEOUT_MS ?? 15000);

/**
 * 캐시 수명(초). 데이터가 실제로 얼마나 자주 변하는지에 맞춘다.
 * Render 무료 플랜 백엔드는 15분 무요청이면 잠들기 때문에,
 * 학생이 잠든 백엔드를 기다리는 일이 없도록 넉넉히 잡는다.
 *
 * 다만 상한을 1시간으로 둔다. 백엔드가 동기화 사고 등으로 "성공적으로 빈 배열"을
 * 돌려주면 그 빈 결과도 그대로 캐시되기 때문이다. 건물 목록처럼 거의 변하지 않는
 * 데이터라도 하루씩 잡아두면 잘못된 빈 화면이 하루 동안 굳는다.
 * 콜드 스타트를 막는 데는 몇 분이면 충분하므로 길게 잡을 이유가 없다.
 */
export const TTL = {
  dining: 3600,
  notices: 600,
  places: 3600,
  phoneBook: 3600,
  courses: 3600,
  pcSoftware: 3600,
  librarySeats: 60,
  classrooms: 300,
} as const;

export interface Fetched<T> {
  data: T;
  /** 백엔드에서 새 값을 받지 못했다. */
  degraded: boolean;
  /** degraded 상태에서 직전에 성공했던 응답을 대신 보여주고 있다. */
  servedFromSnapshot: boolean;
  /** servedFromSnapshot 일 때, 그 응답을 받았던 시각. */
  snapshotAt: string | null;
}

/**
 * 마지막으로 성공한 응답을 프로세스 메모리에 들고 있는다.
 *
 * Next 의 fetch 캐시는 재검증이 실패하면 빈 결과를 그대로 캐시에 밀어 넣는다.
 * 백엔드가 잠깐 죽었다는 이유로 멀쩡하던 화면이 통째로 비는 것을 막으려고
 * 마지막 성공값을 따로 붙잡아 둔다. 인스턴스가 살아 있는 동안만 유지되는
 * best-effort 계층이고, 없는 값을 만들어내지는 않는다.
 */
const lastGood = new Map<string, { data: unknown; at: string }>();

function buildUrl(path: string, params?: Record<string, string | number | undefined | null>): string {
  const url = new URL(BASE + path);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function getJson<T>(
  path: string,
  options: {
    revalidate: number;
    fallback: T;
    params?: Record<string, string | number | undefined | null>;
    /** 실시간 새로고침처럼 캐시를 건너뛰어야 할 때. */
    noStore?: boolean;
    /** 기본 제한시간을 덮어쓴다. 외부 실시간 조회를 하는 엔드포인트용. */
    timeoutMs?: number;
  },
): Promise<Fetched<T>> {
  const url = buildUrl(path, options.params);

  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(options.timeoutMs ?? TIMEOUT_MS),
      headers: { accept: 'application/json' },
      ...(options.noStore
        ? { cache: 'no-store' as const }
        : { next: { revalidate: options.revalidate } }),
    });

    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }

    const data = (await response.json()) as T;
    lastGood.set(url, { data, at: new Date().toISOString() });
    return { data, degraded: false, servedFromSnapshot: false, snapshotAt: null };
  } catch (error) {
    console.warn(`[songsim] ${url} 호출 실패:`, error instanceof Error ? error.message : error);

    const snapshot = lastGood.get(url);
    if (snapshot) {
      return {
        data: snapshot.data as T,
        degraded: true,
        servedFromSnapshot: true,
        snapshotAt: snapshot.at,
      };
    }

    return { data: options.fallback, degraded: true, servedFromSnapshot: false, snapshotAt: null };
  }
}

// --- 홈 카드 4종 ---------------------------------------------------------

export function getDiningMenus(limit = 10) {
  return getJson<CampusDiningMenu[]>('/dining-menus', {
    revalidate: TTL.dining,
    fallback: [],
    params: { limit },
  });
}

export function getLibrarySeats(options: { fresh?: boolean } = {}) {
  return getJson<LibrarySeatStatusResponse>('/library-seats', {
    revalidate: TTL.librarySeats,
    noStore: options.fresh,
    timeoutMs: LIVE_TIMEOUT_MS,
    fallback: {
      availability_mode: 'unavailable',
      checked_at: '',
      note: null,
      source_url: null,
      rooms: [],
    },
  });
}

export function getEmptyClassrooms(building: string, limit = 10) {
  return getJson<EstimatedEmptyClassroomResponse | null>('/classrooms/empty', {
    revalidate: TTL.classrooms,
    fallback: null,
    params: { building, limit },
  });
}

export function getNotices(options: { category?: string; limit?: number } = {}) {
  return getJson<Notice[]>('/notices', {
    revalidate: TTL.notices,
    fallback: [],
    params: { category: options.category, limit: options.limit ?? 10 },
  });
}

export function getNoticeCategories() {
  return getJson<NoticeCategoryInfo[]>('/notice-categories', {
    revalidate: TTL.places,
    fallback: [],
  });
}

export function getAffiliatedNotices(options: { topic?: string; limit?: number } = {}) {
  return getJson<AffiliatedNotice[]>('/affiliated-notices', {
    revalidate: TTL.notices,
    fallback: [],
    params: { topic: options.topic, limit: options.limit ?? 10 },
  });
}

// --- 찾기 / 검색 ---------------------------------------------------------

export function getPlaces(options: { query?: string; category?: string; limit?: number } = {}) {
  return getJson<Place[]>('/places', {
    revalidate: TTL.places,
    fallback: [],
    params: { query: options.query ?? '', category: options.category, limit: options.limit ?? 10 },
  });
}

export function getBuildings(limit = 50) {
  return getPlaces({ category: 'building', limit });
}

export function getPhoneBook(options: { query?: string; limit?: number } = {}) {
  return getJson<PhoneBookEntry[]>('/phone-book', {
    revalidate: TTL.phoneBook,
    fallback: [],
    params: { query: options.query, limit: options.limit ?? 20 },
  });
}

export function getCourses(options: { query?: string; limit?: number } = {}) {
  return getJson<Course[]>('/courses', {
    revalidate: TTL.courses,
    fallback: [],
    params: { query: options.query ?? '', limit: options.limit ?? 20 },
  });
}

export function getPcSoftware(options: { query?: string; limit?: number } = {}) {
  return getJson<PCSoftwareEntry[]>('/pc-software', {
    revalidate: TTL.pcSoftware,
    fallback: [],
    params: { query: options.query, limit: options.limit ?? 20 },
  });
}
