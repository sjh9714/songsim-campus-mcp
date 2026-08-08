import Link from 'next/link';
import type { ReactNode } from 'react';

export default function Card({
  title,
  href,
  moreLabel = '더보기',
  action,
  children,
  note,
}: {
  title: string;
  href?: string;
  moreLabel?: string;
  action?: ReactNode;
  children: ReactNode;
  note?: ReactNode;
}) {
  const isExternal = Boolean(href && /^https?:\/\//.test(href));

  return (
    <section className="card">
      <div className="card__head">
        <h2 className="card__title">{title}</h2>
        {action ??
          (href ? (
            // 앱이 답하지 않는 것들은 학교로 내보낸다. 그때는 새 탭으로 열어
            // 학생이 보던 자리를 잃지 않게 한다.
            isExternal ? (
              <a className="card__more" href={href} target="_blank" rel="noreferrer">
                {moreLabel} ↗
              </a>
            ) : (
              <Link className="card__more" href={href}>
                {moreLabel} ›
              </Link>
            )
          ) : null)}
      </div>
      {children}
      {note ? <p className="card__note">{note}</p> : null}
    </section>
  );
}
