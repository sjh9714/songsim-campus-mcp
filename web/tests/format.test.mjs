import test from 'node:test';
import assert from 'node:assert/strict';
import { formatAgo, todayInSeoul, sortMeals } from '../lib/format.ts';
import { isRecent } from '../lib/live-state.ts';
import { isWithinClassroomUseWindow } from '../lib/classrooms.ts';
import { kakaoDirectionsHref, kakaoMapHref, placeLocationLabel } from '../lib/places.ts';

test('KST midnight, weekend and rental boundaries', () => {
  assert.equal(todayInSeoul(new Date('2026-09-07T15:00:00Z')), '2026-09-08');
  assert.equal(isWithinClassroomUseWindow('2026-09-07T14:00:00+09:00'), true);
  assert.equal(isWithinClassroomUseWindow('2026-09-06T14:00:00+09:00'), false);
  assert.equal(isWithinClassroomUseWindow('2026-09-07T22:00:00+09:00'), false);
  assert.equal(formatAgo('2026-09-07T00:00:00Z', Date.parse('2026-09-07T00:02:00Z')), '2분 전');
});
test('unobserved, future and expired results are never live', () => {
  const now = Date.parse('2026-09-07T00:00:00Z');
  for (const value of [null, 'invalid', '2026-09-06T23:58:59Z', '2026-09-07T00:01:00Z']) assert.equal(isRecent(value, now, 60_000), false);
  assert.equal(isRecent('2026-09-07T00:00:00Z', null, 60_000), false);
  assert.equal(isRecent('2026-09-06T23:59:10Z', now, 60_000), true);
});
test('source meal labels remain in breakfast / lunch corners / dinner order', () => {
  assert.deepEqual(sortMeals({ 석식: {}, 누들: {}, '천원의 아침': {}, 한식: {} }), ['천원의 아침', '한식', '누들', '석식']);
});
test('map URLs encode spaces and Korean; missing or invalid coordinates use search', () => {
  const place = { name: '김수환관', canonical_name: '김수환관', latitude: 37.485, longitude: 126.803 };
  assert.equal(kakaoDirectionsHref(place, '카페 멘사'), `https://map.kakao.com/link/to/${encodeURIComponent('카페 멘사')},37.485,126.803`);
  for (const latitude of [null, NaN, 100]) {
    assert.equal(kakaoDirectionsHref({ ...place, latitude }), null);
    assert.match(kakaoMapHref({ ...place, latitude }), /\/link\/search\//);
  }
});

test('facility location retains the official floor and code without repeating the building', () => {
  const place = { name: '비르투스관', aliases: ['V관'] };
  assert.equal(placeLocationLabel(place, '비르투스관 1층 104호'), '비르투스관 1층 104호 · V관');
  assert.equal(placeLocationLabel(place, '비르투스관(V관) 1층'), '비르투스관(V관) 1층');
  assert.equal(placeLocationLabel(place, '1층 104호'), '1층 104호 · 비르투스관(V관)');
  assert.equal(placeLocationLabel(place, null), '비르투스관(V관)');
  assert.equal(placeLocationLabel({ ...place, aliases: [] }, '비르투스관 1층'), '비르투스관 1층');
});
