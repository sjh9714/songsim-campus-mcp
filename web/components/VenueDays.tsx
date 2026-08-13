'use client';

import { useState } from 'react';

import DayMenu from './DayMenu';
import { formatDate } from '@/lib/format';
import type { CampusDiningDay } from '@/lib/types';

/**
 * 식당 한 곳의 요일 선택과 그날 메뉴.
 *
 * 예전에는 /dining?day= 로 이동해서 골랐다. 그러면 이 화면이 searchParams 를 읽는
 * 동적 라우트가 되어 ISR 캐시가 붙지 않았고, 백엔드가 잠들어 있으면 학생이
 * 타임아웃을 그대로 기다렸다. 게다가 day 가 주소에 하나뿐이라 한 식당에서 요일을
 * 바꾸면 다른 식당까지 같이 바뀌었다. 식당마다 따로 들고 있는 게 맞다.
 */
export default function VenueDays({ days, today }: { days: CampusDiningDay[]; today: string }) {
  // 주말이면 오늘이 주간 표에 없다. 그때는 다가오는 첫날을 보여준다.
  const initial = days.find((item) => item.date >= today) ?? days[0];
  const [date, setDate] = useState(initial.date);
  const selected = days.find((item) => item.date === date) ?? initial;

  return (
    <>
      <div className="daypicker">
        {days.map((item) => (
          <button
            key={item.date}
            type="button"
            className="chip"
            aria-pressed={item.date === selected.date}
            onClick={() => setDate(item.date)}
          >
            {item.weekday}
            {item.date === today ? ' · 오늘' : ''}
          </button>
        ))}
      </div>
      <div className="row__sub" style={{ marginTop: 10 }}>
        {formatDate(selected.date)} ({selected.weekday})
      </div>
      <DayMenu day={selected} />
    </>
  );
}
