'use client';

import EmptyState from './EmptyState';
import StaleBadge from './StaleBadge';
import Card from './Card';
import type { Fetched } from '@/lib/api';
import { formatAgo } from '@/lib/format';
import { useNow } from '@/lib/use-now';
import { useLiveData } from '@/lib/use-live-data';
import { isRecent, LIVE_MAX_AGE_MS } from '@/lib/live-state';
import type { LibrarySeatStatus, LibrarySeatStatusResponse } from '@/lib/types';

// XML 데이터 주소는 브라우저에서 내용이 보이지 않는다. 카드 아래의 전체 현황은
// 학교 도서관이 따로 제공하는 사람용 화면으로 보내고, 방 이름은 API의 좌석 맵을 쓴다.
const LIBRARY_SEAT_STATUS_PAGE_URL =
  'https://mlibrary.catholic.ac.kr/mobile/PA/roomStatus.php';

function RoomMapLink({
  room,
  compact = false,
}: {
  room: LibrarySeatStatus;
  compact?: boolean;
}) {
  const label = compact ? (
    <span className="row__sub">{room.room_name}</span>
  ) : (
    <>
      <span className="row__title">{room.room_name}</span>
      {room.total_seats !== null ? (
        <span className="row__sub">전체 {room.total_seats}석</span>
      ) : null}
    </>
  );

  if (!room.map_url) {
    return <span>{label}</span>;
  }

  return (
    <a
      className={`room-map-link${compact ? ' room-map-link--compact' : ''}`}
      href={room.map_url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${room.room_name} 좌석 맵 열기 (새 탭)`}
    >
      {label}
    </a>
  );
}

/**
 * 도서관 좌석 카드.
 *
 * 백엔드가 도서관 서버로 실시간 조회를 하기 때문에 정상 응답에도 8초 안팎이 걸린다.
 * 그래서 이 카드만 Suspense 경계 안에 두고, 나머지 화면은 먼저 그린다.
 */
export default function LibrarySeatsView({ initial, compact = false }: { initial: Fetched<LibrarySeatStatusResponse>; compact?: boolean }) {
  const { state: seats, loading, refresh } = useLiveData('kind=library-seats', initial);
  const now = useNow();
  const usable = isRecent(seats.data.checked_at, now, LIVE_MAX_AGE_MS)
    && seats.data.availability_mode === 'live' && !seats.degraded;
  const rooms = seats.data.rooms;
  const withSeats = rooms.filter((room) => room.remaining_seats !== null);
  const totalRemaining = withSeats.reduce((sum, room) => sum + (room.remaining_seats ?? 0), 0);

  // 좌석을 못 받았을 때 백엔드 note 는 "확인하지 못했습니다" 로, 아래 빈 상태와 같은 말이다.
  // 셋이 겹쳐 같은 문장이 세 번 나오던 것을 정리한다. note 가 값을 더 설명할 때만 남긴다.
  const note = (
    <>
      {seats.data.checked_at && now !== null ? <time dateTime={seats.data.checked_at}>{formatAgo(seats.data.checked_at, now)} 확인</time> : null}
      {seats.data.availability_mode === 'stale_cache'
        ? ' · 실시간 조회에 실패해 직전에 받아둔 값이에요.'
        : null}
      {rooms.length > 0 && seats.data.note ? ` · ${seats.data.note}` : null}
    </>
  );

  const body =
    !usable || rooms.length === 0 ? (
      <EmptyState
        message={loading || now === null ? '현재 좌석을 확인하고 있어요.' : '현재 좌석 수를 확인하지 못했어요.'}
        hint="오래된 좌석 수는 현재 현황으로 표시하지 않아요. 공식 현황에서도 확인할 수 있어요."
      />
    ) : compact ? (
      <>
        <div className="row--split" style={{ marginBottom: 10 }}>
          <span className="row__title">지금 남은 자리</span>
          <span className="row__value">{totalRemaining}석</span>
        </div>
        <ul className="list">
          {withSeats.slice(0, 3).map((room) => (
            <li key={room.room_name} className="row--split">
              <RoomMapLink room={room} compact />
              <span className="row__value">{room.remaining_seats}석 남음</span>
            </li>
          ))}
        </ul>
      </>
    ) : (
      <ul className="list">
        {rooms.map((room) => (
          <li key={room.room_name} className="row--split">
            <RoomMapLink room={room} />
            <span className="row__value">
              {room.remaining_seats !== null ? `${room.remaining_seats}석 남음` : '—'}
            </span>
          </li>
        ))}
      </ul>
    );

  const controls = <div className="live-controls">
    <button type="button" className="chip" disabled={loading} onClick={refresh}>{loading ? '확인 중…' : '새로고침'}</button>
    <a className="linkout" href={LIBRARY_SEAT_STATUS_PAGE_URL} target="_blank" rel="noreferrer">공식 좌석 현황 페이지 ›</a>
  </div>;

  if (compact) {
    // "빈 강의실도 보기" 로 두면 좌석 카드인데 링크가 딴 데를 가리켜,
    // 좌석을 더 보려는 학생이 갈 곳을 잃는다. /study 에 둘 다 있으므로 그렇게 적는다.
    return (
      <Card title="도서관 좌석" href="/study" moreLabel="좌석·빈 강의실" note={note}>
        {body}
        {controls}
      </Card>
    );
  }

  return (
    <Card title="도서관 좌석" action={<StaleBadge state={seats} />} note={note}>
      {body}
      {controls}
    </Card>
  );
}
