import type { MetadataRoute } from 'next';

/**
 * 홈 화면에 추가했을 때 앱처럼 열리게 한다.
 *
 * service worker 는 두지 않는다. 공지나 좌석처럼 지금 값이 중요한 데이터를
 * 오프라인 캐시로 굳혀 보여주면 "없는 값은 만들지 않는다"는 원칙이 깨진다.
 * 잠든 백엔드 대응은 서버 쪽 ISR 캐시가 맡는다.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: '성심교정 도우미',
    short_name: '성심교정',
    description: '가톨릭대학교 성심교정 학식, 도서관 좌석, 빈 강의실, 공지, 건물과 연락처',
    start_url: '/',
    display: 'standalone',
    background_color: '#f6f5f2',
    theme_color: '#17527d',
    lang: 'ko',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  };
}
