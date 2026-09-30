// 발표 영상 v2 원본 녹화 — 느린 호흡(10-01 사용자 그릴링): 영수증1 가능(확인 화면까지) → 영수증2 불가(바로 판정) → 대시보드.
// 서버 하나(목데이터 14건 DB, "시연 케이스": false)에 그대로 올린다 — 점프 컷 없음. 끝 장면(보고서 서식)은 make_report_still.py.
// 실행: PJ=http://127.0.0.1:18092 NODE_PATH=~/workspace/03-agents/naver-agent/node_modules \
//       node tools/e2e/record_slow.js <출력폴더> <업로드폴더>
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const PJ = process.env.PJ;
const OUT = process.argv[2], UP = process.argv[3];
const FR = path.join(OUT, 'frames');
fs.mkdirSync(FR, { recursive: true });
const PHOTO1 = path.join(UP, 'IMG_20260616_123412.jpg');   // R7 중화요리 홍보각 70,000원 — 외부 교수 2명 참석
const PHOTO2 = path.join(UP, 'IMG_20260612_124528.jpg');   // R4 한식당 미가 24,000원 — 참여연구자 2명
const MIN1 = '2026-06-16 12:00~13:30 과제 협력 방향 논의 회의(장소: 중화요리 홍보각).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), 정수진(한국전자통신연구원), 이준호(서울대학교 부교수), 한지원(KAIST 박사과정).';
const MIN2 = '2026-06-12 12:00 과제 내부 점검 회의(장소: 한식당 미가).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원).';

const CURSOR = fs.readFileSync(path.join(__dirname, 'record_video.js'), 'utf8').match(/const CURSOR = (`[\s\S]*?`);/)[1];

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.2, locale: 'ko-KR', acceptDownloads: true });
  await ctx.addInitScript(eval(CURSOR));
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
  async function moveTo(x, y, steps = 30) { await page.mouse.move(x, y, { steps }); cur = [x, y]; }
  async function center(sel) {
    const el = page.locator(sel).first();
    await el.scrollIntoViewIfNeeded();
    const bx = await el.boundingBox();
    return [bx.x + bx.width / 2, bx.y + bx.height / 2];
  }
  async function hover(sel, pause = 700) { const [x, y] = await center(sel); await moveTo(x, y); await wait(pause); }
  async function click(sel, pause = 350) {
    const [x, y] = await center(sel);
    await moveTo(x, y); await wait(pause);
    await page.mouse.down(); await wait(90); await page.mouse.up();
  }
  async function nav(sel, urlRe) { await Promise.all([page.waitForURL(urlRe, { timeout: 30000 }), click(sel)]); await page.mouse.move(cur[0], cur[1]); }
  async function upload(photo, minutes) {
    const [fc] = await Promise.all([page.waitForEvent('filechooser'), click('label.file .btn')]);
    await wait(500);
    await fc.setFiles(photo);
    await wait(1300);                         // 썸네일이 붙는 걸 보여 준다
    await click('#text_doc');
    await wait(400);
    await page.fill('#text_doc', minutes);   // 회의록 문서에서 복사해 붙여 넣은 것처럼 한 번에
    await wait(1200);
  }
  async function judge() {
    await Promise.all([page.waitForURL(/\/case\/\d+$/, { timeout: 60000 }), click('#judge-btn')]);
    await page.mouse.move(cur[0], cur[1]);
    return page.getAttribute('.hero', 'data-verdict');
  }
  const out = {};

  // ── 영수증 1: R7 — 올리기 → 확인 화면 → 판정 가능 ──
  await page.goto(PJ + '/new');
  await page.mouse.move(700, 430); cur = [700, 430];
  await wait(600);
  rec = true;
  mark('a');
  await wait(900);
  await upload(PHOTO1, MIN1);
  await click('#extract-btn');
  mark('x1');
  await page.waitForSelector('#judge-form', { timeout: 300000 });
  mark('x1_end');
  await wait(900);
  for (const f of ['amount_total', 'date', 'vendor_name']) await hover(`#fields tr[data-f=${f}] .lab`, 800);
  const ext = page.locator('#att tbody tr', { hasText: '이준호' }).first();
  if (await ext.count()) { const bx = await ext.boundingBox(); await moveTo(bx.x + bx.width * 0.3, bx.y + bx.height / 2); await wait(1100); }
  out.v1 = await judge();
  mark('v1');
  await wait(700);
  await hover('.hero', 1600);
  await hover('details.stt > summary', 1300);
  mark('b');

  // ── 영수증 2: R4 — 올리기 → (확인 화면은 편집으로 건너뜀) → 판정 불가 → 안 되는 이유 ──
  await nav('.nav a[href="/new"]', /\/new$/);
  await wait(700);
  await upload(PHOTO2, MIN2);
  await click('#extract-btn');
  mark('x2');
  await page.waitForSelector('#judge-form', { timeout: 300000 });
  mark('x2_end');
  out.v2 = await judge();
  mark('v2');
  await wait(1100);
  await click('details.why > summary');
  await wait(2600);
  mark('c');

  // ── 대시보드: 쌓인 목록에서 행을 천천히 옮기며 미리보기 ──
  await nav('.nav a[href="/"]', /\/$/);
  await wait(1500);
  for (const i of [0, 1, 4]) await hover(`#cases tr.r:not([hidden]) >> nth=${i}`, 1700);
  mark('end');
  rec = false;
  await cdp.send('Page.stopScreencast');

  out.frames = nFrames; out.errors = errs;
  fs.writeFileSync(path.join(OUT, 'marks.json'), JSON.stringify({ marks, out }, null, 1));
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})().catch(e => { console.error('REC FAIL', e); process.exit(1); });
