import type { MetadataRoute } from 'next';

/**
 * 검색 화면만 크롤링에서 뺀다.
 *
 * 홈과 검색 결과 화면에는 /search?q=... 로 가는 추천 검색어 링크가 실제 <a> 로
 * 깔려 있다. 이 화면만 동적 라우트라 요청마다 백엔드를 부르는데, 크롤러가 그
 * 링크를 따라다니면 잠든 무료 플랜 백엔드를 계속 깨우게 된다. 학생이 직접
 * 검색해서 들어오는 화면이지 검색엔진이 훑을 화면은 아니다.
 *
 * 나머지 화면은 프리렌더라 크롤링해도 백엔드에 부담이 없고, 학생이 검색으로
 * 찾아올 수 있어야 하므로 열어 둔다.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: '/search',
    },
  };
}
