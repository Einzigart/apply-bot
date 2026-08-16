"""Profile router."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ...cv_parser import extract_text_from_pdf, parse_cv_with_llm
from ..schemas import ImportCVResponse, ProfileResponse, SaveProfileRequest, SuccessResponse

router = APIRouter(prefix="/api/profile", tags=["profile"])
YAML_FILES = ("profile.yaml", "config.yaml")


def _get_merged_config(data_dir: Path) -> dict:
    base_path = data_dir / "config.yaml"
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


@router.get("", response_model=ProfileResponse)
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

    name = str(prof.get("name", "")).strip()
    has_profile = bool(name and name != "Jane Candidate")

    return ProfileResponse(
        profile=prof,
        raw=raw,
        has_profile=has_profile,
    )


@router.post("/import-cv", response_model=ImportCVResponse)
async def import_cv(request: Request, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported for CV import.",
        )

    try:
        pdf_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {e}")

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # 1. Extract text from PDF
    try:
        cv_text = extract_text_from_pdf(pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to extract text from PDF: {e}")

    # 2. Optionally store the uploaded PDF into the data directory
    data_dir: Path = request.app.state.data_dir
    try:
        saved_cv_path = data_dir / file.filename
        saved_cv_path.write_bytes(pdf_bytes)
    except Exception:
        pass  # Non-fatal if writing file fails

    # 3. Call configured LLM to parse and structure CV
    cfg = _get_merged_config(data_dir)
    try:
        extracted = parse_cv_with_llm(cv_text, cfg=cfg, filename=file.filename)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse CV with AI model: {e}",
        )

    preview = cv_text[:500] + ("..." if len(cv_text) > 500 else "")
    return ImportCVResponse(
        success=True,
        profile=extracted,
        extracted_text_preview=preview,
        message="CV parsed and structured successfully.",
    )


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
