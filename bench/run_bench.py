"""실측 벤치 — 정답지 케이스를 llama-server로 추출해 문서당 초·tok/s·필드 정확도를 잰다.

사용: .venv/bin/python bench/run_bench.py --host 노트북 [--cases data/answer_key.json] [--n 10] [--url http://127.0.0.1:8097]
결과: bench/results/<host>-<YYYYMMDD-HHMM>.json — /bench 화면이 표로 보여준다. Colab은 bench/colab.ipynb에서 같은 함수를 부른다.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.score import score_fields  # noqa: E402
from panjeong.extract.client import LlamaClient  # noqa: E402
from panjeong.extract.prompt import GRAMMAR_PATH, build_prompt, derive_external, refine_with_text  # noqa: E402
from panjeong.rules.models import Attendee  # noqa: E402


def refine_prediction(data: dict, text: str, institution: str | None = None) -> dict:
    """모델 원출력에 실제 파이프라인의 코드 보정(텍스트 확정·소속 기반 외부 여부)을 적용한 예측.
    벤치는 「모델 단독」과 「코드 보정 후」를 따로 잰다 — 판정에 들어가는 값은 후자다."""
    out = refine_with_text(dict(data), text)
    atts = [Attendee(name=str(a.get("name", "")).strip(), affiliation=a.get("affiliation"), external=a.get("external"))
            for a in (out.get("attendees") or []) if a and a.get("name")]
    atts = derive_external(atts, institution)
    out["attendees"] = [{"name": a.name, "affiliation": a.affiliation, "external": a.external} for a in atts]
    return out


def _institution() -> str | None:
    p = ROOT / "data" / "project.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get("기관명")
    return None


def run(cases, url: str, host: str, n: int | None = None, model: str = "", institution: str | None = None) -> dict:
    client = LlamaClient(url)
    if not client.health():
        raise SystemExit(f"llama-server가 응답하지 않음: {url}")
    grammar = GRAMMAR_PATH.read_text(encoding="utf-8")
    institution = institution or _institution()
    rows, secs, tg, pp = [], [], [], []
    correct = total = correct_raw = 0
    for c in cases[: n or len(cases)]:
        text = "\n".join(d["text"] for d in c["docs"])
        data, meta = client.extract(build_prompt([(d["kind"], d["text"]) for d in c["docs"]]), grammar)
        s_raw = score_fields(data, c["gold"])
        s = score_fields(refine_prediction(data, text, institution), c["gold"])
        correct += s["correct"]; correct_raw += s_raw["correct"]; total += s["total"]
        secs.append(meta["seconds"]); tg.append(meta.get("tg_per_s") or 0); pp.append(meta.get("pp_per_s") or 0)
        rows.append({"id": c["id"], "seconds": meta["seconds"], "score": s, "score_raw": s_raw})
        model = model or (meta.get("model") or "")
        print(f"{c['id']}: {meta['seconds']:.1f}s  모델 {s_raw['correct']}/{s_raw['total']} → 보정 후 {s['correct']}/{s['total']}  wrong={s['wrong']}")
    out = {"host": host, "platform": platform.platform(), "model": Path(model).name if model else "?", "n": len(rows),
           "sec_per_doc": sum(secs) / len(secs), "tg_per_s": sum(tg) / len(tg), "pp_per_s": sum(pp) / len(pp),
           "field_acc_raw": f"{correct_raw}/{total} ({100 * correct_raw / max(total, 1):.0f}%)",
           "field_acc": f"{correct}/{total} ({100 * correct / max(total, 1):.0f}%)", "date": datetime.now().isoformat(timespec="minutes"),
           "rows": rows}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="환경 이름 (노트북·N100·NCP-L40S·Colab-T4 …)")
    ap.add_argument("--cases", default=str(ROOT / "data" / "answer_key.json"))
    ap.add_argument("--url", default="http://127.0.0.1:8097")
    ap.add_argument("--n", type=int, default=None)
    a = ap.parse_args()
    cases = json.loads(Path(a.cases).read_text(encoding="utf-8"))
    out = run(cases, a.url, a.host, a.n)
    dst = ROOT / "bench" / "results" / f"{a.host}-{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    dst.parent.mkdir(parents=True, exist_ok=True)  # 번들로 옮긴 환경(Colab 등)엔 results/가 없다 — 09-27 20건 측정 끝에 저장만 실패
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {dst}  문서당 {out['sec_per_doc']:.1f}s  생성 {out['tg_per_s']:.1f} tok/s  정확도 모델 단독 {out['field_acc_raw']} / 코드 보정 후 {out['field_acc']}")


if __name__ == "__main__":
    main()
