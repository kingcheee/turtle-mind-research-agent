"""저장소 — 새 화면(건 목록 표·판정 상세)이 읽는 조회: 원문 보존, 목록 행, 같은 규칙 건, 건별 이력."""
import json
import sqlite3
from datetime import datetime

import pytest

from panjeong.rules.engine import judge
from panjeong.rules.models import Attendee, CaseInput, Trip
from panjeong.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "v.db")


def meeting(date="2026-06-12", people=(("김철수", False), ("이영희", False))):
    return CaseInput(category="회의비", date=date, time="12:40", amount_total=24000, vendor_type="식당",
                     attendees=[Attendee(n, "ETRI", False, p) for n, p in [(a, not o) for a, o in people]],
                     attendee_count=len(people), purpose="과제 내부 점검 회의", has_minutes=True)


DOCS = [{"kind": "영수증", "text": "한식당 미가 합계 24,000원", "file": "20260927-1-M01.png"},
        {"kind": "회의록", "text": "2026-06-12 과제 내부 점검 회의", "file": None}]


def save(store, case, docs=None, vendor="한식당 미가", now=None):
    cid = store.save_case(case, extracted={"vendor_name": vendor}, source_files=[], docs=docs, now=now)
    store.save_judgment(cid, judge(case, store.context_for(case)), now=now)
    return cid


def test_docs_are_kept_with_the_case(store):
    cid = save(store, meeting(), docs=DOCS)
    assert store.get_case(cid)["docs"] == DOCS


def test_old_database_without_docs_column_is_migrated(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE cases(id INTEGER PRIMARY KEY, created_at TEXT, category TEXT, basis_date TEXT, "
                "amount INTEGER, case_json TEXT, extracted_json TEXT, source_files TEXT)")
    con.execute("INSERT INTO cases(category, case_json) VALUES('회의비', ?)",
                (json.dumps({"category": "회의비", "date": "2026-06-12"}),))
    con.commit(); con.close()
    s = Store(p)
    assert s.get_case(1)["docs"] == []
    cid = save(s, meeting(), docs=DOCS)
    assert s.get_case(cid)["docs"] == DOCS


def test_list_case_rows_carries_verdict_rules_article_and_place(store):
    cid = save(store, meeting())
    ok = save(store, meeting(people=(("김철수", False), ("박민수", True))), vendor="카페 브루잉")
    trip = CaseInput(category="출장비", date="2026-06-20", amount_total=2810000, purpose="NeurIPS 워크숍 발표",
                     attendees=[Attendee("김철수")], attendee_count=1,
                     trip=Trip(destination="Boston, USA", start="2026-06-20", end="2026-06-25", domestic=False,
                               plan_doc=False, report_doc=True))
    tid = save(store, trip, vendor=None)
    rows = {r["id"]: r for r in store.list_case_rows()}
    assert [r["id"] for r in store.list_case_rows()] == [tid, ok, cid]   # 최근 순
    r = rows[cid]
    assert r["verdict"] == "불가" and r["rule_ids"] == ["M-25-4-EXT"] and r["articles"] == ["제25조 제4항"]
    assert r["notice_no"] == "제2026-38호" and r["place"] == "한식당 미가" and r["n"] == 2
    assert r["what"] == "과제 내부 점검 회의" and r["time"] == "12:40"
    assert rows[ok]["verdict"] == "가능" and rows[ok]["rule_ids"] == ["OK"]
    assert rows[tid]["place"] == "Boston, USA" and rows[tid]["rule_ids"] == ["T-25-8-PLAN"]


def test_cases_with_rule_finds_cases_whose_latest_judgment_cites_it(store):
    a = save(store, meeting())
    b = save(store, meeting(date="2026-06-15"))
    save(store, meeting(people=(("김철수", False), ("박민수", True))))
    ids = [r["id"] for r in store.cases_with_rule("M-25-4-EXT")]
    assert ids == [b, a]
    assert [r["id"] for r in store.cases_with_rule("M-25-4-EXT", cite="25-4-W1")] == []


def test_case_history_collects_case_judgment_and_queue_events_in_order(store):
    t = datetime(2026, 9, 27, 14, 0, 0)
    cid = save(store, meeting(), now=t)
    other = save(store, meeting(), now=t)
    store.update_case(cid, meeting(date="2025-03-10"), now=datetime(2026, 9, 27, 14, 5))
    store.save_judgment(cid, judge(meeting(date="2025-03-10")), now=datetime(2026, 9, 27, 14, 5, 1))
    qid = store.appeal(cid, "외부 자문위원 참석", now=datetime(2026, 9, 27, 14, 6))
    store.decide(qid, "불인정", note="명단 없음", now=datetime(2026, 9, 27, 14, 7))
    kinds = [e["kind"] for e in store.case_history(cid)]
    assert kinds == ["case.saved", "judgment.saved", "case.edited", "judgment.saved", "queue.appeal", "queue.decided"]
    assert all(e["kind"] != "case.saved" or e["ref_id"] == cid for e in store.case_history(cid))
    assert [e["kind"] for e in store.case_history(other)] == ["case.saved", "judgment.saved"]
