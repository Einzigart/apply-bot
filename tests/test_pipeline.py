from unittest.mock import MagicMock, patch

import pytest

from src.pipeline import run_pipeline
from src.db import connect, find_job, latest_evaluations, list_applications


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_jobs.db"
    return connect(db_file)


def test_run_pipeline_page_by_page_execution(test_db, monkeypatch):
    """Verifies that pipeline scrapes page 1, scores, applies, and continues to page 2."""
    cfg = {
        "search": {
            "base": "https://id.jobstreet.com",
            "url_template": "{base}/id/{role_slug}-jobs/in-{loc_slug}",
            "roles": [{"name": "Data Analyst", "slug": "data-analyst"}],
            "locations": [{"name": "Jakarta", "slug": "Jakarta"}],
        },
        "filters": {
            "title_blacklist": ["intern", "senior"],
            "role_keywords": ["data", "analyst"],
            "location_whitelist": ["jakarta"],
            "max_years_experience": 1,
            "company_cooldown_days": 28,
        },
        "scoring": {
            "match_threshold": 0.6,
            "borderline_band": [0.5, 0.7],
            "extra_skill_vocab": ["sql", "python"],
        },
        "apply": {
            "pacing_seconds": [0, 0],
            "skip_external_ats": True,
            "submit_button_text": "Kirim",
            "success_text": "Lamaranmu telah dikirim",
        },
    }
    profile = {
        "name": "Candidate",
        "skills": [{"name": "Python"}, {"name": "SQL"}],
        "salary": {"min_acceptable": 6000000, "preferred": 7000000},
    }

    # Simulate 2 pages of scraping
    page_1_cards = [
        {
            "jobstreet_id": "1001",
            "url": "https://id.jobstreet.com/id/job/1001",
            "title": "Junior Data Analyst",
            "company": "Company A",
            "location": "Jakarta",
            "teaser": "Python and SQL role",
            "description": "Looking for Junior Data Analyst with Python and SQL. 0-1 years.",
        },
        {
            "jobstreet_id": "1002",
            "url": "https://id.jobstreet.com/id/job/1002",
            "title": "Senior Data Analyst",  # Will be filtered out
            "company": "Company B",
            "location": "Jakarta",
            "teaser": "Senior role",
        },
    ]

    page_2_cards = [
        {
            "jobstreet_id": "1003",
            "url": "https://id.jobstreet.com/id/job/1003",
            "title": "Data Analyst",
            "company": "Company C",
            "location": "Jakarta",
            "teaser": "SQL analytics",
            "description": "Data Analyst position. SQL requirements.",
        }
    ]

    def mock_scrape_serp_http(url, cfg):
        if "page=2" in url:
            return page_2_cards
        return page_1_cards

    monkeypatch.setattr("src.pipeline.scrape_serp_http", mock_scrape_serp_http)
    monkeypatch.setattr("src.pipeline.scrape_detail_http", lambda card, cfg: card)

    applied_jobs = []

    def mock_run_apply(cfg, conn, profile, *, execute, use_llm_letter, limit, headless, jobs=None):
        nonlocal applied_jobs
        applied_jobs.extend(jobs or [])
        return {
            "submitted": len(jobs or []) if execute else 0,
            "dry-run": len(jobs or []) if not execute else 0,
            "failed": 0,
            "skipped": 0,
        }

    monkeypatch.setattr("src.pipeline.run_apply", mock_run_apply)

    stats = run_pipeline(
        cfg,
        test_db,
        profile,
        pages=2,
        headless=True,
        offline_score=True,
        execute=False,
    )

    assert stats.pages_processed == 2
    assert stats.cards_seen == 3
    assert stats.title_filtered == 1  # Senior Data Analyst
    assert stats.new_jobs == 2  # 1001 and 1003
    assert stats.scored == 2
    assert stats.dry_run == 2
    assert len(applied_jobs) == 2
    assert {j["jobstreet_id"] for j in applied_jobs} == {"1001", "1003"}


def test_run_pipeline_respects_apply_limit(test_db, monkeypatch):
    """Verifies that pipeline stops or caps applications when limit is hit."""
    cfg = {
        "search": {
            "base": "https://id.jobstreet.com",
            "url_template": "{base}/id/{role_slug}-jobs/in-{loc_slug}",
            "roles": [{"name": "Data Analyst", "slug": "data-analyst"}],
            "locations": [{"name": "Jakarta", "slug": "Jakarta"}],
        },
        "filters": {
            "title_blacklist": [],
            "role_keywords": ["data"],
            "location_whitelist": ["jakarta"],
            "max_years_experience": 1,
            "company_cooldown_days": 28,
        },
        "scoring": {
            "match_threshold": 0.6,
            "borderline_band": [0.5, 0.7],
            "extra_skill_vocab": ["python"],
        },
        "apply": {
            "pacing_seconds": [0, 0],
            "skip_external_ats": True,
            "submit_button_text": "Kirim",
            "success_text": "Lamaranmu telah dikirim",
        },
    }
    profile = {
        "name": "Candidate",
        "skills": [{"name": "Python"}],
        "salary": {"min_acceptable": 6000000, "preferred": 7000000},
    }

    page_cards = [
        {
            "jobstreet_id": "2001",
            "url": "https://id.jobstreet.com/id/job/2001",
            "title": "Data Analyst 1",
            "company": "Company 1",
            "location": "Jakarta",
            "description": "Python job",
        },
        {
            "jobstreet_id": "2002",
            "url": "https://id.jobstreet.com/id/job/2002",
            "title": "Data Analyst 2",
            "company": "Company 2",
            "location": "Jakarta",
            "description": "Python job",
        },
    ]

    monkeypatch.setattr("src.pipeline.scrape_serp_http", lambda url, cfg: page_cards)
    monkeypatch.setattr("src.pipeline.scrape_detail_http", lambda card, cfg: card)

    applied_jobs = []

    def mock_run_apply(cfg, conn, profile, *, execute, use_llm_letter, limit, headless, jobs=None):
        nonlocal applied_jobs
        to_apply = jobs[:limit] if limit is not None else jobs
        applied_jobs.extend(to_apply or [])
        return {
            "submitted": 0,
            "dry-run": len(to_apply or []),
            "failed": 0,
            "skipped": 0,
        }

    monkeypatch.setattr("src.pipeline.run_apply", mock_run_apply)

    stats = run_pipeline(
        cfg,
        test_db,
        profile,
        pages=2,
        headless=True,
        offline_score=True,
        execute=False,
        apply_limit=1,
    )

    assert stats.dry_run == 1
    assert len(applied_jobs) == 1
    assert applied_jobs[0]["jobstreet_id"] == "2001"


def test_cli_pipeline_command(tmp_path, monkeypatch):
    """Test CLI invocation of pipeline command via cmd_pipeline."""
    from src.run import cmd_pipeline
    import argparse

    cfg = {"search": {"base": "https://id.jobstreet.com", "roles": [], "locations": []}}
    monkeypatch.setattr("src.run.load_config", lambda: cfg)
    monkeypatch.setattr("src.run.load_profile", lambda: {})
    monkeypatch.setattr("src.run.DB_PATH", tmp_path / "test.db")

    called = False
    def mock_run_pipeline(*args, **kwargs):
        nonlocal called
        called = True
        from src.pipeline import PipelineStats
        return PipelineStats(pages_processed=1, cards_seen=10, scored=5, submitted=2)

    monkeypatch.setattr("src.pipeline.run_pipeline", mock_run_pipeline)

    args = argparse.Namespace(
        pages=1,
        headless=True,
        browser=False,
        roles=None,
        locations=None,
        cards_only=False,
        offline=True,
        execute=True,
        llm_letter=False,
        limit=5,
    )
    cmd_pipeline(args)
    assert called is True
