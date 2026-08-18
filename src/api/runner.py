"""Run pipeline commands as CLI subprocesses from FastAPI backend.

Subprocess manager shared with the CLI runner.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from ..config import ROOT
from ..db import connect, finish_run_if_open, get_run, start_run

COMMANDS = {"discover", "score", "apply", "pipeline", "calibrate", "login"}

_lock = threading.Lock()
_active: dict[int, subprocess.Popen] = {}
_started: set[int] = set()


class BusyError(RuntimeError):
    pass


def _prune() -> None:
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
            "APPLY_BOT_DATA_DIR": str(db_path.parent),
            "APPLY_BOT_LOGS_DIR": str(logs_dir),
        }
        cmd = [sys.executable, "-u", "-m", "src.run", *argv]
        if getattr(sys, "frozen", False):
            # In PyInstaller bundle, sys.executable is api-server binary
            cmd = [sys.executable, "--cli", *argv]

        out = open(log_file, "wb")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=ROOT,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        finally:
            out.close()
        _active[run_id] = proc
        _started.add(run_id)
        return run_id


def is_alive(run_id: int) -> bool:
    with _lock:
        proc = _active.get(run_id)
        return proc is not None and proc.poll() is None


def stop(db_path: Path, run_id: int) -> bool:
    with _lock:
        _prune()
        proc = _active.get(run_id)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
            del _active[run_id]

        conn = connect(db_path)
        try:
            finish_run_if_open(conn, run_id, "cancelled by user")
        finally:
            conn.close()
        return True


def status(db_path: Path, run_id: int) -> dict:
    conn = connect(db_path)
    try:
        row = get_run(conn, run_id)
        if row is None:
            return {}
        run = dict(row)
        alive = is_alive(run_id)
        if run["finished_at"] is None and run_id in _started and not alive:
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

def shutdown() -> None:
    """Terminate and kill all active subprocesses on server shutdown."""
    with _lock:
        for run_id, proc in list(_active.items()):
            if proc.poll() is None:
                try:
                    try:
                        import signal
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception:
                        proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            import signal
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except Exception:
                            proc.kill()
                except Exception:
                    pass
        _active.clear()
