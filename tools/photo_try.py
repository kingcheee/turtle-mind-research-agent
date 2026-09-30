"""사진 영수증 + 회의록 텍스트 → 실제 모델(llama-server 18097) 추출 → 판정. 임시 데이터 폴더라 data/panjeong.db를 안 건드린다.
사용: .venv/bin/python tools/photo_try.py 사진.jpg "회의록 텍스트" [텍스트 문서 종류, 기본 회의록]   (09-28 Gemini 합성 영수증 사진 시험용)"""
import re, shutil, sys, tempfile, time
from html.parser import HTMLParser
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from panjeong.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
photo = Path(sys.argv[1]); minutes = sys.argv[2] if len(sys.argv) > 2 else ''; kind = sys.argv[3] if len(sys.argv) > 3 else '회의록'
tmp = Path(tempfile.mkdtemp(prefix='photo_try-'))
shutil.copy(ROOT / 'data' / 'project.json', tmp / 'project.json')
c = TestClient(create_app(data_dir=tmp, llama_url='http://127.0.0.1:18097', forms_dir=ROOT.parent / '서식'))

class Form(HTMLParser):
    def __init__(s): super().__init__(); s.f = {}; s.sel = None; s.ta = None; s.inform = False
    def handle_starttag(s, t, a):
        a = dict(a)
        if t == 'form' and a.get('id') == 'judge-form': s.inform = True
        if not s.inform: return
        if t == 'input' and a.get('name'):
            if a.get('type') == 'checkbox':
                if 'checked' in a: s.f[a['name']] = a.get('value', 'on')
            else: s.f[a['name']] = a.get('value', '')
        elif t == 'select' and a.get('name'): s.sel = a['name']; s.f.setdefault(s.sel, None)
        elif t == 'option' and s.sel and ('selected' in a or s.f.get(s.sel) is None): s.opt = s.sel; s.f[s.sel] = a.get('value')
        elif t == 'textarea' and a.get('name'): s.ta = a['name']; s.f[s.ta] = ''
    def handle_endtag(s, t):
        if t == 'select': s.sel = None
        if t == 'textarea': s.ta = None
        if t == 'form': s.inform = False
    def handle_data(s, d):
        if s.ta: s.f[s.ta] += d
        if getattr(s, 'opt', None) and s.f.get(s.opt) is None: s.f[s.opt] = d.strip()
        s.opt = None

t0 = time.time()
with photo.open('rb') as fh:
    r = c.post('/extract', data={'text_doc': minutes, 'text_doc_type': kind, 'file_doc_type': '영수증'},
               files={'files': (photo.name, fh, 'image/jpeg')})
p = Form(); p.feed(r.text)
f = p.f
print(f'추출 {time.time()-t0:.1f}s')
for k in ('category', 'date', 'time', 'amount_total', 'vat_included', 'vendor_name', 'vendor_type', 'attendee_count', 'purpose', 'has_alcohol'):
    print(f'  {k} = {f.get(k)!r}')
print('  attendees =', f.get('attendees_json'))
j = c.post('/judge', data={k: v for k, v in f.items() if v is not None})
m = re.search(r'data-verdict="([^"]+)" data-rules="([^"]*)"', j.text)
print('판정', m.groups() if m else None, j.url)
ocr = re.search(r'name="docs_json" value="([^"]*)"', r.text)
import html, json
for d in json.loads(html.unescape(ocr.group(1))) if ocr else []:
    if d.get('file'):
        print('OCR 원문:'); print(d['text'])
shutil.rmtree(tmp, ignore_errors=True)
