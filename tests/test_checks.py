"""요건 대조(판정 화면의 요건 ↔ 사실 표) — 각 줄의 결과는 엔진이 건 규칙 ID에서만 나온다.

시연 6건은 README 「시연 순서」·index 시연 버튼과 같은 사실관계다(참여연구자 명단 = 김철수·이영희·정수진)."""
from panjeong.rules.checks import requirement_rows
from panjeong.rules.engine import judge
from panjeong.rules.models import Attendee, CaseInput, Context, Trip

ROSTER = {"김철수", "이영희", "정수진"}


def att(name, aff="한국전자통신연구원"):
    ext = aff != "한국전자통신연구원"
    return Attendee(name=name, affiliation=aff, external=ext, participant=name in ROSTER)


def meeting(**over):
    base = dict(category="회의비", date="2026-06-12", time="12:40", amount_total=52800, vat_included=True,
                vendor_type="식당", has_alcohol=False, attendee_count=None, purpose="과제 중간점검 회의",
                attendees=[att("김철수"), att("이영희"), att("박민수", "KAIST"), att("정수진")],
                has_minutes=True)
    base.update(over)
    if base["attendee_count"] is None:
        base["attendee_count"] = len(base["attendees"])
    return CaseInput(**base)


DEMO = {
    1: meeting(),
    2: meeting(date="2026-06-15", time="15:10", amount_total=80000, vendor_type="카페", has_minutes=False,
               attendees=[att("김철수"), att("이영희"), att("정수진"), att("최민호"), att("박민수", "KAIST"), att("한지원", "KAIST")]),
    3: meeting(date="2026-06-13", time="12:20", amount_total=33000,
               attendees=[att("김철수"), att("박민수", "KAIST"), att("이영희")]),
    4: meeting(amount_total=24000, attendees=[att("김철수"), att("이영희")]),
    5: CaseInput(category="출장비", date="2026-06-20", amount_total=2810000, vendor_type="교통",
                 attendees=[att("김철수")], attendee_count=1, purpose="NeurIPS 워크숍 발표",
                 trip=Trip(destination="Boston, USA", start="2026-06-20", end="2026-06-25", domestic=False,
                           meals_provided=True, plan_doc=False, report_doc=True)),
    6: meeting(amount_total=36000, attendees=[att("김철수"), att("이영희"), att("최민호")]),
}


def rows_for(case, ctx=None):
    return requirement_rows(case, judge(case, ctx or Context(today="2026-09-27")))


def mark(rows, needle):
    hit = [r for r in rows if needle in r.req]
    assert hit, f"{needle!r} 줄 없음: {[r.req for r in rows]}"
    return hit[0].mark


def test_first_row_is_the_notice_window_of_the_basis_date():
    r = rows_for(DEMO[1])[0]
    assert r.mark == "+" and "적용 고시" in r.req and "2026-06-12" in r.fact and "제2026-38호" in r.fact


def test_demo1_all_requirements_met():
    rows = rows_for(DEMO[1])
    assert {r.mark for r in rows} == {"+"}
    assert mark(rows, "제4항") == "+" and mark(rows, "제5항") == "+"
    assert any("1인당 13,200원" in r.fact for r in rows)


def test_demo2_missing_minutes_is_supplement_on_25_5():
    rows = rows_for(DEMO[2])
    assert mark(rows, "제5항") == "?"
    assert mark(rows, "제4항") == "+"


def test_demo3_weekend_row_is_supplement():
    rows = rows_for(DEMO[3])
    assert mark(rows, "주말") == "?"
    assert any("토요일" in r.fact for r in rows)


def test_demo4_participant_only_meeting_violates_25_4():
    rows = rows_for(DEMO[4])
    assert mark(rows, "제4항") == "−"
    r = next(r for r in rows if "제4항" in r.req)
    assert "전원 과제 참여연구자" in r.fact and r.result == "위반"


def test_demo5_overseas_trip_without_plan_is_supplement():
    rows = rows_for(DEMO[5])
    assert mark(rows, "출장계획서") == "?"
    assert mark(rows, "출장결과보고서") == "+"


def test_demo6_non_participant_named_in_fact():
    rows = rows_for(DEMO[6])
    assert mark(rows, "제4항") == "+"
    assert "최민호" in next(r for r in rows if "제4항" in r.req).fact


def test_w1_rows_use_institution_wording_and_prior_approval():
    rows = rows_for(meeting(date="2025-03-10", amount_total=24000, attendees=[att("김철수"), att("이영희")]))
    assert "제2023-49호" in rows[0].fact
    r4 = next(r for r in rows if "소속되지 않은 자" in r.req)
    assert r4.mark == "−" and "전원 기관 소속" in r4.fact
    assert mark(rows, "사전") == "?"


def test_w0_basic_project_proviso_row_is_met():
    rows = rows_for(meeting(date="2024-10-15", amount_total=24000, attendees=[att("김철수"), att("이영희")],
                            basic_project=True))
    assert mark(rows, "기본사업") == "+"
    assert "−" not in {r.mark for r in rows}


def test_exception_dictionary_turns_the_row_into_met_with_source():
    case = DEMO[3]
    from panjeong.rules.engine import exception_key
    ctx = Context(exceptions={exception_key("M-INST-WKD", case): {"source_queue_id": 7}})
    rows = rows_for(case, ctx)
    r = next(r for r in rows if "주말" in r.req)
    assert r.mark == "+" and "예외 사전" in r.fact and "#7" in r.fact


def test_missing_date_is_a_required_value_row_only():
    rows = rows_for(meeting(date=None))
    assert [r.mark for r in rows] == ["?"] and "집행일" in rows[0].fact


def test_lunch_without_meeting_evidence_shows_only_14_6_row():
    rows = rows_for(meeting(attendees=[], attendee_count=None, purpose=None, has_minutes=False))
    assert [r.mark for r in rows] == ["+", "−"] and "제14항" in rows[1].req


def test_rows_accept_stored_judgment_dicts():
    from dataclasses import asdict
    case = DEMO[4]
    j = asdict(judge(case, Context()))
    rows = requirement_rows(case, j)
    assert mark(rows, "제4항") == "−"
