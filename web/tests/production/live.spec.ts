import { test, expect } from '@playwright/test';

test('production current-time rendering and health-center journey', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  const menuResponse = await request.get('https://songsim-api-sg.onrender.com/dining-menus', { timeout: 60_000 });
  expect(menuResponse.ok()).toBeTruthy();
  const menus = await menuResponse.json();
  expect(Array.isArray(menus) && menus.length > 0).toBeTruthy();
  for (const menu of menus) {
    // A successful HTTP response is not proof that the collection job is still running.
    expect(Date.now() - Date.parse(menu.last_synced_at)).toBeLessThan(48 * 3_600_000);
  }
  if (await page.getByRole('heading', { name: '오늘의 학식' }).count()) {
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
    expect(menus.some((m: { days?: { date: string }[] }) => m.days?.some((d) => d.date === today))).toBeTruthy();
  }
  await page.goto(`/search?q=${encodeURIComponent('보건실 어디야')}`);
  await page.getByRole('link', { name: '보건실 위치 보기' }).click();
  await expect(page.getByText('비르투스관 1층 104호', { exact: false })).toBeVisible();
  await expect(page.locator('a[href="tel:02-2164-4126"]')).toBeVisible();
  await expect(page.getByRole('link', { name: '카카오맵 길찾기', exact: true })).toHaveAttribute('href', /\/to\/.*,[0-9.]+,[0-9.]+$/);
  await expect.poll(() => page.locator('.place-map__canvas img').evaluateAll((images) => images.length > 0 && images.every((image) => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBeTruthy();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});

test('production live endpoint never marks old library observations as current', async ({ page }) => {
  const live = page.waitForResponse((response) => response.url().includes('/api/live?kind=library-seats'), { timeout: 65_000 });
  await page.goto('/study');
  const result = await (await live).json();
  if (result.data.availability_mode === 'live' && !result.degraded) {
    expect(Date.now() - Date.parse(result.data.checked_at)).toBeLessThan(60_000);
    await expect(page.locator('.room-map-link').first()).toBeVisible();
  } else {
    await expect(page.getByText('현재 좌석 수를 확인하지 못했어요.')).toBeVisible();
  }
  await expect(page.getByRole('link', { name: '공식 좌석 현황 페이지 ›' })).toHaveAttribute('href', 'https://mlibrary.catholic.ac.kr/mobile/PA/roomStatus.php');
});
