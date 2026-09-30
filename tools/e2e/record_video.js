// 발표 영상 40초 원본 녹화 — 실제 사용자가 영수증 사진을 올리는 흐름(10-01 결정: 시연 케이스 표 숨김, 컷 5 = 대시보드).
// CDP 스크린캐스트 JPEG 프레임(파일명 = 시각)과 컷 표지(marks.json)를 남긴다 → make_video.py가 대기 구간을 잘라 mp4로 만든다.
// 실행: PJ_A=http://127.0.0.1:18091 PJ_B=http://127.0.0.1:18092 NODE_PATH=~/workspace/03-agents/naver-agent/node_modules \
//       node tools/e2e/record_video.js <출력폴더> <업로드폴더>
//   A = 빈 DB(컷 1～4와 컷 5 앞부분), B = 목데이터 DB(컷 5 뒷부분·컷 6). 두 서버 모두 project.json에 "시연 케이스": false.
//   B에는 녹화 전에 같은 두 건을 녹화 없이 먼저 넣어 목록 맨 위에 오게 한다.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const A = process.env.PJ_A, B = process.env.PJ_B;
const OUT = process.argv[2], UP = process.argv[3];
const FR = path.join(OUT, 'frames');
fs.mkdirSync(FR, { recursive: true });
const PHOTO1 = path.join(UP, 'IMG_20260612_124311.jpg');   // R1 한식당 미가 52,800원 — 외부 자문위원 참석
const PHOTO2 = path.join(UP, 'IMG_20260612_124528.jpg');   // R4 한식당 미가 24,000원 — 참여연구자 2명
const MIN1 = '2026-06-12 12:00~13:30 과제 중간점검 회의(장소: 한식당 미가).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), 박민수(KAIST 교수), 정수진(한국전자통신연구원).';
const MIN2 = '2026-06-12 12:00 과제 내부 점검 회의(장소: 한식당 미가).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원).';

// 헤드리스엔 마우스 커서가 안 그려진다 — 화살표 커서와 클릭 물결을 페이지에 그린다(pointer-events 없음).
const CURSOR = `(() => {
  const mk = () => {
    if (document.getElementById('__cur')) return;
    const c = document.createElement('div'); c.id = '__cur';
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 26 26"><path d="M3 2 L3 21 L8 16.5 L11.5 24 L14.5 22.6 L11 15.2 L17.5 15.2 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    c.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;will-change:transform';
    const p = JSON.parse(sessionStorage.getItem('__cur') || '[800,450]');
    c.style.transform = 'translate(' + p[0] + 'px,' + p[1] + 'px)';
    document.documentElement.appendChild(c);
    const st = document.createElement('style');
    st.textContent = '.__rip{position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;border:2px solid rgba(30,100,220,.85);pointer-events:none;z-index:2147483646;animation:__r .45s ease-out forwards}@keyframes __r{from{transform:scale(.3);opacity:1}to{transform:scale(1.4);opacity:0}}';
    document.documentElement.appendChild(st);
  };
  document.addEventListener('mousemove', e => {
    mk(); const c = document.getElementById('__cur');
    c.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)';
    sessionStorage.setItem('__cur', JSON.stringify([e.clientX, e.clientY]));
  }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div'); r.className = '__rip'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.documentElement.appendChild(r); setTimeout(() => r.remove(), 500);
  }, true);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mk); else mk();
})();`;

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.2, locale: 'ko-KR', acceptDownloads: true });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

  let rec = false, nFrames = 0;
  const marks = [];
  const mark = name => { marks.push({ name, t: Date.now() / 1000 }); console.log('mark', name); };
  const cdp = await ctx.newCDPSession(page);
  cdp.on('Page.screencastFrame', async f => {
    if (rec) { fs.writeFileSync(path.join(FR, `${f.metadata.timestamp.toFixed(3)}.jpg`), Buffer.from(f.data, 'base64')); nFrames++; }
    try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) { /* 페이지 전환 중 */ }
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });

  let cur = [800, 450];
  const wait = ms => page.waitForTimeout(ms);
  async function moveTo(x, y, steps = 22) { await page.mouse.move(x, y, { steps }); cur = [x, y]; }
  async function center(sel) {
    const el = page.locator(sel).first();
    await el.scrollIntoViewIfNeeded();
    const bx = await el.boundingBox();
    return [bx.x + bx.width / 2, bx.y + bx.height / 2];
  }
  async function hover(sel, pause = 500) { const [x, y] = await center(sel); await moveTo(x, y); await wait(pause); }
  async function click(sel, pause = 250) {
    const [x, y] = await center(sel);
    await moveTo(x, y); await wait(pause);
    await page.mouse.down(); await wait(90); await page.mouse.up();
  }
  async function nav(sel, urlRe) { await Promise.all([page.waitForURL(urlRe, { timeout: 30000 }), click(sel)]); await page.mouse.move(cur[0], cur[1]); }
  async function upload(photo, minutes) {
    const [fc] = await Promise.all([page.waitForEvent('filechooser'), click('label.file .btn')]);
    await wait(500);
    await fc.setFiles(photo);
    await wait(900);
    await click('#text_doc');
    await wait(300);
    await page.fill('#text_doc', minutes);   // 붙여 넣기 — 회의록 문서에서 복사해 온 것처럼 한 번에
    await wait(900);
  }
  async function extract(tag) {
    await click('#extract-btn');
    mark(`${tag}_wait_start`);
    await page.waitForSelector('#judge-form', { timeout: 300000 });
    mark(`${tag}_wait_end`);
    await wait(700);
  }
  async function judge() {
    await Promise.all([page.waitForURL(/\/case\/\d+$/, { timeout: 60000 }), click('#judge-btn')]);
    await page.mouse.move(cur[0], cur[1]);
    return page.getAttribute('.hero', 'data-verdict');
  }
  const out = {};

  // ── B 준비(녹화 안 함): 같은 두 건을 먼저 넣어 목데이터 목록 맨 위에 오게 ──
  for (const [ph, mn] of [[PHOTO1, MIN1], [PHOTO2, MIN2]]) {
    await page.goto(B + '/new');
    await (await page.$('#files')).setInputFiles(ph);
    await page.fill('#text_doc', mn);
    await page.click('#extract-btn');
    await page.waitForSelector('#judge-form', { timeout: 300000 });
    await Promise.all([page.waitForURL(/\/case\/\d+$/, { timeout: 60000 }), page.click('#judge-btn')]);
    (out.prepB = out.prepB || []).push(await page.getAttribute('.hero', 'data-verdict'));
  }

  // ── 녹화 시작: A(빈 DB) ──
  await page.goto(A + '/');
  await page.mouse.move(640, 420); cur = [640, 420];
  await wait(400);
  rec = true;
  mark('c1');
  await wait(900);
  await nav('.nav a[href="/new"]', /\/new$/);
  await wait(600);
  await upload(PHOTO1, MIN1);
  mark('c2');
  await extract('x1');
  // 확인: 원문 번호와 필드 표를 훑고, 「확인 요망」(업종)에서 멈춘다 — 사용자가 원문과 대조하는 동작
  for (const f of ['amount_total', 'date', 'vendor_name']) { if (await page.$(`#fields tr[data-f=${f}]`)) await hover(`#fields tr[data-f=${f}] .lab`, 450); }
  if (await page.$('#fields tr[data-f=vendor_type]')) await hover('#fields tr[data-f=vendor_type] select', 1100);
  mark('c3');
  out.v1 = await judge();
  await wait(1300);
  await click('details.stt > summary');
  await wait(2200);
  mark('c4');
  await nav('.nav a[href="/new"]', /\/new$/);
  await wait(400);
  await upload(PHOTO2, MIN2);
  await extract('x2');
  await wait(300);
  out.v2 = await judge();
  await wait(1000);
  await click('details.why > summary');
  await wait(2200);
  mark('c5');
  await nav('.nav a[href="/"]', /\/$/);
  await wait(1300);
  mark('c5_switch');
  rec = false;

  // ── B(목데이터 + 같은 두 건): 한 달 뒤 쌓인 목록 ──
  await page.goto(B + '/');
  await page.mouse.move(cur[0], cur[1]);
  await wait(500);
  rec = true;
  mark('c5b');
  await wait(2300);   // 목데이터가 쌓인 전체 목록(가능·보완·불가 섞임)을 보여 주는 게 컷 5의 요점
  await click('#flt button[data-v="bad"]');
  await wait(900);
  await hover('#cases tr.r:not([hidden]) >> nth=1', 1600);
  mark('c6');
  await nav('.nav a[href="/reports"]', /\/reports$/);
  await wait(900);
  const row = page.locator('tr', { hasText: '사용실적보고서' }).first();
  const btn = row.locator('a.btn');
  const bx = await btn.boundingBox();
  await moveTo(bx.x + bx.width / 2, bx.y + bx.height / 2); await wait(300);
  const [dl] = await Promise.all([page.waitForEvent('download'), (async () => { await page.mouse.down(); await wait(90); await page.mouse.up(); })()]);
  await dl.saveAs(path.join(OUT, '사용실적보고서.hwpx'));
  await wait(1200);
  mark('end');
  rec = false;
  await cdp.send('Page.stopScreencast');

  out.frames = nFrames; out.errors = errs;
  fs.writeFileSync(path.join(OUT, 'marks.json'), JSON.stringify({ marks, out }, null, 1));
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})().catch(e => { console.error('REC FAIL', e); process.exit(1); });
