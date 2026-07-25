import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';

import TabBar from '@/components/TabBar';
import './globals.css';

export const metadata: Metadata = {
  title: '성심교정 도우미',
  description:
    '가톨릭대학교 성심교정 학생을 위한 캠퍼스 안내. 학식, 도서관 좌석, 빈 강의실, 공지, 건물과 연락처를 한 곳에서.',
  applicationName: '성심교정 도우미',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f6f5f2' },
    { media: '(prefers-color-scheme: dark)', color: '#14171a' },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <div className="shell">{children}</div>
        <TabBar />
      </body>
    </html>
  );
}
