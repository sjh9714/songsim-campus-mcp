import EmptyState from './EmptyState';
import StaleBadge from './StaleBadge';
import Card from './Card';
import { getLibrarySeats } from '@/lib/api';
import { formatAgo } from '@/lib/format';

/**
 * 도서관 좌석 카드.
 *
 * 백엔드가 도서관 서버로 실시간 조회를 하기 때문에 정상 응답에도 8초 안팎이 걸린다.
 * 그래서 이 카드만 Suspense 경계 안에 두고, 나머지 화면은 먼저 그린다.
 */
export default async function LibrarySeatsCard({ compact = false }: { compact?: boolean }) {
  const seats = await getLibrarySeats();
  const rooms = seats.data.rooms;
  const withSeats = rooms.filter((room) => room.remaining_seats !== null);
  const totalRemaining = withSeats.reduce((sum, room) => sum + (room.remaining_seats ?? 0), 0);

  // 좌석을 못 받았을 때 백엔드 note 는 "확인하지 못했습니다" 로, 아래 빈 상태와 같은 말이다.
  // 셋이 겹쳐 같은 문장이 세 번 나오던 것을 정리한다. note 가 값을 더 설명할 때만 남긴다.
  const note = (
    <>
      {seats.data.checked_at ? `${formatAgo(seats.data.checked_at)} 기준` : null}
      {seats.data.availability_mode === 'stale_cache'
        ? ' · 실시간 조회에 실패해 직전에 받아둔 값이에요.'
        : null}
      {rooms.length > 0 && seats.data.note ? ` · ${seats.data.note}` : null}
    </>
  );

  const body =
    rooms.length === 0 ? (
      <EmptyState
        degraded={seats.degraded}
        message="도서관 좌석 서버가 응답하지 않고 있어요."
        hint="잠시 후 다시 열어봐 주세요."
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
              <span className="row__sub">{room.room_name}</span>
              <span className="row__value">{room.remaining_seats}석</span>
            </li>
          ))}
        </ul>
      </>
    ) : (
      <ul className="list">
        {rooms.map((room) => (
          <li key={room.room_name} className="row--split">
            <span>
              <span className="row__title">{room.room_name}</span>
              {room.total_seats !== null ? (
                <span className="row__sub">전체 {room.total_seats}석</span>
              ) : null}
            </span>
            <span className="row__value">
              {room.remaining_seats !== null ? `${room.remaining_seats}석` : '—'}
            </span>
          </li>
        ))}
      </ul>
    );

  if (compact) {
    return (
      <Card title="도서관 좌석" href="/study" moreLabel="빈 강의실도 보기" note={note}>
        {body}
      </Card>
    );
  }

  return (
    <Card title="도서관 좌석" action={<StaleBadge state={seats} />} note={note}>
      {body}
      {seats.data.source_url ? (
        <a className="linkout" href={seats.data.source_url} target="_blank" rel="noreferrer">
          도서관 좌석 페이지 ›
        </a>
      ) : null}
    </Card>
  );
}
