"""OpenAI-compatible and Native Subscription LLM client and helper.

Provides a unified interface for model calls across:
- Direct BYOK OpenAI-compatible endpoints (OpenRouter, Groq, Ollama, DeepSeek, LocalAI, etc.)
- Native AI Subscriptions (Claude Code Pro/Max, ChatGPT/Codex Plus/Pro, GitHub Copilot, Google Antigravity / Gemini)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .oauth import ANTIGRAVITY_CONFIG, TokenStorage, get_valid_token


def get_llm_config(cfg: dict) -> dict[str, Any]:
    """Extract LLM configuration with environment variable fallbacks."""
    llm_cfg = cfg.get("llm") or {}
    scoring_cfg = cfg.get("scoring") or {}

    provider = (
        os.environ.get("OPENAI_PROVIDER")
        or llm_cfg.get("provider")
        or "openai"
    ).lower().strip()

    base_url = (
        os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("OPENAI_API_BASE")
        or llm_cfg.get("base_url")
        or llm_cfg.get("endpoint")
        or "https://api.openai.com/v1"
    )
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or llm_cfg.get("api_key")
        or ""
    )
    raw_model = (
        os.environ.get("OPENAI_MODEL")
        or llm_cfg.get("model")
        or scoring_cfg.get("model")
        or "gpt-4o-mini"
    )
    raw_prefix = (
        os.environ.get("OPENAI_MODEL_PREFIX")
        or llm_cfg.get("prefix")
        or ""
    )

    clean_prefix = str(raw_prefix).strip().rstrip("/")
    clean_model = str(raw_model).strip() or "gpt-4o-mini"

    if provider == "openai" and clean_prefix:
        if clean_model.startswith(f"{clean_prefix}/"):
            full_model = clean_model
        else:
            full_model = f"{clean_prefix}/{clean_model.lstrip('/')}"
    else:
        full_model = clean_model

    return {
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": full_model,
        "raw_model": raw_model,
        "prefix": raw_prefix,
    }


def _complete_claude(
    messages: list[dict[str, str]],
    model: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> str:
    """Call Anthropic Claude via native subscription token (matches 9router & CLIProxyAPI)."""
    token = get_valid_token("claude")
    endpoint = "https://api.anthropic.com/v1/messages?beta=true"

    system_prompt = ""
    claude_messages = []
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        else:
            claude_messages.append({"role": m["role"], "content": m["content"]})

    if not model or model == "gpt-4o-mini":
        model = "claude-sonnet-5"

    payload: dict[str, Any] = {
        "model": model,
        "messages": claude_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_prompt:
        payload["system"] = system_prompt

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Anthropic-Version": "2023-06-01",
        "Anthropic-Beta": "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14",
        "Anthropic-Dangerous-Direct-Browser-Access": "true",
        "User-Agent": "claude-cli/2.1.220 (external, cli)",
        "X-App": "cli",
        "X-Stainless-Runtime": "node",
        "X-Stainless-Lang": "js",
        "X-Stainless-Retry-Count": "0",
        "Accept": "application/json",
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        content_blocks = data.get("content", [])
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        return "".join(text_parts)


def _complete_codex(
    messages: list[dict[str, str]],
    model: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> str:
    """Call OpenAI Codex / ChatGPT subscription backend API."""
    token = get_valid_token("codex")
    endpoint = "https://chatgpt.com/backend-api/codex/responses"

    if not model or model == "gpt-4o":
        model = "gpt-5.6-luna"

    storage_data = TokenStorage().get_provider("codex") or {}
    account_id = None
    id_token = storage_data.get("id_token")
    if id_token and "." in id_token:
        try:
            import base64
            p_b64 = id_token.split(".")[1]
            p_b64 += "=" * ((4 - len(p_b64) % 4) % 4)
            claims = json.loads(base64.urlsafe_b64decode(p_b64.encode()))
            account_id = claims.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
        except Exception:
            pass

    input_items = []
    instructions = ""
    for m in messages:
        if m["role"] == "system":
            instructions = m["content"]
        else:
            input_items.append({
                "type": "message",
                "role": m["role"],
                "content": [{"type": "input_text", "text": m["content"]}],
            })

    payload: dict[str, Any] = {
        "model": model,
        "input": input_items,
        "stream": True,
        "store": False,
    }
    if instructions:
        payload["instructions"] = instructions

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Originator": "codex_cli_rs",
        "User-Agent": "codex_cli_rs/0.136.0",
        "Accept": "text/event-stream",
    }
    if account_id:
        headers["ChatGPT-Account-ID"] = account_id

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        full_text = []
        for line_bytes in resp:
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                evt = json.loads(data_str)
                event_type = evt.get("type")
                if event_type == "response.output_text.delta":
                    full_text.append(evt.get("delta", ""))
                elif event_type == "response.output_item.done":
                    item = evt.get("item") or {}
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "text" and not full_text:
                                full_text.append(c.get("text", ""))
            except Exception:
                continue

        return "".join(full_text)


def _complete_copilot(
    messages: list[dict[str, str]],
    model: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> str:
    """Call GitHub Copilot chat completions or Anthropic /v1/messages endpoint (9router/cliproxyapi logic)."""
    token = get_valid_token("copilot")

    if not model:
        model = "gpt-5.6-luna"

    if "claude" in model.lower():
        endpoint = "https://api.githubcopilot.com/v1/messages"
        system_prompt = ""
        claude_messages = []
        for m in messages:
            if m["role"] == "system":
                system_prompt = m["content"]
            else:
                claude_messages.append({"role": m["role"], "content": m["content"]})

        payload = {
            "model": model,
            "messages": claude_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "copilot-integration-id": "vscode-chat",
            "editor-version": "vscode/1.110.0",
            "editor-plugin-version": "copilot-chat/0.38.0",
            "user-agent": "GitHubCopilotChat/0.38.0",
            "anthropic-version": "2023-06-01",
            "x-github-api-version": "2025-04-01",
            "Accept": "application/json",
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_blocks = data.get("content", [])
            text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
            return "".join(text_parts)

    endpoint = "https://api.githubcopilot.com/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "copilot-integration-id": "vscode-chat",
        "editor-version": "vscode/1.110.0",
        "editor-plugin-version": "copilot-chat/0.38.0",
        "user-agent": "GitHubCopilotChat/0.38.0",
        "openai-intent": "conversation-panel",
        "x-github-api-version": "2025-04-01",
        "Accept": "application/json",
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"] or ""


def _complete_gemini(
    messages: list[dict[str, str]],
    model: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> str:
    """Call Google Gemini / Antigravity via Google Code Assist."""
    token = get_valid_token("gemini")

    storage_data = TokenStorage().get_provider("gemini") or {}
    project_id = storage_data.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Antigravity authentication has no Google Cloud project; please reconnect.")
    project_id = project_id.strip()

    if not model or "gpt" in model:
        model = "gemini-3.6-flash"

    model_map = {
        "gemini-3.7-flash-high": "gemini-3.7-flash-tiered(high)",
        "gemini-3.7-flash-medium": "gemini-3.7-flash-tiered(medium)",
        "gemini-3.7-flash-low": "gemini-3.7-flash-tiered(low)",
        "gemini-3.6-flash-high": "gemini-3.6-flash-tiered(high)",
        "gemini-3.6-flash-medium": "gemini-3.6-flash-tiered(medium)",
        "gemini-3.6-flash-low": "gemini-3.6-flash-tiered(low)",
    }
    upstream_model = model_map.get(model, model)

    contents = []
    system_instruction = None
    for m in messages:
        if m["role"] == "system":
            system_instruction = {"parts": [{"text": m["content"]}]}
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

    # For Gemini 2.5 / 3.x series, internal reasoning/thinking tokens are charged against
    # maxOutputTokens. Allocate extra headroom so thinking tokens never starve the response text.
    gemini_max_tokens = max(max_tokens + 4096, 8192)

    gemini_req: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": gemini_max_tokens,
            "temperature": temperature,
        },
    }
    if system_instruction:
        gemini_req["systemInstruction"] = system_instruction

    payload = {
        "project": project_id,
        "model": upstream_model,
        "request": gemini_req,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": ANTIGRAVITY_CONFIG["user_agent"],
        "x-request-source": "local",
        "Accept": "application/json",
    }

    endpoints = [
        "https://daily-cloudcode-pa.googleapis.com/v1internal:generateContent",
        "https://cloudcode-pa.googleapis.com/v1internal:generateContent",
    ]

    last_err = None
    for endpoint in endpoints:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_obj = data.get("response") or data
                candidates = response_obj.get("candidates", [])
                if not candidates:
                    return ""
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts)
        except urllib.error.HTTPError as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise last_err
    return ""


def complete(
    messages: list[dict[str, str]],
    cfg: dict,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> str:
    """Make a completion request across subscription providers or OpenAI-compat endpoint."""
    llm_conf = get_llm_config(cfg)
    provider = llm_conf["provider"]
    base_url = llm_conf["base_url"]
    api_key = llm_conf["api_key"]
    model = llm_conf["model"]

    # Native Subscription Providers
    try:
        if provider == "claude":
            return _complete_claude(messages, model, max_tokens=max_tokens, temperature=temperature)
        elif provider in ("codex", "chatgpt"):
            return _complete_codex(messages, model, max_tokens=max_tokens, temperature=temperature)
        elif provider in ("copilot", "github"):
            return _complete_copilot(messages, model, max_tokens=max_tokens, temperature=temperature)
        elif provider in ("gemini", "antigravity"):
            return _complete_gemini(messages, model, max_tokens=max_tokens, temperature=temperature)
    except Exception as e:
        raise RuntimeError(f"Subscription LLM ({provider}) failed: {e}") from e

    # Standard OpenAI-Compatible Endpoint (BYOK)
    # Try official SDK first if available
    try:
        import openai

        client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "no-key",
        )
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""
    except ImportError:
        pass

    # Standard library urllib fallback
    endpoint_url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API request failed ({e.code}): {body}") from e
    except Exception as e:
        raise RuntimeError(f"LLM API request failed: {e}") from e
