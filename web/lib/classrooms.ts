const SEOUL_TIME_ZONE = 'Asia/Seoul';
const WEEKDAYS = new Set(['Mon', 'Tue', 'Wed', 'Thu', 'Fri']);

export const CLASSROOM_USE_WINDOW_LABEL = '평일 오전 9시~오후 10시';

/**
 * 공식 강의실 대여 안내의 기본 이용 시간 안인지 확인한다.
 *
 * API가 계산에 사용한 evaluated_at을 기준으로 삼아 서버 렌더와 브라우저가
 * 같은 상태를 보여준다. 값이 깨졌을 때는 유효한 결과까지 숨기지 않는다.
 */
export function isWithinClassroomUseWindow(evaluatedAt: string): boolean {
  const date = new Date(evaluatedAt);
  if (Number.isNaN(date.getTime())) return true;

  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: SEOUL_TIME_ZONE,
    weekday: 'short',
    hour: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const weekday = parts.find((part) => part.type === 'weekday')?.value;
  const hour = Number(parts.find((part) => part.type === 'hour')?.value);
  if (!weekday || Number.isNaN(hour)) return true;

  return WEEKDAYS.has(weekday) && hour >= 9 && hour < 22;
}
