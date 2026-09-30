// 시연 E2E — 새 화면(/new → 추출 → 확인 → 판정 303 /case/{id} → 수정 → 재판정) + 행정팀·보고서.
// 옛 e2e.js·e2e2.js·e2e3.js·e2e4.js(09-24 화면)를 한 대본으로 합쳤다. 기대 판정값은 그대로.
// 실행: NODE_PATH=~/workspace/03-agents/naver-agent/node_modules node tools/e2e/demo_e2e.js <캡처폴더>
// 서버 PJ_URL(기본 http://127.0.0.1:18080), 실제 모델(llama-server)로 추출한다. 빈 DB에서 시작할 것 — 끝나면 예외 사전·심판이 남는다.
const { chromium } = require('playwright');
const B = process.env.PJ_URL || 'http://127.0.0.1:18080';
const S = process.argv[2] || '.';
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: 'ko-KR' });
  const errs = [], external = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  page.on('request', r => { const h = new URL(r.url()).hostname; if (!['127.0.0.1', 'localhost'].includes(h) && !r.url().startsWith('data:')) external.push(r.url()); });
  const out = {}, fails = [];
  const expect = (name, ok, got) => { if (!ok) fails.push(`${name}: ${JSON.stringify(got)}`); };

  async function extract(n) {
    await page.goto(B + '/new?demo=all');
    await page.click(`#demo tbody tr:nth-child(${n})`);
    await page.click('#extract-btn');
    await page.waitForSelector('#judge-form', { timeout: 180000 });
  }
  async function verdict() {
    return {
      id: await page.getAttribute('[data-screen=case]', 'data-edit').then(s => s.split('/')[2]),
      v: await page.getAttribute('.hero', 'data-verdict'),
      rules: ((await page.getAttribute('.hero', 'data-rules')) || '').split(' ').filter(Boolean),   // 09-28: 규칙 ID는 화면 글자에서 빼고 속성으로 · 09-29: 판정 띠 → .hero
      notice: await page.getAttribute('.hero', 'data-notice'),
    };
  }
  async function judge() {
    await Promise.all([page.waitForURL(/\/case\/\d+$/, { timeout: 30000 }), page.click('#judge-btn')]);
    return verdict();
  }
  async function edit() {
    await page.click('#edit-btn');
    await page.waitForSelector('#judge-form');
  }
  async function openWhy() {  // 09-29: 조치 버튼은 ▸안 되는 이유(접힘) 안에 있다
    if (!(await page.$('details.why[open]'))) await page.click('details.why > summary');
  }
  async function post(sel) {  // 판정 상세의 일반 POST 폼(임시 승인·이의 신청) → 303 같은 주소
    await openWhy();
    await Promise.all([page.waitForNavigation({ timeout: 30000 }), page.click(sel)]);
  }

  // 시나리오 1: 외부 참석 회의 → 가능
  await extract(1);
  out.s1 = await judge();
  expect('s1 가능', out.s1.v === '가능', out.s1);
  await page.screenshot({ path: `${S}/50-s1-ok.png` });

  // 시나리오 2: 회의록 없음 8만 원 → 보완 → 수정: 간이 증명자료 → 가능 (옛 e2e4 참석자 6명 포함)
  await extract(2);
  out.s2_attendees = await page.$$eval('#att tbody tr', r => r.length);
  out.s2_amount = await page.inputValue('#judge-form [name=amount_total]');
  out.s2 = await judge();
  expect('s2 보완', out.s2.v === '보완', out.s2);
  await edit();
  await page.check('#judge-form [name=has_simplified_evidence]');
  out.s2_after = await judge();
  expect('s2 수정 후 가능', out.s2_after.v === '가능' && out.s2_after.id === out.s2.id, out.s2_after);

  // 시나리오 4: 참여연구자만 → 불가(제2026-38호) → W1 2025-03-10 불가+사전결재 → W0 2024-10-15 불가 → 기본사업 체크 가능
  await extract(4);
  await page.screenshot({ path: `${S}/51-s4-review.png` });
  out.s4_review = await page.evaluate(() => ({ sum: document.getElementById('f-sum').textContent, flag: document.getElementById('ab-flag').textContent }));
  out.s4 = await judge();
  expect('s4 불가 M-25-4-EXT', out.s4.v === '불가' && out.s4.rules.includes('M-25-4-EXT'), out.s4);
  await page.screenshot({ path: `${S}/52-s4-verdict.png` });
  await edit();
  await page.fill('#judge-form [name=date]', '2025-03-10');
  out.s4_w1 = await judge();
  expect('s4_w1 불가+M-25-4-PRE', out.s4_w1.v === '불가' && out.s4_w1.rules.includes('M-25-4-PRE'), out.s4_w1);
  await page.screenshot({ path: `${S}/53-s4-w1.png` });
  await edit();
  await page.fill('#judge-form [name=date]', '2024-10-15');
  out.s4_w0_nobasic = await judge();
  expect('s4_w0_nobasic 불가', out.s4_w0_nobasic.v === '불가', out.s4_w0_nobasic);
  await edit();
  await page.check('#judge-form [name=basic_project]');
  out.s4_w0 = await judge();
  expect('s4_w0 가능', out.s4_w0.v === '가능', out.s4_w0);
  await page.screenshot({ path: `${S}/54-s4-w0.png` });

  // 시나리오 6: 같은 기관 과제 미참여자 참석 → 가능(제2026-38호 완화) → 2025-03-10이면 불가(기관 기준)
  await extract(6);
  out.s6_participants = await page.$$eval('#att tbody tr', rs => rs.map(r => r.querySelectorAll('select.opt')[1].value));
  out.s6 = await judge();
  expect('s6 가능', out.s6.v === '가능' && !out.s6.rules.includes('M-25-4-EXT'), out.s6);
  await page.screenshot({ path: `${S}/55-s6-w2.png` });
  await edit();
  await page.fill('#judge-form [name=date]', '2025-03-10');
  out.s6_w1 = await judge();
  expect('s6_w1 불가', out.s6_w1.v === '불가', out.s6_w1);

  // 시나리오 3: 주말 회의 → 보완 → 임시 승인 → 행정팀 인정 + 예외 사전(M-INST-WKD) → 재투입 가능
  await extract(3);
  out.s3 = await judge();
  expect('s3 보완 M-INST-WKD', out.s3.v === '보완' && out.s3.rules.includes('M-INST-WKD'), out.s3);
  await post('form[action$="/approve"] button');
  out.s3_queue = (await page.textContent('.qline')).replace(/\s+/g, ' ').trim();
  expect('s3 임시승인 대기', /임시승인/.test(out.s3_queue) && /대기/.test(out.s3_queue), out.s3_queue);
  await page.screenshot({ path: `${S}/56-s3-approved.png` });
  await page.goto(B + '/admin');
  const rows = await page.$$('#queue tr.r');
  out.admin_clicked = false;
  for (const tr of rows) { if ((await tr.textContent()).includes('임시승인')) { await tr.click(); out.admin_clicked = true; break; } }
  await page.waitForSelector('#detail form.decide', { timeout: 15000 });
  out.rule_options = await page.$$eval('#detail select[name=rule_id] option', e => e.map(x => x.value));
  await page.screenshot({ path: `${S}/57-admin-detail.png` });
  await page.selectOption('#detail select[name=rule_id]', 'M-INST-WKD');
  await page.fill('#detail input[name=note]', '워크숍 정리 회의로 과제 관련성 확인');
  await page.click('#detail form.decide button.pri');
  await page.waitForFunction(() => !document.querySelector('#detail form.decide')
    && !!document.querySelector('#admin-panel tr[data-rule="M-INST-WKD"]'), null, { timeout: 15000 });
  await page.screenshot({ path: `${S}/58-admin-decided.png` });
  await extract(3);
  out.s3_again = await judge();
  out.s3_again_exception = (await page.textContent('.vm')).includes('예외 사전');
  expect('s3 재투입 가능(예외 사전)', out.s3_again.v === '가능' && out.s3_again_exception, out.s3_again);
  await page.screenshot({ path: `${S}/59-s3-exception.png` });

  // 시나리오 5: 국외 출장, 계획서 없음 → 보완
  await extract(5);
  await page.screenshot({ path: `${S}/60-s5-review.png` });
  out.s5 = await judge();
  expect('s5 보완 T-25-8-PLAN', out.s5.v === '보완' && out.s5.rules.includes('T-25-8-PLAN'), out.s5);
  await page.screenshot({ path: `${S}/61-s5-trip.png` });

  // 이의 신청: 시나리오 4 다시 → 불가 → 소명 → 이의 대기
  await extract(4);
  out.s4b = await judge();
  await openWhy();
  await page.fill('form[action$="/appeal"] input[name=statement]', '외부 자문위원(KAIST 박민수)이 실제 참석');
  await post('form[action$="/appeal"] button');
  out.s4b_queue = (await page.textContent('.qline')).replace(/\s+/g, ' ').trim();
  expect('이의 대기', /이의/.test(out.s4b_queue) && /대기/.test(out.s4b_queue), out.s4b_queue);

  // 보고서 4종 내려받기
  for (const k of ['usage', 'audit', 'appeal', 'annex']) {
    const r = await page.request.get(`${B}/reports/${k}.hwpx`);
    out['report_' + k] = r.status();
    expect('보고서 ' + k, r.status() === 200, r.status());
  }
  await page.goto(B + '/reports'); await page.screenshot({ path: `${S}/62-reports.png` });

  // 목록: 필터·검색
  await page.goto(B + '/');
  await page.waitForSelector('#pv .pv-h', { timeout: 5000 }).catch(() => {});
  await page.screenshot({ path: `${S}/63-list.png` });
  out.list_rows = await page.$$eval('#rows tr.r', r => r.length);
  await page.click('#flt button[data-v=bad]');
  out.list_bad = await page.$$eval('#rows tr.r:not([hidden])', r => r.map(x => x.dataset.v));
  expect('불가 필터', out.list_bad.length > 0 && out.list_bad.every(v => v === 'bad'), out.list_bad);
  await page.click('#flt button[data-v=all]');
  await page.fill('#q', 'M-INST-WKD');
  out.list_search = { hint: await page.textContent('#qhint'), n: await page.textContent('#f-n') };
  await page.keyboard.press('Escape');
  await page.keyboard.press('j');
  await page.screenshot({ path: `${S}/64-list-search.png` });
  await page.goto(B + '/admin'); await page.screenshot({ path: `${S}/65-admin.png` });

  out.errors = errs; out.external = external; out.fails = fails;
  console.log(JSON.stringify(out, null, 1));
  await b.close();
  if (fails.length || errs.length || external.length) { console.error('E2E FAIL', fails, errs, external); process.exit(1); }
  console.log('E2E PASS');
})().catch(e => { console.error('E2E FAIL', e); process.exit(1); });
