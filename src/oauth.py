"""OAuth token manager and flows for subscription AI providers.

Supports:
- Claude Code (Anthropic Pro/Max) via PKCE Authorization Code Flow
- OpenAI ChatGPT / Codex (Plus/Pro) via PKCE Authorization Code Flow
- GitHub Copilot via Device Code Flow
- Google Antigravity via standard Google OAuth 2.0 (the legacy `gemini` key is
  retained for existing stored credentials)
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import platform
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .config import DATA_DIR

AUTH_TOKENS_PATH = DATA_DIR / "auth_tokens.json"

# Public OAuth Client IDs & Endpoints
CLAUDE_CONFIG = {
    "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
    "auth_url": "https://claude.ai/oauth/authorize",
    "token_url": "https://platform.claude.com/v1/oauth/token",
    "scopes": ["user:profile", "user:inference", "user:sessions:claude_code", "user:mcp_servers", "user:file_upload"],
    "port": 54545,
    "redirect_uri": "http://localhost:54545/callback",
    "default_model": "claude-sonnet-5",
    "models": [
        "claude-sonnet-5",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
}

CODEX_CONFIG = {
    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
    "auth_url": "https://auth.openai.com/oauth/authorize",
    "token_url": "https://auth.openai.com/oauth/token",
    "scopes": ["openid", "profile", "email", "offline_access"],
    "port": 1455,
    "redirect_uri": "http://localhost:1455/auth/callback",
    "default_model": "gpt-5.6-luna",
    "models": [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.5",
        "gpt-5.4-mini",
        "gpt-4o",
        "gpt-4o-mini",
        "o1",
        "o1-mini",
        "o3-mini",
    ],
}

GITHUB_COPILOT_CONFIG = {
    "client_id": "Iv1.b507a08c87ecfe98",
    "device_code_url": "https://github.com/login/device/code",
    "token_url": "https://github.com/login/oauth/access_token",
    "copilot_token_url": "https://api.github.com/copilot_internal/v2/token",
    "scopes": "read:user",
    "user_agent": "GitHubCopilotChat/0.38.0",
    # The active 9router Copilot refresh profile sends this transport version.
    "api_version": "2025-04-01",
    "default_model": "gpt-5.6-luna",
    "models": [
        "gpt-5.6-luna",
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3.5-sonnet",
        "claude-sonnet-5",
        "o1-mini",
    ],
}

COPILOT_DEFAULT_INTERVAL = 5
COPILOT_DEFAULT_DEVICE_EXPIRY = 900
_COPILOT_REFRESH_LOCK = threading.Lock()

ANTIGRAVITY_CONFIG = {
    "client_id": "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com",
    "client_secret": "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",
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "scopes": [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ],
    "port": 51121,
    "redirect_uri": "http://localhost:51121/oauth-callback",
    "callback_path": "/oauth-callback",
    "load_code_assist_url": "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
    "onboard_user_url": "https://cloudcode-pa.googleapis.com/v1internal:onboardUser",
    # This is the current Antigravity IDE fingerprint used by 9router. It is
    # intentionally stable across hosts because the upstream checks the client.
    "user_agent": "antigravity/ide/2.11.0 darwin/arm64",
    "default_model": "gemini-3.6-flash",
    "models": [
        "gemini-3.6-flash",
        "gemini-3.7-flash-medium",
        "gemini-3.1-pro",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3.7-flash-high",
        "gemini-3.7-flash-low",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking",
    ],
}

# Compatibility name only: existing apply-bot credentials are stored under
# `gemini`, but this flow is Antigravity, not Gemini CLI.
GEMINI_CONFIG = ANTIGRAVITY_CONFIG

GOOGLE_PROVIDER_STORAGE_KEY = "gemini"


def _antigravity_metadata() -> dict[str, int]:
    """Return Antigravity's numeric ClientMetadata enum values."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        platform_id = 2 if machine == "arm64" else 1
    elif system == "linux":
        platform_id = 4 if machine == "aarch64" else 3
    elif system == "windows":
        platform_id = 5
    else:
        platform_id = 0
    return {"ideType": 9, "platform": platform_id, "pluginType": 2}


def normalize_provider_key(provider: str) -> str:
    """Map the public Antigravity alias to its legacy storage key."""
    return GOOGLE_PROVIDER_STORAGE_KEY if provider.lower() in {"gemini", "antigravity"} else provider.lower()


def _validate_google_expires_in(value: Any, *, context: str) -> float:
    try:
        expires_in = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{context} returned an invalid token expiry.") from exc
    if not math.isfinite(expires_in) or expires_in <= 0:
        raise ValueError(f"{context} returned an invalid token expiry.")
    return expires_in


def _validate_google_token_response(tokens: Any, *, context: str, previous_refresh_token: str | None = None) -> tuple[str, str, float]:
    if not isinstance(tokens, dict):
        raise ValueError(f"{context} returned an invalid token response.")
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError(f"{context} did not return an access token.")

    refresh_token = tokens.get("refresh_token")
    if refresh_token is None and previous_refresh_token:
        refresh_token = previous_refresh_token
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise ValueError(f"{context} did not return a refresh token.")

    expires_in = _validate_google_expires_in(tokens.get("expires_in"), context=context)
    return access_token, refresh_token, expires_in


def _validate_stored_google_credentials(token_data: Any, *, provider: str) -> float:
    """Validate persisted Antigravity credentials before refresh or use."""
    if not isinstance(token_data, dict):
        raise ValueError(f"Stored {provider} authentication is invalid; please log in again.")
    raw_expires_at = token_data.get("expires_at")
    try:
        expires_at = float(raw_expires_at)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Stored {provider} token expiry is invalid; please log in again.") from exc
    if not math.isfinite(expires_at) or expires_at <= 0:
        raise ValueError(f"Stored {provider} token expiry is invalid; please log in again.")
    return expires_at


def _validate_stored_google_access_token(token_data: Any, *, provider: str) -> str:
    if not isinstance(token_data, dict):
        raise ValueError(f"Stored {provider} authentication is invalid; please log in again.")
    access_token = token_data.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError(f"Stored {provider} access token is missing; please log in again.")
    return access_token


ANTIGRAVITY_RETRYABLE_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})
# Keep the complete post-OAuth project setup below the five-minute callback
# window: at most 2 x 10s per request, 5 onboarding polls, and short waits.
ANTIGRAVITY_REQUEST_ATTEMPTS = 2
ANTIGRAVITY_REQUEST_TIMEOUT = 10
ANTIGRAVITY_REQUEST_RETRY_DELAY = 1
ANTIGRAVITY_ONBOARD_ATTEMPTS = 5
ANTIGRAVITY_ONBOARD_RETRY_DELAY = 2


def _antigravity_request_json(url: str, body: dict[str, Any], headers: dict[str, str], *, context: str) -> Any:
    """POST JSON to Antigravity with bounded retries for transient failures."""
    last_error: Exception | None = None
    for attempt in range(1, ANTIGRAVITY_REQUEST_ATTEMPTS + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=ANTIGRAVITY_REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in ANTIGRAVITY_RETRYABLE_HTTP_STATUS:
                raise RuntimeError(f"Antigravity {context} failed with HTTP {exc.code}.") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            last_error = exc

        if attempt < ANTIGRAVITY_REQUEST_ATTEMPTS:
            time.sleep(ANTIGRAVITY_REQUEST_RETRY_DELAY)

    detail = f" after {ANTIGRAVITY_REQUEST_ATTEMPTS} attempts"
    raise RuntimeError(f"Antigravity {context} failed{detail}; please try again.") from last_error


def generate_pkce(verifier_bytes: int = 64) -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(verifier_bytes)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


class TokenStorage:
    """Read/write data/auth_tokens.json with in-process caching."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or AUTH_TOKENS_PATH)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_provider(self, provider: str) -> dict[str, Any] | None:
        all_tokens = self.load()
        return all_tokens.get(provider)

    def set_provider(self, provider: str, data: dict[str, Any]) -> None:
        all_tokens = self.load()
        all_tokens[provider] = data
        self.save(all_tokens)

    def delete_provider(self, provider: str) -> None:
        all_tokens = self.load()
        if provider in all_tokens:
            del all_tokens[provider]
            self.save(all_tokens)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Local HTTP callback listener for browser OAuth redirects."""

    server: OAuthServer

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.server.expected_path:
            self.send_error(404)
            return
        params = urllib.parse.parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        self.server.result_code = code
        self.server.result_state = state
        self.server.result_error = error

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if error:
            html = f"<html><body style='font-family:sans-serif;padding:2rem;text-align:center;'><h2>Authentication Failed</h2><p>{error}</p><p>You can close this tab.</p></body></html>"
        else:
            html = "<html><body style='font-family:sans-serif;padding:2rem;text-align:center;'><h2>Authentication Successful!</h2><p>You can close this tab and return to apply-bot.</p></body></html>"
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        pass


class OAuthServer(HTTPServer):
    expected_path: str = "/callback"
    result_code: str | None = None
    result_state: str | None = None
    result_error: str | None = None


def listen_for_code(
    port: int,
    expected_state: str,
    timeout: float = 300.0,
    *,
    expected_path: str = "/callback",
) -> str:
    """Start local HTTP server on port and wait for callback."""
    server = OAuthServer(("127.0.0.1", port), OAuthCallbackHandler)
    server.expected_path = expected_path
    server.timeout = 1.0
    start = time.time()

    while time.time() - start < timeout:
        server.handle_request()
        if server.result_code or server.result_error:
            break

    code = server.result_code
    state = server.result_state
    error = server.result_error
    server.server_close()

    if error:
        raise RuntimeError(f"OAuth callback error: {error}")
    if not code:
        raise TimeoutError("Authentication timed out waiting for browser callback.")
    if state != expected_state:
        raise ValueError("OAuth state mismatch; possible CSRF.")

    return code


# --- Flow Implementations ---

def start_claude_oauth() -> dict[str, Any]:
    """Execute full Claude OAuth flow with PKCE."""
    verifier, challenge = generate_pkce(32)
    state = secrets.token_urlsafe(32)

    params = {
        "code": "true",
        "client_id": CLAUDE_CONFIG["client_id"],
        "response_type": "code",
        "redirect_uri": CLAUDE_CONFIG["redirect_uri"],
        "scope": " ".join(CLAUDE_CONFIG["scopes"]),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    auth_url = f"{CLAUDE_CONFIG['auth_url']}?{urllib.parse.urlencode(params)}"

    # Try opening browser
    try:
        import webbrowser
        webbrowser.open(auth_url)
    except Exception:
        pass

    code = listen_for_code(CLAUDE_CONFIG["port"], state)
    if "#" in code:
        code = code.split("#")[0]

    payload = {
        "grant_type": "authorization_code",
        "client_id": CLAUDE_CONFIG["client_id"],
        "code": code,
        "redirect_uri": CLAUDE_CONFIG["redirect_uri"],
        "code_verifier": verifier,
        "state": state,
    }
    req = urllib.request.Request(
        CLAUDE_CONFIG["token_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))

    token_data = {
        "provider": "claude",
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in", 86400),
        "expires_at": time.time() + tokens.get("expires_in", 86400),
        "scope": tokens.get("scope"),
        "updated_at": time.time(),
    }
    TokenStorage().set_provider("claude", token_data)
    return token_data


def refresh_claude_token(token_data: dict[str, Any]) -> dict[str, Any]:
    """Refresh expired Claude tokens."""
    refresh_tok = token_data.get("refresh_token")
    if not refresh_tok:
        raise ValueError("No refresh token available for Claude")

    payload = {
        "grant_type": "refresh_token",
        "client_id": CLAUDE_CONFIG["client_id"],
        "refresh_token": refresh_tok,
        "scope": token_data.get("scope") or " ".join(CLAUDE_CONFIG["scopes"]),
    }
    req = urllib.request.Request(
        CLAUDE_CONFIG["token_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))

    token_data["access_token"] = tokens.get("access_token")
    if tokens.get("refresh_token"):
        token_data["refresh_token"] = tokens["refresh_token"]
    expires_in = tokens.get("expires_in", 86400)
    token_data["expires_in"] = expires_in
    token_data["expires_at"] = time.time() + expires_in
    token_data["updated_at"] = time.time()

    TokenStorage().set_provider("claude", token_data)
    return token_data


def start_codex_oauth() -> dict[str, Any]:
    """Execute full ChatGPT / Codex OAuth flow with PKCE."""
    verifier, challenge = generate_pkce(32)
    state = secrets.token_urlsafe(32)

    params = {
        "response_type": "code",
        "client_id": CODEX_CONFIG["client_id"],
        "redirect_uri": CODEX_CONFIG["redirect_uri"],
        "scope": " ".join(CODEX_CONFIG["scopes"]),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex_cli_rs",
        "state": state,
    }
    auth_url = f"{CODEX_CONFIG['auth_url']}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"

    try:
        import webbrowser
        webbrowser.open(auth_url)
    except Exception:
        pass

    code = listen_for_code(CODEX_CONFIG["port"], state, expected_path="/auth/callback")

    payload = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": CODEX_CONFIG["client_id"],
        "code": code,
        "redirect_uri": CODEX_CONFIG["redirect_uri"],
        "code_verifier": verifier,
    }).encode("utf-8")

    req = urllib.request.Request(
        CODEX_CONFIG["token_url"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))

    token_data = {
        "provider": "codex",
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "id_token": tokens.get("id_token"),
        "expires_in": tokens.get("expires_in", 3600),
        "expires_at": time.time() + tokens.get("expires_in", 3600),
        "updated_at": time.time(),
    }
    TokenStorage().set_provider("codex", token_data)
    return token_data


def refresh_codex_token(token_data: dict[str, Any]) -> dict[str, Any]:
    """Refresh expired OpenAI Codex tokens."""
    refresh_tok = token_data.get("refresh_token")
    if not refresh_tok:
        raise ValueError("No refresh token available for Codex")

    payload = json.dumps({
        "grant_type": "refresh_token",
        "client_id": CODEX_CONFIG["client_id"],
        "refresh_token": refresh_tok,
    }).encode("utf-8")

    req = urllib.request.Request(
        CODEX_CONFIG["token_url"],
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))

    token_data["access_token"] = tokens.get("access_token")
    if tokens.get("refresh_token"):
        token_data["refresh_token"] = tokens["refresh_token"]
    if tokens.get("id_token"):
        token_data["id_token"] = tokens["id_token"]
    expires_in = tokens.get("expires_in", 3600)
    token_data["expires_in"] = expires_in
    token_data["expires_at"] = time.time() + expires_in
    token_data["updated_at"] = time.time()

    TokenStorage().set_provider("codex", token_data)
    return token_data


# --- GitHub Copilot Device Code Flow ---

def request_copilot_device_code() -> dict[str, Any]:
    """Request device verification code from GitHub."""
    payload = urllib.parse.urlencode({
        "client_id": GITHUB_COPILOT_CONFIG["client_id"],
        "scope": GITHUB_COPILOT_CONFIG["scopes"],
    }).encode("utf-8")

    req = urllib.request.Request(
        GITHUB_COPILOT_CONFIG["device_code_url"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("GitHub device-code response was invalid.")
    for key in ("user_code", "verification_uri", "device_code"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise RuntimeError(f"GitHub device-code response missing {key}.")
    data["interval"] = _normalize_copilot_interval(data.get("interval"))
    if "expires_in" not in data:
        data["expires_in"] = COPILOT_DEFAULT_DEVICE_EXPIRY
    else:
        data["expires_in"] = _normalize_copilot_device_expiry(data["expires_in"])
    return data


def poll_copilot_device_token(device_code: str, interval: int | None = None) -> dict[str, Any]:
    """Perform one bounded GitHub device-code poll and report its next state."""
    interval = _normalize_copilot_interval(interval)
    payload = urllib.parse.urlencode({
        "client_id": GITHUB_COPILOT_CONFIG["client_id"],
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        GITHUB_COPILOT_CONFIG["token_url"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("GitHub authentication returned an invalid response.")

    if data.get("access_token"):
        token_data = _complete_copilot_login(data)
        return {"status": "success", "interval": interval, "token_data": token_data}

    error = data.get("error")
    if error == "authorization_pending":
        return {"status": "pending", "interval": interval}
    if error == "slow_down":
        return {"status": "slow_down", "interval": interval + COPILOT_DEFAULT_INTERVAL}
    if error == "expired_token":
        return {"status": "expired", "interval": interval, "message": "GitHub device code expired; please try again."}
    if error == "access_denied":
        return {"status": "error", "interval": interval, "message": "GitHub authorization was denied."}
    raise RuntimeError(f"GitHub authentication error: {data.get('error_description', error)}")


def _normalize_copilot_interval(interval: Any) -> int:
    """Use GitHub's polling interval when valid, otherwise the documented default."""
    try:
        normalized = int(interval)
    except (TypeError, ValueError, OverflowError):
        normalized = COPILOT_DEFAULT_INTERVAL
    return normalized if normalized > 0 else COPILOT_DEFAULT_INTERVAL


def _normalize_copilot_device_expiry(expires_in: Any) -> int:
    """Validate a present GitHub device-code lifetime."""
    try:
        normalized = int(expires_in)
    except (TypeError, ValueError, OverflowError):
        raise RuntimeError("GitHub device-code response contained an invalid expires_in.") from None
    if normalized <= 0:
        raise RuntimeError("GitHub device-code response contained a nonpositive expires_in.")
    return normalized


def _complete_copilot_login(github_token_data: dict[str, Any]) -> dict[str, Any]:
    """Exchange a newly issued GitHub token and persist one complete Copilot record."""
    github_access_token = github_token_data.get("access_token")
    if not isinstance(github_access_token, str) or not github_access_token.strip():
        raise RuntimeError("GitHub authentication did not return an access token.")
    github_expires_at = (
        _github_expiry(github_token_data["expires_in"])
        if "expires_in" in github_token_data else None
    )
    copilot_token_data = refresh_copilot_session_token(github_access_token)
    token_data = {
        "provider": "copilot",
        "github_access_token": github_access_token,
        "github_token_type": github_token_data.get("token_type"),
        "github_scope": github_token_data.get("scope"),
        "github_expires_in": github_token_data.get("expires_in"),
        "github_expires_at": github_expires_at,
        "github_refresh_token": github_token_data.get("refresh_token"),
        "github_refresh_token_expires_in": github_token_data.get("refresh_token_expires_in"),
        "copilot_token": copilot_token_data["token"],
        "copilot_token_expires_at": _normalize_copilot_expiry(copilot_token_data.get("expires_at")),
        "updated_at": time.time(),
    }
    TokenStorage().set_provider("copilot", token_data)
    return token_data


def refresh_github_access_token(token_data: dict[str, Any]) -> dict[str, Any]:
    """Rotate a GitHub OAuth access token using its refresh token."""
    refresh_token = token_data.get("github_refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise ValueError("GitHub access token expired and no refresh token is available; please log in again.")

    payload = urllib.parse.urlencode({
        "client_id": GITHUB_COPILOT_CONFIG["client_id"],
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode("utf-8")
    req = urllib.request.Request(
        GITHUB_COPILOT_CONFIG["token_url"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        refreshed = json.loads(resp.read().decode("utf-8"))
    if not isinstance(refreshed, dict):
        raise RuntimeError("GitHub refresh returned an invalid response.")
    access_token = refreshed.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise RuntimeError("GitHub refresh response did not contain an access token.")

    if "expires_in" in refreshed:
        github_expires_at = _github_expiry(refreshed["expires_in"])
    else:
        github_expires_at = None

    updated = dict(token_data)
    updated["github_access_token"] = access_token
    for key in ("token_type", "scope"):
        if key in refreshed:
            updated[f"github_{key}"] = refreshed[key]
    if "refresh_token" in refreshed and refreshed["refresh_token"]:
        updated["github_refresh_token"] = refreshed["refresh_token"]
    if "refresh_token_expires_in" in refreshed:
        updated["github_refresh_token_expires_in"] = refreshed["refresh_token_expires_in"]

    if "expires_in" in refreshed:
        updated["github_expires_in"] = refreshed["expires_in"]
        updated["github_expires_at"] = github_expires_at
    else:
        updated["github_expires_in"] = None
        updated["github_expires_at"] = None
    return updated


def _github_expiry(expires_in: Any) -> float | None:
    """Convert GitHub's optional lifetime, rejecting malformed present values."""
    if expires_in is None:
        raise RuntimeError("GitHub access-token response contained an invalid expires_in.")
    try:
        seconds = float(expires_in)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError("GitHub access-token response contained an invalid expires_in.") from exc
    if not math.isfinite(seconds):
        raise RuntimeError("GitHub access-token response contained a non-finite expires_in.")
    if seconds <= 0:
        raise RuntimeError("GitHub access-token response contained a nonpositive expires_in.")
    return time.time() + seconds


def _normalize_copilot_expiry(expires_at: Any) -> float:
    """Return a usable Copilot session expiry, with a bounded fallback for omission."""
    if expires_at is None:
        return time.time() + 1800
    try:
        normalized = float(expires_at)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError("GitHub Copilot token response contained an invalid expiry.") from exc
    if not math.isfinite(normalized):
        raise RuntimeError("GitHub Copilot token response contained a non-finite expiry.")
    if normalized <= 0:
        raise RuntimeError("GitHub Copilot token response contained an invalid expiry.")
    return normalized


def refresh_copilot_session_token(github_access_token: str) -> dict[str, Any]:
    """Exchange GitHub access token for a Copilot API token."""
    req = urllib.request.Request(
        GITHUB_COPILOT_CONFIG["copilot_token_url"],
        headers={
            "Authorization": f"token {github_access_token}",
            "User-Agent": GITHUB_COPILOT_CONFIG["user_agent"],
            "Accept": "application/json",
            "X-GitHub-Api-Version": GITHUB_COPILOT_CONFIG["api_version"],
            "editor-version": "vscode/1.110.0",
            "editor-plugin-version": "copilot-chat/0.38.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("token"), str) or not data["token"].strip():
        raise RuntimeError("GitHub Copilot token response did not contain a session token.")
    return data


# --- Google Antigravity Flow (legacy `gemini` storage key) ---

def start_gemini_oauth() -> dict[str, Any]:
    """Execute the Antigravity OAuth flow while preserving the `gemini` key."""
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": ANTIGRAVITY_CONFIG["client_id"],
        "response_type": "code",
        "redirect_uri": ANTIGRAVITY_CONFIG["redirect_uri"],
        "scope": " ".join(ANTIGRAVITY_CONFIG["scopes"]),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{ANTIGRAVITY_CONFIG['auth_url']}?{urllib.parse.urlencode(params)}"

    try:
        import webbrowser
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Keep the registered fixed redirect: this flow opens the browser before
    # starting its listener, so switching to a random loopback port would
    # require a different registered client/flow architecture.
    code = listen_for_code(
        ANTIGRAVITY_CONFIG["port"],
        state,
        expected_path=ANTIGRAVITY_CONFIG["callback_path"],
    )

    payload = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": ANTIGRAVITY_CONFIG["client_id"],
        "client_secret": ANTIGRAVITY_CONFIG["client_secret"],
        "code": code,
        "redirect_uri": ANTIGRAVITY_CONFIG["redirect_uri"],
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTIGRAVITY_CONFIG["token_url"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))

    access_token, refresh_token, expires_in = _validate_google_token_response(
        tokens, context="Antigravity OAuth token exchange"
    )

    # Fetch User Project ID via loadCodeAssist & onboardUser
    project_id = _setup_antigravity_project(access_token)

    token_data = {
        "provider": GOOGLE_PROVIDER_STORAGE_KEY,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "project_id": project_id,
        "expires_in": expires_in,
        "expires_at": time.time() + expires_in,
        "updated_at": time.time(),
    }
    TokenStorage().set_provider(GOOGLE_PROVIDER_STORAGE_KEY, token_data)
    return token_data


def _setup_antigravity_project(access_token: str) -> str:
    """Resolve and, if needed, onboard the real Antigravity companion project."""
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("Antigravity project setup requires a valid access token.")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": ANTIGRAVITY_CONFIG["user_agent"],
        "x-request-source": "local",
    }

    data = _antigravity_request_json(
        ANTIGRAVITY_CONFIG["load_code_assist_url"],
        {"metadata": _antigravity_metadata()},
        headers,
        context="loadCodeAssist",
    )

    project = data.get("cloudaicompanionProject") if isinstance(data, dict) else None
    if isinstance(project, dict):
        project = project.get("id")
    if isinstance(project, str) and project.strip():
        return project.strip()

    tier_id = "legacy-tier"
    for tier in data.get("allowedTiers", []) if isinstance(data, dict) else []:
        if isinstance(tier, dict) and tier.get("isDefault") is True:
            candidate = tier.get("id")
            if isinstance(candidate, str) and candidate.strip():
                tier_id = candidate.strip()
                break

    for attempt in range(ANTIGRAVITY_ONBOARD_ATTEMPTS):
        onboard_body = {"tierId": tier_id, "metadata": _antigravity_metadata()}
        data = _antigravity_request_json(
            ANTIGRAVITY_CONFIG["onboard_user_url"],
            onboard_body,
            headers,
            context="onboardUser",
        )
        if isinstance(data, dict) and data.get("done") is True:
            project = (data.get("response") or {}).get("cloudaicompanionProject")
            if isinstance(project, dict):
                project = project.get("id")
            if isinstance(project, str) and project.strip():
                return project.strip()
            raise RuntimeError("Antigravity onboarding completed without a project ID.")
        if attempt < ANTIGRAVITY_ONBOARD_ATTEMPTS - 1:
            time.sleep(ANTIGRAVITY_ONBOARD_RETRY_DELAY)

    raise TimeoutError(
        f"Antigravity project onboarding timed out after {ANTIGRAVITY_ONBOARD_ATTEMPTS} polls. Please try again."
    )


def refresh_gemini_token(token_data: dict[str, Any]) -> dict[str, Any]:
    """Refresh an Antigravity token stored under the legacy `gemini` key."""
    refresh_tok = token_data.get("refresh_token")
    if not refresh_tok:
        raise ValueError("No refresh token available for Gemini")

    payload = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": GEMINI_CONFIG["client_id"],
        "client_secret": GEMINI_CONFIG["client_secret"],
        "refresh_token": refresh_tok,
    }).encode("utf-8")

    req = urllib.request.Request(
        GEMINI_CONFIG["token_url"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))

    access_token, refresh_token, expires_in = _validate_google_token_response(
        tokens,
        context="Antigravity token refresh",
        previous_refresh_token=refresh_tok,
    )
    updated_token_data = dict(token_data)
    updated_token_data["access_token"] = access_token
    updated_token_data["refresh_token"] = refresh_token
    updated_token_data["expires_in"] = expires_in
    updated_token_data["expires_at"] = time.time() + expires_in
    updated_token_data["updated_at"] = time.time()

    TokenStorage().set_provider(GOOGLE_PROVIDER_STORAGE_KEY, updated_token_data)
    return updated_token_data


def get_valid_token(provider: str) -> str:
    """Retrieve an active access token for provider, auto-refreshing if needed."""
    storage = TokenStorage()
    storage_provider = normalize_provider_key(provider)
    token_data = storage.get_provider(storage_provider)
    if not token_data:
        raise ValueError(f"No authentication found for provider '{provider}'. Please log in first.")

    now = time.time()
    if storage_provider == GOOGLE_PROVIDER_STORAGE_KEY:
        expires_at = _validate_stored_google_credentials(token_data, provider=provider)
    else:
        expires_at = token_data.get("expires_at", 0)

    if provider == "copilot":
        with _COPILOT_REFRESH_LOCK:
            current = storage.get_provider("copilot")
            if current:
                token_data = current
            now = time.time()
            github_refreshed = False
            raw_github_exp = token_data.get("github_expires_at")
            if raw_github_exp is None:
                github_exp = None
            else:
                try:
                    github_exp = float(raw_github_exp)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Stored GitHub access-token expiry is invalid; please log in again.") from exc
                if not math.isfinite(github_exp) or github_exp <= 0:
                    raise ValueError("Stored GitHub access-token expiry is invalid; please log in again.")
            if github_exp is not None and github_exp - now < 300:
                token_data = refresh_github_access_token(token_data)
                storage.set_provider("copilot", token_data)
                github_refreshed = True

            raw_copilot_exp = token_data.get("copilot_token_expires_at")
            if raw_copilot_exp is None:
                copilot_exp = 0
            else:
                try:
                    copilot_exp = float(raw_copilot_exp)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Stored GitHub Copilot session expiry is invalid; please log in again.") from exc
                if not math.isfinite(copilot_exp) or copilot_exp <= 0:
                    raise ValueError("Stored GitHub Copilot session expiry is invalid; please log in again.")
            if github_refreshed or copilot_exp - now < 300:
                gh_token = token_data.get("github_access_token")
                if not gh_token:
                    raise ValueError("Missing GitHub access token for Copilot")
                c_data = refresh_copilot_session_token(gh_token)
                token_data["copilot_token"] = c_data["token"]
                token_data["copilot_token_expires_at"] = _normalize_copilot_expiry(c_data.get("expires_at"))
                token_data["updated_at"] = time.time()
                storage.set_provider("copilot", token_data)
            copilot_token = token_data.get("copilot_token")
            if not isinstance(copilot_token, str) or not copilot_token.strip():
                raise ValueError("GitHub Copilot session token is missing; please log in again.")
            return copilot_token

    if expires_at - now < 300:
        if provider == "claude":
            token_data = refresh_claude_token(token_data)
        elif provider == "codex":
            token_data = refresh_codex_token(token_data)
        elif storage_provider == GOOGLE_PROVIDER_STORAGE_KEY:
            token_data = refresh_gemini_token(token_data)

    if storage_provider == GOOGLE_PROVIDER_STORAGE_KEY:
        return _validate_stored_google_access_token(token_data, provider=provider)
    return token_data.get("access_token") or ""
