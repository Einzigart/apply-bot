from unittest.mock import MagicMock, patch

from src.run import cmd_login, main


def test_cli_parser_recognizes_login():
    with patch("sys.argv", ["apply-bot", "login"]):
        with patch("src.run.cmd_login") as mock_login, patch("src.db.finish_run"), patch("src.db.start_run"):
            main()
            mock_login.assert_called_once()


def test_cmd_login_saves_storage_state_interactive(tmp_path, monkeypatch):
    storage_path = tmp_path / "storage_state.json"
    monkeypatch.setattr("src.run.STORAGE_STATE_PATH", storage_path)
    monkeypatch.setattr("src.scrape.STORAGE_STATE_PATH", storage_path)
    monkeypatch.setattr("src.scrape.BROWSER_PROFILE_DIR", tmp_path / "browser_profile")
    monkeypatch.setattr("builtins.input", lambda _: "")

    mock_playwright = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_playwright.__enter__.return_value.chromium.launch_persistent_context.return_value = mock_context
    mock_context.pages = [mock_page]

    def fake_storage_state(path):
        with open(path, "w") as f:
            f.write('{"cookies": [], "origins": []}')

    mock_context.storage_state.side_effect = fake_storage_state

    with patch("playwright.sync_api.sync_playwright", return_value=mock_playwright):
        args = MagicMock()
        args.auto_wait = False
        cmd_login(args)

    assert storage_path.exists()
    assert mock_page.goto.called
    assert mock_context.storage_state.called


def test_cmd_login_saves_storage_state_auto_wait(tmp_path, monkeypatch):
    storage_path = tmp_path / "storage_state.json"
    monkeypatch.setattr("src.run.STORAGE_STATE_PATH", storage_path)
    monkeypatch.setattr("src.scrape.STORAGE_STATE_PATH", storage_path)
    monkeypatch.setattr("src.scrape.BROWSER_PROFILE_DIR", tmp_path / "browser_profile")

    mock_playwright = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_page.url = "https://id.jobstreet.com/"
    mock_page.is_closed.return_value = False
    mock_context.cookies.return_value = [{"name": "auth_token", "value": "123"}]

    mock_playwright.__enter__.return_value.chromium.launch_persistent_context.return_value = mock_context
    mock_context.pages = [mock_page]

    def fake_storage_state(path):
        with open(path, "w") as f:
            f.write('{"cookies": [], "origins": []}')

    mock_context.storage_state.side_effect = fake_storage_state

    with patch("playwright.sync_api.sync_playwright", return_value=mock_playwright):
        args = MagicMock()
        args.auto_wait = True
        cmd_login(args)

    assert storage_path.exists()
    assert mock_page.goto.called
    assert mock_context.storage_state.called
