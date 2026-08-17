from unittest.mock import MagicMock
import pytest

from src.apply import batch_answer_questions_with_llm
from src.scrape import build_search_urls, _is_bot_blocked


def test_batch_answer_with_llm_formats_and_extracts(monkeypatch):
    profile = {
        "name": "Alex",
        "skills": [{"name": "Python"}, {"name": "Docker"}],
        "years_experience": 3,
    }
    job = {
        "title": "Backend Dev",
        "company": "Tech Corp",
        "location": "Jakarta",
    }
    questions = [
        {"key": "q1", "label": "Years of experience with Python?", "type": "number"},
        {"key": "q2", "label": "Do you know Docker?", "type": "radio", "options": ["Yes", "No"]},
    ]

    mock_llm_json = '```json\n{"q1": "3", "q2": "Yes"}\n```'
    monkeypatch.setattr("src.apply.complete", lambda msgs, cfg, **kw: mock_llm_json)

    answers = batch_answer_questions_with_llm(questions, job, profile, cfg={})
    assert answers["q1"] == "3"
    assert answers["q2"] == "Yes"


def test_batch_answer_single_question_raw_text_fallback(monkeypatch):
    profile = {"name": "Alex"}
    job = {"title": "Dev"}
    questions = [{"key": "q1", "label": "Notice period", "options": ["Immediate", "1 Month", "2 Months"]}]

    monkeypatch.setattr("src.apply.complete", lambda msgs, cfg, **kw: "immediate")

    answers = batch_answer_questions_with_llm(questions, job, profile, cfg={})
    assert answers["q1"] == "Immediate"


def test_build_search_urls_filtering():
    cfg = {
        "search": {
            "base": "https://id.jobstreet.com",
            "url_template": "{base}/id/{role_slug}-jobs/in-{loc_slug}",
            "roles": [
                {"name": "Python Dev", "slug": "python-dev"},
                {"name": "Golang Dev", "slug": "golang-dev"},
            ],
            "locations": [
                {"name": "Jakarta", "slug": "jakarta"},
                {"name": "Bandung", "slug": "bandung"},
            ],
        }
    }

    # All combinations
    all_urls = build_search_urls(cfg)
    assert len(all_urls) == 4

    # Filtered by role and location
    filtered_urls = build_search_urls(cfg, roles=["Python Dev"], locations=["jakarta"])
    assert len(filtered_urls) == 1
    assert "python-dev" in filtered_urls[0] and "in-jakarta" in filtered_urls[0]


def test_is_bot_blocked_detection():
    mock_page = MagicMock()
    mock_page.title.return_value = "Just a moment..."
    mock_page.url = "https://id.jobstreet.com"
    assert _is_bot_blocked(mock_page) is True

    # Cloudflare challenge url
    mock_page.title.return_value = "Job Details"
    mock_page.url = "https://id.jobstreet.com/__cf_chl_tk"
    assert _is_bot_blocked(mock_page) is True

    # Normal page
    mock_page.title.return_value = "Software Engineer Jobs in Jakarta"
    mock_page.url = "https://id.jobstreet.com/jobs"
    mock_page.locator.return_value.inner_text.return_value = "Normal page text"
    mock_page.content.return_value = "<html>Normal HTML</html>"
    assert _is_bot_blocked(mock_page) is False
