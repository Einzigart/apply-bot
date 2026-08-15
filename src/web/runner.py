"""Run pipeline commands as CLI subprocesses from the web UI.

The CLI stays the single source of truth: a run is just
`python -m src.run <args>` with stdout/stderr captured to
logs/runs/<id>.log. The runs row is created here and handed to the
subprocess via APPLY_BOT_RUN_ID so both sides agree on the record.

One run at a time — the plan forbids parallel browser sessions.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from ..config import ROOT
from ..db import connect, finish_run_if_open, get_run, start_run

COMMANDS = {"discover", "score", "apply", "calibrate", "login"}

_lock = threading.Lock()
_active: dict[int, subprocess.Popen] = {}
_started: set[int] = set()  # every run this process launched, ever


class BusyError(RuntimeError):
    pass


def _prune() -> None:
    """Drop finished processes from the active table."""
    for run_id, proc in list(_active.items()):
        if proc.poll() is not None:
            del _active[run_id]


def start(db_path: Path, logs_dir: Path, argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        raise ValueError(f"command not allowed: {argv[:1]}")
    with _lock:
        _prune()
        if _active:
            raise BusyError("a run is already in progress")
        conn = connect(db_path)
        try:
            run_id = start_run(conn, "src.run " + " ".join(argv))
        finally:
            conn.close()
        log_file = logs_dir / "runs" / f"{run_id}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ | {
            "APPLY_BOT_RUN_ID": str(run_id),
            # Keep the subprocess on the same dirs this server was given,
            # even when they did not come from the environment (tests).
            # By construction db_path is always DATA_DIR/jobs.db.
            "APPLY_BOT_DATA_DIR": str(db_path.parent),
            "APPLY_BOT_LOGS_DIR": str(logs_dir),
        }
        out = open(log_file, "wb")
        try:
            # -u: unbuffered, so the log tail streams while the run is live.
            proc = subprocess.Popen(
                [sys.executable, "-u", "-m", "src.run", *argv],
                cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env,
            )
        finally:
            out.close()  # the child keeps its own copy of the fd
        _active[run_id] = proc
        _started.add(run_id)
        return run_id


def is_alive(run_id: int) -> bool:
    with _lock:
        proc = _active.get(run_id)
        return proc is not None and proc.poll() is None


def status(db_path: Path, run_id: int) -> dict:
    """Live status: DB row + whether the subprocess is still around."""
    conn = connect(db_path)
    try:
        row = get_run(conn, run_id)
        if row is None:
            return {}
        run = dict(row)
        alive = is_alive(run_id)
        if run["finished_at"] is None and run_id in _started and not alive:
            # We launched it, its process is gone, but the row is open: the
            # CLI died before stamping its own record (killed, crashed).
            # Runs we did not launch are left alone — they may be live
            # terminal runs.
            finish_run_if_open(conn, run_id, "interrupted (subprocess died)")
            run = dict(get_run(conn, run_id))
        run["alive"] = alive
        return run
    finally:
        conn.close()


def log_tail(logs_dir: Path, run_id: int, max_bytes: int = 65536) -> str:
    log_file = logs_dir / "runs" / f"{run_id}.log"
    if not log_file.exists():
        return ""
    data = log_file.read_bytes()
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    return data.decode("utf-8", errors="replace")
