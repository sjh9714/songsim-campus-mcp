import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-07T14:00:00+09:00') });
  await page.route('https://dapi.kakao.com/**', (route) => route.abort());
});

test('building code, facility and verified phone links complete the journey', async ({ page }) => {
  await page.goto('/find');
  const building = page.getByRole('link', { name: '김수환관 위치 보기' });
  await expect(building).toContainText('K관');
  await expect(page.locator('a[href="tel:02-2164-4160"]')).toBeVisible();
  await expect(page.locator('a[href="tel:02-740-9749"]')).toBeVisible();
  for (const query of ['K관', '김수환관', '카페 멘사', '보건실 어디야']) {
    await page.goto(`/search?q=${encodeURIComponent(query)}`);
    const name = query.includes('보건실') ? '보건실' : query.includes('멘사') ? '카페 멘사' : '김수환관';
    await page.getByRole('link', { name: `${name} 위치 보기` }).click();
    await expect(page.getByRole('link', { name: '카카오맵 길찾기', exact: true })).toHaveAttribute('href', new RegExp(`/to/${encodeURIComponent(name)},37\\.`));
    await expect(page.getByText('미니 지도를 불러오지 못했어요.', { exact: false })).toBeVisible({ timeout: 12_000 });
    if (name === '보건실') {
      await expect(page.getByText('비르투스관 1층 104호', { exact: false })).toBeVisible();
      await expect(page.locator('a[href="tel:02-2164-4126"]')).toBeVisible();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
});

test('missing coordinates, missing slug and partial API failure remain usable', async ({ page }) => {
  await page.goto('/find/no-coordinates');
  await expect(page.getByRole('link', { name: '카카오맵에서 찾기' })).toBeVisible();
  await expect(page.getByText('학교 공식 좌표가 아직 없어', { exact: false })).toBeVisible();
  await page.goto('/find/does-not-exist');
  await expect(page.getByText('요청한 장소를 찾을 수 없어요.')).toBeVisible();
  await page.goto(`/search?q=${encodeURIComponent('부분실패')}`);
  await expect(page.getByRole('status')).toContainText('일부 정보를 받지 못해');
  await expect(page.getByRole('link', { name: '김수환관 위치 보기' })).toBeVisible();
});

test('cached dining labels follow Seoul midnight and never call an old menu today', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '오늘의 학식' })).toBeVisible();
  await expect(page.getByText('월요일 테스트 메뉴')).toBeVisible();
  await page.clock.setSystemTime(new Date('2026-09-08T00:00:05+09:00'));
  await page.clock.runFor(15_001);
  await expect(page.getByText('화요일 테스트 메뉴')).toBeVisible();
  await expect(page.getByText('월요일 테스트 메뉴')).toHaveCount(0);
  await page.clock.setSystemTime(new Date('2026-09-09T00:00:05+09:00'));
  await page.clock.runFor(15_001);
  await expect(page.getByRole('heading', { name: '오늘의 학식' })).toHaveCount(0);
  await expect(page.getByText('오늘 이후로 정리된 메뉴가 없어요.')).toBeVisible();
});

test('live seats and estimated rooms expire; failures do not retain present-tense counts', async ({ page }) => {
  await page.goto('/study');
  await expect(page.getByRole('link', { name: '제1자유열람실A 좌석 맵 열기 (새 탭)' })).toBeVisible();
  await expect(page.getByText('42석', { exact: true })).toBeVisible();
  await expect(page.getByText('K106', { exact: true })).toBeVisible();
  await expect(page.getByText('지금은 공식 강의실 대여 시간 밖이에요.')).toHaveCount(0);
  await page.route('**/api/live?**', (route) => route.fulfill({ status: 503, body: '{}' }));
  await page.clock.runFor(75_001);
  await expect(page.getByText('42석', { exact: true })).toHaveCount(0);
  await expect(page.getByText('K106', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '공식 좌석 현황 페이지 ›' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test('slow live requests time out without a permanent spinner', async ({ page }) => {
  await page.route('**/api/live?**', () => { /* simulate an upstream that never responds */ });
  await page.goto('/study');
  await page.clock.runFor(56_000);
  await expect(page.getByText('현재 좌석 수를 확인하지 못했어요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '새로고침', exact: true }).first()).toBeEnabled();
});

test('map image success and image failure are distinguished after SDK load', async ({ page }) => {
  test.skip(!process.env.TEST_MAP_KEY, 'The separate key-missing run covers the no-SDK branch.');
  await page.route('https://dapi.kakao.com/**', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: `window.kakao = { maps: { load: (callback) => callback(), LatLng: class {}, StaticMap: class {
      constructor(container) { const image = document.createElement('img'); image.src = '/qa-map.svg'; container.appendChild(image); }
    } } };`,
  }));
  await page.route('**/qa-map.svg', (route) => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="gray"/></svg>' }));
  await page.goto('/find/kim-sou-hwan-hall');
  await expect(page.locator('.place-map__state')).toHaveCount(0);
  await page.route('**/qa-map.svg', (route) => route.abort());
  await page.reload();
  await expect(page.getByText('미니 지도를 불러오지 못했어요.', { exact: false })).toBeVisible();
  await expect(page.getByRole('link', { name: '카카오맵 길찾기', exact: true })).toBeVisible();
});
