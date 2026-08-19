import io
import json
from unittest.mock import MagicMock, patch
import urllib.error
import pytest

from src.llm import (
    complete,
    _complete_copilot,
    _complete_gemini,
    _complete_claude,
    _complete_codex,
)


def test_complete_copilot_claude_model(monkeypatch):
    monkeypatch.setattr("src.llm.get_valid_token", lambda p: "test-copilot-token")

    fake_response = json.dumps({
        "content": [
            {"type": "text", "text": "Claude via Copilot response"}
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        msgs = [{"role": "system", "content": "system prompt"}, {"role": "user", "content": "hello"}]
        res = _complete_copilot(msgs, "claude-3.5-sonnet")
        assert res == "Claude via Copilot response"
        req = mock_urlopen.call_args[0][0]
        assert "messages" in req.full_url


def test_complete_gemini_tiered_and_fallback(monkeypatch):
    monkeypatch.setattr("src.llm.get_valid_token", lambda p: "test-gemini-token")

    fake_response = json.dumps({
        "candidates": [
            {"content": {"parts": [{"text": "Gemini response text"}]}}
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        msgs = [{"role": "system", "content": "act as hr"}, {"role": "user", "content": "analyze"}]
        res = _complete_gemini(msgs, "gemini-3.7-flash-high", max_tokens=1000)
        assert res == "Gemini response text"
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        # Verify headroom is allocated for thinking tokens
        assert body["request"]["generationConfig"]["maxOutputTokens"] >= 5096


def test_complete_provider_dispatcher_and_error(monkeypatch):
    # Test error handling when subscription provider raises exception
    monkeypatch.setattr("src.llm.get_valid_token", lambda p: (_ for _ in ()).throw(ValueError("Token missing")))

    with pytest.raises(RuntimeError, match="Subscription LLM \\(claude\\) failed"):
        complete([{"role": "user", "content": "hi"}], {"llm": {"provider": "claude", "model": "claude-3"}})


def test_complete_urllib_http_error(monkeypatch):
    # Force ImportError on openai to trigger urllib path
    monkeypatch.setattr("builtins.__import__", lambda name, *args, **kw: (_ for _ in ()).throw(ImportError("no openai")) if name == "openai" else __import__(name, *args, **kw))

    fp = io.BytesIO(b"Unauthorized API Key")
    err = urllib.error.HTTPError("http://example.com", 401, "Unauthorized", {}, fp)

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="LLM API request failed \\(401\\): Unauthorized API Key"):
            complete(
                [{"role": "user", "content": "hi"}],
                {"llm": {"provider": "openai", "base_url": "https://api.test", "api_key": "bad-key", "model": "gpt-4"}}
            )
