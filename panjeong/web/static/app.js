/* 연구비 판정관 — 화면 동작 (design.md §7·§8·§10).
   판정은 서버 규칙엔진이 한다. 여기서는 보기·입력 편의(필터, 미리보기, 원문 대조, 키보드)만 다룬다. */
(function () {
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const won = n => Number(n || 0).toLocaleString('ko-KR');
const pad = n => String(n).padStart(2, '0');
const screenEl = () => $('[data-screen]');
const screen = () => { const s = screenEl(); return s ? s.dataset.screen : ''; };
const typing = el => !!(el && el.matches && el.matches('input,textarea,select,[contenteditable="true"]'));
const CHECK = '<svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.4 6.3 4.8 8.6 9.6 3.6" fill="none" stroke="currentColor" stroke-width="2"/></svg>';

/* ── 공통: 분할선 끌기 (시안 02 로직) — 위임이라 HTMX로 바뀐 본문에도 먹는다 ── */
document.addEventListener('mousedown', e => {
  const sp = e.target.closest && e.target.closest('.sp');
  if (!sp || e.button !== 0) return;
  const prev = sp.dataset.t === 'prev';
  const tgt = prev ? sp.previousElementSibling : sp.nextElementSibling;
  const other = prev ? sp.nextElementSibling : sp.previousElementSibling;
  if (!tgt) return;
  e.preventDefault();
  const x = sp.classList.contains('sp-x');
  const dim = el => { const r = el.getBoundingClientRect(); return x ? r.width : r.height; };
  const sign = prev ? 1 : -1;
  const start = x ? e.clientX : e.clientY;
  const size = dim(tgt);
  const max = Math.max(120, size + (other ? dim(other) : 0) - 120);  // 반대쪽도 120px은 남긴다
  sp.classList.add('drag');
  document.body.style.cursor = x ? 'col-resize' : 'row-resize';
  const mv = ev => {
    const v = Math.min(max, Math.max(120, size + sign * ((x ? ev.clientX : ev.clientY) - start)));
    if (x) tgt.style.flex = `0 0 ${v}px`; else tgt.style.height = v + 'px';
  };
  const up = () => {
    sp.classList.remove('drag'); document.body.style.cursor = '';
    removeEventListener('mousemove', mv); removeEventListener('mouseup', up);
  };
  addEventListener('mousemove', mv); addEventListener('mouseup', up);
});

/* ── 공통: 행 클릭 → 이동 (안의 링크·버튼·입력은 그대로) ── */
document.addEventListener('click', e => {
  const tr = e.target.closest && e.target.closest('tr[data-href]');
  if (!tr || e.target.closest('a,button,input,select,textarea,label')) return;
  if (e.metaKey || e.ctrlKey) window.open(tr.dataset.href); else location.href = tr.dataset.href;
});

/* ── 공통: 체크 항목 — label.on 이 실제 체크 상태를 따른다 ── */
document.addEventListener('change', e => {
  const t = e.target;
  if (t.matches && t.matches('.chk input[type=checkbox]')) t.closest('label').classList.toggle('on', t.checked);
});

/* ── 행정팀: 큐에서 고른 행 표시 (패널이 통째로 바뀌므로 위임) ── */
document.addEventListener('click', e => {
  const tr = e.target.closest && e.target.closest('#queue tr.r');
  if (!tr) return;
  $$('#queue tr.r.cur').forEach(r => r.classList.remove('cur'));
  tr.classList.add('cur');
});

/* ── HTMX 요청 실패 — 토스트 대신 액션 바에 한 줄 ── */
function requestFailed(e) {
  const src = e.detail && e.detail.elt;
  const ab = src && (src.closest('form') || src).querySelector('.ab');
  if (!ab) return;
  let m = $('.req-err', ab);
  if (!m) { m = document.createElement('span'); m.className = 'flag bad req-err'; ab.insertBefore(m, ab.firstChild); }
  m.innerHTML = '<i class="sh bad"></i>서버 요청 실패 — 다시 시도';
}
document.addEventListener('htmx:responseError', requestFailed);
document.addEventListener('htmx:sendError', requestFailed);

/* ════════ 건 목록 ════════ */
const List = {
  init(sec) {
    this.sec = sec;
    this.rows = $$('#rows tr.r', sec);
    this.v = 'all'; this.cur = null; this.pvId = null; this.vis = [];
    const q = $('#q');
    this.qRaw = q ? q.value.trim() : '';
    const flt = $('#flt', sec);
    if (flt) flt.addEventListener('click', e => {
      const b = e.target.closest('button[data-v]');
      if (!b) return;
      this.v = b.dataset.v;
      $$('button[data-v]', flt).forEach(x => x.classList.toggle('on', x === b));
      this.apply();
    });
    if (q) {
      q.addEventListener('input', () => {
        this.qRaw = q.value.trim();
        this.apply();
        try { history.replaceState(null, '', this.qRaw ? '/?q=' + encodeURIComponent(this.qRaw) : '/'); } catch (_) {}
      });
      q.form.addEventListener('submit', e => { e.preventDefault(); q.blur(); });  // 목록에선 즉석 필터
    }
    const body = $('#rows', sec);
    if (body) body.addEventListener('mouseover', e => {
      const tr = e.target.closest('tr.r');
      if (tr && tr !== this.cur) this.setCur(tr, false);
    });
    this.apply();
  },
  apply() {
    const q = this.qRaw.toLowerCase();
    const cnt = { all: 0, ok: 0, warn: 0, bad: 0 }, sum = { ok: 0, warn: 0, bad: 0 };
    let tot = 0;
    const vis = [];
    for (const r of this.rows) {
      const v = r.dataset.v;
      const qOk = !q || (r.dataset.q || '').toLowerCase().includes(q);
      if (qOk) { cnt.all++; if (v in cnt) cnt[v]++; }
      const show = qOk && (this.v === 'all' || v === this.v);
      r.hidden = !show;
      if (show) {
        vis.push(r);
        const a = Number(r.dataset.amt) || 0;
        tot += a;
        if (v in sum) sum[v] += a;
      }
    }
    this.vis = vis;
    $$('#flt .n[data-c]', this.sec).forEach(n => { n.textContent = cnt[n.dataset.c] || 0; });
    const fn = $('#f-n', this.sec); if (fn) fn.textContent = vis.length + '건';
    $$('[data-sum]', this.sec).forEach(s => { s.textContent = won(sum[s.dataset.sum]); });
    const ft = $('#f-tot', this.sec); if (ft) ft.textContent = won(tot);
    const nm = $('#rows tr.nomatch', this.sec); if (nm) nm.hidden = !(this.rows.length && !vis.length);
    const hint = $('#qhint', this.sec); if (hint) hint.textContent = q ? `검색 「${this.qRaw}」 · ${vis.length}건` : '';
    if (!this.cur || this.cur.hidden) this.setCur(vis[0] || null, false);
  },
  setCur(tr, scroll) {
    if (this.cur) this.cur.classList.remove('cur');
    this.cur = tr;
    if (!tr) { this.preview(null); return; }
    tr.classList.add('cur');
    if (scroll) tr.scrollIntoView({ block: 'nearest' });
    this.preview(tr.dataset.id);
  },
  preview(id) {
    clearTimeout(this.timer);
    if (id === this.pvId) return;
    const pv = $('#pv', this.sec);
    if (!pv || !pv.offsetParent) return;   // 폰 배치에선 미리보기를 숨긴다(행을 누르면 바로 판정 상세)
    if (!id) { this.pvId = null; pv.innerHTML = ''; return; }
    this.timer = setTimeout(async () => {
      this.pvId = id;
      try {
        const r = await fetch('/case/' + id + '/preview');
        if (!r.ok) throw new Error(r.status);
        const html = await r.text();
        if (this.pvId === id) pv.innerHTML = html;
      } catch (_) { if (this.pvId === id) { pv.innerHTML = ''; this.pvId = null; } }
    }, 80);
  },
  move(d) {
    const vis = this.vis;
    if (!vis.length) return;
    let i = vis.indexOf(this.cur);
    i = i < 0 ? 0 : Math.min(vis.length - 1, Math.max(0, i + d));
    this.setCur(vis[i], true);
  },
  key(e) {
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); this.move(1); }
    else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); this.move(-1); }
    else if (e.key === 'Enter' && this.cur) location.href = '/case/' + this.cur.dataset.id;
    else if (e.key === 'n' || e.key === 'N') location.href = '/new';
  },
};

/* ════════ 새 증빙 · 올리기 ════════ */
const New = {
  init(sec) {
    const form = $('#up-form', sec);
    if (!form) return;
    this.form = form;
    const ta = $('#text_doc', form), files = $('#files', form), kind = $('[name=text_doc_type]', form);
    const fkind = $('[name=file_doc_type]', form);
    const dph = $('#demo_photo', form), dbox = $('#demo-ph', form);
    const sum = () => {
      const d = dph && dph.value ? 1 : 0, n = files ? files.files.length : 0, t = ta ? ta.value.trim().length : 0;
      const parts = [];
      if (d) parts.push('사진 1 (영수증)');
      if (n) parts.push(`사진 ${n}${fkind ? ' (' + fkind.value + ')' : ''}`);
      if (t) parts.push(`텍스트 ${t.toLocaleString('ko-KR')}자${kind ? ' (' + kind.value + ')' : ''}`);
      $('#up-sum', form).textContent = parts.join(' · ') || '문서 없음';
      return d + n + t;
    };
    this.sum = sum;
    // 시연 행의 Gemini 영수증 사진 — 폼에는 이름만(demo_photo), 서버가 사진을 영수증 문서로 붙여 OCR한다
    const setPhoto = name => {
      if (!dph || !dbox) return;
      dph.value = name || '';
      dbox.hidden = !name;
      if (name) $('img', dbox).src = '/demo-photos/' + name;
    };
    if (dbox) $('#demo-ph-x', dbox).addEventListener('click', () => { setPhoto(''); sum(); });
    const pick = tr => {
      if (ta) ta.value = tr.dataset.text;
      if (kind) kind.value = tr.dataset.kind;
      setPhoto(tr.dataset.photo);
      $$('#demo tr.r', sec).forEach(r => r.classList.toggle('cur', r === tr));
      sum();
    };
    const demo = $('#demo', sec);
    if (demo) {
      demo.addEventListener('click', e => { const tr = e.target.closest('tr.r'); if (tr) pick(tr); });
      demo.addEventListener('keydown', e => {
        const tr = e.target.closest('tr.r');
        if (!tr) return;
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(tr); }
        else if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); (tr.nextElementSibling || tr).focus(); }
        else if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); (tr.previousElementSibling || tr).focus(); }
      });
    }
    if (files) files.addEventListener('change', () => {
      const names = Array.from(files.files).map(f => f.name);
      $('#file-n', form).textContent = names.length ? `파일 ${names.length}개 · ${names.join(', ')}` : '선택한 파일 없음';
      sum();
    });
    if (ta) ta.addEventListener('input', sum);
    form.addEventListener('change', e => { if (e.target === kind || e.target === fkind) sum(); });
    // 문서가 하나도 없으면 서버에 보내지 않는다 — 입력 화면을 잃지 않게
    form.addEventListener('htmx:beforeRequest', e => {
      if (e.target !== form || sum()) return;
      e.preventDefault();
      $('#up-sum', form).innerHTML = '<span class="flag bad"><i class="sh bad"></i>문서 없음 — 사진이나 텍스트를 넣어야 추출한다</span>';
    });
    sum();
  },
  submit() { if (this.form) this.form.requestSubmit(); },
};

/* ════════ 확인 — 원문 대조 (옛 extract_form 로직을 새 마크업으로) ════════
   필드 값을 원문에서 찾아 번호를 매기고, 못 찾거나 추정한 값은 「확인 요망」, 비어 있는 필수값은 「차단 오류」.
   판정에는 관여하지 않는다 — 고친 값이 그대로 판정 입력이 된다. */
const ALC = ['소주', '맥주', '생맥주', '주류', '와인', '막걸리', '하이볼', '사케', '양주', '위스키', '칵테일', '고량주'];
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
function dateVariants(d) {
  const out = [d];
  const m = d.match(DATE_RE);
  if (m) {
    const y = m[1], mo = +m[2], da = +m[3];
    out.push(`${y}년 ${mo}월 ${da}일`, d.replace(/-/g, '.'), `${y}. ${mo}. ${da}.`, `${y}.${mo}.${da}`, d.replace(/-/g, '/'), `${mo}월 ${da}일`);
  }
  return out;
}

const Review = {
  init(form) {
    this.form = form;
    this.ev = $('#ev');
    this.hotEl = null;
    this.lines = $$('#ev .src .ln > span[data-raw]').map(sp => {
      if (!sp.dataset.raw) sp.dataset.raw = sp.textContent;
      const i = sp.previousElementSibling;
      return { sp, raw: sp.dataset.raw, doc: sp.closest('.doc'), kind: sp.closest('.doc').dataset.kind, no: i ? i.textContent.trim() : '' };
    });
    let t;
    const later = ms => { clearTimeout(t); t = setTimeout(() => this.run(), ms); };
    form.addEventListener('change', e => {
      const el = e.target;
      if (el.name === 'category') { const tb = $('#tripbox', form); if (tb) tb.hidden = el.value !== '출장비'; }
      later(0);
    });
    form.addEventListener('input', e => { if (e.target.matches('input[type=text],input[type=number]')) later(300); });
    form.addEventListener('submit', () => this.syncAtt());
    const add = $('#att-add', form);
    if (add) add.addEventListener('click', () => this.addAtt());
    const att = $('#att', form);
    if (att) att.addEventListener('click', e => {
      const x = e.target.closest('button.x');
      if (!x) return;
      x.closest('tr').remove();
      this.renumberAtt();
      this.run();
    });
    // 필드 ↔ 원문 서로 밝히기
    form.addEventListener('mouseover', e => this.hot(e.target.closest('[data-f]')));
    form.addEventListener('mouseleave', () => this.hot(null));
    if (this.ev) this.ev.addEventListener('click', e => {
      const m = e.target.closest('mark[data-f]');
      if (!m) return;
      const tr = $(`tr[data-f="${m.dataset.f.split(' ')[0]}"]`, form);
      const inp = tr && $('input,select', tr);
      if (!inp) return;
      tr.scrollIntoView({ block: 'nearest' });
      inp.focus();
    });
    this.run();
  },

  val(n) { const el = this.form.elements[n]; return el && el.value != null ? String(el.value).trim() : ''; },

  /* 원문에서 needle 하나를 찾아 범위를 잡는다. 겹치지 않는 자리를 먼저, 없으면 이미 잡힌 마크를 같이 쓴다. */
  place(key, needles, est) {
    const list = needles.filter(s => s != null).map(s => String(s).trim()).filter(s => s.length >= 2);
    const overlap = (L, i, len) => L.ranges.find(r => i < r.i + r.len && r.i < i + len);
    for (const s of list) for (const L of this.lines) {
      for (let i = L.raw.indexOf(s); i >= 0; i = L.raw.indexOf(s, i + 1)) {
        if (overlap(L, i, s.length)) continue;
        const r = { i, len: s.length, keys: [key], est: est ? [key] : [] };
        L.ranges.push(r);
        return { L, r, s };
      }
    }
    for (const s of list) for (const L of this.lines) {
      const i = L.raw.indexOf(s);
      if (i < 0) continue;
      const r = overlap(L, i, s.length);
      if (!r) continue;
      if (!r.keys.includes(key)) r.keys.push(key);
      if (est && !r.est.includes(key)) r.est.push(key);
      return { L, r, s };
    }
    return null;
  },
  /* needle 이 나오는 문서마다 첫 줄 — 여러 문서에서 찾으면 출처에 모두 적는다 */
  docsWith(needles) {
    const seen = new Map();
    for (const L of this.lines) {
      if (seen.has(L.doc)) continue;
      if (needles.some(s => s && s.length >= 2 && L.raw.includes(s))) seen.set(L.doc, L);
    }
    return Array.from(seen.values());
  },
  src(L, extra) { return L ? `${esc(L.kind)} <span class="mono">L${L.no}</span>${extra || ''}` : ''; },

  run() {
    const f = this.form, V = n => this.val(n);
    for (const L of this.lines) L.ranges = [];
    $$('tr.why', f).forEach(tr => tr.remove());
    $$('tr[data-f]', f).forEach(tr => {
      tr.classList.remove('est', 'err', 'has-why');
      for (const c of ['.rn', '.srcref', '.cmp']) { const td = $(c, tr); if (td) td.innerHTML = ''; }
    });
    const res = new Map();
    const R = (key, st, src, why, hit) => { res.set(key, { st, src: src || '', why: why || '', hit }); };
    const ground = (key, needles, missWhy, opt = {}) => {
      const h = this.place(key, needles, opt.est);
      if (h) R(key, opt.est ? 'est' : 'ok', this.src(h.L, opt.extra ? opt.extra(h) : ''), opt.est ? missWhy : '', h);
      else R(key, 'est', '원문에 없음', missWhy);
      return h;
    };

    // 목적 — 긴 문구를 먼저 놓아야 「회의」 같은 짧은 근거가 겹치지 않는 다른 자리를 찾는다
    const pu = V('purpose');
    if (!pu) R('purpose', 'est', '', '목적 없음 — 회의·출장 목적을 적을 것');
    else ground('purpose', [pu], '원문에 없는 문구 — 모델이 요약한 값일 수 있음');

    // 비목
    const cat = V('category');
    if (cat === '회의비') ground('category', ['회의', '미팅', '워크숍'], '원문에 회의 근거 없음 — 비목을 확인할 것');
    else if (cat === '출장비') ground('category', ['출장'], '원문에 출장 근거 없음 — 비목을 확인할 것');
    else R('category', 'est', '', '비목 불명 — 회의비·출장비 중 고를 것');

    // 집행일 — 필수. 적용 고시(기준일)를 정한다
    const d = V('date');
    if (!d) R('date', 'err', '', '값 없음 — 집행일이 적용 고시(기준일)를 정함');
    else {
      const dv = dateVariants(d);
      const h = this.place('date', dv);
      if (h) {
        const docs = this.docsWith(dv);
        R('date', 'ok', docs.length > 1 ? docs.map(L => this.src(L)).join(' · ') : this.src(h.L), '', h);
      } else R('date', 'est', '원문에 없음', '원문에서 날짜를 찾지 못함 — 영수증 날짜로 고칠 것');
    }

    // 시각
    const tm = V('time');
    if (!tm) R('time', 'est', '', '원문에 시각 없음 — 점심시간 판정(제25조 제14항)에 씀');
    else {
      const [hh, mm] = tm.split(':');
      ground('time', [tm, tm.replace(/^0/, ''), `${+hh}시 ${+mm}분`, +mm ? null : `${+hh}시`], '원문에서 시각을 찾지 못함');
    }

    // 금액 — 필수
    const am = V('amount_total');
    if (!am) R('amount_total', 'err', '', '값 없음 — 금액을 넣을 것');
    else {
      const num = Number(am), fmt = num.toLocaleString('ko-KR');
      ground('amount_total', [fmt + '원', fmt, num + '원', String(num)], '원문에서 금액을 찾지 못함 — 여러 영수증의 합산값일 수 있음',
        { extra: h => (/합계|총액|합 계|TOTAL/i.test(h.L.raw) ? ' · 합계' : '') });
    }

    // 부가세
    const VAT_IN = ['부가세 포함', '부가가치세 포함', 'VAT 포함', '부가세포함', 'VAT포함'];
    const VAT_EX = ['부가세 별도', '부가가치세 별도', 'VAT 별도', '부가세별도', 'VAT별도'];
    const vat = V('vat_included');
    if (vat === 'true') ground('vat_included', VAT_IN, '원문에 「부가세 포함」 표기 없음');
    else if (vat === 'false') ground('vat_included', VAT_EX, '원문에 「부가세 별도」 표기 없음');
    else {
      const h = this.place('vat_included', VAT_IN.concat(VAT_EX), true);
      R('vat_included', 'est', h ? this.src(h.L) : '', h ? `원문에 「${h.s}」 — 값을 고를 것` : '원문에 부가세 표기 없음 — 10만 원 경계에 걸리면 고칠 것', h);
    }

    // 가맹점 — 판정 입력이 아니라 원문에 없으면 중립
    const vn = V('vendor_name');
    const vh = vn ? this.place('vendor_name', [vn]) : null;
    if (vh) R('vendor_name', 'ok', this.src(vh.L), '', vh);
    else R('vendor_name', 'neu', vn ? '원문에 없음' : '');

    // 업종 — 상호·품목에서 추정한 값이라 항상 확인
    const vt = V('vendor_type');
    const th = this.place('vendor_type', [vn, vt], true);
    R('vendor_type', 'est', th ? this.src(th.L, ' · 추정') : '추정',
      vt ? '원문에 업종 표기 없음 — 상호·품목에서 추정한 값' : '업종 모름 — 상호·품목을 보고 고를 것', th);

    // 주류
    const al = V('has_alcohol');
    const alcIn = ALC.find(w => this.lines.some(L => L.raw.includes(w)));
    if (al === 'true') ground('has_alcohol', ALC, '원문에서 주류 품목을 찾지 못함');
    else if (al === 'false') {
      if (alcIn) { const h = this.place('has_alcohol', [alcIn], true); R('has_alcohol', 'est', this.src(h && h.L), `원문에 「${alcIn}」 — 주류가 있을 수 있음`, h); }
      else R('has_alcohol', 'ok', '원문에 주류 키워드 없음');
    } else {
      const h = alcIn ? this.place('has_alcohol', [alcIn], true) : null;
      R('has_alcohol', 'est', h ? this.src(h.L) : '', h ? `원문에 「${alcIn}」 — 값을 고를 것` : '주류 여부 모름 — 품목에 주류가 없으면 「없음」', h);
    }

    // 참석 인원 — 명단과 교차 확인
    const attRows = $$('#att tbody tr', f);
    const ac = V('attendee_count');
    const ch = ac ? this.place('attendee_count', [ac + '명', '참석 ' + ac, ac + ' 명']) : null;
    const list = `명단 <span class="mono">${attRows.length}명</span>`;
    if (!attRows.length) R('attendee_count', 'est', ch ? this.src(ch.L) : '', ac ? '참석자 명단 없음 — 1인 한도 판정에 명단이 쓰임' : '참석 인원·명단 모두 없음 — 1인 한도(3만 원) 판정에 씀', ch);
    else if (String(attRows.length) === ac) R('attendee_count', 'ok', ch ? this.src(ch.L, ' · ' + list) : list, '', ch);
    else R('attendee_count', 'est', ch ? this.src(ch.L, ' · ' + list) : list, `명단 ${attRows.length}명과 다름 — 둘 중 하나를 고칠 것`, ch);

    // 출장
    const trip = $('#tripbox', f);
    if (trip && !trip.hidden) {
      const dest = V('trip_destination');
      if (!dest) R('trip_destination', 'est', '', '출장지 없음 — 국외 여부(제25조 제8항) 판정에 씀');
      else ground('trip_destination', [dest], '원문에서 출장지를 찾지 못함');
      for (const [k, lab] of [['trip_start', '시작일'], ['trip_end', '종료일']]) {
        const v = V(k);
        if (!v) R(k, 'est', '', `출장 ${lab} 없음`);
        else ground(k, dateVariants(v), `원문에서 ${lab}을 찾지 못함`);
      }
      const dom = V('trip_domestic');
      if (dom === 'false') ground('trip_domestic', ['국외', '해외'], '원문에 「국외」 표기 없음 — 출장지에서 추정한 값');
      else if (dom === 'true') ground('trip_domestic', ['국내'], '원문에 「국내」 표기 없음 — 출장지에서 추정한 값');
      else R('trip_domestic', 'est', '', '국내외 모름 — 국외면 계획서·결과보고서(제25조 제8항)');
    }

    // 참석자 — 이름을 원문에서 찾는다 (번호 배지 없이 마크만)
    let nIn = 0, nEx = 0, nOut = 0;
    attRows.forEach((tr, i) => {
      if (!tr.dataset.f) tr.dataset.f = 'p' + (i + 1);
      const name = ($('input[type=text]', tr) || {}).value || '';
      const h = name.trim().length >= 2 ? this.place(tr.dataset.f, [name.trim()]) : null;
      const cell = $('.srcref', tr);
      const basis = ((cell && cell.dataset.basis) || '').replace(/^\s*·\s*/, '');
      if (cell) cell.innerHTML = (h ? this.src(h.L) : '<span class="mut">원문에 없음</span>') + (basis ? ' · ' + esc(basis) : '');
      const [ext, part] = $$('select.opt', tr);
      if (ext) { ext.classList.toggle('hi', ext.value === 'true'); if (ext.value === 'true') nEx++; else if (ext.value === 'false') nIn++; }
      if (part) { part.classList.toggle('hi', part.value === 'false'); if (part.value === 'false') nOut++; }
    });
    const an = $('#att-n', f); if (an) an.textContent = attRows.length;
    const as = $('#att-sum', f);
    if (as) as.textContent = attRows.length ? `내부 ${nIn} · 외부 ${nEx} · 과제 미참여 ${nOut}` : '';

    // 번호는 필드 표 순서대로 — 원문에 잡힌 필드만
    const nums = new Map();
    let n = 0;
    $$('#fields tr[data-f], #tripf tr[data-f]', f).forEach(tr => {
      const r = res.get(tr.dataset.f);
      if (r && r.hit) nums.set(tr.dataset.f, ++n);
    });

    // 원문 줄 다시 그리기
    for (const L of this.lines) {
      const arr = L.ranges.slice().sort((a, b) => a.i - b.i);
      let out = '', pos = 0;
      for (const r of arr) {
        const keys = r.keys.slice().sort((a, b) => (nums.get(a) || 99) - (nums.get(b) || 99));
        const badges = keys.filter(k => nums.has(k)).map(k => `<b class="ref${r.est.includes(k) ? ' est' : ''}">${pad(nums.get(k))}</b>`).join('');
        const allEst = r.est.length && r.keys.every(k => r.est.includes(k));
        out += esc(L.raw.slice(pos, r.i)) + `<mark data-f="${keys.join(' ')}"${allEst ? ' class="est"' : ''}>${badges}${esc(L.raw.slice(r.i, r.i + r.len))}</mark>`;
        pos = r.i + r.len;
      }
      L.sp.innerHTML = out + esc(L.raw.slice(pos));
    }

    // 필드 행 채우기
    let ok = 0, est = 0, err = 0, total = 0;
    const FLAG = { est: '<span class="flag warn"><i class="sh warn"></i>확인 요망</span>', err: '<span class="flag bad"><i class="sh bad"></i>차단 오류</span>' };
    $$('#fields tr[data-f], #tripf tr[data-f]', f).forEach(tr => {
      const r = res.get(tr.dataset.f);
      if (!r) return;
      total++;
      const num = nums.get(tr.dataset.f);
      $('.rn', tr).innerHTML = num ? `<b class="ref${r.st === 'est' ? ' est' : ''}">${pad(num)}</b>` : '';
      $('.srcref', tr).innerHTML = r.src;
      $('.cmp', tr).innerHTML = r.st === 'ok' ? `<span class="okm">${CHECK}일치</span>` : r.st === 'neu' ? '<span class="mut">—</span>' : FLAG[r.st];
      if (r.st === 'ok') ok++;
      if (r.st === 'est' || r.st === 'err') {
        r.st === 'est' ? est++ : err++;
        tr.classList.add(r.st);
        if (r.why) {
          tr.classList.add('has-why');
          tr.insertAdjacentHTML('afterend', `<tr class="why ${r.st}"><td></td><td></td><td colspan="3">${esc(r.why)}</td></tr>`);
        }
      }
    });
    const ftot = $('#f-total', f); if (ftot) ftot.textContent = total;
    const fsum = $('#f-sum', f);
    if (fsum) fsum.innerHTML = `원문 일치 <span class="mono">${ok}</span> · 확인 요망 <span class="mono">${est}</span>` + (err ? ` · 차단 오류 <span class="mono">${err}</span>` : '');
    const flag = $('#ab-flag', f);
    if (flag) flag.innerHTML = (err ? `<span class="flag bad"><i class="sh bad"></i>차단 오류 ${err}</span> ` : '') + (est ? `<span class="flag warn"><i class="sh warn"></i>확인 요망 ${est}</span>` : '');
    const abs = $('#ab-sum', f);
    if (abs) abs.textContent = `필드 ${total} · 원문 일치 ${ok} · 참석자 ${attRows.length}`;
    if (this.hotEl && !document.contains(this.hotEl)) this.hotEl = null;
  },

  hot(el) {
    if (el === this.hotEl) return;
    $$('.hot', this.form).forEach(x => x.classList.remove('hot'));
    this.hotEl = el;
    let marks = 0;
    if (el) for (const k of el.dataset.f.split(' ')) {
      $$(`[data-f~="${k}"]`, this.form).forEach(x => { x.classList.add('hot'); if (x.tagName === 'MARK') marks++; });
    }
    if (this.ev) this.ev.classList.toggle('dim', marks > 0);
  },

  addAtt() {
    const body = $('#att tbody', this.form);
    const used = new Set($$('tr[data-f]', body).map(tr => tr.dataset.f));
    let k = body.children.length + 1;
    while (used.has('p' + k)) k++;
    const tr = document.createElement('tr');
    tr.dataset.f = 'p' + k;
    tr.innerHTML = '<td class="mono mut"></td>'
      + '<td><span class="val"><input type="text" aria-label="이름"></span></td>'
      + '<td><span class="val"><input type="text" aria-label="소속"></span></td>'
      + '<td><select class="opt" aria-label="기관"><option value="null">모름</option><option value="true">외부</option><option value="false">내부</option></select></td>'
      + '<td><select class="opt" aria-label="과제"><option value="null">모름</option><option value="true">참여</option><option value="false">미참여</option></select></td>'
      + '<td class="srcref"></td>'
      + '<td><button class="btn icon sm x" type="button" title="삭제" aria-label="삭제">×</button></td>';
    body.appendChild(tr);
    this.renumberAtt();
    this.run();
    $('input', tr).focus();
  },
  renumberAtt() { $$('#att tbody tr', this.form).forEach((tr, i) => { tr.cells[0].textContent = i + 1; }); },

  syncAtt() {
    const tri = v => (v === 'null' || v === '' ? null : v === 'true');
    const rows = $$('#att tbody tr', this.form).map(tr => {
      const [n, a] = $$('input[type=text]', tr);
      const [e, p] = $$('select.opt', tr);
      return { name: n ? n.value.trim() : '', affiliation: (a && a.value.trim()) || null, external: e ? tri(e.value) : null, participant: p ? tri(p.value) : null };
    }).filter(r => r.name);
    const h = $('#attendees_json', this.form);
    if (h) h.value = JSON.stringify(rows);
  },
  submit() { this.syncAtt(); this.form.requestSubmit(); },
  key(e) {
    if (e.key === 'r' || e.key === 'R') { const b = $('#re-extract', this.form); if (b) { e.preventDefault(); b.click(); } }
  },
};

/* ════════ 판정 상세 ════════ */
const Case = {
  init(sec) {
    this.sec = sec;
    sec.addEventListener('click', e => {
      const b = e.target.closest('.tl button[data-code]');
      if (!b) return;
      const p = b.closest('.panel'), bq = $('blockquote', p), tpl = $('template', b);
      if (!bq) return;
      if (bq.dataset.orig == null) bq.dataset.orig = bq.innerHTML;  // 적용 구간은 판정 구절 마크가 있는 원래 인용으로 되돌린다
      const applied = b.classList.contains('applied');
      bq.innerHTML = applied ? bq.dataset.orig : (tpl ? tpl.innerHTML : bq.innerHTML);
      $$('.tl button', p).forEach(x => x.classList.toggle('view', x === b));
      const note = $('.stt-note', p);
      if (note) note.hidden = applied;
    });
  },
  key(e) {
    const d = this.sec.dataset;
    if (e.key === '[' && d.prev) location.href = d.prev;
    else if (e.key === ']' && d.next) location.href = d.next;
    else if ((e.key === 'e' || e.key === 'E') && d.edit) location.href = d.edit;
    else if (e.key === 'Escape') location.href = '/';
  },
};

/* ── 키보드 (§10) — 입력칸에 초점이 있으면 글자 단축키는 먹지 않는다 ── */
document.addEventListener('keydown', e => {
  const mod = e.metaKey || e.ctrlKey;
  if (mod && (e.key === 'k' || e.key === 'K')) {
    const q = $('#q');
    if (q) { e.preventDefault(); q.focus(); q.select(); }
    return;
  }
  const scr = screen();
  if (mod && e.key === 'Enter') {
    if (scr === 'new') { e.preventDefault(); New.submit(); }
    else if (scr === 'review' && Review.form && document.contains(Review.form)) { e.preventDefault(); Review.submit(); }
    return;
  }
  if (typing(e.target)) { if (e.key === 'Escape') e.target.blur(); return; }
  if (mod || e.altKey) return;
  if (e.key === 'Enter' && e.target.matches && e.target.matches('tr[hx-get]')) { e.preventDefault(); e.target.click(); return; }
  if (scr === 'list') List.key(e);
  else if (scr === 'review' && Review.form) Review.key(e);
  else if (scr === 'case' && Case.sec) Case.key(e);
});

/* ── 화면별 초기화 — 확인 화면은 조각 안 인라인 스크립트가 PJ.review 를 부른다 ── */
function boot() {
  const sec = screenEl();
  if (!sec || sec.dataset.bound) return;
  sec.dataset.bound = '1';
  const s = sec.dataset.screen;
  if (s === 'list') List.init(sec);
  else if (s === 'new') New.init(sec);
  else if (s === 'case') Case.init(sec);
}
document.addEventListener('DOMContentLoaded', boot);
document.addEventListener('htmx:afterSwap', boot);

/* ── 폰 배치(app.css 끝 블록, ≤900px) — 페이지 전체가 스크롤되므로 바뀐 본문이 보이게 옮긴다 ── */
document.addEventListener('htmx:afterSwap', e => {
  if (!matchMedia('(max-width:900px)').matches) return;
  const t = e.detail && e.detail.target;
  if (!t) return;
  if (t.id === 'mn') scrollTo(0, 0);
  else if (t.id === 'detail') t.scrollIntoView({ block: 'start', behavior: 'smooth' });
});

window.PJ = { review(form) { if (form) Review.init(form); } };
})();
