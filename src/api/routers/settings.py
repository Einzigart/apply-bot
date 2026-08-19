"""Settings, OAuth, and LLM configuration router."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import yaml
from fastapi import APIRouter, HTTPException, Request

from ...db import reset_database
from ...llm import complete, get_llm_config
from ...models_fetcher import list_models_for_provider
from ...oauth import (
    CLAUDE_CONFIG,
    CODEX_CONFIG,
    GEMINI_CONFIG,
    GITHUB_COPILOT_CONFIG,
    TokenStorage,
    poll_copilot_device_token,
    request_copilot_device_code,
    start_claude_oauth,
    start_codex_oauth,
    start_gemini_oauth,
)
from ..schemas import (
    CopilotDeviceCodeResponse,
    CopilotPollRequest,
    SaveSettingsRequest,
    SuccessResponse,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _get_merged_config(data_dir: Path) -> dict:
    base_path = data_dir / "config.yaml"
    if not base_path.exists():
        base_path = data_dir / "config.example.yaml"
    cfg = {}
    if base_path.exists():
        try:
            cfg = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            cfg = {}

    for sec_file in ("secrets.yaml", "config.local.yaml"):
        sec_path = data_dir / sec_file
        if sec_path.exists():
            try:
                sec_cfg = yaml.safe_load(sec_path.read_text(encoding="utf-8")) or {}
                if isinstance(sec_cfg, dict):
                    for k, v in sec_cfg.items():
                        if k in cfg and isinstance(cfg[k], dict) and isinstance(v, dict):
                            cfg[k].update(v)
                        else:
                            cfg[k] = v
            except yaml.YAMLError:
                pass
    return cfg


def _find_chrome_executable(cfg: dict | None = None) -> str | None:
    """Find Google Chrome binary executable across standard, custom, or environment paths."""
    import shutil
    import sys

    # 1. Custom path configured in secrets.yaml / config.yaml (e.g. search.chrome_path or env CHROME_PATH)
    custom_path = os.environ.get("CHROME_PATH") or os.environ.get("GOOGLE_CHROME_BIN")
    if not custom_path and cfg:
        custom_path = (cfg.get("search") or {}).get("chrome_path")
    if custom_path and os.path.exists(custom_path):
        return custom_path

    # 2. System PATH binaries
    for binary_name in ["google-chrome", "chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome.exe"]:
        found = shutil.which(binary_name)
        if found:
            return found

    # 3. Platform standard and alternative installation paths
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            os.path.expanduser("~/Applications/Chromium.app/Contents/MacOS/Chromium"),
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
    else:
        # Linux
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            "/var/lib/flatpak/exports/bin/com.google.Chrome",
            os.path.expanduser("~/.local/share/flatpak/exports/bin/com.google.Chrome"),
        ]

    for path in candidates:
        if path and os.path.exists(path):
            return path

    return None


def _check_chrome_installed(cfg: dict | None = None) -> bool:
    """Check if Google Chrome (or custom Chromium executable) is installed."""
    return _find_chrome_executable(cfg) is not None


@router.get("")
def get_settings(request: Request):
    data_dir: Path = request.app.state.data_dir
    cfg = _get_merged_config(data_dir)
    llm_cfg = cfg.get("llm") or {}
    active_llm = get_llm_config(cfg)
    chrome_path = _find_chrome_executable(cfg)
    chrome_installed = chrome_path is not None
    env_overrides = {
        "base_url": bool(os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")),
        "api_key": bool(os.environ.get("OPENAI_API_KEY")),
        "model": bool(os.environ.get("OPENAI_MODEL")),
        "prefix": bool(os.environ.get("OPENAI_MODEL_PREFIX")),
    }

    raw_api_key = str(active_llm.get("api_key") or llm_cfg.get("api_key") or "").strip()
    has_api_key = bool(raw_api_key)
    masked_suffix = raw_api_key[-4:] if len(raw_api_key) >= 4 else (raw_api_key if raw_api_key else "")
    api_key_masked = f"...{masked_suffix}" if masked_suffix else ""

    safe_cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in cfg.items()}
    if "llm" in safe_cfg and isinstance(safe_cfg["llm"], dict):
        safe_cfg["llm"] = {k: v for k, v in safe_cfg["llm"].items() if k != "api_key"}

    safe_llm_cfg = {k: v for k, v in llm_cfg.items() if k != "api_key"}
    safe_active_llm = {k: v for k, v in active_llm.items() if k != "api_key"}
    safe_llm_cfg["has_api_key"] = has_api_key
    safe_llm_cfg["masked_suffix"] = masked_suffix
    safe_active_llm["has_api_key"] = has_api_key
    safe_active_llm["masked_suffix"] = masked_suffix

    storage_file = data_dir / "storage_state.json"
    has_auth = storage_file.exists()
    auth_mtime = storage_file.stat().st_mtime if has_auth else None

    secrets_path = data_dir / "secrets.yaml"
    sec_cfg = {}
    if secrets_path.exists():
        try:
            sec_cfg = yaml.safe_load(secrets_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            sec_cfg = {}
    sec_filters = sec_cfg.get("filters") or {}

    profile_path = data_dir / "profile.yaml"
    profile_data = {}
    if profile_path.exists():
        try:
            profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            profile_data = {}

    tokens_storage = TokenStorage(data_dir / "auth_tokens.json")
    auth_tokens = tokens_storage.load()
    token_status = {}
    for prov, t_data in auth_tokens.items():
        if isinstance(t_data, dict) and (t_data.get("access_token") or t_data.get("refresh_token") or t_data.get("token")):
            token_status[prov] = {
                "connected": True,
                "expires_at": t_data.get("expires_at") or t_data.get("copilot_token_expires_at"),
            }
        else:
            token_status[prov] = {
                "connected": False,
                "expires_at": None,
            }
    for prov in ("claude", "codex", "copilot", "gemini"):
        if prov not in token_status:
            token_status[prov] = {"connected": False, "expires_at": None}

    safe_oauth_configs = {}
    for k, v in {
        "claude": CLAUDE_CONFIG,
        "codex": CODEX_CONFIG,
        "copilot": GITHUB_COPILOT_CONFIG,
        "gemini": GEMINI_CONFIG,
    }.items():
        cfg_dict = dict(v)
        cfg_dict.pop("client_secret", None)
        safe_oauth_configs[k] = cfg_dict

    return {
        "cfg": safe_cfg,
        "llm_cfg": safe_llm_cfg,
        "active_llm": safe_active_llm,
        "env_overrides": env_overrides,
        "has_auth": has_auth,
        "auth_mtime": auth_mtime,
        "sec_filters": sec_filters,
        "profile": profile_data,
        "has_api_key": has_api_key,
        "masked_suffix": masked_suffix,
        "api_key_masked": api_key_masked,
        "auth_tokens": token_status,
        "oauth_configs": safe_oauth_configs,
        "chrome_installed": chrome_installed,
        "chrome_path": chrome_path,
    }


@router.post("", response_model=SuccessResponse)
def save_settings(payload: SaveSettingsRequest, request: Request):
    data_dir: Path = request.app.state.data_dir
    section = payload.section
    data = payload.data
    secrets_path = data_dir / "secrets.yaml"
    sec_cfg = {}
    if secrets_path.exists():
        try:
            sec_cfg = yaml.safe_load(secrets_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            sec_cfg = {}

    if section == "llm":
        provider = str(data.get("provider", "openai")).strip()
        endpoint = str(data.get("endpoint", "")).strip()
        model = str(data.get("model", "")).strip()
        prefix = str(data.get("prefix", "")).strip()
        api_key = str(data.get("api_key", "")).strip()

        llm_dict = sec_cfg.get("llm") or {}
        llm_dict["provider"] = provider
        llm_dict["endpoint"] = endpoint or "https://api.openai.com/v1"
        llm_dict["model"] = model or "gpt-4o-mini"
        llm_dict["prefix"] = prefix
        if api_key:
            llm_dict["api_key"] = api_key
        sec_cfg["llm"] = llm_dict
        secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
        return SuccessResponse(message=f"LLM settings saved (Provider: {provider}, Model: {llm_dict['model']}).")

    elif section == "filters":
        filter_dict = sec_cfg.get("filters") or {}
        if "company_cooldown_days" in data:
            filter_dict["company_cooldown_days"] = max(0, int(data["company_cooldown_days"]))
        if "max_years_experience" in data:
            filter_dict["max_years_experience"] = max(0, int(data["max_years_experience"]))
        if "min_years_experience" in data:
            filter_dict["min_years_experience"] = max(0, int(data["min_years_experience"]))
        if "location_whitelist" in data:
            locs = data["location_whitelist"]
            filter_dict["location_whitelist"] = [x.strip().lower() for x in locs] if isinstance(locs, list) else [x.strip().lower() for x in str(locs).split(",") if x.strip()]
        if "role_keywords" in data:
            roles = data["role_keywords"]
            filter_dict["role_keywords"] = [x.strip().lower() for x in roles] if isinstance(roles, list) else [x.strip().lower() for x in str(roles).split(",") if x.strip()]
        if "title_blacklist" in data:
            bl = data["title_blacklist"]
            filter_dict["title_blacklist"] = [x.strip().lower() for x in bl] if isinstance(bl, list) else [x.strip().lower() for x in str(bl).split(",") if x.strip()]

        sec_cfg["filters"] = filter_dict
        secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
        return SuccessResponse(message="Job filter settings saved.")

    elif section == "scoring":
        scoring_dict = sec_cfg.get("scoring") or {}
        if "match_threshold" in data:
            pct = float(data["match_threshold"])
            if pct > 1.0:
                pct = pct / 100.0
            scoring_dict["match_threshold"] = round(pct, 2)
        sec_cfg["scoring"] = scoring_dict
        secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
        return SuccessResponse(message="Scoring threshold saved.")

    elif section == "salary":
        profile_path = data_dir / "profile.yaml"
        prof_data = {}
        if profile_path.exists():
            try:
                prof_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                prof_data = {}
        sal_dict = prof_data.get("salary") or {}
        if "preferred" in data:
            sal_dict["preferred"] = int(data["preferred"])
        if "min_acceptable" in data:
            sal_dict["min_acceptable"] = int(data["min_acceptable"])
        prof_data["salary"] = sal_dict
        prof_data["salary_expectation"] = (
            f"{sal_dict.get('min_acceptable', 6000000)}-"
            f"{sal_dict.get('preferred', 7000000)} IDR/month"
        )
        profile_path.write_text(yaml.safe_dump(prof_data, sort_keys=False), encoding="utf-8")
        return SuccessResponse(message="Salary settings saved.")

    elif section == "roles_search":
        search_dict = sec_cfg.get("search") or {}
        if "roles" in data:
            search_dict["roles"] = data["roles"]
        if "locations" in data:
            search_dict["locations"] = data["locations"]
        sec_cfg["search"] = search_dict
        secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
        return SuccessResponse(message="Search targets saved.")

    elif section == "letter":
        profile_path = data_dir / "profile.yaml"
        prof_data = {}
        if profile_path.exists():
            try:
                prof_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                prof_data = {}
        letter_dict = prof_data.get("letter") or {}
        if "pitch" in data:
            letter_dict["pitch"] = str(data["pitch"]).strip()
        if "custom_instructions" in data:
            letter_dict["custom_instructions"] = str(data["custom_instructions"]).strip()
        if "categories" in data and isinstance(data["categories"], list):
            letter_dict["categories"] = data["categories"]
        if "middles" in data and isinstance(data["middles"], dict):
            letter_dict["middles"] = data["middles"]
        prof_data["letter"] = letter_dict
        profile_path.write_text(yaml.safe_dump(prof_data, sort_keys=False), encoding="utf-8")
        return SuccessResponse(message="Cover letter settings saved.")

    raise HTTPException(status_code=400, detail=f"Unknown settings section: {section}")


@router.get("/models/{provider}")
def get_provider_models(provider: str, request: Request):
    data_dir: Path = request.app.state.data_dir
    cfg = _get_merged_config(data_dir)
    models = list_models_for_provider(provider, cfg=cfg)
    return {"provider": provider, "models": models}


@router.post("/oauth/{provider}/login", response_model=SuccessResponse)
def oauth_login(provider: str):
    prov = provider.lower()
    if prov not in ("claude", "codex", "chatgpt", "gemini", "antigravity"):
        raise HTTPException(status_code=400, detail=f"Unknown OAuth provider: {provider}")
    try:
        if prov == "claude":
            start_claude_oauth()
            return SuccessResponse(message="Successfully authenticated with Claude Code!")
        elif prov in ("codex", "chatgpt"):
            start_codex_oauth()
            return SuccessResponse(message="Successfully authenticated with ChatGPT!")
        elif prov in ("gemini", "antigravity"):
            start_gemini_oauth()
            return SuccessResponse(message="Successfully authenticated with Google Antigravity!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth login failed: {e}")


@router.post("/oauth/{provider}/logout", response_model=SuccessResponse)
def oauth_logout(provider: str, request: Request):
    data_dir: Path = request.app.state.data_dir
    storage = TokenStorage(data_dir / "auth_tokens.json")
    storage.delete_provider(provider.lower())
    return SuccessResponse(message=f"Logged out from {provider.capitalize()}.")


@router.post("/oauth/copilot/device-code", response_model=CopilotDeviceCodeResponse)
def copilot_device_code():
    try:
        data = request_copilot_device_code()
        return CopilotDeviceCodeResponse(
            user_code=data.get("user_code", ""),
            verification_uri=data.get("verification_uri", ""),
            device_code=data.get("device_code", ""),
            interval=data.get("interval", 5),
            expires_in=data.get("expires_in", 900),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/oauth/copilot/poll", response_model=SuccessResponse)
def copilot_poll(payload: CopilotPollRequest):
    try:
        poll_copilot_device_token(payload.device_code, interval=payload.interval, timeout=120)
        return SuccessResponse(message="Authentication successful!")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobstreet/system-login")
def jobstreet_system_login(request: Request):
    """Launch authentic system Chromium browser for JobStreet / Google login."""
    if not _check_chrome_installed():
        raise HTTPException(
            status_code=400,
            detail="Google Chrome is not detected on your system. Please install Google Chrome from https://www.google.com/chrome before logging in.",
        )

    from ...run import cmd_login
    import threading
    from unittest.mock import MagicMock

    def _worker():
        args = MagicMock()
        args.auto_wait = True
        try:
            cmd_login(args)
        except Exception as e:
            print(f"Jobstreet system login error: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return {"success": True, "message": "External browser opened. Please log in using Google."}


@router.delete("/jobstreet/auth", response_model=SuccessResponse)
def delete_jobstreet_auth(request: Request):
    """Remove saved JobStreet session storage file."""
    data_dir: Path = request.app.state.data_dir
    storage_file = data_dir / "storage_state.json"
    if storage_file.exists():
        try:
            storage_file.unlink()
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete session file: {e}")
    return SuccessResponse(message="Jobstreet session removed successfully.")


@router.post("/test-llm")
def test_llm(request: Request):
    data_dir: Path = request.app.state.data_dir
    cfg = _get_merged_config(data_dir)
    try:
        resp = complete(
            messages=[{"role": "user", "content": "Respond with 'LLM connection successful!'"}],
            cfg=cfg,
            max_tokens=30,
        )
        return {"success": True, "response": resp.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/all-data", response_model=SuccessResponse)
def delete_all_data(request: Request):
    """Delete candidate profile and reset SQLite database."""
    data_dir: Path = request.app.state.data_dir
    db_path: Path = request.app.state.db_path

    # 1. Reset SQLite database
    try:
        reset_database(db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset database: {e}")

    # 2. Delete candidate profile file
    profile_path = data_dir / "profile.yaml"
    if profile_path.exists():
        try:
            profile_path.unlink()
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete profile: {e}")

    return SuccessResponse(message="User profile and database deleted successfully.")

