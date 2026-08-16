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
