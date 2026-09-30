"""결정론 규칙엔진 — 판정은 여기서만 난다. LLM은 이 파일을 모른다.

집계: 불가 > 보완 > 가능. 고시 조문이 아닌 규칙(INST-)은 보완까지만 낸다.
예외 사전에 등록된 키와 일치하는 규칙은 X-DICT(가능)로 바뀌고 심판 ID를 인용한다.
"""
from __future__ import annotations

from datetime import date as _date
from typing import List, Optional

from .models import CaseInput, Context, Judgment, Reason
from .statutes import CITATIONS, INNOVATION_FUND_FROM, window_for

VERDICT_RANK = {"가능": 0, "보완": 1, "불가": 2}

# 예외 사전이 덮어쓸 수 있는 규칙과 그 정규화 조건
EXCEPTION_ELIGIBLE = {
    "M-25-4-EXT": lambda c: ("internal_only", "basic" if c.basic_project else "nonbasic"),
    "M-25-4-PRE": lambda c: ("no_prior_approval",),
    "M-INST-ALC": lambda c: ("alcohol",),
    "M-INST-CAP": lambda c: ("over_cap",),
    "M-INST-WKD": lambda c: ("weekend",),
    "T-25-7-MEAL": lambda c: ("meal_provided_full_claim",),
    "T-INST-EVID": lambda c: ("no_transport_evidence",),
}


def exception_key(rule_id: str, case: CaseInput) -> str:
    cond = EXCEPTION_ELIGIBLE.get(rule_id, lambda c: ())(case)
    return "|".join([rule_id, *cond])


def _reason(rule_id: str, verdict: str, cite_key: str, notice_no: Optional[str] = None,
            action: Optional[str] = None, text: Optional[str] = None) -> Reason:
    c = CITATIONS[cite_key]
    return Reason(rule_id=rule_id, verdict=verdict, article=c.article, text=text or c.text,
                  source_kind=c.source_kind, url=c.url, effective_from=c.effective_from,
                  effective_to=c.effective_to, notice_no=notice_no, action=action, cite=cite_key)


def _is_weekend_or_holiday(d: str, ctx: Context) -> bool:
    y, m, dd = (int(x) for x in d.split("-"))
    return _date(y, m, dd).weekday() >= 5 or d in ctx.policy.holidays


def _is_lunch(t: Optional[str], ctx: Context) -> bool:
    return bool(t) and ctx.policy.lunch_start <= t <= ctx.policy.lunch_end


def has_meeting_evidence(case: CaseInput) -> bool:
    """회의 근거(회의록·결재·간이 증명·참석자·목적)가 하나라도 있는가 — 없으면 제4항 이하를 보지 않는다."""
    return bool(case.has_minutes or case.has_internal_approval or case.has_simplified_evidence
                or case.attendees or case.purpose)


def _meeting_rules(case: CaseInput, ctx: Context, w) -> List[Reason]:
    rs: List[Reason] = []
    weekend = _is_weekend_or_holiday(case.date, ctx)

    # 회의 근거가 전혀 없는 평일 점심 식대 → 계상 불가 식대
    if not has_meeting_evidence(case):
        if not weekend and _is_lunch(case.time, ctx):
            rs.append(_reason("M-25-14-6", "불가", "25-14-6", w.notice_no,
                              text="회의 근거(회의록·참석자·목적) 없는 평일 점심 식대 — " + CITATIONS["25-14-6"].text))
        else:
            rs.append(_reason("M-25-5-DOC", "보완", "25-5", w.notice_no, action="회의록 또는 내부결재문서 첨부"))
        return rs

    # 제25조 제4항 — 회의비 식비의 참석자 요건. 「외부」의 기준이 구간마다 다르다:
    #   W0·W1 기관 기준(소속되지 않은 자), W2 과제 기준(참여연구자 외의 자). 기본사업 단서는 W0에만 있다.
    if w.requires_external and not (w.basic_project_exception and case.basic_project):
        cite = "25-4-" + w.code
        if w.external_basis == "과제":
            # 참여 여부가 비면 기관 소속으로 대신한다(내부자 = 참여연구자, 외부인 = 미참여) — 명단 없는 옛 건·직접 입력 건의 보수적 기본값
            outsiders = [(not a.participant) if a.participant is not None else (None if a.external is None else a.external)
                         for a in case.attendees]
            who, fix = "과제 참여연구자만 참여한 회의", "참석자의 과제 참여 여부 확인 — 참여연구자 외의 참석자 명단 보완"
        else:
            outsiders = [a.external for a in case.attendees]
            who, fix = "기관 내부 소속자만 참여한 회의", "외부 참석자 확인 필요 — 참석자 명단·소속 보완"
        if outsiders and all(o is False for o in outsiders):
            if w.code == "W2" and case.innovation_fund and case.date >= INNOVATION_FUND_FROM:
                rs.append(_reason("M-25-2-6", "가능", "25-2-6", w.notice_no,
                                  text="연구혁신비 비목으로 집행 — " + CITATIONS["25-2-6"].text))
            else:
                rs.append(_reason("M-25-4-EXT", "불가", cite, w.notice_no, action=f"{who}의 식비는 계상 불가"))
        elif not outsiders or any(o is None for o in outsiders):
            rs.append(_reason("M-25-4-EXT", "보완", cite, w.notice_no, action=fix))
        if w.requires_prior_approval and not case.has_internal_approval:
            rs.append(_reason("M-25-4-PRE", "보완", "25-4-W1", w.notice_no, action="사전 내부결재 문서 확인"))

    # 제25조 제5항 — 증빙
    if not (case.has_minutes or case.has_internal_approval):
        small = case.amount_total is not None and case.amount_total <= 100000
        if not (small and case.has_simplified_evidence):
            act = ("회의록 또는 내부결재문서 첨부 (10만 원 이하이므로 목적·일시·장소·내용·참석자 명단 증명자료로 대체 가능)"
                   if small else "회의록 또는 내부결재문서 첨부")
            rs.append(_reason("M-25-5-DOC", "보완", "25-5", w.notice_no, action=act))

    # 출장일 중복
    dup = [a.name for a in case.attendees if a.name in ctx.attendees_on_trip]
    if dup:
        rs.append(_reason("M-DUP-TRIP", "불가", "DUP-TRIP", w.notice_no,
                          text=f"참석자 {', '.join(dup)}은(는) {case.date} 출장 중 — " + CITATIONS["DUP-TRIP"].text))

    # 기관 지침 — 보완까지만
    if case.has_alcohol or case.vendor_type == "주점":
        rs.append(_reason("M-INST-ALC", "보완", "INST-ALC", action="주류·업종 소명 또는 해당 금액 제외"))
    n = case.attendee_count or len(case.attendees)
    if case.amount_total and n and case.amount_total / n > ctx.policy.per_person_cap:
        rs.append(_reason("M-INST-CAP", "보완", "INST-CAP",
                          action=f"1인당 {case.amount_total // n:,}원 — 기관 한도 {ctx.policy.per_person_cap:,}원 초과 소명"))
    if weekend:
        rs.append(_reason("M-INST-WKD", "보완", "INST-WKD", action="과제 관련성 추가 증빙"))
    return rs


def _travel_rules(case: CaseInput, ctx: Context, w) -> List[Reason]:
    rs: List[Reason] = []
    t = case.trip
    if t is None:
        rs.append(_reason("G-EXTRACT", "보완", "EXTRACT", action="출장지·기간·국내외 여부 재입력"))
        return rs
    if t.meals_provided and t.meal_claimed_full:
        rs.append(_reason("T-25-7-MEAL", "보완", "25-7", w.notice_no, action="제공된 식사분 차감 후 재계상"))
    if t.domestic is False:
        if t.plan_doc is False:
            rs.append(_reason("T-25-8-PLAN", "보완", "25-8", w.notice_no, action="출장계획서 첨부"))
        today = ctx.today or _date.today().isoformat()
        if t.report_doc is False and t.end and t.end <= today:
            rs.append(_reason("T-25-8-RPT", "보완", "25-8", w.notice_no, action="출장결과보고서 첨부"))
    if t.has_transport_evidence is False:
        rs.append(_reason("T-INST-EVID", "보완", "INST-EVID", action="교통비 증빙·출장 목적 서류 첨부"))
    return rs


def judge(case: CaseInput, ctx: Optional[Context] = None) -> Judgment:
    ctx = ctx or Context()
    reasons: List[Reason] = []

    if not case.date:
        reasons.append(_reason("G-EXTRACT", "보완", "EXTRACT", action="집행일 재입력"))
        return Judgment("보완", reasons, [r.action for r in reasons if r.action], None, None, None)
    w = window_for(case.date)
    if case.amount_total is None:
        reasons.append(_reason("G-EXTRACT", "보완", "EXTRACT", w.notice_no, action="금액 재입력"))
    if case.category == "회의비":
        reasons += _meeting_rules(case, ctx, w)
    elif case.category == "출장비":
        reasons += _travel_rules(case, ctx, w)
    else:
        reasons.append(_reason("G-EXTRACT", "보완", "EXTRACT", w.notice_no, action="비목(회의비/출장비) 지정"))

    # 예외 사전
    final: List[Reason] = []
    for r in reasons:
        key = exception_key(r.rule_id, case) if r.rule_id in EXCEPTION_ELIGIBLE else None
        if key and key in ctx.exceptions:
            src = ctx.exceptions[key].get("source_queue_id")
            final.append(_reason("X-DICT", "가능", "DICT", w.notice_no,
                                 text=f"예외 사전 일치 ({r.rule_id}) — 근거: 심판 #{src}. " + CITATIONS["DICT"].text))
        else:
            final.append(r)

    verdict = "가능"
    for r in final:
        if VERDICT_RANK[r.verdict] > VERDICT_RANK[verdict]:
            verdict = r.verdict
    if verdict == "가능" and not any(r.verdict == "가능" for r in final):
        final.append(_reason("OK", "가능", "25-5", w.notice_no,
                             text="적용 조문(제25조 제4항·제5항 등)의 요건을 모두 충족 — " + w.label))
    actions = [r.action for r in final if r.verdict != "가능" and r.action]
    return Judgment(verdict, final, actions, case.date, w.notice_no, w.code)
