"""Applications router."""
from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Depends, Query

from ... import db
from ..deps import get_db
from ..schemas import ApplicationsListResponse

router = APIRouter(prefix="/api/applications", tags=["applications"])
PER_PAGE = 50


@router.get("", response_model=ApplicationsListResponse)
def list_applications(
    page: int = Query(1, ge=1),
    per_page: int = Query(PER_PAGE, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = db.list_applications(
        conn, limit=per_page + 1, offset=(page - 1) * per_page
    )
    has_next = len(rows) > per_page
    return {
        "apps": [dict(r) for r in rows[:per_page]],
        "page": page,
        "has_next": has_next,
        "total": db.count_applications(conn),
    }
