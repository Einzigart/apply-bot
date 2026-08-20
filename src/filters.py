"""Deterministic gates. Every skip returns a human-readable reason.

Order (cheapest first): title -> location -> experience -> dedup -> role fit.
"""
from __future__ import annotations

import re
from datetime import date

from .db import company_in_cooldown, job_already_applied, norm_text


def _word_patterns(words: list[str]) -> list[re.Pattern]:
    """\\b only where the term actually starts/ends with a word char,
    so 'sr.' still matches 'Sr. Backend Developer'."""
    pats = []
    for w in words:
        w = w.strip()
        start = r"\b" if w[0].isalnum() else ""
        end = r"\b" if w[-1].isalnum() else ""
        pats.append(re.compile(start + re.escape(w) + end, re.I))
    return pats


def title_check(title: str, cfg: dict) -> tuple[bool, str | None]:
    """Blacklist check: title matching title_blacklist is rejected.
    If role_keywords is defined and non-empty, checks that at least one keyword matches.
    If role_keywords is empty or absent, allows all search results through to scoring.
    """
    for pat in _word_patterns(cfg["filters"].get("title_blacklist", [])):
        if pat.search(title or ""):
            return False, f"title blacklist: '{pat.pattern}'"
    keywords = cfg["filters"].get("role_keywords") or []
    if keywords:
        t = norm_text(title)
        if not any(norm_text(k) in t for k in keywords):
            return False, "title has no target-role keyword"
    return True, None


def location_ok(location: str | None, cfg: dict) -> bool:
    """If location_whitelist is empty, allows all locations. Otherwise checks match."""
    loc = norm_text(location)
    if not loc:
        return True  # unknown location -> don't filter out yet
    whitelist = cfg["filters"].get("location_whitelist") or []
    if not whitelist:
        return True
    return any(norm_text(w) in loc for w in whitelist)


# (pattern, needs_age_check) — patterns whose match contains an experience word
# are self-governed and never describe age, so they skip the age check.
_YEARS_PATTERNS = [
    # "minimal 2 tahun", "minimum 3 years", "at least 1 year", "setidaknya 2 tahun"
    (re.compile(
        r"(?:minimal|minimum|min\.?|at least|setidaknya|paling sedikit|lebih dari)\s*"
        r"(\d{1,2})\s*(?:tahun|thn|years?|yrs?)", re.I), True),
    # ranges: "0-1 years", "1-3 tahun" -> upper bound governs
    (re.compile(r"(\d{1,2})\s*[-–~]\s*(\d{1,2})\s*(?:tahun|thn|years?|yrs?)", re.I), True),
    # "2 years experience", "1 tahun pengalaman", "3+ years of experience"
    (re.compile(
        r"(\d{1,2})\s*\+?\s*(?:tahun|thn|years?|yrs?)\s*"
        r"(?:of\s*)?(?:pengalaman|experience|kerja|working)", re.I), False),
    # "pengalaman 2 tahun", "pengalaman kerja 1 tahun"
    (re.compile(r"pengalaman\s*(?:kerja\s*)?(?:selama\s*)?(\d{1,2})\s*(?:tahun|thn)", re.I), False),
]
_FRESH = re.compile(r"fresh[\s-]?graduate|freshgrad|new grad|lulusan baru", re.I)
_AGE = re.compile(r"usia|umur|berusia|berumur|age", re.I)


def _is_age_context(text: str, start: int) -> bool:
    """'Usia 23-30 tahun' / 'max age 30' are age requirements, not experience."""
    return bool(_AGE.search(text[max(0, start - 40):start]))


def parse_years_required(text: str | None) -> int | None:
    """Max years-of-experience signal found in the text, or None if unstated.
    Conservative: any range contributes its upper bound. Age mentions ignored."""
    if not text:
        return None
    found: list[int] = []
    for pat, needs_age_check in _YEARS_PATTERNS:
        for m in pat.finditer(text):
            if needs_age_check and _is_age_context(text, m.start()):
                continue
            found.append(max(int(g) for g in m.groups()))
    if found:
        return max(found)
    return 0 if _FRESH.search(text) else None


def passes_all(job: dict, cfg: dict, conn, today: date | None = None) -> tuple[bool, str | None]:
    """Full deterministic gate run against a job row/dict."""
    ok, reason = title_check(job.get("title") or "", cfg)
    if not ok:
        return False, reason

    if not location_ok(job.get("location"), cfg):
        return False, f"location outside whitelist: {job.get('location')!r}"

    years = parse_years_required(
        " ".join(filter(None, [job.get("title"), job.get("description"), job.get("teaser")]))
    )
    max_exp = cfg["filters"].get("max_years_experience")
    min_exp = cfg["filters"].get("min_years_experience")
    if years is not None:
        if max_exp is not None and years > max_exp:
            return False, f"requires {years} years experience (> {max_exp})"
        if min_exp is not None and min_exp > 0 and years < min_exp:
            return False, f"requires {years} years experience (< {min_exp})"

    if conn is not None:
        from .db import norm_company

        if job.get("jobstreet_id") and job_already_applied(conn, job["jobstreet_id"]):
            return False, "already applied to this job"
        cnorm = job.get("company_norm") or norm_company(job.get("company"))
        if company_in_cooldown(conn, cnorm, cfg["filters"]["company_cooldown_days"], today):
            return False, f"company applied within {cfg['filters']['company_cooldown_days']}d cooldown"

    return True, None
