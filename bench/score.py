"""추출 정확도 채점 — 정답지의 스칼라 필드 + 참석자 목록(이름·외부 여부)을 필드 단위로 센다."""
from __future__ import annotations

from typing import Any, Dict, List

SCALARS = ("category", "amount_total", "date", "vendor_type", "has_alcohol", "attendee_count")


def _norm(v: Any) -> Any:
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def score_fields(pred: Dict[str, Any], gold: Dict[str, Any]) -> Dict[str, Any]:
    wrong: List[str] = []
    total = 0
    for k in SCALARS:
        if k not in gold:
            continue
        total += 1
        if _norm((pred or {}).get(k)) != _norm(gold[k]):
            wrong.append(k)
    if "attendees" in gold:
        total += 1
        g = {(_norm(a.get("name")), a.get("external")) for a in gold["attendees"]}
        p = {(_norm(a.get("name")), a.get("external")) for a in (pred or {}).get("attendees") or []}
        if g != p:
            wrong.append("attendees")
    return {"total": total, "correct": total - len(wrong), "wrong": wrong}
