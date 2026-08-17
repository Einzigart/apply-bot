"""Applications router."""
from __future__ import annotations

import csv
import io
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.responses import StreamingResponse

from ... import db
from ..deps import get_db
from ..schemas import (
    ApplicationsListResponse,
    SuccessResponse,
    UpdateApplicationStatusRequest,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])
PER_PAGE = 50


@router.get("/export")
def export_applications(
    format: str = Query("csv", pattern="^(csv|tsv|excel)$"),
    status: str | None = Query(None),
    q: str | None = Query(None),
    sort: str | None = Query(None),
    order: str | None = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    # Fetch all matching applications without pagination limits
    rows = db.list_applications(
        conn,
        limit=10000,
        offset=0,
        status=status,
        q=q,
        sort=sort,
        order=order,
    )

    headers = [
        "Applied Date",
        "Role Title",
        "Company",
        "Location",
        "Status",
        "Salary Entered",
        "Job URL",
        "Confirmation Text",
        "Cover Letter",
    ]

    output = io.StringIO()
    # Write UTF-8 BOM for Excel compatibility
    output.write("\ufeff")

    delimiter = "\t" if format in ("tsv", "excel") else ","
    writer = csv.writer(output, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)

    for r in rows:
        d = dict(r)
        writer.writerow([
            d.get("applied_at") or "",
            d.get("title") or "",
            d.get("company") or "",
            d.get("location") or "",
            d.get("status") or "Submitted",
            d.get("salary_entered") or "",
            d.get("url") or "",
            d.get("confirmation") or "",
            (d.get("cover_letter") or "").replace("\r\n", " ").replace("\n", " "),
        ])

    csv_data = output.getvalue().encode("utf-8-sig")

    if format == "excel":
        filename = "applications.csv"
        media_type = "text/csv; charset=utf-8"
    elif format == "tsv":
        filename = "applications.tsv"
        media_type = "text/tab-separated-values; charset=utf-8"
    else:
        filename = "applications.csv"
        media_type = "text/csv; charset=utf-8"

    return Response(
        content=csv_data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=ApplicationsListResponse)
def list_applications(
    page: int = Query(1, ge=1),
    per_page: int = Query(PER_PAGE, ge=1, le=200),
    status: str | None = Query(None),
    q: str | None = Query(None),
    sort: str | None = Query(None),
    order: str | None = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = db.list_applications(
        conn,
        limit=per_page + 1,
        offset=(page - 1) * per_page,
        status=status,
        q=q,
        sort=sort,
        order=order,
    )
    has_next = len(rows) > per_page
    total = db.count_applications(conn, status=status, q=q)
    return {
        "apps": [dict(r) for r in rows[:per_page]],
        "page": page,
        "has_next": has_next,
        "total": total,
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

