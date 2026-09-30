"""시연 시드(선택) — 정답지 60건을 모델 없이 규칙엔진으로 판정해 저장소에 넣는다. 목록이 비어 보이지 않게."""
import json
from pathlib import Path

from panjeong.store import Store
from tools.seed_demo import seed

KEY = Path(__file__).parent.parent / "data" / "answer_key.json"


def _cases():
    return json.loads(KEY.read_text(encoding="utf-8"))


def test_seed_stores_every_answer_key_case_with_its_expected_verdict(tmp_path):
    cases = _cases()
    store = Store(tmp_path / "p.db")
    assert seed(store, cases) == len(cases) == 60
    rows = store.list_case_rows()
    assert len(rows) == 60
    assert sorted(r["verdict"] for r in rows) == sorted(c["expected"]["verdict"] for c in cases)


def test_seeded_case_keeps_original_docs_and_vendor_for_the_review_screen(tmp_path):
    c = _cases()[0]
    store = Store(tmp_path / "p.db")
    seed(store, [c])
    got = store.get_case(store.list_case_rows()[0]["id"])
    assert [(d["kind"], d["text"]) for d in got["docs"]] == [(d["kind"], d["text"]) for d in c["docs"]]
    assert got["extracted"]["vendor_name"] == c["gold"]["vendor_name"]
