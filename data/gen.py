"""합성 정답지 생성기 — 실제 서식·공개 집행내역·감사 사례를 본떠 60건(회의비 30·출장비 30)을 만든다.

사용: .venv/bin/python -m data.gen [--out data/answer_key.json] [--seed 7]
케이스 = {"id", "docs":[{"kind","text"}], "gold":{추출 정답}, "flags":{화면 플래그·출장 상세·출장 중인 참석자}, "expected":{"verdict","rule_ids"}, "tags", "source", "image"}

본뜬 것(agy 리서치 2026-09-24, ~/projects/00-research/2026-09/w3/2026-09-24-rnd-meeting-travel-expense-docs/):
- 회의록 필드: 고려대 산학협력단 <양식7> 회의록·서울대 경제연구소 [양식4] 회의록 — 과제번호·회의일시(시작~종료)·장소(상호+주소)·목적·내용·참석자(참여연구자/외부) 구분·집행금액·1인당
- 상호·주소·인원·금액·시각: 서울시 업무추진비·통일부 업무추진비 공개내역 발췌(`data/seeds/`) — R&D 회의 문맥으로 목적만 바꿔 전이
- 출장 문서: 고려대 [양식5-1] 출장품의·여비신청서, KAIST [별표8-1] 국외출장계획서·[별표10-1] 결과보고서 — 여비 4비목(운임·일비·식비·숙박비), 식사 제공 시 차감 문구
- 감사 사례: C-01(참석 인원 대비 고액), C-03(주점 위장), C-10(사전결재 미비, 기상청 특정감사), C-11(출장 식대 이중), C-15(학회 등록비 식사 포함)
기대 판정은 지어내지 않고 규칙엔진으로 검산한다 — 시나리오의 의도(intended)와 엔진이 어긋나면 생성이 실패한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date as _date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from panjeong.extract.prompt import ALCOHOL_KEYWORDS, to_case_input
from panjeong.rules.engine import judge
from panjeong.rules.models import CaseInput, Context, Policy

HERE = Path(__file__).resolve().parent
SEEDS = HERE / "seeds"
INSTITUTION = "한국전자통신연구원"
PROJECT = {"no": "2026-DEMO-001", "name": "연구비 판정관 시연", "pi": "김지우"}
PARTICIPANTS = ["김철수", "이영희", "정수진"]                       # 과제 참여연구자 (data/project.json과 동일)
HOLIDAYS = {"2026-05-05", "2026-06-03", "2026-06-06", "2026-08-17", "2026-10-09"}
TODAY = "2026-09-24"

ROSTER = {  # 이름 → 소속 표기 (회의록에 그대로 적힌다)
    "김철수": "한국전자통신연구원 선임연구원", "이영희": "한국전자통신연구원 책임연구원", "정수진": "한국전자통신연구원 연구원",
    "최민호": "한국전자통신연구원 행정팀", "한지원": "한국전자통신연구원 연구원(타 과제)",
    "박민수": "KAIST 교수", "이준호": "서울대학교 부교수", "김나래": "한국과학기술기획평가원 연구위원",
    "오세훈": "㈜퓨처테크 대표", "장미란": "고려대학교 연구교수", "윤도현": "한국연구재단 PM",
}
INTERNAL = ["김철수", "이영희", "정수진"]
NONPART = ["최민호", "한지원"]
EXTERNAL = ["박민수", "이준호", "김나래", "오세훈", "장미란", "윤도현"]
PURPOSES = ["온디바이스 경량화 모델 성능 검토 회의", "외부 자문위원 초청 기술 자문 회의", "과제 중간점검 결과 협의",
            "학습 데이터셋 구축 방향 협의", "연차 보고서 작성 방향 회의", "규칙엔진 조문 매핑 검토 회의",
            "실증 기관 요구사항 청취 회의", "특허 출원 범위 협의", "공동연구기관 역할 분담 회의", "시제품 평가 지표 협의"]
MAINS = {"식당": ["된장찌개", "돼지국밥", "갈비탕", "비빔밥", "칼국수", "제육정식", "생선구이 정식", "냉면", "설렁탕", "쌈밥 정식"],
         "카페": ["아메리카노", "카페라떼", "자몽에이드", "밀크티"], "주점": ["안주 모둠", "치킨", "감자튀김"]}
WEEKDAY_KO = "월화수목금토일"


def _load(name: str) -> List[Dict[str, Any]]:
    p = SEEDS / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    low = lambda s: (s or "").lower()
    return [r for r in rows if not any(k.lower() in low(r["vendor"]) or k.lower() in low(r.get("purpose")) for k in ALCOHOL_KEYWORDS)]


def _vendor_type(vendor: str) -> str:
    return "카페" if any(k in vendor.lower() for k in ("카페", "커피", "coffee", "베이커리", "빵", "디저트", "cafe")) else "식당"


def _ko_date(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return f"{d}({WEEKDAY_KO[_date(y, m, dd).weekday()]})"


def _shift(d: str, days: int) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return (_date(y, m, dd) + timedelta(days=days)).isoformat()


def _biz(rng: random.Random) -> str:
    return f"{rng.randint(100, 899)}-{rng.randint(10, 99)}-{rng.randint(10000, 99999)}"


# ---------------------------------------------------------------- 회의비 문서
def receipt(rng: random.Random, vendor: str, address: str, date: str, time: str, total: int, n: int,
            vtype: str, alcohol: Optional[str] = None, memo: Optional[str] = None) -> str:
    items = []
    alc_amt = 0
    if alcohol:
        alc_amt = {"소주": 8000, "생맥주": 12000}[alcohol]
        items.append((alcohol, 2, alc_amt))
    main = rng.choice(MAINS[vtype])
    base = total - alc_amt
    unit = max(1000, (base // n) // 100 * 100)
    items.insert(0, (main, n, unit * n))
    rest = base - unit * n
    if rest > 0:
        items.append(("음료" if vtype == "식당" else "디저트", 1, rest))
    lines = [f"[카드매출전표] {vendor}", f"사업자번호 {_biz(rng)}  {address}", f"거래일시 {date} {time}",
             "품목  수량  금액"] + [f"{name}  {q}  {amt:,}" for name, q, amt in items]
    lines.append(f"합계 {total:,}원 (부가세 포함)")
    lines.append(f"신용카드 승인 {rng.randint(10000000, 99999999)}  연구비카드")
    if memo:
        lines.append(f"메모: {memo}")
    return "\n".join(lines)


def minutes(vendor: str, address: str, date: str, time: str, purpose: str, names: List[str], total: int) -> str:
    part = [f"{n}({ROSTER[n]})" for n in names if n in INTERNAL]
    other = [f"{n}({ROSTER[n]})" for n in names if n not in INTERNAL]
    h, m = (int(x) for x in time.split(":"))
    end = f"{(h + 1) % 24:02d}:{m:02d}"
    return "\n".join([
        f"[회의록] 과제번호 {PROJECT['no']} · 과제명 {PROJECT['name']} · 연구책임자 {PROJECT['pi']}({INSTITUTION})",
        f"회의일시: {_ko_date(date)} {time}~{end}",
        f"회의장소: {vendor} ({address})",
        f"회의목적: {purpose}",
        f"회의내용: {purpose} 관련 안건 검토, 의견 수렴, 후속 일정 확정.",
        f"참석자(참여연구자): {', '.join(part) if part else '없음'}",
        f"참석자(외부·과제 미참여): {', '.join(other) if other else '없음'}",
        f"집행금액: {total:,}원 (참석 {len(names)}명, 1인당 {total // len(names):,}원)",
    ])


def approval(date: str, purpose: str, names: List[str], total: int) -> str:
    ext = [n for n in names if n not in INTERNAL]
    return "\n".join([
        f"[내부결재문서] 회의비 집행 품의 — 결재 완료 {_shift(date, -2)} (회의 시작 전)",
        f"과제번호 {PROJECT['no']} · 회의 일시 {date} · 목적 {purpose}",
        f"외부참석자: {', '.join(f'{n}({ROSTER[n]})' for n in ext) if ext else '없음'} · 사용 예정 금액 {total:,}원",
    ])


def simplified(date: str, time: str, vendor: str, purpose: str, names: List[str]) -> str:
    return (f"[영수증 이면 기재] 목적: {purpose} / 일시: {date} {time} / 장소: {vendor} / 내용: 안건 협의 및 결정 / "
            f"참석자: {', '.join(f'{n}({ROSTER[n]})' for n in names)}")


MEETING_SPECS = [
    # id, date, names, docs(영=영수증 회=회의록 결=내부결재 간=간이), amount(None=시드), opts, intended, tags
    ("M01", "2026-06-12", ["김철수", "이영희", "박민수", "정수진"], "영회", None, {}, "가능", ["외부있음"]),
    ("M02", "2026-06-15", ["김철수", "이영희", "정수진", "박민수"], "영간", 100000, {"simplified": True}, "가능", ["간이증빙-10만원이하", "외부있음"]),
    ("M03", "2026-06-16", ["김철수", "이영희", "정수진", "이준호"], "영간", 101000, {"simplified": True}, "보완", ["10만원초과-회의록없음"]),
    ("M04", "2026-06-17", ["김철수", "이영희", "김나래"], "영", 80000, {"memo": True}, "보완", ["회의록없음-메모만"]),
    ("M05", "2026-06-12", ["김철수", "이영희"], "영회", None, {}, "불가", ["외부없음-W2"]),
    ("M06", "2026-06-12", ["김철수", "이영희", "최민호"], "영회", None, {}, "가능", ["동일기관-미참여자-W2"]),
    ("M07", "2026-06-12", ["김철수", "이영희", "정수진"], "영회", None, {"innovation": True}, "가능", ["연구혁신비-W2"]),
    ("M08", "2026-05-20", ["김철수", "이영희"], "영회", None, {"innovation": True}, "불가", ["연구혁신비-시행전"]),
    ("M09", "2026-06-13", ["김철수", "박민수", "이영희"], "영회", None, {}, "보완", ["주말"]),
    ("M10", "2026-05-05", ["김철수", "이영희", "장미란"], "영회결", None, {}, "보완", ["W1마지막날-2026-05-05", "공휴일"]),
    ("M11", "2026-05-06", ["김철수", "정수진", "윤도현"], "영회", None, {}, "가능", ["W2첫날-2026-05-06"]),
    ("M12", "2025-03-10", ["김철수", "이영희", "박민수", "정수진"], "영회", None, {}, "보완", ["사전결재없음-W1"]),
    ("M13", "2025-03-11", ["김철수", "이영희", "이준호"], "영회결", None, {}, "가능", ["사전결재있음-W1"]),
    ("M14", "2025-03-12", ["김철수", "이영희"], "영회결", None, {"basic": True}, "불가", ["기본사업-W1불인정"]),
    ("M15", "2024-10-15", ["김철수", "이영희"], "영회", None, {"basic": True}, "가능", ["기본사업-W0"]),
    ("M16", "2024-10-16", ["김철수", "정수진"], "영회", None, {}, "불가", ["외부없음-W0"]),
    ("M17", "2024-11-30", ["김철수", "이영희", "박민수"], "영회", None, {}, "보완", ["개정전날-2024-11-30", "주말"]),
    ("M18", "2024-12-01", ["김철수", "이영희", "김나래"], "영회결", None, {}, "보완", ["개정일-2024-12-01", "주말"]),
    ("M19", "2026-07-02", ["김철수", "이영희", "오세훈"], "영회", None, {"alcohol": "소주"}, "보완", ["주류"]),
    ("M20", "2026-07-03", ["김철수", "박민수", "정수진"], "영회", 84000, {"alcohol": "생맥주", "vendor": ("호프 앤 펍 대전점", "대전 유성구 대학로 99"), "vtype": "주점"}, "보완", ["주류", "주점", "감사사례-C-03"]),
    ("M21", "2026-07-08", ["김철수", "이영희", "이준호"], "영회", 390000, {"vendor": ("호텔 인터불고 뷔페", "대구 수성구 팔공로 212"), "vtype": "식당"}, "보완", ["1인한도초과", "감사사례-C-01"]),
    ("M22", "2026-06-20", ["김철수", "이영희", "박민수"], "영회", None, {"on_trip": ["김철수"]}, "불가", ["출장일중복", "주말"]),
    ("M23", "2026-06-18", [], "영", 36000, {"time": "12:20", "count": 3}, "불가", ["근거없는-평일점심"]),
    ("M24", "2026-06-18", [], "영", 54000, {"time": "19:10", "count": 3}, "보완", ["근거없는-평일저녁"]),
    ("M25", "2025-04-02", ["김철수", "이영희", "정수진", "박민수", "이준호", "김나래", "오세훈", "장미란", "윤도현", "최민호", "한지원"], "영회", 517000, {}, "보완", ["사전결재없음-W1", "1인한도초과", "감사사례-C-10"]),
    ("M26", "2026-07-01", ["이영희", "김나래", "정수진"], "영회", None, {"vtype": "카페", "vendor": ("카페 브루잉", "대전 유성구 가정로 218")}, "가능", ["카페", "외부있음"]),
    ("M27", "2026-08-20", ["김철수", "김나래", "윤도현"], "영회", None, {"seed": "mou"}, "가능", ["외부있음", "통일부시드"]),
    ("M28", "2026-01-15", ["김철수", "이영희", "장미란"], "영회결", 99000, {}, "보완", ["1인한도초과", "W1"]),
    ("M29", "2026-06-12", ["김철수", "이영희", "정수진", "박민수", "이준호"], "영회", None, {"seed": "mou"}, "가능", ["외부있음", "통일부시드"]),
    ("M30", "2026-09-10", ["김철수", "이영희", "정수진", "오세훈", "장미란"], "영회", None, {}, "가능", ["외부있음"]),
]


def _meeting_case(rng: random.Random, spec, seoul, mou) -> Dict[str, Any]:
    cid, date, names, docs, amount, opts, intended, tags = spec
    n = opts.get("count") or len(names)
    seed = None
    if opts.get("seed") == "mou" and mou:
        seed = mou[rng.randrange(len(mou))]
        vendor, address = seed["vendor"], "서울 종로구 (통일부 공개내역 상호)"
        time = opts.get("time") or rng.choice(["12:10", "12:35", "18:40", "19:05"])
        total = amount or int(seed["amount"])
        source = f"통일부 기관장 업무추진비 공개내역 {seed['date']} {seed['vendor']} {int(seed['amount']):,}원 — 상호·금액 참고"
    elif seoul:
        pool = [r for r in seoul if int(r["headcount"]) == n] or seoul
        seed = pool[rng.randrange(len(pool))]
        vendor, address = seed["vendor"], seed["address"] or "서울 중구"
        time = opts.get("time") or seed["time"]
        total = amount or int(seed["amount"])
        source = f"서울시 업무추진비 공개내역 {seed['date']} {seed['vendor']} {int(seed['headcount'])}명 {int(seed['amount']):,}원 — 상호·인원·금액·시각 참고"
    else:
        vendor, address, time, total, source = "한식당 미가", "대전 유성구 대학로 291", opts.get("time") or "12:40", amount or 13000 * n, "내장 기본값"
    if opts.get("vendor"):
        vendor, address = opts["vendor"]
    vtype = opts.get("vtype") or _vendor_type(vendor)
    if not amount and seed and total / n > 30000:
        total = 12000 * n + 4800   # 시드가 한도 초과면 한도 안으로 — 한도 초과 케이스는 금액을 명시한다
    alcohol = opts.get("alcohol")
    purpose = rng.choice(PURPOSES) if names else None
    memo = None
    if opts.get("memo"):
        memo = f"{purpose}, 참석 {n}명: " + ", ".join(f"{x}({ROSTER[x]})" for x in names)
    d: List[Dict[str, str]] = [{"kind": "영수증", "text": receipt(rng, vendor, address, date, time, total, n, vtype, alcohol, memo)}]
    if "회" in docs:
        d.append({"kind": "회의록", "text": minutes(vendor, address, date, time, purpose, names, total)})
    if "결" in docs:
        d.append({"kind": "내부결재문서", "text": approval(date, purpose, names, total)})
    if "간" in docs:
        d.append({"kind": "기타", "text": simplified(date, time, vendor, purpose, names)})
    attendees = [{"name": x, "affiliation": ROSTER[x], "external": INSTITUTION not in ROSTER[x], "participant": x in PARTICIPANTS}
                 for x in names]
    gold = {"category": "회의비", "amount_total": total, "date": date, "time": time, "vendor_name": vendor, "vendor_type": vtype,
            "has_alcohol": bool(alcohol), "attendee_count": n, "attendees": attendees, "purpose": purpose, "vat_included": True}
    flags = {"has_simplified_evidence": bool(opts.get("simplified")), "basic_project": bool(opts.get("basic")),
             "innovation_fund": bool(opts.get("innovation")), "on_trip": opts.get("on_trip", [])}
    if seed:
        tags = tags + ["공개데이터시드"]
    return {"id": cid, "docs": d, "gold": gold, "flags": flags, "intended": intended, "tags": tags, "source": source}


# ---------------------------------------------------------------- 출장비 문서
DOMESTIC = [("부산", "한국정보과학회 하계학술대회", 59800), ("대전", "출연연 공동 워크숍", 23700), ("광주", "실증 기관 현장 방문", 46800),
            ("대구", "협력기업 기술 협의", 43500), ("제주", "국제 AI 심포지엄", 98000), ("강릉", "데이터 수집 현장 조사", 27600),
            ("전주", "지역 실증센터 협의", 34900), ("포항", "장비 공동 활용 협의", 52300), ("세종", "과기정통부 과제 점검회의", 19800),
            ("춘천", "공동연구기관 회의", 21400), ("천안", "시제품 평가 회의", 15200), ("울산", "산업체 현장 실증", 56700)]
OVERSEAS = [("Boston, USA", "NeurIPS 워크숍 발표", 1850000, 240000), ("Tokyo, Japan", "IEEE ICASSP 발표", 620000, 180000),
            ("Singapore", "ACL 학회 참가", 890000, 210000), ("Berlin, Germany", "협력기관 공동연구 협의", 1420000, 200000),
            ("Vienna, Austria", "ISCA Interspeech 발표", 1510000, 190000), ("San Jose, USA", "협력기업 기술 실사", 1930000, 260000),
            ("Vancouver, Canada", "CVPR 워크숍 발표", 1760000, 230000), ("Seoul→Taipei", "COMPUTEX 기술 조사", 480000, 150000)]


def plan_doc(name: str, dest: str, start: str, end: str, purpose: str, domestic: bool, total: int, items: List[str]) -> str:
    kind = "국내" if domestic else "국외"
    head = "[출장품의 및 여비신청서]" if domestic else "[국외출장계획서]"
    return "\n".join([
        f"{head} {kind} 출장 — 과제번호 {PROJECT['no']} · 과제명 {PROJECT['name']}",
        f"출장자: {name}({ROSTER[name]})", f"출장지: {dest}. 기간: {start} ~ {end}",
        f"출장목적: {purpose} (과제 연관성: 연구 결과 발표 및 협의)",
        "세부일정: " + ("학회 등록·발표·협의" if not domestic else "이동·회의·복귀"),
        f"예상 경비: {', '.join(items)} 합계 {total:,}원", f"결재일: {_shift(start, -7)}",
    ])


def report_doc(name: str, dest: str, start: str, end: str, purpose: str, domestic: bool, total: int, items: List[str],
               meals: bool) -> str:
    kind = "국내" if domestic else "국외"
    head = "[출장결과보고서(복명서)]" if domestic else "[국외출장결과보고서]"
    lines = [f"{head} {kind} 출장 — 과제번호 {PROJECT['no']}",
             f"출장자: {name}({ROSTER[name]})", f"출장지: {dest}. 기간: {start} ~ {end}",
             f"출장목적: {purpose}", "주요 업무내용: 발표 및 질의응답, 협력 기관 면담, 후속 협의 일정 확정.",
             f"여비 정산: {', '.join(items)} 합계 {total:,}원 (집행일 {start})",
             "증빙: " + ("승차권 영수증, 숙박 카드매출전표" if domestic else "e-ticket, 탑승권, 호텔 인보이스, 학회 참가증")]
    if meals:
        lines.append("비고: 학회 측 점심 제공(등록비 포함) — 식비 전액 청구")
    return "\n".join(lines)


def transport_receipt(rng: random.Random, dest: str, date: str, fare: int, domestic: bool) -> str:
    if domestic:
        return "\n".join([f"[승차권 영수증] KTX 서울→{dest} 왕복", f"승차일 {date}", f"운임 {fare:,}원", f"결제 연구비카드 승인 {rng.randint(10000000, 99999999)}"])
    return "\n".join([f"[e-ticket 영수증] 항공 인천→{dest} 왕복", f"출발일 {date}", f"항공료 {fare:,}원", f"결제 연구비카드 승인 {rng.randint(10000000, 99999999)}"])


TRAVEL_SPECS = [
    # id, name, kind(D=국내 O=국외), idx, start, nights, docs(계=계획서/신청서 결=결과보고서 영=교통 영수증), opts, intended, tags
    ("T01", "김철수", "D", 0, "2026-06-20", 1, "계결영", {}, "가능", ["국내-가능"]),
    ("T02", "이영희", "D", 1, "2026-06-24", 0, "계결영", {}, "가능", ["국내-당일"]),
    ("T03", "정수진", "D", 2, "2026-07-07", 1, "계결영", {"meals": True, "full": True}, "보완", ["식사제공-전액청구", "감사사례-C-11"]),
    ("T04", "김철수", "D", 3, "2026-07-14", 1, "계결영", {}, "가능", ["국내-가능"]),
    ("T05", "이영희", "D", 4, "2026-07-21", 2, "계결영", {"meals": True, "full": True}, "보완", ["식사제공-전액청구", "감사사례-C-15"]),
    ("T06", "정수진", "D", 5, "2026-08-04", 1, "계결", {"evidence": False}, "보완", ["교통증빙없음"]),
    ("T07", "김철수", "D", 6, "2026-08-11", 1, "계결영", {}, "가능", ["국내-가능"]),
    ("T08", "이영희", "D", 7, "2026-08-18", 2, "계결영", {}, "가능", ["국내-가능"]),
    ("T09", "정수진", "D", 8, "2026-08-25", 0, "계결영", {}, "가능", ["국내-당일"]),
    ("T10", "김철수", "D", 9, "2026-09-01", 1, "계결", {"evidence": False}, "보완", ["교통증빙없음"]),
    ("T11", "이영희", "D", 10, "2026-09-08", 0, "계결영", {"meals": True, "full": False}, "가능", ["식사제공-차감완료"]),
    ("T12", "정수진", "D", 11, "2026-09-15", 1, "계결영", {}, "가능", ["국내-가능"]),
    ("T13", "김철수", "D", 0, "2026-05-12", 1, "계결영", {"meals": True, "full": True}, "보완", ["식사제공-전액청구"]),
    ("T14", "이영희", "D", 2, "2026-05-19", 1, "계결영", {}, "가능", ["국내-가능"]),
    ("T15", "정수진", "D", 4, "2026-04-14", 2, "계결", {"evidence": False}, "보완", ["교통증빙없음"]),
    ("T16", "김철수", "O", 0, "2026-06-20", 5, "결영", {}, "보완", ["국외-계획서없음"]),
    ("T17", "이영희", "O", 1, "2026-05-25", 3, "계영", {}, "보완", ["국외-결과보고서없음"]),
    ("T18", "정수진", "O", 2, "2026-07-27", 4, "계결영", {}, "가능", ["국외-가능"]),
    ("T19", "김철수", "O", 3, "2026-08-03", 4, "계결영", {}, "가능", ["국외-가능"]),
    ("T20", "이영희", "O", 4, "2026-09-06", 5, "결영", {"meals": True, "full": True}, "보완", ["국외-계획서없음", "식사제공-전액청구"]),
    ("T21", "정수진", "O", 5, "2026-10-12", 4, "계영", {}, "가능", ["국외-미래출장-결과보고서불요"]),
    ("T22", "김철수", "O", 6, "2026-06-15", 5, "계결영", {}, "가능", ["국외-가능"]),
    ("T23", "이영희", "O", 7, "2026-06-02", 3, "계영", {}, "보완", ["국외-결과보고서없음"]),
    ("T24", "정수진", "O", 0, "2025-12-08", 5, "결영", {}, "보완", ["국외-계획서없음"]),
    ("T25", "김철수", "O", 1, "2026-01-19", 3, "계결영", {}, "가능", ["국외-가능"]),
    ("T26", "이영희", "O", 2, "2026-03-09", 4, "계결", {"evidence": False}, "보완", ["국외-교통증빙없음"]),
    ("T27", "정수진", "O", 3, "2026-04-06", 4, "계결영", {"meals": True, "full": False}, "가능", ["국외-식사제공-차감완료"]),
    ("T28", "김철수", "O", 4, "2026-02-16", 5, "계결영", {}, "가능", ["국외-가능"]),
    ("T29", "이영희", "D", 6, "2026-03-24", 1, "계결영", {}, "가능", ["국내-가능"]),
    ("T30", "정수진", "D", 8, "2026-02-03", 0, "계결영", {}, "가능", ["국내-당일"]),
]


def _travel_case(rng: random.Random, spec) -> Dict[str, Any]:
    cid, name, kind, idx, start, nights, docs, opts, intended, tags = spec
    domestic = kind == "D"
    end = _shift(start, nights)
    days = nights + 1
    meals = bool(opts.get("meals"))
    full = bool(opts.get("full"))
    if domestic:
        dest, purpose, fare = DOMESTIC[idx]
        fare_total = fare * 2
        per_day_meal = 20000
        meal = per_day_meal * days
        if meals and not full:
            meal -= per_day_meal // 3 * days          # 제공 끼니(1/3)씩 차감
        items = [f"운임 {fare_total:,}원", f"일비 {days}일 {20000 * days:,}원", f"식비 {days}일 {meal:,}원"]
        lodging = 80000 * nights
        if nights:
            items.append(f"숙박비 {nights}박 {lodging:,}원")
        total = fare_total + 20000 * days + meal + lodging
    else:
        dest, purpose, fare, per_day = OVERSEAS[idx]
        fare_total = fare
        meal = per_day * days
        if meals and not full:
            meal -= per_day // 3 * days
        lodging = 220000 * nights
        items = [f"항공료 {fare_total:,}원", f"일비 {days}일 {38000 * days:,}원", f"식비 {days}일 {meal:,}원", f"숙박비 {nights}박 {lodging:,}원"]
        total = fare_total + 38000 * days + meal + lodging
    if meals and not full:
        items.append("(학회 제공 식사 제외 후 산정)")
    d: List[Dict[str, str]] = []
    if "계" in docs:
        d.append({"kind": "출장신청서", "text": plan_doc(name, dest, start, end, purpose, domestic, total, items)})
    if "결" in docs:
        d.append({"kind": "출장결과보고서", "text": report_doc(name, dest, start, end, purpose, domestic, total, items, meals and full)})
    if "영" in docs:
        d.append({"kind": "영수증", "text": transport_receipt(rng, dest.split(",")[0], start, fare_total, domestic)})
    if not d:
        raise ValueError(f"{cid}: 출장 케이스는 문서가 하나 이상")
    gold = {"category": "출장비", "amount_total": total, "date": start, "time": None, "vendor_name": None,
            "vendor_type": "교통", "has_alcohol": False, "attendee_count": 1,
            "attendees": [{"name": name, "affiliation": ROSTER[name], "external": False, "participant": True}],
            "purpose": purpose, "vat_included": None}
    flags = {"trip": {"destination": dest, "start": start, "end": end, "domestic": domestic, "meals_provided": meals or None,
                      "plan_doc": "계" in docs, "report_doc": "결" in docs, "meal_claimed_full": full if meals else None,
                      "has_transport_evidence": opts.get("evidence", "영" in docs)}}
    src = ("고려대 [양식5-1] 출장품의·여비신청서·[양식6] 출장보고서 구조" if domestic
           else "KAIST [별표8-1] 국외출장계획서·[별표10-1] 국외출장결과보고서 구조")
    if any("감사사례" in t for t in tags):
        src += " · " + ", ".join(t for t in tags if "감사사례" in t)
    return {"id": cid, "docs": d, "gold": gold, "flags": flags, "intended": intended, "tags": tags, "source": src}


# ---------------------------------------------------------------- 엔진 검산
def case_input_from(c: Dict[str, Any]) -> CaseInput:
    g, f = c["gold"], c["flags"]
    extracted = {k: g.get(k) for k in ("category", "amount_total", "date", "time", "vendor_type", "has_alcohol",
                                       "attendee_count", "purpose", "vat_included")}
    extracted["attendees"] = [{"name": a["name"], "affiliation": a.get("affiliation"), "external": None, "participant": None}
                              for a in g.get("attendees") or []]
    overrides: Dict[str, Any] = {k: f[k] for k in ("has_simplified_evidence", "basic_project", "innovation_fund") if k in f}
    if f.get("trip"):
        t = f["trip"]
        extracted["trip"] = {k: t.get(k) for k in ("destination", "start", "end", "domestic", "meals_provided")}
        overrides.update({k: t.get(k) for k in ("plan_doc", "report_doc", "meal_claimed_full", "has_transport_evidence")})
    return to_case_input(extracted, doc_types=[d["kind"] for d in c["docs"]], overrides=overrides,
                         institution=INSTITUTION, participants=PARTICIPANTS)


def context_from(c: Dict[str, Any]) -> Context:
    return Context(attendees_on_trip=set(c["flags"].get("on_trip") or []), policy=Policy(holidays=set(HOLIDAYS)), today=TODAY)


def build_cases(seed: int = 7) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    seoul, mou = _load("seoul_meals.csv"), _load("mou_meals.csv")
    cases = [_meeting_case(rng, s, seoul, mou) for s in MEETING_SPECS] + [_travel_case(rng, s) for s in TRAVEL_SPECS]
    for i, c in enumerate(cases):
        j = judge(case_input_from(c), context_from(c))
        if j.verdict != c["intended"]:
            raise AssertionError(f"{c['id']}: 시나리오 의도 {c['intended']} ≠ 엔진 {j.verdict} {[r.rule_id for r in j.reasons]}")
        c["expected"] = {"verdict": j.verdict, "rule_ids": sorted({r.rule_id for r in j.reasons}), "notice_no": j.notice_no}
        c["image"] = c["gold"]["category"] == "회의비" and i < 20
    return cases


def write_answer_key(out: Path, seed: int = 7) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_cases(seed), ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "answer_key.json"))
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    p = write_answer_key(Path(a.out), a.seed)
    data = json.loads(p.read_text(encoding="utf-8"))
    from collections import Counter
    print(f"→ {p}  {len(data)}건  판정 {dict(Counter(c['expected']['verdict'] for c in data))}")
