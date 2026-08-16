"""Cover letters. Template by default (zero tokens); --llm-letter tailors the
middle sentence with one small call.

All personal content (name, pitch, middle sentences) comes from the
profile's `letter:` section — nothing candidate-specific lives in code.
"""
from __future__ import annotations

from .db import norm_text
from .llm import complete

TEMPLATE = """Dear Hiring Team,

I am applying for the {role} position at {company}. {middle}

Thank you for your consideration. I would welcome the opportunity to discuss my application.

Sincerely,
{name}"""


def family_for(title: str) -> str:
    t = norm_text(title)
    if any(k in t for k in ("data analyst", "data scientist", "data engineer", "analyst", "bi ")):
        return "data"
    if any(k in t for k in ("ai ", "artificial intelligence", "machine learning", "ml ", "llm", "nlp")):
        return "ai"
    if any(k in t for k in ("software", "developer", "programmer", "backend", "back-end",
                            "front-end", "frontend", "full stack", "fullstack", "engineer")):
        return "swe"
    return "general"


def render(role: str, company: str, profile: dict, *, family: str | None = None) -> str:
    middles = profile["letter"]["middles"]
    middle = middles.get(family or family_for(role)) or middles["general"]
    return TEMPLATE.format(role=role, company=company, middle=middle,
                           name=profile["name"])


def render_llm(role: str, company: str, description: str, cfg: dict,
               profile: dict) -> str:
    """One small call to tailor the middle sentence; falls back to template."""
    try:
        prompt = (
            "Write ONE sentence (max 35 words) in plain English for a cover letter.\n"
            f"Candidate profile: {profile['letter']['pitch']}.\n"
            f"Target role: {role} at {company}.\n"
            f"Job excerpt: {(description or '')[:600]}\n"
            "Requirements:\n"
            "- Concise, direct, honest, and humble tone.\n"
            "- Connect real experience to the role without exaggerating.\n"
            "- Do NOT use em dashes (—) or hyphen dashes (--).\n"
            "- Do NOT invent skills or qualifications."
        )
        resp_text = complete(
            messages=[{"role": "user", "content": prompt}],
            cfg=cfg,
            max_tokens=100,
            temperature=0.5,
        )
        middle = resp_text.strip().strip('"').replace("—", ",").replace(" -- ", ", ").replace("--", ", ")
        return TEMPLATE.format(role=role, company=company, middle=middle,
                               name=profile["name"])
    except Exception:
        return render(role, company, profile)
