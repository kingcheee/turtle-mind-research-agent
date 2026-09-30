// 발표 영상 v4 원본 녹화 — record_v3.js + 클릭마다 (시각, 좌표, 종류)를 marks.json에 남긴다(make_v4.py가 카메라 줌에 쓴다).
// 화면은 2560×1440(deviceScaleFactor 1.6 — 줌해도 글자가 뭉개지지 않게). 흐름은 v3와 같다(대시보드는 찍지만 v4 편집에선 안 쓴다).
// 표지 추가: j1(판정 클릭 직전) · l1(목록 이동 클릭 직전).
// 대시보드 시작 → 새 증빙(문서 종류 목록 → R7 사진 → 회의록 → 추출) → 확인 화면(필드·참석자) → 판정(가능 → 요건 대조·판정 근거·조항)
// → 건 목록(Gemini 사진 행만 미리보기) → 사이드바 「사용실적보고서」 클릭(hwpx 다운로드 알림). 끝 장면(서식)은 make_report_still.py.
// 녹화 때만 하는 것 둘: ①<select>를 누르면 그 자리에 목록을 그린다(헤드리스 스크린캐스트엔 기본 드롭다운이 안 찍힌다)
// ②다운로드가 시작되면 브라우저의 다운로드 알림 모양을 페이지에 그린다(헤드리스엔 알림 표시줄이 없다). 앱은 안 고친다.
// 실행: PJ=http://127.0.0.1:18092 NODE_PATH=~/workspace/03-agents/naver-agent/node_modules \
//       node tools/e2e/record_v4.js <출력폴더> <업로드폴더>
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const PJ = process.env.PJ;
const OUT = process.argv[2], UP = process.argv[3];
const FR = path.join(OUT, 'frames');
fs.mkdirSync(FR, { recursive: true });
const PHOTO = path.join(UP, 'IMG_20260616_123412.jpg');   // R7 중화요리 홍보각 70,000원 — 외부 교수 2명 참석 → 가능
const MIN = '2026-06-16 12:00~13:30 과제 협력 방향 논의 회의(장소: 중화요리 홍보각).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), 정수진(한국전자통신연구원), 이준호(서울대학교 부교수), 한지원(KAIST 박사과정).';
const PREVIEW_IDS = [7, 5];      // 목록에서 미리보기할 행(새로 올린 건 다음) — Gemini 사진이 붙은 목데이터 행만(#7 국밥집 온기 · #5 한식당 미가)

const CURSOR = fs.readFileSync(path.join(__dirname, 'record_video.js'), 'utf8').match(/const CURSOR = (`[\s\S]*?`);/)[1];

// 녹화용 목록 — <select> 자리에 앱 서식과 같은 모양으로 펼친다. 항목 위치를 돌려줘 커서를 그리로 옮긴다.
const FAKE_MENU = `(sel) => {
  const r = sel.getBoundingClientRect();
  const m = document.createElement('div'); m.id = '__menu';
  m.style.cssText = 'position:fixed;z-index:9999;left:' + r.left + 'px;top:' + (r.bottom + 2) + 'px;min-width:' + r.width + 'px;' +
    'background:#fff;border:1px solid #C6CED8;border-radius:3px;box-shadow:0 6px 18px rgba(20,30,50,.14);padding:4px 0;font-size:15px';
  const out = [];
  for (const o of sel.options) {
    const d = document.createElement('div'); d.textContent = o.text; d.dataset.v = o.value;
    d.style.cssText = 'padding:6px 12px;line-height:20px;white-space:nowrap' + (o.selected ? ';background:#E8F0FE' : '');
    m.appendChild(d);
  }
  document.body.appendChild(m);
  for (const d of m.children) { const b = d.getBoundingClientRect(); out.push([d.dataset.v, b.left + 24, b.top + b.height / 2]); }
  return out;
}`;
const MENU_HOT = `(v) => { for (const d of document.getElementById('__menu').children) d.style.background = d.dataset.v === v ? '#E8F0FE' : ''; }`;
const MENU_CLOSE = `() => { const m = document.getElementById('__menu'); if (m) m.remove(); }`;
// 다운로드 알림 — 브라우저 오른쪽 위 알림 모양(파일 이름·크기·완료)
const DL_BUBBLE = `([name, kb]) => {
  const b = document.createElement('div'); b.id = '__dl';
  b.style.cssText = 'position:fixed;z-index:9999;right:18px;top:12px;display:flex;align-items:center;gap:12px;padding:12px 16px;' +
    'background:#fff;border:1px solid #C6CED8;border-radius:10px;box-shadow:0 8px 24px rgba(20,30,50,.18);font-size:14px;max-width:560px';
  b.innerHTML = '<div style="width:34px;height:34px;border-radius:8px;background:#E8F0FE;display:flex;align-items:center;justify-content:center;flex:none">' +
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1a56db" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0l-5-5m5 5l5-5M4 19h16"/></svg></div>' +
    '<div style="min-width:0"><div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + name + '</div>' +
    '<div style="color:#5b6470;margin-top:2px">' + kb + ' KB · 다운로드 완료</div></div>';
  document.body.appendChild(b);
}`;

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.6, locale: 'ko-KR', acceptDownloads: true });
  await ctx.addInitScript(eval(CURSOR));
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

  let rec = false, nFrames = 0;
  const marks = [], clicks = [];
  const logClick = (kind, x, y) => { clicks.push({ kind, t: Date.now() / 1000, x, y }); };
  const mark = name => { marks.push({ name, t: Date.now() / 1000 }); console.log('mark', name); };
  const cdp = await ctx.newCDPSession(page);
  cdp.on('Page.screencastFrame', async f => {
    if (rec) { fs.writeFileSync(path.join(FR, `${f.metadata.timestamp.toFixed(3)}.jpg`), Buffer.from(f.data, 'base64')); nFrames++; }
    try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) { /* 페이지 전환 중 */ }
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 2560, maxHeight: 1440, everyNthFrame: 1 });

  let cur = [800, 450];
  const wait = ms => page.waitForTimeout(ms);
  async function moveTo(x, y, steps = 30) { await page.mouse.move(x, y, { steps }); cur = [x, y]; }
  async function center(sel) {
    const el = page.locator(sel).first();
    await el.scrollIntoViewIfNeeded();
    const bx = await el.boundingBox();
    return [bx.x + bx.width / 2, bx.y + bx.height / 2];
  }
  async function hover(sel, pause = 700) { const [x, y] = await center(sel); await moveTo(x, y); await wait(pause); }
  async function click(sel, pause = 350, kind = 'click') {
    const [x, y] = await center(sel);
    await moveTo(x, y); await wait(pause);
    logClick(kind, x, y);
    await page.mouse.down(); await wait(90); await page.mouse.up();
  }
  async function nav(sel, urlRe, kind = 'nav') { await Promise.all([page.waitForURL(urlRe, { timeout: 30000 }), click(sel, 350, kind)]); await page.mouse.move(cur[0], cur[1]); }
  // 목록 화면에서는 커서를 사이드바(x=100)로 뺐다가 목표 높이에서 들어간다 — 행 위를 가로지르면 지나는 행마다 미리보기가 뜬다
  async function detour(x, y) { await moveTo(100, cur[1], 12); await moveTo(100, y, 16); await moveTo(x, y, 14); }
  async function hoverRow(sel, pause) { const [x, y] = await center(sel); await detour(x, y); await wait(pause); }
  const out = {};

  // ── 대시보드에서 시작 ──
  await page.goto(PJ + '/');
  { const [x, y] = await center('#cases tr.r[data-id="7"]'); await page.mouse.move(x, y); cur = [x, y]; }   // 처음 미리보기 = #7 국밥집 온기(Gemini 사진) — 기본은 첫 행 #16(사진 없음)
  await wait(800);
  rec = true;
  mark('a');
  await wait(900);
  { const [x, y] = await center('.bar a.btn.pri[href="/new"]'); await moveTo(100, y, 16); await moveTo(x, y, 18); }
  await nav('.bar a.btn.pri[href="/new"]', /\/new$/);
  mark('n1');
  await wait(600);

  // ── 새 증빙: 문서 종류 목록을 펼쳐 「영수증」을 고른다 ──
  const selBox = await page.locator('select[name=file_doc_type]').boundingBox();
  await moveTo(selBox.x + selBox.width / 2, selBox.y + selBox.height / 2); await wait(300);
  logClick('menu', selBox.x + selBox.width / 2, selBox.y + selBox.height / 2);
  const items = await page.evaluate(eval(FAKE_MENU), await page.locator('select[name=file_doc_type]').elementHandle());
  await wait(350);
  for (const [v, x, y] of items.slice(0, 3)) {                 // 커서가 목록을 두어 칸 내려갔다 「영수증」으로 돌아온다
    await moveTo(x, y, 10); await page.evaluate(eval(MENU_HOT), v); await wait(200);
  }
  const [rv, rx, ry] = items[0];
  await moveTo(rx, ry, 12); await page.evaluate(eval(MENU_HOT), rv); await wait(350);
  logClick('item', rx, ry);
  await page.mouse.down(); await wait(90); await page.mouse.up();
  await page.evaluate(eval(MENU_CLOSE));
  await page.selectOption('select[name=file_doc_type]', rv);
  await wait(350);

  // 사진 → 회의록 → 추출
  const [fc] = await Promise.all([page.waitForEvent('filechooser'), click('label.file .btn', 250, 'file')]);
  await wait(300);
  await fc.setFiles(PHOTO);
  await wait(1000);                         // 사진이 크게 붙는 걸 보여 준다
  await click('#text_doc', 250, 'text');
  await wait(300);
  await page.fill('#text_doc', MIN);        // 회의록 문서에서 복사해 붙여 넣은 것처럼 한 번에
  await wait(800);
  await click('#extract-btn', 300, 'extract');
  mark('x1');
  await page.waitForSelector('#judge-form', { timeout: 300000 });
  mark('x1_end');
  await wait(500);

  // ── 확인 화면: 필드 셋 → 참석자 목록(외부 두 사람) ──
  for (const f of ['amount_total', 'date', 'vendor_name']) await hover(`#fields tr[data-f=${f}] .lab`, 500);
  const att = page.locator('#att tbody tr');
  const n = await att.count();
  for (let i = 0; i < n; i++) {
    const bx = await att.nth(i).boundingBox();
    if (!bx) continue;
    await moveTo(bx.x + bx.width * 0.3, bx.y + bx.height / 2, 8);
    await wait(i >= 3 ? 500 : 250);          // 외부 참석자 두 행(이준호·한지원)에서 더 머문다
  }

  // ── 판정: 가능 → 요건 대조·판정 근거·조항을 하나씩 펼친다 ──
  mark('j1');
  await Promise.all([page.waitForURL(/\/case\/\d+$/, { timeout: 60000 }), click('#judge-btn', 350, 'judge')]);
  await page.mouse.move(cur[0], cur[1]);
  out.v1 = await page.getAttribute('.hero', 'data-verdict');
  mark('v1');
  await wait(400);
  await hover('.hero', 900);
  for (const s of ['details.fold:not(.why):not(.stt) > summary', 'details.why > summary', 'details.stt > summary']) {
    await click(s, 250, 'fold'); await wait(250);
    await page.locator(s.replace(' > summary', '')).evaluate(el => el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));   // 펼친 내용이 화면 아래로 잘리지 않게
    await wait(800);
  }
  mark('d1');

  // ── 건 목록: 방금 건이 맨 위 → Gemini 사진 행만 미리보기 ──
  mark('l1');
  await nav('.nav a[href="/"]', /\/$/, 'list');
  await wait(700);
  await hoverRow('#cases tr.r:not([hidden]) >> nth=0', 1300);
  for (const id of PREVIEW_IDS) await hoverRow(`#cases tr.r[data-id="${id}"]`, 1300);
  mark('r1');

  // ── 사용실적보고서: 사이드바 링크 → hwpx 다운로드 알림 ──
  { const [x, y] = await center('.tree a[href="/reports/usage.hwpx"]'); await detour(x, y); }
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), click('.tree a[href="/reports/usage.hwpx"]', 350, 'report')]);
  const dlPath = await dl.path();
  const name = dl.suggestedFilename();
  fs.copyFileSync(dlPath, path.join(OUT, '사용실적보고서-앱.hwpx'));
  out.download = name;
  await page.evaluate(eval(DL_BUBBLE), [name, Math.round(fs.statSync(dlPath).size / 1024)]);
  mark('dl');
  await wait(2000);
  mark('end');
  rec = false;
  await cdp.send('Page.stopScreencast');

  out.frames = nFrames; out.errors = errs;
  fs.writeFileSync(path.join(OUT, 'marks.json'), JSON.stringify({ marks, clicks, out }, null, 1));
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})().catch(e => { console.error('REC FAIL', e); process.exit(1); });
