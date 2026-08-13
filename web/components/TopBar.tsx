import SearchBar from './SearchBar';

export default function TopBar({
  title,
  subtitle,
  query,
}: {
  title: string;
  subtitle?: string;
  query?: string;
}) {
  return (
    <header className="topbar">
      <h1 className="topbar__title">
        {title}
        {subtitle ? <small>{subtitle}</small> : null}
      </h1>
      {/* key 를 검색어로 둔다. /search?q=A 에서 추천 검색어를 눌러 ?q=B 로 가면
          같은 라우트라 이 컴포넌트가 다시 마운트되지 않는데, 검색창은 처음 값만
          들고 있어서 결과는 B 인데 입력창에는 A 가 남아 있었다. */}
      <SearchBar key={query ?? ''} initialQuery={query} />
    </header>
  );
}
