"""OCR 경로 스모크 — data/images/*.png를 Tesseract로 읽어 정답 금액·날짜가 텍스트에 있는지, refine_with_text가 합계를 잡는지 센다.
사용: .venv/bin/python tools/ocr_smoke.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panjeong.extract.ocr import image_to_text  # noqa: E402
from panjeong.extract.prompt import refine_with_text  # noqa: E402


def main() -> int:
    key = json.loads((ROOT / "data" / "answer_key.json").read_text(encoding="utf-8"))
    n = ok_amt = ok_date = ok_total = 0
    for c in key:
        p = ROOT / "data" / "images" / f"{c['id']}.png"
        if not c.get("image") or not p.exists():
            continue
        n += 1
        t = image_to_text(p)
        amt = c["gold"]["amount_total"]
        a = f"{amt:,}" in t.replace(" ", "")
        d = c["gold"]["date"] in t
        r = refine_with_text({"category": "회의비"}, t).get("amount_total") == amt
        ok_amt += a; ok_date += d; ok_total += r
        mark = "" if (a and d and r) else "   <- " + t.replace("\n", " | ")[:160]
        print(f"{c['id']}: 금액문자열 {'O' if a else 'X'} 날짜 {'O' if d else 'X'} 합계추출 {'O' if r else 'X'}{mark}")
    print(f"{n}장: 금액 {ok_amt}/{n} · 날짜 {ok_date}/{n} · 합계 추출 {ok_total}/{n}")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
