"""UI 검토용 목데이터 16건 — 모델 없이. 판정 3종·회의/출장·사진 영수증·심판 큐 상태·예외 사전·재판정 이력이 다 보이게."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from panjeong.store import Store
from tools.seed_mock import seed_mock

ROOT = Path(__file__).parent.parent
KEY = ROOT / "data" / "answer_key.json"


@pytest.fixture
def seeded(tmp_path):
    store = Store(tmp_path / "p.db")
    n = seed_mock(store, json.loads(KEY.read_text(encoding="utf-8")), uploads=tmp_path / "up",
                  images=ROOT / "data" / "images", now=datetime(2026, 9, 28, 10, 0))
    return store, n, tmp_path / "up"


def test_sixteen_cases_with_every_verdict_and_both_categories(seeded):
    store, n, _ = seeded
    rows = store.list_case_rows()
    assert n == len(rows) == 16
    assert {r["verdict"] for r in rows} == {"가능", "보완", "불가"}
    assert {r["category"] for r in rows} == {"회의비", "출장비"}


def test_queue_shows_waiting_overdue_and_both_decisions(seeded):
    store, _, _ = seeded
    q = store.list_queue(include_closed=True)
    assert {"대기", "기한초과", "인정", "불인정"} <= {x["status"] for x in q}
    assert {"임시승인", "이의"} <= {x["kind"] for x in q}
    assert len(store.list_exceptions()) == 1


def test_exception_dictionary_and_rejudge_history_are_visible(seeded):
    store, _, _ = seeded
    rows = store.list_case_rows()
    assert any("X-DICT" in r["rule_ids"] for r in rows)
    judged_twice = [r for r in rows if sum(e["kind"] == "judgment.saved" for e in store.case_history(r["id"])) >= 2]
    assert judged_twice


GEMINI = {  # 사진에 실제로 찍힌 상호·합계·거래일 → 목데이터에서의 마지막 판정 (09-28 Gemini 합성 영수증 5장)
    "R1": ("한식당 미가", 52800, "2026-06-12", "가능"),
    "R2": ("카페 브루잉", 80000, "2026-06-15", "가능"),    # 회의록 없음 보완 → 회의록 받아 재판정
    "R3": ("국밥집 온기", 33000, "2026-06-13", "보완"),    # 주말 → 임시 승인 → 인정 + 예외 사전
    "R4": ("한식당 미가", 24000, "2026-06-12", "불가"),    # 참여연구자만 → 이의 신청
    "R6": ("한식당 미가", 36000, "2026-06-12", "가능"),    # 같은 기관 과제 미참여자
}


def test_gemini_receipt_photos_are_the_receipts_of_matching_cases(seeded):
    """09-29 사용자: 「내가 제미나이로 생성한 영수증 사진을 미리보기·판정 화면에 넣어 줘」 — 아무 건에나 붙이지 않고
    사진 속 내용과 같은 건(시연 1·2·3·4·6)을 만들어 그 건의 영수증으로 넣는다."""
    store, _, up = seeded
    got = {}
    for r in store.list_case_rows():
        row = store.get_case(r["id"])
        receipts = [d for d in row["docs"] if d["kind"] == "영수증"]
        for key in GEMINI:
            if receipts and receipts[0].get("file") == f"mock-{key}.jpg":
                c = row["case"]
                got[key] = (row["extracted"].get("vendor_name"), c.amount_total, c.date, r["verdict"])
                assert (up / f"mock-{key}.jpg").stat().st_size > 100_000     # 렌더 그림이 아니라 사진
    assert got == GEMINI


def test_photo_receipts_are_copied_and_linked_to_docs(seeded):
    store, _, up = seeded
    files = [d["file"] for r in store.list_case_rows() for d in store.get_case(r["id"])["docs"] if d.get("file")]
    assert len(files) >= 8
    assert all((up / f).exists() for f in files)
