"""Runs router."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request

from ... import db
from .. import runner
from ..deps import get_db
from ..schemas import (
    RunDetailResponse,
    RunTailResponse,
    StartRunRequest,
    StartRunResponse,
    SuccessResponse,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _request_to_argv(payload: StartRunRequest) -> list[str]:
    cmd = payload.command
    if cmd not in runner.COMMANDS:
        raise HTTPException(status_code=400, detail=f"Unknown command: {cmd!r}")

    argv = [cmd]
    if cmd == "discover":
        if payload.discover_pages:
            argv += ["--pages", str(payload.discover_pages)]
        if payload.discover_cards_only:
            argv.append("--cards-only")
    elif cmd == "score":
        if payload.score_offline:
            argv.append("--offline")
        if payload.score_limit:
            argv += ["--limit", str(payload.score_limit)]
    elif cmd == "apply":
        if payload.apply_limit:
            argv += ["--limit", str(payload.apply_limit)]
        if payload.apply_headless:
            argv.append("--headless")
        if payload.apply_llm_letter:
            argv.append("--llm-letter")
        if payload.apply_execute:
            argv.append("--execute")
    elif cmd == "pipeline":
        if payload.pipeline_pages:
            argv += ["--pages", str(payload.pipeline_pages)]
        if payload.pipeline_limit:
            argv += ["--limit", str(payload.pipeline_limit)]
        if payload.pipeline_cards_only:
            argv.append("--cards-only")
        if payload.pipeline_offline:
            argv.append("--offline")
        if payload.pipeline_llm_letter:
            argv.append("--llm-letter")
        if payload.pipeline_headless:
            argv.append("--headless")
        if payload.pipeline_execute:
            argv.append("--execute")
    elif cmd == "login":
        argv.append("--auto-wait")
    return argv


@router.get("")
def list_runs(
    sort: str | None = None,
    order: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    return {"runs": [dict(r) for r in db.list_runs(conn, limit=100, sort=sort, order=order)]}


@router.post("", response_model=StartRunResponse)
def start_run(payload: StartRunRequest, request: Request):
    argv = _request_to_argv(payload)
    db_path: Path = request.app.state.db_path
    logs_dir: Path = request.app.state.logs_dir

    try:
        run_id = runner.start(db_path, logs_dir, argv)
        return StartRunResponse(
            success=True, run_id=run_id, message="Run started successfully"
        )
    except runner.BusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run_detail(run_id: int, request: Request):
    db_path: Path = request.app.state.db_path
    logs_dir: Path = request.app.state.logs_dir
    run = runner.status(db_path, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run": run,
        "log": runner.log_tail(logs_dir, run_id),
    }


@router.post("/{run_id}/cancel", response_model=SuccessResponse)
def cancel_run(run_id: int, request: Request):
    db_path: Path = request.app.state.db_path
    run = runner.status(db_path, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    runner.stop(db_path, run_id)
    return SuccessResponse(message=f"Run {run_id} cancelled.")


@router.get("/{run_id}/tail", response_model=RunTailResponse)
def get_run_tail(run_id: int, request: Request):
    db_path: Path = request.app.state.db_path
    logs_dir: Path = request.app.state.logs_dir
    run = runner.status(db_path, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "finished": run.get("finished_at") is not None,
        "notes": run.get("notes"),
        "log": runner.log_tail(logs_dir, run_id),
    }
