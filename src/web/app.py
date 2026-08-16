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
from ..models_fetcher import list_models_for_provider
from ..oauth import (
    CLAUDE_CONFIG,
    CODEX_CONFIG,
    GEMINI_CONFIG,
    GITHUB_COPILOT_CONFIG,
    TokenStorage,
    poll_copilot_device_token,
    refresh_claude_token,
    refresh_codex_token,
    refresh_gemini_token,
    request_copilot_device_code,
    start_claude_oauth,
    start_codex_oauth,
    start_gemini_oauth,
)
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
        sort = request.args.get("sort") or None
        order = request.args.get("order") or None
        page = max(request.args.get("page", 1, type=int) or 1, 1)
        total = db.count_jobs_filtered(conn, decision=decision, q=q)
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        if page > total_pages and total > 0:
            page = total_pages
        rows = db.jobs_with_latest_eval(
            conn, decision=decision, q=q, sort=sort, order=order,
            limit=PER_PAGE, offset=(page - 1) * PER_PAGE,
        )
        return render_template(
            "jobs.html", jobs=rows, decision=decision or "",
            q=q or "", sort=sort or "", order=order or "", page=page,
            total=total, total_pages=total_pages, per_page=PER_PAGE,
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

    @app.post("/runs/<int:run_id>/cancel")
    def cancel_run(run_id: int):
        run = runner.status(db_path, run_id)
        if not run:
            abort(404)
        runner.stop(db_path, run_id)
        flash(f"Run {run_id} cancelled.")
        return redirect(request.referrer or url_for("run_detail", run_id=run_id))

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

    def get_merged_config() -> dict:
        base_path = data_dir / "config.yaml"
        cfg = {}
        if base_path.exists():
            try:
                cfg = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                cfg = {}

        for sec_file in ("secrets.yaml", "config.local.yaml"):
            sec_path = data_dir / sec_file
            if sec_path.exists():
                try:
                    sec_cfg = yaml.safe_load(sec_path.read_text(encoding="utf-8")) or {}
                    if isinstance(sec_cfg, dict):
                        for k, v in sec_cfg.items():
                            if k in cfg and isinstance(cfg[k], dict) and isinstance(v, dict):
                                cfg[k].update(v)
                            else:
                                cfg[k] = v
                except yaml.YAMLError:
                    pass
        return cfg

    @app.get("/settings")
    def settings():
        cfg = get_merged_config()
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

        secrets_path = data_dir / "secrets.yaml"
        sec_cfg = {}
        if secrets_path.exists():
            try:
                sec_cfg = yaml.safe_load(secrets_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                sec_cfg = {}
        sec_filters = sec_cfg.get("filters") or {}

        profile_path = data_dir / "profile.yaml"
        profile_data = {}
        if profile_path.exists():
            try:
                profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                profile_data = {}

        tokens_storage = TokenStorage(data_dir / "auth_tokens.json")
        auth_tokens = tokens_storage.load()

        return render_template(
            "settings.html",
            cfg=cfg,
            llm_cfg=llm_cfg,
            active_llm=active_llm,
            env_overrides=env_overrides,
            has_auth=has_auth,
            auth_mtime=auth_mtime,
            sec_filters=sec_filters,
            profile=profile_data,
            auth_tokens=auth_tokens,
            oauth_configs={
                "claude": CLAUDE_CONFIG,
                "codex": CODEX_CONFIG,
                "copilot": GITHUB_COPILOT_CONFIG,
                "gemini": GEMINI_CONFIG,
            },
        )

    @app.post("/settings")
    def save_settings():
        section = request.form.get("section")
        secrets_path = data_dir / "secrets.yaml"
        sec_cfg = {}
        if secrets_path.exists():
            try:
                sec_cfg = yaml.safe_load(secrets_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                sec_cfg = {}

        if section == "llm":
            provider = request.form.get("provider", "openai").strip()
            endpoint = request.form.get("endpoint", "").strip()
            model = request.form.get("model", "").strip()
            prefix = request.form.get("prefix", "").strip()
            api_key = request.form.get("api_key", "").strip()

            llm_dict = sec_cfg.get("llm") or {}
            llm_dict["provider"] = provider
            llm_dict["endpoint"] = endpoint or "https://api.openai.com/v1"
            llm_dict["model"] = model or "gpt-4o-mini"
            llm_dict["prefix"] = prefix
            llm_dict["api_key"] = api_key
            sec_cfg["llm"] = llm_dict

            secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
            msg = f"LLM settings saved (Provider: {provider}, Model: {llm_dict['model']})."
            if request.headers.get("Accept") == "application/json" or request.is_json:
                return jsonify({"success": True, "message": msg})
            flash(msg)
        elif section == "filters":
            filter_dict = sec_cfg.get("filters") or {}

            raw_cooldown = request.form.get("company_cooldown_days", "").strip()
            if raw_cooldown:
                try:
                    filter_dict["company_cooldown_days"] = max(0, int(raw_cooldown))
                except ValueError:
                    pass

            raw_exp = request.form.get("max_years_experience", "").strip()
            if raw_exp:
                try:
                    filter_dict["max_years_experience"] = max(0, int(raw_exp))
                except ValueError:
                    pass

            raw_min_exp = request.form.get("min_years_experience", "").strip()
            if raw_min_exp:
                try:
                    filter_dict["min_years_experience"] = max(0, int(raw_min_exp))
                except ValueError:
                    pass

            raw_loc = request.form.get("location_whitelist", "").strip()
            if raw_loc:
                filter_dict["location_whitelist"] = [
                    x.strip().lower() for x in raw_loc.split(",") if x.strip()
                ]

            raw_keywords = request.form.get("role_keywords", "").strip()
            if raw_keywords:
                filter_dict["role_keywords"] = [
                    x.strip().lower() for x in raw_keywords.split(",") if x.strip()
                ]

            raw_blacklist = request.form.get("title_blacklist", "").strip()
            if raw_blacklist:
                filter_dict["title_blacklist"] = [
                    x.strip().lower() for x in raw_blacklist.split(",") if x.strip()
                ]

            sec_cfg["filters"] = filter_dict
            secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
            msg = "Job filter settings saved to data/secrets.yaml."
            if request.headers.get("Accept") == "application/json" or request.is_json:
                return jsonify({"success": True, "message": msg})
            flash(msg)

        elif section == "scoring":
            scoring_dict = sec_cfg.get("scoring") or {}

            raw_thresh = request.form.get("match_threshold", "").strip()
            if raw_thresh:
                try:
                    pct = float(raw_thresh)
                    if pct > 1.0:
                        pct = pct / 100.0
                    scoring_dict["match_threshold"] = round(pct, 2)
                except ValueError:
                    pass

            raw_band_low = request.form.get("borderline_band_low", "").strip()
            raw_band_high = request.form.get("borderline_band_high", "").strip()
            if raw_band_low and raw_band_high:
                try:
                    b_low = float(raw_band_low)
                    b_high = float(raw_band_high)
                    if b_low > 1.0:
                        b_low = b_low / 100.0
                    if b_high > 1.0:
                        b_high = b_high / 100.0
                    scoring_dict["borderline_band"] = [round(b_low, 2), round(b_high, 2)]
                except ValueError:
                    pass

            sec_cfg["scoring"] = scoring_dict
            secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
            msg = "Scoring threshold settings saved to data/secrets.yaml."
            if request.headers.get("Accept") == "application/json" or request.is_json:
                return jsonify({"success": True, "message": msg})
            flash(msg)

        elif section == "salary":
            # Profile salary settings
            profile_path = data_dir / "profile.yaml"
            if profile_path.exists():
                try:
                    prof_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError:
                    prof_data = {}
            else:
                prof_data = {}

            sal_dict = prof_data.get("salary") or {}
            raw_pref = request.form.get("preferred_salary", "").strip()
            raw_min = request.form.get("min_acceptable_salary", "").strip()
            if raw_pref:
                try:
                    sal_dict["preferred"] = int(raw_pref.replace(",", "").replace(".", ""))
                except ValueError:
                    pass
            if raw_min:
                try:
                    sal_dict["min_acceptable"] = int(raw_min.replace(",", "").replace(".", ""))
                except ValueError:
                    pass
            prof_data["salary"] = sal_dict
            prof_data["salary_expectation"] = f"{sal_dict.get('min_acceptable', 6000000)}-{sal_dict.get('preferred', 7000000)} IDR/month"
            profile_path.write_text(yaml.safe_dump(prof_data, sort_keys=False), encoding="utf-8")
            msg = "Salary range settings saved to data/profile.yaml."
            if request.headers.get("Accept") == "application/json" or request.is_json:
                return jsonify({"success": True, "message": msg})
            flash(msg)

        elif section == "roles_search":
            search_dict = sec_cfg.get("search") or {}
            raw_roles = request.form.get("roles_list", "").strip()
            if raw_roles:
                roles_parsed = []
                for line in raw_roles.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if ":" in line:
                        name, slug = line.split(":", 1)
                    else:
                        name = line
                        slug = line.lower().replace(" ", "-")
                    roles_parsed.append({"name": name.strip(), "slug": slug.strip()})
                search_dict["roles"] = roles_parsed

            raw_locations = request.form.get("locations_list", "").strip()
            if raw_locations:
                locs_parsed = []
                for line in raw_locations.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if ":" in line:
                        name, slug = line.split(":", 1)
                    else:
                        name = line
                        slug = line.replace(" ", "-")
                    locs_parsed.append({"name": name.strip(), "slug": slug.strip()})
                search_dict["locations"] = locs_parsed

            sec_cfg["search"] = search_dict
            secrets_path.write_text(yaml.safe_dump(sec_cfg, sort_keys=False), encoding="utf-8")
            msg = "Target search roles & locations saved."
            if request.headers.get("Accept") == "application/json" or request.is_json:
                return jsonify({"success": True, "message": msg})
            flash(msg)
        else:
            msg = "No changes made."
            if request.headers.get("Accept") == "application/json" or request.is_json:
                return jsonify({"success": True, "message": msg})
            flash(msg)

        return redirect(url_for("settings"))

    @app.get("/settings/models/<provider>")
    def get_provider_models(provider: str):
        cfg = get_merged_config()
        models = list_models_for_provider(provider, cfg=cfg)
        return jsonify({"provider": provider, "models": models})

    @app.post("/settings/oauth/<provider>/login")
    def oauth_login(provider: str):
        provider = provider.lower()
        storage = TokenStorage(data_dir / "auth_tokens.json")
        try:
            if provider == "claude":
                start_claude_oauth()
                flash("Successfully authenticated with Claude Code (Anthropic)!")
            elif provider in ("codex", "chatgpt"):
                start_codex_oauth()
                flash("Successfully authenticated with OpenAI Codex / ChatGPT!")
            elif provider in ("gemini", "antigravity"):
                start_gemini_oauth()
                flash("Successfully authenticated with Google Antigravity!")
            else:
                flash(f"Unknown OAuth provider: {provider}")
        except Exception as e:
            flash(f"Authentication failed: {e}")
        return redirect(url_for("settings"))

    @app.post("/settings/oauth/<provider>/logout")
    def oauth_logout(provider: str):
        storage = TokenStorage(data_dir / "auth_tokens.json")
        storage.delete_provider(provider.lower())
        flash(f"Logged out from {provider.capitalize()}.")
        return redirect(url_for("settings"))

    @app.post("/settings/oauth/copilot/device-code")
    def copilot_device_code():
        try:
            data = request_copilot_device_code()
            return jsonify({
                "user_code": data.get("user_code"),
                "verification_uri": data.get("verification_uri"),
                "device_code": data.get("device_code"),
                "interval": data.get("interval", 5),
                "expires_in": data.get("expires_in", 900),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/settings/oauth/copilot/poll")
    def copilot_poll():
        device_code = request.json.get("device_code", "") if request.json else request.form.get("device_code", "")
        interval = int(request.json.get("interval", 5) if request.json else request.form.get("interval", 5))
        try:
            token_data = poll_copilot_device_token(device_code, interval=interval, timeout=120)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/settings/test-llm")
    def test_llm():
        cfg = get_merged_config()
        try:
            resp = complete(
                messages=[{"role": "user", "content": "Respond with 'LLM connection successful!'"}],
                cfg=cfg,
                max_tokens=30,
            )
            return jsonify({"success": True, "response": resp.strip()})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

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
    elif cmd == "pipeline":
        add_int(argv, "--pages", "pipeline_pages")
        add_int(argv, "--limit", "pipeline_limit")
        if form.get("pipeline_cards_only"):
            argv.append("--cards-only")
        if form.get("pipeline_offline"):
            argv.append("--offline")
        if form.get("pipeline_llm_letter"):
            argv.append("--llm-letter")
        if form.get("pipeline_headless"):
            argv.append("--headless")
        if form.get("pipeline_execute"):
            argv.append("--execute")
    elif cmd == "login":
        argv.append("--auto-wait")
    return argv
