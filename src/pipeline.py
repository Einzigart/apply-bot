"""End-to-end pipeline: per-page scrape -> score -> apply loop.

Processes each search page iteratively:
1. Scrape SERP cards for the page (and detail descriptions if fetch_details).
2. Filter & score newly scraped jobs (offline or LLM).
3. If suitable approved jobs ('apply') exist on this page, apply to all of them immediately.
4. Continue to the next page / search query until done.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright

from .apply import run_apply
from .config import load_config, load_profile
from .db import find_job, upsert_job
from .filters import title_check
from .score import score_pending
from .scrape import (
    BotWallError,
    _check_bot_wall,
    _launch,
    _new_context,
    _new_page,
    _pace,
    build_search_urls,
    scrape_detail,
    scrape_detail_http,
    scrape_serp,
    scrape_serp_http,
)


@dataclass
class PipelineStats:
    pages_processed: int = 0
    cards_seen: int = 0
    new_jobs: int = 0
    details_fetched: int = 0
    title_filtered: int = 0
    scored: int = 0
    submitted: int = 0
    dry_run: int = 0
    failed: int = 0
    skipped_cooldown: int = 0
    errors: list[str] = field(default_factory=list)


def run_pipeline(
    cfg: dict,
    conn,
    profile: dict,
    *,
    pages: int = 2,
    headless: bool = True,
    roles: list[str] | None = None,
    locations: list[str] | None = None,
    fetch_details: bool = True,
    use_playwright: bool = False,
    offline_score: bool = False,
    execute: bool = False,
    use_llm_letter: bool = False,
    apply_limit: int | None = None,
) -> PipelineStats:
    """Run full pipeline page-by-page: scrape -> score -> apply -> next page."""
    stats = PipelineStats()
    urls = build_search_urls(cfg, roles, locations)
    seen_ids: set[str] = set()

    total_queries = len(urls) * pages
    query_count = 0
    total_applied = 0

    print(
        f"Starting full pipeline run across {len(urls)} search(es) "
        f"({pages} page(s) each, ~{total_queries} queries total)..."
    )
    print(
        f"Options: offline_score={offline_score}, execute={execute}, "
        f"llm_letter={use_llm_letter}, headless={headless}"
    )

    pw_browser = None
    pw_page = None
    playwright_ctx = None

    try:
        if use_playwright:
            playwright_ctx = sync_playwright().start()
            pw_browser = _launch(playwright_ctx, headless=headless)
            pw_page = _new_page(_new_context(pw_browser))

        for u_idx, url in enumerate(urls, 1):
            for page_no in range(1, pages + 1):
                query_count += 1
                page_url = url if page_no == 1 else f"{url}?page={page_no}"
                short_path = page_url.replace(cfg.get("search", {}).get("base", ""), "")
                print(f"\n[{query_count}/{total_queries}] Page: {short_path}", flush=True)

                _pace(cfg)

                # 1. SCRAPE
                cards = None
                if not use_playwright:
                    try:
                        cards = scrape_serp_http(page_url, cfg)
                    except BotWallError:
                        raise
                    except Exception as e:
                        stats.errors.append(f"HTTP SERP {page_url}: {e}")

                if cards is None:
                    if pw_browser is None:
                        playwright_ctx = sync_playwright().start()
                        pw_browser = _launch(playwright_ctx, headless=headless)
                        pw_page = _new_page(_new_context(pw_browser))
                    try:
                        cards = scrape_serp(pw_page, page_url, cfg)
                    except BotWallError:
                        raise
                    except Exception as e:
                        stats.errors.append(f"Playwright SERP {page_url}: {e}")
                        break

                stats.pages_processed += 1
                if not cards:
                    print("  -> 0 jobs found on this page")
                    break

                stats.cards_seen += len(cards)
                page_saved_jobs = []

                for card in cards:
                    jid = card["jobstreet_id"]
                    if jid in seen_ids:
                        continue
                    seen_ids.add(jid)

                    existing = find_job(conn, jid)
                    ok, _reason = title_check(card.get("title") or "", cfg)
                    if not ok:
                        stats.title_filtered += 1
                        continue
                    if existing and existing["description"]:
                        # Job already exists with description in DB
                        # If it has not been evaluated, we can still include it in this batch
                        page_saved_jobs.append(dict(existing))
                        continue

                    job = card
                    if fetch_details:
                        detail_job = None
                        if not use_playwright:
                            try:
                                detail_job = scrape_detail_http(card, cfg)
                            except BotWallError:
                                raise
                            except Exception as e:
                                stats.errors.append(f"HTTP detail {jid}: {e}")

                        if detail_job is None:
                            if pw_browser is None:
                                playwright_ctx = sync_playwright().start()
                                pw_browser = _launch(playwright_ctx, headless=headless)
                                pw_page = _new_page(_new_context(pw_browser))
                            try:
                                _pace(cfg)
                                detail_job = scrape_detail(pw_page, card, cfg)
                            except BotWallError:
                                raise
                            except Exception as e:
                                stats.errors.append(f"Playwright detail {jid}: {e}")

                        if detail_job:
                            job = detail_job
                            stats.details_fetched += 1

                    job_id = upsert_job(conn, job)
                    stats.new_jobs += 1
                    saved_job = dict(job)
                    saved_job["id"] = job_id
                    page_saved_jobs.append(saved_job)

                print(
                    f"  -> {len(cards)} cards seen, {len(page_saved_jobs)} relevant candidates on page",
                    flush=True,
                )

                if not page_saved_jobs:
                    continue

                # 2. SCORE newly discovered jobs for this page
                score_res = score_pending(
                    cfg,
                    conn,
                    profile,
                    offline=offline_score,
                    jobs=page_saved_jobs,
                )
                stats.scored += score_res["scored"]
                print(
                    f"  -> Scored {score_res['scored']} jobs (filtered {score_res['filtered']})",
                    flush=True,
                )

                # Check which of these jobs scored 'apply'
                page_job_ids = {j["id"] for j in page_saved_jobs}
                suitable_rows = conn.execute(
                    f"""SELECT j.*, e.match_pct, e.reason FROM jobs j
                       JOIN evaluations e ON e.job_id = j.id
                       WHERE e.id = (SELECT MAX(id) FROM evaluations WHERE job_id = j.id)
                         AND e.decision = 'apply'
                         AND j.id IN ({','.join('?' for _ in page_job_ids)})
                         AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id)
                       ORDER BY e.match_pct DESC""",
                    list(page_job_ids),
                ).fetchall()

                suitable_jobs = [dict(r) for r in suitable_rows]
                if not suitable_jobs:
                    print("  -> No suitable ('apply') jobs on this page to apply")
                    continue

                print(
                    f"  -> Found {len(suitable_jobs)} suitable job(s) ready for application! Applying now...",
                    flush=True,
                )

                # 3. APPLY to all suitable jobs from this page
                rem_limit = None
                if apply_limit is not None:
                    rem_limit = max(0, apply_limit - total_applied)
                    if rem_limit <= 0:
                        print("  -> Apply limit reached for this run. Skipping application.")
                        continue
                    suitable_jobs = suitable_jobs[:rem_limit]

                app_res = run_apply(
                    cfg,
                    conn,
                    profile,
                    execute=execute,
                    use_llm_letter=use_llm_letter,
                    limit=rem_limit,
                    headless=headless,
                    jobs=suitable_jobs,
                )

                stats.submitted += app_res["submitted"]
                stats.dry_run += app_res["dry-run"]
                stats.failed += app_res["failed"]
                stats.skipped_cooldown += app_res["skipped"]
                total_applied += app_res["submitted"] + app_res["dry-run"]

                print(
                    f"  -> Page application results: {app_res['submitted']} submitted, "
                    f"{app_res['dry-run']} dry-run, {app_res['failed']} failed, "
                    f"{app_res['skipped']} skipped (cooldown)",
                    flush=True,
                )

                if apply_limit is not None and total_applied >= apply_limit:
                    print(f"\nReached total application limit ({apply_limit}). Stopping pipeline.")
                    return stats

    finally:
        if pw_browser:
            pw_browser.close()
        if playwright_ctx:
            playwright_ctx.stop()

    return stats
