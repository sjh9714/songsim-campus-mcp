'use client';

import Link from 'next/link';

import EmptyState from '@/components/EmptyState';
import TopBar from '@/components/TopBar';

/**
 * 화면을 그리다 예상 못 한 오류가 났을 때.
 *
 * 없으면 Next 기본 오류 화면이 나오는데, 검은 배경에 영문이라 학생 입장에서는
 * 사이트가 통째로 깨진 것처럼 보인다. 여기서 다시 시도할 길과 돌아갈 길을 준다.
 */
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <>
      <TopBar title="잠시 문제가 생겼어요" subtitle="이 화면을 그리지 못했어요" />
      <section className="card">
        <EmptyState
          message="화면을 불러오다 문제가 생겼어요."
          hint="다시 시도해 보고, 계속 이러면 잠시 뒤에 열어봐 주세요."
        />
        <div className="chips">
          <button type="button" className="chip" onClick={reset}>
            다시 시도
          </button>
          <Link className="chip" href="/">
            홈으로
          </Link>
        </div>
      </section>
    </>
  );
}
