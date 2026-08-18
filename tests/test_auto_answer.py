from unittest.mock import MagicMock

import pytest

from src.apply import answer_with_llm, _fill_known_fields


def test_answer_with_llm_dropdown_selection(monkeypatch):
    cfg = {"llm": {"model": "gpt-4o-mini"}}
    profile = {
        "work_rights": "Indonesian Citizen",
        "languages": ["Indonesian", "English"],
    }
    job = {"title": "Data Analyst", "company": "Tech Corp", "location": "Jakarta"}

    monkeypatch.setattr("src.apply.complete", lambda messages, cfg, **kwargs: '{"q": "Indonesian Citizen"}')

    options = ["Indonesian Citizen", "Permanent Resident", "Work Visa Required"]
    ans = answer_with_llm("What is your work authorization status?", "select", options, job, profile, cfg)
    assert ans == "Indonesian Citizen"


def test_answer_with_llm_fallback_matching(monkeypatch):
    cfg = {"llm": {"model": "gpt-4o-mini"}}
    profile = {"years_experience": 1}
    job = {"title": "Junior Python Dev"}

    monkeypatch.setattr("src.apply.complete", lambda messages, cfg, **kwargs: '{"q": "1 year"}')

    options = ["Less than 1 year", "1-2 years", "3+ years"]
    ans = answer_with_llm("How many years of Python experience do you have?", "select", options, job, profile, cfg)
    assert ans in ("1-2 years", "Less than 1 year")


def test_fill_known_fields_uses_llm_for_unseen_questions(monkeypatch):
    mock_page = MagicMock()
    mock_page.evaluate.return_value = {
        "groups": [],
        "fields": [
            {
                "tag": "input",
                "type": "text",
                "name": "notice",
                "id": "notice_id",
                "label": "Notice Period",
                "value": "",
                "options": [],
            }
        ]
    }
    mock_locator = MagicMock()
    mock_page.locator.return_value = mock_locator
    mock_locator.first = mock_locator
    mock_locator.element_handle.return_value = MagicMock()

    answers = []
    cfg = {"llm": {"model": "gpt-4o-mini"}}
    profile = {"notice_period": "Immediately"}
    job = {"title": "Data Analyst", "company": "Test Co"}

    monkeypatch.setattr("src.apply.complete", lambda messages, cfg, **kwargs: '{"field_0": "Immediately"}')

    unknown = _fill_known_fields(
        mock_page, answers, 7000000, False,
        conn=None, job=job, profile=profile, cfg=cfg
    )

    assert unknown == []
    assert len(answers) == 1
    assert answers[0]["answer"] == "Immediately"
    mock_locator.fill.assert_called_once_with("Immediately")


def test_answer_with_llm_zero_experience_english(monkeypatch):
    cfg = {"llm": {"model": "gpt-4o-mini"}}
    profile = {
        "experience": [{"role": "Software Engineer", "summary": "Python and web dev"}],
        "years_experience": 1,
    }
    job = {"title": "IT Business Analyst", "company": "PT Asuransi Central Asia"}

    # Mock LLM returning 0 / No experience for insurance question
    monkeypatch.setattr("src.apply.complete", lambda messages, cfg, **kwargs: '{"q": "0 years"}')

    options = ["Less than 1 year", "1-2 years", "3-5 years", "More than 5 years"]
    ans = answer_with_llm(
        "How many years' experience do you have in the insurance industry?",
        "select",
        options,
        job,
        profile,
        cfg,
    )
    assert ans == "Less than 1 year"


def test_answer_with_llm_zero_experience_indonesian(monkeypatch):
    cfg = {"llm": {"model": "gpt-4o-mini"}}
    profile = {
        "experience": [{"role": "Software Engineer", "summary": "Python and web dev"}],
        "years_experience": 1,
    }
    job = {"title": "IT Business Analyst", "company": "PT Asuransi Central Asia"}

    monkeypatch.setattr("src.apply.complete", lambda messages, cfg, **kwargs: '{"q": "Tidak ada pengalaman"}')

    options = ["Kurang dari 1 tahun", "1-2 tahun", "3-5 tahun", "Lebih dari 5 tahun"]
    ans = answer_with_llm(
        "Berapa tahun pengalaman Anda di industri asuransi?",
        "select",
        options,
        job,
        profile,
        cfg,
    )
    assert ans == "Kurang dari 1 tahun"


def test_select_best_option_zero_experience_fallbacks():
    from src.apply import select_best_option

    # English options
    mock_select = MagicMock()
    mock_select.evaluate.return_value = [
        {"index": 0, "value": "", "text": "Select an option"},
        {"index": 1, "value": "0", "text": "Less than 1 year"},
        {"index": 2, "value": "1", "text": "1-2 years"},
        {"index": 3, "value": "2", "text": "3+ years"},
    ]

    for zero_input in ["0", "0 years", "None", "No experience", "N/A"]:
        assert select_best_option(mock_select, zero_input) is True
        mock_select.select_option.assert_called_with(index=1)

    # Indonesian options
    mock_select_id = MagicMock()
    mock_select_id.evaluate.return_value = [
        {"index": 0, "value": "", "text": "Pilih salah satu"},
        {"index": 1, "value": "0", "text": "Kurang dari 1 tahun"},
        {"index": 2, "value": "1", "text": "1-2 tahun"},
    ]

    for zero_input in ["0", "0 tahun", "Tidak ada", "Tidak ada pengalaman", "Tidak satupun"]:
        assert select_best_option(mock_select_id, zero_input) is True
        mock_select_id.select_option.assert_called_with(index=1)

