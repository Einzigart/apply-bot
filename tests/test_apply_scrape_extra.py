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

from src.apply import _click_apply, ApplySkipped

def test_h1_already_applied_guard_raises_apply_skipped():
    mock_page = MagicMock()
    # Mock locator returning count > 0 for applied text
    def mock_locator(selector):
        loc = MagicMock()
        if selector == 'text="Kamu sudah melamar lowongan ini"':
            loc.count.return_value = 1
        elif selector == 'text="You applied for this job"':
            loc.count.return_value = 0
        else:
            loc.count.return_value = 0
            loc.first.count.return_value = 0
        return loc

    mock_page.locator.side_effect = mock_locator
    with pytest.raises(ApplySkipped, match="already applied previously"):
        _click_apply(mock_page)

    # Test English variant
    def mock_locator_en(selector):
        loc = MagicMock()
        if selector == 'text="You applied for this job"':
            loc.count.return_value = 1
        else:
            loc.count.return_value = 0
            loc.first.count.return_value = 0
        return loc

    mock_page.locator.side_effect = mock_locator_en
    with pytest.raises(ApplySkipped, match="already applied previously"):
        _click_apply(mock_page)

from src.apply import salary_for

def test_m1_salary_for_dot_grouped_idr():
    profile = {"salary": {"min_acceptable": 6000000, "preferred": 7000000}}
    # When advertised max is 6M (min_acceptable is 6M)
    assert salary_for({"salary_text": "Rp 5.500.000 – Rp 6.000.000"}, profile) == 6000000
    # When advertised max is above min_acceptable
    assert salary_for({"salary_text": "Rp 6.500.000 – Rp 8.000.000"}, profile) == 7000000
    # Comma grouped format still works
    assert salary_for({"salary_text": "5,000,000 - 6,000,000"}, profile) == 6000000


def test_click_apply_detects_external_target_blank():
    mock_page = MagicMock()
    mock_page.locator.return_value.count.return_value = 0
    mock_page.locator.return_value.first.count.return_value = 0

    mock_btn = MagicMock()
    mock_btn.get_attribute.side_effect = lambda attr: "_blank" if attr == "target" else "/id/job/94056112/apply"
    mock_btn.inner_text.return_value = "Lamar Cepat"
    mock_btn.query_selector.return_value = None

    mock_page.query_selector.return_value = mock_btn

    with pytest.raises(ApplySkipped, match="external ATS redirect detected"):
        _click_apply(mock_page)


def test_click_apply_detects_external_button_text():
    mock_page = MagicMock()
    mock_page.locator.return_value.count.return_value = 0
    mock_page.locator.return_value.first.count.return_value = 0

    mock_btn = MagicMock()
    mock_btn.get_attribute.side_effect = lambda attr: "_self" if attr == "target" else "/id/job/123/apply"
    mock_btn.inner_text.return_value = "Apply on company site"
    mock_btn.query_selector.return_value = None

    mock_page.query_selector.return_value = mock_btn

    with pytest.raises(ApplySkipped, match="external ATS redirect detected"):
        _click_apply(mock_page)

