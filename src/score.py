"""Stage 2/3: deterministic filter pass + match scoring.

Two scorers:
- LLM scorer (default in later phases): one text-only call per batch,
  structured JSON verdicts. Never sees a browser snapshot.
- Offline scorer (--offline): keyword overlap between the job text and the
  profile skill vocabulary. Free, instant, deterministic.

In both cases: the model proposes, code disposes — hard vetoes re-run on the
structured output before anything reaches the apply stage.
"""
from __future__ import annotations

import json
import re

from .db import (
    insert_evaluation,
    jobs_without_evaluation,
    norm_text,
)
from .filters import parse_years_required, passes_all
from .llm import complete, get_llm_config

RULES_MODEL = "rules-v1"


# --- deterministic filter stage --------------------------------------------

def run_filters(cfg: dict, conn, jobs: list[dict] | None = None) -> tuple[list, int]:
    """Evaluate every unevaluated job against the deterministic gates.
    Returns (survivors, n_skipped)."""
    survivors, skipped = [], 0
    candidate_jobs = jobs if jobs is not None else jobs_without_evaluation(conn)
    for job in candidate_jobs:
        ok, reason = passes_all(dict(job), cfg, conn)
        if ok:
            survivors.append(dict(job))
        else:
            skipped += 1
            insert_evaluation(conn, job["id"], {
                "model": RULES_MODEL,
                "decision": "skip",
                "reason": reason,
            })
    return survivors, skipped


# --- decision mapping --------------------------------------------------------

def decide(match_pct: int | None, years_required: int | None,
           seniority: str | None, cfg: dict) -> tuple[str, str]:
    """Veto layer applied to any scorer's output."""
    max_years = cfg["filters"].get("max_years_experience")
    min_years = cfg["filters"].get("min_years_experience")
    if years_required is not None:
        if max_years is not None and years_required > max_years:
            return "skip", f"veto: requires {years_required} years (> {max_years})"
        if min_years is not None and min_years > 0 and years_required < min_years:
            return "skip", f"veto: requires {years_required} years (< {min_years})"
    if (seniority or "").lower() in {"senior", "lead", "manager", "intern"}:
        # Only veto seniority keywords if title blacklist contains them
        blacklist = [w.lower() for w in cfg["filters"].get("title_blacklist", [])]
        if any(w in (seniority or "").lower() for w in blacklist):
            return "skip", f"veto: seniority '{seniority}'"
    if match_pct is None:
        return "review", "no match signal"
    lo, hi = cfg["scoring"]["borderline_band"]
    pct = match_pct / 100
    if pct >= hi:
        return "apply", f"match {match_pct}% >= {int(hi * 100)}%"
    if pct >= lo:
        return "review", f"borderline match {match_pct}%"
    threshold = int(cfg["scoring"]["match_threshold"] * 100)
    return "skip", f"match {match_pct}% below {threshold}% threshold"


# --- offline scorer -----------------------------------------------------------

def _skill_vocab(profile: dict, cfg: dict) -> dict[str, str]:
    """alias (normalized) -> canonical name, for profile skills + extra vocab."""
    vocab: dict[str, str] = {}
    for skill in profile.get("skills", []):
        canon = norm_text(skill["name"])
        vocab[canon] = canon
        for alias in skill.get("aliases", []):
            vocab[norm_text(alias)] = canon
    for extra in cfg["scoring"]["extra_skill_vocab"]:
        vocab.setdefault(norm_text(extra), norm_text(extra))
    return vocab


def offline_score(job: dict, profile: dict, cfg: dict) -> dict:
    text = norm_text(" ".join(filter(None, [
        job.get("title"), job.get("description"), job.get("teaser")])))
    vocab = _skill_vocab(profile, cfg)
    profile_canons = {norm_text(s["name"]) for s in profile.get("skills", [])}

    mentioned: set[str] = set()
    for alias, canon in vocab.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            mentioned.add(canon)
    met = sorted(mentioned & profile_canons)
    unmet = sorted(mentioned - profile_canons)
    match_pct = round(100 * len(met) / len(mentioned)) if mentioned else None

    years = parse_years_required(text)
    title = norm_text(job.get("title"))
    seniority = ("intern" if re.search(r"\bintern|magang\b", title)
                 else "senior" if re.search(r"\bsenior|lead|manager\b", title)
                 else "junior" if re.search(r"\bjunior|fresh|graduate|entry\b", title)
                 else "unknown")
    decision, reason = decide(match_pct, years, seniority, cfg)
    return {
        "model": "offline-v1",
        "match_pct": match_pct,
        "years_required": years,
        "seniority": seniority,
        "met": json.dumps(met),
        "unmet": json.dumps(unmet),
        "decision": decision,
        "reason": reason,
    }


# --- LLM scorer ---------------------------------------------------------------

PROMPT_TEMPLATE = """You are evaluating job-candidate fit. Decide strictly from the texts.

PROFILE:
{profile_yaml}

RULES:
- Candidate qualifies if the profile meets at least 60% of the stated
  requirements. Nice-to-haves count at half weight.
- Reject if the role requires more than {max_years} year of experience.
- Reject if the role is intern, senior, lead, supervisor, or manager level.
- Never assume qualifications that are not in the profile.

For EACH job below return one JSON object:
{{"job_id": str,
  "match_pct": int,           # 0-100, share of stated requirements met
  "years_required": int|null, # null if unstated
  "seniority": "junior"|"mid"|"senior"|"intern"|"unknown",
  "met": [str],
  "unmet": [str],
  "apply": bool,
  "reason": str}}             # one sentence

Return a JSON array only, no prose.

JOBS:
{jobs_block}
"""


def build_prompt(profile_yaml: str, jobs: list[dict], cfg: dict) -> str:
    blocks = []
    for j in jobs:
        desc = (j.get("description") or j.get("teaser") or "")[:3000]
        blocks.append(
            f"{j['jobstreet_id']} — {j.get('title')} @ {j.get('company')}, "
            f"{j.get('location')}, {j.get('salary_text') or 'salary not shown'}\n{desc}"
        )
    return PROMPT_TEMPLATE.format(
        profile_yaml=profile_yaml,
        max_years=cfg["filters"]["max_years_experience"],
        jobs_block="\n\n".join(blocks),
    )


def _parse_verdicts(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("LLM response contained no JSON array")
    return json.loads(m.group(0))


def llm_score(jobs: list[dict], profile_yaml: str, cfg: dict) -> list[dict]:
    llm_conf = get_llm_config(cfg)
    model_name = llm_conf["model"]
    prompt = build_prompt(profile_yaml, jobs, cfg)
    resp_text = complete(
        [{"role": "user", "content": prompt}],
        cfg,
        max_tokens=2000,
    )
    verdicts = _parse_verdicts(resp_text)
    by_id = {str(v.get("job_id")): v for v in verdicts}
    out = []
    for j in jobs:
        v = by_id.get(str(j["jobstreet_id"]))
        if v is None:
            out.append({"model": model_name, "decision": "review",
                        "reason": "LLM returned no verdict"})
            continue
        decision, reason = decide(v.get("match_pct"), v.get("years_required"),
                                  v.get("seniority"), cfg)
        out.append({
            "model": model_name,
            "match_pct": v.get("match_pct"),
            "years_required": v.get("years_required"),
            "seniority": v.get("seniority"),
            "met": json.dumps(v.get("met", [])),
            "unmet": json.dumps(v.get("unmet", [])),
            "decision": decision,
            "reason": f"{reason} | llm: {v.get('reason', '')}",
        })
    return out


# --- orchestration --------------------------------------------------------------

def score_pending(cfg: dict, conn, profile: dict, *, offline: bool,
                  limit: int | None = None, jobs: list[dict] | None = None) -> dict:
    survivors, n_filtered = run_filters(cfg, conn, jobs=jobs)
    if limit:
        survivors = survivors[:limit]

    scored = 0
    if offline:
        for job in survivors:
            insert_evaluation(conn, job["id"], offline_score(job, profile, cfg))
            scored += 1
    else:
        import yaml

        llm_conf = get_llm_config(cfg)
        model_name = llm_conf["model"]
        profile_yaml = yaml.safe_dump(profile, sort_keys=False)
        batch_size = cfg["scoring"]["batch_size"]
        for i in range(0, len(survivors), batch_size):
            batch = survivors[i:i + batch_size]
            try:
                verdicts = llm_score(batch, profile_yaml, cfg)
            except Exception as e:
                verdicts = [{"model": model_name, "decision": "review",
                             "reason": f"LLM error: {e}"}] * len(batch)
            for job, ev in zip(batch, verdicts):
                insert_evaluation(conn, job["id"], ev)
                scored += 1
    return {"filtered": n_filtered, "scored": scored}
