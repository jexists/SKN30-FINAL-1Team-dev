// icons.js 의 SVG 를 96px PNG 로 구워 icons/ 에 캐시한다.
// pptx 는 SVG 를 그대로 못 넣고, 이 환경엔 cairosvg 가 없어 Chrome 으로 굽는다.
// 아이콘이 늘거나 바뀔 때만 다시 돌리면 된다.
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const dir = path.dirname(new URL(import.meta.url).pathname);
mkdirSync(path.join(dir, 'icons'), { recursive: true });

const browser = await chromium.launch({ channel: 'chrome' });
// 24pt 아이콘을 4배로 구워 슬라이드에서 선이 뭉개지지 않게 한다.
const page = await browser.newPage({ viewport: { width: 96, height: 96 }, deviceScaleFactor: 1 });
await page.goto('about:blank');
await page.addScriptTag({ path: path.join(dir, 'icons.js') });

const keys = await page.evaluate(() => Object.keys(ICON));
for (const key of keys) {
  await page.evaluate((k) => {
    document.body.style.cssText = 'margin:0;background:transparent';
    document.body.innerHTML = ICON[k];
    const svg = document.querySelector('svg');
    svg.setAttribute('width', 96);
    svg.setAttribute('height', 96);
    svg.style.cssText = 'display:block;stroke:#2563EB;stroke-width:2;fill:none;' +
      'stroke-linecap:round;stroke-linejoin:round';
  }, key);
  await page.locator('svg').screenshot({
    path: path.join(dir, 'icons', `${key}.png`),
    omitBackground: true,
  });
}
console.log(`  아이콘 ${keys.length}개 → icons/`);
await browser.close();
