"""정답지 생성기 — 케이스는 규칙 경계를 밟고, 기대 판정은 엔진으로 검산돼야 한다."""
import json
from pathlib import Path

import pytest

from data import gen
from panjeong.extract.prompt import refine_with_text, to_case_input
from panjeong.rules.engine import judge
from panjeong.rules.models import Context

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TAGS = {
    "간이증빙-10만원이하", "10만원초과-회의록없음", "외부없음-W2", "외부있음", "주말", "사전결재없음-W1",
    "개정전날-2024-11-30", "개정일-2024-12-01", "W1마지막날-2026-05-05", "W2첫날-2026-05-06",
    "식사제공-전액청구", "국외-계획서없음", "국외-결과보고서없음", "주류", "1인한도초과", "출장일중복",
    "기본사업-W0", "기본사업-W1불인정", "동일기관-미참여자-W2", "연구혁신비-W2",
}


@pytest.fixture(scope="module")
def cases():
    return gen.build_cases(seed=7)


def test_generates_60_cases_half_meeting_half_travel(cases):
    assert len(cases) == 60
    assert sum(c["gold"]["category"] == "회의비" for c in cases) == 30
    assert sum(c["gold"]["category"] == "출장비" for c in cases) == 30
    assert len({c["id"] for c in cases}) == 60


def test_case_schema(cases):
    for c in cases:
        assert {"id", "docs", "gold", "expected", "flags", "tags"} <= set(c)
        assert c["docs"] and all({"kind", "text"} <= set(d) for d in c["docs"])
        assert {"category", "amount_total", "date"} <= set(c["gold"])
        assert {"verdict", "rule_ids"} <= set(c["expected"])
        assert c["expected"]["verdict"] in ("가능", "보완", "불가")


def test_expected_verdict_is_what_the_engine_says_on_gold(cases):
    for c in cases:
        case = gen.case_input_from(c)
        j = judge(case, gen.context_from(c))
        assert j.verdict == c["expected"]["verdict"], c["id"]
        assert {r.rule_id for r in j.reasons} == set(c["expected"]["rule_ids"]), c["id"]


def test_boundary_tags_are_all_covered(cases):
    tags = {t for c in cases for t in c["tags"]}
    assert REQUIRED_TAGS <= tags, REQUIRED_TAGS - tags


def test_document_text_reproduces_gold_amount_and_date(cases):
    for c in cases:
        text = "\n".join(d["text"] for d in c["docs"])
        assert c["gold"]["date"] in text, c["id"]
        out = refine_with_text({"category": c["gold"]["category"]}, text)
        assert out["amount_total"] == c["gold"]["amount_total"], c["id"]
        if c["gold"]["category"] == "출장비":
            t = out["trip"]
            assert t["start"] == c["flags"]["trip"]["start"] and t["end"] == c["flags"]["trip"]["end"], c["id"]
            assert t["destination"], c["id"]
            assert t["domestic"] == c["flags"]["trip"]["domestic"], c["id"]


def test_meeting_docs_carry_attendees_matching_gold(cases):
    for c in cases:
        if c["gold"]["category"] != "회의비":
            continue
        text = "\n".join(d["text"] for d in c["docs"])
        for a in c["gold"]["attendees"]:
            assert a["name"] in text, (c["id"], a["name"])
        if c["gold"]["attendees"]:   # 영수증만 있는 건은 명단 없이 인원수만 있다
            assert c["gold"]["attendee_count"] == len(c["gold"]["attendees"]), c["id"]


def test_external_flag_in_gold_is_derivable_from_affiliation(cases):
    for c in cases:
        if c["gold"]["category"] != "회의비":
            continue
        ci = to_case_input({"category": "회의비", "date": c["gold"]["date"], "amount_total": c["gold"]["amount_total"],
                            "attendees": [{"name": a["name"], "affiliation": a["affiliation"], "external": None} for a in c["gold"]["attendees"]]},
                           institution=gen.INSTITUTION)
        assert [a.external for a in ci.attendees] == [a["external"] for a in c["gold"]["attendees"]], c["id"]


def test_some_cases_cite_public_dataset_source(cases):
    assert sum("서울" in (c.get("source") or "") or "통일부" in (c.get("source") or "") for c in cases) >= 10


def test_write_answer_key_is_deterministic(tmp_path):
    p1 = gen.write_answer_key(tmp_path / "a.json", seed=7)
    p2 = gen.write_answer_key(tmp_path / "b.json", seed=7)
    assert p1.read_bytes() == p2.read_bytes()
    data = json.loads(p1.read_text(encoding="utf-8"))
    assert len(data) == 60 and data[0]["id"]


def test_image_cases_are_receipts_and_number_twenty(cases):
    imgs = [c for c in cases if c.get("image")]
    assert len(imgs) == 20
    assert all(any(d["kind"] == "영수증" for d in c["docs"]) for c in imgs)
