"""Tests for FastAPI backend API endpoints."""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import yaml
from fastapi.testclient import TestClient

from src import db
from src.api import runner
from src.api.main import create_app

REAL_DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture()
def env(tmp_path):
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    data_dir.mkdir()
    logs_dir.mkdir()
    for name in ("config.yaml", "profile.yaml"):
        src_path = REAL_DATA / name
        if not src_path.exists() and name == "profile.yaml":
            src_path = REAL_DATA / "profile.example.yaml"
        shutil.copy(src_path, data_dir / name)
    runner._active.clear()
    runner._started.clear()
    yield SimpleNamespace(
        data_dir=data_dir, logs_dir=logs_dir, db_path=data_dir / "jobs.db"
    )
    runner._active.clear()
    runner._started.clear()


@pytest.fixture()
def client(env):
    app = create_app(data_dir=env.data_dir, logs_dir=env.logs_dir)
    with TestClient(app) as c:
        yield c


def seed_job(
    env,
    jobstreet_id="80000001",
    title="Data Analyst",
    company="PT Contoh",
    decision=None,
    applied=False,
    is_external=0,
):
    conn = db.connect(env.db_path)
    try:
        job_id = db.upsert_job(
            conn,
            {
                "jobstreet_id": jobstreet_id,
                "title": title,
                "company": company,
                "location": "Jakarta",
                "url": f"https://id.jobstreet.com/id/job/{jobstreet_id}",
                "is_external": is_external,
            },
        )
        if decision:
            db.insert_evaluation(
                conn,
                job_id,
                {
                    "model": "rules-v1",
                    "decision": decision,
                    "match_pct": 70,
                    "reason": "seeded",
                },
            )
        if applied:
            db.insert_application(
                conn, job_id, {"applied_at": date.today().isoformat()}
            )
        return job_id
    finally:
        conn.close()


def test_dashboard_endpoint(client, env):
    seed_job(env, decision="apply")
    seed_job(env, jobstreet_id="80000002", title="ML Engineer", decision="review")
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["total_jobs"] == 2
    assert data["apply_queue"] == 1
    assert data["counts"]["apply"] == 1
    assert data["counts"]["review"] == 1


def test_jobs_list_and_filter(client, env):
    seed_job(env, jobstreet_id="80000001", title="Backend Dev", decision="apply")
    seed_job(env, jobstreet_id="80000002", title="Frontend Dev", decision="skip")

    res = client.get("/api/jobs")
    assert res.status_code == 200
    assert res.json()["total"] == 2

    res_apply = client.get("/api/jobs?decision=apply")
    assert res_apply.json()["total"] == 1
    assert res_apply.json()["jobs"][0]["title"] == "Backend Dev"

    res_q = client.get("/api/jobs?q=Frontend")
    assert res_q.json()["total"] == 1
    assert res_q.json()["jobs"][0]["title"] == "Frontend Dev"


def test_jobs_list_is_external_filter(client, env):
    seed_job(env, jobstreet_id="80000001", title="Direct Job", decision="apply", is_external=0)
    seed_job(env, jobstreet_id="80000002", title="External Job", decision="apply", is_external=1)

    res_all = client.get("/api/jobs")
    assert res_all.json()["total"] == 2

    res_ext = client.get("/api/jobs?is_external=true")
    assert res_ext.json()["total"] == 1
    assert res_ext.json()["jobs"][0]["title"] == "External Job"
    assert res_ext.json()["jobs"][0]["is_external"] == 1

    res_direct = client.get("/api/jobs?is_external=false")
    assert res_direct.json()["total"] == 1
    assert res_direct.json()["jobs"][0]["title"] == "Direct Job"
    assert res_direct.json()["jobs"][0]["is_external"] == 0


def test_decide_job(client, env):
    seed_job(env, jobstreet_id="80000003", title="Data Engineer", decision="review")
    res = client.post(
        "/api/jobs/80000003/decide",
        json={"decision": "apply", "reason": "approved in API test"},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Bad decision
    res_bad = client.post("/api/jobs/80000003/decide", json={"decision": "invalid"})
    assert res_bad.status_code == 400

    # Nonexistent job
    res_404 = client.post("/api/jobs/nonexistent/decide", json={"decision": "apply"})
    assert res_404.status_code == 404


def test_applications_endpoint(client, env):
    seed_job(env, applied=True)
    res = client.get("/api/applications")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["apps"]) == 1
    assert data["apps"][0]["title"] == "Data Analyst"
    app_id = data["apps"][0]["id"]

    # Patch status
    res_patch = client.patch(
        f"/api/applications/{app_id}/status",
        json={"status": "Process"},
    )
    assert res_patch.status_code == 200

    # Check updated status
    res_updated = client.get("/api/applications")
    assert res_updated.json()["apps"][0]["status"] == "Process"



def test_profile_read_and_save(client, env):
    res = client.get("/api/profile")
    assert res.status_code == 200
    data = res.json()
    assert "profile" in data
    assert "raw" in data

    save_payload = {
        "name": "Jane API Tester",
        "location": "Jakarta, Indonesia",
        "work_rights": "Indonesian citizen",
        "cv_file": "Jane_CV.pdf",
        "years_experience": 2,
        "languages": ["Indonesian", "English"],
        "locations_ok": ["Jakarta", "Remote"],
        "education": {
            "degree": "B.Sc.",
            "university": "UI",
            "period": "2020-2024",
            "gpa": "3.8",
        },
        "experience": [{"role": "Engineer", "org": "Acme", "period": "2024", "summary": "Built APIs"}],
        "skills": ["python", "fastapi"],
        "projects": ["Apply-Bot API"],
        "salary": {"preferred": 8000000, "min_acceptable": 7000000},
        "salary_expectation": "7M-8M IDR",
        "letter": {"pitch": "Python fullstack"},
    }
    save_res = client.post("/api/profile", json=save_payload)
    assert save_res.status_code == 200
    assert save_res.json()["success"] is True

    saved = yaml.safe_load((env.data_dir / "profile.yaml").read_text(encoding="utf-8"))
    assert saved["name"] == "Jane API Tester"
    assert saved["years_experience"] == 2


def test_settings_read_and_save(client, env):
    res = client.get("/api/settings")
    assert res.status_code == 200
    assert "active_llm" in res.json()

    # Save LLM
    llm_payload = {
        "section": "llm",
        "data": {
            "provider": "openai",
            "endpoint": "https://api.test.com/v1",
            "model": "gpt-4o",
            "api_key": "sk-test",
        },
    }
    save_res = client.post("/api/settings", json=llm_payload)
    assert save_res.status_code == 200

    # Save filters
    filter_payload = {
        "section": "filters",
        "data": {
            "company_cooldown_days": 14,
            "max_years_experience": 2,
            "location_whitelist": ["jakarta", "remote"],
        },
    }
    save_filters = client.post("/api/settings", json=filter_payload)
    assert save_filters.status_code == 200


def test_test_llm_endpoint(client, env):
    with mock.patch("src.api.routers.settings.complete", return_value="LLM connection successful!"):
        res = client.post("/api/settings/test-llm")
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert res.json()["response"] == "LLM connection successful!"


def test_jobstreet_auth_endpoints(client, env):
    storage_file = env.data_dir / "storage_state.json"
    storage_file.write_text('{"cookies": []}', encoding="utf-8")
    assert storage_file.exists()

    res = client.get("/api/settings")
    assert res.status_code == 200
    assert res.json()["has_auth"] is True

    del_res = client.delete("/api/settings/jobstreet/auth")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True
    assert not storage_file.exists()

    res_after = client.get("/api/settings")
    assert res_after.status_code == 200
    assert res_after.json()["has_auth"] is False


def test_profile_import_cv_endpoint(client, env):
    # Non-pdf rejected
    res_bad = client.post(
        "/api/profile/import-cv",
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )
    assert res_bad.status_code == 400

    # Mock extract_text_from_pdf and parse_cv_with_llm
    mock_profile = {
        "name": "Jane Imported",
        "location": "Bandung, Indonesia",
        "work_rights": "Citizen",
        "cv_file": "my_cv.pdf",
        "years_experience": 1.5,
        "languages": ["English", "Indonesian"],
        "locations_ok": ["Bandung", "Remote"],
        "education": {
            "degree": "B.Sc. IT",
            "university": "ITB",
            "period": "2020-2024",
            "gpa": "3.90/4.00",
            "certifications": [],
        },
        "experience": [],
        "skills": [{"name": "python", "aliases": ["python3"]}],
        "projects": ["Web scraper project"],
        "salary": {"preferred": 9000000, "min_acceptable": 7500000},
        "salary_expectation": "7.5M-9M IDR",
        "letter": {"pitch": "Python developer", "middles": {}},
    }

    with mock.patch("src.api.routers.profile.extract_text_from_pdf", return_value="Dummy PDF text content"), \
         mock.patch("src.api.routers.profile.parse_cv_with_llm", return_value=mock_profile):
        res = client.post(
            "/api/profile/import-cv",
            files={"file": ("my_cv.pdf", b"%PDF-1.4 dummy binary content", "application/pdf")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["profile"]["name"] == "Jane Imported"
        assert data["profile"]["years_experience"] == 1.5
        assert "Dummy PDF text content" in data["extracted_text_preview"]


def test_delete_all_data_endpoint(client, env):
    # Setup profile.yaml and dummy records in database
    profile_file = env.data_dir / "profile.yaml"
    profile_file.write_text("name: Candidate To Delete\n", encoding="utf-8")
    assert profile_file.exists()

    conn = db.connect(env.db_path)
    db.upsert_job(conn, {"jobstreet_id": "job-del-123", "title": "Software Engineer"})
    assert db.count_jobs(conn) == 1
    conn.close()

    # Call delete all data endpoint
    res = client.delete("/api/settings/all-data")
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Check profile.yaml is deleted
    assert not profile_file.exists()

    # Check db is reset and empty
    conn_after = db.connect(env.db_path)
    assert db.count_jobs(conn_after) == 0
    conn_after.close()


