"""공식 서식 hwpx 채우기 — 좌표는 09-24 실측(`서식/*.tables.md` + dumpall). 채움 전 구조 단언, 채운 뒤 재독.

- usage : 시행규칙 별지 제7호 연구개발비 사용실적보고서 (3섹션 → 섹션 0). 표3 표지, 표9 「8) 연구활동비」 현금 행(r19) 사용금액⑥(c18)
- audit : 고시 별지 제5호 자체 회계감사 의견서 (단일 표). 「4) 연구활동비」 현금 r75: 부적정 사용내역 c10 · 부적정 사용 금액(천원) c33
          「다. 자체 회계감사 후 부적정 사용 금액」 현금 r59c5 · 합계 r61c5 (천원)
- appeal: 고시 별지 제7호 정산 이의신청서. 신청 대상 및 내용 r12c2 · 신청 요지 및 이슈 r13c2
- annex : 판정관 생성 건별 집행내역 (HTML 인쇄용)
"""
from __future__ import annotations

import json
import sys
from datetime import date
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

MVP_ROOT = Path(__file__).resolve().parents[2]
if str(MVP_ROOT) not in sys.path:
    sys.path.insert(0, str(MVP_ROOT))
import hwpx_fill_vendored as h  # noqa: E402

from ..store import Store  # noqa: E402

FORMS_DIR_DEFAULT = MVP_ROOT.parent / "서식"
FILES = {
    "usage": "시행규칙_별지제7호서식_연구개발비사용실적보고서.hwpx",
    "audit": "고시_별지제5호_자체회계감사의견서.hwpx",
    "appeal": "고시_별지제7호_정산이의신청서.hwpx",
}
DEFAULT_PROJECT = {"사업명": "국가과학AI연구센터 AI 해커톤 시연 과제", "연구개발과제명": "연구비 판정관 시연",
                   "연구개발과제번호": "2026-DEMO-001", "기관명": "거북이정신", "연구책임자": "김지우"}


def _won(v: Optional[int]) -> str:
    return f"{int(v):,}" if v is not None else ""


def _thousand(v: int) -> str:
    return f"{v // 1000:,}"


def _rows(store: Store) -> List[Dict[str, Any]]:
    out = []
    for c in store.list_cases():
        row = store.get_case(c["id"]); j = store.latest_judgment(c["id"])
        out.append({"id": c["id"], "case": row["case"], "extracted": row["extracted"], "verdict": c["verdict"],
                    "queue_status": c["queue_status"], "judgment": j})
    return out


def _summary(r: Dict[str, Any]) -> str:
    c, j = r["case"], r["judgment"] or {}
    vendor = (r["extracted"] or {}).get("vendor_name") or ""
    arts = "; ".join(f"{x['article']}({x['rule_id']})" for x in j.get("reasons", []) if x["verdict"] != "가능") or "요건 충족"
    return f"#{r['id']} {c.category} {c.date} {vendor} {_won(c.amount_total)}원 — 판정 {r['verdict']}: {arts} · 기준일 {j.get('basis_date')} · {j.get('notice_no')}"


def build_report(key: str, store: Store, forms_dir: Path | str = FORMS_DIR_DEFAULT, out_dir: Path | str = "data/reports",
                 project: Optional[Dict[str, str]] = None) -> Path:
    forms_dir, out_dir = Path(forms_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pj = dict(DEFAULT_PROJECT)
    pfile = out_dir.parent / "project.json"
    if pfile.exists():
        pj.update(json.loads(pfile.read_text(encoding="utf-8")))
    if project:
        pj.update(project)
    rows = _rows(store)
    today = date.today()
    stamp = today.strftime("%Y%m%d")

    if key == "annex":
        return _annex(rows, out_dir / f"별첨_건별집행내역_{stamp}.html", pj)

    src = forms_dir / FILES[key]
    dst = out_dir / f"{FILES[key][:-5]}_{stamp}.hwpx"
    if key == "usage":
        allowed = sum(r["case"].amount_total or 0 for r in rows if r["verdict"] == "가능" and r["case"].category in ("회의비", "출장비"))
        provisional = sum(r["case"].amount_total or 0 for r in rows if r["verdict"] == "보완" and r["queue_status"] in ("대기", "기한초과"))
        items = [
            {"table": 3, "row": 2, "col": 4, "value": pj["사업명"]},
            {"table": 3, "row": 5, "col": 4, "value": pj["연구개발과제명"]},
            {"table": 3, "row": 6, "col": 6, "value": pj["기관명"]},
            {"table": 3, "row": 7, "col": 6, "value": pj["연구책임자"]},
            {"table": 9, "row": 19, "col": 18, "value": _won(allowed)},
        ]
        if provisional:
            items.append({"table": 9, "row": 19, "col": 25, "value": f"임시승인 {_won(provisional)} (심판 대기)"})
        h.fill_cells(str(src), str(dst), items, expect_tables=None, section=0)
        return dst

    if key == "audit":
        rejected = [r for r in rows if r["verdict"] == "불가"]
        total = sum(r["case"].amount_total or 0 for r in rejected)
        detail = " / ".join(_summary(r) for r in rejected) or "해당 없음"
        items = [
            {"table": 1, "row": 13, "col": 17, "value": pj["연구개발과제명"]},
            {"table": 1, "row": 15, "col": 17, "value": pj["기관명"]},
            {"table": 1, "row": 17, "col": 22, "value": pj["연구책임자"]},
            {"table": 1, "row": 59, "col": 5, "value": _thousand(total)},
            {"table": 1, "row": 61, "col": 5, "value": _thousand(total)},
            {"table": 1, "row": 75, "col": 10, "value": detail},
            {"table": 1, "row": 75, "col": 33, "value": _thousand(total)},
            {"table": 1, "row": 94, "col": 1, "value": f"연구비 판정관이 집행 시점 판정 로그를 근거로 작성 ({today.isoformat()}). 「불가」 판정 {len(rejected)}건, 합계 {_won(total)}원."},
        ]
        h.fill_cells(str(src), str(dst), items, expect_tables=[[103, 46]])
        return dst

    if key == "appeal":
        appeals = [q for q in store.list_queue(include_closed=True) if q["kind"] == "이의"]
        by_id = {r["id"]: r for r in rows}
        target = "\n".join(_summary(by_id[q["case_id"]]) for q in appeals if q["case_id"] in by_id) or "이의 신청 건 없음"
        statement = "\n".join(q.get("statement") or "" for q in appeals) or ""
        items = [
            {"table": 1, "row": 3, "col": 2, "value": pj["사업명"]},
            {"table": 1, "row": 4, "col": 2, "value": pj["연구개발과제명"]},
            {"table": 1, "row": 4, "col": 7, "value": pj["연구개발과제번호"]},
            {"table": 1, "row": 5, "col": 2, "value": pj["기관명"]},
            {"table": 1, "row": 5, "col": 7, "value": pj["연구책임자"]},
            {"table": 1, "row": 12, "col": 2, "value": target},
            {"table": 1, "row": 13, "col": 2, "value": statement},
            {"table": 1, "row": 16, "col": 1, "value": f"   {today.year}년 {today.month:02d}월 {today.day:02d}일"},
        ]
        h.fill_cells(str(src), str(dst), items, expect_tables=[[22, 9]])
        return dst
    raise KeyError(key)


def _annex(rows: List[Dict[str, Any]], out: Path, pj: Dict[str, str]) -> Path:
    trs = []
    for r in rows:
        c, j = r["case"], r["judgment"] or {}
        vendor = (r["extracted"] or {}).get("vendor_name") or ""
        arts = "<br>".join(escape(f"{x['article']} ({x['rule_id']})") for x in j.get("reasons", []) if x["verdict"] != "가능") or "요건 충족"
        trs.append(f"<tr><td>{r['id']}</td><td>{escape(c.date or '')}</td><td>{escape(c.category)}</td><td>{escape(vendor)}</td>"
                   f"<td class=r>{_won(c.amount_total)}</td><td class='v {r['verdict']}'>{r['verdict'] or ''}</td><td>{arts}</td>"
                   f"<td>{escape(str(j.get('basis_date') or ''))}<br><small>{escape(str(j.get('notice_no') or ''))}</small></td><td>{escape(r['queue_status'] or '')}</td></tr>")
    html = f"""<!doctype html><html lang=ko><meta charset=utf-8><title>별첨 — 건별 집행내역</title>
<style>body{{font-family:Pretendard,system-ui,sans-serif;font-size:11pt;margin:24mm}}h1{{font-size:15pt}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #333;padding:4px 6px;vertical-align:top}}th{{background:#eee}}td.r{{text-align:right}}td.v{{font-weight:700}}td.가능{{color:#2e8b3d}}td.보완{{color:#8a5f00}}td.불가{{color:#c8322b}}@media print{{body{{margin:12mm}}}}</style>
<h1>별첨. 연구활동비(회의비·출장비) 건별 집행내역 — 집행 시점 판정 로그</h1>
<p>{escape(pj['사업명'])} / {escape(pj['연구개발과제명'])} / {escape(pj['기관명'])} / 연구책임자 {escape(pj['연구책임자'])} · 작성 {date.today().isoformat()} · 판정 근거: 「국가연구개발사업 연구개발비 사용 기준」(과기정통부고시) 조문, 집행일 기준 적용</p>
<table><tr><th>#</th><th>집행일</th><th>비목</th><th>업체</th><th>금액(원)</th><th>판정</th><th>조문·규칙</th><th>기준일·고시</th><th>심판</th></tr>{''.join(trs)}</table>
<p><small>판정은 결정론 규칙엔진이 내렸으며 AI는 문서 구조화에만 쓰였다. 결과는 참고용이며 최종 판단은 기관 규정 담당자에게 있다.</small></p></html>"""
    out.write_text(html, encoding="utf-8")
    return out
