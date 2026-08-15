"""OpenAI-compatible LLM client and helper.

Provides a unified interface for model calls across any OpenAI-compatible
endpoint (OpenAI, OpenRouter, Groq, Ollama, vLLM, DeepSeek, LocalAI, etc.).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def get_llm_config(cfg: dict) -> dict[str, Any]:
    """Extract LLM configuration with environment variable fallbacks."""
    llm_cfg = cfg.get("llm") or {}
    scoring_cfg = cfg.get("scoring") or {}

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
    model = (
        os.environ.get("OPENAI_MODEL")
        or llm_cfg.get("model")
        or scoring_cfg.get("model")
        or "gpt-4o-mini"
    )
    prefix = (
        os.environ.get("OPENAI_MODEL_PREFIX")
        or llm_cfg.get("prefix")
        or ""
    )

    full_model = f"{prefix}{model}" if prefix else model

    return {
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": full_model,
        "raw_model": model,
        "prefix": prefix,
    }


def complete(
    messages: list[dict[str, str]],
    cfg: dict,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> str:
    """Make a chat completion request to an OpenAI-compatible endpoint.

    Uses the openai SDK if installed, otherwise falls back to standard urllib
    to avoid hard dependency issues.
    """
    llm_conf = get_llm_config(cfg)
    base_url = llm_conf["base_url"]
    api_key = llm_conf["api_key"]
    model = llm_conf["model"]

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
