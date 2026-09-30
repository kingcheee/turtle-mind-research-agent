"""화면 = 라우트(design.md §8) — 목록·올리기·확인·판정 상세·수정·미리보기·업로드 파일."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from panjeong.rules.statutes import CITATIONS
from panjeong.store import Store
from panjeong.web.app import DEMO, DEMO_ALL, create_app
from tests.test_web import EXTRACTED, fake_extractor, judge_form

EXTERNAL = [{"name": "김철수", "affiliation": "ETRI", "external": False},
            {"name": "박민수", "affiliation": "KAIST", "external": True}]
DOCS = [{"kind": "회의록", "text": "2026-06-12 과제 내부 점검 회의.\n참석: 김철수, 이영희", "file": None}]


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "web.db", deadline_minutes=1)
    return TestClient(create_app(store=store, extractor=fake_extractor, data_dir=tmp_path))


def test_judge_redirects_to_case_page(client):
    r = client.post("/judge", data=judge_form(), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/case/1"


def test_case_page_shows_band_statute_timeline_and_requirement_rows(client):
    client.post("/judge", data=judge_form())
    r = client.get("/case/1").text
    assert re.search(r'<div class="hero bad" data-verdict="불가"', r) and 'class="vband' not in r
    assert CITATIONS["25-4-W2"].text.split(" ")[0] in r and "참여연구자만 참여하는 회의" in r
    assert '<mark class="hl bad">' in r
    assert all(f'data-code="{w}"' in r for w in ("W0", "W1", "W2"))
    assert 'class="drow m"' in r and "전원 과제 참여연구자" in r
    assert "규칙엔진 판정 — 모델 관여 없음" in r
    assert "/case/1/edit" in r


def test_allowed_case_shows_reviewed_article_and_basis(client):
    client.post("/judge", data=judge_form(attendees_json=json.dumps(EXTERNAL)))
    r = client.get("/case/1").text
    assert 'class="hero ok"' in r and "검토한 조문" in r and "판정 근거" in r
    assert "사용실적보고서에 합산됨" in r


def test_list_page_shows_table_rows_and_empty_state(client):
    assert "아직 판정한 건이 없습니다" in client.get("/").text
    client.post("/judge", data=judge_form())
    client.post("/judge", data=judge_form(attendees_json=json.dumps(EXTERNAL)))
    r = client.get("/").text
    assert 'data-screen="list"' in r and 'id="cases"' in r
    assert 'data-id="1" data-v="bad"' in r and 'data-id="2" data-v="ok"' in r
    assert r.index('data-id="2"') < r.index('data-id="1"')      # 최근 순
    assert "제25조 제4항" in r
    # 09-28 사용자: 규칙 ID 칸은 빼고 그 자리에 판정일(마지막 판정 시각)
    assert '<code class="tag">' not in r and ">규칙<" not in r
    assert ">판정일<" in r and re.search(r'class="mono jd">\d{2}-\d{2} \d{2}:\d{2}<', r)
    assert "아직 판정한 건이 없습니다" not in r


def test_static_assets_carry_a_version_so_edits_show_on_reload(client):
    r = client.get("/").text
    assert re.search(r'/static/app\.css\?v=\d+', r) and re.search(r'/static/app\.js\?v=\d+', r)


def test_new_page_has_upload_form_and_demo_cases(client):
    r = client.get("/new").text
    assert 'hx-post="/extract"' in r and 'name="files"' in r and 'name="text_doc"' in r
    assert r.count('data-kind="') == len(DEMO) == 5 and "영수증:" not in r   # 10-01: 5개, 영수증은 사진으로만
    assert client.get("/new?demo=all").text.count('data-kind="') == len(DEMO_ALL) == 11   # E2E·영상 컷용 전체
    assert "예시 영수증/회의록" in r and "<th>예상</th>" not in r and "시연 케이스" not in r
    assert "참여연구자만 회의 식비" in r


def test_demo_rows_carry_the_gemini_receipt_photos(client):
    """09-29 사용자: 사이트가 사용자가 Gemini로 만든 영수증 사진을 직접 쓰게 — 시연 1·2·3·4·6번 행에 그 사진이 붙는다(5번 출장은 사진 없음)."""
    r = client.get("/new").text
    photos = re.findall(r'<tr class="r" data-kind="[^"]*" data-photo="([^"]*)"', r)
    assert photos == ["R1.jpg", "R3.jpg", "R4.jpg", "R8.jpg", "R9.jpg"]
    all_photos = re.findall(r'<tr class="r" data-kind="[^"]*" data-photo="([^"]*)"', client.get("/new?demo=all").text)
    assert all_photos == ["R1.jpg", "R2.jpg", "R3.jpg", "R4.jpg", "", "R6.jpg", "R7.jpg", "R8.jpg", "R9.jpg", "R13.jpg", "R15.jpg"]
    assert 'name="demo_photo"' in r and 'id="demo-ph"' in r
    img = client.get("/demo-photos/R1.jpg")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg" and len(img.content) > 100_000
    assert client.get("/demo-photos/cases.json").status_code == 404
    assert client.get("/demo-photos/..%2Fanswer_key.json").status_code == 404


def test_extract_attaches_the_demo_photo_as_a_receipt_and_reads_it(client, monkeypatch, tmp_path):
    import panjeong.web.app as appmod
    seen = []
    monkeypatch.setattr(appmod, "image_to_text", lambda p: seen.append(p) or "한식당 미가 합계 52,800원")
    r = client.post("/extract", data={"demo_photo": "R1.jpg", "text_doc": DEMO[0][3], "text_doc_type": "회의록"},
                    headers={"HX-Request": "1"}).text
    m = re.search(r'/uploads/([^"]*-R1\.jpg)', r)
    assert m and (tmp_path / "uploads" / m.group(1)).stat().st_size > 100_000 and len(seen) == 1
    docs = json.loads(__import__("html").unescape(re.search(r'name="docs_json" value="([^"]*)"', r).group(1)))
    assert [(d["kind"], bool(d["file"])) for d in docs] == [("영수증", True), ("회의록", False)]
    bad = client.post("/extract", data={"demo_photo": "../project.json", "text_doc": "메모", "text_doc_type": "기타"},
                      headers={"HX-Request": "1"}).text
    assert "/uploads/" not in bad and len(seen) == 1


def test_extract_full_page_or_partial_by_htmx_header(client):
    full = client.post("/extract", data={"text_doc": "한식당 미가 52,800원", "text_doc_type": "영수증"}).text
    assert full.startswith("<!doctype html>") and 'data-screen="review"' in full
    part = client.post("/extract", data={"text_doc": "한식당 미가 52,800원", "text_doc_type": "영수증"},
                       headers={"HX-Request": "true"}).text
    assert "<html" not in part and 'id="judge-form"' in part and 'action="/judge"' in part
    assert 'name="docs_json"' in part and "한식당 미가 52,800원" in part


def test_re_extract_reuses_docs_json(client):
    r = client.post("/extract", data={"docs_json": json.dumps(DOCS, ensure_ascii=False)}, headers={"HX-Request": "1"})
    assert r.status_code == 200 and "과제 내부 점검 회의" in r.text and 'id="judge-form"' in r.text


def test_docs_are_saved_and_edit_rejudges_the_same_case(client):
    client.post("/judge", data=judge_form(docs_json=json.dumps(DOCS, ensure_ascii=False)))
    e = client.get("/case/1/edit").text
    assert 'name="case_id" value="1"' in e and "과제 내부 점검 회의" in e and 'value="2026-06-12"' in e
    r = client.post("/judge", data=judge_form(case_id="1", date="2025-03-10"), follow_redirects=False)
    assert r.headers["location"] == "/case/1"
    page = client.get("/case/1").text
    assert re.search(r'data-rules="[^"]*M-25-4-PRE', page) and "제2023-49호" in page
    assert "수정" in page                                          # 09-29 이력 칸은 뺐다 — 판정 이력은 test_store_views가 본다
    assert client.get("/").text.count('class="r"') == 1       # 새 건이 생기지 않았다


def test_preview_is_a_partial(client):
    client.post("/judge", data=judge_form())
    r = client.get("/case/1/preview").text
    assert "<html" not in r and "미리보기" in r and 'href="/case/1"' in r


def test_preview_shows_the_receipt_photo_not_the_verdict(client):
    """09-28 사용자: 미리보기는 판정 결과가 아니라 실제 영수증을 사진으로."""
    photo = [{"kind": "영수증", "file": "r1.png", "text": "월향 60,000원"}, {"kind": "회의록", "file": None, "text": "회의 내용"}]
    client.post("/judge", data=judge_form(docs_json=json.dumps(photo, ensure_ascii=False)))
    r = client.get("/case/1/preview").text
    assert re.search(r'<img [^>]*src="/uploads/r1\.png"', r) and 'href="/uploads/r1.png"' in r
    assert "pd m" not in r and "pv-q" not in r and 'class="vd' not in r      # 판정·요건 대조·조문 인용은 없다
    assert "회의록" in r                                                     # 함께 올린 문서는 이름만
    text_only = [{"kind": "영수증", "file": None, "text": "한식당 미가\n합계 52,800원"}]
    client.post("/judge", data=judge_form(docs_json=json.dumps(text_only, ensure_ascii=False)))
    r2 = client.get("/case/2/preview").text
    assert "<img" not in r2 and 'class="slip"' in r2 and "한식당 미가" in r2 and "사진 없음" in r2
    client.post("/judge", data=judge_form(docs_json=json.dumps(DOCS, ensure_ascii=False)))
    assert "영수증 없음" in client.get("/case/3/preview").text


def test_neighbour_links_without_related_cases_panel(client):
    # 09-29 사용자 「하나하나씩 없애가보자」: 같은 조문을 인용한 건 표는 뺐다 — 이전·다음 건 이동만 남는다.
    client.post("/judge", data=judge_form())
    client.post("/judge", data=judge_form(date="2026-06-15"))
    r2 = client.get("/case/2").text
    assert 'data-next="/case/1"' in r2 and 'class="panel relp"' not in r2 and "같은 조문을 인용한 건" not in r2
    assert 'data-prev="/case/2"' in client.get("/case/1").text


def _fold(html: str, kind: str) -> str:
    start = html.index(f'<details class="panel fold {kind}"')
    return html[start:html.index("</details>", start)]


def test_case_page_has_no_side_column_and_actions_live_in_the_reason_fold(client):
    """09-29 사용자 「컴퓨터에서도 너무 난잡하니까 … 하나하나씩 없애가보자」: 영수증|판정 + 접이식 3칸만 남긴다.
    오른쪽 사실 칸(사실 요약·증빙·이력·보고서)과 따로 있던 조치 줄은 빼고, 조치 버튼은 ▸안 되는 이유 안(필요 조치 아래)으로."""
    client.post("/judge", data=judge_form())                                              # 1 불가
    r = client.get("/case/1").text
    assert 'id="vs"' not in r and "사실 요약" not in r and 'class="act"' not in r and 'class="sp sp-x"' not in r
    why = _fold(r, "why")
    assert 'action="/case/1/appeal"' in why and "이의 신청" in why
    client.post("/case/1/appeal", data={"statement": "외부 자문위원이 실제로 참석"})
    why = _fold(client.get("/case/1").text, "why")
    assert re.search(r'class="qline">.*?이의.*?<b>대기</b>', why, re.S) and 'action="/case/1/appeal"' not in why
    client.post("/judge", data=judge_form(has_alcohol="on", attendees_json=json.dumps(EXTERNAL)))   # 2 보완
    why = _fold(client.get("/case/2").text, "why")
    assert 'href="/case/2/edit"' in why and "자료 보완 후 재판정" in why and 'action="/case/2/approve"' in why
    client.post("/judge", data=judge_form(attendees_json=json.dumps(EXTERNAL)))            # 3 가능
    ok = _fold(client.get("/case/3").text, "why")
    assert "판정 근거" in ok and "사용실적보고서에 합산됨" in ok


def test_unknown_case_is_404(client):
    assert client.get("/case/99").status_code == 404
    assert client.get("/case/99/edit").status_code == 404


def test_uploads_are_served_but_not_outside(client, tmp_path):
    (tmp_path / "uploads" / "a.png").write_bytes(b"\x89PNG")
    assert client.get("/uploads/a.png").status_code == 200
    assert client.get("/uploads/missing.png").status_code == 404
    assert client.get("/uploads/..%2Fweb.db").status_code == 404


RULE_ID = re.compile(r"\b(?:[MTGX]-[A-Z0-9]+(?:-[A-Z0-9]+)*|OK)\b")


def _visible(html: str) -> str:
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S)
    import html as h
    return h.unescape(re.sub(r"<[^>]+>", " ", html))


def test_no_rule_ids_visible_on_any_screen(tmp_path):
    """09-28 사용자: 「규칙은 아예 빼 주자」 — 규칙 ID(M-25-4-EXT·OK 등)는 화면 글자에서 전부 뺀다(속성엔 남아도 된다)."""
    from datetime import datetime
    from pathlib import Path
    from tools.seed_mock import seed_mock
    root = Path(__file__).parent.parent
    store = Store(tmp_path / "m.db")
    seed_mock(store, json.loads((root / "data" / "answer_key.json").read_text(encoding="utf-8")),
              uploads=tmp_path / "uploads", images=root / "data" / "images", now=datetime(2026, 9, 28, 10, 0))
    c = TestClient(create_app(store=store, extractor=fake_extractor, data_dir=tmp_path))
    ids = [r["id"] for r in store.list_case_rows()]
    qids = [q["id"] for q in store.list_queue(include_closed=True)]
    urls = ["/", "/new", "/reports", "/admin", "/bench"] + [f"/case/{i}" for i in ids] + \
           [f"/case/{i}/preview" for i in ids] + [f"/admin/queue/{q}" for q in qids]
    hits = {}
    for u in urls:
        r = c.get(u)
        assert r.status_code == 200, u
        found = sorted(set(RULE_ID.findall(_visible(r.text))))
        if found:
            hits[u] = found
    assert hits == {}


def test_requirement_rows_are_folded_by_default(client):
    # 09-28 사용자 요청: 판정 상세에 들어가자마자 요건 대조 줄이 다 보이면 말이 많다 — 접어 두고 머리의 요약 숫자만 보인다.
    client.post("/judge", data=judge_form())
    r = client.get("/case/1").text
    m = re.search(r'<details class="panel fold"([^>]*)>\s*<summary class="panel-h">(.*?)</summary>', r, re.S)
    assert m and "open" not in m.group(1)
    assert "요건 대조" in m.group(2) and "위반" in m.group(2)
    assert r.index('class="drow m"') > m.end()          # 줄은 접힌 본문 안


def test_extract_accepts_an_uploaded_photo(client, monkeypatch):
    """09-28 발견: request.form()의 파일은 starlette UploadFile이라 fastapi.UploadFile isinstance 검사에 걸려 사진이 조용히 버려졌다."""
    import panjeong.web.app as appmod
    monkeypatch.setattr(appmod, "image_to_text", lambda p: "한식당 미가 합계 52,800원")
    r = client.post("/extract", data={"file_doc_type": "영수증"}, files={"files": ("r1.jpg", b"not really a jpeg", "image/jpeg")},
                    headers={"HX-Request": "1"})
    assert r.status_code == 200 and 'id="judge-form"' in r.text
    assert "한식당 미가 합계 52,800원" in r.text and re.search(r'/uploads/[^"]*-r1\.jpg', r.text)


def test_case_page_has_phone_hero_receipt_photo_beside_big_verdict(client):
    """09-29 사용자(폰으로 보고): 판정 화면은 조항이 아니라 영수증 사진 + 옆에 크게 판정만. 폰 배치(app.css)에서만 보인다."""
    photo = [{"kind": "영수증", "file": "r1.png", "text": "월향 60,000원"}]
    client.post("/judge", data=judge_form(docs_json=json.dumps(photo, ensure_ascii=False)))
    r = client.get("/case/1").text
    m = re.search(r'<div class="hero bad"[^>]*>(.*?)</div><!--/hero-->', r, re.S)
    assert m, "판정 화면 맨 위에 hero 블록"
    h = m.group(1)
    assert re.search(r'<img [^>]*src="/uploads/r1\.png"', h) and 'href="/uploads/r1.png"' in h
    assert re.search(r'class="hv bad">.*?불가</div>', h, re.S) and "조문상 계상할 수 없음" in h
    assert "제25조" not in h and "drow" not in h                              # 조항·요건 대조는 없다
    hero = lambda cid: re.search(r'<div class="hero[^"]*"[^>]*>(.*?)</div><!--/hero-->', client.get(f"/case/{cid}").text, re.S).group(1)
    # 09-29: 영수증 문서가 따로 없으면(시연 케이스 = 영수증 줄이 든 회의록 텍스트) 빈 칸 대신 올린 문서 원문을 전표로
    client.post("/judge", data=judge_form(docs_json=json.dumps(DOCS, ensure_ascii=False)))
    h2 = hero(2)
    assert "영수증 없음" not in h2 and re.search(r'class="slip"><figcaption>회의록 원문</figcaption><pre>2026-06-12 과제 내부 점검 회의', h2)
    client.post("/judge", data=judge_form(docs_json="[]"))
    assert "영수증 없음" in hero(3)


def test_case_page_is_receipt_verdict_then_folds_for_requirements_reasons_and_article(client):
    """09-29 사용자: PC도 폰처럼 — 영수증|판정 아래 요건 대조·안 되는 이유·조항을 전부 접어서. 법 원문은 조항을 펼쳐야 보인다."""
    client.post("/judge", data=judge_form())
    r = client.get("/case/1").text
    folds = re.findall(r'<details class="panel fold([^"]*)"([^>]*)>\s*<summary class="panel-h">(.*?)</summary>', r, re.S)
    assert [f[0].strip() for f in folds] == ["", "why", "stt"]              # 요건 대조 → 안 되는 이유 → 조항
    assert all("open" not in f[1] for f in folds)                           # 전부 접힌 채로 시작
    assert r.index('class="hero bad"') < r.index('<details class="panel fold"')
    why, stt = folds[1][2], folds[2][2]
    assert "안 되는 이유" in why and "내부 참석자만의 회의 식비" in why       # 접혀도 이유 이름은 보인다
    assert "조항" in stt and "제25조 제4항" in stt and CITATIONS["25-4-W2"].text.split(" ")[0] not in stt   # 제목엔 조항 번호만
    body = r[r.index('<details class="panel fold why"'):r.index('<details class="panel fold stt"')]
    assert "내부 참석자만의 회의 식비" in body and CITATIONS["25-4-W2"].text.split(" ")[0] not in body    # 이유 칸에 법 원문 없음
    client.post("/judge", data=judge_form(attendees_json=json.dumps(EXTERNAL)))
    ok = client.get("/case/2").text
    assert re.search(r'<details class="panel fold why"[^>]*>\s*<summary class="panel-h">.*?판정 근거', ok, re.S)
