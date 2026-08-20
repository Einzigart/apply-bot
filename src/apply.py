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

import sys

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
from .letter import render_llm
from .llm import complete
from .scrape import _check_bot_wall, _launch_persistent, _new_page


class ApplySkipped(Exception):
    """Job application skipped (e.g. external ATS / employer website)."""
    pass


class ApplyFailed(RuntimeError):
    pass


def batch_answer_questions_with_llm(
    questions: list[dict],
    job: dict,
    profile: dict,
    cfg: dict,
) -> dict[str, str]:
    """Batch answers all pending questionnaire fields in a single LLM request.
    Provides holistic context to the LLM, strictly follows user profile, and eliminates round-trip latency.
    """
    if not questions:
        return {}

    import json
    import re
    import yaml

    profile_text = yaml.safe_dump(profile, sort_keys=False)

    q_list_formatted = []
    for idx, q in enumerate(questions, 1):
        q_key = q.get("key") or f"q{idx}"
        opts = f" (Available options: {', '.join(q['options'])})" if q.get("options") else ""
        q_list_formatted.append(f"{idx}. [{q_key}] \"{q['label']}\" [Type: {q.get('type', 'text')}]{opts}")

    prompt = f"""You are filling out a job application questionnaire on behalf of the candidate.
Answer all of the following employer questions accurately and truthfully based strictly on the candidate's profile and background.

CANDIDATE PROFILE:
{profile_text}

JOB DETAILS:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}

QUESTIONS TO ANSWER:
{chr(10).join(q_list_formatted)}

    RULES:
1. Accuracy: Base answers truthfully on candidate profile. Do not invent experience or certifications the candidate does not have.
2. For multiple-choice/checkbox questions: If multiple options match candidate skills, join them with commas (e.g. "Ubuntu, Debian"). If none match candidate profile, choose "None of these" or "Tidak ada" (or "Tidak satupun").
3. For dropdown/select/radio questions: Return the EXACT matching option text from the provided options list whenever options are available.
4. For number or years of experience questions:
   - If candidate has no experience in the requested skill/industry:
     * When options are provided (English): choose "Less than 1 year", "0 years", or "No experience" (whichever is in the available options).
     * When options are provided (Indonesian): choose "Kurang dari 1 tahun", "0 tahun", or "Tidak ada pengalaman" (whichever is in the available options).
     * When no options are provided: return "0".
   - If candidate has experience, return only the number of years or the exact matching option text.
5. Output format: Return a valid JSON object mapping each question key (e.g. "q1", "group_0", "field_0") to its answer string.
Example JSON output:
{{
  "{questions[0].get('key', 'q1')}": "..."
}}
"""
    try:
        ans = complete(
            [{"role": "user", "content": prompt}],
            cfg,
            max_tokens=1000,
            temperature=0.0,
        )
        clean_json = ans.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        parsed = None
        try:
            parsed = json.loads(clean_json)
        except Exception:
            # Try to extract JSON object via regex if there's surrounding text
            m = re.search(r"(\{.*\})", clean_json, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(1))
                except Exception:
                    pass

        # Fallback if LLM replied with raw text for single question
        if not isinstance(parsed, dict) and len(questions) == 1:
            key = questions[0]["key"]
            val = clean_json.strip('"').strip("'")
            opts = questions[0].get("options", [])
            if opts and val:
                matched_opt = None
                for opt in opts:
                    if opt.strip().lower() == val.lower() or val.lower() in opt.strip().lower():
                        matched_opt = opt.strip()
                        break
                if not matched_opt and val.lower() in ("0", "0 year", "0 years", "0 tahun", "none", "no experience", "tidak ada", "tidak ada pengalaman", "n/a", "not applicable", "zero"):
                    for opt in opts:
                        low = opt.strip().lower()
                        if any(k in low for k in ("less than 1", "kurang dari 1", "no experience", "tidak ada", "0 year", "0 tahun", "none")):
                            matched_opt = opt.strip()
                            break
                if matched_opt:
                    val = matched_opt
            return {key: val}

        if isinstance(parsed, dict):
            res_dict = {}
            for idx, q in enumerate(questions, 1):
                key = q["key"]
                val = parsed.get(key)
                # Fallback to q1, q2 style keys or index if key not directly found
                if val is None:
                    val = parsed.get(f"q{idx}")
                if val is None:
                    val = parsed.get(str(idx))
                if val is None:
                    val = parsed.get(q["label"])

                if val is True:
                    val = "Yes"
                elif val is False:
                    val = "No"
                elif val is not None:
                    val = str(val).strip()
                else:
                    val = ""

                opts = q.get("options", [])
                if opts and val:
                    matched_opt = None
                    for opt in opts:
                        if opt.strip().lower() == val.lower():
                            matched_opt = opt.strip()
                            break
                        elif val.lower() in opt.strip().lower() and len(val) >= 2:
                            matched_opt = opt.strip()
                            break

                    # Zero/no-experience fallback normalization (English & Indonesian)
                    if not matched_opt and val.lower() in ("0", "0 year", "0 years", "0 tahun", "none", "no experience", "tidak ada", "tidak ada pengalaman", "n/a", "not applicable", "zero"):
                        for opt in opts:
                            low = opt.strip().lower()
                            if any(k in low for k in ("less than 1", "kurang dari 1", "no experience", "tidak ada", "0 year", "0 tahun", "none")):
                                matched_opt = opt.strip()
                                break

                    if matched_opt:
                        val = matched_opt
                res_dict[key] = val
            return res_dict
    except Exception as e:
        print(f"  [Batch LLM Questionnaire Error]: {e}", flush=True)
    return {}


def answer_with_llm(
    question_label: str,
    field_type: str,
    options: list[str],
    job: dict,
    profile: dict,
    cfg: dict,
) -> str | None:
    """Single question fallback wrapper using batch answering logic."""
    res = batch_answer_questions_with_llm(
        [{"key": "q", "label": question_label, "type": field_type, "options": options}],
        job,
        profile,
        cfg,
    )
    return res.get("q")


def _screenshot(page: Page, tag: str) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    path = LOGS_DIR / f"{date.today().isoformat()}-{tag}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        pass
    return path


def answer_for(question_label: str, answers: list) -> str | None:
    for entry in answers or []:
        if isinstance(entry, (list, tuple)):
            match_pat = entry[1] if len(entry) > 1 else ""
            ans_val = entry[2] if len(entry) > 2 else ""
        elif isinstance(entry, dict):
            match_pat = entry.get("match", "")
            ans_val = entry.get("answer", "")
        else:
            try:
                match_pat = entry["match"]
                ans_val = entry["answer"]
            except Exception:
                continue

        if match_pat and re.search(match_pat, question_label or "", re.I):
            return str(ans_val)
    return None


def salary_for(job: dict, profile: dict) -> int:
    """README salary rules: prefer 7M; 6M when the advertised max is 6M."""
    advertised = job.get("salary_text") or ""
    sal = profile["salary"]
    raw_nums = re.findall(r"\d{1,3}(?:[.,]\d{3})+", advertised)
    nums = [int(re.sub(r"[.,]", "", n)) for n in raw_nums]
    if nums and max(nums) <= sal["min_acceptable"]:
        return sal["min_acceptable"]
    return sal["preferred"]


def _click_apply(page: Page) -> None:
    # Check if job was already applied to
    try:
        if (page.locator('text="Kamu sudah melamar lowongan ini"').count()
                or page.locator('text="You applied for this job"').count()):
            raise ApplySkipped("already applied previously")
    except ApplySkipped:
        raise
    except Exception:
        pass

    # Check for external apply button
    try:
        external_btn = page.locator('a[href*="/apply/external"]').first
        if external_btn.count():
            raise ApplySkipped("external ATS link detected on job detail")
    except ApplySkipped:
        raise
    except Exception:
        pass

    btn = page.query_selector(f"{S.DETAIL_APPLY} button, {S.DETAIL_APPLY} a")
    if not btn:
        btn = page.query_selector(S.DETAIL_APPLY)
    if not btn:
        raise ApplyFailed("apply button not found (selector drift?)")
    
    # Check href and attributes on apply button
    try:
        href = btn.get_attribute("href") or ""
        target = btn.get_attribute("target") or ""
        btn_text = (btn.inner_text() or "").strip().lower()
        has_svg_icon = bool(btn.query_selector("svg"))

        if "/apply/external" in href:
            raise ApplySkipped(f"external ATS redirect: {href}")

        # Check for external apply patterns: target="_blank", external popout svg, or "Daftar" / "Register" button text
        if target == "_blank" or has_svg_icon or btn_text in ("daftar", "register", "apply on company site", "apply on employer site"):
            raise ApplySkipped("external ATS redirect detected on job detail button")
    except ApplySkipped:
        raise
    except Exception:
        pass

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

        # Filter out placeholder/empty options
        valid_opts = [o for o in options if o["text"] and not o["text"].lower().startswith("select") and not o["text"].lower().startswith("pilih")]
        if not valid_opts:
            valid_opts = options

        ans_clean = str(answer or "").strip()
        ans_low = ans_clean.lower()

        # 1. Exact match against text or value
        for opt in valid_opts:
            if opt["text"].lower() == ans_low or opt["value"].lower() == ans_low:
                select_el.select_option(index=opt["index"])
                return True

        # 2. Match with word boundary / full phrase containment
        for opt in valid_opts:
            opt_low = opt["text"].lower()
            if len(ans_low) >= 3 and (ans_low in opt_low or (len(opt_low) >= 3 and opt_low in ans_low)):
                select_el.select_option(index=opt["index"])
                return True

        # 3. Numeric salary matching (e.g. 7000000 -> "Rp 7 million", "7 jt", "7 juta", "7.000.000")
        if salary_int > 0:
            millions = salary_int // 1_000_000
            for opt in valid_opts:
                low = opt["text"].lower()
                if str(millions) in low and any(k in low for k in ("million", "jt", "juta", str(salary_int), f"{millions}.000")):
                    select_el.select_option(index=opt["index"])
                    return True

        # 4. Fallback for zero experience (English & Indonesian)
        zero_markers = (
            "0", "0 year", "0 years", "0 tahun", "none", "no experience",
            "tidak ada", "tidak ada pengalaman", "tidak memiliki pengalaman",
            "n/a", "not applicable", "zero", "tidak satupun", "tidak"
        )
        if ans_low in zero_markers or any(ans_low == z for z in zero_markers):
            for opt in valid_opts:
                opt_text_low = opt["text"].lower()
                if any(k in opt_text_low for k in (
                    "less than 1", "kurang dari 1", "no experience", "tidak ada",
                    "tidak memiliki", "0 year", "0 tahun", "none", "tidak satupun"
                )):
                    select_el.select_option(index=opt["index"])
                    return True

        # 5. Fallback for single numbers (e.g. "1" -> "1 year", "1 tahun")
        if ans_low.isdigit():
            for opt in valid_opts:
                opt_text_low = opt["text"].lower()
                if f"{ans_low} year" in opt_text_low or f"{ans_low} tahun" in opt_text_low:
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

    # 1. Scan and extract all form elements using client-side JS
    js_extract = """() => {
        const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
        const results = {
            groups: [],
            fields: []
        };

        function findGroupTitle(inputs, sampleInput) {
            const optionTexts = new Set(inputs.map(i => {
                let t = '';
                if (i.closest('label')) t = clean(i.closest('label').innerText);
                else if (i.parentElement) t = clean(i.parentElement.innerText);
                return t.toLowerCase();
            }).filter(Boolean));

            const fieldset = sampleInput.closest('fieldset');
            if (fieldset) {
                const legend = fieldset.querySelector('legend');
                if (legend && clean(legend.innerText).length > 2) {
                    return clean(legend.innerText).split('\\n')[0].trim();
                }
            }

            let curr = sampleInput.parentElement;
            for (let i = 0; i < 10; i++) {
                if (!curr || curr === document.body) break;

                const headings = Array.from(curr.querySelectorAll('legend, h1, h2, h3, h4, h5, strong, span.font-bold, [data-automation*="question-text"]'));
                for (const h of headings) {
                    const text = clean(h.innerText);
                    if (text.length > 3 && !optionTexts.has(text.toLowerCase())) {
                        return text.split('\\n')[0].trim();
                    }
                }

                let prev = curr.previousElementSibling;
                while (prev) {
                    const pHead = prev.querySelector('legend, h1, h2, h3, h4, h5, strong, span.font-bold, [data-automation*="question-text"]') || prev;
                    const text = clean(pHead.innerText);
                    if (text.length > 3 && text.length < 250 && !optionTexts.has(text.toLowerCase())) {
                        return text.split('\\n')[0].trim();
                    }
                    prev = prev.previousElementSibling;
                }

                curr = curr.parentElement;
            }
            return '';
        }

        function getElementLabel(el) {
            if (el.labels && el.labels[0] && clean(el.labels[0].innerText)) {
                return clean(el.labels[0].innerText);
            }
            const ariaLabelledBy = el.getAttribute('aria-labelledby');
            if (ariaLabelledBy) {
                const target = document.getElementById(ariaLabelledBy);
                if (target && clean(target.innerText)) return clean(target.innerText);
            }
            if (el.getAttribute('aria-label') && clean(el.getAttribute('aria-label'))) {
                return clean(el.getAttribute('aria-label'));
            }
            const parentLabel = el.closest('label');
            if (parentLabel && clean(parentLabel.innerText)) {
                return clean(parentLabel.innerText);
            }
            let curr = el.parentElement;
            for (let i = 0; i < 8; i++) {
                if (!curr || curr === document.body) break;
                const h = curr.querySelector('legend, h1, h2, h3, h4, h5, strong, span.font-bold, [data-automation*="question-text"]');
                if (h && clean(h.innerText).length > 2) {
                    return clean(h.innerText).split('\\n')[0].trim();
                }
                curr = curr.parentElement;
            }
            return clean(el.placeholder) || el.name || el.id || '';
        }

        // Ignore elements inside report ad modal, banners, or hidden popups
        function isIgnored(el) {
            if (el.closest('[data-automation*="report"], [aria-label*="report" i], [aria-label*="laporkan" i], #report-job, footer, header, nav')) {
                return true;
            }
            return false;
        }

        // A. Radio & Checkbox Groups
        const seenNames = new Set();
        const allRadioCheck = Array.from(document.querySelectorAll('input[type="checkbox"], input[type="radio"]'));
        for (const inp of allRadioCheck) {
            if (isIgnored(inp)) continue;
            const name = inp.name;
            if (!name || seenNames.has(name)) continue;
            seenNames.add(name);

            const groupInputs = Array.from(document.querySelectorAll(`input[name="${name}"]`));
            const title = findGroupTitle(groupInputs, inp) || name;

            const options = groupInputs.map((item, idx) => {
                let optText = '';
                const lbl = item.closest('label');
                if (lbl) optText = clean(lbl.innerText);
                else if (item.parentElement) optText = clean(item.parentElement.innerText);
                if (!optText && item.nextElementSibling) optText = clean(item.nextElementSibling.innerText);

                return {
                    index: idx,
                    id: item.id,
                    value: item.value,
                    checked: item.checked,
                    text: optText
                };
            });

            results.groups.push({
                name: name,
                type: inp.type, // "radio" or "checkbox"
                title: title,
                anyChecked: options.some(o => o.checked),
                options: options
            });
        }

        // B. Select Dropdowns
        const selects = Array.from(document.querySelectorAll('select'));
        for (const s of selects) {
            if (isIgnored(s)) continue;
            if (!s.offsetParent && s.style.display === 'none') continue;
            const label = getElementLabel(s);
            const options = Array.from(s.options).map((o, idx) => ({
                index: idx,
                value: o.value,
                text: clean(o.text),
                selected: o.selected
            })).filter(o => o.text && !o.text.toLowerCase().startsWith('select') && !o.text.toLowerCase().startsWith('pilih'));

            let selectedVal = '';
            if (s.options[s.selectedIndex]) {
                const optText = clean(s.options[s.selectedIndex].text);
                const optVal = clean(s.options[s.selectedIndex].value);
                const low = optText.toLowerCase();
                if (optVal && !low.startsWith('select') && !low.startsWith('pilih') && !low.startsWith('choose')) {
                    selectedVal = optText;
                }
            }

            results.fields.push({
                tag: 'select',
                name: s.name,
                id: s.id,
                label: label,
                selectedValue: selectedVal,
                options: options
            });
        }

        // C. Text / Number Inputs / Textareas
        const otherInputs = Array.from(document.querySelectorAll('input[type="text"], input[type="number"], input[type="tel"], input[type="email"], input[type="url"], input:not([type]), textarea'));
        for (const el of otherInputs) {
            if (isIgnored(el)) continue;
            if (!el.offsetParent && el.style.display === 'none') continue;
            const tag = el.tagName.toLowerCase();
            const label = getElementLabel(el);
            results.fields.push({
                tag: tag,
                type: el.type || 'text',
                name: el.name,
                id: el.id,
                label: label,
                value: el.value,
                options: []
            });
        }

        return results;
    }"""

    scan_data = {"groups": [], "fields": []}
    try:
        scan_data = page.evaluate(js_extract)
    except Exception:
        pass

    pending_items: list[dict] = []

    # 1. Process Checkbox / Radio Groups
    groups_map = []
    for idx, g in enumerate(scan_data.get("groups", [])):
        title = g["title"]
        g_name = g["name"]
        g_type = g["type"]
        options = g["options"]
        valid_opt_texts = [o["text"] for o in options if o["text"]]

        # Check cached answer
        cached_ans = answer_for(title, answers)

        q_key = f"group_{idx}"
        groups_map.append({
            "key": q_key,
            "name": g_name,
            "type": g_type,
            "title": title,
            "options": options,
            "valid_opt_texts": valid_opt_texts,
            "cached_answer": cached_ans,
            "any_checked": g["anyChecked"],
        })

        if cached_ans is None and not g["anyChecked"]:
            pending_items.append({
                "key": q_key,
                "label": title,
                "type": g_type,
                "options": valid_opt_texts,
            })

    # Check for personal info fields (e.g. Silakan lengkapi informasi pribadi kamu)
    # such as first name, last name, phone, residence location if required
    p_name = (profile or {}).get("name", "")
    p_phone = (profile or {}).get("phone", "")
    p_loc = (profile or {}).get("location", "")
    p_email = (profile or {}).get("email", "")

    # 2. Process Selects & Input Fields
    fields_map = []
    for idx, f in enumerate(scan_data.get("fields", [])):
        tag = f["tag"]
        label = f["label"]
        name = f["name"]
        id_attr = f["id"]
        options = f.get("options", [])
        valid_opt_texts = [o["text"] for o in options if o["text"]]

        if tag == "textarea" and re.search(r"cover\s*letter|surat\s*lamaran", label, re.I):
            continue

        cached_ans = answer_for(label, answers)
        if cached_ans is None and re.search(r"salary|gaji|penghasilan", label, re.I):
            cached_ans = str(salary)
        elif cached_ans is None and re.search(r"phone|telepon|hp|mobile|handphone|nomor\s*kontak|contact\s*number", label, re.I) and p_phone:
            cached_ans = str(p_phone)
        elif cached_ans is None and re.search(r"^(?:first\s*name|nama\s*depan|given\s*name)$", label, re.I) and p_name:
            cached_ans = p_name.split()[0] if p_name.split() else p_name
        elif cached_ans is None and re.search(r"^(?:last\s*name|nama\s*belakang|family\s*name|surname)$", label, re.I) and p_name:
            cached_ans = " ".join(p_name.split()[1:]) if len(p_name.split()) > 1 else p_name.split()[0]
        elif cached_ans is None and re.search(r"^(?:full\s*name|nama\s*lengkap|nama)$", label, re.I) and p_name:
            cached_ans = p_name
        elif cached_ans is None and re.search(r"^(?:email|surel|alamat\s*email)$", label, re.I) and p_email:
            cached_ans = p_email
        elif cached_ans is None and re.search(r"^(?:location|city|kota|alamat|domisili|residence|lokasi)$", label, re.I) and p_loc:
            cached_ans = p_loc

        q_key = f"field_{idx}"
        fields_map.append({
            "key": q_key,
            "tag": tag,
            "label": label,
            "name": name,
            "id": id_attr,
            "options": options,
            "valid_opt_texts": valid_opt_texts,
            "cached_answer": cached_ans,
            "selected_value": f.get("selectedValue", ""),
        })

        if cached_ans is None and not f.get("selectedValue"):
            pending_items.append({
                "key": q_key,
                "label": label,
                "type": tag,
                "options": valid_opt_texts,
            })

    # Log detected questions on current screen
    total_questions = len(groups_map) + len(fields_map)
    if total_questions > 0:
        print(f"    Viewing form: detected {total_questions} field(s)/question(s) ({len(pending_items)} unanswered)", flush=True)

    # 3. Batch answer pending questions with LLM
    batch_results = {}
    if pending_items and profile and cfg:
        print(f"    Generating answers for {len(pending_items)} question(s) via LLM...", flush=True)
        batch_results = batch_answer_questions_with_llm(pending_items, job or {}, profile, cfg)
        for q in pending_items:
            ans_val = batch_results.get(q["key"])
            if ans_val:
                print(f"    -> Question: \"{q['label']}\"", flush=True)
                print(f"       Answer:   \"{ans_val}\"", flush=True)
                if conn is not None:
                    add_answer(conn, re.escape(q["label"]), ans_val)
                answers.append({"match": re.escape(q["label"]), "answer": ans_val})

    # 4. Apply answers to Groups / Checkboxes / Radios
    for g_entry in groups_map:
        ans_val = g_entry["cached_answer"] or batch_results.get(g_entry["key"])
        title = g_entry["title"]
        g_name = g_entry["name"]
        g_type = g_entry["type"]
        options = g_entry["options"]

        if not ans_val and not g_entry["any_checked"]:
            if interactive:
                ans_val = input(f"    ? {title} (options: {', '.join(g_entry['valid_opt_texts'])}): ").strip() or None
            if not ans_val:
                unknown.append(title)
                continue
            if conn is not None:
                add_answer(conn, re.escape(title), ans_val)
            answers.append({"match": re.escape(title), "answer": ans_val})

        if ans_val:
            chosen_parts = [p.strip().lower() for p in ans_val.split(",") if p.strip()]
            matched = False
            selected_labels = []

            for opt_item in options:
                text = opt_item["text"].lower()
                opt_id = opt_item["id"]
                idx = opt_item["index"]

                # Check if exact text match or clean part match
                is_match = False
                for p in chosen_parts:
                    if p == text or (len(p) >= 3 and len(text) >= 3 and (p in text or text in p)):
                        is_match = True
                        break

                if is_match:
                    try:
                        locator = page.locator(f"#{opt_id}").first if opt_id else page.locator(f"input[name='{g_name}']").nth(idx)
                        locator.check(force=True)
                        matched = True
                        selected_labels.append(opt_item["text"] or opt_item["value"])
                    except Exception:
                        try:
                            page.locator(f"label:has(#{opt_id})").first.click(force=True)
                            matched = True
                            selected_labels.append(opt_item["text"] or opt_item["value"])
                        except Exception:
                            pass

            # If no skills matched, check negative fallback (e.g. None of these / Tidak ada)
            if not matched and options:
                for opt_item in options:
                    text = opt_item["text"].lower()
                    opt_id = opt_item["id"]
                    idx = opt_item["index"]
                    if any(k in text for k in ("none", "tidak ada", "bukan salah satu", "no experience")):
                        try:
                            locator = page.locator(f"#{opt_id}").first if opt_id else page.locator(f"input[name='{g_name}']").nth(idx)
                            locator.check(force=True)
                            matched = True
                            selected_labels.append(opt_item["text"] or opt_item["value"])
                        except Exception:
                            pass
                        break

            if matched:
                print(f"    Setting {g_type} \"{title}\" -> {', '.join(selected_labels)}", flush=True)
            elif not g_entry["any_checked"]:
                unknown.append(f"{title} (checkbox option not matched: {ans_val})")

    # 5. Apply answers to Input Fields / Selects
    for f_entry in fields_map:
        label = f_entry["label"]
        tag = f_entry["tag"]
        name = f_entry["name"]
        id_attr = f_entry["id"]
        selected_val = f_entry.get("selected_value")
        ans_val = f_entry["cached_answer"] or batch_results.get(f_entry["key"])

        # If already selected/has a value and no override answer, we are good
        if ans_val is None and selected_val:
            continue

        if ans_val is None:
            if interactive:
                ans_val = input(f"    ? {label}: ").strip() or None
            if ans_val is None:
                unknown.append(label)
                continue
            if conn is not None:
                add_answer(conn, re.escape(label), ans_val)
            answers.append({"match": re.escape(label), "answer": ans_val})

        try:
            el_locator = page.locator(f"#{id_attr}").first if id_attr else page.locator(f"[name='{name}']").first
            el = el_locator.element_handle()
            if not el:
                continue

            if tag == "select":
                ok = select_best_option(el, ans_val, salary_int=salary)
                if ok:
                    print(f"    Selecting dropdown \"{label}\" -> {ans_val}", flush=True)
                else:
                    unknown.append(f"{label} (select option not matched: {ans_val})")
            else:
                el_locator.fill(str(ans_val))
                print(f"    Filling \"{label}\" -> {ans_val}", flush=True)
            page.wait_for_timeout(250)
        except Exception:
            unknown.append(f"{label} (fill failed)")

    return unknown


def _click_continue_if_present(page: Page) -> bool:
    btn = page.locator('button[data-testid="continue-button"], button[data-automation="continue-button"], button:has-text("Lanjut"), button:has-text("Continue"), button:has-text("Next")').last
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


def _check_step_errors(page: Page) -> list[str]:
    """Checks if there are active validation banners or field error messages blocking progression."""
    try:
        errors = page.evaluate("""() => {
            const errList = [];
            const banners = Array.from(document.querySelectorAll('[data-automation*="error"], [role="alert"], [data-testid*="error"]'));
            for (const b of banners) {
                const t = (b.innerText || '').replace(/\\s+/g, ' ').trim();
                if (t.length > 5 && !errList.includes(t)) errList.push(t);
            }
            return errList;
        }""")
        return errors or []
    except Exception:
        return []


def apply_to_job(page: Page, job: dict, cfg: dict, profile: dict,
                 answers: list, *, execute: bool = False,
                 use_llm_letter: bool = False, interactive: bool = True,
                 conn=None) -> dict:
    salary = salary_for(job, profile)

    letter = None
    if use_llm_letter:
        print("  -> Writing cover letter (LLM-tailored)...", flush=True)
        letter = render_llm(job["title"], job["company"],
                            job.get("description") or "", cfg, profile)
    else:
        print("  -> Skipping cover letter (AI cover letter disabled)...", flush=True)

    print(f"  -> Navigating to job page: {job['url']}", flush=True)
    page.goto(job["url"], wait_until="domcontentloaded", timeout=45_000)
    _check_bot_wall(page)

    print("  -> Clicking 'Apply' button...", flush=True)
    _click_apply(page)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    page.wait_for_timeout(1000)
    _check_bot_wall(page)
    _check_auth_state(page)
    _check_external_ats(page, cfg)

    # Step through JobStreet's multi-step apply wizard:
    # 1. Documents (Resume & Cover Letter)
    # 2. Role Requirements (Questionnaire)
    # 3. Profile Updates / Personal Information
    # 4. Review & Submit
    max_steps = 10
    reached_review = False
    for step in range(1, max_steps + 1):
        _check_bot_wall(page)
        _check_auth_state(page)
        _check_external_ats(page, cfg)

        print(f"  -> Application step {step}: inspecting form elements...", flush=True)

        submit_btn = page.locator('button[data-testid="review-submit-application"], button[data-automation="review-submit-application"], button:has-text("Kirim lamaran"), button:has-text("Submit application")').first
        if "/review" in page.url or (submit_btn.count() and submit_btn.is_visible()):
            print("  -> Reached final review step.", flush=True)
            reached_review = True
            break

        if use_llm_letter and letter:
            tulis_radio = page.locator('label:has-text("Tulis surat lamaran"), label:has-text("Write a cover letter"), input[value="change"]').first
            if tulis_radio.count() and tulis_radio.is_visible():
                try:
                    print("    Putting cover letter into form...", flush=True)
                    tulis_radio.click(force=True)
                    page.wait_for_timeout(400)
                    textarea = page.locator('textarea').first
                    if textarea.count() and textarea.is_visible():
                        textarea.fill(letter)
                        print(f"    Cover letter entered ({len(letter)} characters).", flush=True)
                except Exception as e:
                    print(f"    [Warning putting cover letter: {e}]", flush=True)
        else:
            no_letter_radio = page.locator('label:has-text("Jangan sertakan surat lamaran"), label:has-text("Don\'t include a cover letter"), label:has-text("Do not include a cover letter"), input[value="none"]').first
            if no_letter_radio.count() and no_letter_radio.is_visible():
                try:
                    print("    Selecting 'Jangan sertakan surat lamaran'...", flush=True)
                    no_letter_radio.click(force=True)
                except Exception as e:
                    print(f"    [Warning selecting 'Jangan sertakan surat lamaran': {e}]", flush=True)

        unknown = _fill_known_fields(
            page, answers, salary, interactive, conn,
            job=job, profile=profile, cfg=cfg
        )
        if unknown:
            raise ApplyFailed(f"unknown questions on step {step} ({page.url}): {unknown}")

        # Advance to the next wizard step with explicit wait
        print("  -> Checking and advancing to next step...", flush=True)
        continued = _click_continue_if_present(page)
        page.wait_for_timeout(2000)
        _check_external_ats(page, cfg)

        # Check for any active validation errors after attempting to advance
        step_errors = _check_step_errors(page)
        if step_errors:
            _screenshot(page, f"val-error-{job['jobstreet_id']}")
            raise ApplyFailed(f"validation errors on step {step}: {', '.join(step_errors)}")

        if not continued:
            submit_btn = page.locator('button[data-testid="review-submit-application"], button[data-automation="review-submit-application"], button:has-text("Kirim lamaran"), button:has-text("Submit application")').first
            if submit_btn.count() and submit_btn.is_visible():
                print("  -> Reached review and submit screen.", flush=True)
                reached_review = True
                break
            page.wait_for_timeout(1000)

    # Final check before submit
    _check_external_ats(page, cfg)
    print("  -> Final review: checking submission button...", flush=True)
    submit_btn = page.locator('button[data-testid="review-submit-application"], button[data-automation="review-submit-application"], button:has-text("Kirim lamaran"), button:has-text("Submit application")').first
    if not submit_btn.count() or not submit_btn.is_visible():
        if "/apply/external" in page.url.lower() or ("jobstreet.com" not in page.url.lower() and "seek.com" not in page.url.lower()):
            raise ApplySkipped(f"external ATS redirect: {page.url}")
        _screenshot(page, f"fail-{job['jobstreet_id']}")
        step_errors = _check_step_errors(page)
        err_detail = f" (validation: {', '.join(step_errors)})" if step_errors else ""
        raise ApplyFailed(f"submit button not found at {page.url}{err_detail} — incomplete application step")

    if not execute:
        shot = _screenshot(page, f"dryrun-{job['jobstreet_id']}")
        print("  -> [DRY-RUN] Stopped before final submission.", flush=True)
        return {"status": "dry-run", "salary": salary, "letter": letter,
                "screenshot": str(shot)}

    print("  -> Submitting application now...", flush=True)
    submit_btn.click(force=True)

    # JobStreet success messages can vary in exact wording and case:
    # "Lamaranmu telah dikirim", "Lamaran terkirim", "Application submitted", etc.
    # or redirect to /apply/success or confirmation screen.
    print("  -> Verifying application submission confirmation...", flush=True)
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
            arg=success_regex.pattern,
            timeout=25_000,
        )
    except Exception as e:
        _screenshot(page, f"fail-{job['jobstreet_id']}")
        raise ApplyFailed("success text not seen after submit") from e

    body_text = ""
    try:
        body_text = page.locator("body").inner_text() if page.locator("body").count() else ""
    except Exception:
        pass
    match = success_regex.search(body_text)
    observed_confirmation = match.group(0).strip() if match else cfg.get("apply", {}).get("success_text", "Lamaran dikirim")

    print(f"  -> Application successfully confirmed: {observed_confirmation}", flush=True)
    return {"status": "submitted", "salary": salary, "letter": letter,
            "confirmation": observed_confirmation}


def run_apply(cfg: dict, conn, profile: dict, *, execute: bool,
              use_llm_letter: bool, limit: int | None, headless: bool,
              jobs: list[dict] | None = None,
              playwright_ctx=None,
              browser_context=None) -> dict:
    if jobs is None:
        jobs = approved_unapplied(conn)
    if limit is None:
        limit = cfg.get("apply", {}).get("max_applications_per_run")
    if limit:
        jobs = jobs[:limit]
    # Rows from the DB plus dicts appended for interactively-typed answers.
    answers = list(list_answers(conn))
    results = {"submitted": 0, "dry-run": 0, "failed": 0, "skipped": 0}

    cooldown_days = cfg.get("filters", {}).get("company_cooldown_days", 0)
    valid_jobs = []
    for j in (jobs or []):
        j_dict = dict(j)
        if company_in_cooldown(conn, norm_company(j_dict.get("company")), cooldown_days):
            results["skipped"] += 1
            print(f"  -> Skipped: company {j_dict.get('company')} is in cooldown period.", flush=True)
        else:
            valid_jobs.append(j_dict)
    jobs = valid_jobs

    if not jobs:
        return results

    interactive = (not headless) and bool(getattr(sys, "stdin", None)) and sys.stdin.isatty()

    def _execute_apply_loop(page: Page) -> None:
        for idx, job in enumerate(jobs, 1):
            job = dict(job)
            print(f"\n[{idx}/{len(jobs)}] Processing application for: {job.get('title')} @ {job.get('company')}", flush=True)
            try:
                res = apply_to_job(page, job, cfg, profile, answers,
                                   execute=execute,
                                   use_llm_letter=use_llm_letter,
                                   interactive=interactive, conn=conn)
            except ApplySkipped as e:
                results["skipped"] += 1
                if "external" in str(e).lower() and conn and job.get("id"):
                    try:
                        conn.execute("UPDATE jobs SET is_external = 1 WHERE id = ?", (job["id"],))
                        conn.commit()
                    except Exception:
                        pass
                print(f"  SKIPPED {job.get('title')} @ {job.get('company')} ({e})", flush=True)
                continue
            except ApplyFailed as e:
                _screenshot(page, f"error-{job['jobstreet_id']}")
                results["failed"] += 1
                print(f"  FAILED {job.get('title')} @ {job.get('company')}: {e}", flush=True)
                continue
            except Exception as e:
                if "closed" in str(e).lower() or "target" in str(e).lower() or "pipe" in str(e).lower():
                    results["failed"] += 1
                    print(f"  FAILED {job.get('title')} @ {job.get('company')}: browser connection lost ({e})", flush=True)
                    break
                _screenshot(page, f"error-{job['jobstreet_id']}")
                results["failed"] += 1
                print(f"  FAILED {job.get('title')} @ {job.get('company')}: unexpected error ({e})", flush=True)
                continue

            if res["status"] == "submitted":
                insert_application(conn, job["id"], {
                    "applied_at": datetime.now().date().isoformat(),
                    "salary_entered": f"IDR {res['salary']:,}/month",
                    "cover_letter": res["letter"],
                    "confirmation": res["confirmation"],
                })
                results["submitted"] += 1
                print(f"  SUBMITTED {job.get('title')} @ {job.get('company')}", flush=True)
            else:
                results["dry-run"] += 1
                print(f"  DRY-RUN  {job.get('title')} @ {job.get('company')} "
                      f"(screenshot: {res['screenshot']})", flush=True)

            # Pacing delay between successive job applications
            page.wait_for_timeout(1500)

    if browser_context is not None:
        page = _new_page(browser_context)
        _execute_apply_loop(page)
    elif playwright_ctx is not None:
        context = _launch_persistent(playwright_ctx, headless=headless)
        page = _new_page(context)
        try:
            _execute_apply_loop(page)
        finally:
            try:
                context.close()
            except Exception:
                pass
            browser = getattr(context, "_apply_bot_browser", None)
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
    else:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            context = _launch_persistent(p, headless=headless)
            page = _new_page(context)
            try:
                _execute_apply_loop(page)
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                browser = getattr(context, "_apply_bot_browser", None)
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
    return results
