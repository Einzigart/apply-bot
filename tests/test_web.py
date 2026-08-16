"""Web UI tests.

Each test gets throwaway data/logs dirs passed straight to create_app();
runner.start() forwards those dirs to CLI subprocesses via env vars, so
the end-to-end run test never touches the real data/ directory.
"""
from __future__ import annotations

import shutil
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from src import db
from src.web import runner
from src.web.app import create_app

REAL_DATA = Path(__file__).resolve().parent.parent / "data"
YAMLS = ("config.yaml", "profile.yaml")


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
    yield SimpleNamespace(data_dir=data_dir, logs_dir=logs_dir,
                          db_path=data_dir / "jobs.db")
    runner._active.clear()
    runner._started.clear()


@pytest.fixture()
def client(env):
    app = create_app(data_dir=env.data_dir, logs_dir=env.logs_dir)
    app.testing = True
    with app.test_client() as c:
        yield c


def seed_job(env, jobstreet_id="80000001", title="Data Analyst",
             company="PT Contoh", decision=None, applied=False):
    conn = db.connect(env.db_path)
    try:
        job_id = db.upsert_job(conn, {
            "jobstreet_id": jobstreet_id, "title": title, "company": company,
            "location": "Jakarta",
            "url": f"https://id.jobstreet.com/id/job/{jobstreet_id}",
        })
        if decision:
            db.insert_evaluation(conn, job_id, {
                "model": "rules-v1", "decision": decision,
                "match_pct": 70, "reason": "seeded",
            })
        if applied:
            db.insert_application(conn, job_id,
                                  {"applied_at": date.today().isoformat()})
        return job_id
    finally:
        conn.close()


# --- pages ------------------------------------------------------------------

def test_pages_render(client, env):
    seed_job(env, decision="apply")
    seed_job(env, jobstreet_id="80000002", title="ML Engineer",
             company="PT Dua", decision="review")
    for path in ("/", "/jobs", "/applications", "/runs", "/profile"):
        assert client.get(path).status_code == 200, path


def test_profile_page_shows_candidate(client, env):
    prof = yaml.safe_load((env.data_dir / "profile.yaml").read_text(encoding="utf-8"))
    body = client.get("/profile").get_data(as_text=True)
    assert prof["name"] in body


def test_profile_page_lists_saved_answers(client, env):
    conn = db.connect(env.db_path)
    try:
        db.add_answer(conn, "notice period", "Immediately")
    finally:
        conn.close()
    body = client.get("/profile").get_data(as_text=True)
    assert "notice period" in body and "Immediately" in body


def test_jobs_filters(client, env):
    seed_job(env, decision="apply")
    seed_job(env, jobstreet_id="80000002", title="ML Engineer",
             company="PT Dua", decision="skip")

    body = client.get("/jobs?decision=apply").get_data(as_text=True)
    assert "Data Analyst" in body and "ML Engineer" not in body

    body = client.get("/jobs?q=Dua").get_data(as_text=True)
    assert "ML Engineer" in body and "Data Analyst" not in body

    body = client.get("/jobs?decision=unevaluated").get_data(as_text=True)
    assert "no jobs match" in body


def test_jobs_sorting(client, env):
    seed_job(env, jobstreet_id="80000001", title="Backend Engineer",
             company="Alpha Corp", decision="apply")
    seed_job(env, jobstreet_id="80000002", title="Frontend Engineer",
             company="Beta Corp", decision="skip")

    res_asc = client.get("/jobs?sort=title&order=asc").get_data(as_text=True)
    assert res_asc.index("Backend Engineer") < res_asc.index("Frontend Engineer")

    res_desc = client.get("/jobs?sort=title&order=desc").get_data(as_text=True)
    assert res_desc.index("Frontend Engineer") < res_desc.index("Backend Engineer")


def test_decide_job_via_web(client, env):
    seed_job(env, jobstreet_id="80000003", title="Backend Dev",
             company="PT Tiga", decision="review")

    res = client.post("/jobs/80000003/decide",
                      data={"decision": "apply", "reason": "approved in web"})
    assert res.status_code == 302

    conn = db.connect(env.db_path)
    try:
        latest = db.latest_evaluations(conn)[0]
        assert latest["title"] == "Backend Dev"
        assert latest["decision"] == "apply"
        assert latest["model"] == "human"
    finally:
        conn.close()


def test_decide_job_bad_input(client, env):
    seed_job(env, jobstreet_id="80000004", title="Frontend Dev",
             company="PT Empat")
    assert client.post("/jobs/80000004/decide", data={"decision": "invalid"}).status_code == 400
    assert client.post("/jobs/nonexistent/decide", data={"decision": "apply"}).status_code == 404


def test_applications_page_lists_history(client, env):
    seed_job(env, decision="apply", applied=True)
    body = client.get("/applications").get_data(as_text=True)
    assert "PT Contoh" in body


def test_run_detail_unknown_id_404s(client):
    assert client.get("/runs/999").status_code == 404


# --- run triggering ---------------------------------------------------------

def test_start_run_rejects_bad_input(client):
    assert client.post("/runs", data={"command": "rm -rf /"}).status_code == 400
    assert client.post("/runs", data={"command": "discover",
                                      "discover_pages": "two"}).status_code == 400


def test_start_run_refuses_when_busy(client, env):
    class FakeAliveProc:
        def poll(self):
            return None

    runner._active[999] = FakeAliveProc()
    res = client.post("/runs", data={"command": "calibrate"},
                      follow_redirects=True)
    assert b"already in progress" in res.data


def test_run_score_offline_end_to_end(client, env):
    """POST /runs spawns the real CLI; it must finish, log, and record."""
    res = client.post("/runs", data={"command": "score", "score_offline": "on"})
    assert res.status_code == 302
    run_id = int(res.headers["Location"].rstrip("/").rsplit("/", 1)[-1])

    deadline = time.time() + 60
    while time.time() < deadline:
        data = client.get(f"/runs/{run_id}/tail").get_json()
        if data["finished"]:
            break
        time.sleep(0.3)
    else:
        pytest.fail("run did not finish within 60s")

    assert data["notes"] == "ok"
    assert "scored: 0" in data["log"]
    assert (env.logs_dir / "runs" / f"{run_id}.log").exists()

    conn = db.connect(env.db_path)
    try:
        row = db.get_run(conn, run_id)
    finally:
        conn.close()
    assert row["command"] == "src.run score --offline"
    assert row["finished_at"] is not None


def test_run_pipeline_offline_web_form(client, env, monkeypatch):
    """POST /runs with pipeline command translates args correctly."""
    form_data = {
        "command": "pipeline",
        "pipeline_pages": "1",
        "pipeline_offline": "on",
        "pipeline_cards_only": "on",
        "pipeline_headless": "on",
    }
    argv = runner._argv_for_test = None
    orig_start = runner.start

    def mock_start(db_path, logs_dir, argv):
        runner._argv_for_test = argv
        return orig_start(db_path, logs_dir, ["score", "--offline"])

    monkeypatch.setattr(runner, "start", mock_start)
    res = client.post("/runs", data=form_data)
    assert res.status_code == 302
    assert runner._argv_for_test == [
        "pipeline",
        "--pages",
        "1",
        "--cards-only",
        "--offline",
        "--headless",
    ]


def test_cancel_run_endpoint(client, env):
    conn = db.connect(env.db_path)
    try:
        run_id = db.start_run(conn, "src.run score")
    finally:
        conn.close()

    res = client.post(f"/runs/{run_id}/cancel", follow_redirects=True)
    assert res.status_code == 200
    assert b"cancelled" in res.data

    conn = db.connect(env.db_path)
    try:
        row = db.get_run(conn, run_id)
        assert row["finished_at"] is not None
        assert "cancelled" in row["notes"]
    finally:
        conn.close()


# --- settings page -----------------------------------------------------------

def test_settings_page_and_save(client, env):
    res = client.get("/settings")
    assert res.status_code == 200
    assert b"LLM / AI Model Provider Selector" in res.data
    assert b"API Endpoint / Base URL" in res.data
    assert b"Jobstreet Authentication" in res.data

    post_data = {
        "section": "llm",
        "provider": "openai",
        "endpoint": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "prefix": "groq/",
        "api_key": "gsk-test-123",
    }
    post_res = client.post("/settings", data=post_data, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"LLM settings saved" in post_res.data

    import yaml
    sec_cfg = yaml.safe_load((env.data_dir / "secrets.yaml").read_text(encoding="utf-8"))
    assert sec_cfg["llm"]["provider"] == "openai"
    assert sec_cfg["llm"]["endpoint"] == "https://api.groq.com/openai/v1"
    assert sec_cfg["llm"]["model"] == "llama-3.3-70b-versatile"
    assert sec_cfg["llm"]["prefix"] == "groq/"
    assert sec_cfg["llm"]["api_key"] == "gsk-test-123"

    # Test saving filter settings (company cooldown, max years, location)
    post_filter = {
        "section": "filters",
        "company_cooldown_days": "0",
        "max_years_experience": "2",
        "location_whitelist": "jakarta, bandung",
        "role_keywords": "data, ml",
        "title_blacklist": "intern, senior",
    }
    post_res = client.post("/settings", data=post_filter, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"settings saved" in post_res.data.lower()
    sec_cfg = yaml.safe_load((env.data_dir / "secrets.yaml").read_text(encoding="utf-8"))
    assert sec_cfg["filters"]["company_cooldown_days"] == 0
    assert sec_cfg["filters"]["max_years_experience"] == 2
    assert sec_cfg["filters"]["location_whitelist"] == ["jakarta", "bandung"]

    # Test saving scoring threshold settings
    post_scoring = {
        "section": "scoring",
        "match_threshold": "75",
    }
    post_res = client.post("/settings", data=post_scoring, follow_redirects=True)
    assert post_res.status_code == 200
    sec_cfg = yaml.safe_load((env.data_dir / "secrets.yaml").read_text(encoding="utf-8"))
    assert sec_cfg["scoring"]["match_threshold"] == 0.75

    # Test saving salary preferences
    post_salary = {
        "section": "salary",
        "preferred_salary": "8,000,000",
        "min_acceptable_salary": "6500000",
    }
    post_res = client.post("/settings", data=post_salary, follow_redirects=True)
    assert post_res.status_code == 200
    prof_data = yaml.safe_load((env.data_dir / "profile.yaml").read_text(encoding="utf-8"))
    assert prof_data["salary"]["preferred"] == 8000000
    assert prof_data["salary"]["min_acceptable"] == 6500000


def test_test_llm_action(client, env, monkeypatch):
    import unittest.mock as mock
    with mock.patch("src.web.app.complete", return_value="LLM connection successful!"):
        res = client.post("/settings/test-llm")
        assert res.status_code == 200
        json_data = res.get_json()
        assert json_data["success"] is True
        assert json_data["response"] == "LLM connection successful!"


# --- runs table helpers -----------------------------------------------------

def test_runs_recording_helpers(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        run_id = db.start_run(conn, "src.run score")
        assert db.get_run(conn, run_id)["finished_at"] is None
        db.finish_run(conn, run_id, "ok")
        assert db.get_run(conn, run_id)["notes"] == "ok"
        # closed rows are not stamped again
        assert db.finish_run_if_open(conn, run_id, "late") is False
        assert db.get_run(conn, run_id)["notes"] == "ok"

        open_id = db.start_run(conn, "src.run discover")
        assert db.mark_interrupted_runs(conn) == 1
        assert "interrupted" in db.get_run(conn, open_id)["notes"]
    finally:
        conn.close()
