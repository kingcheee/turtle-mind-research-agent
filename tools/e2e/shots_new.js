// 새 화면(02 고밀도 작업대) 한 바퀴 캡처 + 검사: 페이지 스크롤 0 · 가로 넘침 0 · 콘솔/페이지 에러 0 · 외부 요청 0
// 실행: NODE_PATH=~/workspace/03-agents/naver-agent/node_modules node tools/e2e/shots_new.js <캡처폴더> [시연번호=4]
// 서버 주소는 PJ_URL(기본 http://127.0.0.1:18080). 실제 모델로 추출하므로 llama-server가 떠 있어야 한다.
const { chromium } = require('playwright');
const B = process.env.PJ_URL || 'http://127.0.0.1:18080';
const S = process.argv[2] || '.';
const DEMO = +(process.argv[3] || 4);
const W = +(process.env.PJ_W || 1440), H = +(process.env.PJ_H || 900);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const errors = [], external = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(`[${page.url()}] console: ${m.text()}`); });
  page.on('pageerror', e => errors.push(`[${page.url()}] page: ${e.message}`));
  page.on('request', r => { const h = new URL(r.url()).hostname; if (!['127.0.0.1', 'localhost'].includes(h) && !r.url().startsWith('data:')) external.push(r.url()); });
  const out = {};
  async function check(name, shot) {
    out[name] = await page.evaluate(() => {
      const se = document.scrollingElement;
      const over = [];
      // 가로로 넘친 요소(스크롤 영역 안쪽 제외) — 셸 밖으로 나간 것만
      document.querySelectorAll('.app *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width && r.right > innerWidth + 1) over.push((el.className && String(el.className).slice(0, 40)) || el.tagName);
      });
      return { pageScroll: se.scrollHeight - innerHeight, hOverflow: se.scrollWidth - innerWidth, outside: over.slice(0, 5) };
    });
    if (shot) await page.screenshot({ path: `${S}/${shot}.png` });
  }
  // 1 빈 목록
  await page.goto(B + '/'); await check('list_empty', '40-list-empty');
  // 2 올리기 → 시연 행 → ⌘↵
  await page.goto(B + '/new?demo=all'); await check('new', '41-new');
  await page.click(`#demo tbody tr:nth-child(${DEMO})`);
  out.new_text = (await page.inputValue('#text_doc')).slice(0, 40);
  out.new_sum = await page.textContent('#up-sum');
  await page.screenshot({ path: `${S}/41b-new-picked.png` });
  const t0 = Date.now();
  await page.keyboard.press('Control+Enter');
  await page.waitForSelector('#judge-form', { timeout: 180000 });
  out.extract_sec = (Date.now() - t0) / 1000;
  await page.waitForTimeout(300);
  await check('review_layout', '42-review');
  out.review = await page.evaluate(() => ({
    total: document.getElementById('f-total').textContent, sum: document.getElementById('f-sum').textContent,
    flag: document.getElementById('ab-flag').textContent, absum: document.getElementById('ab-sum').textContent,
    marks: document.querySelectorAll('#ev mark').length, why: [...document.querySelectorAll('#fields tr.why')].map(t => t.textContent),
    rows: [...document.querySelectorAll('#fields tr[data-f]')].map(t => [t.dataset.f, t.querySelector('.rn').textContent, t.querySelector('.srcref').textContent, t.querySelector('.cmp').textContent].join(' | ')),
    att: document.getElementById('att-sum').textContent,
  }));
  // 강조 연동: 첫 번호 행에 마우스
  const numbered = await page.$('#fields tr[data-f]:has(.rn .ref)');
  if (numbered) { await numbered.hover(); out.hover_hot_marks = await page.$$eval('#ev mark.hot', m => m.length); await page.screenshot({ path: `${S}/42b-review-hover.png` }); }
  // 3 판정
  await page.click('#judge-btn');
  await page.waitForURL(/\/case\/\d+$/, { timeout: 30000 });
  await check('case', '43-case');
  out.case_verdict = await page.getAttribute('.hero', 'data-verdict');   // 09-29: 판정 띠(.vband) → .hero, 규칙 ID는 속성으로만
  out.case_tags = ((await page.getAttribute('.hero', 'data-rules')) || '').split(' ').filter(Boolean);
  const tl = await page.$$('.tl button[data-code]');
  if (tl.length > 1) {
    await page.click('details.stt:has(.tl) > summary');                    // 조항 칸은 접힌 채 시작한다
    const q0 = await page.textContent('.stt blockquote');
    await tl[1].click();
    out.tl_changed = q0 !== await page.textContent('.stt blockquote');
    out.tl_note = await page.isVisible('.stt-note');
    await page.screenshot({ path: `${S}/44-case-timeline.png` });
  }
  // 4 목록(건 1개) + 미리보기
  await page.goto(B + '/'); await page.waitForSelector('#pv .pv-h', { timeout: 5000 }).catch(() => {});
  await check('list', '45-list');
  out.list_pv = !!(await page.$('#pv .pv-h'));
  // 5 수정 화면
  const cid = (await page.getAttribute('#rows tr.r', 'data-id'));
  await page.goto(`${B}/case/${cid}/edit`); await page.waitForTimeout(200); await check('edit', '46-edit');
  // 6 행정팀·보고서·실측
  for (const [p, n] of [['/admin', '47-admin'], ['/reports', '48-reports'], ['/bench', '49-bench']]) {
    const r = await page.goto(B + p);
    if (r.status() === 404) { out[p] = 404; continue; }
    await check(p.slice(1), n);
  }
  out.errors = errors; out.external = external;
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})();
