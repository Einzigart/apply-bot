"""apply-bot CLI.

  python -m src.run migrate-log [--log PATH]
  python -m src.run discover [--pages N] [--headless] [--roles ...] [--locations ...]
  python -m src.run score [--offline] [--limit N]
  python -m src.run review
  python -m src.run decide <jobstreet_id> apply|skip [--reason "..."]
  python -m src.run apply [--execute] [--llm-letter] [--limit N] [--headless]
  python -m src.run calibrate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DB_PATH, load_answers, load_config, load_profile
from .db import connect, latest_evaluations


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

    conn = connect(DB_PATH)
    results = run_apply(
        load_config(), conn, load_answers(),
        execute=args.execute, use_llm_letter=args.llm_letter,
        limit=args.limit, headless=args.headless,
    )
    print(f"\nsubmitted: {results['submitted']}, dry-run: {results['dry-run']}, "
          f"failed: {results['failed']}, skipped (cooldown): {results['skipped']}")
    if not args.execute:
        print("dry-run mode — nothing was submitted. Re-run with --execute to submit.")


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

    m = sub.add_parser("migrate-log", help="import application-log.md into SQLite")
    m.add_argument("--log", default="docs/legacy/application-log.md")
    m.set_defaults(fn=cmd_migrate)

    d = sub.add_parser("discover", help="scrape SERPs + job details (read-only)")
    d.add_argument("--pages", type=int, default=2)
    d.add_argument("--headless", action="store_true")
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

    c = sub.add_parser("calibrate", help="re-check history against current rules")
    c.set_defaults(fn=cmd_calibrate)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
