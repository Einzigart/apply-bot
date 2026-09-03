import json
import urllib.error
import urllib.parse
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from src.oauth import (
    TokenStorage,
    _antigravity_metadata,
    ANTIGRAVITY_CONFIG,
    get_valid_token,
    listen_for_code,
    OAuthCallbackHandler,
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


def test_antigravity_oauth_uses_standard_google_flow_and_numeric_metadata():
    token_response = MagicMock()
    token_response.read.return_value = json.dumps({
        "access_token": "new-antigravity-access",
        "refresh_token": "new-antigravity-refresh",
        "expires_in": 3600,
    }).encode("utf-8")
    token_response.__enter__.return_value = token_response

    project_response = MagicMock()
    project_response.read.return_value = json.dumps({
        "cloudaicompanionProject": {"id": "real-antigravity-project"},
    }).encode("utf-8")
    project_response.__enter__.return_value = project_response

    with patch("webbrowser.open") as mock_browser_open:
        with patch("src.oauth.listen_for_code", return_value="authorization-code"):
            with patch("urllib.request.urlopen", side_effect=[token_response, project_response]) as mock_urlopen:
                with patch("src.oauth.TokenStorage"):
                    from src.oauth import start_gemini_oauth

                    result = start_gemini_oauth()

    auth_params = urllib.parse.parse_qs(
        urllib.parse.urlparse(mock_browser_open.call_args.args[0]).query
    )
    token_request = mock_urlopen.call_args_list[0].args[0]
    token_params = urllib.parse.parse_qs(token_request.data.decode("utf-8"))
    project_request = mock_urlopen.call_args_list[1].args[0]
    project_payload = json.loads(project_request.data.decode("utf-8"))

    assert "code_challenge" not in auth_params
    assert "code_challenge_method" not in auth_params
    assert len(auth_params["state"][0]) == 43
    assert "code_verifier" not in token_params
    assert token_params["redirect_uri"] == ["http://localhost:51121/oauth-callback"]
    assert project_payload["metadata"] == _antigravity_metadata()
    assert project_request.get_header("User-agent") == "antigravity/ide/2.11.0 darwin/arm64"
    assert project_request.get_header("X-request-source") == "local"
    assert result["provider"] == "gemini"
    assert result["project_id"] == "real-antigravity-project"


def test_antigravity_project_onboarding_uses_default_tier_and_retries(monkeypatch):
    load_response = MagicMock()
    load_response.read.return_value = json.dumps({
        "allowedTiers": [{"id": "default-tier", "isDefault": True}],
    }).encode("utf-8")
    load_response.__enter__.return_value = load_response

    pending_response = MagicMock()
    pending_response.read.return_value = json.dumps({"done": False}).encode("utf-8")
    pending_response.__enter__.return_value = pending_response
    done_response = MagicMock()
    done_response.read.return_value = json.dumps({
        "done": True,
        "response": {"cloudaicompanionProject": {"id": "onboarded-project"}},
    }).encode("utf-8")
    done_response.__enter__.return_value = done_response

    monkeypatch.setattr("src.oauth.time.sleep", lambda _: None)
    with patch("urllib.request.urlopen", side_effect=[load_response, pending_response, done_response]) as mock_urlopen:
        project_id = _setup_antigravity_project("valid-token")

    onboard_request = mock_urlopen.call_args_list[1].args[0]
    assert json.loads(onboard_request.data.decode("utf-8")) == {
        "tierId": "default-tier",
        "metadata": _antigravity_metadata(),
    }
    assert project_id == "onboarded-project"


def test_antigravity_project_retries_transient_load_and_onboard_failures(monkeypatch):
    load_response = MagicMock()
    load_response.read.return_value = json.dumps({}).encode("utf-8")
    load_response.__enter__.return_value = load_response
    onboard_response = MagicMock()
    onboard_response.read.return_value = json.dumps({
        "done": True,
        "response": {"cloudaicompanionProject": {"id": "retried-project"}},
    }).encode("utf-8")
    onboard_response.__enter__.return_value = onboard_response

    monkeypatch.setattr("src.oauth.time.sleep", lambda _: None)
    with patch("urllib.request.urlopen", side_effect=[
        urllib.error.URLError("temporary load failure"),
        load_response,
        urllib.error.URLError("temporary onboard failure"),
        onboard_response,
    ]) as mock_urlopen:
        assert _setup_antigravity_project("valid-token") == "retried-project"
    assert mock_urlopen.call_count == 4


def test_antigravity_project_retry_failure_is_actionable(monkeypatch):
    monkeypatch.setattr("src.oauth.time.sleep", lambda _: None)
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")) as mock_urlopen:
        with pytest.raises(RuntimeError, match="loadCodeAssist failed after 2 attempts"):
            _setup_antigravity_project("valid-token")
    assert mock_urlopen.call_count == 2


def test_antigravity_project_retries_transient_http_failure(monkeypatch):
    project_response = MagicMock()
    project_response.read.return_value = json.dumps({
        "cloudaicompanionProject": {"id": "recovered-project"},
    }).encode("utf-8")
    project_response.__enter__.return_value = project_response

    monkeypatch.setattr("src.oauth.time.sleep", lambda _: None)
    http_error = urllib.error.HTTPError("https://cloudcode-pa.googleapis.com", 503, "busy", {}, None)
    with patch("urllib.request.urlopen", side_effect=[http_error, project_response]) as mock_urlopen:
        assert _setup_antigravity_project("valid-token") == "recovered-project"
    assert mock_urlopen.call_count == 2
    assert mock_urlopen.call_args_list[0].kwargs["timeout"] == 10


def test_antigravity_project_retries_transient_json_failure(monkeypatch):
    invalid_json_response = MagicMock()
    invalid_json_response.read.return_value = b"not-json"
    invalid_json_response.__enter__.return_value = invalid_json_response
    project_response = MagicMock()
    project_response.read.return_value = json.dumps({
        "cloudaicompanionProject": {"id": "recovered-project"},
    }).encode("utf-8")
    project_response.__enter__.return_value = project_response

    monkeypatch.setattr("src.oauth.time.sleep", lambda _: None)
    with patch("urllib.request.urlopen", side_effect=[invalid_json_response, project_response]) as mock_urlopen:
        assert _setup_antigravity_project("valid-token") == "recovered-project"
    assert mock_urlopen.call_count == 2


def test_antigravity_project_onboarding_budget_is_bounded(monkeypatch):
    load_response = MagicMock()
    load_response.read.return_value = json.dumps({}).encode("utf-8")
    load_response.__enter__.return_value = load_response
    pending_responses = []
    for _ in range(5):
        response = MagicMock()
        response.read.return_value = json.dumps({"done": False}).encode("utf-8")
        response.__enter__.return_value = response
        pending_responses.append(response)

    monkeypatch.setattr("src.oauth.time.sleep", lambda _: None)
    with patch("urllib.request.urlopen", side_effect=[load_response, *pending_responses]) as mock_urlopen:
        with pytest.raises(TimeoutError, match="after 5 polls"):
            _setup_antigravity_project("valid-token")
    assert mock_urlopen.call_count == 6


def test_listen_for_code_keeps_positional_timeout_and_validates_state(monkeypatch):
    class FakeServer:
        instances = []
        callback_state = "expected-state"

        def __init__(self, *_args):
            self.result_code = "authorization-code"
            self.result_state = self.callback_state
            self.result_error = None
            self.expected_path = None
            self.__class__.instances.append(self)

        def handle_request(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr("src.oauth.OAuthServer", FakeServer)
    assert listen_for_code(51121, "expected-state", 0, expected_path="/oauth-callback") == "authorization-code"
    assert FakeServer.instances[-1].expected_path == "/oauth-callback"

    for callback_state in (None, "wrong-state"):
        FakeServer.callback_state = callback_state
        with pytest.raises(ValueError, match="state mismatch"):
            listen_for_code(51121, "expected-state", 0, expected_path=ANTIGRAVITY_CONFIG["callback_path"])

    callback_handler = OAuthCallbackHandler.__new__(OAuthCallbackHandler)
    callback_handler.path = "/wrong-path?code=ignored&state=expected-state"
    callback_handler.server = SimpleNamespace(expected_path="/oauth-callback")
    callback_handler.send_error = MagicMock()
    callback_handler.do_GET()
    callback_handler.send_error.assert_called_once_with(404)


@pytest.mark.parametrize("platform_name,machine,expected", [
    ("Darwin", "arm64", 2),
    ("Darwin", "x86_64", 1),
    ("Linux", "aarch64", 4),
    ("Linux", "x86_64", 3),
    ("Windows", "AMD64", 5),
    ("FreeBSD", "x86_64", 0),
])
def test_antigravity_platform_metadata(platform_name, machine, expected, monkeypatch):
    monkeypatch.setattr("src.oauth.platform.system", lambda: platform_name)
    monkeypatch.setattr("src.oauth.platform.machine", lambda: machine)
    assert _antigravity_metadata()["platform"] == expected


def test_refresh_gemini_token(tmp_path):
    storage_path = tmp_path / "auth_tokens.json"
    storage = TokenStorage(storage_path)
    storage.set_provider("gemini", {"refresh_token": "gem-refresh-123", "access_token": "old-tok"})

    fake_token_resp = json.dumps({
        "access_token": "new-gemini-access-token",
        "refresh_token": "rotated-gemini-refresh-token",
        "expires_in": 3600,
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_token_resp
    mock_resp.__enter__.return_value = mock_resp

    with patch("src.oauth.TokenStorage", return_value=storage):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            updated = refresh_gemini_token({"refresh_token": "gem-refresh-123"})
            assert updated["access_token"] == "new-gemini-access-token"
            assert updated["refresh_token"] == "rotated-gemini-refresh-token"


def test_get_valid_token_antigravity_alias_refreshes_legacy_gemini_storage(tmp_path):
    storage = TokenStorage(tmp_path / "auth_tokens.json")
    storage.set_provider("gemini", {
        "access_token": "expired-access",
        "refresh_token": "gem-refresh",
        "expires_at": time.time() - 100,
    })

    with patch("src.oauth.TokenStorage", return_value=storage):
        with patch("src.oauth.refresh_gemini_token", return_value={"access_token": "fresh-access"}) as refresh:
            assert get_valid_token("antigravity") == "fresh-access"
            refresh.assert_called_once()


def test_refresh_gemini_token_rejects_missing_access_token():
    response = MagicMock()
    response.read.return_value = json.dumps({"expires_in": 3600}).encode("utf-8")
    response.__enter__.return_value = response

    with patch("urllib.request.urlopen", return_value=response):
        with pytest.raises(ValueError, match="access token"):
            refresh_gemini_token({"refresh_token": "gem-refresh-123"})


@pytest.mark.parametrize("expires_at", [None, "not-a-number", float("nan"), 0, -1])
def test_get_valid_token_rejects_invalid_stored_google_expiry(tmp_path, expires_at):
    storage = TokenStorage(tmp_path / "auth_tokens.json")
    storage.set_provider("gemini", {
        "access_token": "stored-access",
        "refresh_token": "stored-refresh",
        "expires_at": expires_at,
    })
    with patch("src.oauth.TokenStorage", return_value=storage):
        with pytest.raises(ValueError, match="token expiry is invalid"):
            get_valid_token("antigravity")


def test_get_valid_token_rejects_empty_stored_google_access_token(tmp_path):
    storage = TokenStorage(tmp_path / "auth_tokens.json")
    storage.set_provider("gemini", {
        "access_token": "",
        "refresh_token": "stored-refresh",
        "expires_at": time.time() + 3600,
    })
    with patch("src.oauth.TokenStorage", return_value=storage):
        with pytest.raises(ValueError, match="access token is missing"):
            get_valid_token("gemini")


def test_get_valid_token_rejects_empty_refreshed_google_access_token(tmp_path):
    storage = TokenStorage(tmp_path / "auth_tokens.json")
    storage.set_provider("gemini", {
        "access_token": "expired-access",
        "refresh_token": "stored-refresh",
        "expires_at": time.time() - 100,
    })
    with patch("src.oauth.TokenStorage", return_value=storage):
        with patch("src.oauth.refresh_gemini_token", return_value={"access_token": ""}):
            with pytest.raises(ValueError, match="access token is missing"):
                get_valid_token("gemini")


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
