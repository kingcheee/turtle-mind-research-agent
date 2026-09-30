"""공개 시연 목데이터 — Gemini 영수증 사진 10장, 각 사진 속 내용 그대로의 건. 심판 큐는 비어 있다."""
from datetime import datetime
from pathlib import Path

from panjeong.store import Store
from tools.seed_gemini import seed_gemini

ROOT = Path(__file__).parent.parent


def test_ten_gemini_photo_cases_every_verdict_no_queue(tmp_path):
    store = Store(tmp_path / "p.db")
    n = seed_gemini(store, uploads=tmp_path / "up", now=datetime(2026, 10, 1, 9, 0))
    rows = store.list_case_rows()
    assert n == len(rows) == 10
    assert {r["verdict"] for r in rows} == {"가능", "보완", "불가"}
    assert store.list_queue(include_closed=True) == [] and store.list_exceptions() == []
    for r in rows:
        docs = store.get_case(r["id"])["docs"]
        receipt = [d for d in docs if d["kind"] == "영수증"]
        assert receipt and receipt[0]["file"] and (tmp_path / "up" / receipt[0]["file"]).stat().st_size > 100_000  # 사진
    dates = [store.get_case(r["id"])["case"].date for r in rows]
    assert dates == sorted(dates, reverse=True) or dates == sorted(dates)  # 거래일 순으로 쌓임
