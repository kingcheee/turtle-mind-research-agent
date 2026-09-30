"""서식 출력 — 공식 hwpx에 좌표로 채우고 다시 읽어 확인한다(0건 채움 금지)."""
from pathlib import Path
import pytest
import hwpx_fill_vendored as h
from panjeong.store import Store
from panjeong.rules.models import Attendee, CaseInput
from panjeong.rules.engine import judge
from panjeong.reports.fill import build_report, FORMS_DIR_DEFAULT

FORMS = Path(FORMS_DIR_DEFAULT)
pytestmark = pytest.mark.skipif(not FORMS.exists(), reason="공식 서식 폴더 없음")


def cells(path, coords, section=None):
    """read_cells 결과를 {"T1r12c2": text} 꼴로 — 없는 좌표는 KeyError로 드러난다."""
    res = h.read_cells(str(path), coords, section=section)
    assert res["ok"], res["errors"]
    return {f"T{c['table']}r{c['row']}c{c['col']}": c["text"] for c in res["cells"]}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "r.db")
    ok = CaseInput(category="회의비", date="2026-06-12", time="12:40", amount_total=52800, vat_included=True, vendor_type="식당",
                   attendees=[Attendee("김철수", "ETRI", False), Attendee("박민수", "KAIST", True)], attendee_count=2,
                   purpose="중간점검", has_minutes=True)
    bad = CaseInput(category="회의비", date="2026-06-12", time="12:40", amount_total=24000, vat_included=True, vendor_type="식당",
                    attendees=[Attendee("김철수", "ETRI", False), Attendee("이영희", "ETRI", False)], attendee_count=2,
                    purpose="내부 점검", has_minutes=True)
    for c in (ok, bad):
        cid = s.save_case(c, extracted={}, source_files=[])
        s.save_judgment(cid, judge(c, s.context_for(c)))
    s.appeal(2, statement="외부 자문위원이 실제로 참석했습니다")
    return s


def test_usage_report_fills_research_activity_cash_row_with_allowed_total(store, tmp_path):
    out = build_report("usage", store, FORMS, tmp_path, project={"사업명": "AI 해커톤 시연", "연구개발과제명": "연구비 판정관",
                                                                      "기관명": "거북이정신", "연구책임자": "김지우"})
    assert out.exists() and out.suffix == ".hwpx"
    cells = globals()["cells"](out, [{"table": 9, "row": 19, "col": 18}, {"table": 3, "row": 5, "col": 4}], section=0)
    assert cells["T9r19c18"] == "52,800"
    assert cells["T3r5c4"] == "연구비 판정관"


def test_audit_report_lists_rejected_cases_in_research_activity_row(store, tmp_path):
    out = build_report("audit", store, FORMS, tmp_path)
    cells = globals()["cells"](out, [{"table": 1, "row": 75, "col": 10}, {"table": 1, "row": 75, "col": 33}, {"table": 1, "row": 94, "col": 1}])
    assert "M-25-4-EXT" in cells["T1r75c10"] and "24,000" in cells["T1r75c10"]
    assert cells["T1r75c33"] == "24"   # 천원 단위
    assert cells["T1r94c1"].startswith("연구비 판정관이")   # 「4. 종합의견」 바로 아래 빈 칸(r94) — r98은 날짜 줄이었다


def test_appeal_form_carries_case_summary_and_statement(store, tmp_path):
    out = build_report("appeal", store, FORMS, tmp_path)
    cells = globals()["cells"](out, [{"table": 1, "row": 12, "col": 2}, {"table": 1, "row": 13, "col": 2}])
    assert "제25조 제4항" in cells["T1r12c2"] and "24,000" in cells["T1r12c2"]
    assert "외부 자문위원" in cells["T1r13c2"]


def test_annex_lists_every_case_with_verdict(store, tmp_path):
    out = build_report("annex", store, FORMS, tmp_path)
    assert out.exists()
    text = out.read_text(encoding="utf-8") if out.suffix == ".html" else ""
    if text:
        assert "52,800" in text and "불가" in text and "제2026-38호" in text
