"""Flask web UI: trigger runs, tail logs, browse jobs and history.

A local, single-user tool: binds to 127.0.0.1, no auth — do not expose
it. All pipeline work still goes through the CLI (subprocesses managed
by runner.py); this app only reads the DB and the data/*.yaml files.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from flask import (Flask, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from .. import db
from ..config import DATA_DIR, LOGS_DIR
from . import runner

PER_PAGE = 50
YAML_FILES = ("profile.yaml", "config.yaml", "answers.yaml")


def create_app(data_dir: Path | None = None, logs_dir: Path | None = None) -> Flask:
    app = Flask(__name__)
    data_dir = Path(data_dir or DATA_DIR)
    logs_dir = Path(logs_dir or LOGS_DIR)
    db_path = data_dir / "jobs.db"
    # Sessions only carry flash messages; a per-process key is enough for
    # a localhost single-user tool.
    app.secret_key = os.urandom(24)

    conn = db.connect(db_path)  # also creates the schema on first serve
    db.mark_interrupted_runs(conn)
    conn.close()

    def get_conn():
        if "conn" not in g:
            g.conn = db.connect(db_path)
        return g.conn

    @app.teardown_appcontext
    def _close_conn(_exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.get("/")
    def index():
        conn = get_conn()
        counts = {r["decision"]: r["c"] for r in db.decision_counts(conn)}
        return render_template(
            "index.html",
            total_jobs=db.count_jobs(conn),
            counts=counts,
            apply_queue=len(db.approved_unapplied(conn)),
            total_apps=db.count_applications(conn),
            runs=db.list_runs(conn, limit=10),
        )

    @app.get("/jobs")
    def jobs():
        conn = get_conn()
        decision = request.args.get("decision") or None
        q = request.args.get("q") or None
        page = max(request.args.get("page", 1, type=int) or 1, 1)
        rows = db.jobs_with_latest_eval(
            conn, decision=decision, q=q,
            limit=PER_PAGE + 1, offset=(page - 1) * PER_PAGE,
        )
        return render_template(
            "jobs.html", jobs=rows[:PER_PAGE], decision=decision or "",
            q=q or "", page=page, has_next=len(rows) > PER_PAGE,
        )

    @app.get("/applications")
    def applications():
        conn = get_conn()
        page = max(request.args.get("page", 1, type=int) or 1, 1)
        rows = db.list_applications(conn, limit=PER_PAGE + 1,
                                    offset=(page - 1) * PER_PAGE)
        return render_template(
            "applications.html", apps=rows[:PER_PAGE], page=page,
            has_next=len(rows) > PER_PAGE,
            total=db.count_applications(conn),
        )

    @app.get("/runs")
    def runs():
        return render_template("runs.html",
                               runs=db.list_runs(get_conn(), limit=100))

    @app.post("/runs")
    def start_run():
        argv = _form_to_argv(request.form)
        try:
            run_id = runner.start(db_path, logs_dir, argv)
        except runner.BusyError as e:
            flash(f"not started: {e}")
            return redirect(url_for("runs"))
        return redirect(url_for("run_detail", run_id=run_id))

    @app.get("/runs/<int:run_id>")
    def run_detail(run_id: int):
        run = runner.status(db_path, run_id)
        if not run:
            abort(404)
        return render_template("run_detail.html", run=run,
                               log=runner.log_tail(logs_dir, run_id))

    @app.get("/runs/<int:run_id>/tail")
    def run_tail(run_id: int):
        run = runner.status(db_path, run_id)
        if not run:
            abort(404)
        return jsonify(
            finished=run["finished_at"] is not None,
            notes=run["notes"],
            log=runner.log_tail(logs_dir, run_id),
        )

    @app.get("/profile")
    def profile():
        raw = {}
        for name in YAML_FILES:
            path = data_dir / name
            raw[name] = (path.read_text(encoding="utf-8")
                         if path.exists() else "(file missing)")
        try:
            prof = yaml.safe_load(raw["profile.yaml"])
        except yaml.YAMLError:
            prof = None
        if not isinstance(prof, dict):
            prof = None  # template falls back to the raw file
        return render_template("profile.html", prof=prof, raw=raw)

    return app


def _form_to_argv(form) -> list[str]:
    """Translate the run form into a whitelisted CLI argv.

    Field names are prefixed with their command (discover_pages, ...) so
    options can never bleed between commands.
    """
    cmd = form.get("command", "")
    if cmd not in runner.COMMANDS:
        abort(400, f"unknown command: {cmd!r}")

    def add_int(argv: list[str], flag: str, field: str) -> None:
        raw = (form.get(field) or "").strip()
        if not raw:
            return
        try:
            argv += [flag, str(int(raw))]
        except ValueError:
            abort(400, f"{field} must be a whole number, got {raw!r}")

    argv = [cmd]
    if cmd == "discover":
        add_int(argv, "--pages", "discover_pages")
        if form.get("discover_headless"):
            argv.append("--headless")
        if form.get("discover_cards_only"):
            argv.append("--cards-only")
    elif cmd == "score":
        if form.get("score_offline"):
            argv.append("--offline")
        add_int(argv, "--limit", "score_limit")
    elif cmd == "apply":
        add_int(argv, "--limit", "apply_limit")
        if form.get("apply_headless"):
            argv.append("--headless")
        if form.get("apply_llm_letter"):
            argv.append("--llm-letter")
        if form.get("apply_execute"):
            argv.append("--execute")
    return argv
