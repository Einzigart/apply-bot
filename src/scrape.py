"""Stage 1: scrape search results and job details. Zero LLM tokens.

Works anonymously (search/detail pages are public). Login is only needed for
the apply stage.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright, Page

from . import selectors as S
from .db import norm_text, upsert_job, find_job
from .filters import title_check


class BotWallError(RuntimeError):
    pass


@dataclass
class DiscoverStats:
    urls_visited: int = 0
    cards_seen: int = 0
    new_jobs: int = 0
    details_fetched: int = 0
    title_filtered: int = 0
    errors: list[str] = field(default_factory=list)


def build_search_urls(cfg: dict, roles: list[str] | None = None,
                      locations: list[str] | None = None) -> list[str]:
    s = cfg["search"]
    urls = []
    for role in s["roles"]:
        if roles and role["name"] not in roles and role["slug"] not in roles:
            continue
        for loc in s["locations"]:
            if locations and loc["name"] not in locations and loc["slug"] not in locations:
                continue
            urls.append(s["url_template"].format(
                base=s["base"], role_slug=role["slug"], loc_slug=loc["slug"]))
    return urls


def _pace(cfg: dict) -> None:
    lo, hi = cfg["apply"]["pacing_seconds"]
    time.sleep(random.uniform(lo, hi))


def _check_bot_wall(page: Page) -> None:
    try:
        text = page.locator("body").inner_text()[:1000].lower()
    except Exception:
        return
    if any(m in text for m in S.BOT_WALL_MARKERS):
        raise BotWallError(f"bot wall detected at {page.url} — stopping run")


def _launch(p, headless: bool):
    try:
        return p.chromium.launch(channel="chrome", headless=headless)
    except Exception:
        return p.chromium.launch(headless=headless)


def _lines(teaser: str) -> list[str]:
    return [l.strip() for l in (teaser or "").splitlines() if l.strip()]


def _guess_company(teaser: str) -> str | None:
    lines = _lines(teaser)
    for i, line in enumerate(lines):
        if line.lower() == "di" and i + 1 < len(lines):
            return lines[i + 1]
        m = re.match(r"^di\s+(.+)$", line, re.I)
        if m:
            return m.group(1)
    return None


def _guess_location(teaser: str, cfg: dict) -> str | None:
    # NB: no "indonesia" keyword — company names like "PT Hyundai Capital
    # Finance Indonesia" would match. Detail pages give the authoritative
    # location; this is only a SERP heuristic.
    for line in _lines(teaser):
        low = line.lower()
        if any(k in low for k in ("jakarta", "tangerang", "remote", "banten",
                                  "bogor", "depok", "bekasi")):
            return line
    return None


def _guess_salary(teaser: str) -> str | None:
    for line in _lines(teaser):
        low = line.lower()
        if "idr" in low or "rp" in low or "per month" in low or "per bulan" in low:
            if any(c.isdigit() for c in line):
                return line
    return None


def _title_from_teaser(teaser: str) -> str | None:
    """Card layout: 'Listed ... ago' / TITLE / 'di' / COMPANY / ..."""
    for line in _lines(teaser):
        if line.lower().startswith("listed"):
            continue
        return line
    return None


def scrape_serp(page: Page, url: str, cfg: dict) -> list[dict]:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    try:
        page.wait_for_selector(S.SERP_CARD, timeout=15_000)
    except Exception:
        return []  # no results for this combo
    _check_bot_wall(page)

    jobs, seen = [], set()
    for card in page.query_selector_all(S.SERP_CARD):
        link = card.query_selector(S.SERP_JOB_LINK)
        if not link:
            continue
        href = link.get_attribute("href") or ""
        m = re.search(S.JOB_ID_RE, href)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        teaser = card.inner_text()
        jobs.append({
            "jobstreet_id": m.group(1),
            "url": f"{cfg['search']['base']}/id/job/{m.group(1)}",
            "title": _title_from_teaser(teaser),
            "teaser": teaser,
            "company": _guess_company(teaser),
            "location": _guess_location(teaser, cfg),
            "salary_text": _guess_salary(teaser),
        })
    return jobs


def _safe_text(page: Page, selector: str) -> str | None:
    el = page.query_selector(selector)
    if not el:
        return None
    try:
        return el.inner_text().strip() or None
    except Exception:
        return None


def scrape_detail(page: Page, job: dict, cfg: dict) -> dict:
    page.goto(job["url"], wait_until="domcontentloaded", timeout=45_000)
    try:
        page.wait_for_selector(S.DETAIL_DESCRIPTION, timeout=15_000)
    except Exception as e:
        raise S.SiteChangedError(f"detail page missing {S.DETAIL_DESCRIPTION}: {job['url']}") from e
    _check_bot_wall(page)

    out = dict(job)
    out["title"] = _safe_text(page, S.DETAIL_TITLE) or job.get("title")
    out["company"] = _safe_text(page, S.DETAIL_ADVERTISER) or job.get("company")
    out["location"] = _safe_text(page, S.DETAIL_LOCATION) or job.get("location")
    out["salary_text"] = _safe_text(page, S.DETAIL_SALARY) or job.get("salary_text")
    out["description"] = _safe_text(page, S.DETAIL_DESCRIPTION)
    extras = [
        _safe_text(page, S.DETAIL_CLASSIFICATIONS),
        _safe_text(page, S.DETAIL_WORK_TYPE),
        _safe_text(page, S.DETAIL_BADGES),
    ]
    out["teaser"] = "\n".join(x for x in extras if x) or job.get("teaser")
    return out


def discover(cfg: dict, conn, *, pages: int = 2, headless: bool = True,
             roles: list[str] | None = None, locations: list[str] | None = None,
             fetch_details: bool = True) -> DiscoverStats:
    stats = DiscoverStats()
    urls = build_search_urls(cfg, roles, locations)
    seen_ids: set[str] = set()

    with sync_playwright() as p:
        browser = _launch(p, headless=headless)
        page = browser.new_context(
            locale="id-ID", viewport={"width": 1366, "height": 900}
        ).new_page()
        try:
            for url in urls:
                for page_no in range(1, pages + 1):
                    page_url = url if page_no == 1 else f"{url}?page={page_no}"
                    try:
                        cards = scrape_serp(page, page_url, cfg)
                    except BotWallError:
                        raise
                    except Exception as e:
                        stats.errors.append(f"{page_url}: {e}")
                        break
                    stats.urls_visited += 1
                    if not cards:
                        break
                    stats.cards_seen += len(cards)
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
                            continue
                        job = card
                        if fetch_details:
                            _pace(cfg)
                            try:
                                job = scrape_detail(page, card, cfg)
                                stats.details_fetched += 1
                            except Exception as e:
                                stats.errors.append(f"detail {jid}: {e}")
                        upsert_job(conn, job)
                        stats.new_jobs += 1
                    _pace(cfg)
        finally:
            browser.close()
    return stats
