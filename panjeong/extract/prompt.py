"""프롬프트 + 추출 JSON → CaseInput. 증빙 플래그는 문서 종류에서 유도하고 화면에서 덮어쓸 수 있다."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..rules.models import Attendee, CaseInput, Trip

GRAMMAR_PATH = Path(__file__).with_name("grammar.gbnf")

SYSTEM = ("너는 국가연구개발과제 연구비 증빙 문서에서 필드를 추출하는 도구다. "
          "문서에 근거가 없는 값은 반드시 null로 둔다. 추측하지 않는다. JSON만 출력한다.")

INSTRUCTION = ("다음 문서 묶음(한 건의 집행)에서 필드를 추출하라. "
               "category는 회의·식사 관련이면 회의비, 출장·교통·숙박이면 출장비, 알 수 없으면 불명. "
               "external은 참석자가 문서에 적힌 주 기관(첫 참석자의 소속) 밖의 사람인지다(모르면 null). "
               "has_alcohol은 품목에 주류(소주·맥주·와인·양주 등)가 있는지다. "
               "vendor_name은 상호(가게·업체 이름)이며 사업자등록번호가 아니다. "
               "trip은 출장 문서가 있을 때만 채우고 아니면 null.")


def build_prompt(docs: Sequence[Tuple[str, str]]) -> str:
    body = "\n\n".join(f"[{kind}]\n{text.strip()}" for kind, text in docs)
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
            f"<|im_start|>user\n{INSTRUCTION}\n\n{body}<|im_end|>\n"
            f"<|im_start|>assistant\n")


def _norm_aff(a: Optional[str]) -> str:
    return re.sub(r"\s+", "", a or "").lower()


def derive_external(attendees: List[Attendee], institution: Optional[str] = None) -> List[Attendee]:
    """소속이 있으면 외부 여부는 **코드가** 정한다(모델 플래그 무시).
    주 기관 = 설정된 연구개발기관명, 없으면 소속이 둘 이상일 때의 최다 소속. 둘 다 없으면(참석자 1명) 모델 값을 남긴다.
    소속 문자열이 주 기관을 포함하거나 그 반대면 내부, 아니면 외부."""
    affs = [_norm_aff(a.affiliation) for a in attendees if a.affiliation]
    if institution:
        primary = _norm_aff(institution)
    elif len(affs) >= 2:
        primary = Counter(affs).most_common(1)[0][0]
    else:
        return attendees
    for a in attendees:
        if a.affiliation:
            n = _norm_aff(a.affiliation)
            a.external = not (primary in n or n in primary)
    return attendees


def derive_participant(attendees: List[Attendee], participants: Optional[Iterable[str]] = None) -> List[Attendee]:
    """과제 참여연구자 여부(제2026-38호 ④의 기준). 화면에서 명시한 값은 지킨다.
    명단(project.json 「참여연구자」)이 있으면 이름 대조, 없으면 기관 내부자 = 참여연구자로 본다(보수적 기본값 — 불가 쪽으로 기운다)."""
    roster = {re.sub(r"\s+", "", n) for n in (participants or []) if n}
    for a in attendees:
        if a.participant is not None:
            continue
        if roster:
            a.participant = re.sub(r"\s+", "", a.name) in roster
        elif a.external is not None:
            a.participant = not a.external
    return attendees


ALCOHOL_KEYWORDS = ("소주", "맥주", "생맥", "막걸리", "와인", "양주", "위스키", "주류", "호프", "포차", "이자카야", "펍", "pub", "bar ", "칵테일", "사케")


# 업종은 품목·문서 키워드로 정한다(1.5B는 된장찌개 영수증도 「카페」라 한다 — 노트북 벤치 20/20 오답). 순서대로 첫 일치가 이긴다.
VENDOR_KEYWORDS = (
    ("교통", ("ktx", "srt", "승차권", "항공", "e-ticket", "탑승", "운임", "고속버스", "택시", "톨게이트")),
    ("숙박", ("숙박업소", "호텔 인보이스", "invoice", "객실", "체크인")),
    ("주점", ("호프", "펍", "pub", "포차", "이자카야", "주점", "bar ", "칵테일")),
    ("식당", ("찌개", "국밥", "탕", "정식", "비빔밥", "칼국수", "냉면", "구이", "쌈밥", "식당", "뷔페", "한식", "중식", "일식", "분식", "회집", "참치", "삼겹")),
    ("카페", ("아메리카노", "라떼", "커피", "coffee", "카페", "cafe", "에이드", "케이크", "디저트", "베이커리", "밀크티")),
)


def infer_vendor_type(text: str) -> Optional[str]:
    low = (text or "").lower()
    for vtype, keys in VENDOR_KEYWORDS:
        if any(k in low for k in keys):
            return vtype
    return None


_DATE = r"(\d{4}-\d{2}-\d{2})"
_RANGE = re.compile(_DATE + r"\s*[~∼～\-–]\s*" + _DATE)
_DEST = re.compile(r"출장지\s*[:：]\s*([^\n。]+?)(?=\s*\.\s|\s*기간|\s*목적|\n|$)")
# 합계 숫자는 온전한 것만 — 쉼표 묶음이 끝까지 맞거나, 쉼표 없는 네 자리 이상이거나, 바로 뒤가 「원」.
# OCR이 「합계 52,80뻔」처럼 깨뜨리면 앞 「52」를 잡지 않고 다음 합계(같은 건의 회의록 등)로 넘어간다(09-29).
# 「원」을 「8」로 읽은 「64,0008」은 묶음이 끝났으니 64,000(Tesseract에 흔함 — ocr_smoke M07～M09).
_TOTAL = re.compile(r"합\s*계\s*[:：]?\s*(\d{1,3}(?:,\d{3})+(?!,\d)|\d{4,}(?![\d,])|\d+(?=\s*원))")
_AMOUNT = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,})\s*원")
_MEAL = re.compile(r"(식사|점심|저녁|조식|중식|석식|식대)\s*(를|을)?\s*제공")


_TEXT_DATE = re.compile(r"(?<!\d)(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)")
_VENUE = re.compile(r"장소\s*[:：]\s*([^()/,\n]+)")


def _nullish(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "none", "null", "미상", "불명"))


def refine_with_text(extracted: Dict[str, Any], text: str) -> Dict[str, Any]:
    """모델의 범주 판단 중 문서 텍스트로 확정할 수 있는 것은 코드가 덮어쓴다(판정은 코드).
    - has_alcohol: 주류·주점 키워드가 있으면 True, 없으면 False (모델 값은 쓰지 않는다)
    - vendor_type: 품목·문서 키워드(VENDOR_KEYWORDS)가 있으면 그것, 없으면 모델 값(단 「주점」은 주류 키워드 없으면 「식당」)
    - vendor_name: 회의록 「장소: X」가 영수증 원문에도 있으면 X(두 문서 일치)
    - date: 모델 날짜가 원문에 없고 월·일이 같은 원문 날짜가 하나뿐이면 그 날짜(OCR 연도 오독)
    - amount_total: 「합계 N원」이 있으면 그 값. 없고 모델 값이 없거나 비현실적(<1,000)이면 「N원」 합산
    - trip: 기간(YYYY-MM-DD ~ YYYY-MM-DD)·출장지·국내/국외·식사 제공을 텍스트에서 채운다. 집행일이 비면 출장 시작일"""
    out = dict(extracted)
    text = text or ""
    low = text.lower()
    found = any(k.lower() in low for k in ALCOHOL_KEYWORDS)
    out["has_alcohol"] = found
    inferred = infer_vendor_type(text)
    if inferred:
        out["vendor_type"] = inferred
    elif out.get("vendor_type") == "주점" and not found:
        out["vendor_type"] = "식당"

    # 가맹점명이 원문에서 낱말 중간에서만 끊기면(「한식당 미」 ← 「한식당 미가」) 그 낱말 끝까지 늘린다 —
    # Gemini 사진 OCR 「한식당미가」가 붙자 모델이 이름을 잘랐다(09-29). 원문에 없거나 온전한 낱말로 있으면 그대로.
    v = out.get("vendor_name")
    if isinstance(v, str) and v.strip():
        v = v.strip()
        if not re.search(re.escape(v) + r"(?![가-힣A-Za-z0-9])", text):
            cut = re.search(re.escape(v) + r"[가-힣A-Za-z0-9]+", text)
            if cut:
                out["vendor_name"] = cut.group(0)

    # 회의록의 「장소: X」가 영수증 원문에도 찍혀 있으면(공백 무시) 두 문서가 맞춰 준 상호다 — 그걸 쓴다.
    # 사진 OCR에서 모델이 「대표 김미가」(→「대총김미가」)나 「sz. 금액」 줄을 상호로 뽑았다(10-01). 영수증에 없으면 모델 값 그대로.
    venue = _VENUE.search(text)
    if venue:
        x = venue.group(1).strip()
        flat = lambda s: re.sub(r"\s+", "", s or "")
        if x and flat(text).count(flat(x)) >= 2 and flat(out.get("vendor_name")) != flat(x):
            out["vendor_name"] = x

    # 모델 날짜가 원문 어디에도 없고, 월·일이 같은 원문 날짜가 딱 하나면 연도 오독이다 — 그 날짜를 쓴다.
    # 사진 OCR 「20226-06-16」을 모델이 2022-06-16으로 냈고 회의록엔 2026-06-16이 있었다(10-01).
    d0 = out.get("date")
    if isinstance(d0, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d0.strip()):
        d0 = d0.strip()
        seen = {f"{y}-{int(mo):02d}-{int(dd):02d}" for y, mo, dd in _TEXT_DATE.findall(text)}
        if d0 not in seen:
            same = {s for s in seen if s[5:] == d0[5:]}
            if len(same) == 1:
                out["date"] = same.pop()

    m = _TOTAL.search(text)
    if m:
        out["amount_total"] = int(m.group(1).replace(",", ""))
    else:
        cur = out.get("amount_total")
        if cur is None or (isinstance(cur, (int, float)) and cur < 1000):
            amounts = [int(a.replace(",", "")) for a in _AMOUNT.findall(text)]
            if amounts:
                out["amount_total"] = sum(amounts)

    trip = out.get("trip")
    if out.get("category") == "출장비" or trip or "출장" in text:
        t = dict(trip or {})
        for k in ("destination", "start", "end"):
            if _nullish(t.get(k)):
                t[k] = None
        r = _RANGE.search(text)
        if r:
            t["start"], t["end"] = t.get("start") or r.group(1), t.get("end") or r.group(2)
        d = _DEST.search(text)
        if d and not t.get("destination"):
            t["destination"] = d.group(1).strip().rstrip(".")
        if t.get("domestic") is None:
            if "국외" in text or "해외" in text:
                t["domestic"] = False
            elif "국내" in text:
                t["domestic"] = True
            elif t.get("destination") and re.search(r"[A-Za-z]", t["destination"]):
                t["domestic"] = False
        if t.get("meals_provided") is None and _MEAL.search(text):
            t["meals_provided"] = True
        out["trip"] = t
        if _nullish(out.get("date")) and t.get("start"):
            out["date"] = t["start"]
    return out


def _int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def to_case_input(extracted: Dict[str, Any], doc_types: Iterable[str] = (),
                  overrides: Optional[Dict[str, Any]] = None, institution: Optional[str] = None,
                  participants: Optional[Iterable[str]] = None) -> CaseInput:
    doc_types = set(doc_types)
    ov = overrides or {}
    attendees = [Attendee(name=str(a.get("name", "")).strip(), affiliation=a.get("affiliation"),
                          external=a.get("external"), participant=a.get("participant"))
                 for a in (extracted.get("attendees") or []) if a and a.get("name")]
    attendees = derive_participant(derive_external(attendees, institution), participants)
    trip = None
    t = extracted.get("trip")
    if t or extracted.get("category") == "출장비":
        t = t or {}
        trip = Trip(destination=t.get("destination"), start=t.get("start"), end=t.get("end"),
                    domestic=t.get("domestic"), meals_provided=t.get("meals_provided"),
                    plan_doc=ov.get("plan_doc", "출장신청서" in doc_types or t.get("plan_doc") is True),
                    report_doc=ov.get("report_doc", "출장결과보고서" in doc_types or t.get("report_doc") is True),
                    meal_claimed_full=ov.get("meal_claimed_full", t.get("meal_claimed_full")),
                    has_transport_evidence=ov.get("has_transport_evidence", t.get("has_transport_evidence")))
    return CaseInput(
        category=ov.get("category", extracted.get("category") or "불명"),
        date=ov.get("date", extracted.get("date")),
        time=ov.get("time", extracted.get("time")),
        amount_total=_int_or_none(ov.get("amount_total", extracted.get("amount_total"))),
        vat_included=ov.get("vat_included", extracted.get("vat_included")),
        vendor_type=ov.get("vendor_type", extracted.get("vendor_type")),
        has_alcohol=ov.get("has_alcohol", extracted.get("has_alcohol")),
        attendees=attendees,
        attendee_count=_int_or_none(ov.get("attendee_count", extracted.get("attendee_count"))) or (len(attendees) or None),
        purpose=ov.get("purpose", extracted.get("purpose")),
        has_minutes=bool(ov.get("has_minutes", "회의록" in doc_types)),
        has_internal_approval=bool(ov.get("has_internal_approval", "내부결재문서" in doc_types)),
        has_simplified_evidence=bool(ov.get("has_simplified_evidence", False)),
        basic_project=bool(ov.get("basic_project", False)),
        innovation_fund=bool(ov.get("innovation_fund", False)),
        trip=trip,
    )
