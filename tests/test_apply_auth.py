from unittest.mock import MagicMock, patch

from src.apply import run_apply


def test_run_apply_handles_sqlite3_rows(tmp_path, monkeypatch):
    import sqlite3
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE jobs (id INTEGER PRIMARY KEY, jobstreet_id TEXT, title TEXT, company TEXT, company_norm TEXT, url TEXT, is_external INTEGER DEFAULT 0);
        CREATE TABLE evaluations (id INTEGER PRIMARY KEY, job_id INTEGER, model TEXT, decision TEXT, match_pct INTEGER, reason TEXT, scored_at TEXT);
        CREATE TABLE applications (id INTEGER PRIMARY KEY, job_id INTEGER, applied_at TEXT, salary_entered INTEGER, cover_letter TEXT, confirmation TEXT, status TEXT);
        CREATE TABLE answers (id INTEGER PRIMARY KEY, match TEXT, answer TEXT, created_at TEXT);
    """)
    conn.execute("INSERT INTO jobs (id, jobstreet_id, title, company, company_norm, url) VALUES (1, '123', 'Backend Dev', 'PT Test', 'pt test', 'https://jobstreet.com/job/123')")
    conn.execute("INSERT INTO evaluations (job_id, model, decision, match_pct, reason) VALUES (1, 'human', 'apply', 90, 'good match')")
    conn.commit()

    monkeypatch.setattr(
        "src.apply.apply_to_job",
        lambda *args, **kwargs: {
            "status": "dry-run",
            "salary": 7000000,
            "letter": "test",
            "screenshot": "shot.png",
        },
    )

    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_playwright.__enter__.return_value.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.pages = [mock_page]

    cfg = {"filters": {"company_cooldown_days": 28}}
    profile = {"salary": {"min_acceptable": 6000000, "preferred": 7000000}}

    with patch("playwright.sync_api.sync_playwright", return_value=mock_playwright):
        res = run_apply(
            cfg,
            conn,
            profile,
            execute=False,
            use_llm_letter=False,
            limit=1,
            headless=True,
        )

    assert res["dry-run"] == 1


def test_run_apply_loads_storage_state_when_present(tmp_path, monkeypatch):
    storage_file = tmp_path / "storage_state.json"
    storage_file.write_text('{"cookies": []}')
    monkeypatch.setattr("src.apply.STORAGE_STATE_PATH", storage_file)
    monkeypatch.setattr("src.scrape.STORAGE_STATE_PATH", storage_file)
    monkeypatch.setattr("src.scrape.BROWSER_PROFILE_DIR", tmp_path / "browser_profile")

    conn = MagicMock()
    # Mock approved_unapplied returning 1 job
    job = {
        "id": 1,
        "jobstreet_id": "12345",
        "title": "Data Analyst",
        "company": "PT Test",
        "url": "https://id.jobstreet.com/id/job/12345",
    }
    monkeypatch.setattr("src.apply.approved_unapplied", lambda _conn: [job])
    monkeypatch.setattr("src.apply.list_answers", lambda _conn: [])
    monkeypatch.setattr("src.apply.company_in_cooldown", lambda *args: False)
    monkeypatch.setattr(
        "src.apply.apply_to_job",
        lambda *args, **kwargs: {
            "status": "dry-run",
            "salary": 7000000,
            "letter": "test",
            "screenshot": "shot.png",
        },
    )

    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_playwright.__enter__.return_value.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.pages = [mock_page]

    cfg = {"filters": {"company_cooldown_days": 28}}
    profile = {"salary": {"min_acceptable": 6000000, "preferred": 7000000}}

    with patch("playwright.sync_api.sync_playwright", return_value=mock_playwright):
        res = run_apply(
            cfg,
            conn,
            profile,
            execute=False,
            use_llm_letter=False,
            limit=1,
            headless=True,
        )

    assert res["dry-run"] == 1
    mock_playwright.__enter__.return_value.chromium.launch.assert_called_once()


def test_run_apply_works_without_storage_state(tmp_path, monkeypatch):
    storage_file = tmp_path / "non_existent.json"
    monkeypatch.setattr("src.apply.STORAGE_STATE_PATH", storage_file)
    monkeypatch.setattr("src.scrape.STORAGE_STATE_PATH", storage_file)
    monkeypatch.setattr("src.scrape.BROWSER_PROFILE_DIR", tmp_path / "browser_profile")

    conn = MagicMock()
    job = {
        "id": 1,
        "jobstreet_id": "12345",
        "title": "Data Analyst",
        "company": "PT Test",
        "url": "https://id.jobstreet.com/id/job/12345",
    }
    monkeypatch.setattr("src.apply.approved_unapplied", lambda _conn: [job])
    monkeypatch.setattr("src.apply.list_answers", lambda _conn: [])
    monkeypatch.setattr("src.apply.company_in_cooldown", lambda *args: False)
    monkeypatch.setattr(
        "src.apply.apply_to_job",
        lambda *args, **kwargs: {
            "status": "dry-run",
            "salary": 7000000,
            "letter": "test",
            "screenshot": "shot.png",
        },
    )

    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_playwright.__enter__.return_value.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.pages = [mock_page]

    cfg = {"filters": {"company_cooldown_days": 28}}
    profile = {"salary": {"min_acceptable": 6000000, "preferred": 7000000}}

    with patch("playwright.sync_api.sync_playwright", return_value=mock_playwright):
        run_apply(
            cfg,
            conn,
            profile,
            execute=False,
            use_llm_letter=False,
            limit=1,
            headless=True,
        )

    mock_playwright.__enter__.return_value.chromium.launch.assert_called_once()


def test_run_apply_reuses_existing_browser_context(tmp_path, monkeypatch):
    conn = MagicMock()
    job = {
        "id": 1,
        "jobstreet_id": "12345",
        "title": "Data Analyst",
        "company": "PT Test",
        "url": "https://id.jobstreet.com/id/job/12345",
    }
    monkeypatch.setattr("src.apply.list_answers", lambda _conn: [])
    monkeypatch.setattr("src.apply.company_in_cooldown", lambda *args: False)
    apply_called = False

    def mock_apply_to_job(page, *args, **kwargs):
        nonlocal apply_called
        apply_called = True
        return {
            "status": "dry-run",
            "salary": 7000000,
            "letter": "test",
            "screenshot": "shot.png",
        }

    monkeypatch.setattr("src.apply.apply_to_job", mock_apply_to_job)

    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_context.pages = [mock_page]

    cfg = {"filters": {"company_cooldown_days": 28}}
    profile = {"salary": {"min_acceptable": 6000000, "preferred": 7000000}}

    # When browser_context is passed directly, sync_playwright should NOT be invoked
    with patch("playwright.sync_api.sync_playwright") as mock_sp:
        res = run_apply(
            cfg,
            conn,
            profile,
            execute=False,
            use_llm_letter=False,
            limit=1,
            headless=True,
            jobs=[job],
            browser_context=mock_context,
        )

    assert res["dry-run"] == 1
    assert apply_called is True
    mock_sp.assert_not_called()
    mock_context.close.assert_not_called()  # caller owns context lifecycle


def test_run_apply_reuses_existing_playwright_ctx(tmp_path, monkeypatch):
    conn = MagicMock()
    job = {
        "id": 1,
        "jobstreet_id": "12345",
        "title": "Data Analyst",
        "company": "PT Test",
        "url": "https://id.jobstreet.com/id/job/12345",
    }
    monkeypatch.setattr("src.apply.list_answers", lambda _conn: [])
    monkeypatch.setattr("src.apply.company_in_cooldown", lambda *args: False)
    monkeypatch.setattr(
        "src.apply.apply_to_job",
        lambda *args, **kwargs: {
            "status": "dry-run",
            "salary": 7000000,
            "letter": "test",
            "screenshot": "shot.png",
        },
    )

    mock_pw_ctx = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_pw_ctx.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.pages = [mock_page]

    cfg = {"filters": {"company_cooldown_days": 28}}
    profile = {"salary": {"min_acceptable": 6000000, "preferred": 7000000}}

    with patch("playwright.sync_api.sync_playwright") as mock_sp:
        res = run_apply(
            cfg,
            conn,
            profile,
            execute=False,
            use_llm_letter=False,
            limit=1,
            headless=True,
            jobs=[job],
            playwright_ctx=mock_pw_ctx,
        )

    assert res["dry-run"] == 1
    mock_sp.assert_not_called()
    mock_pw_ctx.chromium.launch.assert_called_once()
    mock_context.close.assert_called_once()
