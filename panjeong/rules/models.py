"""규칙엔진 입출력 모델. 추출 JSON을 화면에서 고친 값이 CaseInput이 된다."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class Attendee:
    name: str
    affiliation: Optional[str] = None
    external: Optional[bool] = None      # 연구개발기관 외부인 여부 (W0·W1: 「기관에 소속되지 않은 자」)
    participant: Optional[bool] = None   # 해당 과제 참여연구자 여부 (W2: 「참여연구자만 참여하는 회의」)


@dataclass
class Trip:
    destination: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    domestic: Optional[bool] = None
    meals_provided: Optional[bool] = None
    plan_doc: Optional[bool] = None
    report_doc: Optional[bool] = None
    meal_claimed_full: Optional[bool] = None
    has_transport_evidence: Optional[bool] = None


@dataclass
class CaseInput:
    category: str                       # 회의비 | 출장비 | 불명
    date: Optional[str]                 # 집행일 YYYY-MM-DD
    time: Optional[str] = None          # HH:MM
    amount_total: Optional[int] = None
    vat_included: Optional[bool] = None
    vendor_type: Optional[str] = None   # 식당|카페|주점|호텔|교통|숙박|기타
    has_alcohol: Optional[bool] = None
    attendees: List[Attendee] = field(default_factory=list)
    attendee_count: Optional[int] = None
    purpose: Optional[str] = None
    has_minutes: bool = False           # 회의록
    has_internal_approval: bool = False # 내부결재문서
    has_simplified_evidence: bool = False  # 목적·일시·장소·내용·참석자 명단 증명자료(10만 원 이하)
    basic_project: bool = False         # 출연연 기본사업 (구 제25조④ 단서 — 2024-11-30까지만)
    innovation_fund: bool = False       # 연구혁신비 비목으로 집행 (제25조의2⑥ — 2026-06-11부터)
    trip: Optional[Trip] = None


@dataclass
class Policy:
    per_person_cap: int = 30000
    holidays: Set[str] = field(default_factory=set)
    lunch_start: str = "11:30"
    lunch_end: str = "14:00"


@dataclass
class Context:
    exceptions: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # exception_key -> {"source_queue_id": n, ...}
    attendees_on_trip: Set[str] = field(default_factory=set)             # 집행일에 출장 중인 이름
    policy: Policy = field(default_factory=Policy)
    today: Optional[str] = None


@dataclass
class Reason:
    rule_id: str
    verdict: str                 # 가능 | 보완 | 불가
    article: str
    text: str
    source_kind: str
    url: str = ""
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    notice_no: Optional[str] = None
    action: Optional[str] = None  # 보완 시 해야 할 일
    cite: Optional[str] = None    # statutes.CITATIONS 키 — 판정 화면이 조문 원문을 꺼낸다


@dataclass
class Judgment:
    verdict: str
    reasons: List[Reason]
    required_actions: List[str]
    basis_date: Optional[str]
    notice_no: Optional[str]
    window_code: Optional[str]
