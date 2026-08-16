"""Dashboard router."""
from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Depends

from ... import db
from ..deps import get_db
from ..schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
def get_dashboard(
    sort: str | None = None,
    order: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    counts = {r["decision"]: r["c"] for r in db.decision_counts(conn)}
    return {
        "total_jobs": db.count_jobs(conn),
        "apply_queue": len(db.approved_unapplied(conn)),
        "counts": counts,
        "total_apps": db.count_applications(conn),
        "runs": [dict(r) for r in db.list_runs(conn, limit=10, sort=sort, order=order)],
    }
