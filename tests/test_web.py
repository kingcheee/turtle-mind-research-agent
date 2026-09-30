"""웹 — FastAPI TestClient로 실제 라우트·템플릿·저장소를 탄다. 추출기만 주입한다."""
import json
import pytest
from fastapi.testclient import TestClient
from panjeong.web.app import create_app
from panjeong.store import Store


EXTRACTED = {"doc_type": "영수증", "category": "회의비", "amount_total": 52800, "vat_included": True,
             "date": "2026-06-12", "time": "12:40", "vendor_name": "한식당 미가", "vendor_type": "식당",
             "has_alcohol": False, "attendee_count": 2,
             "attendees": [{"name": "김철수", "affiliation": "ETRI", "external": False},
                           {"name": "이영희", "affiliation": "ETRI", "external": False}],
             "purpose": "내부 점검", "trip": None}


def fake_extractor(docs):
    return EXTRACTED, {"seconds": 0.01, "gen_tokens": 5, "tg_per_s": 99.0}


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "web.db", deadline_minutes=1)
    app = create_app(store=store, extractor=fake_extractor, data_dir=tmp_path)
    return TestClient(app)


def judge_form(**over):
    f = {"category": "회의비", "date": "2026-06-12", "time": "12:40", "amount_total": "52800",
         "vat_included": "true", "vendor_type": "식당", "attendee_count": "2", "purpose": "내부 점검",
         "attendees_json": json.dumps(EXTRACTED["attendees"], ensure_ascii=False),
         "has_minutes": "on", "extracted_json": json.dumps(EXTRACTED, ensure_ascii=False), "doc_types": "영수증,회의록"}
    f.update(over)
    return f


def test_home_renders_researcher_tab(client):
    r = client.get("/")
    assert r.status_code == 200 and "연구비 판정관" in r.text and "행정팀" in r.text


def test_extract_uses_injected_extractor_and_prefills_form(client):
    r = client.post("/extract", data={"text_doc": "한식당 미가 52,800원", "text_doc_type": "영수증"})
    assert r.status_code == 200
    assert "52800" in r.text and "김철수" in r.text


def test_judge_saves_case_and_renders_verdict_with_article(client):
    r = client.post("/judge", data=judge_form())
    assert r.status_code == 200
    assert "불가" in r.text and "제25조 제4항" in r.text and "2026-06-12" in r.text
    assert client.get("/admin").status_code == 200


def test_provisional_approval_appears_in_admin_queue(client):
    client.post("/judge", data=judge_form(has_alcohol="on", attendees_json=json.dumps(
        [{"name": "김철수", "affiliation": "ETRI", "external": False}, {"name": "박민수", "affiliation": "KAIST", "external": True}])))
    r = client.post("/case/1/approve")
    assert r.status_code == 200
    assert "임시승인" in client.get("/admin").text


def test_admin_accept_with_exception_makes_next_judgment_allowed(client):
    client.post("/judge", data=judge_form())
    client.post("/case/1/approve")
    r = client.post("/admin/decide/1", data={"decision": "인정", "note": "기본사업 성격", "register_exception": "on",
                                              "rule_id": "M-25-4-EXT"})
    assert r.status_code == 200
    assert 'data-rule="M-25-4-EXT"' in client.get("/admin").text     # 규칙 ID는 화면 글자가 아니라 속성으로(09-28)
    r2 = client.post("/judge", data=judge_form())
    assert "예외 사전" in r2.text and ">가능<" in r2.text.replace("\n", "")


def test_form_participant_flag_and_innovation_fund_reach_the_engine(client):
    non_participant = [{"name": "김철수", "affiliation": "ETRI", "external": False, "participant": True},
                       {"name": "최민호", "affiliation": "ETRI", "external": False, "participant": False}]
    r = client.post("/judge", data=judge_form(attendees_json=json.dumps(non_participant, ensure_ascii=False)))
    assert ">가능<" in r.text.replace("\n", "") and "M-25-4-EXT" not in r.text
    r2 = client.post("/judge", data=judge_form(innovation_fund="on"))
    assert ">가능<" in r2.text.replace("\n", "") and "제25조의2 제6항" in r2.text


def test_appeal_creates_appeal_item(client):
    client.post("/judge", data=judge_form())
    r = client.post("/case/1/appeal", data={"statement": "외부 자문위원이 참석했습니다"})
    assert r.status_code == 200
    assert "이의" in client.get("/admin").text


def test_reports_page_lists_official_forms(client):
    r = client.get("/reports")
    assert r.status_code == 200 and "사용실적보고서" in r.text and "이의신청서" in r.text


def test_queue_detail_offers_rule_ids_of_the_judgment_for_exception_registration(client):
    client.post("/judge", data=judge_form())
    client.post("/case/1/appeal", data={"statement": "소명"})
    r = client.get("/admin/queue/1")
    assert r.status_code == 200
    assert 'value="M-25-4-EXT" selected' in r.text   # 첫 규칙이 기본 선택 — 「(없음)」이 기본이면 등록을 빼먹는다
