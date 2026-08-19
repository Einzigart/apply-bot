"""apply-bot CLI.

  python -m src.run login
  python -m src.run migrate-log --log PATH
  python -m src.run discover [--pages N] [--headless] [--roles ...] [--locations ...]
  python -m src.run score [--offline] [--limit N]
  python -m src.run review
  python -m src.run decide <jobstreet_id> apply|skip [--reason "..."]
  python -m src.run apply [--execute] [--llm-letter] [--limit N] [--headless]
  python -m src.run pipeline [--pages N] [--execute] [--offline] [--llm-letter] [--limit N] [--headless]
  python -m src.run calibrate
  python -m src.run serve [--port N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .config import DB_PATH, STORAGE_STATE_PATH, load_config, load_profile
from .db import connect, latest_evaluations


def cmd_login(args):
    from playwright.sync_api import sync_playwright
    from .scrape import _new_page

    cfg = load_config()
    base_url = cfg.get("search", {}).get("base", "https://id.jobstreet.com")
    login_url = f"{base_url}/id/oauth/login?returnUrl=%2F"

    print("Opening browser for Jobstreet login...")
    print(f"URL: {login_url}")
    print("Please log in and complete any verification/CAPTCHA in the opened window.")

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-default-browser-check",
        "--no-first-run",
    ]
    # Check for custom or detected Chrome executable path
    custom_executable = os.environ.get("CHROME_PATH") or (cfg.get("search") or {}).get("chrome_path")
    if not custom_executable:
        from .api.routers.settings import _find_chrome_executable
        custom_executable = _find_chrome_executable(cfg)

    launch_channels = ["chrome", "chromium", "msedge", None]
    if custom_executable and os.path.exists(custom_executable):
        launch_channels = [custom_executable] + launch_channels

    with sync_playwright() as p:
        browser = None
        for target in launch_channels:
            try:
                if target and os.path.exists(target):
                    browser = p.chromium.launch(executable_path=target, headless=False, args=launch_args, ignore_default_args=["--enable-automation"])
                elif target:
                    browser = p.chromium.launch(channel=target, headless=False, args=launch_args, ignore_default_args=["--enable-automation"])
                else:
                    browser = p.chromium.launch(headless=False, args=launch_args, ignore_default_args=["--enable-automation"])
                break
            except Exception:
                continue
        if not browser:
            raise RuntimeError("Failed to launch browser for login")

        context = browser.new_context(
            locale="id-ID",
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        )
        if STORAGE_STATE_PATH.exists():
            try:
                state_data = json.loads(STORAGE_STATE_PATH.read_text(encoding="utf-8"))
                context.add_cookies(state_data.get("cookies", []))
            except Exception:
                pass

        page = _new_page(context)
        page.goto(login_url, wait_until="domcontentloaded")

        if args.auto_wait:
            print("Waiting up to 300s for successful login detection (or window close)...")
            start_time = time.time()
            saved = False
            while time.time() - start_time < 300:
                if page.is_closed():
                    print("Browser window was closed.")
                    break

                try:
                    cookies = context.cookies()
                    current_url = page.url
                    # Check for Jobstreet/SEEK auth indicators
                    has_auth_cookie = any(
                        "session" in c["name"].lower() or "auth" in c["name"].lower() or "token" in c["name"].lower()
                        for c in cookies
                    )
                    if ("/login" not in current_url and "sign" not in current_url and "auth" not in current_url) and has_auth_cookie:
                        print("Login detected! Waiting for auth redirects to settle...")
                        # Allow Jobstreet to finish setting cross-domain cookies and tokens
                        time.sleep(5)
                        try:
                            # Navigate to root homepage to ensure final auth cookies are set on .jobstreet.com
                            page.goto("https://id.jobstreet.com/id", wait_until="networkidle", timeout=15000)
                            time.sleep(2)
                        except Exception:
                            pass
                        STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                        context.storage_state(path=str(STORAGE_STATE_PATH))
                        saved = True
                        break
                except Exception:
                    # Page or context might have closed
                    break

                time.sleep(1)

            if not saved and not page.is_closed():
                print("Saving current browser session state before closing...")
                STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(STORAGE_STATE_PATH))
        else:
            input("Press Enter here once you have finished logging in: ")
            STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(STORAGE_STATE_PATH))

        try:
            context.close()
        except Exception:
            pass

    print(f"Session saved successfully to {STORAGE_STATE_PATH}")


def cmd_migrate(args):
    from .migrate_log import migrate

    log_path = Path(args.log)
    if not log_path.exists():
        sys.exit(f"log not found: {log_path}")
    conn = connect(DB_PATH)
    stats = migrate(conn, log_path.read_text(encoding="utf-8"))
    print(f"rows seen: {stats.rows}")
    print(f"imported:  {stats.imported} (linked to jobstreet id: {stats.linked}, "
          f"unlinked: {stats.unlinked}, non-submitted skipped: {stats.skipped_status}, "
          f"duplicate ads reused: {stats.duplicate_ads})")
    print(f"notable skips imported: {stats.skipped_jobs}")
    for e in stats.errors:
        print(f"  ERROR {e}")


def cmd_discover(args):
    from .scrape import BotWallError, discover

    conn = connect(DB_PATH)
    try:
        stats = discover(
            load_config(), conn,
            pages=args.pages, headless=args.headless,
            roles=args.roles, locations=args.locations,
            fetch_details=not args.cards_only,
            use_playwright=args.browser,
        )
    except BotWallError as e:
        sys.exit(str(e))
    print(f"urls visited: {stats.urls_visited}")
    print(f"cards seen:   {stats.cards_seen}")
    print(f"title-filtered (pre-detail): {stats.title_filtered}")
    print(f"details fetched: {stats.details_fetched}")
    print(f"new/updated jobs: {stats.new_jobs}")
    for e in stats.errors[:10]:
        print(f"  ERROR {e}")


def cmd_score(args):
    from .score import score_pending

    conn = connect(DB_PATH)
    res = score_pending(load_config(), conn, load_profile(),
                        offline=args.offline, limit=args.limit)
    print(f"filtered out by rules: {res['filtered']}")
    print(f"scored: {res['scored']} ({'offline' if args.offline else 'LLM'})")
    for row in latest_evaluations(conn, "apply"):
        print(f"  APPLY  {row['match_pct']}%  {row['title']} @ {row['company']}")
    for row in latest_evaluations(conn, "review"):
        print(f"  REVIEW {row['match_pct']}%  {row['title']} @ {row['company']} — {row['reason']}")


def cmd_review(_args):
    conn = connect(DB_PATH)
    queue = latest_evaluations(conn, "review")
    if not queue:
        print("review queue is empty")
        return
    print(f"{len(queue)} jobs need your decision:\n")
    for row in queue:
        print(f"  {row['match_pct'] or '?'}%  {row['title']} @ {row['company']}")
        print(f"       {row['location']} — {row['reason']}")
        print(f"       {row['url']}\n")


def cmd_decide(args):
    from .db import record_decision

    conn = connect(DB_PATH)
    if not record_decision(conn, args.job_id, args.decision, args.reason):
        sys.exit(f"job not found: {args.job_id}")
    print(f"{args.job_id}: latest decision now '{args.decision}'")


def cmd_apply(args):
    from .apply import run_apply

    cfg = load_config()
    limit = args.limit if args.limit is not None else cfg.get("apply", {}).get("max_applications_per_run")
    conn = connect(DB_PATH)
    results = run_apply(
        cfg, conn, load_profile(),
        execute=args.execute, use_llm_letter=args.llm_letter,
        limit=limit, headless=args.headless,
    )
    print(f"\nsubmitted: {results['submitted']}, dry-run: {results['dry-run']}, "
          f"failed: {results['failed']}, skipped (cooldown): {results['skipped']}")
    if not args.execute:
        print("dry-run mode — nothing was submitted. Re-run with --execute to submit.")


def cmd_pipeline(args):
    from .pipeline import BotWallError, run_pipeline

    conn = connect(DB_PATH)
    try:
        stats = run_pipeline(
            load_config(),
            conn,
            load_profile(),
            pages=args.pages,
            headless=args.headless,
            roles=args.roles,
            locations=args.locations,
            fetch_details=not args.cards_only,
            use_playwright=args.browser,
            offline_score=args.offline,
            execute=args.execute,
            use_llm_letter=args.llm_letter,
            apply_limit=args.limit,
        )
    except BotWallError as e:
        sys.exit(str(e))

    print("\n--- Pipeline Summary ---")
    print(f"pages processed: {stats.pages_processed}")
    print(f"cards seen:      {stats.cards_seen}")
    print(f"title-filtered:  {stats.title_filtered}")
    print(f"details fetched: {stats.details_fetched}")
    print(f"new/updated:     {stats.new_jobs}")
    print(f"scored:          {stats.scored}")
    print(f"submitted:       {stats.submitted}")
    print(f"dry-run:         {stats.dry_run}")
    print(f"failed:          {stats.failed}")
    print(f"skipped (cooldown): {stats.skipped_cooldown}")
    if not args.execute:
        print("dry-run mode — applications prepared without final submit.")
    for e in stats.errors[:10]:
        print(f"  ERROR {e}")


def cmd_serve(args):
    import uvicorn
    from .api.main import create_app

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=args.port)


def cmd_calibrate(_args):
    """Re-run today's rules over migrated history.

    Migrated rows have no job descriptions, so this mainly exercises the
    title/location/dedup gates. Full calibration happens in Phase 2 against
    freshly scraped jobs with descriptions.
    """
    from .filters import passes_all

    cfg = load_config()
    conn = connect(DB_PATH)
    rows = conn.execute(
        """SELECT j.*, a.applied_at FROM applications a
           JOIN jobs j ON j.id = a.job_id ORDER BY a.applied_at"""
    ).fetchall()
    agree, disagree = 0, []
    for row in rows:
        job = dict(row)
        # historical application must ignore its own cooldown entry:
        ok, reason = passes_all(job, cfg, None)
        if ok:
            agree += 1
        else:
            disagree.append((job["title"], job["company"], reason))
    print(f"{len(rows)} historical applications re-checked against current rules "
          f"(without cooldown gate):")
    print(f"  rules agree (would still apply): {agree}")
    print(f"  rules disagree (would skip):     {len(disagree)}")
    for title, company, reason in disagree[:20]:
        print(f"    - {title} @ {company}: {reason}")


def main():
    p = argparse.ArgumentParser(prog="apply-bot")
    sub = p.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("login", help="log in interactively and save session state")
    l.add_argument("--auto-wait", action="store_true", help="wait for login redirection automatically instead of stdin")
    l.set_defaults(fn=cmd_login)

    m = sub.add_parser("migrate-log", help="import application-log.md into SQLite")
    m.add_argument("--log", required=True,
                   help="path to the legacy application-log.md")
    m.set_defaults(fn=cmd_migrate)

    d = sub.add_parser("discover", help="scrape SERPs + job details (read-only)")
    d.add_argument("--pages", type=int, default=2)
    d.add_argument("--headless", action="store_true")
    d.add_argument("--browser", action="store_true",
                   help="force Playwright browser scraping instead of fast HTTP extraction")
    d.add_argument("--roles", nargs="*")
    d.add_argument("--locations", nargs="*")
    d.add_argument("--cards-only", action="store_true",
                   help="skip detail-page fetching (faster, coarser)")
    d.set_defaults(fn=cmd_discover)

    s = sub.add_parser("score", help="filter + score pending jobs")
    s.add_argument("--offline", action="store_true", help="keyword scorer, no LLM")
    s.add_argument("--limit", type=int)
    s.set_defaults(fn=cmd_score)

    r = sub.add_parser("review", help="show the borderline review queue")
    r.set_defaults(fn=cmd_review)

    v = sub.add_parser("decide", help="record a review verdict for a job")
    v.add_argument("job_id", help="jobstreet id (from the review queue)")
    v.add_argument("decision", choices=["apply", "skip"])
    v.add_argument("--reason", help="why (kept for calibration)")
    v.set_defaults(fn=cmd_decide)

    a = sub.add_parser("apply", help="apply to approved jobs (dry-run by default)")
    a.add_argument("--execute", action="store_true", help="actually submit")
    a.add_argument("--llm-letter", action="store_true")
    a.add_argument("--limit", type=int, default=10)
    a.add_argument("--headless", action="store_true")
    a.set_defaults(fn=cmd_apply)

    pl = sub.add_parser("pipeline", help="run full pipeline page-by-page (scrape -> score -> apply)")
    pl.add_argument("--pages", type=int, default=2)
    pl.add_argument("--headless", action="store_true")
    pl.add_argument("--browser", action="store_true",
                    help="force Playwright browser scraping instead of fast HTTP extraction")
    pl.add_argument("--roles", nargs="*")
    pl.add_argument("--locations", nargs="*")
    pl.add_argument("--cards-only", action="store_true",
                    help="skip detail-page fetching")
    pl.add_argument("--offline", action="store_true", help="keyword scorer, no LLM")
    pl.add_argument("--execute", action="store_true", help="actually submit applications")
    pl.add_argument("--llm-letter", action="store_true", help="tailor cover letter via LLM")
    pl.add_argument("--limit", type=int, help="cap total applications")
    pl.set_defaults(fn=cmd_pipeline)

    c = sub.add_parser("calibrate", help="re-check history against current rules")
    c.set_defaults(fn=cmd_calibrate)

    w = sub.add_parser("serve", help="web UI on 127.0.0.1 (local use only)")
    # 5001: macOS AirPlay Receiver occupies the Flask default 5000.
    w.add_argument("--port", type=int, default=5001)
    w.set_defaults(fn=cmd_serve)

    args = p.parse_args()

    # Record every pipeline run (terminal- or UI-triggered) in the runs table.
    # The web runner pre-creates a row and hands its id over via env var.
    if args.cmd == "serve":
        args.fn(args)
        return
    from .db import finish_run, start_run

    conn = connect(DB_PATH)
    run_id = os.environ.get("APPLY_BOT_RUN_ID")
    run_id = int(run_id) if run_id else start_run(conn, "src.run " + " ".join(sys.argv[1:]))
    try:
        args.fn(args)
    except SystemExit as e:
        finish_run(conn, run_id, f"exit {e.code}")
        raise
    except Exception as e:
        finish_run(conn, run_id, f"error: {e}")
        raise
    finish_run(conn, run_id, "ok")


def cli_entry():
    main()


if __name__ == "__main__":
    main()
