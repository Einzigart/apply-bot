"""Config loading. Everything configurable lives in data/*.yaml."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# In PyInstaller standalone onedir mode, fallback to sys._MEIPASS for bundled assets
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))

# Env overrides exist so tests and the web runner can point the whole
# pipeline (including CLI subprocesses) at a throwaway data dir.
DATA_DIR = Path(os.environ.get("APPLY_BOT_DATA_DIR", ROOT / "data"))
LOGS_DIR = Path(os.environ.get("APPLY_BOT_LOGS_DIR", ROOT / "logs"))
DB_PATH = DATA_DIR / "jobs.db"
STORAGE_STATE_PATH = DATA_DIR / "storage_state.json"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dictionary into base."""
    merged = dict(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def _load(name: str):
    path = DATA_DIR / name
    if not path.exists():
        fallback_path = RESOURCE_ROOT / "data" / name
        if fallback_path.exists():
            with open(fallback_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        # Also check for example fallback
        if name == "config.yaml":
            example_path = RESOURCE_ROOT / "data" / "config.example.yaml"
            if example_path.exists():
                with open(example_path, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> dict:
    base_cfg = _load("config.yaml")
    # Merge local secrets if present (data/secrets.yaml or data/config.local.yaml)
    for local_name in ("secrets.yaml", "config.local.yaml"):
        local_cfg = _load(local_name)
        if local_cfg:
            base_cfg = _deep_merge(base_cfg, local_cfg)
    return base_cfg


def load_profile() -> dict:
    return _load("profile.yaml")
