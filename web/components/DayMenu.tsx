import type { CampusDiningDay } from '@/lib/types';
import { sortMeals } from '@/lib/format';

/**
 * 하루치 메뉴를 끼니별로 보여준다.
 *
 * 원본은 요일 x 끼니 표인데, PDF 텍스트를 그대로 펴면 5일치가 한 덩어리로 쏟아져
 * 어느 날 것인지 알 수 없었다. 학생이 알고 싶은 건 "오늘 뭐 나와?" 하나다.
 */
export default function DayMenu({
  day,
  compact = false,
}: {
  day: CampusDiningDay;
  /** 홈처럼 훑는 자리에서는 끼니마다 주 메뉴 한 줄만 보여준다. */
  compact?: boolean;
}) {
  const meals = sortMeals(day.meals);
  if (meals.length === 0) return null;

  // 홈에서 끼니마다 여섯 줄씩 펼치면 카드 하나가 첫 화면을 통째로 먹는다.
  // 학생이 훑을 때 필요한 건 "오늘 뭐가 메인이냐" 하나다.
  if (compact) {
    return (
      <ul className="daymenu daymenu--compact">
        {meals.map((meal) => {
          const value = day.meals[meal];
          return (
            <li className="row--split" key={meal}>
              <span>
                <span className="daymenu__name">{meal}</span>{' '}
                <span className="daymenu__main">{value.items[0]}</span>
              </span>
              {value.kcal ? <span className="daymenu__kcal">{value.kcal}kcal</span> : null}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div className="daymenu">
      {meals.map((meal) => {
        const value = day.meals[meal];
        return (
          <div className="daymenu__meal" key={meal}>
            <div className="daymenu__head">
              <span className="daymenu__name">{meal}</span>
              {value.kcal ? <span className="daymenu__kcal">{value.kcal}kcal</span> : null}
            </div>
            <ul className="daymenu__items">
              {value.items.map((item, index) => (
                // 같은 이름이 두 번 나올 수 있어(배추김치 등) 순서를 키에 섞는다.
                <li key={`${item}-${index}`} className={index === 0 ? 'daymenu__main' : undefined}>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
