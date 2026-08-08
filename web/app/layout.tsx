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
  // 학교 사이트와 같이 라이트 전용이다. 다크 변형을 두지 않는다.
  themeColor: '#ffffff',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <div className="shell">
          {children}
          {/* 학교 사이트와 결을 맞췄기 때문에 공식 서비스로 오해할 수 있다.
              공지를 그대로 싣고 있어서 더 그렇다. 그래서 상시 밝혀 둔다. */}
          <footer className="disclaimer">
            <strong>비공식 학생 프로젝트입니다.</strong> 가톨릭대학교가 만들거나 운영하는 서비스가
            아니며, 학교가 공개한 정보를 모아서 보여줍니다. 중요한 내용은 각 화면의 학교 원문
            링크에서 다시 확인해 주세요.
          </footer>
        </div>
        <TabBar />
      </body>
    </html>
  );
}
