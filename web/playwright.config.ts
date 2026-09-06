import { defineConfig } from '@playwright/test';

// Next's fetch cache survives builds. A run-specific mock URL must not reuse an old fixture.
const fixtureBase = `http://127.0.0.1:8019/fixture-${Date.now()}`;

export default defineConfig({
  testDir: './tests/browser',
  workers: 2,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: 'http://127.0.0.1:3019', viewport: { width: 390, height: 844 }, trace: 'retain-on-failure' },
  webServer: [
    { command: 'node tests/mock-api.mjs', url: 'http://127.0.0.1:8019/healthz' },
    { command: 'npm run build && npm run start -- --port 3019', url: 'http://127.0.0.1:3019', timeout: 180_000,
      env: { SONGSIM_API_BASE: fixtureBase, SONGSIM_API_TIMEOUT_MS: '1000', NEXT_PUBLIC_KAKAO_MAP_JS_KEY: process.env.TEST_MAP_KEY ?? '' } },
  ],
});
