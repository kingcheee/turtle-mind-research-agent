"""요건 대조 — 판정 화면의 「요건 ↔ 사실」 줄(design.md §7.19).

원칙: **각 줄의 결과는 판정 이유(rule_id)가 정한다.** 이 파일은 판정하지 않는다.
- 엔진이 건 규칙 → 그 판정(불가 −, 보완 ?)
- 예외 사전(X-DICT)이 덮은 규칙 → + 와 「예외 사전(심판 #n)」
- 엔진이 안 건 규칙 → +
- 판정에 쓰이지 않은 사실(국내 출장 등) → · 참고
사실 칸은 사람이 확인한 case 값이다. 줄을 지어내지 않으려고, 엔진이 평가하지 않은 요건(회의 근거 없는 식대의 제4항 등)은 줄로 만들지 않는다.
"""
from __future__ import annotations

import re
from datetime import date as _date
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

from .engine import has_meeting_evidence
from .models import CaseInput
from .statutes import window_for

RESULT = {"+": "충족", "−": "위반", "?": "보완", "·": "참고"}
CLASS = {"+": "p", "−": "m", "?": "q", "·": "c"}
MARK_OF = {"불가": "−", "보완": "?", "가능": "+"}
_DICT = re.compile(r"예외 사전 일치 \(([A-Z0-9-]+)\) — 근거: 심판 #(\w+)")
_WEEKDAY = "월화수목금토일"


class Row(NamedTuple):
    mark: str      # + − ? ·
    req: str       # 요건 — 조문·규칙 조건
    fact: str      # 사실 — 확인된 증빙 값
    result: str    # 충족 | 위반 | 보완 | 참고

    @property
    def cls(self) -> str:
        return CLASS[self.mark]


def _get(o: Any, k: str, default: Any = None) -> Any:
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def _won(v: Optional[int]) -> str:
    return f"{v:,}원" if v is not None else "—"


def _names(xs: Iterable[str]) -> str:
    return ", ".join(xs)


class _Rules:
    """판정 이유를 규칙 ID별로 — 줄마다 결과를 여기서 꺼낸다."""

    def __init__(self, judgment: Any):
        self.hit: Dict[str, Any] = {}
        self.dict_src: Dict[str, str] = {}
        self.used: set = set()
        for r in _get(judgment, "reasons", []) or []:
            rid = _get(r, "rule_id")
            if rid == "X-DICT":
                m = _DICT.search(_get(r, "text", "") or "")
                if m:
                    self.dict_src[m.group(1)] = m.group(2)
                continue
            self.hit.setdefault(rid, r)
        self.reasons = list(_get(judgment, "reasons", []) or [])

    def row(self, rule_id: str, req: str, fact: str) -> Row:
        self.used.add(rule_id)
        if rule_id in self.dict_src:
            return Row("+", req, f"{fact} · 예외 사전(심판 #{self.dict_src[rule_id]})", RESULT["+"])
        r = self.hit.get(rule_id)
        mk = MARK_OF[_get(r, "verdict")] if r is not None else "+"
        return Row(mk, req, fact, RESULT[mk])

    def has(self, rule_id: str) -> bool:
        return rule_id in self.hit or rule_id in self.dict_src


def _note(req: str, fact: str) -> Row:
    return Row("·", req, fact, RESULT["·"])


def _attendee_fact(case: CaseInput, basis: str) -> str:
    n = len(case.attendees)
    if not n:
        return "참석자 명단 없음"
    if basis == "과제":
        out = [a for a in case.attendees if (a.participant is False if a.participant is not None else a.external is True)]
        unk = [a for a in case.attendees if a.participant is None and a.external is None]
        if out:
            return f"참석 {n}명 — 과제 미참여 {len(out)}명({_names(a.name for a in out)})"
        if unk:
            return f"참석 {n}명 — 과제 참여 여부 모름 {len(unk)}명({_names(a.name for a in unk)})"
        return f"참석 {n}명 — 전원 과제 참여연구자"
    out = [a for a in case.attendees if a.external is True]
    unk = [a for a in case.attendees if a.external is None]
    if out:
        return f"참석 {n}명 — 기관 외부 {len(out)}명({_names(a.name for a in out)})"
    if unk:
        return f"참석 {n}명 — 소속 확인 안 됨 {len(unk)}명({_names(a.name for a in unk)})"
    return f"참석 {n}명 — 전원 기관 소속"


def _meeting_rows(case: CaseInput, R: _Rules, w, cap: int) -> List[Row]:
    rows: List[Row] = []
    if R.has("M-25-14-6"):
        rows.append(R.row("M-25-14-6", "평일 점심 식대 — 회의 근거 없는 식대 계상 불가 (제25조 제14항 제6호)",
                          f"회의록·참석자·목적 없음 · {case.time or '시각 모름'}"))
        return rows
    if not has_meeting_evidence(case):
        rows.append(R.row("M-25-5-DOC", "내부결재문서 또는 회의록 중 어느 하나와 영수증서 (제5항)", "회의 근거 서류 없음"))
        return rows

    # 제25조 제4항 — 구간별 문구
    if w.code == "W2":
        req4 = "과제 참여연구자만 참여하는 회의가 아닐 것 (제4항)"
        fact4 = _attendee_fact(case, "과제")
    elif w.code == "W1":
        req4 = "기관에 소속되지 않은 자가 참여하는 회의 (제4항 단서)"
        fact4 = _attendee_fact(case, "기관")
    else:
        req4 = "기관 소속자만 참여하는 회의가 아닐 것 (제4항)"
        fact4 = _attendee_fact(case, "기관")
    basic = w.basic_project_exception and case.basic_project
    if basic:
        rows.append(_note(req4, fact4))
        rows.append(Row("+", "정부출연기관의 기본사업 — 계상할 수 있음 (제4항 단서)", "기본사업 체크", RESULT["+"]))
    elif R.has("M-25-2-6"):
        rows.append(_note(req4, fact4))
        rows.append(R.row("M-25-2-6", "연구혁신비로 참여연구자만의 회의 식비 계상 가능 (제25조의2 제6항)", "연구혁신비 비목으로 집행"))
    else:
        rows.append(R.row("M-25-4-EXT", req4, fact4))
    if w.requires_prior_approval and not basic:
        rows.append(R.row("M-25-4-PRE", "사전에 내부결재가 완료된 회의 (제4항 단서)",
                          "내부결재문서 있음" if case.has_internal_approval else "사전 내부결재 증빙 없음"))

    # 제25조 제5항 — 증빙
    small = case.amount_total is not None and case.amount_total <= 100000
    docs = [n for n, v in (("회의록", case.has_minutes), ("내부결재문서", case.has_internal_approval)) if v]
    if docs:
        fact5 = " · ".join(f"{d} 있음" for d in docs)
    elif small and case.has_simplified_evidence:
        fact5 = f"{_won(case.amount_total)} — 10만 원 이하 · 간이 증명자료로 대신 (제5항 단서)"
    else:
        fact5 = "회의록·내부결재문서 없음" + (f" · {_won(case.amount_total)} — 10만 원 이하라 간이 증명자료로 대신 가능" if small else "")
    rows.append(R.row("M-25-5-DOC", "내부결재문서 또는 회의록 중 어느 하나와 영수증서 (제5항)", fact5))

    if R.has("M-DUP-TRIP"):
        dup = R.hit.get("M-DUP-TRIP")
        rows.append(R.row("M-DUP-TRIP", "출장 기간 중인 사람을 회의비 식대 참석자로 올리지 않을 것",
                          (_get(dup, "text", "") or "").split(" — ")[0] if dup is not None else "출장 중복"))
    if case.has_alcohol or case.vendor_type == "주점":
        what = " · ".join(x for x, v in (("주류 포함", case.has_alcohol), ("업종 주점", case.vendor_type == "주점")) if v)
        rows.append(R.row("M-INST-ALC", "주류·유흥업종 집행 제한 (기관 지침)", what))
    n = case.attendee_count or len(case.attendees)
    if case.amount_total and n:
        rows.append(R.row("M-INST-CAP", "회의비 1인당 식비 한도 (기관 지침)",
                          f"1인당 {case.amount_total // n:,}원 · 한도 {cap:,}원"))
    d = _date.fromisoformat(case.date)
    if d.weekday() >= 5 or R.has("M-INST-WKD"):
        rows.append(R.row("M-INST-WKD", "주말·공휴일 회의 — 과제와 직접 관련된 회의임을 입증하는 추가 증빙 (기관 지침)",
                          f"{case.date} {_WEEKDAY[d.weekday()]}요일"))
    return rows


def _travel_rows(case: CaseInput, R: _Rules) -> List[Row]:
    t = case.trip
    if t is None:
        return [R.row("G-EXTRACT", "출장지·기간·국내외 (필수값)", "출장 정보 없음")]
    rows: List[Row] = []
    where = " · ".join(x for x in (t.destination, f"{t.start}~{(t.end or '')[5:]}" if t.start else None) if x)
    if t.domestic is False:
        rows.append(R.row("T-25-8-PLAN", "국외 출장비를 사용하려는 때 — 출장계획서 (제8항)",
                          "출장계획서 있음" if t.plan_doc else "출장계획서 없음"))
        if R.has("T-25-8-RPT") or t.report_doc:
            rows.append(R.row("T-25-8-RPT", "국외 출장비를 사용한 때 — 출장결과보고서 (제8항)",
                              "출장결과보고서 있음" if t.report_doc else "출장결과보고서 없음"))
        else:
            rows.append(_note("국외 출장비를 사용한 때 — 출장결과보고서 (제8항)",
                              f"출장결과보고서 없음 — 종료일 {t.end or '모름'} 뒤 제출"))
    elif t.domestic is True:
        rows.append(_note("국내 출장 — 제8항(국외 출장 서류) 대상 아님", where or "국내"))
    else:
        rows.append(_note("국내외 여부 — 국외면 출장계획서·결과보고서 (제8항)", "국내외 확인 안 됨"))
    if t.meals_provided:
        rows.append(R.row("T-25-7-MEAL", "관계기관 제공 식대·식사 금액 차감 (제7항)",
                          "식사 제공 · 식비 전액 청구" if t.meal_claimed_full else "식사 제공 · 전액 청구 표시 없음"))
    if t.has_transport_evidence is not None:
        rows.append(R.row("T-INST-EVID", "교통비 증빙·출장 목적 서류 (기관 지침)",
                          "있음" if t.has_transport_evidence else "없음"))
    return rows


def requirement_rows(case: CaseInput, judgment: Any, cap: int = 30000) -> List[Row]:
    """판정(Judgment 또는 저장된 dict)과 확인된 case로 요건 대조 줄을 만든다."""
    R = _Rules(judgment)
    if not case.date:
        return [R.row("G-EXTRACT", "집행일 — 기준일(시행 구간)을 정하는 필수값", "집행일 없음")]
    w = window_for(case.date)
    rows = [Row("+", "적용 고시 — 기준일(집행일)이 속한 시행 구간", f"집행일 {case.date} → {w.notice_no}", RESULT["+"])]
    if case.amount_total is None:
        rows.append(R.row("G-EXTRACT", "금액 — 필수값", "금액 없음"))
    if case.category == "회의비":
        rows += _meeting_rows(case, R, w, cap)
    elif case.category == "출장비":
        rows += _travel_rows(case, R)
    else:
        rows.append(R.row("G-EXTRACT", "비목 — 회의비 또는 출장비", "비목 미지정"))
    # 줄로 못 옮긴 이유가 있으면 숨기지 않고 원문 그대로 붙인다
    for r in R.reasons:
        rid = _get(r, "rule_id")
        if rid in ("OK", "X-DICT") or rid in R.used:
            continue
        R.used.add(rid)
        mk = MARK_OF[_get(r, "verdict")]
        rows.append(Row(mk, f"{_get(r, 'article')} — {rid}", _get(r, "action") or _get(r, "text") or "", RESULT[mk]))
    return rows
