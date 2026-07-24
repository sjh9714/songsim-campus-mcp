'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const TABS = [
  { href: '/', label: '홈', icon: '🏠' },
  { href: '/dining', label: '학식', icon: '🍚' },
  { href: '/study', label: '공부', icon: '📚' },
  { href: '/notices', label: '공지', icon: '📢' },
  { href: '/find', label: '찾기', icon: '🔎' },
];

export default function TabBar() {
  const pathname = usePathname();

  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => {
        const active = tab.href === '/' ? pathname === '/' : pathname.startsWith(tab.href);
        return (
          <Link key={tab.href} href={tab.href} aria-current={active ? 'page' : undefined}>
            <span className="tabbar__icon" aria-hidden="true">
              {tab.icon}
            </span>
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
