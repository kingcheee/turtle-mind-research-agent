"""공개 시연용 목데이터 — Gemini 합성 영수증 사진이 있는 건만(`data/photos/cases.json`의 photo 항목 10건). 모델 없이 정답지 필드로 판정.

10-01 사용자: 공개 사이트(Funnel)에는 「16건 말고 제미나이 사진만 10장」. 심판 큐·예외 사전·재판정 이력은 만들지 않는다
(행정팀 칸을 숨긴 공개본이라 큐가 있어도 갈 데가 없다). 영수증 거래일 순으로 지난 2주에 걸쳐 쌓는다.

    .venv/bin/python -m tools.seed_gemini            # data/panjeong.db에 10건 추가 (서버가 떠 있어도 된다)
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from data import gen
from panjeong.rules.engine import judge
from panjeong.store import Store

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "data" / "photos"


def photo_cases(photos: Path = PHOTOS) -> list[Dict[str, Any]]:
    cases = json.loads((photos / "cases.json").read_text(encoding="utf-8"))
    return sorted((c for c in cases if c.get("photo")), key=lambda c: (c["gold"]["date"], c["gold"].get("time") or ""))


def seed_gemini(store: Store, uploads: Path, now: Optional[datetime] = None, photos: Path = PHOTOS) -> int:
    now = now or datetime.now()
    uploads = Path(uploads); uploads.mkdir(parents=True, exist_ok=True)
    cases = photo_cases(photos)
    for n, c in enumerate(cases):
        t = now - timedelta(days=len(cases) - 1 - n, hours=len(cases) - n)  # 거래일 순 · 하루 한 건
        f = f"mock-{c['id']}{Path(c['photo']).suffix}"
        shutil.copyfile(photos / c["photo"], uploads / f)
        docs = [{"kind": d["kind"], "text": d["text"], "file": f if d["kind"] == "영수증" else None} for d in c["docs"]]
        case = gen.case_input_from(c)
        j = judge(case, gen.context_from(c))
        if j.verdict != c["intended"]:
            raise AssertionError(f"{c['id']}: 의도 {c['intended']} ≠ 엔진 {j.verdict} {[r.rule_id for r in j.reasons]}")
        cid = store.save_case(case, extracted=dict(c["gold"]), source_files=[f], docs=docs, now=t)
        store.save_judgment(cid, j, now=t + timedelta(minutes=1))
    return len(cases)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "panjeong.db"))
    a = ap.parse_args()
    n = seed_gemini(Store(a.db), uploads=ROOT / "data" / "uploads")
    print(f"{n}건 저장 → {a.db}")


if __name__ == "__main__":
    main()
