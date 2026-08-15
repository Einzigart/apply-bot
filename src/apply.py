"""Stage 5: scripted application submission. Zero LLM tokens.

SAFETY MODEL
- Dry-run by default: fills what it knows, stops before the submit button.
- Never guesses: unknown question / unexpected screen -> screenshot to logs/,
  mark the job as errored, move on.
- Submission is recorded only after the configured success text is visible.

NOTE (Phase 4): the internals of Jobstreet's multi-step apply form (CV picker,
'Tulis surat lamaran' toggle, question widgets) must be calibrated against a
live form before --execute is trusted. The structure below is written so that
calibration only touches selectors and small helpers, not the flow.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import Page

from . import selectors as S
from .config import LOGS_DIR, ROOT
from .db import (
    approved_unapplied,
    company_in_cooldown,
    insert_application,
    norm_company,
)
from .letter import render, render_llm


class ApplyFailed(RuntimeError):
    pass


def _screenshot(page: Page, tag: str) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    path = LOGS_DIR / f"{date.today().isoformat()}-{tag}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        pass
    return path


def answer_for(question_label: str, answers: list[dict]) -> str | None:
    for entry in answers or []:
        if re.search(entry["match"], question_label or "", re.I):
            return str(entry["answer"])
    return None


def salary_for(job: dict, cfg: dict) -> int:
    """README salary rules: prefer 7M; 6M when the advertised max is 6M."""
    advertised = job.get("salary_text") or ""
    sal_cfg = cfg["salary"]
    nums = [int(n.replace(",", "")) for n in re.findall(r"([\d,]{7,})", advertised)]
    if nums and max(nums) <= sal_cfg["min_acceptable"]:
        return sal_cfg["min_acceptable"]
    return sal_cfg["preferred"]


def _click_apply(page: Page) -> None:
    btn = page.query_selector(f"{S.DETAIL_APPLY} button, {S.DETAIL_APPLY} a")
    if not btn:
        btn = page.query_selector(S.DETAIL_APPLY)
    if not btn:
        raise ApplyFailed("apply button not found (selector drift?)")
    btn.click()


def _check_external_ats(page: Page, cfg: dict) -> None:
    if cfg["apply"]["skip_external_ats"] and "jobstreet.com" not in page.url:
        raise ApplyFailed(f"external ATS redirect: {page.url}")


def _fill_known_fields(page: Page, answers: list[dict], salary: int,
                       interactive: bool) -> list[str]:
    """Best-effort fill of visible text/select/textarea fields by label match.
    Returns labels of questions that had no saved answer.

    TODO(phase-4): calibrate against the live form — label resolution and the
    CV/cover-letter steps need real selectors from a dry run.
    """
    unknown: list[str] = []
    fields = page.query_selector_all(
        "input[type=text], input[type=number], textarea, select"
    )
    for el in fields:
        try:
            if not el.is_visible():
                continue
            label = el.evaluate(
                """(e) => e.getAttribute('aria-label')
                    || (e.labels && e.labels[0] ? e.labels[0].innerText : '')
                    || (e.closest('label') ? e.closest('label').innerText : '')
                    || e.getAttribute('placeholder') || ''"""
            ).strip()
        except Exception:
            continue
        if not label:
            continue
        answer = answer_for(label, answers)
        if answer is None and re.search(r"salary|gaji|penghasilan", label, re.I):
            answer = str(salary)
        if answer is None:
            if interactive:
                answer = input(f"  ? {label}: ").strip() or None
            if answer is None:
                unknown.append(label)
                continue
        try:
            tag = el.evaluate("(e) => e.tagName.toLowerCase()")
            if tag == "select":
                el.select_option(label=re.compile(re.escape(answer), re.I))
            else:
                el.fill(answer)
        except Exception:
            unknown.append(f"{label} (fill failed)")
    return unknown


def apply_to_job(page: Page, job: dict, cfg: dict, answers: list[dict], *,
                 execute: bool = False, use_llm_letter: bool = False,
                 interactive: bool = True) -> dict:
    """Returns a result dict; raises ApplyFailed on anything unexpected."""
    salary = salary_for(job, cfg)
    letter = (render_llm(job["title"], job["company"], job.get("description") or "", cfg)
              if use_llm_letter else render(job["title"], job["company"]))

    page.goto(job["url"], wait_until="domcontentloaded", timeout=45_000)
    _click_apply(page)
    page.wait_for_load_state("domcontentloaded")
    _check_external_ats(page, cfg)

    unknown = _fill_known_fields(page, answers, salary, interactive)
    if unknown:
        raise ApplyFailed(f"unknown questions: {unknown}")

    if not execute:
        shot = _screenshot(page, f"dryrun-{job['jobstreet_id']}")
        return {"status": "dry-run", "salary": salary, "letter": letter,
                "screenshot": str(shot)}

    submit = page.get_by_role("button", name=re.compile(
        re.escape(cfg["apply"]["submit_button_text"]), re.I))
    if not submit.count():
        raise ApplyFailed("submit button not found — refusing to guess")
    submit.first.click()

    try:
        page.get_by_text(re.escape(cfg["apply"]["success_text"])).wait_for(timeout=20_000)
    except Exception as e:
        _screenshot(page, f"fail-{job['jobstreet_id']}")
        raise ApplyFailed("success text not seen after submit") from e

    return {"status": "submitted", "salary": salary, "letter": letter,
            "confirmation": cfg["apply"]["success_text"]}


def run_apply(cfg: dict, conn, answers: list[dict], *, execute: bool,
              use_llm_letter: bool, limit: int | None, headless: bool) -> dict:
    from playwright.sync_api import sync_playwright

    jobs = approved_unapplied(conn)
    if limit:
        jobs = jobs[:limit]
    results = {"submitted": 0, "dry-run": 0, "failed": 0, "skipped": 0}

    if not jobs:
        return results

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = p.chromium.launch(headless=headless)
        # TODO(phase-4): load data/storage_state.json here for the logged-in session
        page = browser.new_context(locale="id-ID").new_page()
        try:
            for job in jobs:
                job = dict(job)
                if company_in_cooldown(conn, norm_company(job.get("company")),
                                       cfg["filters"]["company_cooldown_days"]):
                    results["skipped"] += 1
                    continue
                try:
                    res = apply_to_job(page, job, cfg, answers, execute=execute,
                                       use_llm_letter=use_llm_letter,
                                       interactive=not headless)
                except ApplyFailed as e:
                    _screenshot(page, f"error-{job['jobstreet_id']}")
                    results["failed"] += 1
                    print(f"  FAILED {job.get('title')} @ {job.get('company')}: {e}")
                    continue

                if res["status"] == "submitted":
                    insert_application(conn, job["id"], {
                        "applied_at": datetime.now().date().isoformat(),
                        "salary_entered": f"IDR {res['salary']:,}/month",
                        "cover_letter": res["letter"],
                        "confirmation": res["confirmation"],
                    })
                    results["submitted"] += 1
                    print(f"  SUBMITTED {job.get('title')} @ {job.get('company')}")
                else:
                    results["dry-run"] += 1
                    print(f"  DRY-RUN  {job.get('title')} @ {job.get('company')} "
                          f"(screenshot: {res['screenshot']})")
        finally:
            browser.close()
    return results
