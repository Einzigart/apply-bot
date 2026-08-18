"""Dynamic model catalog fetcher and discovery for AI providers.

Queries live endpoints (e.g. Copilot /models, Codex /backend-api/codex/models,
Anthropic /v1/models, Google Gemini API, OpenAI-compatible /v1/models) and falls
back to static catalogs from router-for-me/models repository.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from .oauth import get_valid_token

# Remote fallback catalogs (periodically updated upstream without needing code changes)
REMOTE_MODELS_URLS = [
    "https://raw.githubusercontent.com/router-for-me/models/refs/heads/main/models.json",
    "https://models.router-for.me/models.json",
]

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
CACHE_TTL = 3600.0  # 1 hour


def _fetch_json(url: str, headers: dict[str, str] | None = None, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": "apply-bot/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_remote_catalog() -> dict[str, Any]:
    """Fetch the latest global model catalog from remote repository."""
    for url in REMOTE_MODELS_URLS:
        try:
            return _fetch_json(url, timeout=5.0)
        except Exception:
            continue
    return {}


def list_models_for_provider(provider: str, *, cfg: dict | None = None) -> list[dict[str, str]]:
    """Return available model IDs and names for a given provider (live or remote synced)."""
    provider = (provider or "openai").lower().strip()
    now = time.time()

    cache_key = f"{provider}"
    if cache_key in _CACHE:
        ts, models = _CACHE[cache_key]
        if now - ts < CACHE_TTL:
            return models

    models: list[dict[str, str]] = []

    try:
        if provider == "copilot":
            token = get_valid_token("copilot")
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Copilot-Integration-Id": "vscode-chat",
                "editor-version": "vscode/1.110.0",
                "editor-plugin-version": "copilot-chat/0.38.0",
                "user-agent": "GitHubCopilotChat/0.38.0",
                "x-github-api-version": "2025-04-01",
            }
            data = _fetch_json("https://api.githubcopilot.com/models", headers=headers)
            items = data.get("data", []) if isinstance(data, dict) else []
            for item in items:
                if item.get("capabilities", {}).get("type") == "chat" and item.get("policy", {}).get("state") != "disabled":
                    m_id = item.get("id")
                    name = item.get("name") or m_id
                    if m_id:
                        models.append({"id": m_id, "name": name})

        elif provider in ("codex", "chatgpt"):
            token = get_valid_token("codex")
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Originator": "codex_cli_rs",
                "User-Agent": "codex_cli_rs/0.144.6",
            }
            url = "https://chatgpt.com/backend-api/codex/models?client_version=0.144.6"
            data = _fetch_json(url, headers=headers)
            items = data.get("models", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for item in items:
                m_id = item.get("slug") or item.get("id")
                name = item.get("display_name") or item.get("name") or m_id
                if m_id:
                    models.append({"id": m_id, "name": name})

        elif provider == "claude":
            token = get_valid_token("claude")
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "anthropic-version": "2023-06-01",
            }
            try:
                data = _fetch_json("https://api.anthropic.com/v1/models", headers=headers)
                items = data.get("data", [])
                for item in items:
                    m_id = item.get("id")
                    name = item.get("display_name") or m_id
                    if m_id:
                        models.append({"id": m_id, "name": name})
            except Exception:
                pass

        elif provider in ("gemini", "antigravity"):
            remote = fetch_remote_catalog()
            entries = remote.get("antigravity") or remote.get("gemini") or []
            for entry in entries:
                m_id = entry.get("id")
                name = entry.get("display_name") or entry.get("name") or m_id
                if m_id:
                    models.append({"id": m_id, "name": name})

        elif provider == "openai" and cfg:
            # Query custom OpenAI / OpenRouter / local endpoint /models
            llm_cfg = cfg.get("llm") or {}
            base_url = (llm_cfg.get("endpoint") or llm_cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
            api_key = llm_cfg.get("api_key", "")
            headers = {"Accept": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            data = _fetch_json(f"{base_url}/models", headers=headers)
            items = data.get("data", []) if isinstance(data, dict) else []
            for item in items:
                m_id = item.get("id")
                if m_id:
                    models.append({"id": m_id, "name": item.get("name") or m_id})

    except Exception:
        pass

    # If live fetch returned no models or provider is Gemini/offline, lookup remote catalog
    if not models:
        remote = fetch_remote_catalog()
        key_map = {
            "claude": "claude",
            "codex": "codex-plus",
            "chatgpt": "codex-plus",
            "copilot": "github",
            "gemini": "gemini",
            "antigravity": "antigravity",
        }
        sec_key = key_map.get(provider, provider)
        entries = remote.get(sec_key) or []
        for entry in entries:
            m_id = entry.get("id")
            name = entry.get("display_name") or entry.get("name") or m_id
            if m_id:
                models.append({"id": m_id, "name": name})

    # Hardcoded safety fallback if remote network is unreachable
    if not models:
        defaults = {
            "claude": [
                {"id": "claude-sonnet-5", "name": "Claude Sonnet 5"},
                {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
                {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"},
                {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"},
            ],
            "codex": [
                {"id": "gpt-5.6-luna", "name": "GPT 5.6 Luna"},
                {"id": "gpt-5.6-terra", "name": "GPT 5.6 Terra"},
                {"id": "gpt-5.5", "name": "GPT 5.5"},
                {"id": "gpt-5.4-mini", "name": "GPT 5.4 Mini"},
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            ],
            "copilot": [
                {"id": "gpt-5.6-luna", "name": "GPT 5.6 Luna"},
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "claude-sonnet-5", "name": "Claude Sonnet 5"},
                {"id": "claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
                {"id": "o1-mini", "name": "o1-mini"},
            ],
            "gemini": [
                {"id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash"},
                {"id": "gemini-3.7-flash-medium", "name": "Gemini 3.7 Flash Medium"},
                {"id": "gemini-3.1-pro", "name": "Gemini 3.1 Pro"},
                {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
                {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
                {"id": "gemini-3.7-flash-high", "name": "Gemini 3.7 Flash (High)"},
            ],
            "openai": [
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
                {"id": "gpt-4o", "name": "GPT-4o"},
            ],
        }
        models = defaults.get(provider, [{"id": "gpt-4o-mini", "name": "GPT-4o Mini"}])

    _CACHE[cache_key] = (now, models)
    return models
