"""웹 셸(2026-09-27 개편, design.md 「고밀도 작업대」) — 행정팀·보고서·실측이 같은 셸(막대 .bar + 표)을 쓰고, 행정팀 표시 스위치가 먹는지."""
import json
from datetime import datetime

from fastapi.testclient import TestClient

from panjeong.store import Store
from panjeong.web.app import create_app, dday
from tests.test_web import EXTRACTED, fake_extractor, judge_form


EXTERNAL = [{"name": "김철수", "affiliation": "ETRI", "external": False},
            {"name": "박민수", "affiliation": "KAIST", "external": True}]


def make_client(tmp_path, project=None):
    if project is not None:
        (tmp_path / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    store = Store(tmp_path / "web.db", deadline_minutes=1)
    return TestClient(create_app(store=store, extractor=fake_extractor, data_dir=tmp_path))


def test_dday_filter_counts_calendar_days_to_deadline():
    now = datetime(2026, 9, 24, 23, 0, 0)
    assert dday("2026-10-01T23:00:00", now) == "D-7"
    assert dday("2026-09-22T09:10:00", now) == "D+2"
    assert dday("2026-09-24T18:00:00", now) == "D-DAY"
    assert dday(None, now) == "—"


def test_admin_tab_uses_shell_with_queue_table(tmp_path):
    c = make_client(tmp_path)
    c.post("/judge", data=judge_form(has_alcohol="on", attendees_json=json.dumps(EXTERNAL)))
    c.post("/case/1/approve")
    r = c.get("/admin")
    assert r.status_code == 200
    assert 'class="bar"' in r.text and "심판 큐" in r.text and 'data-screen="admin"' in r.text
    assert 'id="queue"' in r.text and 'hx-get="/admin/queue/1"' in r.text
    assert "임시승인" in r.text and "D-DAY" in r.text   # 기한 1분 → 오늘


def test_queue_detail_renders_decision_bar_with_statement(tmp_path):
    c = make_client(tmp_path)
    c.post("/judge", data=judge_form())
    c.post("/case/1/appeal", data={"statement": "외부 자문위원이 실제로 참석"})
    r = c.get("/admin/queue/1")
    assert 'class="decide"' in r.text and "외부 자문위원이 실제로 참석" in r.text
    assert 'value="M-25-4-EXT" selected' in r.text


def test_reports_and_bench_tabs_use_shell(tmp_path):
    c = make_client(tmp_path)
    r = c.get("/reports").text
    assert 'data-screen="reports"' in r and 'class="bar"' in r and "/reports/usage.hwpx" in r
    b = c.get("/bench").text
    assert 'data-screen="bench"' in b and 'class="bar"' in b


def test_admin_switch_off_hides_tab_and_queue_actions(tmp_path):
    c = make_client(tmp_path, project={"행정팀": False})
    assert 'href="/admin"' not in c.get("/").text
    r = c.post("/judge", data=judge_form(has_alcohol="on", attendees_json=json.dumps(EXTERNAL)))
    assert ">보완<" in r.text.replace("\n", "") and "임시 승인" not in r.text
    r2 = c.post("/judge", data=judge_form())
    assert ">불가<" in r2.text.replace("\n", "") and "이의 신청" not in r2.text


def test_admin_switch_defaults_on(tmp_path):
    c = make_client(tmp_path)
    assert 'href="/admin"' in c.get("/").text
    r = c.post("/judge", data=judge_form(has_alcohol="on", attendees_json=json.dumps(EXTERNAL)))
    assert "임시 승인" in r.text


def test_sidebar_has_no_project_block(tmp_path):
    # 09-28 사용자 요청: 왼쪽의 과제(번호·과제명·기관·책임·참여) 블록은 정신없어서 뺀다 — 적용 기준만 남긴다.
    c = make_client(tmp_path, project={"연구개발과제번호": "2026-DEMO-001", "연구개발과제명": "판정관 시연 과제",
                                       "기관명": "한국전자통신연구원", "연구책임자": "김지우", "참여연구자": ["김철수", "이영희"]})
    side = c.get("/").text.split('<aside class="sd">')[1].split("</aside>")[0]
    assert "<h4>과제</h4>" not in side and "판정관 시연 과제" not in side and "김철수" not in side
    assert "<h4>적용 기준</h4>" in side
