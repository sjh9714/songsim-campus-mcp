export default function CardSkeleton({ title }: { title: string }) {
  return (
    <section className="card">
      <div className="card__head">
        <h2 className="card__title">{title}</h2>
        <span className="badge">불러오는 중</span>
      </div>
      <div className="empty">잠시만요…</div>
    </section>
  );
}
