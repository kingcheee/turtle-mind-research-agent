// 정답지의 영수증 텍스트를 카드매출전표 모양(폭 380px, Pretendard)으로 그려 PNG로 — OCR 경로 검증용 이미지 20장.
// 사용: NODE_PATH=~/workspace/03-agents/naver-agent/node_modules node data/render_receipts.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const KEY = path.join(__dirname, 'answer_key.json');
const OUT = path.join(__dirname, 'images');
const FONTS = path.join(ROOT, 'panjeong', 'web', 'static', 'fonts');

function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
function html(text) {
  const lines = text.split('\n');
  const body = lines.map((l, i) => {
    const cls = i === 0 ? 'h' : (l.startsWith('합계') ? 't' : '');
    return `<div class="${cls}">${esc(l)}</div>`;
  }).join('');
  return `<!doctype html><meta charset="utf-8"><style>
@font-face{font-family:P;src:url(file://${FONTS}/Pretendard-Regular.ttf);font-weight:400}
@font-face{font-family:P;src:url(file://${FONTS}/Pretendard-Bold.ttf);font-weight:700}
body{margin:0;background:#cfd3d8}
.r{width:380px;padding:24px 20px;background:#fff;font-family:P,sans-serif;font-size:16px;line-height:1.75;color:#111}
.r div{white-space:pre-wrap;word-break:break-all}
.r .h{font-weight:700;font-size:19px;text-align:center;margin-bottom:10px}
.r .t{font-weight:700;font-size:18px;margin-top:8px;border-top:1px dashed #444;padding-top:8px}
</style><body><div class="r">${body}</div>`;
}

(async () => {
  const key = JSON.parse(fs.readFileSync(KEY, 'utf8'));
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 420, height: 700 }, deviceScaleFactor: 2 });
  let n = 0;
  const tmp = path.join(OUT, '_tmp.html');
  for (const c of key) {
    if (!c.image) continue;
    const doc = c.docs.find(d => d.kind === '영수증');
    if (!doc) continue;
    fs.writeFileSync(tmp, html(doc.text));
    await page.goto('file://' + tmp);
    await page.evaluate(() => document.fonts.ready);
    const el = await page.$('.r');
    await el.screenshot({ path: path.join(OUT, `${c.id}.png`) });
    n++;
  }
  fs.unlinkSync(tmp);
  console.log(`rendered ${n} → ${OUT}`);
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
