"""Tests for database and configuration backup export and import endpoints."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import yaml
from fastapi.testclient import TestClient

from src import db
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
        if not src_path.exists():
            example_name = name.replace(".yaml", ".example.yaml")
            src_path = REAL_DATA / example_name
        shutil.copy(src_path, data_dir / name)
    yield SimpleNamespace(
        data_dir=data_dir, logs_dir=logs_dir, db_path=data_dir / "jobs.db"
    )


@pytest.fixture()
def client(env):
    app = create_app(data_dir=env.data_dir, logs_dir=env.logs_dir)
    with TestClient(app) as c:
        yield c


def test_export_and_import_backup_roundtrip(client, env):
    # 1. Seed database records
    conn = db.connect(env.db_path)
    try:
        job_id = db.upsert_job(
            conn,
            {
                "jobstreet_id": "99001122",
                "title": "Lead Software Engineer",
                "company": "PT Tech Global",
                "location": "Jakarta",
                "url": "https://id.jobstreet.com/id/job/99001122",
                "is_external": 0,
            },
        )
        db.insert_evaluation(
            conn,
            job_id,
            {
                "model": "gpt-4o-mini",
                "decision": "apply",
                "match_pct": 85,
                "reason": "Strong match",
            },
        )
        db.insert_application(
            conn,
            job_id,
            {
                "applied_at": "2026-08-19",
                "salary_entered": "15000000",
                "status": "Submitted",
            },
        )
        run_id = db.start_run(conn, "pipeline --pages 2")
        db.finish_run(conn, run_id, "Completed normally")
        db.add_answer(conn, "Notice period", "1 month")
    finally:
        conn.close()

    # 2. Seed profile and auth tokens
    profile_path = env.data_dir / "profile.yaml"
    profile_data = {
        "name": "Farid Developer",
        "location": "Jakarta, Indonesia",
        "years_experience": 4,
        "skills": ["python", "react"],
    }
    profile_path.write_text(yaml.safe_dump(profile_data), encoding="utf-8")

    tokens_path = env.data_dir / "auth_tokens.json"
    tokens_data = {
        "claude": {"access_token": "token-123", "expires_at": 9999999999},
    }
    tokens_path.write_text(json.dumps(tokens_data), encoding="utf-8")

    # 3. Call Export Endpoint
    export_res = client.get("/api/settings/backup/export")
    assert export_res.status_code == 200
    assert "attachment; filename=" in export_res.headers.get("content-disposition", "")

    backup_payload = export_res.json()
    assert backup_payload["app"] == "apply-bot"
    assert backup_payload["version"] == "1.0"
    assert backup_payload["data"]["profile"]["name"] == "Farid Developer"
    assert backup_payload["data"]["auth_tokens"]["claude"]["access_token"] == "token-123"

    db_dump = backup_payload["data"]["database"]
    assert len(db_dump["jobs"]) == 1
    assert db_dump["jobs"][0]["jobstreet_id"] == "99001122"
    assert len(db_dump["evaluations"]) == 1
    assert len(db_dump["applications"]) == 1
    assert len(db_dump["runs"]) == 1
    assert len(db_dump["answers"]) == 1
    assert db_dump["answers"][0]["match"] == "Notice period"

    # 4. Wipe local environment to simulate new/clean machine
    db.reset_database(env.db_path)
    profile_path.write_text("name: Temporary Person\n", encoding="utf-8")
    tokens_path.write_text("{}", encoding="utf-8")

    conn_check = db.connect(env.db_path)
    assert db.count_jobs(conn_check) == 0
    conn_check.close()

    # 5. Call Import Endpoint with exported payload
    import_bytes = json.dumps(backup_payload).encode("utf-8")
    import_res = client.post(
        "/api/settings/backup/import",
        files={"file": ("my-backup.json", import_bytes, "application/json")},
    )
    assert import_res.status_code == 200
    res_data = import_res.json()
    assert res_data["success"] is True
    assert res_data["summary"]["profile_name"] == "Farid Developer"
    assert res_data["summary"]["jobs_count"] == 1
    assert res_data["summary"]["evaluations_count"] == 1
    assert res_data["summary"]["applications_count"] == 1
    assert res_data["summary"]["runs_count"] == 1
    assert res_data["summary"]["answers_count"] == 1

    # 6. Verify restored files and SQLite state
    restored_profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert restored_profile["name"] == "Farid Developer"
    assert restored_profile["years_experience"] == 4

    restored_tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    assert restored_tokens["claude"]["access_token"] == "token-123"

    conn_restored = db.connect(env.db_path)
    try:
        assert db.count_jobs(conn_restored) == 1
        jobs = db.jobs_with_latest_eval(conn_restored)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Lead Software Engineer"
        assert jobs[0]["decision"] == "apply"
        assert jobs[0]["match_pct"] == 85

        apps = db.list_applications(conn_restored)
        assert len(apps) == 1
        assert apps[0]["status"] == "Submitted"

        answers = db.list_answers(conn_restored)
        assert len(answers) == 1
        assert answers[0]["match"] == "Notice period"
    finally:
        conn_restored.close()


def test_import_backup_validation(client, env):
    # Reject non-json file
    res_txt = client.post(
        "/api/settings/backup/import",
        files={"file": ("backup.txt", b"plain text", "text/plain")},
    )
    assert res_txt.status_code == 400

    # Reject invalid json format
    res_invalid = client.post(
        "/api/settings/backup/import",
        files={"file": ("backup.json", b'{"app": "other-app"}', "application/json")},
    )
    assert res_invalid.status_code == 400
