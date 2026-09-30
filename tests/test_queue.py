"""저장소 — 케이스·판정·심판 큐·예외 사전·이벤트. SQLite 임시 파일로 실제 코드 경로를 탄다."""
from datetime import datetime, timedelta
import pytest
from panjeong.store import Store
from panjeong.rules.models import Attendee, CaseInput, Trip
from panjeong.rules.engine import judge, exception_key


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db", deadline_minutes=7 * 24 * 60)


def internal_meeting():
    return CaseInput(category="회의비", date="2026-06-12", time="12:40", amount_total=52800, vat_included=True,
                     vendor_type="식당", has_alcohol=False,
                     attendees=[Attendee("김철수", "ETRI", False), Attendee("이영희", "ETRI", False)],
                     attendee_count=2, purpose="내부 점검", has_minutes=True)


def test_save_case_and_judgment_are_listed(store):
    case = internal_meeting()
    cid = store.save_case(case, extracted={"x": 1}, source_files=["a.png"])
    j = judge(case, store.context_for(case))
    jid = store.save_judgment(cid, j)
    rows = store.list_cases()
    assert rows[0]["id"] == cid and rows[0]["verdict"] == "불가"
    assert store.get_judgment(jid)["reasons"][0]["rule_id"] == "M-25-4-EXT"


def test_provisional_approval_enqueues_with_deadline(store):
    cid = store.save_case(internal_meeting(), extracted={}, source_files=[])
    now = datetime(2026, 6, 12, 13, 0)
    qid = store.provisional_approve(cid, now=now)
    q = store.get_queue_item(qid)
    assert q["kind"] == "임시승인" and q["status"] == "대기"
    assert q["deadline_at"] == (now + timedelta(days=7)).isoformat(timespec="seconds")


def test_decision_accept_registers_exception_used_by_next_judgment(store):
    case = internal_meeting()
    cid = store.save_case(case, extracted={}, source_files=[])
    qid = store.provisional_approve(cid, now=datetime(2026, 6, 12, 13, 0))
    store.decide(qid, "인정", note="기본사업 성격 인정", register_exception=True, rule_id="M-25-4-EXT",
                 exception_key=exception_key("M-25-4-EXT", case), decided_by="행정팀")
    ctx = store.context_for(case)
    assert exception_key("M-25-4-EXT", case) in ctx.exceptions
    j = judge(case, ctx)
    assert j.verdict == "가능" and any(r.rule_id == "X-DICT" for r in j.reasons)


def test_overdue_items_are_flagged_on_refresh(store):
    cid = store.save_case(internal_meeting(), extracted={}, source_files=[])
    qid = store.provisional_approve(cid, now=datetime(2026, 6, 1, 9, 0))
    store.refresh_overdue(now=datetime(2026, 6, 9, 9, 0))
    assert store.get_queue_item(qid)["status"] == "기한초과"
    assert store.list_queue()[0]["id"] == qid  # 기한초과가 맨 위


def test_appeal_creates_appeal_queue_item(store):
    cid = store.save_case(internal_meeting(), extracted={}, source_files=[])
    qid = store.appeal(cid, statement="외부 자문위원이 실제로 참석했음", now=datetime(2026, 6, 12, 14, 0))
    assert store.get_queue_item(qid)["kind"] == "이의"


def test_every_mutation_appends_an_event(store):
    cid = store.save_case(internal_meeting(), extracted={}, source_files=[])
    store.provisional_approve(cid, now=datetime(2026, 6, 12, 13, 0))
    kinds = [e["kind"] for e in store.list_events()]
    assert kinds == ["case.saved", "queue.provisional"]


def test_attendees_on_trip_for_date_come_from_saved_travel_cases(store):
    trip_case = CaseInput(category="출장비", date="2026-06-20", amount_total=180000, attendees=[Attendee("김철수")],
                          trip=Trip(destination="부산", start="2026-06-20", end="2026-06-21", domestic=True))
    store.save_case(trip_case, extracted={}, source_files=[])
    meet = CaseInput(category="회의비", date="2026-06-21", attendees=[Attendee("김철수", "ETRI", False), Attendee("박민수", "KAIST", True)],
                     amount_total=50000, has_minutes=True)
    assert store.context_for(meet).attendees_on_trip == {"김철수"}
    assert store.context_for(CaseInput(category="회의비", date="2026-06-22", amount_total=1)).attendees_on_trip == set()
