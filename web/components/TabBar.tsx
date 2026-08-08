'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

// 이모지는 기기마다 다르게 렌더된다. 학식(🍚)이 회색 원으로 보이는 기기가 있었고,
// 학교 결에 맞춘 정돈된 화면에서도 튀었다. 글자만으로도 다섯 개는 충분히 구분된다.
const TABS = [
  { href: '/', label: '홈' },
  { href: '/dining', label: '학식' },
  { href: '/study', label: '공부' },
  { href: '/notices', label: '공지' },
  { href: '/find', label: '찾기' },
];

export default function TabBar() {
  const pathname = usePathname();

  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => {
        const active = tab.href === '/' ? pathname === '/' : pathname.startsWith(tab.href);
        return (
          <Link key={tab.href} href={tab.href} aria-current={active ? 'page' : undefined}>
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
