// 배포본 화면을 shots/*.png 로 캡처한다.
//
//   SALESLUV_ID=... SALESLUV_PW=... node capture.mjs [slug일부]
//
// 계정은 환경변수로만 받는다. 이 파일에도, 로그에도, 커밋에도 값을 남기지 않는다.
// 세션은 .auth.json 에 저장해 다음 실행에서 로그인을 건너뛴다.
import { chromium } from 'playwright';
import { existsSync } from 'node:fs';
import path from 'node:path';

const dir = path.dirname(new URL(import.meta.url).pathname);
const BASE = 'https://d3m90og33enu6v.cloudfront.net';
const AUTH = path.join(dir, '.auth.json');

// 카드 안쪽이 592×271(≈2.17:1). 2:1 로 찍으면 비율 왜곡 없이 거의 꽉 찬다.
const VIEWPORT = { width: 1800, height: 900 };

/** 화면이 자리를 잡을 때까지. 스켈레톤은 div[role=status] 로 선다. */
async function settle(page) {
  await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
  await page
    .waitForFunction(
      () => ![...document.querySelectorAll('[role="status"]')].some((el) => el.checkVisibility()),
      null,
      { timeout: 20_000 },
    )
    .catch(() => {});
  await page.waitForTimeout(1200);
}

const TARGETS = [
  { slug: '01-대시보드', url: '/' },
  {
    slug: '02-고객현황',
    url: '/customers',
    // "고객 등록" 은 드롭다운 트리거다. 명함·사업자등록증·엑셀·직접등록이 펼쳐진 상태를 찍는다.
    async action(page) {
      await page.getByRole('button', { name: '고객 등록' }).click();
      await page.getByRole('menu', { name: '고객 등록 방식' }).waitFor();
      await page.waitForTimeout(400);
    },
  },
  { slug: '03-CS대응', url: '/complaints' },
  { slug: '04-캘린더', url: '/calendar' },
  { slug: '05-업무보고', url: '/daily' },
  { slug: '06-미팅보고서작성', url: '/meetings/new?agenda=fa69a70e-0c9e-5030-9d69-620c728d7dba' },
  { slug: '07-미팅보고서', url: '/meetings/1956ad97-c2e7-48e2-b2e0-cf0633cb02df' },
  { slug: '08-일일보고서작성', url: '/daily/new?date=2026-09-18' },
  { slug: '09-일일보고서', url: '/daily/2d33e14f-ce57-4371-8b8f-c6a9e66fb5b8' },
  {
    slug: '10-보고서PDF저장',
    url: '/daily/2d33e14f-ce57-4371-8b8f-c6a9e66fb5b8',
    // "PDF 다운로드" 는 window.print() 라 네이티브 대화상자가 뜬다. 페이지 밖이라 찍을 수 없고
    // 브라우저 UI 는 어차피 캡처 대상이 아니다. 저장됐을 때의 양식지 자체를 찍는다.
    print: true,
  },
  { slug: '11-영업현황-리스트', url: '/deals' },
  { slug: '12-영업현황-보드', url: '/deals/board' },
  { slug: '13-매출분석', url: '/sales' },
  { slug: '14-거래문서', url: '/documents/trade' },
  {
    slug: '15-영업자료',
    url: '/documents/sales',
    // 자료 1건을 열어 원본과 AI 문서 요약이 나란히 선 상태를 찍는다.
    async action(page) {
      // 자료 목록은 머리글 표와 본문 표가 나뉘어 있고, 바깥 래퍼도 tr 로 잡힌다.
      // 실제 자료 줄은 가장 안쪽 것이라 last() 로 고른다. 줄 전체가 클릭 대상이다
      // (DocumentTable.tsx:235).
      await page.locator('tbody tr').filter({ hasText: 'PDF' }).last().click();
      const open = page.getByRole('button', { name: '원본 보기' });
      await open.waitFor({ timeout: 15_000 });
      await open.click();
      await page.getByRole('button', { name: '원본 닫기' }).waitFor({ timeout: 30_000 });
      await page.waitForTimeout(1500);
    },
  },
  {
    slug: '16-AI브리핑',
    url: '/',
    // 대시보드 오늘 일정에서 일정을 열면 AI 브리핑이 선다. 브리핑이 인용한 C/S 를 눌러
    // 그 건의 상세까지 펼친 상태를 찍는다 — 브리핑이 무엇을 읽었는지가 같이 보여야 한다.
    async action(page) {
      // 줄 전체가 클릭 대상이다 (DayAgenda.tsx:78).
      await page.getByText('효성요양병원 (울산 중구)').first().click();
      await page.getByRole('heading', { name: 'AI 브리핑' }).waitFor({ timeout: 20_000 });

      // 브리핑은 자동 생성이 아니다. 없으면 새로고침을 눌러 만들고 기다린다.
      const empty = page.getByText('아직 만든 AI 브리핑이 없습니다');
      if (await empty.isVisible().catch(() => false)) {
        await page.getByRole('button', { name: '새로고침' }).click();
        await empty.waitFor({ state: 'hidden', timeout: 180_000 });
      }

      const cs = page.locator('section[aria-label="브리핑 C/S"] button').first();
      await cs.waitFor({ timeout: 60_000 });
      await cs.click();
      await settle(page);
      await page.waitForTimeout(1500);
    },
  },
];

const only = process.argv[2];
const targets = only ? TARGETS.filter((t) => t.slug.includes(only)) : TARGETS;
if (!targets.length) throw new Error(`"${only}" 에 맞는 화면이 없습니다.`);

const browser = await chromium.launch({ channel: 'chrome' });
const context = await browser.newContext({
  viewport: VIEWPORT,
  deviceScaleFactor: 2,
  ...(existsSync(AUTH) ? { storageState: AUTH } : {}),
});
const page = await context.newPage();

// 저장된 세션은 만료된다. 파일이 있다고 믿지 말고 실제로 들어가 보고 판단한다.
// 로그인 화면으로 밀어내는 건 React 가 뜬 뒤라(ProtectedRoute.tsx:14) 자리를 잡고 나서 본다.
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await settle(page);
if (await page.locator('#email').isVisible()) {
  const { SALESLUV_ID, SALESLUV_PW } = process.env;
  if (!SALESLUV_ID || !SALESLUV_PW)
    throw new Error('세션이 없거나 만료됐습니다. SALESLUV_ID / SALESLUV_PW 를 주세요.');

  await page.fill('#email', SALESLUV_ID);
  await page.fill('#password', SALESLUV_PW);
  await page.click('button[type=submit]');
  // 로그인 성공은 대시보드로의 이동으로만 확인한다 (Login.tsx 의 <Navigate>).
  await page.waitForURL(`${BASE}/`, { timeout: 30_000 });
  await context.storageState({ path: AUTH });
  console.log('  로그인 완료 → .auth.json');
}

for (const t of targets) {
  await page.emulateMedia({ media: t.print ? 'print' : 'screen' });
  await page.goto(BASE + t.url, { waitUntil: 'domcontentloaded' });
  await settle(page);
  if (t.action) await t.action(page);

  const file = path.join(dir, 'shots', `${t.slug}.png`);
  // 전체 페이지로 찍지 않는다. 슬라이드 카드가 2.17:1 이라 세로로 긴 캡처를 넣으면
  // 글씨가 읽을 수 없게 줄어든다. 늘 뷰포트 한 장(2:1)만 찍는다.
  await page.screenshot({ path: file });
  console.log('  →', path.relative(dir, file));
}

await browser.close();
