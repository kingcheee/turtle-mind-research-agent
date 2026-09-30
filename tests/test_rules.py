"""규칙엔진 — 조문 하나가 판정 하나. 각 테스트는 규칙 ID 하나를 겨냥한다."""
from panjeong.rules.models import Attendee, CaseInput, Context, Trip
from panjeong.rules.engine import judge, exception_key


def att(name, aff="한국전자통신연구원", external=False, participant=None):
    # participant 미지정이면 기관 내부자 = 과제 참여연구자로 본다(명단 없을 때의 보수적 기본값)
    if participant is None and external is not None:
        participant = not external
    return Attendee(name=name, affiliation=aff, external=external, participant=participant)


def meeting(**over):
    base = dict(
        category="회의비", date="2026-06-12", time="12:40",
        amount_total=52800, vat_included=True, vendor_type="식당", has_alcohol=False,
        attendees=[att("김철수"), att("이영희"), att("박민수", "KAIST", True), att("정수진")],
        attendee_count=4, purpose="과제 중간점검 회의",
        has_minutes=True, has_internal_approval=False, has_simplified_evidence=False,
        basic_project=False, trip=None,
    )
    base.update(over)
    return CaseInput(**base)


def travel(**over):
    base = dict(
        category="출장비", date="2026-06-20", time=None,
        amount_total=180000, vat_included=None, vendor_type="교통", has_alcohol=None,
        attendees=[att("김철수")], attendee_count=1, purpose="학회 발표",
        has_minutes=False, has_internal_approval=True, has_simplified_evidence=False,
        basic_project=False,
        trip=Trip(destination="부산", start="2026-06-20", end="2026-06-21", domestic=True,
                  meals_provided=False, plan_doc=True, report_doc=True,
                  meal_claimed_full=True, has_transport_evidence=True),
    )
    base.update(over)
    return CaseInput(**base)


def rule_ids(j):
    return {r.rule_id for r in j.reasons}


# --- 회의비 ---------------------------------------------------------------

def test_external_meeting_with_minutes_is_allowed():
    j = judge(meeting(), Context())
    assert j.verdict == "가능"
    assert j.basis_date == "2026-06-12"
    assert j.notice_no == "제2026-38호"


def test_internal_only_meal_after_2026_05_06_is_rejected_by_25_4():
    j = judge(meeting(attendees=[att("김철수"), att("이영희")], attendee_count=2), Context())
    assert j.verdict == "불가"
    assert "M-25-4-EXT" in rule_ids(j)
    r = next(r for r in j.reasons if r.rule_id == "M-25-4-EXT")
    assert r.article == "제25조 제4항"
    assert r.effective_from == "2026-05-06"


def test_w2_cites_participant_based_text_of_2026_38():
    j = judge(meeting(attendees=[att("김철수"), att("이영희")], attendee_count=2), Context())
    r = next(r for r in j.reasons if r.rule_id == "M-25-4-EXT")
    assert "참여연구자만 참여하는 회의" in r.text
    assert "소속" not in r.text


def test_w2_same_institution_non_participant_counts_as_outsider():
    # 제2026-38호: 같은 기관이라도 과제 미참여자가 참석하면 식비 계상 가능
    j = judge(meeting(attendees=[att("김철수"), att("이영희"), att("최민호", participant=False)], attendee_count=3), Context())
    assert j.verdict == "가능"
    assert "M-25-4-EXT" not in rule_ids(j)


def test_w1_same_institution_non_participant_is_still_internal():
    # 제2023-49호 ④는 「기관에 소속되지 않은 자」 기준 — 과제 미참여자라도 같은 기관이면 내부
    j = judge(meeting(date="2025-03-10", has_internal_approval=True,
                      attendees=[att("김철수"), att("이영희"), att("최민호", participant=False)], attendee_count=3), Context())
    assert j.verdict == "불가"
    r = next(r for r in j.reasons if r.rule_id == "M-25-4-EXT")
    assert "소속되지 않은 자가 참여하는 회의 중 사전에 내부결재가 완료된 회의" in r.text
    assert r.effective_from == "2024-12-01" and r.effective_to == "2026-05-05"


def test_w2_unknown_participation_needs_supplement():
    j = judge(meeting(attendees=[att("김철수"), att("이영희", external=None, participant=None)], attendee_count=2), Context())
    assert j.verdict == "보완"
    assert "M-25-4-EXT" in rule_ids(j)


def test_basic_project_proviso_does_not_survive_2024_12_01():
    internal = [att("김철수"), att("이영희")]
    assert judge(meeting(date="2025-03-10", has_internal_approval=True, attendees=internal, attendee_count=2,
                         basic_project=True), Context()).verdict == "불가"
    assert judge(meeting(date="2026-06-12", attendees=internal, attendee_count=2, basic_project=True), Context()).verdict == "불가"


def test_internal_only_meal_before_2024_12_01_is_rejected_by_old_25_4_unless_basic_project():
    # 구 조문(2024-11-30까지)도 기관 내부자만의 회의 식비는 불가 — 단서는 정부출연기관 기본사업뿐
    internal = [att("김철수"), att("이영희")]
    j = judge(meeting(date="2024-10-15", attendees=internal, attendee_count=2), Context())
    assert j.verdict == "불가"
    r = next(r for r in j.reasons if r.rule_id == "M-25-4-EXT")
    assert "정부출연기관의 기본사업" in r.text and r.effective_to == "2024-11-30"
    j2 = judge(meeting(date="2024-10-15", attendees=internal, attendee_count=2, basic_project=True), Context())
    assert j2.verdict == "가능" and "M-25-4-EXT" not in rule_ids(j2)


def test_innovation_fund_allows_participant_only_meal_from_2026_06_11():
    internal = [att("김철수"), att("이영희")]
    j = judge(meeting(date="2026-06-12", attendees=internal, attendee_count=2, innovation_fund=True), Context())
    assert j.verdict == "가능"
    r = next(r for r in j.reasons if r.rule_id == "M-25-2-6")
    assert r.article == "제25조의2 제6항" and r.effective_from == "2026-06-11"
    # 시행 전(2026-05-06~06-10)엔 연구혁신비 단서가 없다
    assert judge(meeting(date="2026-05-20", attendees=internal, attendee_count=2, innovation_fund=True), Context()).verdict == "불가"


def test_w1_requires_prior_internal_approval_as_supplement():
    j = judge(meeting(date="2025-03-10", has_internal_approval=False), Context())
    assert j.verdict == "보완"
    assert "M-25-4-PRE" in rule_ids(j)


def test_w2_does_not_require_prior_approval():
    j = judge(meeting(date="2026-06-12", has_internal_approval=False), Context())
    assert "M-25-4-PRE" not in rule_ids(j)


def test_missing_minutes_over_100k_needs_supplement():
    j = judge(meeting(amount_total=150000, has_minutes=False, has_simplified_evidence=True), Context())
    assert j.verdict == "보완"
    assert "M-25-5-DOC" in rule_ids(j)


def test_missing_minutes_under_100k_with_simplified_evidence_is_allowed():
    j = judge(meeting(amount_total=80000, has_minutes=False, has_simplified_evidence=True), Context())
    assert j.verdict == "가능"


def test_missing_minutes_under_100k_without_any_evidence_needs_supplement():
    j = judge(meeting(amount_total=80000, has_minutes=False, has_simplified_evidence=False), Context())
    assert j.verdict == "보완"
    assert "M-25-5-DOC" in rule_ids(j)


def test_weekday_lunch_without_meeting_evidence_is_rejected_by_25_14_6():
    j = judge(meeting(attendees=[], attendee_count=None, purpose=None,
                      has_minutes=False, has_simplified_evidence=False), Context())
    assert j.verdict == "불가"
    assert "M-25-14-6" in rule_ids(j)


def test_alcohol_is_supplement_only_not_rejection():
    j = judge(meeting(has_alcohol=True), Context())
    assert j.verdict == "보완"
    assert "M-INST-ALC" in rule_ids(j)
    r = next(r for r in j.reasons if r.rule_id == "M-INST-ALC")
    assert r.source_kind == "기관 지침"


def test_per_person_over_cap_is_supplement():
    j = judge(meeting(amount_total=160000), Context())  # 4명 → 1인 40,000 > 30,000
    assert j.verdict == "보완"
    assert "M-INST-CAP" in rule_ids(j)


def test_weekend_meeting_is_supplement():
    j = judge(meeting(date="2026-06-13"), Context())  # 토요일
    assert j.verdict == "보완"
    assert "M-INST-WKD" in rule_ids(j)


def test_attendee_on_trip_same_day_is_duplicate_rejection():
    ctx = Context(attendees_on_trip={"김철수"})
    j = judge(meeting(), ctx)
    assert j.verdict == "불가"
    assert "M-DUP-TRIP" in rule_ids(j)


# --- 출장비 ---------------------------------------------------------------

def test_domestic_trip_with_evidence_is_allowed():
    assert judge(travel(), Context()).verdict == "가능"


def test_meal_provided_but_claimed_in_full_needs_deduction():
    j = judge(travel(trip=Trip(destination="부산", start="2026-06-20", end="2026-06-21", domestic=True,
                               meals_provided=True, plan_doc=True, report_doc=True,
                               meal_claimed_full=True, has_transport_evidence=True)), Context())
    assert j.verdict == "보완"
    assert "T-25-7-MEAL" in rule_ids(j)


def test_overseas_trip_without_plan_doc_needs_supplement():
    j = judge(travel(trip=Trip(destination="Boston", start="2026-06-20", end="2026-06-25", domestic=False,
                               meals_provided=False, plan_doc=False, report_doc=True,
                               meal_claimed_full=False, has_transport_evidence=True)), Context())
    assert j.verdict == "보완"
    assert "T-25-8-PLAN" in rule_ids(j)


# --- 공통 -----------------------------------------------------------------

def test_missing_date_is_supplement_for_reinput():
    j = judge(meeting(date=None), Context())
    assert j.verdict == "보완"
    assert "G-EXTRACT" in rule_ids(j)


def test_rejection_beats_supplement_in_aggregation():
    j = judge(meeting(attendees=[att("김철수"), att("이영희")], attendee_count=2, has_alcohol=True), Context())
    assert j.verdict == "불가"
    assert {"M-25-4-EXT", "M-INST-ALC"} <= rule_ids(j)


def test_exception_dictionary_turns_rejection_into_allowed_with_source():
    case = meeting(attendees=[att("김철수"), att("이영희")], attendee_count=2)
    key = exception_key("M-25-4-EXT", case)
    ctx = Context(exceptions={key: {"source_queue_id": 12}})
    j = judge(case, ctx)
    assert j.verdict == "가능"
    x = next(r for r in j.reasons if r.rule_id == "X-DICT")
    assert "12" in x.text


# --- 인용 키 (판정 화면이 조문 원문을 CITATIONS에서 꺼낸다) -------------------

def test_reason_carries_citation_key_for_statute_panel():
    j = judge(meeting(attendees=[att("김철수"), att("이영희")], attendee_count=2), Context())
    r = next(r for r in j.reasons if r.rule_id == "M-25-4-EXT")
    assert r.cite == "25-4-W2"
    ok = judge(meeting(), Context())
    assert next(r for r in ok.reasons if r.rule_id == "OK").cite == "25-5"
    pre = judge(meeting(date="2025-03-10", attendees=[att("김철수"), att("박민수", "KAIST", True)]), Context())
    assert next(r for r in pre.reasons if r.rule_id == "M-25-4-PRE").cite == "25-4-W1"
