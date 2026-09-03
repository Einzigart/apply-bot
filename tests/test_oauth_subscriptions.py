"""Tests for OAuth token manager and native subscription LLM completions."""
import base64
import hashlib
import json
import threading
import time
import unittest.mock as mock
import urllib.parse
import pytest

from src.llm import complete, get_llm_config
from src.oauth import (
    TokenStorage,
    generate_pkce,
    get_valid_token,
    refresh_claude_token,
    refresh_codex_token,
    refresh_gemini_token,
    refresh_github_access_token,
    refresh_copilot_session_token,
    poll_copilot_device_token,
    request_copilot_device_code,
    start_claude_oauth,
    start_codex_oauth,
)


def test_pkce_generation():
    verifier, challenge = generate_pkce()
    assert len(verifier) == 86
    assert len(challenge) == 43
    assert "=" not in verifier
    assert "=" not in challenge


def test_claude_oauth_uses_9router_pkce_lengths():
    token_response = mock.MagicMock()
    token_response.read.return_value = json.dumps({
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "expires_in": 3600,
    }).encode("utf-8")
    token_response.__enter__.return_value = token_response

    with mock.patch("webbrowser.open") as mock_browser_open:
        with mock.patch("src.oauth.listen_for_code", return_value="test-authorization-code"):
            with mock.patch("urllib.request.urlopen", return_value=token_response) as mock_urlopen:
                with mock.patch("src.oauth.TokenStorage"):
                    start_claude_oauth()

    auth_url = mock_browser_open.call_args.args[0]
    auth_params = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
    token_request = mock_urlopen.call_args.args[0]
    token_payload = json.loads(token_request.data)

    assert len(auth_params["state"][0]) == 43
    assert len(auth_params["code_challenge"][0]) == 43
    assert auth_params["code_challenge_method"] == ["S256"]
    assert len(token_payload["code_verifier"]) == 43
    assert token_payload["state"] == auth_params["state"][0]


def test_codex_oauth_matches_9router_authorize_and_exchange():
    token_response = mock.MagicMock()
    token_response.read.return_value = json.dumps({
        "access_token": "test-codex-access-token",
        "refresh_token": "test-codex-refresh-token",
        "id_token": "test-codex-id-token",
        "expires_in": 3600,
    }).encode("utf-8")
    token_response.__enter__.return_value = token_response

    with mock.patch("webbrowser.open") as mock_browser_open:
        with mock.patch("src.oauth.listen_for_code", return_value="test-codex-code"):
            with mock.patch("urllib.request.urlopen", return_value=token_response) as mock_urlopen:
                with mock.patch("src.oauth.TokenStorage"):
                    start_codex_oauth()

    auth_url = mock_browser_open.call_args.args[0]
    parsed_url = urllib.parse.urlparse(auth_url)
    auth_params = urllib.parse.parse_qs(parsed_url.query)
    token_request = mock_urlopen.call_args.args[0]
    token_params = urllib.parse.parse_qs(token_request.data.decode("utf-8"))

    assert parsed_url.netloc == "auth.openai.com"
    assert auth_params["scope"] == ["openid profile email offline_access"]
    assert "scope=openid%20profile%20email%20offline_access" in parsed_url.query
    assert auth_params["id_token_add_organizations"] == ["true"]
    assert auth_params["codex_cli_simplified_flow"] == ["true"]
    assert auth_params["originator"] == ["codex_cli_rs"]
    assert "prompt" not in auth_params
    assert len(auth_params["state"][0]) == 43
    assert len(auth_params["code_challenge"][0]) == 43
    assert auth_params["code_challenge_method"] == ["S256"]
    assert token_request.full_url == "https://auth.openai.com/oauth/token"
    assert token_request.get_header("Content-type") == "application/x-www-form-urlencoded"
    assert set(token_params) == {
        "grant_type",
        "client_id",
        "code",
        "redirect_uri",
        "code_verifier",
    }
    assert token_params["grant_type"] == ["authorization_code"]
    assert token_params["client_id"] == ["app_EMoamEEZ73f0CkXaXp7hrann"]
    assert token_params["code"] == ["test-codex-code"]
    assert token_params["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    verifier = token_params["code_verifier"][0]
    assert len(verifier) == 43
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("utf-8")).digest()
    ).decode("utf-8").rstrip("=")
    assert auth_params["code_challenge"] == [expected_challenge]


def test_refresh_codex_token_matches_9router_json_contract():
    token_response = mock.MagicMock()
    token_response.read.return_value = json.dumps({
        "access_token": "new-codex-access-token",
        "refresh_token": "new-codex-refresh-token",
        "id_token": "new-codex-id-token",
        "expires_in": 3600,
    }).encode("utf-8")
    token_response.__enter__.return_value = token_response

    token_data = {
        "provider": "codex",
        "access_token": "old-codex-access-token",
        "refresh_token": "old-codex-refresh-token",
    }
    with mock.patch("urllib.request.urlopen", return_value=token_response) as mock_urlopen:
        with mock.patch("src.oauth.TokenStorage"):
            updated = refresh_codex_token(token_data)

    request = mock_urlopen.call_args.args[0]
    assert isinstance(request.data, bytes)
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://auth.openai.com/oauth/token"
    assert request.get_header("Content-type") == "application/json"
    assert payload == {
        "grant_type": "refresh_token",
        "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "refresh_token": "old-codex-refresh-token",
    }
    assert updated["access_token"] == "new-codex-access-token"
    assert updated["refresh_token"] == "new-codex-refresh-token"
    assert updated["id_token"] == "new-codex-id-token"


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


def _oauth_response(payload):
    response = mock.MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    return response


def test_copilot_device_poll_is_one_shot_and_normalizes_interval():
    pending = _oauth_response({"error": "authorization_pending"})
    with mock.patch("urllib.request.urlopen", return_value=pending) as urlopen:
        result = poll_copilot_device_token("device-code", interval=0)

    assert result == {"status": "pending", "interval": 5}
    assert urlopen.call_count == 1


def test_copilot_device_code_normalizes_and_validates_upstream_response():
    for expires_in, expected in ((None, 900), (1800, 1800), (90000, 90000)):
        response = _oauth_response({
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "device_code": "device-code",
            "interval": 0,
            **({} if expires_in is None else {"expires_in": expires_in}),
        })
        with mock.patch("urllib.request.urlopen", return_value=response):
            result = request_copilot_device_code()

        assert result["interval"] == 5
        assert result["expires_in"] == expected

    for expires_in in ("invalid", 0, -1, float("nan"), float("inf")):
        response = _oauth_response({
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "device_code": "device-code",
            "expires_in": expires_in,
        })
        with mock.patch("urllib.request.urlopen", return_value=response):
            with pytest.raises(RuntimeError, match="expires_in"):
                request_copilot_device_code()

    malformed = _oauth_response({"user_code": "", "verification_uri": "", "device_code": ""})
    with mock.patch("urllib.request.urlopen", return_value=malformed):
        with pytest.raises(RuntimeError, match="device-code response missing"):
            request_copilot_device_code()


def test_copilot_device_poll_increases_interval_on_slow_down():
    slow_down = _oauth_response({"error": "slow_down"})
    with mock.patch("urllib.request.urlopen", return_value=slow_down):
        result = poll_copilot_device_token("device-code", interval=5)

    assert result == {"status": "slow_down", "interval": 10}


def test_copilot_device_poll_reports_expiry():
    expired = _oauth_response({"error": "expired_token"})
    with mock.patch("urllib.request.urlopen", return_value=expired):
        result = poll_copilot_device_token("device-code", interval=-1)

    assert result["status"] == "expired"
    assert result["interval"] == 5


def test_copilot_device_flow_preserves_github_metadata_and_expiry(monkeypatch):
    github_tokens = _oauth_response({
        "access_token": "github-access",
        "token_type": "bearer",
        "scope": "read:user",
        "expires_in": 28800,
        "refresh_token": "github-refresh",
        "refresh_token_expires_in": 15897600,
    })
    copilot_tokens = _oauth_response({"token": "copilot-session", "expires_at": 1_900_000_000})
    stored = mock.MagicMock()

    monkeypatch.setattr("src.oauth.TokenStorage", lambda: stored)
    with mock.patch("urllib.request.urlopen", side_effect=[github_tokens, copilot_tokens]):
        result = poll_copilot_device_token("device-code", interval=1)

    token_data = result["token_data"]
    assert result["status"] == "success"
    assert token_data["github_access_token"] == "github-access"
    assert token_data["github_refresh_token"] == "github-refresh"
    assert token_data["github_expires_in"] == 28800
    assert token_data["github_refresh_token_expires_in"] == 15897600
    assert token_data["github_token_type"] == "bearer"
    assert token_data["github_scope"] == "read:user"
    assert token_data["github_expires_at"] > time.time()
    assert token_data["copilot_token"] == "copilot-session"
    assert token_data["copilot_token_expires_at"] == 1_900_000_000
    stored.set_provider.assert_called_once_with("copilot", token_data)


def test_copilot_device_flow_rejects_invalid_github_expiry():
    with mock.patch("urllib.request.urlopen", return_value=_oauth_response({
        "access_token": "github-access",
        "expires_in": 0,
    })):
        with pytest.raises(RuntimeError, match="nonpositive expires_in"):
            poll_copilot_device_token("device-code", interval=1)


def test_copilot_session_token_requires_token_and_adds_api_version(monkeypatch):
    response = _oauth_response({"token": "copilot-session"})
    with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
        result = refresh_copilot_session_token("github-access")

    request = urlopen.call_args.args[0]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert result["token"] == "copilot-session"
    assert headers["x-github-api-version"] == "2025-04-01"

    missing_token = _oauth_response({"expires_at": 1_900_000_000})
    with mock.patch("urllib.request.urlopen", return_value=missing_token):
        with pytest.raises(RuntimeError, match="session token"):
            refresh_copilot_session_token("github-access")


def test_github_refresh_rotates_token_and_metadata():
    token_data = {
        "github_access_token": "old-access",
        "github_refresh_token": "old-refresh",
        "github_expires_at": time.time() - 1,
    }
    refreshed = _oauth_response({
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "refresh_token_expires_in": 123456,
        "expires_in": 28800,
    })
    with mock.patch("urllib.request.urlopen", return_value=refreshed):
        result = refresh_github_access_token(token_data)

    assert result["github_access_token"] == "new-access"
    assert result["github_refresh_token"] == "new-refresh"
    assert result["github_refresh_token_expires_in"] == 123456
    assert result["github_expires_in"] == 28800
    assert result["github_expires_at"] > time.time()


def test_github_refresh_requires_refresh_token():
    with pytest.raises(ValueError, match="no refresh token"):
        refresh_github_access_token({"github_access_token": "expired"})


def test_get_valid_copilot_rejects_invalid_stored_github_expiry(monkeypatch):
    storage = mock.MagicMock()
    monkeypatch.setattr("src.oauth.TokenStorage", lambda: storage)
    for invalid_expiry in ("invalid", 0, -1, float("nan"), float("inf")):
        storage.get_provider.return_value = {
            "provider": "copilot",
            "github_access_token": "access",
            "github_expires_at": invalid_expiry,
            "copilot_token": "session",
            "copilot_token_expires_at": time.time() + 3600,
        }
        with pytest.raises(ValueError, match="Stored GitHub access-token expiry is invalid"):
            get_valid_token("copilot")


def test_get_valid_copilot_rejects_invalid_stored_session_expiry(monkeypatch):
    storage = mock.MagicMock()
    monkeypatch.setattr("src.oauth.TokenStorage", lambda: storage)
    for invalid_expiry in ("invalid", 0, -1, float("nan"), float("inf")):
        storage.get_provider.return_value = {
            "provider": "copilot",
            "github_access_token": "access",
            "copilot_token": "session",
            "copilot_token_expires_at": invalid_expiry,
        }
        with pytest.raises(ValueError, match="Stored GitHub Copilot session expiry is invalid"):
            get_valid_token("copilot")


def test_github_refresh_rejects_present_invalid_expiry():
    response = _oauth_response({"access_token": "new-access", "expires_in": 0})
    with mock.patch("urllib.request.urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="nonpositive expires_in"):
            refresh_github_access_token({"github_refresh_token": "refresh"})


def test_copilot_session_expiry_defaults_when_omitted(monkeypatch):
    stored = mock.MagicMock()
    monkeypatch.setattr("src.oauth.TokenStorage", lambda: stored)
    with mock.patch("urllib.request.urlopen", side_effect=[
        _oauth_response({"access_token": "github-access"}),
        _oauth_response({"token": "copilot-session"}),
    ]):
        result = poll_copilot_device_token("device-code", interval=1)

    assert result["token_data"]["copilot_token_expires_at"] > time.time()


def test_copilot_session_rejects_nonfinite_expiry():
    with mock.patch("urllib.request.urlopen", side_effect=[
        _oauth_response({"access_token": "github-access"}),
        _oauth_response({"token": "copilot-session", "expires_at": float("nan")}),
    ]):
        with pytest.raises(RuntimeError, match="non-finite expiry"):
            poll_copilot_device_token("device-code", interval=1)


def test_get_valid_copilot_refreshes_github_then_mints_session_once(monkeypatch):
    token_data = {
        "provider": "copilot",
        "github_access_token": "old-access",
        "github_refresh_token": "old-refresh",
        "github_expires_at": time.time() - 1,
        "copilot_token": "old-session",
        "copilot_token_expires_at": time.time() + 3600,
    }
    storage = mock.MagicMock()
    storage.get_provider.return_value = token_data
    refreshed = dict(token_data, github_access_token="new-access", github_refresh_token="new-refresh")
    monkeypatch.setattr("src.oauth.TokenStorage", lambda: storage)
    with mock.patch("src.oauth.refresh_github_access_token", return_value=refreshed) as refresh_github:
        with mock.patch("src.oauth.refresh_copilot_session_token", return_value={
            "token": "new-session",
            "expires_at": time.time() + 3600,
        }) as refresh_copilot:
            assert get_valid_token("copilot") == "new-session"

    refresh_github.assert_called_once_with(token_data)
    refresh_copilot.assert_called_once_with("new-access")
    assert storage.set_provider.call_count == 2
    saved = storage.set_provider.call_args.args[1]
    assert saved["github_refresh_token"] == "new-refresh"
    assert saved["copilot_token"] == "new-session"


def test_get_valid_copilot_persists_github_rotation_before_session_failure(monkeypatch):
    original = {
        "provider": "copilot",
        "github_access_token": "old-access",
        "github_refresh_token": "old-refresh",
        "github_expires_at": time.time() - 1,
        "copilot_token": "old-session",
        "copilot_token_expires_at": time.time() + 3600,
    }
    storage = mock.MagicMock()
    storage.get_provider.return_value = original
    rotated = dict(original, github_access_token="new-access", github_refresh_token="new-refresh")
    monkeypatch.setattr("src.oauth.TokenStorage", lambda: storage)
    monkeypatch.setattr("src.oauth.refresh_github_access_token", lambda _: rotated)
    with mock.patch("src.oauth.refresh_copilot_session_token", side_effect=RuntimeError("Copilot unavailable")):
        with pytest.raises(RuntimeError, match="Copilot unavailable"):
            get_valid_token("copilot")

    storage.set_provider.assert_called_once_with("copilot", rotated)


def test_get_valid_copilot_serializes_refresh_and_rechecks_storage(monkeypatch):
    class MemoryStorage:
        def __init__(self):
            self.data = {
                "provider": "copilot",
                "github_access_token": "old-access",
                "github_refresh_token": "old-refresh",
                "github_expires_at": time.time() - 1,
                "copilot_token": "old-session",
                "copilot_token_expires_at": time.time() + 3600,
            }
            self.writes = []

        def get_provider(self, _):
            return dict(self.data)

        def set_provider(self, _, value):
            self.data = dict(value)
            self.writes.append(dict(value))

    storage = MemoryStorage()
    monkeypatch.setattr("src.oauth.TokenStorage", lambda: storage)
    refresh_github_calls = 0

    def refresh_github(value):
        nonlocal refresh_github_calls
        refresh_github_calls += 1
        return dict(value, github_access_token="new-access", github_expires_at=time.time() + 3600)

    monkeypatch.setattr("src.oauth.refresh_github_access_token", refresh_github)
    monkeypatch.setattr(
        "src.oauth.refresh_copilot_session_token",
        lambda token: {"token": f"session-{token}", "expires_at": time.time() + 3600},
    )
    results = []
    threads = [threading.Thread(target=lambda: results.append(get_valid_token("copilot"))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["session-new-access", "session-new-access"]
    assert refresh_github_calls == 1
    assert len(storage.writes) == 2


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
