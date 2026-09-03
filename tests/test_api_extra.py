from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.db import connect, start_run, finish_run


@pytest.fixture
def env(tmp_path):
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "apply_bot.db"

    conn = connect(db_file)
    conn.close()

    (data_dir / "config.yaml").write_text("filters:\n  title_blacklist: []\nscoring:\n  match_threshold: 0.6\n", encoding="utf-8")
    (data_dir / "profile.yaml").write_text("name: Test User\nskills: []\n", encoding="utf-8")

    app = create_app(data_dir=data_dir, logs_dir=logs_dir)
    client = TestClient(app)
    return {
        "client": client,
        "data_dir": data_dir,
        "logs_dir": logs_dir,
        "db_file": db_file,
    }


def test_runs_api_lifecycle(env, monkeypatch):
    client = env["client"]
    db_file = env["db_file"]

    # Test list runs
    res = client.get("/api/runs")
    assert res.status_code == 200
    assert "runs" in res.json()

    # Mock runner start
    monkeypatch.setattr("src.api.runner.start", lambda db_path, logs_dir, argv: 42)
    monkeypatch.setattr("src.api.runner.status", lambda db_path, run_id: {"id": 42, "command": "pipeline", "alive": False} if run_id == 42 else {})
    monkeypatch.setattr("src.api.runner.log_tail", lambda logs_dir, run_id: "Sample log output")
    monkeypatch.setattr("src.api.runner.stop", lambda db_path, run_id: True)

    # Start run - valid
    start_payload = {
        "command": "pipeline",
        "pipeline_pages": 2,
        "pipeline_limit": 5,
        "pipeline_cards_only": True,
        "pipeline_offline": True,
        "pipeline_llm_letter": False,
        "pipeline_headless": True,
        "pipeline_execute": False,
    }
    start_res = client.post("/api/runs", json=start_payload)
    assert start_res.status_code == 200
    assert start_res.json()["run_id"] == 42

    # Start run - invalid command
    bad_res = client.post("/api/runs", json={"command": "nonexistent"})
    assert bad_res.status_code == 400

    # Get detail
    det_res = client.get("/api/runs/42")
    assert det_res.status_code == 200
    assert det_res.json()["run"]["id"] == 42
    assert "Sample log" in det_res.json()["log"]

    # 404 on not found
    assert client.get("/api/runs/999").status_code == 404

    # Cancel run
    cancel_res = client.post("/api/runs/42/cancel")
    assert cancel_res.status_code == 200
    assert client.post("/api/runs/999/cancel").status_code == 404

    # Tail run
    tail_res = client.get("/api/runs/42/tail")
    assert tail_res.status_code == 200
    assert tail_res.json()["log"] == "Sample log output"


def test_settings_sections_and_oauth_endpoints(env, monkeypatch):
    client = env["client"]

    # Save settings sections: roles_search, filters, scoring, salary, letter, llm
    assert client.post("/api/settings", json={"section": "roles_search", "data": {"roles": [{"name": "SWE", "slug": "swe"}]}}).status_code == 200
    assert client.post("/api/settings", json={"section": "filters", "data": {"max_years_experience": 2}}).status_code == 200
    assert client.post("/api/settings", json={"section": "scoring", "data": {"match_threshold": 0.7, "batch_size": 5}}).status_code == 200
    assert client.post("/api/settings", json={"section": "salary", "data": {"preferred": 15000000, "min_acceptable": 12000000}}).status_code == 200
    assert client.post("/api/settings", json={"section": "letter", "data": {"pitch": "Senior Dev", "custom_instructions": "Be brief"}}).status_code == 200
    assert client.post("/api/settings", json={"section": "llm", "data": {"provider": "openai", "model": "gpt-4o"}}).status_code == 200

    # Unknown section
    assert client.post("/api/settings", json={"section": "unknown", "data": {}}).status_code == 400

    # Test provider models endpoint
    monkeypatch.setattr("src.api.routers.settings.list_models_for_provider", lambda prov, cfg: [{"id": "gpt-4o", "label": "GPT-4o"}])
    models_res = client.get("/api/settings/models/copilot")
    assert models_res.status_code == 200
    assert len(models_res.json()["models"]) == 1

    # Test OAuth logins
    monkeypatch.setattr("src.api.routers.settings.start_claude_oauth", lambda: True)
    monkeypatch.setattr("src.api.routers.settings.start_codex_oauth", lambda: True)
    monkeypatch.setattr("src.api.routers.settings.start_gemini_oauth", lambda: True)
    assert client.post("/api/settings/oauth/claude/login").status_code == 200
    assert client.post("/api/settings/oauth/codex/login").status_code == 200
    assert client.post("/api/settings/oauth/gemini/login").status_code == 200
    assert client.post("/api/settings/oauth/invalid_prov/login").status_code == 400

    # OAuth logout
    assert client.post("/api/settings/oauth/claude/logout").status_code == 200

    # Copilot device code and polling
    monkeypatch.setattr("src.api.routers.settings.request_copilot_device_code", lambda: {
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "device_code": "dev-123",
        "interval": 5,
        "expires_in": 900,
    })
    dev_res = client.post("/api/settings/oauth/copilot/device-code")
    assert dev_res.status_code == 200
    assert dev_res.json()["user_code"] == "ABCD-1234"

    monkeypatch.setattr("src.api.routers.settings.poll_copilot_device_token", lambda dcode, **kw: True)
    poll_res = client.post("/api/settings/oauth/copilot/poll", json={"device_code": "dev-123", "interval": 5})
    assert poll_res.status_code == 200


def test_runner_module_helpers(tmp_path):
    from src.api import runner
    db_file = tmp_path / "runner_test.db"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_file)
    conn.close()

    # Log tail missing file
    assert runner.log_tail(logs_dir, 9999) == ""

    # Write a test log
    run_log = logs_dir / "runs" / "123.log"
    run_log.parent.mkdir(parents=True, exist_ok=True)
    run_log.write_text("Hello from runner log\nSecond line", encoding="utf-8")
    tail = runner.log_tail(logs_dir, 123, max_bytes=10)
    assert tail == "econd line"

    # Status of nonexistent run
    assert runner.status(db_file, 9999) == {}

def test_h3_runner_shutdown(tmp_path, monkeypatch):
    import os
    import time
    from unittest.mock import MagicMock
    from src.api import runner

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 99999
    runner._active[1] = mock_proc

    # Mock os.killpg and proc.terminate
    killed = []
    if hasattr(os, "killpg"):
        monkeypatch.setattr("os.killpg", lambda pgid, sig: killed.append((pgid, sig)))
    if hasattr(os, "getpgid"):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)

    runner.shutdown()

    assert mock_proc.terminate.called or len(killed) > 0
    assert len(runner._active) == 0


def test_runner_windows_shutdown_and_stop(tmp_path, monkeypatch):
    import subprocess
    import sys
    from unittest.mock import MagicMock
    from src.api import runner

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 88888
    runner._active[2] = mock_proc

    monkeypatch.setattr("src.api.runner.sys.platform", "win32")
    executed_cmds = []

    def mock_run(cmd, **kw):
        executed_cmds.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr("src.api.runner.subprocess.run", mock_run)

    # Re-trigger with creationflags mocked since CREATE_NO_WINDOW might not exist on macOS
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        monkeypatch.setattr("src.api.runner.subprocess.CREATE_NO_WINDOW", 0x08000000, raising=False)

    runner.shutdown()
    assert len(runner._active) == 0
    assert any("taskkill" in cmd[0] for cmd in executed_cmds)

    # Test stop on Windows
    runner._active[3] = mock_proc
    db_file = tmp_path / "test_stop.db"
    conn = connect(db_file)
    conn.close()
    runner.stop(db_file, 3)
    assert 3 not in runner._active

def test_h5_cv_upload_path_traversal_prevention(env, monkeypatch):
    client = env["client"]
    monkeypatch.setattr("src.api.routers.profile.extract_text_from_pdf", lambda b: "CV Text Content")
    monkeypatch.setattr("src.api.routers.profile.parse_cv_with_llm", lambda text, **kw: {"name": "Test Candidate"})

    traversal_filename = "../../evil_traversal.pdf"
    file_payload = {"file": (traversal_filename, b"%PDF-1.4 test dummy pdf content", "application/pdf")}
    res = client.post("/api/profile/import-cv", files=file_payload)
    assert res.status_code == 200

    # Ensure file was saved inside env["data_dir"] as evil_traversal.pdf, not outside
    assert (env["data_dir"] / "evil_traversal.pdf").exists()
    assert not (env["data_dir"].parent / "evil_traversal.pdf").exists()
