import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/production',
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 60_000 },
  use: { baseURL: 'https://songsim-web.vercel.app', viewport: { width: 390, height: 844 }, trace: 'retain-on-failure' },
});
