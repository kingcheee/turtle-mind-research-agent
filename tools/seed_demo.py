"""시연 시드(선택) — `data/answer_key.json` 정답지 60건을 모델 없이 판정해 저장소에 넣는다.

목록·보고서·「같은 조문을 인용한 건」이 비어 보이지 않게 하려는 것. 판정은 규칙엔진(`judge`)이 정답 필드로 한다 —
정답지의 `expected`와 같은 결과(tests/test_gen.py가 검산). 시연 리허설은 빈 DB에서 하므로 이 시드는 선택이다.

    .venv/bin/python -m tools.seed_demo            # data/panjeong.db에 60건 추가
    .venv/bin/python -m tools.seed_demo --db 경로   # 다른 DB
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable

from data import gen
from panjeong.rules.engine import judge
from panjeong.store import Store

ROOT = Path(__file__).resolve().parent.parent


def seed(store: Store, cases: Iterable[Dict[str, Any]]) -> int:
    n = 0
    for c in cases:
        case = gen.case_input_from(c)
        extracted = dict(c["gold"])
        docs = [{"kind": d["kind"], "text": d["text"], "file": None} for d in c["docs"]]
        cid = store.save_case(case, extracted=extracted, source_files=[], docs=docs)
        store.save_judgment(cid, judge(case, gen.context_from(c)))
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "panjeong.db"))
    ap.add_argument("--key", default=str(ROOT / "data" / "answer_key.json"))
    a = ap.parse_args()
    cases = json.loads(Path(a.key).read_text(encoding="utf-8"))
    print(f"{seed(Store(a.db), cases)}건 저장 → {a.db}")


if __name__ == "__main__":
    main()
