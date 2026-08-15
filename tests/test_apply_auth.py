from unittest.mock import MagicMock, patch

from src.apply import run_apply


def test_run_apply_loads_storage_state_when_present(tmp_path, monkeypatch):
    storage_file = tmp_path / "storage_state.json"
    storage_file.write_text('{"cookies": []}')
    monkeypatch.setattr("src.apply.STORAGE_STATE_PATH", storage_file)

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
    mock_context.new_page.return_value = mock_page

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
    mock_browser.new_context.assert_called_once_with(
        locale="id-ID",
        storage_state=str(storage_file),
    )


def test_run_apply_works_without_storage_state(tmp_path, monkeypatch):
    storage_file = tmp_path / "non_existent.json"
    monkeypatch.setattr("src.apply.STORAGE_STATE_PATH", storage_file)

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
    mock_context.new_page.return_value = mock_page

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

    mock_browser.new_context.assert_called_once_with(locale="id-ID")
