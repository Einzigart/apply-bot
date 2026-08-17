import json
import time
from unittest.mock import MagicMock, patch
import pytest

from src.oauth import (
    TokenStorage,
    get_valid_token,
    refresh_gemini_token,
    _setup_antigravity_project,
    CLAUDE_CONFIG,
    CODEX_CONFIG,
    GEMINI_CONFIG,
)
from src.models_fetcher import list_models_for_provider


def test_setup_antigravity_project_success():
    fake_resp = json.dumps({"cloudaicompanionProject": {"id": "my-gemini-project-123"}}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_resp
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        project_id = _setup_antigravity_project("valid-token")
        assert project_id == "my-gemini-project-123"


def test_refresh_gemini_token(tmp_path):
    storage_path = tmp_path / "auth_tokens.json"
    storage = TokenStorage(storage_path)
    storage.set_provider("gemini", {"refresh_token": "gem-refresh-123", "access_token": "old-tok"})

    fake_token_resp = json.dumps({
        "access_token": "new-gemini-access-token",
        "expires_in": 3600,
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_token_resp
    mock_resp.__enter__.return_value = mock_resp

    with patch("src.oauth.TokenStorage", return_value=storage):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            updated = refresh_gemini_token({"refresh_token": "gem-refresh-123"})
            assert updated["access_token"] == "new-gemini-access-token"


def test_get_valid_token_gemini_auto_refresh(tmp_path):
    storage_path = tmp_path / "auth_tokens.json"
    storage = TokenStorage(storage_path)
    # Expired token
    storage.set_provider("gemini", {
        "access_token": "expired-access",
        "refresh_token": "gem-refresh",
        "expires_at": time.time() - 100,
    })

    with patch("src.oauth.TokenStorage", return_value=storage):
        with patch("src.oauth.refresh_gemini_token", return_value={"access_token": "fresh-gem-tok"}):
            tok = get_valid_token("gemini")
            assert tok == "fresh-gem-tok"


def test_list_models_for_provider_branches(monkeypatch):
    # Mock remote catalog fetch
    monkeypatch.setattr("src.models_fetcher.fetch_remote_catalog", lambda: {
        "gemini": [{"id": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash"}],
        "claude": [{"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"}],
    })

    # Claude static/remote list
    claude_models = list_models_for_provider("claude")
    assert any("sonnet" in m["id"].lower() for m in claude_models)

    # Gemini list
    gemini_models = list_models_for_provider("gemini")
    assert any("gemini-2.5" in m["id"] for m in gemini_models)

    # Unknown provider returns default OpenAI models
    unknown = list_models_for_provider("custom_provider")
    assert any("gpt-4o" in m["id"] for m in unknown)
