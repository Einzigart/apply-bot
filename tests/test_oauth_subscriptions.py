"""Tests for OAuth token manager and native subscription LLM completions."""
import json
import time
import unittest.mock as mock
import pytest

from src.llm import complete, get_llm_config
from src.oauth import (
    TokenStorage,
    generate_pkce,
    get_valid_token,
    refresh_claude_token,
    refresh_codex_token,
    refresh_gemini_token,
    refresh_copilot_session_token,
)


def test_pkce_generation():
    verifier, challenge = generate_pkce()
    assert len(verifier) >= 43
    assert len(challenge) > 20
    assert "=" not in challenge


def test_token_storage_crud(tmp_path):
    storage_file = tmp_path / "auth_tokens.json"
    storage = TokenStorage(storage_file)

    assert storage.load() == {}
    assert storage.get_provider("claude") is None

    storage.set_provider("claude", {"access_token": "sk-ant-test", "expires_at": time.time() + 3600})
    assert storage.get_provider("claude")["access_token"] == "sk-ant-test"

    storage.delete_provider("claude")
    assert storage.get_provider("claude") is None


def test_get_valid_token_auto_refresh(tmp_path):
    storage_file = tmp_path / "auth_tokens.json"
    storage = TokenStorage(storage_file)

    # Expired token
    storage.set_provider("claude", {
        "access_token": "old-token",
        "refresh_token": "ref-token",
        "expires_at": time.time() - 100,
    })

    with mock.patch("src.oauth.AUTH_TOKENS_PATH", storage_file):
        with mock.patch("src.oauth.TokenStorage", return_value=storage):
            with mock.patch("src.oauth.refresh_claude_token") as mock_refresh:
                mock_refresh.return_value = {
                    "access_token": "new-refreshed-token",
                    "refresh_token": "ref-token",
                    "expires_at": time.time() + 3600,
                }
                token = get_valid_token("claude")
                assert token == "new-refreshed-token"
                mock_refresh.assert_called_once()


def test_complete_claude_subscription(tmp_path):
    cfg = {
        "llm": {
            "provider": "claude",
            "model": "claude-3-5-sonnet-20241022",
        }
    }

    mock_resp = {
        "content": [
            {"type": "text", "text": "Hello from Claude Subscription!"}
        ]
    }

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def read(self):
            return json.dumps(mock_resp).encode("utf-8")

    with mock.patch("src.llm.get_valid_token", return_value="test-claude-token"):
        with mock.patch("urllib.request.urlopen", return_value=MockResponse()) as mock_urlopen:
            resp = complete([{"role": "user", "content": "hi"}], cfg)
            assert resp == "Hello from Claude Subscription!"
            req = mock_urlopen.call_args[0][0]
            assert req.full_url == "https://api.anthropic.com/v1/messages?beta=true"
            assert req.headers["Authorization"] == "Bearer test-claude-token"
            assert req.headers["Anthropic-version"] == "2023-06-01"


def test_complete_codex_subscription():
    cfg = {
        "llm": {
            "provider": "codex",
            "model": "gpt-5.4-mini",
        }
    }

    sse_stream = [
        b'data: {"type": "response.output_text.delta", "delta": "Hello from "}\n',
        b'data: {"type": "response.output_text.delta", "delta": "ChatGPT Codex!"}\n',
        b'data: [DONE]\n',
    ]

    class MockSSEResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def __iter__(self):
            return iter(sse_stream)

    with mock.patch("src.llm.get_valid_token", return_value="test-codex-token"):
        with mock.patch("urllib.request.urlopen", return_value=MockSSEResponse()) as mock_urlopen:
            resp = complete([{"role": "user", "content": "hi"}], cfg)
            assert resp == "Hello from ChatGPT Codex!"
            req = mock_urlopen.call_args[0][0]
            assert req.full_url == "https://chatgpt.com/backend-api/codex/responses"
            assert req.headers["Authorization"] == "Bearer test-codex-token"
            assert req.headers["Originator"] == "codex_cli_rs"


def test_complete_copilot_subscription():
    cfg = {
        "llm": {
            "provider": "copilot",
            "model": "gpt-4o",
        }
    }

    mock_resp = {
        "choices": [
            {"message": {"content": "Hello from Copilot!"}}
        ]
    }

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def read(self):
            return json.dumps(mock_resp).encode("utf-8")

    with mock.patch("src.llm.get_valid_token", return_value="test-copilot-token"):
        with mock.patch("urllib.request.urlopen", return_value=MockResponse()) as mock_urlopen:
            resp = complete([{"role": "user", "content": "hi"}], cfg)
            assert resp == "Hello from Copilot!"
            req = mock_urlopen.call_args[0][0]
            assert req.full_url == "https://api.githubcopilot.com/chat/completions"
            assert req.headers["Copilot-integration-id"] == "vscode-chat"


def test_complete_gemini_subscription():
    cfg = {
        "llm": {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
        }
    }

    mock_resp = {
        "response": {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Hello from Gemini Code Assist!"}
                        ]
                    }
                }
            ]
        }
    }

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def read(self):
            return json.dumps(mock_resp).encode("utf-8")

    with mock.patch("src.llm.get_valid_token", return_value="test-gemini-token"):
        with mock.patch("urllib.request.urlopen", return_value=MockResponse()) as mock_urlopen:
            resp = complete([{"role": "user", "content": "hi"}], cfg)
            assert resp == "Hello from Gemini Code Assist!"
            req = mock_urlopen.call_args[0][0]
            assert "googleapis.com" in req.full_url
            assert req.headers["Authorization"] == "Bearer test-gemini-token"
