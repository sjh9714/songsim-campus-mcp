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
      <SearchBar initialQuery={query} />
    </header>
  );
}
