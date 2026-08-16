"""Tests for dynamic model fetching and discovery."""
import json
import unittest.mock as mock

from src.models_fetcher import list_models_for_provider, fetch_remote_catalog


def test_list_models_for_copilot_live():
    mock_copilot_data = {
        "data": [
            {
                "id": "claude-opus-4.8",
                "name": "Claude 4.8 Opus",
                "capabilities": {"type": "chat"},
                "policy": {"state": "enabled"},
            },
            {
                "id": "gpt-5.5",
                "name": "GPT 5.5",
                "capabilities": {"type": "chat"},
                "policy": {"state": "enabled"},
            },
            {
                "id": "text-embedding-3-small",
                "name": "Embedding",
                "capabilities": {"type": "embedding"},
            }
        ]
    }

    with mock.patch("src.models_fetcher.get_valid_token", return_value="copilot-token"):
        with mock.patch("src.models_fetcher._fetch_json", return_value=mock_copilot_data):
            models = list_models_for_provider("copilot")
            ids = [m["id"] for m in models]
            assert "claude-opus-4.8" in ids
            assert "gpt-5.5" in ids
            assert "text-embedding-3-small" not in ids


def test_list_models_for_codex_live():
    mock_codex_data = {
        "models": [
            {"id": "gpt-5.2", "display_name": "GPT-5.2"},
            {"id": "o3-pro", "display_name": "o3 Pro"},
        ]
    }

    with mock.patch("src.models_fetcher.get_valid_token", return_value="codex-token"):
        with mock.patch("src.models_fetcher._fetch_json", return_value=mock_codex_data):
            models = list_models_for_provider("codex")
            ids = [m["id"] for m in models]
            assert "gpt-5.2" in ids
            assert "o3-pro" in ids


def test_list_models_remote_fallback_when_offline():
    mock_remote_data = {
        "claude": [
            {"id": "claude-3-7-sonnet-latest", "display_name": "Claude 3.7 Sonnet"},
        ]
    }

    with mock.patch("src.models_fetcher.get_valid_token", side_effect=Exception("No token")):
        with mock.patch("src.models_fetcher.fetch_remote_catalog", return_value=mock_remote_data):
            models = list_models_for_provider("claude")
            assert len(models) >= 1
            assert any(m["id"] == "claude-3-7-sonnet-latest" for m in models)
