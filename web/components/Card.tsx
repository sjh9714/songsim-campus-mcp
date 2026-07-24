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
  return (
    <section className="card">
      <div className="card__head">
        <h2 className="card__title">{title}</h2>
        {action ?? (href ? (
          <Link className="card__more" href={href}>
            {moreLabel} ›
          </Link>
        ) : null)}
      </div>
      {children}
      {note ? <p className="card__note">{note}</p> : null}
    </section>
  );
}
