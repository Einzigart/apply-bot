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
from ..llm import complete, get_llm_config
from . import runner

PER_PAGE = 50
YAML_FILES = ("profile.yaml", "config.yaml")


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

    @app.post("/jobs/<job_id>/decide")
    def decide_job(job_id: str):
        conn = get_conn()
        decision = request.form.get("decision", "").strip()
        reason = request.form.get("reason", "").strip() or None
        if decision not in ("apply", "skip"):
            abort(400, "decision must be 'apply' or 'skip'")
        if not db.record_decision(conn, job_id, decision, reason):
            abort(404, "job not found")
        flash(f"Job {job_id} marked as '{decision}'")
        next_url = request.form.get("next") or request.referrer or url_for("jobs")
        return redirect(next_url)

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
        is_login = argv and argv[0] == "login"
        try:
            run_id = runner.start(db_path, logs_dir, argv)
        except runner.BusyError as e:
            flash(f"not started: {e}")
            return redirect(request.referrer or url_for("runs"))
        if is_login:
            flash("Browser window opened for Jobstreet login. Please complete sign-in in the window.")
            return redirect(url_for("settings"))
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

        return render_template("profile.html", prof=prof, raw=raw,
                               answers=db.list_answers(get_conn()))

    @app.get("/settings")
    def settings():
        config_path = data_dir / "config.yaml"
        cfg = {}
        if config_path.exists():
            try:
                cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                cfg = {}

        llm_cfg = cfg.get("llm") or {}
        active_llm = get_llm_config(cfg)
        env_overrides = {
            "base_url": bool(os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")),
            "api_key": bool(os.environ.get("OPENAI_API_KEY")),
            "model": bool(os.environ.get("OPENAI_MODEL")),
            "prefix": bool(os.environ.get("OPENAI_MODEL_PREFIX")),
        }

        storage_file = data_dir / "storage_state.json"
        has_auth = storage_file.exists()
        auth_mtime = storage_file.stat().st_mtime if has_auth else None

        return render_template(
            "settings.html",
            cfg=cfg,
            llm_cfg=llm_cfg,
            active_llm=active_llm,
            env_overrides=env_overrides,
            has_auth=has_auth,
            auth_mtime=auth_mtime,
        )

    @app.post("/settings")
    def save_settings():
        section = request.form.get("section")
        config_path = data_dir / "config.yaml"
        cfg = {}
        if config_path.exists():
            try:
                cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                cfg = {}

        if section == "llm":
            endpoint = request.form.get("endpoint", "").strip()
            model = request.form.get("model", "").strip()
            prefix = request.form.get("prefix", "").strip()
            api_key = request.form.get("api_key", "").strip()

            llm_dict = cfg.get("llm") or {}
            llm_dict["endpoint"] = endpoint or "https://api.openai.com/v1"
            llm_dict["model"] = model or "gpt-4o-mini"
            llm_dict["prefix"] = prefix
            llm_dict["api_key"] = api_key
            cfg["llm"] = llm_dict

            # Also keep scoring.model in sync if present
            if "scoring" in cfg and isinstance(cfg["scoring"], dict):
                cfg["scoring"]["model"] = llm_dict["model"]

            config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
            flash("LLM settings saved successfully.")
        else:
            flash("No changes made.")

        return redirect(url_for("settings"))

    @app.post("/settings/test-llm")
    def test_llm():
        config_path = data_dir / "config.yaml"
        cfg = {}
        if config_path.exists():
            try:
                cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                cfg = {}

        try:
            resp = complete(
                messages=[{"role": "user", "content": "Respond with 'LLM connection successful!'"}],
                cfg=cfg,
                max_tokens=30,
            )
            flash(f"LLM Response: {resp.strip()}")
        except Exception as e:
            flash(f"LLM Connection Error: {e}")

        return redirect(url_for("settings"))

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
    elif cmd == "login":
        argv.append("--auto-wait")
    return argv
