const KST = 'Asia/Seoul';

/** "2026-07-25T09:00:00+09:00" -> "7월 25일" */
export function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: KST,
    month: 'long',
    day: 'numeric',
  }).format(date);
}

/**
 * "2026-07-25T09:00:00+09:00" -> "오전 9:00"
 *
 * 오전/오후는 직접 붙인다. ko-KR 로케일에 맡기면 결과가 실행 환경마다 다르다.
 * Node 22 는 "PM 7:00" 을, 브라우저는 "오후 7:00" 을 낸다(CLDR 판 차이).
 * 서버에서 그린 글자와 하이드레이션 후 글자가 어긋나면 안 되고,
 * 애초에 학생에게 "PM 7:00" 을 보여주고 있었다.
 */
export function formatTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: KST,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(date);
  const hour = Number(parts.find((part) => part.type === 'hour')?.value);
  const minute = parts.find((part) => part.type === 'minute')?.value;
  if (Number.isNaN(hour) || minute === undefined) return null;

  return `${hour < 12 ? '오전' : '오후'} ${hour % 12 === 0 ? 12 : hour % 12}:${minute}`;
}

/** 지금으로부터 얼마나 지났는지. "방금", "12분 전", "3시간 전", "7월 20일" */
export function formatAgo(iso: string | null | undefined, now = Date.now()): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  const seconds = Math.floor((now - date.getTime()) / 1000);
  if (seconds < 0) return formatDate(iso);
  if (seconds < 60) return '방금';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간 전`;
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)}일 전`;
  return formatDate(iso);
}

/** 학교 기준(KST) 오늘 날짜. 서버가 어느 지역에서 렌더하든 같은 날을 가리켜야 한다. */
export function todayInSeoul(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: KST,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

/** 끼니 표시 순서. 학교 표의 이름을 그대로 쓰되 시간 순으로 정렬한다. */
const MEAL_ORDER = ['조식', '중식', '석식'];

export function sortMeals(meals: Record<string, unknown>): string[] {
  return Object.keys(meals).sort((a, b) => {
    const left = MEAL_ORDER.indexOf(a);
    const right = MEAL_ORDER.indexOf(b);
    return (left === -1 ? MEAL_ORDER.length : left) - (right === -1 ? MEAL_ORDER.length : right);
  });
}

/**
 * 요약이 제목을 그대로 되풀이하는 부분을 걷어낸다.
 *
 * 학교 공지는 본문 첫 줄이 제목과 같은 경우가 많아서, 그대로 두면 목록에서
 * 같은 문장을 두 번 읽게 된다. 겹치는 앞부분만 덜어내고 나머지를 남긴다.
 */
export function stripEchoedTitle(summary: string, title: string): string {
  const normalize = (value: string) => value.replace(/\s+/g, ' ').trim();
  const cleanSummary = normalize(summary);
  const cleanTitle = normalize(title);
  if (!cleanTitle) return cleanSummary;

  if (cleanSummary.startsWith(cleanTitle)) {
    const rest = cleanSummary.slice(cleanTitle.length).replace(/^[\s\-–—·:,.]+/, '');
    return rest || '';
  }
  return cleanSummary;
}

/** 긴 본문을 카드에 들어갈 길이로 자른다. */
export function truncate(text: string | null | undefined, limit: number): string {
  if (!text) return '';
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (normalized.length <= limit) return normalized;
  return normalized.slice(0, Math.max(0, limit - 1)).trimEnd() + '…';
}
