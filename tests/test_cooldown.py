from datetime import date
from src import db
from src.apply import run_apply
from src.score import score_pending


def test_company_cooldown_filter_and_apply_protection(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "test_cooldown.db")
    cfg = {
        "filters": {
            "title_blacklist": [],
            "role_keywords": ["engineer"],
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

    # First job from PT Alpha
    job1_id = db.upsert_job(conn, {
        "jobstreet_id": "111",
        "title": "Software Engineer",
        "company": "PT Alpha Tech",
        "location": "Jakarta",
        "description": "Python required",
    })
    # Mark job 1 as applied today
    db.insert_application(conn, job1_id, {
        "applied_at": date.today().isoformat(),
    })

    # Second job from the same company (PT Alpha Tech)
    job2_id = db.upsert_job(conn, {
        "jobstreet_id": "222",
        "title": "Data Engineer",
        "company": "PT Alpha Tech",
        "location": "Jakarta",
        "description": "Python required",
    })

    # Scoring pass should filter out job 2 due to company cooldown
    res = score_pending(cfg, conn, profile, offline=True, jobs=[{"id": job2_id, "jobstreet_id": "222", "title": "Data Engineer", "company": "PT Alpha Tech", "location": "Jakarta", "description": "Python required"}])
    assert res["filtered"] == 1
    assert res["scored"] == 0

    # Verify latest evaluation in DB is skip due to cooldown
    latest = db.latest_evaluations(conn, decision="skip")
    assert any("company applied within 28d cooldown" in row["reason"] for row in latest)

    # Even if forcefully passed to run_apply, run_apply checks company_in_cooldown
    app_res = run_apply(cfg, conn, profile, execute=False, use_llm_letter=False, limit=10, headless=True, jobs=[{"id": job2_id, "jobstreet_id": "222", "title": "Data Engineer", "company": "PT Alpha Tech"}])
    assert app_res["skipped"] == 1
    assert app_res["dry-run"] == 0
    assert app_res["submitted"] == 0


def test_company_cooldown_disabled_when_zero(tmp_path):
    conn = db.connect(tmp_path / "test_zero_cooldown.db")
    cfg = {
        "filters": {
            "title_blacklist": [],
            "role_keywords": ["engineer"],
            "max_years_experience": 1,
            "company_cooldown_days": 0,  # Disabled
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

    job1_id = db.upsert_job(conn, {
        "jobstreet_id": "111",
        "title": "Software Engineer",
        "company": "PT Alpha Tech",
        "location": "Jakarta",
        "description": "Python required",
    })
    db.insert_application(conn, job1_id, {
        "applied_at": date.today().isoformat(),
    })

    job2_id = db.upsert_job(conn, {
        "jobstreet_id": "222",
        "title": "Data Engineer",
        "company": "PT Alpha Tech",
        "location": "Jakarta",
        "description": "Python required",
    })

    # With cooldown=0, job 2 should NOT be filtered out by company cooldown
    res = score_pending(cfg, conn, profile, offline=True, jobs=[{"id": job2_id, "jobstreet_id": "222", "title": "Data Engineer", "company": "PT Alpha Tech", "location": "Jakarta", "description": "Python required"}])
    assert res["filtered"] == 0
    assert res["scored"] == 1
    assert db.company_in_cooldown(conn, "alpha tech", 0) is False
