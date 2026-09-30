"""판정 화면용 표시 데이터 — 조문 패널·시행 구간·이력 문구. 판정하지 않는다(엔진 출력과 statutes.py만 읽는다)."""
from __future__ import annotations

import re
from datetime import date as _date
from typing import Any, Dict, List, Optional

from markupsafe import Markup, escape

from ..rules.models import CaseInput
from ..rules.statutes import CITATIONS, WINDOWS, window_for

VCLASS = {"가능": "ok", "보완": "warn", "불가": "bad"}

# 09-28 사용자 「규칙은 아예 빼 주자」 — 화면엔 규칙 ID 대신 이 이름을 쓴다(ID는 data- 속성에만).
RULE_LABEL = {
    "M-25-4-EXT": "내부 참석자만의 회의 식비",
    "M-25-4-PRE": "사전 내부결재 없음",
    "M-25-5-DOC": "회의록·내부결재문서 없음",
    "M-25-14-6": "회의 근거 없는 평일 점심 식대",
    "M-25-2-6": "연구혁신비 비목",
    "M-DUP-TRIP": "출장 중인 참석자 식대",
    "M-INST-ALC": "주류 포함",
    "M-INST-CAP": "1인 한도 초과",
    "M-INST-WKD": "주말·공휴일 사용",
    "G-EXTRACT": "필수값 누락",
    "T-25-7-MEAL": "제공 식사분 중복 청구",
    "T-25-8-PLAN": "출장계획서 없음",
    "T-25-8-RPT": "출장결과보고서 없음",
    "T-INST-EVID": "교통비 증빙 없음",
    "X-DICT": "예외 사전 일치",
    "OK": "요건 충족",
}
# 예외 키의 조건 중 규칙 이름에 없는 정보만(나머지는 규칙 이름과 같은 말이라 뺀다)
COND_LABEL = {"basic": "기본사업", "nonbasic": "기본사업 아님"}


def rule_label(rule_id: Optional[str]) -> str:
    return RULE_LABEL.get(rule_id or "", "기타 요건")


def exception_text(key: Optional[str]) -> str:
    """예외 키 「M-25-4-EXT|internal_only|nonbasic」 → 「내부 참석자만의 회의 식비 · 기본사업 아님」."""
    rid, *cond = (key or "").split("|")
    return " · ".join([rule_label(rid), *(COND_LABEL[c] for c in cond if c in COND_LABEL)])


def humanize_rule_ids(text: str) -> str:
    """엔진 이유 문구 속 「(M-INST-WKD)」 같은 규칙 ID를 이름으로 — 엔진 문구 자체는 checks.py가 읽으니 화면에서만 바꾼다."""
    return re.sub(r"\b(?:[MTGX]-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b", lambda m: RULE_LABEL.get(m.group(0), m.group(0)), text or "")
MEANING = {"가능": "조문 요건 충족 — 집행·보고서 합산", "보완": "서류·소명을 더 내면 가능", "불가": "조문상 계상할 수 없음"}

# 판정을 가른 구절 — (규칙 ID, 인용 키) 또는 인용 키 → 원문 속 구절. 원문에 없는 구절이면 표시하지 않는다.
HIGHLIGHT: Dict[Any, str] = {
    ("M-25-4-EXT", "25-4-W0"): "해당 연구개발기관에 소속된 자만 참여하는 회의",
    ("M-25-4-EXT", "25-4-W1"): "해당 연구개발기관에 소속되지 않은 자가 참여하는 회의",
    ("M-25-4-PRE", "25-4-W1"): "사전에 내부결재가 완료된 회의",
    ("M-25-4-EXT", "25-4-W2"): "해당 연구개발과제의 참여연구자만 참여하는 회의",
    ("T-25-8-PLAN", "25-8"): "출장계획서를 갖추어야 하고",
    ("T-25-8-RPT", "25-8"): "출장결과보고서를 갖추어야 한다",
    "25-5": "내부결재문서 또는 회의록 중 어느 하나와 영수증서를 갖추어야 한다",
    "25-14-6": "평일 점심 또는 출장비 중 식비가 포함된 출장일의 참여연구자 및 연구근접지원인력의 식대",
    "25-7": "출장비에서 해당 금액을 차감하고 계상하여야 한다",
    "25-2-6": "연구혁신비로 해당 연구개발과제의 참여연구자만 참여하는 회의에 회의비 중 식비를 계상할 수 있다",
    "INST-WKD": "해당 과제와 직접 관련된 회의임을 입증하는 추가 증빙",
    "INST-ALC": "주류 결제 및 유흥업종에서의 회의비 집행",
    "INST-CAP": "초과분을 소명하게 한다",
    "INST-EVID": "교통비 증빙(승차권·e-ticket)",
    "DUP-TRIP": "동일인을 회의비 식대 참석자로 명시해 중복 집행한 사례",
    "EXTRACT": "재입력을 요청한다",
    "25-4-W0": "해당 연구개발기관에 소속된 자만 참여하는 회의",
    "25-4-W1": "해당 연구개발기관에 소속되지 않은 자가 참여하는 회의 중 사전에 내부결재가 완료된 회의",
    "25-4-W2": "해당 연구개발과제의 참여연구자만 참여하는 회의",
    "25-8": "출장계획서를 갖추어야 하고, 국외 출장비를 사용한 때에는 출장결과보고서를 갖추어야 한다",
}
WIN_LABEL = {"W0": ("구 조문", "~ 2024-11-30"), "W1": ("제2023-49호", "2024-12-01 ~ 2026-05-05"),
             "W2": ("제2026-38호", "2026-05-06 ~")}
DOC_NAME = "국가연구개발사업 연구개발비 사용 기준"
_CITE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}(?:~\d{2}-\d{2})?|\d{1,3}(?:,\d{3})+|\b[A-Z]{1,2}-[A-Z0-9-]+\b|#\d+)")


def mono(text: Any) -> Markup:
    """식별자(날짜·금액·규칙 ID·건 번호)만 모노로 — 한글이 섞인 조문 번호는 그대로(design.md §2.2)."""
    return Markup(_CITE_RE.sub(lambda m: f'<span class="mono">{m.group(1)}</span>', str(escape(text or ""))))


def _get(o: Any, k: str, default: Any = None) -> Any:
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def _hl_text(text: str, phrases: List[tuple]) -> Markup:
    out = str(escape(text))
    for phrase, cls in phrases:
        p = str(escape(phrase))
        if p and p in out:
            out = out.replace(p, f'<mark class="hl {cls}">{p}</mark>', 1)
    return Markup(out)


def _phrase(rule_id: str, cite: str) -> Optional[str]:
    return HIGHLIGHT.get((rule_id, cite)) or HIGHLIGHT.get(cite)


def _panel(cite: str, marks: List[tuple], case: CaseInput, reviewed: bool = False) -> Dict[str, Any]:
    c = CITATIONS[cite]
    w = window_for(case.date) if case.date else None
    p: Dict[str, Any] = dict(cite=cite, article=c.article, title=c.title, source_kind=c.source_kind, url=c.url,
                             quote=_hl_text(c.text, marks), reviewed=reviewed, inst=c.source_kind != "고시",
                             notice=w.notice_no if w and c.source_kind == "고시" else None,
                             eff=_eff(c.effective_from, c.effective_to), timeline=None)
    if cite.startswith("25-4-"):
        applied = cite.split("-")[-1]
        p["notice"] = WIN_LABEL[applied][0] if applied != "W0" else "구 제25조 제4항"
        p["timeline"] = [dict(code=x.code, label=WIN_LABEL[x.code][0], period=WIN_LABEL[x.code][1],
                              applied=x.code == applied,
                              quote=p["quote"] if x.code == applied else Markup(escape(CITATIONS["25-4-" + x.code].text)))
                         for x in WINDOWS]
    return p


def _eff(f: Optional[str], t: Optional[str]) -> str:
    if f and t:
        return f"{f} ~ {t} 시행"
    if f:
        return f"{f} 시행"
    if t:
        return f"~ {t}"
    return ""


def statute_panels(judgment: Any, case: CaseInput) -> List[Dict[str, Any]]:
    """가능이 아닌 이유마다 조문 패널 하나(같은 조문은 한 패널에 구절 여럿). 가능이면 「검토한 조문」."""
    reasons = list(_get(judgment, "reasons", []) or [])
    order: List[str] = []
    marks: Dict[str, List[tuple]] = {}
    for r in reasons:
        cite = _get(r, "cite")
        if not cite or _get(r, "verdict") == "가능" or cite not in CITATIONS:
            continue
        if cite not in marks:
            order.append(cite); marks[cite] = []
        ph = _phrase(_get(r, "rule_id"), cite)
        if ph:
            marks[cite].append((ph, VCLASS[_get(r, "verdict")]))
    if order:
        return [_panel(c, marks[c], case) for c in order]
    # 가능 — 가능을 만든 조문(연구혁신비 등)이 있으면 그것, 없으면 비목의 핵심 조문을 「검토한 조문」으로
    for r in reasons:
        cite = _get(r, "cite")
        if cite and cite in CITATIONS and _get(r, "rule_id") not in ("OK", "X-DICT"):
            ph = _phrase(_get(r, "rule_id"), cite)
            return [_panel(cite, [(ph, "ok")] if ph else [], case, reviewed=True)]
    w = window_for(case.date) if case.date else None
    if case.category == "회의비" and w:
        cite = "25-4-" + w.code
    elif case.category == "출장비" and case.trip and case.trip.domestic is False:
        cite = "25-8"
    else:
        cite = "25-5"
    return [_panel(cite, [], case, reviewed=True)]


def primary_reason(judgment: Any) -> Any:
    reasons = list(_get(judgment, "reasons", []) or [])
    for r in reasons:
        if _get(r, "verdict") != "가능":
            return r
    return reasons[0] if reasons else None


def weekday(d: Optional[str]) -> str:
    try:
        return "월화수목금토일"[_date.fromisoformat(d).weekday()]
    except (TypeError, ValueError):
        return ""


def event_text(kind: str, p: Dict[str, Any]) -> Optional[str]:
    """기록 한 줄을 사람이 읽는 문구로 — 건 이력과 행정팀 「기록」 표가 같이 쓴다. 모르는 종류면 None."""
    if kind == "judgment.saved":
        names = [rule_label(r) for r in (p.get("rules") or []) if r != "OK"]
        return f"판정 {p.get('verdict')}" + "".join(f" · {n}" for n in dict.fromkeys(names))
    return {
        "case.saved": "건 저장 · 사람이 확인한 필드",
        "case.edited": f"수정 · 집행일 {p.get('date') or '—'} · 금액 {p.get('amount') or '—'}",
        "queue.provisional": "임시 승인 · 7일 내 심판",
        "queue.appeal": f"이의 신청 · {p.get('statement') or ''}".rstrip(" ·"),
        "queue.decided": f"행정팀 {p.get('decision')}" + (f" · {p['note']}" if p.get("note") else ""),
        "queue.overdue": "심판 기한 초과",
        "exception.registered": f"예외 사전 등록 · {exception_text(p.get('key') or p.get('rule_id'))}",
    }.get(kind)


def event_ref(e: Dict[str, Any]) -> str:
    """기록이 가리키는 대상 — 건 #n 또는 심판 #n."""
    k, p = e["kind"], e["payload"]
    if k.startswith("case."):
        return f"건 #{e['ref_id']}"
    if k == "judgment.saved":
        return f"건 #{p.get('case_id')}"
    return f"심판 #{e['ref_id']}"


def history_lines(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """건 이력 — 시각·문구. 마지막 판정 줄에 「규칙엔진 판정 — 모델 관여 없음」."""
    out: List[Dict[str, Any]] = []
    for e in events:
        k, p = e["kind"], e["payload"]
        ts = str(e["ts"])
        text = event_text(k, p)
        if text is None:
            continue
        out.append(dict(date=ts[:10], time=ts[11:19], text=text, judgment=k == "judgment.saved", fin=False))
    for x in reversed(out):
        if x["judgment"]:
            x["fin"] = True
            break
    return out
