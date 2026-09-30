"""시행일 구간 — 집행일이 어느 고시 구간에 속하는지. 경계값을 정확히 가른다."""
from panjeong.rules.statutes import window_for


def test_before_2024_12_01_is_w0_old_25_4_institution_basis_with_basic_project_proviso():
    # 구 제25조④: 「해당 연구개발기관에 소속된 자만 참여하는 회의」 식비 불가, 단서 「정부출연기관의 기본사업」
    w = window_for("2024-11-30")
    assert w.code == "W0"
    assert w.requires_external is True
    assert w.external_basis == "기관"
    assert w.basic_project_exception is True
    assert w.requires_prior_approval is False


def test_2024_12_01_starts_w1_2023_49_text_with_prior_approval_and_no_basic_project_proviso():
    # 제2023-49호 개정 ④(제2024-10호 부칙으로 2024-12-01 시행): 외부인 참여 + 사전 내부결재, 기본사업 단서 삭제
    w = window_for("2024-12-01")
    assert w.code == "W1"
    assert "제2023-49호" in w.notice_no
    assert w.requires_external is True
    assert w.external_basis == "기관"
    assert w.requires_prior_approval is True
    assert w.basic_project_exception is False


def test_2026_05_05_is_still_w1():
    assert window_for("2026-05-05").code == "W1"


def test_2026_05_06_starts_w2_participant_basis_without_prior_approval():
    # 제2026-38호 ④: 「해당 연구개발과제의 참여연구자만 참여하는 회의」 식비 불가 — 기관이 아니라 과제 참여 기준
    w = window_for("2026-05-06")
    assert w.code == "W2"
    assert w.notice_no == "제2026-38호"
    assert w.requires_external is True
    assert w.external_basis == "과제"
    assert w.requires_prior_approval is False
    assert w.basic_project_exception is False


def test_none_date_returns_none():
    assert window_for(None) is None
