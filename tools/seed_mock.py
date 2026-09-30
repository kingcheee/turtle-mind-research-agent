"""UI 검토용 목데이터 16건 — 모델 없이 정답지 필드로 판정해 넣는다(사진 영수증·원문 포함).

화면의 모든 상태가 보이게 고른 16건을 지난 2주에 걸친 시각으로 쌓는다:
판정 가능·보완·불가 / 회의비(사진 영수증 10장)·출장비(국내·국외) / 심판 큐 대기·기한 초과·인정(+예외 사전)·불인정 /
예외 사전으로 「가능」이 된 건(X-DICT) / 수정 후 재판정 이력 / 이의 신청.
09-29 사용자 요청: 사진 영수증 중 5장은 사용자가 Gemini로 만든 실제 같은 사진(`data/photos/R*.jpg`)이다. 그 사진 내용
그대로의 건(시연 1·2·3·4·6, `data/photos/cases.json`)이 비슷한 역할의 정답지 건 자리에 들어간다. 나머지는 렌더한 PNG.
시연 리허설은 빈 DB로 한다 — 이건 화면을 살펴보고 고치려는 용도다.

    .venv/bin/python -m tools.seed_mock            # data/panjeong.db에 16건 추가 (서버가 떠 있어도 된다)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from data import gen
from panjeong.rules.engine import exception_key, judge
from panjeong.store import Store

ROOT = Path(__file__).resolve().parent.parent

# (정답지 id, 며칠 전, 시각, 그 뒤 일) — 시간 순
PLAN = [
    ("R1", 13, "10:12", None),                # 가능 · 외부 참석 (Gemini 사진, 옛 M01 자리)
    ("M03", 12, "14:30", None),               # 보완 · 10만 원 초과인데 회의록 없음
    ("R2", 12, "16:05", "rejudge"),           # 보완 → 다음 날 회의록 받아 수정 → 가능 (재판정 이력, Gemini 사진, 옛 M04)
    ("R4", 11, "09:40", "appeal"),            # 불가 · 과제 참여연구자만 → 이의 신청 대기 (Gemini 사진, 옛 M05)
    ("R6", 10, "11:20", None),                # 가능 · 같은 기관 과제 미참여자 (Gemini 사진, 옛 M06)
    ("M07", 9, "13:15", None),                # 가능 · 연구혁신비(제25조의2)
    ("R3", 9, "15:50", "approve_accept"),     # 보완 · 주말 → 임시 승인 → 인정 + 예외 사전 (Gemini 사진, 옛 M09)
    ("M12", 9, "17:30", "approve"),           # 보완 · 사전결재 없음 → 임시 승인 → 기한 초과
    ("T03", 8, "10:00", None),                # 보완 · 출장 중 식사 제공인데 전액 청구
    ("T06", 7, "11:45", "approve_reject"),    # 보완 · 교통 증빙 없음 → 임시 승인 → 불인정
    ("M17", 5, "09:30", None),                # 주말이지만 예외 사전 일치 → 가능(X-DICT)
    ("T16", 4, "14:10", "approve"),           # 보완 · 국외 출장 계획서 없음 → 임시 승인 대기
    ("M19", 3, "12:50", "approve"),           # 보완 · 주류 → 임시 승인 대기
    ("M22", 2, "18:20", None),                # 불가 · 참석자가 그날 출장 중 + 주말
    ("M23", 1, "12:35", None),                # 불가 · 근거 없는 평일 점심
    ("T18", 0, "09:15", None),                # 가능 · 국외 출장
]


PHOTOS = ROOT / "data" / "photos"


def seed_mock(store: Store, cases: Iterable[Dict[str, Any]], uploads: Path, images: Path,
              now: Optional[datetime] = None, photos: Path = PHOTOS) -> int:
    now = now or datetime.now()
    photos = Path(photos)
    by_id = {c["id"]: c for c in cases}
    by_id.update({c["id"]: c for c in json.loads((photos / "cases.json").read_text(encoding="utf-8"))})
    uploads = Path(uploads)
    uploads.mkdir(parents=True, exist_ok=True)
    tick = lambda t, m: t + timedelta(minutes=m)
    appeals = []

    def run(case, c, t):
        ctx = dataclasses.replace(gen.context_from(c), exceptions=store.context_for(case).exceptions)
        return store.save_judgment(cid, judge(case, ctx), now=t)

    for n, (key, days, hm, then) in enumerate(PLAN):
        c = by_id[key]
        h, m = map(int, hm.split(":"))
        t = (now - timedelta(days=days)).replace(hour=h, minute=m, second=0, microsecond=0)
        if t > now:
            t = now - timedelta(minutes=len(PLAN) - n)
        docs = []
        for d in c["docs"]:
            f = None
            img = photos / c["photo"] if c.get("photo") else images / f"{key}.png"
            if c.get("image") and d["kind"] == "영수증" and img.exists():
                f = f"mock-{key}{img.suffix}"
                shutil.copyfile(img, uploads / f)
            docs.append({"kind": d["kind"], "text": d["text"], "file": f})
        case = gen.case_input_from(c)
        cid = store.save_case(case, extracted=dict(c["gold"]), source_files=[d["file"] for d in docs if d["file"]],
                              docs=docs, now=t)
        run(case, c, tick(t, 1))
        if then == "rejudge":
            case = dataclasses.replace(case, has_minutes=True)
            store.update_case(cid, case, now=tick(t, 60 * 20))
            run(case, c, tick(t, 60 * 20 + 1))
        elif then == "appeal":
            appeals.append(cid)  # 어제 들어온 이의 — 심판 번호가 시간 순이 되게 맨 뒤에
        elif then and then.startswith("approve"):
            qid = store.provisional_approve(cid, now=tick(t, 3))
            if then == "approve_accept":
                store.decide(qid, "인정", note="워크숍 정리 회의로 과제 관련성 확인", register_exception=True,
                             rule_id="M-INST-WKD", exception_key=exception_key("M-INST-WKD", case), now=tick(t, 60 * 22))
            elif then == "approve_reject":
                store.decide(qid, "불인정", note="교통비 증빙 미제출 — 증빙 받은 뒤 재판정", now=tick(t, 60 * 44))
    for cid in appeals:
        store.appeal(cid, "외부 자문위원(KAIST 박민수)이 실제로 참석 — 회의록 서명 명단 첨부", now=now - timedelta(days=1, hours=2))
    store.refresh_overdue(now=now)
    return len(PLAN)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "panjeong.db"))
    a = ap.parse_args()
    cases = json.loads((ROOT / "data" / "answer_key.json").read_text(encoding="utf-8"))
    n = seed_mock(Store(a.db), cases, uploads=ROOT / "data" / "uploads", images=ROOT / "data" / "images")
    print(f"{n}건 저장 → {a.db}")


if __name__ == "__main__":
    main()
