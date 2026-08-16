"""Profile router."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml
from fastapi import APIRouter, HTTPException, Request

from ..schemas import SaveProfileRequest, SuccessResponse

router = APIRouter(prefix="/api/profile", tags=["profile"])
YAML_FILES = ("profile.yaml", "config.yaml")


@router.get("")
def get_profile(request: Request):
    data_dir: Path = request.app.state.data_dir
    raw: dict[str, str] = {}
    for name in YAML_FILES:
        path = data_dir / name
        raw[name] = path.read_text(encoding="utf-8") if path.exists() else "(file missing)"

    try:
        prof = yaml.safe_load(raw.get("profile.yaml", ""))
    except yaml.YAMLError:
        prof = None
    if not isinstance(prof, dict):
        prof = {}

    return {
        "profile": prof,
        "raw": raw,
    }


@router.post("", response_model=SuccessResponse)
def save_profile(payload: SaveProfileRequest, request: Request):
    data_dir: Path = request.app.state.data_dir
    profile_path = data_dir / "profile.yaml"

    prof: dict[str, Any] = {}
    if profile_path.exists():
        try:
            prof = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            prof = {}
    if not isinstance(prof, dict):
        prof = {}

    prof["name"] = payload.name.strip()
    prof["location"] = payload.location.strip()
    prof["work_rights"] = payload.work_rights.strip()
    prof["cv_file"] = payload.cv_file.strip() or "CV.pdf"
    prof["years_experience"] = payload.years_experience
    prof["languages"] = payload.languages
    prof["locations_ok"] = payload.locations_ok
    prof["education"] = payload.education
    prof["experience"] = payload.experience
    prof["skills"] = payload.skills
    prof["projects"] = payload.projects
    prof["salary"] = payload.salary
    if payload.salary_expectation:
        prof["salary_expectation"] = payload.salary_expectation
    elif payload.salary:
        prof["salary_expectation"] = (
            f"{payload.salary.get('min_acceptable', 6000000)}-"
            f"{payload.salary.get('preferred', 7000000)} IDR/month"
        )
    prof["letter"] = payload.letter

    try:
        profile_path.write_text(yaml.safe_dump(prof, sort_keys=False), encoding="utf-8")
        return SuccessResponse(message="Profile updated successfully.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {e}")
