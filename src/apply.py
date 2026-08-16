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
from .config import LOGS_DIR, ROOT, STORAGE_STATE_PATH
from .db import (
    add_answer,
    approved_unapplied,
    company_in_cooldown,
    insert_application,
    list_answers,
    norm_company,
)
from .letter import render, render_llm
from .llm import complete


class ApplyFailed(RuntimeError):
    pass


def answer_with_llm(
    question_label: str,
    field_type: str,
    options: list[str],
    job: dict,
    profile: dict,
    cfg: dict,
) -> str | None:
    """Use the configured LLM to answer application questions based on user's profile and job info."""
    import yaml

    profile_text = yaml.safe_dump(profile, sort_keys=False)
    options_prompt = ""
    if options:
        options_prompt = f"Available options:\n" + "\n".join(f"- {opt}" for opt in options) + "\nChoose EXACTLY ONE option from the list."

    prompt = f"""You are filling out a job application form on behalf of the candidate.
Answer the following employer question concisely and accurately based on the candidate profile and job details.

CANDIDATE PROFILE:
{profile_text}

JOB DETAILS:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}

QUESTION:
{question_label}

FIELD TYPE: {field_type}
{options_prompt}

INSTRUCTIONS:
- If available options are provided, reply with ONLY the exact text of the best matching option.
- If it is a number or years of experience, output ONLY the number (e.g. 1 or 0 or immediate).
- If it is a yes/no question, reply 'Yes' or 'No' (or 'Ya'/'Tidak' if Indonesian options).
- Keep your answer as brief as possible, ideally 1-5 words or the exact matching choice.
- Do NOT include quotes, explanations, markdown, or commentary. Output the raw answer only.
"""
    try:
        ans = complete(
            [{"role": "user", "content": prompt}],
            cfg,
            max_tokens=60,
            temperature=0.0,
        )
        cleaned = ans.strip().strip('"').strip("'")
        if options and cleaned:
            # Match against options case-insensitively
            for opt in options:
                if opt.strip().lower() == cleaned.lower():
                    return opt.strip()
            for opt in options:
                if cleaned.lower() in opt.strip().lower():
                    return opt.strip()
        return cleaned or None
    except Exception as e:
        print(f"  [LLM Answer Error]: {e}")
        return None


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


def salary_for(job: dict, profile: dict) -> int:
    """README salary rules: prefer 7M; 6M when the advertised max is 6M."""
    advertised = job.get("salary_text") or ""
    sal = profile["salary"]
    nums = [int(n.replace(",", "")) for n in re.findall(r"([\d,]{7,})", advertised)]
    if nums and max(nums) <= sal["min_acceptable"]:
        return sal["min_acceptable"]
    return sal["preferred"]


def _click_apply(page: Page) -> None:
    btn = page.query_selector(f"{S.DETAIL_APPLY} button, {S.DETAIL_APPLY} a")
    if not btn:
        btn = page.query_selector(S.DETAIL_APPLY)
    if not btn:
        raise ApplyFailed("apply button not found (selector drift?)")
    btn.click()


def _check_auth_state(page: Page) -> None:
    """Checks if the user was logged out or redirected to auth login page."""
    current_url = page.url.lower()
    if "login.seek.com" in current_url or "/oauth/login" in current_url or "/login" in current_url:
        raise ApplyFailed("JobStreet session expired or logged out (redirected to login.seek.com)")
    
    # Check page content for login prompt markers
    try:
        body_text = page.locator("body").inner_text()[:1000].lower()
        if any(marker in body_text for marker in S.LOGIN_MARKERS):
            raise ApplyFailed("JobStreet session expired or logged out (login marker detected)")
    except Exception:
        pass


def _check_external_ats(page: Page, cfg: dict) -> None:
    if cfg["apply"]["skip_external_ats"] and "jobstreet.com" not in page.url and "seek.com" not in page.url:
        raise ApplyFailed(f"external ATS redirect: {page.url}")


def _fill_known_fields(page: Page, answers: list, salary: int,
                       interactive: bool, conn=None, job: dict | None = None,
                       profile: dict | None = None, cfg: dict | None = None) -> list[str]:
    """Best-effort fill of visible text/select/textarea fields by label match.
    If no pre-saved answer exists:
    1. If LLM config is available, LLM automatically picks/infers the answer from profile & job details.
    2. In interactive mode, prompts the user if LLM fails or is unavailable.
    3. Saves chosen answers to the answers table and in-memory cache.
    """
    unknown: list[str] = []
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass

    try:
        fields = page.query_selector_all(
            "input[type=text], input[type=number], textarea, select"
        )
    except Exception:
        # Retry once if navigation occurred right as selectors were queried
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
            fields = page.query_selector_all(
                "input[type=text], input[type=number], textarea, select"
            )
        except Exception:
            return []

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

        tag = "input"
        try:
            tag = el.evaluate("(e) => e.tagName.toLowerCase()")
        except Exception:
            pass

        answer = answer_for(label, answers)
        if answer is None and re.search(r"salary|gaji|penghasilan", label, re.I):
            answer = str(salary)

        # If not found in saved answers, ask LLM to select or answer
        if answer is None and profile and cfg:
            options: list[str] = []
            if tag == "select":
                try:
                    options = el.evaluate(
                        """(s) => Array.from(s.options).map(o => o.text.trim()).filter(t => t && !t.toLowerCase().includes('pilih') && !t.toLowerCase().includes('select'))"""
                    ) or []
                except Exception:
                    options = []

            print(f"  [Auto-Answering Question via LLM]: '{label}' (type={tag}) ...", flush=True)
            llm_ans = answer_with_llm(label, tag, options, job or {}, profile, cfg)
            if llm_ans:
                answer = llm_ans
                print(f"  -> LLM Answered: '{answer}'", flush=True)
                if conn is not None:
                    add_answer(conn, re.escape(label), answer)
                answers.append({"match": re.escape(label), "answer": answer})

        if answer is None:
            if interactive:
                answer = input(f"  ? {label}: ").strip() or None
            if answer is None:
                unknown.append(label)
                continue
            if conn is not None:
                add_answer(conn, re.escape(label), answer)
            answers.append({"match": re.escape(label), "answer": answer})

        try:
            if tag == "select":
                el.select_option(label=re.compile(re.escape(answer), re.I))
            else:
                el.fill(answer)
        except Exception:
            unknown.append(f"{label} (fill failed)")
    return unknown


def apply_to_job(page: Page, job: dict, cfg: dict, profile: dict,
                 answers: list, *, execute: bool = False,
                 use_llm_letter: bool = False, interactive: bool = True,
                 conn=None) -> dict:
    """Returns a result dict; raises ApplyFailed on anything unexpected."""
    salary = salary_for(job, profile)
    letter = (render_llm(job["title"], job["company"],
                         job.get("description") or "", cfg, profile)
              if use_llm_letter else render(job["title"], job["company"], profile))

    page.goto(job["url"], wait_until="domcontentloaded", timeout=45_000)
    _click_apply(page)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    _check_auth_state(page)
    _check_external_ats(page, cfg)

    unknown = _fill_known_fields(
        page, answers, salary, interactive, conn,
        job=job, profile=profile, cfg=cfg
    )
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


def run_apply(cfg: dict, conn, profile: dict, *, execute: bool,
              use_llm_letter: bool, limit: int | None, headless: bool,
              jobs: list[dict] | None = None) -> dict:
    from playwright.sync_api import sync_playwright

    if jobs is None:
        jobs = approved_unapplied(conn)
    if limit:
        jobs = jobs[:limit]
    # Rows from the DB plus dicts appended for interactively-typed answers.
    answers = list(list_answers(conn))
    results = {"submitted": 0, "dry-run": 0, "failed": 0, "skipped": 0}

    if not jobs:
        return results

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = p.chromium.launch(headless=headless)

        context_kwargs = {"locale": "id-ID"}
        if STORAGE_STATE_PATH.exists():
            context_kwargs["storage_state"] = str(STORAGE_STATE_PATH)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        try:
            for job in jobs:
                job = dict(job)
                if company_in_cooldown(conn, norm_company(job.get("company")),
                                       cfg["filters"]["company_cooldown_days"]):
                    results["skipped"] += 1
                    continue
                try:
                    res = apply_to_job(page, job, cfg, profile, answers,
                                       execute=execute,
                                       use_llm_letter=use_llm_letter,
                                       interactive=not headless, conn=conn)
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
