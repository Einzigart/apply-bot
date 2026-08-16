"""Stage 1: scrape search results and job details. Zero LLM tokens.

Fast HTTP extraction via JobStreet's server-rendered Redux data
(`window.SEEK_REDUX_DATA`) with automatic fallback to Playwright if needed.
Works anonymously (search/detail pages are public). Login is only needed for
the apply stage.
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright, Page

from . import selectors as S
from .config import BROWSER_PROFILE_DIR, STORAGE_STATE_PATH
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


DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def extract_seek_redux_data(html_text: str) -> dict | None:
    """Extract the `window.SEEK_REDUX_DATA = {...}` JSON payload from JobStreet HTML."""
    marker = "window.SEEK_REDUX_DATA = "
    idx = html_text.find(marker)
    if idx == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html_text, idx + len(marker))
        return obj
    except json.JSONDecodeError:
        return None


def html_to_markdown(raw_html: str) -> str:
    """Convert HTML snippet to clean text / markdown representation locally."""
    if not raw_html or not raw_html.strip():
        return ""

    # Replace list items with bullets
    text = re.sub(r'<li\b[^>]*>', '\n- ', raw_html, flags=re.IGNORECASE)
    # Replace block-level elements with newlines
    text = re.sub(r'<(?:br|p|div|h[1-6]|ul|ol)\b[^>]*\/?>', '\n', text, flags=re.IGNORECASE)
    # Strip any remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = html.unescape(text)

    # Normalize whitespace & multiple blank lines
    lines = [line.strip() for line in text.splitlines()]
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    return "\n".join(cleaned).strip()


def fetch_http_page(url: str, user_agent: str | None = None, timeout: int = 20) -> str:
    """Fetch URL over HTTP using standard headers."""
    ua = user_agent or random.choice(DEFAULT_USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


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


def _is_bot_blocked(page: Page) -> bool:
    try:
        title = (page.title() or "").lower()
        url = (page.url or "").lower()
        if any(m in title for m in ("just a moment", "security check", "cloudflare", "turnstile", "captcha")):
            return True
        if "__cf_chl" in url or "challenge" in url:
            return True
        text = page.locator("body").inner_text()[:1000].lower()
        if any(m in text for m in S.BOT_WALL_MARKERS):
            return True
        # If body is empty or has Cloudflare script
        content = (page.content() or "")[:1000].lower()
        if "challenges.cloudflare.com" in content or "cf-browser-verification" in content:
            return True
        return False
    except Exception:
        return False


def _check_bot_wall(page: Page, wait_timeout: int = 120) -> None:
    """Checks for bot walls / Cloudflare challenges.
    If detected, pauses and polls every second up to `wait_timeout` (measured: 120s default)
    giving the user or browser time to solve the verification challenge.
    Saves updated cookies to storage_state.json upon successful clearance.
    """
    if not _is_bot_blocked(page):
        return

    print(f"\n[Cloudflare / Bot Challenge Detected] at {page.url}")
    print(f"Pausing pipeline to wait for verification (timeout: {wait_timeout}s)...")
    print("If running in headed mode, please complete the challenge in the browser window.")

    start_t = time.time()
    while time.time() - start_t < wait_timeout:
        time.sleep(2)
        try:
            if not _is_bot_blocked(page):
                print("Cloudflare verification cleared! Resuming pipeline...")
                # Save updated clearance cookies back to storage_state
                try:
                    STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    page.context.storage_state(path=str(STORAGE_STATE_PATH))
                except Exception:
                    pass
                return
        except Exception:
            break

    raise BotWallError(f"bot wall challenge timed out after {wait_timeout}s at {page.url} — stopping run")


def _check_bot_wall_html(html_text: str, url: str) -> None:
    low = (html_text or "")[:2000].lower()
    if any(m in low for m in S.BOT_WALL_MARKERS):
        raise BotWallError(f"bot wall detected at {url} — stopping run")


def _launch_persistent(p, headless: bool):
    """Launch persistent browser context using dedicated profile directory.
    Retains cookies, local storage, and Cloudflare clearance between runs.
    """
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # If not running in explicit standalone headless mode or if EMBEDDED mode is preferred,
    # run headless with remote-debugging-port so it streams into the UI without popups
    is_app_mode = os.environ.get("APPLY_BOT_APP_MODE", "1") == "1"
    actual_headless = True if is_app_mode else headless

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-default-browser-check",
        "--no-first-run",
        "--remote-debugging-port=9222",
    ]
    kwargs = {
        "user_data_dir": str(BROWSER_PROFILE_DIR),
        "headless": actual_headless,
        "args": launch_args,
        "ignore_default_args": ["--enable-automation"],
        "locale": "id-ID",
        "viewport": {"width": 1366, "height": 900},
    }
    last_err = None
    for ch in ["chrome", "msedge", "chromium", None]:
        try:
            if ch:
                return p.chromium.launch_persistent_context(
                    channel=ch,
                    **kwargs,
                )
            else:
                return p.chromium.launch_persistent_context(
                    **kwargs,
                )
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("Failed to launch chromium persistent context")

    # Sync storage_state cookies into context if available
    if STORAGE_STATE_PATH.exists():
        try:
            state_data = json.loads(STORAGE_STATE_PATH.read_text(encoding="utf-8"))
            cookies = state_data.get("cookies", [])
            if cookies:
                context.add_cookies(cookies)
        except Exception:
            pass

    return context


def _launch(p, headless: bool):
    return _launch_persistent(p, headless=headless)


def _new_context(browser):
    return browser


def _new_page(context) -> Page:
    """Get or create a page on the persistent context with full stealth instrumentation."""
    if hasattr(context, "pages") and context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()

    stealth_js = """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        window.navigator.chrome = {
            runtime: {},
        };
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """
    try:
        cdp = context.new_cdp_session(page)
        cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})
    except Exception:
        try:
            page.add_init_script(stealth_js)
        except Exception:
            pass
    return page


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


def scrape_serp_http(url: str, cfg: dict) -> list[dict] | None:
    """Scrapes SERP using fast HTTP request and parses SEEK_REDUX_DATA.
    Returns None if HTTP / parsing fails, signalling fallback to Playwright."""
    try:
        html_text = fetch_http_page(url)
    except Exception:
        return None

    _check_bot_wall_html(html_text, url)
    redux = extract_seek_redux_data(html_text)
    if not redux:
        return None

    jobs_data = redux.get("results", {}).get("results", {}).get("jobs", [])
    if not isinstance(jobs_data, list):
        return None

    jobs: list[dict] = []
    seen: set[str] = set()

    for item in jobs_data:
        jid = str(item.get("id") or "")
        if not jid or jid in seen:
            continue
        seen.add(jid)

        title = item.get("title")
        if isinstance(title, dict):
            title = title.get("text") or title.get("label") or str(title)

        adv = item.get("advertiser") or {}
        company = adv.get("description") if isinstance(adv, dict) else None
        if not company:
            company = item.get("companyName")
        if isinstance(company, dict):
            company = company.get("text") or company.get("label") or str(company)

        loc_list = item.get("locations") or []
        location = loc_list[0].get("label") if loc_list and isinstance(loc_list[0], dict) else None
        if not location and isinstance(item.get("location"), dict):
            location = item.get("location", {}).get("label")
        elif not location and isinstance(item.get("location"), str):
            location = item.get("location")

        salary = item.get("salary") or item.get("salaryLabel")
        if isinstance(salary, dict):
            salary = salary.get("label") or salary.get("text") or str(salary)

        teaser = item.get("teaser")
        if isinstance(teaser, dict):
            teaser = teaser.get("text") or teaser.get("label") or str(teaser)

        jobs.append({
            "jobstreet_id": jid,
            "url": f"{cfg['search']['base']}/id/job/{jid}",
            "title": title,
            "teaser": teaser,
            "company": company,
            "location": location,
            "salary_text": salary,
        })
    return jobs


def scrape_detail_http(job: dict, cfg: dict) -> dict | None:
    """Scrapes job detail via fast HTTP request and parses SEEK_REDUX_DATA.
    Returns None if HTTP / parsing fails, signalling fallback to Playwright."""
    try:
        html_text = fetch_http_page(job["url"])
    except Exception:
        return None

    _check_bot_wall_html(html_text, job["url"])
    redux = extract_seek_redux_data(html_text)
    if not redux:
        return None

    job_data = redux.get("jobdetails", {}).get("result", {}).get("job")
    if not isinstance(job_data, dict):
        return None

    if job_data.get("isExpired"):
        # Explicitly marked expired on JobStreet
        return None

    out = dict(job)
    title = job_data.get("title") or job.get("title")
    if isinstance(title, dict):
        title = title.get("text") or title.get("label") or str(title)
    out["title"] = title

    adv = job_data.get("advertiser") or {}
    adv_name = adv.get("name") or adv.get("description") if isinstance(adv, dict) else None
    company = adv_name or job.get("company")
    if isinstance(company, dict):
        company = company.get("text") or company.get("label") or str(company)
    out["company"] = company

    loc = job_data.get("location") or {}
    location = loc.get("label") if isinstance(loc, dict) else None
    if not location:
        location = job.get("location")
    if isinstance(location, dict):
        location = location.get("text") or location.get("label") or str(location)
    out["location"] = location

    salary = job_data.get("salary") or job.get("salary_text")
    if isinstance(salary, dict):
        salary = salary.get("label") or salary.get("text") or str(salary)
    out["salary_text"] = salary

    content_html = job_data.get("content") or ""
    out["description"] = html_to_markdown(content_html) if content_html else None

    extras = []
    classifications = job_data.get("classifications") or []
    if isinstance(classifications, list):
        for c in classifications:
            if isinstance(c, dict) and c.get("label"):
                extras.append(c["label"])
    work_types = job_data.get("workTypes")
    if isinstance(work_types, dict) and work_types.get("label"):
        extras.append(work_types["label"])
    elif isinstance(work_types, list):
        for w in work_types:
            if isinstance(w, dict) and w.get("label"):
                extras.append(w["label"])
    if job_data.get("abstract"):
        extras.append(job_data["abstract"])

    out["teaser"] = "\n".join(x for x in extras if x) or job.get("teaser")
    return out


def scrape_serp(page: Page, url: str, cfg: dict) -> list[dict]:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    _check_bot_wall(page)
    try:
        page.wait_for_selector(S.SERP_CARD, timeout=15_000)
    except Exception:
        # Check again if blocked by challenge
        _check_bot_wall(page)
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
    _check_bot_wall(page)
    try:
        page.wait_for_selector(S.DETAIL_DESCRIPTION, timeout=15_000)
    except Exception as e:
        _check_bot_wall(page)
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
             fetch_details: bool = True, use_playwright: bool = False) -> DiscoverStats:
    """Discovers jobs via fast HTTP extraction with Playwright fallback."""
    stats = DiscoverStats()
    urls = build_search_urls(cfg, roles, locations)
    seen_ids: set[str] = set()

    # If use_playwright is forced, bypass HTTP
    if use_playwright:
        return _discover_playwright(
            cfg, conn, urls=urls, pages=pages, headless=headless,
            fetch_details=fetch_details, seen_ids=seen_ids, stats=stats
        )

    pw_browser = None
    pw_page = None
    playwright_ctx = None

    total_queries = len(urls) * pages
    query_count = 0
    print(f"Discovering jobs across {len(urls)} target searches ({pages} page(s) each, ~{total_queries} queries total)...")

    try:
        for u_idx, url in enumerate(urls, 1):
            for page_no in range(1, pages + 1):
                query_count += 1
                page_url = url if page_no == 1 else f"{url}?page={page_no}"
                short_path = page_url.replace(cfg.get("search", {}).get("base", ""), "")
                print(f"[{query_count}/{total_queries}] Fetching {short_path} ...", flush=True)

                cards = None
                try:
                    cards = scrape_serp_http(page_url, cfg)
                except BotWallError:
                    raise
                except Exception as e:
                    stats.errors.append(f"HTTP SERP {page_url}: {e}")

                # Fallback to Playwright if HTTP SERP didn't return cards
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

                stats.urls_visited += 1
                if not cards:
                    print(f"  -> 0 jobs found on this page")
                    break
                stats.cards_seen += len(cards)
                new_on_page = 0

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
                        detail_job = None
                        try:
                            detail_job = scrape_detail_http(card, cfg)
                        except BotWallError:
                            raise
                        except Exception as e:
                            stats.errors.append(f"HTTP detail {jid}: {e}")

                        # Fallback to Playwright for detail page if HTTP failed
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

                    upsert_job(conn, job)
                    stats.new_jobs += 1
                    new_on_page += 1
                print(f"  -> {len(cards)} cards seen, {new_on_page} new/updated matching roles", flush=True)
    finally:
        if pw_browser:
            pw_browser.close()
        if playwright_ctx:
            playwright_ctx.stop()

    return stats


def _discover_playwright(cfg: dict, conn, *, urls: list[str], pages: int, headless: bool,
                        fetch_details: bool, seen_ids: set[str], stats: DiscoverStats) -> DiscoverStats:
    with sync_playwright() as p:
        browser = _launch(p, headless=headless)
        page = _new_page(_new_context(browser))
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

