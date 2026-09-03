import json
from unittest.mock import MagicMock
import pytest

from src.score import (
    decide,
    run_filters,
    offline_score,
    _skill_vocab,
    build_prompt,
    _parse_verdicts,
    llm_score,
    score_pending,
)
from src.db import connect, upsert_job, find_job, latest_evaluations


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "score_test.db")
    yield conn
    conn.close()


CFG = {
    "filters": {
        "title_blacklist": ["senior", "lead", "manager", "intern"],
        "role_keywords": ["python", "developer", "engineer"],
        "min_years_experience": 1,
        "max_years_experience": 3,
        "company_cooldown_days": 14,
    },
    "scoring": {
        "match_threshold": 0.5,
        "batch_size": 2,
        "extra_skill_vocab": ["docker", "fastapi"],
    },
    "llm": {
        "provider": "openai-compatible",
        "model": "test-model",
        "base_url": "https://api.openai.com/v1",
        "api_key": "dummy",
    },
}

PROFILE = {
    "name": "Jane Doe",
    "skills": [
        {"name": "Python", "aliases": ["py", "python3"]},
        {"name": "SQL", "aliases": ["postgres", "postgresql"]},
    ],
}


def test_decide_logic():
    # Test max_years veto
    dec, reason = decide(80, 5, "junior", CFG)
    assert dec == "skip"
    assert "veto: requires 5 years" in reason

    # Test min_years veto
    dec, reason = decide(80, 0, "junior", CFG)
    assert dec == "skip"
    assert "veto: requires 0 years" in reason

    # Test seniority veto
    dec, reason = decide(80, 2, "senior", CFG)
    assert dec == "skip"
    assert "veto: seniority" in reason

    # Test no match signal
    dec, reason = decide(None, 2, "mid", CFG)
    assert dec == "skip"
    assert "no match signal" in reason

    # Test match below threshold (threshold is 50%)
    dec, reason = decide(40, 2, "mid", CFG)
    assert dec == "skip"
    assert "below 50% threshold" in reason

    # Test match >= threshold
    dec, reason = decide(75, 2, "mid", CFG)
    assert dec == "apply"
    assert "match 75% >= 50%" in reason


def test_offline_score_and_skill_vocab():
    vocab = _skill_vocab(PROFILE, CFG)
    assert vocab["python"] == "python"
    assert vocab["python3"] == "python"
    assert vocab["docker"] == "docker"

    # Perfect match job
    job_ok = {
        "title": "Junior Python Developer",
        "description": "Requires Python and SQL with 2 years of experience",
        "teaser": "Jakarta office",
    }
    res = offline_score(job_ok, PROFILE, CFG)
    assert res["decision"] == "apply"
    assert res["match_pct"] == 100
    assert res["seniority"] == "junior"
    assert res["years_required"] == 2
    assert "python" in json.loads(res["met"])

    # Unmet skill job
    job_docker = {
        "title": "Docker Infrastructure Engineer",
        "description": "Requires Docker and FastAPI. Experience 2 years",
    }
    res_docker = offline_score(job_docker, PROFILE, CFG)
    assert res_docker["decision"] == "skip"
    assert res_docker["match_pct"] == 0
    assert "docker" in json.loads(res_docker["unmet"])


def test_llm_score_parse_and_fallback(monkeypatch):
    jobs = [
        {"jobstreet_id": "1001", "title": "Python Dev", "company": "Co A", "location": "Jakarta"},
        {"jobstreet_id": "1002", "title": "Backend Dev", "company": "Co B", "location": "Jakarta"},
    ]

    # Malformed response parsing
    with pytest.raises(ValueError, match="no JSON array"):
        _parse_verdicts("No json here")

    # Mock complete with partial verdicts (only for 1001)
    mock_resp = json.dumps([
        {
            "job_id": "1001",
            "match_pct": 90,
            "years_required": 2,
            "seniority": "mid",
            "met": ["python"],
            "unmet": [],
            "reason": "Great candidate",
        }
    ])
    monkeypatch.setattr("src.score.complete", lambda msgs, cfg, **kwargs: mock_resp)

    verdicts = llm_score(jobs, "profile_yaml_str", CFG)
    assert len(verdicts) == 2
    assert verdicts[0]["decision"] == "apply"
    assert verdicts[0]["match_pct"] == 90
    # 1002 had no verdict
    assert verdicts[1]["decision"] == "review"
    assert "LLM returned no verdict" in verdicts[1]["reason"]


def test_score_pending_offline_and_llm(db, monkeypatch):
    j1 = upsert_job(db, {
        "jobstreet_id": "sp-1",
        "title": "Python Developer",
        "company": "Company A",
        "location": "Jakarta",
        "description": "Junior python dev 2 years experience with Python and SQL",
    })
    j2 = upsert_job(db, {
        "jobstreet_id": "sp-2",
        "title": "Lead Software Architect",
        "company": "Company B",
        "location": "Jakarta",
        "description": "10 years experience",
    })

    # Test run_filters
    survivors, n_skipped = run_filters(CFG, db)
    assert n_skipped == 1  # j2 has blacklisted "Lead"
    assert len(survivors) == 1
    assert survivors[0]["id"] == j1

    # Offline scoring orchestration
    res = score_pending(CFG, db, PROFILE, offline=True)
    assert res["filtered"] == 0  # j2 already evaluated as skip, none new skipped
    assert res["scored"] == 1

    # LLM scoring orchestration with exception fallback
    j3 = upsert_job(db, {
        "jobstreet_id": "sp-3",
        "title": "Python Engineer",
        "company": "Company C",
        "location": "Jakarta",
        "description": "Python dev",
    })

    def mock_broken_complete(*args, **kwargs):
        raise ConnectionError("Network down")

    monkeypatch.setattr("src.score.complete", mock_broken_complete)

    llm_res = score_pending(CFG, db, PROFILE, offline=False)
    assert llm_res["scored"] == 1
    evals = latest_evaluations(db)
    j3_eval = next(e for e in evals if e["job_id"] == j3)
    assert j3_eval["decision"] == "review"
    assert "Network down" in j3_eval["reason"]

def test_m2_seniority_word_boundaries():
    # "Internal Audit Data Analyst" must NOT be detected as "intern"
    res1 = offline_score({
        "title": "Internal Audit Data Analyst",
        "description": "Requires Python. 2 years experience.",
    }, PROFILE, CFG)
    assert res1["seniority"] != "intern"

    # "Leadership Development" must NOT be detected as "senior"
    res2 = offline_score({
        "title": "Leadership Development Associate",
        "description": "Requires Python. 2 years experience.",
    }, PROFILE, CFG)
    assert res2["seniority"] != "senior"

    # Exact keywords should still be detected
    res3 = offline_score({
        "title": "Data Analyst Intern",
        "description": "Requires Python. 0 years experience.",
    }, PROFILE, CFG)
    assert res3["seniority"] == "intern"

    res4 = offline_score({
        "title": "Lead Python Developer",
        "description": "Requires Python. 2 years experience.",
    }, PROFILE, CFG)
    assert res4["seniority"] == "senior"

def test_m8_parse_verdicts_with_bracketed_preamble():
    text_with_preamble = """Thinking [step 1: checking job criteria]
Here is the JSON evaluation:
[
  {
    "job_id": "1001",
    "match_pct": 95,
    "years_required": 1,
    "seniority": "junior",
    "met": ["python"],
    "unmet": [],
    "reason": "Great match"
  }
]
Hope this helps!"""
    verdicts = _parse_verdicts(text_with_preamble)
    assert len(verdicts) == 1
    assert verdicts[0]["job_id"] == "1001"
    assert verdicts[0]["match_pct"] == 95


def test_score_unicode_characters_and_windows_encodings(db):
    """Ensure titles, companies, reasons with fullwidth/non-ASCII characters don't crash."""
    unicode_title = "Python Engineer （Bekasi） \uff08Fullwidth\uff09"
    unicode_company = "PT Teknologi Maju 🌟"
    j = upsert_job(db, {
        "jobstreet_id": "sp-unicode-1",
        "title": unicode_title,
        "company": unicode_company,
        "location": "Jakarta",
        "description": "Junior engineer with Python and 2 years experience",
    })
    res = score_pending(CFG, db, PROFILE, offline=True)
    assert res["scored"] == 1
    evals = latest_evaluations(db)
    ev = next(e for e in evals if e["job_id"] == j)
    assert ev["title"] == unicode_title
    assert ev["company"] == unicode_company
