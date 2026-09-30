"""벤치 채점 — 추출 JSON을 정답지와 필드 단위로 비교한다."""
from bench.score import score_fields


GOLD = {"category": "회의비", "amount_total": 52800, "date": "2026-06-12", "vendor_type": "식당", "has_alcohol": False,
        "attendee_count": 4, "attendees": [{"name": "김철수", "external": False}, {"name": "박민수", "external": True}]}


def test_exact_match_scores_full():
    s = score_fields(dict(GOLD), GOLD)
    assert s["correct"] == s["total"] and s["total"] >= 7


def test_wrong_scalar_and_missing_attendee_are_counted():
    pred = dict(GOLD); pred["vendor_type"] = "카페"; pred["attendees"] = [{"name": "김철수", "external": False}]
    s = score_fields(pred, GOLD)
    assert s["correct"] == s["total"] - 2
    assert "vendor_type" in s["wrong"] and "attendees" in s["wrong"]


def test_none_prediction_is_wrong_not_crash():
    s = score_fields({}, GOLD)
    assert s["correct"] == 0 and s["total"] >= 7


def test_refine_prediction_applies_code_corrections_before_scoring():
    # 모델 단독 vs 코드 보정 후를 따로 잰다 — 보정(텍스트 확정·소속 기반 외부 여부)은 실제 파이프라인의 일부다
    from bench.run_bench import refine_prediction
    raw = {"category": "회의비", "amount_total": 52800, "date": "2026-06-12", "vendor_type": "카페", "has_alcohol": None, "attendee_count": 4,
           "attendees": [{"name": "김철수", "affiliation": "한국전자통신연구원 선임연구원", "external": None},
                         {"name": "박민수", "affiliation": "KAIST 교수", "external": None}]}
    text = "[카드매출전표] 한식당 미가 된장찌개 4 48,000 합계 52,800원\n참석자: 김철수, 박민수"
    pred = refine_prediction(raw, text, institution="한국전자통신연구원")
    assert pred["vendor_type"] == "식당" and pred["has_alcohol"] is False
    assert [(a["name"], a["external"]) for a in pred["attendees"]] == [("김철수", False), ("박민수", True)]
    assert score_fields(pred, GOLD)["correct"] == score_fields(pred, GOLD)["total"]
