// 발표 영상 40초(03-발표-대본.md §3)의 컷별 화면을 실제 모델로 찍는다 — 녹화 전 확인·슬라이드 UI 캡처용.
// 실행: PJ_URL=http://127.0.0.1:18090 NODE_PATH=~/workspace/03-agents/naver-agent/node_modules node tools/e2e/video_cuts.js <캡처폴더>
// 빈 DB 서버에서 돌릴 것(건이 생긴다). 16:9 1600×900 × 1.2배 = 1920×1080 PNG.
const { chromium } = require('playwright');
const B = process.env.PJ_URL || 'http://127.0.0.1:18080';
const S = process.argv[2] || '.';
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.2, locale: 'ko-KR' });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  const out = {};
  const shot = name => page.screenshot({ path: `${S}/${name}.png` });
  const open = async sel => { await page.click(`${sel} > summary`); await page.waitForTimeout(250); };   // 펼침 애니메이션 0.12초
  async function extract(n) {
    await page.goto(B + '/new?demo=all');
    await page.click(`#demo tbody tr:nth-child(${n})`);
    return page;
  }
  async function judge() {
    await Promise.all([page.waitForURL(/\/case\/\d+$/, { timeout: 30000 }), page.click('#judge-btn')]);
    return page.getAttribute('.hero', 'data-verdict');
  }

  // 컷 1: 새 증빙 → 시연 「외부 참석 회의」 행 → 텍스트 칸이 채워진다
  await extract(1);
  await shot('v1-new');
  // 컷 2: 추출 → 확인 화면(원문 번호 마크 ↔ 필드 표)
  let t = Date.now();
  await page.click('#extract-btn');
  await page.waitForSelector('#judge-form', { timeout: 180000 });
  out.extract_sec_1 = Math.round((Date.now() - t) / 100) / 10;
  await page.waitForTimeout(400);
  await shot('v2-review');
  // 컷 3: 판정 → 영수증(원문) | 가능, 조항을 펼치면 기준일 적용 구간
  out.v3 = await judge();
  await shot('v3-verdict-ok');
  await open('details.stt');
  await shot('v3b-article');
  // 컷 4: 「참여연구자만 회의 식비」 → 불가, 안 되는 이유
  await extract(4);
  await page.click('#extract-btn');
  await page.waitForSelector('#judge-form', { timeout: 180000 });
  out.v4 = await judge();
  await shot('v4-verdict-bad');
  await open('details.why');
  await shot('v4b-why');
  // 컷 5: 수정 → 집행일 2025-03-10 → 재판정 → 안 되는 이유에 사전결재가 붙고, 조항은 제2023-49호
  await page.click('#edit-btn');
  await page.waitForSelector('#judge-form');
  await page.fill('#judge-form [name=date]', '2025-03-10');
  await shot('v5-edit-date');
  out.v5 = await judge();
  out.v5_why = (await page.textContent('details.why > summary')).replace(/\s+/g, ' ').trim();
  await shot('v5-verdict-w1');
  await open('details.stt');
  out.v5_notice = (await page.textContent('details.stt .stt-m')).replace(/\s+/g, ' ').trim();
  await shot('v5b-article-w1');
  // 컷 6: 보고서 화면(사용실적보고서 hwpx 내려받기)
  await page.goto(B + '/reports');
  await shot('v6-reports');
  out.errors = errs;
  console.log(JSON.stringify(out, null, 1));
  await b.close();
  if (errs.length) process.exit(1);
})().catch(e => { console.error('CUTS FAIL', e); process.exit(1); });
