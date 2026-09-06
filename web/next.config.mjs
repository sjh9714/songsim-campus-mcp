import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 상위 디렉터리에 다른 lockfile이 있어도 web/ 을 워크스페이스 루트로 고정한다.
  outputFileTracingRoot: dirname(fileURLToPath(import.meta.url)),
  // Static shells use ISR; time-sensitive labels and availability are rechecked in the browser.
  experimental: {
    staleTimes: {
      dynamic: 30,
      static: 300,
    },
  },
};

export default nextConfig;
