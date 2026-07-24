import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 상위 디렉터리에 다른 lockfile이 있어도 web/ 을 워크스페이스 루트로 고정한다.
  outputFileTracingRoot: dirname(fileURLToPath(import.meta.url)),
  // 백엔드가 잠들어 있어도 빌드가 실패하지 않도록, 데이터는 전부 런타임에서만 가져온다.
  experimental: {
    staleTimes: {
      dynamic: 30,
      static: 300,
    },
  },
};

export default nextConfig;
