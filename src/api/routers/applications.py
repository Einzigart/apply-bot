"""Applications router."""
from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query

from ... import db
from ..deps import get_db
from ..schemas import (
    ApplicationsListResponse,
    SuccessResponse,
    UpdateApplicationStatusRequest,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])
PER_PAGE = 50


@router.get("", response_model=ApplicationsListResponse)
def list_applications(
    page: int = Query(1, ge=1),
    per_page: int = Query(PER_PAGE, ge=1, le=200),
    sort: str | None = Query(None),
    order: str | None = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = db.list_applications(
        conn,
        limit=per_page + 1,
        offset=(page - 1) * per_page,
        sort=sort,
        order=order,
    )
    has_next = len(rows) > per_page
    return {
        "apps": [dict(r) for r in rows[:per_page]],
        "page": page,
        "has_next": has_next,
        "total": db.count_applications(conn),
    }


@router.patch("/{app_id}/status", response_model=SuccessResponse)
def update_status(
    app_id: int,
    payload: UpdateApplicationStatusRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    updated = db.update_application_status(conn, app_id, payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Application not found")
    return SuccessResponse(message="Status updated successfully")

