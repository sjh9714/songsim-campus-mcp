/**
 * 공유용 QR 코드를 만든다.
 *
 * 학생이 이 사이트에 닿는 길이 주소를 직접 치는 것뿐이었다. 강의실이나 게시판에
 * 붙여 두고 찍을 수 있게 정적 자산 하나를 만들어 둔다.
 *
 * 화면은 새로 만들지 않는다. QR 은 어쩌다 한 번 쓰는 것이고, 매일 쓰는 것만
 * 화면에 둔다는 이 앱의 방향과 어긋난다. 필요한 사람이 /qr.svg 를 열어 인쇄한다.
 *
 * 손으로 만든 SVG 를 커밋하지 않고 빌드 때마다 다시 만든다. 주소가 바뀌면
 * QR 도 따라 바뀌어야 하는데, 커밋해 두면 조용히 어긋난다.
 */

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import qrcode from 'qrcode-generator';

const SITE_URL = process.env.SONGSIM_SITE_URL ?? 'https://songsim-web.vercel.app';

// 타입 0 = 내용 길이에 맞춰 자동으로 고른다.
// 오류 정정 M = 인쇄물이 조금 더러워지거나 접혀도 읽힌다. 종이에 붙일 것이라 낮게 두지 않는다.
const qr = qrcode(0, 'M');
qr.addData(SITE_URL);
qr.make();

const count = qr.getModuleCount();
// 여백(quiet zone)은 규격상 4모듈이다. 없으면 스캐너가 경계를 못 찾는다.
const margin = 4;
const size = count + margin * 2;

const cells = [];
for (let row = 0; row < count; row += 1) {
  for (let col = 0; col < count; col += 1) {
    if (qr.isDark(row, col)) {
      cells.push(`M${col + margin} ${row + margin}h1v1h-1z`);
    }
  }
}

const svg = [
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}"`,
  ` width="512" height="512" shape-rendering="crispEdges"`,
  ` role="img" aria-label="${SITE_URL} QR 코드">`,
  `<rect width="${size}" height="${size}" fill="#ffffff"/>`,
  `<path d="${cells.join('')}" fill="#0c2e86"/>`,
  `</svg>`,
].join('');

const outPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'qr.svg');
mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, `${svg}\n`, 'utf8');

console.log(`[make-qr] ${SITE_URL} → public/qr.svg (${count}x${count} 모듈)`);
