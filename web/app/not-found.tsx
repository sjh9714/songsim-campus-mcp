import Link from 'next/link';

import EmptyState from '@/components/EmptyState';
import TopBar from '@/components/TopBar';

/**
 * 없는 주소로 들어왔을 때.
 *
 * Next 기본 404 는 검은 화면에 영문 한 줄이라 이 사이트와 아무 관계 없어 보인다.
 * 공지 화면을 없앤 적이 있어서 /notices 를 북마크해 둔 학생은 여기로 온다.
 * 막다른 길로 두지 않고 매일 쓰는 화면으로 되돌려 보낸다.
 */
export default function NotFound() {
  return (
    <>
      <TopBar title="없는 화면이에요" subtitle="주소가 바뀌었거나 사라졌어요" />
      <section className="card">
        <EmptyState
          message="찾으시는 화면이 없어요."
          hint="주소가 바뀌었을 수 있어요. 아래에서 골라 주세요."
        />
        <div className="chips">
          <Link className="chip" href="/">
            홈
          </Link>
          <Link className="chip" href="/dining">
            학식
          </Link>
          <Link className="chip" href="/study">
            공부
          </Link>
          <Link className="chip" href="/find">
            찾기
          </Link>
        </div>
        {/* 공지 화면은 없앴다. 그걸 찾아온 학생은 학교 공지사항으로 보낸다. */}
        <a
          className="linkout"
          href="https://www.catholic.ac.kr/ko/campuslife/notice.do"
          target="_blank"
          rel="noreferrer"
        >
          학교 공지사항 ↗
        </a>
      </section>
    </>
  );
}
