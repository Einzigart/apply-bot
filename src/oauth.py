"""OAuth token manager and flows for subscription AI providers.

Supports:
- Claude Code (Anthropic Pro/Max) via PKCE Authorization Code Flow
- OpenAI ChatGPT / Codex (Plus/Pro) via PKCE Authorization Code Flow
- GitHub Copilot via Device Code Flow
- Google Gemini CLI / Antigravity via Google OAuth 2.0 PKCE Flow
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
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

GEMINI_CONFIG = ANTIGRAVITY_CONFIG


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
    result_code: str | None = None
    result_state: str | None = None
    result_error: str | None = None


def listen_for_code(port: int, expected_state: str, timeout: float = 300.0) -> str:
    """Start local HTTP server on port and wait for callback."""
    server = OAuthServer(("127.0.0.1", port), OAuthCallbackHandler)
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
    if state and state != expected_state:
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

    code = listen_for_code(CODEX_CONFIG["port"], state)

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
        return json.loads(resp.read().decode("utf-8"))


def poll_copilot_device_token(device_code: str, interval: int = 5, timeout: float = 300.0) -> dict[str, Any]:
    """Poll GitHub until user confirms device code, then exchange for Copilot token."""
    start = time.time()
    payload = urllib.parse.urlencode({
        "client_id": GITHUB_COPILOT_CONFIG["client_id"],
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }).encode("utf-8")

    github_access_token = None

    while time.time() - start < timeout:
        time.sleep(interval)
        req = urllib.request.Request(
            GITHUB_COPILOT_CONFIG["token_url"],
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if "access_token" in data:
            github_access_token = data["access_token"]
            break
        error = data.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise RuntimeError(f"GitHub authentication error: {data.get('error_description', error)}")

    if not github_access_token:
        raise TimeoutError("GitHub Copilot authentication timed out.")

    # Obtain Copilot internal session token
    copilot_token_data = refresh_copilot_session_token(github_access_token)

    token_data = {
        "provider": "copilot",
        "github_access_token": github_access_token,
        "copilot_token": copilot_token_data.get("token"),
        "copilot_token_expires_at": copilot_token_data.get("expires_at"),
        "updated_at": time.time(),
    }
    TokenStorage().set_provider("copilot", token_data)
    return token_data


def refresh_copilot_session_token(github_access_token: str) -> dict[str, Any]:
    """Exchange GitHub access token for a Copilot API token."""
    req = urllib.request.Request(
        GITHUB_COPILOT_CONFIG["copilot_token_url"],
        headers={
            "Authorization": f"token {github_access_token}",
            "User-Agent": GITHUB_COPILOT_CONFIG["user_agent"],
            "Accept": "application/json",
            "editor-version": "vscode/1.110.0",
            "editor-plugin-version": "copilot-chat/0.38.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- Google Gemini CLI Flow ---

def start_gemini_oauth() -> dict[str, Any]:
    """Execute Google Gemini / Antigravity OAuth flow (exact 9router/cliproxyapi implementation)."""
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(16)

    params = {
        "client_id": ANTIGRAVITY_CONFIG["client_id"],
        "response_type": "code",
        "redirect_uri": ANTIGRAVITY_CONFIG["redirect_uri"],
        "scope": " ".join(ANTIGRAVITY_CONFIG["scopes"]),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{ANTIGRAVITY_CONFIG['auth_url']}?{urllib.parse.urlencode(params)}"

    try:
        import webbrowser
        webbrowser.open(auth_url)
    except Exception:
        pass

    code = listen_for_code(ANTIGRAVITY_CONFIG["port"], state)

    payload = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": ANTIGRAVITY_CONFIG["client_id"],
        "client_secret": ANTIGRAVITY_CONFIG["client_secret"],
        "code": code,
        "redirect_uri": ANTIGRAVITY_CONFIG["redirect_uri"],
        "code_verifier": verifier,
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTIGRAVITY_CONFIG["token_url"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))

    access_token = tokens.get("access_token")

    # Fetch User Project ID via loadCodeAssist & onboardUser
    project_id = _setup_antigravity_project(access_token)

    token_data = {
        "provider": "gemini",
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token"),
        "project_id": project_id,
        "expires_in": tokens.get("expires_in", 3600),
        "expires_at": time.time() + tokens.get("expires_in", 3600),
        "updated_at": time.time(),
    }
    TokenStorage().set_provider("gemini", token_data)
    return token_data


def _setup_antigravity_project(access_token: str) -> str:
    """Query loadCodeAssist and onboardUser to obtain authorized GCP companion project."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "antigravity/ide/2.1.1 darwin/arm64",
    }

    try:
        req = urllib.request.Request(
            "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
            data=json.dumps({"metadata": {"ideType": "ANTIGRAVITY"}}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            proj = data.get("cloudaicompanionProject")
            if isinstance(proj, dict):
                proj = proj.get("id")
            if proj:
                return str(proj).strip()
    except Exception:
        pass

    try:
        onboard_body = {
            "tierId": "free-tier",
            "metadata": {"ideType": 9, "platform": 2, "pluginType": 2}
        }
        req = urllib.request.Request(
            "https://cloudcode-pa.googleapis.com/v1internal:onboardUser",
            data=json.dumps(onboard_body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            proj = data.get("response", {}).get("cloudaicompanionProject", {})
            if isinstance(proj, dict):
                return proj.get("id", "")
            return str(proj)
    except Exception:
        pass

    return ""


def refresh_gemini_token(token_data: dict[str, Any]) -> dict[str, Any]:
    """Refresh Google Gemini access token."""
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

    token_data["access_token"] = tokens.get("access_token")
    if tokens.get("refresh_token"):
        token_data["refresh_token"] = tokens["refresh_token"]
    expires_in = tokens.get("expires_in", 3600)
    token_data["expires_in"] = expires_in
    token_data["expires_at"] = time.time() + expires_in
    token_data["updated_at"] = time.time()

    TokenStorage().set_provider("gemini", token_data)
    return token_data


def get_valid_token(provider: str) -> str:
    """Retrieve an active access token for provider, auto-refreshing if needed."""
    storage = TokenStorage()
    token_data = storage.get_provider(provider)
    if not token_data:
        raise ValueError(f"No authentication found for provider '{provider}'. Please log in first.")

    now = time.time()
    expires_at = token_data.get("expires_at", 0)

    if provider == "copilot":
        copilot_exp = token_data.get("copilot_token_expires_at", 0)
        if copilot_exp - now < 300:
            gh_token = token_data.get("github_access_token")
            if not gh_token:
                raise ValueError("Missing GitHub access token for Copilot")
            c_data = refresh_copilot_session_token(gh_token)
            token_data["copilot_token"] = c_data.get("token")
            token_data["copilot_token_expires_at"] = c_data.get("expires_at", now + 1800)
            token_data["updated_at"] = now
            storage.set_provider("copilot", token_data)
        return token_data.get("copilot_token") or ""

    if expires_at - now < 300:
        if provider == "claude":
            token_data = refresh_claude_token(token_data)
        elif provider == "codex":
            token_data = refresh_codex_token(token_data)
        elif provider == "gemini":
            token_data = refresh_gemini_token(token_data)

    return token_data.get("access_token") or ""
