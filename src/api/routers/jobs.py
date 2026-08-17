"""Jobs router."""
from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query

from ... import db
from ..deps import get_db
from ..schemas import DecideJobRequest, JobsListResponse, SuccessResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
PER_PAGE = 50


@router.get("", response_model=JobsListResponse)
def list_jobs(
    decision: str | None = Query(None),
    q: str | None = Query(None),
    is_external: bool | None = Query(None),
    sort: str | None = Query(None),
    order: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(PER_PAGE, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_db),
):
    total = db.count_jobs_filtered(conn, decision=decision, q=q, is_external=is_external)
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages and total > 0:
        page = total_pages

    rows = db.jobs_with_latest_eval(
        conn,
        decision=decision,
        q=q,
        is_external=is_external,
        sort=sort,
        order=order,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return {
        "jobs": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


@router.post("/{job_id}/decide", response_model=SuccessResponse)
def decide_job(
    job_id: str,
    payload: DecideJobRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    decision = payload.decision.strip().lower()
    if decision not in ("apply", "skip"):
        raise HTTPException(status_code=400, detail="Decision must be 'apply' or 'skip'")
    if not db.record_decision(conn, job_id, decision, payload.reason):
        raise HTTPException(status_code=404, detail="Job not found")
    return SuccessResponse(message=f"Job {job_id} marked as '{decision}'")
