"""Pydantic schemas for the FastAPI backend."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = "ok"


class ErrorResponse(BaseModel):
    error: str


# --- Dashboard ---
class RunItem(BaseModel):
    id: int
    command: str
    started_at: str
    finished_at: str | None = None
    notes: str | None = None


class DashboardStats(BaseModel):
    total_jobs: int
    apply_queue: int
    counts: dict[str, int]
    total_apps: int
    runs: list[dict[str, Any]]


# --- Jobs ---
class JobItem(BaseModel):
    id: int
    jobstreet_id: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str | None = None
    decision: str | None = None
    match_pct: int | None = None
    model: str | None = None
    last_seen: str | None = None
    reason: str | None = None
    is_external: int | None = 0


class JobsListResponse(BaseModel):
    jobs: list[dict[str, Any]]
    total: int
    page: int
    per_page: int
    total_pages: int


class DecideJobRequest(BaseModel):
    decision: str = Field(..., description="'apply' or 'skip'")
    reason: str | None = None


# --- Applications ---
class UpdateApplicationStatusRequest(BaseModel):
    status: str = Field(..., description="New application status")


class CreateApplicationRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Job title / role")
    company: str = Field(..., min_length=1, description="Company name")
    url: str = Field(..., min_length=1, description="Job posting URL")
    applied_at: str | None = Field(None, description="Date applied (YYYY-MM-DD), defaults to today")
    location: str | None = None
    salary_entered: str | None = None
    status: str = Field("Submitted", description="Application status")


class UpdateApplicationRequest(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str | None = None
    applied_at: str | None = None
    salary_entered: str | None = None
    status: str | None = None


class ImportApplicationsResponse(BaseModel):
    success: bool = True
    imported: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    message: str = ""


class ApplicationItem(BaseModel):
    id: int
    job_id: int
    applied_at: str
    salary_entered: str | None = None
    status: str
    confirmation: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str | None = None


class ApplicationsListResponse(BaseModel):
    apps: list[dict[str, Any]]
    page: int
    has_next: bool
    total: int


# --- Runs ---
class StartRunRequest(BaseModel):
    command: str
    # Command specific options
    discover_pages: int | None = None
    discover_cards_only: bool | None = None
    score_offline: bool | None = None
    score_limit: int | None = None
    apply_limit: int | None = None
    apply_headless: bool | None = None
    apply_llm_letter: bool | None = None
    apply_execute: bool | None = None
    pipeline_pages: int | None = None
    pipeline_limit: int | None = None
    pipeline_cards_only: bool | None = None
    pipeline_offline: bool | None = None
    pipeline_llm_letter: bool | None = None
    pipeline_headless: bool | None = None
    pipeline_execute: bool | None = None


class StartRunResponse(BaseModel):
    success: bool = True
    run_id: int | None = None
    message: str | None = None


class RunDetailResponse(BaseModel):
    run: dict[str, Any]
    log: str


class RunTailResponse(BaseModel):
    finished: bool
    notes: str | None = None
    log: str


# --- Profile ---
class SaveProfileRequest(BaseModel):
    name: str = ""
    location: str = ""
    work_rights: str = ""
    cv_file: str = "CV.pdf"
    years_experience: float | int = 0
    languages: list[str] = Field(default_factory=list)
    locations_ok: list[str] = Field(default_factory=list)
    education: dict[str, Any] = Field(default_factory=dict)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[Any] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    salary: dict[str, Any] = Field(default_factory=dict)
    salary_expectation: str = ""
    letter: dict[str, Any] = Field(default_factory=dict)
    predicted_config: dict[str, Any] | None = None


class ImportCVResponse(BaseModel):
    success: bool = True
    profile: dict[str, Any] = Field(default_factory=dict)
    extracted_text_preview: str = ""
    message: str = "CV parsed successfully"


class ProfileResponse(BaseModel):
    profile: dict[str, Any]
    raw: dict[str, str]
    has_profile: bool = False



# --- Settings ---
class SaveSettingsRequest(BaseModel):
    section: str
    data: dict[str, Any] = Field(default_factory=dict)


class CopilotDeviceCodeResponse(BaseModel):
    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int


class CopilotPollRequest(BaseModel):
    device_code: str
    interval: int = 5
