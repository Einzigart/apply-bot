"""Config loading. Everything configurable lives in data/*.yaml."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# Env overrides exist so tests and the web runner can point the whole
# pipeline (including CLI subprocesses) at a throwaway data dir.
DATA_DIR = Path(os.environ.get("APPLY_BOT_DATA_DIR", ROOT / "data"))
LOGS_DIR = Path(os.environ.get("APPLY_BOT_LOGS_DIR", ROOT / "logs"))
DB_PATH = DATA_DIR / "jobs.db"
STORAGE_STATE_PATH = DATA_DIR / "storage_state.json"


def _load(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config() -> dict:
    return _load("config.yaml")


def load_profile() -> dict:
    return _load("profile.yaml")
