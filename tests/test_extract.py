"""추출 계층 — OCR 정리, 프롬프트, llama-server 클라이언트, 추출 JSON → CaseInput."""
import json
import httpx
from panjeong.extract.ocr import clean_ocr_text
from panjeong.extract.prompt import build_prompt, to_case_input, GRAMMAR_PATH
from panjeong.extract.client import LlamaClient


def test_clean_ocr_joins_hangul_syllables_but_keeps_number_boundaries():
    raw = "한 식 당 미 가 사 업 자 123-45-67890\n된 장 찌 개 4 48,000\n합 계 52,800 원 ( 부 가 세 포 함 )"
    out = clean_ocr_text(raw)
    assert "한식당미가사업자 123-45-67890" in out
    assert "된장찌개 4 48,000" in out
    assert "합계 52,800 원 (부가세포함)" in out


def test_prompt_wraps_documents_in_chat_template():
    p = build_prompt([("영수증", "한식당 미가 52,800원"), ("회의록", "참석: 김철수")])
    assert p.startswith("<|im_start|>system")
    assert "[영수증]" in p and "[회의록]" in p
    assert p.rstrip().endswith("<|im_start|>assistant")


def test_grammar_file_exists_and_declares_root():
    text = GRAMMAR_PATH.read_text(encoding="utf-8")
    assert text.lstrip().startswith("root ::=")
    assert 'trip' in text and 'time' in text


def test_client_returns_parsed_json_and_timings():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        assert "grammar" in body and body["temperature"] == 0
        return httpx.Response(200, json={"content": '{"doc_type":"영수증","category":"회의비"}',
                                         "tokens_evaluated": 10, "tokens_predicted": 5,
                                         "timings": {"prompt_per_second": 100.0, "predicted_per_second": 15.0}})
    client = LlamaClient("http://llama.test", transport=httpx.MockTransport(handler))
    data, meta = client.extract("prompt text", grammar="root ::= \"x\"")
    assert data["category"] == "회의비"
    assert meta["gen_tokens"] == 5 and meta["tg_per_s"] == 15.0


def test_to_case_input_maps_fields_and_derives_evidence_from_doc_types():
    extracted = {
        "doc_type": "영수증", "category": "회의비", "amount_total": 52800, "vat_included": True,
        "date": "2026-06-12", "time": "12:40", "vendor_name": "한식당 미가", "vendor_type": "식당",
        "has_alcohol": False, "attendee_count": 4,
        "attendees": [{"name": "박민수", "affiliation": "KAIST", "external": True}],
        "purpose": "중간점검", "trip": None,
    }
    case = to_case_input(extracted, doc_types=["영수증", "회의록"])
    assert case.category == "회의비" and case.amount_total == 52800
    assert case.attendees[0].external is True
    assert case.has_minutes is True and case.has_internal_approval is False


def test_to_case_input_maps_trip_and_marks_plan_doc_from_doc_types():
    extracted = {"doc_type": "출장신청서", "category": "출장비", "amount_total": 180000, "date": "2026-06-20",
                 "trip": {"destination": "Boston", "start": "2026-06-20", "end": "2026-06-25", "domestic": False,
                          "meals_provided": False}}
    case = to_case_input(extracted, doc_types=["출장신청서"])
    assert case.trip.domestic is False and case.trip.plan_doc is True and case.trip.report_doc is False


def test_external_is_derived_from_affiliation_when_model_leaves_it_null():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "김철수", "affiliation": "한국전자통신연구원", "external": None},
                               {"name": "이영희", "affiliation": "한국전자통신연구원", "external": None},
                               {"name": "박민수", "affiliation": "KAIST 교수", "external": None}]}
    case = to_case_input(extracted, doc_types=["영수증", "회의록"])
    assert [a.external for a in case.attendees] == [False, False, True]


def test_external_stays_none_when_affiliation_unknown():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "김철수", "affiliation": None, "external": None}]}
    case = to_case_input(extracted, doc_types=["영수증"])
    assert case.attendees[0].external is None


def test_model_external_flag_is_kept_only_when_affiliation_is_unknown():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "김철수", "affiliation": None, "external": True}]}
    case = to_case_input(extracted, doc_types=["영수증"])
    assert case.attendees[0].external is True


def test_affiliation_overrides_wrong_model_external_flag():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "김철수", "affiliation": "한국전자통신연구원", "external": False},
                               {"name": "박민수", "affiliation": "KAIST 교수", "external": False},
                               {"name": "이영희", "affiliation": "한국전자통신연구원", "external": True}]}
    case = to_case_input(extracted, doc_types=["영수증"])
    assert [a.external for a in case.attendees] == [False, True, False]


from panjeong.extract.prompt import refine_with_text


def test_refine_marks_alcohol_from_document_keywords_not_model():
    ex = {"has_alcohol": False, "vendor_type": "식당"}
    out = refine_with_text(ex, "한식당 미가 된장찌개 4 소주 2병 합계 60,000원")
    assert out["has_alcohol"] is True


def test_refine_downgrades_bar_vendor_type_when_no_alcohol_keywords():
    ex = {"has_alcohol": False, "vendor_type": "주점"}
    out = refine_with_text(ex, "국밥집 온기 돼지국밥 3 x 11,000 합계 33,000원")
    assert out["vendor_type"] == "식당" and out["has_alcohol"] is False


def test_refine_keeps_bar_when_keywords_present():
    ex = {"has_alcohol": None, "vendor_type": "주점"}
    out = refine_with_text(ex, "호프 앤 펍 생맥주 4 잔 합계 28,000원")
    assert out["vendor_type"] == "주점" and out["has_alcohol"] is True


def test_refine_infers_vendor_type_from_menu_keywords_over_model_guess():
    # 1.5B 모델은 된장찌개 영수증도 「카페」라 한다(벤치 20/20 오답) — 품목 키워드가 있으면 코드가 정한다
    assert refine_with_text({"vendor_type": "카페"}, "[카드매출전표] 흥부골\n된장찌개 3 55,800\n합계 64,000원")["vendor_type"] == "식당"
    assert refine_with_text({"vendor_type": "식당"}, "카페 브루잉 아메리카노 6 x 5,000 케이크 2 합계 80,000원")["vendor_type"] == "카페"
    assert refine_with_text({"vendor_type": "카페"}, "호프 앤 펍 생맥주 4 잔 합계 28,000원")["vendor_type"] == "주점"
    assert refine_with_text({"vendor_type": "기타"}, "[승차권 영수증] KTX 서울→부산 왕복 운임 119,600원")["vendor_type"] == "교통"
    assert refine_with_text({"vendor_type": "기타"}, "[e-ticket 영수증] 항공 인천→Boston 항공료 1,850,000원")["vendor_type"] == "교통"


def test_refine_keeps_model_vendor_type_when_no_keyword():
    assert refine_with_text({"vendor_type": "호텔"}, "그랜드 컨벤션 합계 300,000원")["vendor_type"] == "호텔"
    assert refine_with_text({"vendor_type": None}, "알 수 없는 업체 합계 10,000원")["vendor_type"] is None


def test_institution_setting_decides_external_even_for_single_attendee():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "박민수", "affiliation": "KAIST 교수", "external": None}]}
    case = to_case_input(extracted, doc_types=["영수증"], institution="한국전자통신연구원")
    assert case.attendees[0].external is True
    case2 = to_case_input({**extracted, "attendees": [{"name": "김철수", "affiliation": "한국전자통신연구원 선임", "external": True}]},
                          doc_types=["영수증"], institution="한국전자통신연구원")
    assert case2.attendees[0].external is False


def test_participant_is_decided_by_project_roster_when_given():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "김철수", "affiliation": "한국전자통신연구원", "external": None},
                               {"name": "최민호", "affiliation": "한국전자통신연구원", "external": None},
                               {"name": "박민수", "affiliation": "KAIST", "external": None}]}
    case = to_case_input(extracted, doc_types=["영수증"], institution="한국전자통신연구원", participants=["김철수", "이영희"])
    assert [a.participant for a in case.attendees] == [True, False, False]
    assert [a.external for a in case.attendees] == [False, False, True]


def test_participant_falls_back_to_institution_membership_without_roster():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "김철수", "affiliation": "한국전자통신연구원", "external": None},
                               {"name": "박민수", "affiliation": "KAIST", "external": None},
                               {"name": "홍길동", "affiliation": None, "external": None}]}
    case = to_case_input(extracted, doc_types=["영수증"], institution="한국전자통신연구원")
    assert [a.participant for a in case.attendees] == [True, False, None]


def test_explicit_participant_flag_from_form_is_kept():
    extracted = {"category": "회의비", "amount_total": 50000, "date": "2026-06-12",
                 "attendees": [{"name": "최민호", "affiliation": "한국전자통신연구원", "external": None, "participant": False}]}
    case = to_case_input(extracted, doc_types=["영수증"], institution="한국전자통신연구원", participants=["최민호"])
    assert case.attendees[0].participant is False


TRIP_TEXT = ("국외 출장 결과보고서. 출장자: 김철수(한국전자통신연구원). 출장지: Boston, USA. 기간: 2026-06-20 ~ 2026-06-25. "
             "목적: NeurIPS 워크숍 발표. 항공료 1,850,000원, 숙박 4박 960,000원, 학회 측 점심 제공(3일).")


def test_refine_fills_trip_dates_destination_and_domestic_from_text():
    ex = {"category": "출장비", "date": None, "amount_total": 2,
          "trip": {"destination": "None", "start": None, "end": None, "domestic": None, "meals_provided": None}}
    out = refine_with_text(ex, TRIP_TEXT)
    t = out["trip"]
    assert t["start"] == "2026-06-20" and t["end"] == "2026-06-25"
    assert t["destination"].startswith("Boston") and t["domestic"] is False
    assert out["date"] == "2026-06-20"


def test_refine_sums_listed_amounts_when_model_amount_is_implausible():
    ex = {"category": "출장비", "amount_total": 2, "trip": None}
    out = refine_with_text(ex, TRIP_TEXT)
    assert out["amount_total"] == 1850000 + 960000


def test_refine_keeps_explicit_total_over_sum():
    ex = {"category": "회의비", "amount_total": None, "trip": None}
    out = refine_with_text(ex, "된장찌개 4 x 12,000 = 48,000원 공기밥 4,800원 합계 52,800원")
    assert out["amount_total"] == 52800


def test_refine_skips_a_broken_ocr_total_for_a_clean_one():
    """09-29 E2E: Gemini 영수증 사진(1200px) OCR이 「합계 52,80뻔」 — 쉼표 묶음이 깨진 합계에서 앞 「52」만 잡아 52원이 됐다.
    깨진 합계는 건너뛰고 같은 건의 회의록 「합계 52,800원」을 쓴다."""
    ocr = "한식당미가\n거래일시 2026-06-12 12:40\n공급가액 48,000\n부캬세 4,8요0\n합계 52,80뻔\n카드번호 1234"
    minutes = "참석: 김철수, 박민수(KAIST).\n영수증: 한식당 미가 합계 52,800원(부가세 포함)"
    assert refine_with_text({"amount_total": 52800}, ocr + "\n" + minutes)["amount_total"] == 52800
    assert refine_with_text({"amount_total": 52800}, ocr)["amount_total"] == 52800      # 깨진 합계뿐이면 모델 값 유지
    assert refine_with_text({"amount_total": None}, "합계 52800")["amount_total"] == 52800  # 쉼표 없는 네 자리 이상은 그대로
    assert refine_with_text({"amount_total": None}, "합계: 900원")["amount_total"] == 900
    # Tesseract는 「원」을 「8」로 자주 읽는다(ocr_smoke M07·M08·M09, R6 「36,0008」) — 쉼표 묶음이 끝났으면 그 값
    assert refine_with_text({"amount_total": None}, "합계 64,0008 (부가세포함)")["amount_total"] == 64000
    assert refine_with_text({"amount_total": 7}, "합계 1,234,56")["amount_total"] == 7       # 덜 끝난 묶음은 버림


def test_refine_completes_a_vendor_name_cut_mid_word():
    """09-29 E2E: 시연 4번에 Gemini 사진(OCR 「한식당미가」)을 붙이자 모델이 가맹점을 「한식당 미」로 잘랐다(텍스트만일 땐 「한식당 미가」).
    원문에 그 이름이 낱말 경계로 끝나는 자리가 없고 낱말 중간에서만 끊기면 그 낱말 끝까지 늘린다."""
    text = "한식당미가\n합계 24,000 원\n2026-06-12 12:00 과제 내부 점검 회의(장소: 한식당 미가).\n영수증: 한식당 미가 2026-06-12 12:40"
    assert refine_with_text({"vendor_name": "한식당 미"}, text)["vendor_name"] == "한식당 미가"
    assert refine_with_text({"vendor_name": "카페"}, "카페 브루잉 합계 80,000원")["vendor_name"] == "카페"   # 온전한 낱말이면 그대로
    assert refine_with_text({"vendor_name": "월향"}, "합계 60,000원")["vendor_name"] == "월향"               # 원문에 없으면 그대로
    assert refine_with_text({"vendor_name": None}, text)["vendor_name"] is None


def test_refine_marks_meals_provided_from_text():
    ex = {"category": "출장비", "amount_total": 100000, "trip": {"destination": "부산", "start": "2026-06-20", "end": "2026-06-21", "domestic": True, "meals_provided": None}}
    out = refine_with_text(ex, "국내 출장. 학회 측 점심 제공.")
    assert out["trip"]["meals_provided"] is True
