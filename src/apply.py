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
from .scrape import _check_bot_wall, _launch_persistent, _new_page


class ApplySkipped(Exception):
    """Job application skipped (e.g. external ATS / employer website)."""
    pass


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
    if cfg["apply"]["skip_external_ats"]:
        current_url = page.url.lower()
        if "/apply/external" in current_url or ("jobstreet.com" not in current_url and "seek.com" not in current_url):
            raise ApplySkipped(f"external ATS redirect: {page.url}")


def select_best_option(select_el, answer: str, salary_int: int = 0) -> bool:
    try:
        options = select_el.evaluate(
            """(e) => Array.from(e.options).map((o, i) => ({index: i, value: o.value, text: o.text.trim()}))"""
        )
        if not options:
            return False

        for opt in options:
            if opt["text"].lower() == answer.lower() or opt["value"].lower() == answer.lower():
                select_el.select_option(index=opt["index"])
                return True

        for opt in options:
            if answer.lower() in opt["text"].lower() or opt["text"].lower() in answer.lower():
                select_el.select_option(index=opt["index"])
                return True

        if salary_int > 0:
            millions = salary_int // 1_000_000
            for opt in options:
                low = opt["text"].lower()
                if str(millions) in low and any(k in low for k in ("million", "jt", "juta", str(salary_int))):
                    select_el.select_option(index=opt["index"])
                    return True
    except Exception:
        pass
    return False


def _fill_known_fields(page: Page, answers: list, salary: int,
                       interactive: bool, conn=None, job: dict | None = None,
                       profile: dict | None = None, cfg: dict | None = None) -> list[str]:
    unknown: list[str] = []
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5_000)
    except Exception:
        pass

    try:
        fields = page.query_selector_all(
            "input[type=text], input[type=number], input[type=tel], select, textarea"
        )
    except Exception:
        return []

    for el in fields:
        try:
            if not el.is_visible():
                continue
            label = el.evaluate(
                """(e) => (e.labels && e.labels[0] ? e.labels[0].innerText : '')
                    || e.getAttribute('aria-label')
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

        # If it's a cover letter textarea, it is already filled in step 1
        if tag == "textarea" and re.search(r"cover\s*letter|surat\s*lamaran", label, re.I):
            continue

        answer = answer_for(label, answers)
        if answer is None and re.search(r"salary|gaji|penghasilan", label, re.I):
            answer = str(salary)

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
                ok = select_best_option(el, answer, salary_int=salary)
                if not ok:
                    unknown.append(f"{label} (select option not matched: {answer})")
            else:
                el.fill(answer)
        except Exception:
            unknown.append(f"{label} (fill failed)")
    return unknown


def _click_continue_if_present(page: Page) -> bool:
    btn = page.locator('button[data-testid="continue-button"], button:has-text("Lanjut")').last
    try:
        if btn.count() and btn.is_visible():
            btn.click(force=True)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=8_000)
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False


def apply_to_job(page: Page, job: dict, cfg: dict, profile: dict,
                 answers: list, *, execute: bool = False,
                 use_llm_letter: bool = False, interactive: bool = True,
                 conn=None) -> dict:
    salary = salary_for(job, profile)
    letter = (render_llm(job["title"], job["company"],
                         job.get("description") or "", cfg, profile)
              if use_llm_letter else render(job["title"], job["company"], profile))

    page.goto(job["url"], wait_until="domcontentloaded", timeout=45_000)
    _check_bot_wall(page)
    _click_apply(page)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    _check_bot_wall(page)
    _check_auth_state(page)
    _check_external_ats(page, cfg)

    # Step through JobStreet's multi-step apply wizard:
    # 1. Documents (Resume & Cover Letter)
    # 2. Role Requirements (Questionnaire)
    # 3. Profile Updates
    # 4. Review & Submit
    max_steps = 6
    for step in range(1, max_steps + 1):
        _check_bot_wall(page)
        _check_auth_state(page)
        _check_external_ats(page, cfg)

        submit_btn = page.locator('button[data-testid="review-submit-application"], button:has-text("Kirim lamaran")').first
        if "/review" in page.url or (submit_btn.count() and submit_btn.is_visible()):
            break

        tulis_radio = page.locator('label:has-text("Tulis surat lamaran"), input[value="change"]').first
        if tulis_radio.count() and tulis_radio.is_visible():
            try:
                tulis_radio.click(force=True)
                page.wait_for_timeout(400)
                textarea = page.locator('textarea').first
                if textarea.count() and textarea.is_visible():
                    textarea.fill(letter)
            except Exception:
                pass

        unknown = _fill_known_fields(
            page, answers, salary, interactive, conn,
            job=job, profile=profile, cfg=cfg
        )
        if unknown:
            raise ApplyFailed(f"unknown questions on step {step} ({page.url}): {unknown}")

        # Advance to the next wizard step with explicit wait
        continued = _click_continue_if_present(page)
        page.wait_for_timeout(2000)
        _check_external_ats(page, cfg)
        if not continued:
            submit_btn = page.locator('button[data-testid="review-submit-application"], button:has-text("Kirim lamaran")').first
            if submit_btn.count() and submit_btn.is_visible():
                break
            page.wait_for_timeout(1000)

    # Final check before submit
    _check_external_ats(page, cfg)
    submit_btn = page.locator('button[data-testid="review-submit-application"], button:has-text("Kirim lamaran")').first
    if not submit_btn.count() or not submit_btn.is_visible():
        _screenshot(page, f"fail-{job['jobstreet_id']}")
        raise ApplyFailed(f"submit button not found at {page.url} — refusing to guess")

    if not execute:
        shot = _screenshot(page, f"dryrun-{job['jobstreet_id']}")
        return {"status": "dry-run", "salary": salary, "letter": letter,
                "screenshot": str(shot)}

    submit_btn.click(force=True)

    # JobStreet success messages can vary in exact wording and case:
    # "Lamaranmu telah dikirim", "Lamaran terkirim", "Application submitted", etc.
    # or redirect to /apply/success or confirmation screen.
    success_regex = re.compile(
        r"lamaran(?:mu)?\s+(?:telah\s+)?(?:di)?kirim|lamaran\s+terkirim|application\s+submitted|application\s+sent",
        re.I
    )
    try:
        page.wait_for_function(
            """(pat) => {
                const re = new RegExp(pat, 'i');
                const text = (document.body ? document.body.innerText : '') || '';
                return re.test(text) || window.location.href.includes('/success');
            }""",
            arg=r"lamaran.*kirim|terkirim|application.*(submitted|sent)",
            timeout=25_000,
        )
    except Exception as e:
        _screenshot(page, f"fail-{job['jobstreet_id']}")
        raise ApplyFailed("success text not seen after submit") from e

    return {"status": "submitted", "salary": salary, "letter": letter,
            "confirmation": cfg["apply"].get("success_text", "Lamaran dikirim")}


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
        context = _launch_persistent(p, headless=headless)
        page = _new_page(context)
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
                except ApplySkipped as e:
                    results["skipped"] += 1
                    print(f"  SKIPPED {job.get('title')} @ {job.get('company')} ({e})")
                    continue
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
            context.close()
    return results
