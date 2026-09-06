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
  await expect(page.getByText('42석 남음', { exact: true })).toBeVisible();
  await expect(page.getByText('K106', { exact: true })).toBeVisible();
  await expect(page.getByText('지금은 공식 강의실 대여 시간 밖이에요.')).toHaveCount(0);
  await page.route('**/api/live?**', (route) => route.fulfill({ status: 503, body: '{}' }));
  await page.clock.runFor(75_001);
  await expect(page.getByText('42석 남음', { exact: true })).toHaveCount(0);
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

test('map redraws to the container width and retains image failure fallback after resize', async ({ page }) => {
  test.skip(!process.env.TEST_MAP_KEY, 'The separate key-missing run covers the no-SDK branch.');
  await page.route('https://dapi.kakao.com/**', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: `window.kakao = { maps: { load: (callback) => callback(), LatLng: class {}, StaticMap: class {
      constructor(container) { const image = document.createElement('img'); image.width = container.clientWidth; image.height = container.clientHeight; image.src = '/qa-map.svg?width=' + image.width; container.appendChild(image); }
    } } };`,
  }));
  await page.route('**/qa-map.svg?*', (route) => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="gray"/></svg>' }));
  await page.goto('/find/kim-sou-hwan-hall');
  await expect(page.locator('.place-map__state')).toHaveCount(0);
  for (const width of [360, 844, 1440, 390]) {
    await page.setViewportSize({ width, height: width === 844 ? 390 : 844 });
    await expect.poll(async () => {
      await page.clock.runFor(200);
      return page.locator('.place-map__canvas').evaluate((container) => {
        const image = container.querySelector('img');
        return image?.complete && image.naturalWidth > 0 && Math.abs(image.width - container.clientWidth) <= 1;
      });
    }).toBeTruthy();
    await expect(page.locator('.place-map__state')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
  await page.route('**/qa-map.svg?*', (route) => route.abort());
  await page.setViewportSize({ width: 400, height: 844 });
  await page.clock.runFor(500);
  await expect(page.getByText('미니 지도를 불러오지 못했어요.', { exact: false })).toBeVisible();
  await expect(page.getByRole('link', { name: '카카오맵 길찾기', exact: true })).toBeVisible();
});

test('phone digits stay together beside long departments at narrow widths', async ({ page }) => {
  await page.goto('/find');
  await expect(page.locator('a[href="tel:02-2164-4951"]')).toBeVisible();
  for (const width of [360, 390, 844, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.locator('.phone-links a').evaluateAll((links) => links.every((link) =>
      link.getBoundingClientRect().height <= parseFloat(getComputedStyle(link).lineHeight) + 1,
    ))).toBeTruthy();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
});

// Keep distinct failure mocks in independent browser contexts across engines.
for (const stalled of ['loader', 'image']) {
  test(`a stalled Kakao ${stalled} ends with useful external links`, async ({ page }) => {
    test.skip(!process.env.TEST_MAP_KEY, 'The key-missing run never loads an SDK.');
    await page.route('https://dapi.kakao.com/**', (route) => route.fulfill({
      contentType: 'application/javascript',
      body: `window.kakao = { maps: { load: (callback) => { ${stalled === 'image' ? 'callback();' : ''} }, LatLng: class {}, StaticMap: class {
        constructor(container) { const image = document.createElement('img'); image.src = '/stalled-map.svg'; container.appendChild(image); }
      } } };`,
    }));
    await page.route('**/stalled-map.svg', () => { /* deliberately never complete the map image */ });
    await page.goto('/find/kim-sou-hwan-hall', { waitUntil: 'domcontentloaded' });
    if (stalled === 'image') await page.locator('.place-map__canvas img').waitFor({ state: 'attached' });
    await expect.poll(async () => {
      await page.clock.runFor(1000);
      return page.getByText('미니 지도를 불러오지 못했어요.', { exact: false }).isVisible();
    }, { intervals: [100] }).toBeTruthy();
    await expect(page.getByRole('link', { name: '카카오맵 길찾기', exact: true })).toBeVisible();
    await expect(page.locator('.place-map')).toHaveAttribute('aria-busy', 'false');
  });
}

test('home venue name and location have separate spacing', async ({ page }) => {
  await page.goto('/');
  const venue = page.locator('.row__title.dining-venue').first();
  await expect(venue).toBeVisible();
  expect(await venue.evaluate((element) => {
    const name = element.children[0].getBoundingClientRect();
    const location = element.children[1].getBoundingClientRect();
    return location.left >= name.right + 7 || location.top >= name.bottom;
  })).toBeTruthy();
});

test('dining switches one venue at a time with keyboard and remembers each day', async ({ page }) => {
  await page.goto('/dining');
  const tabs = page.getByRole('tablist', { name: '교내 식당 선택' });
  const first = tabs.getByRole('tab').nth(0);
  await expect(first).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel')).toHaveCount(1);
  await page.getByRole('button', { name: '화', exact: true }).click();
  await expect(page.getByText('화요일 테스트 메뉴')).toBeVisible();
  await first.focus();
  await first.press('ArrowRight');
  await expect(tabs.getByRole('tab').nth(1)).toBeFocused();
  await expect(page.getByRole('tabpanel')).toHaveCount(1);
  await expect(page.getByText('주간 메뉴표 형태가 아니라', { exact: false })).toBeVisible();
  await expect(page.getByText('제한된 메뉴 원문 테스트', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '학교 원문 보기 ›', exact: true })).toBeVisible();
  await page.getByRole('tabpanel').getByText('운영시간·주간 안내', { exact: true }).click();
  await expect(page.getByText('공식 운영 안내 · 10:30 ~ 14:30')).toBeVisible();
  await expect(page.getByRole('link', { name: '학교 원문 보기 ›', exact: true })).toBeVisible();
  await tabs.getByRole('tab').nth(1).press('End');
  await expect(tabs.getByRole('tab').nth(2)).toBeFocused();
  await expect(page.getByText('정리된 메뉴 정보가 없어요.', { exact: false })).toBeVisible();
  await tabs.getByRole('tab').nth(2).press('Home');
  await expect(first).toBeFocused();
  await expect(page.getByText('화요일 테스트 메뉴')).toBeVisible();
  await expect(page.getByText('월요일 테스트 메뉴')).toBeHidden();
  for (const width of [360, 390, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
});

test('building selector stays compact and restores the last building', async ({ page }) => {
  await page.goto('/study');
  const selector = page.getByRole('combobox', { name: '강의실 건물' });
  await expect(selector.locator('option')).toHaveCount(2);
  await selector.selectOption('virtus-hall');
  await page.reload();
  await expect(selector).toHaveValue('virtus-hall');
  for (const width of [360, 390, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    expect((await selector.boundingBox())!.height).toBeLessThanOrEqual(48);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
});

test('place contact is labeled and desktop tabs align with the content column', async ({ page }) => {
  await page.goto(`/find/virtus-hall?q=${encodeURIComponent('보건실')}`);
  await expect(page.locator('.place-detail__location')).toHaveText('비르투스관 1층 104호 · V관');
  await expect(page.locator('a[href="tel:02-2164-4126"]')).toHaveText('전화 02-2164-4126');
  await expect(page.locator('.topbar__title')).toHaveText('위치 찾기');
  await page.setViewportSize({ width: 1440, height: 900 });
  const shell = (await page.locator('.shell').boundingBox())!;
  const nav = (await page.locator('.tabbar').boundingBox())!;
  expect(Math.abs(nav.x - shell.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(nav.width - shell.width)).toBeLessThanOrEqual(1);
});
