"""Cover letters. Template by default (zero tokens); --llm-letter tailors the
middle sentence with one small call."""
from __future__ import annotations

from .db import norm_text

TEMPLATE = """Dear Hiring Team,

I am applying for the {role} position at {company}. {middle}

Thank you for your consideration. I would welcome the opportunity to discuss my application.

Sincerely,
the candidate"""

MIDDLES = {
    "data": ("My background in data analysis — SQL, Python, ETL pipelines, and "
             "Looker dashboards built during my time at the Ministry of Communication "
             "and Digital Affairs — matches this role, and I am eager to contribute, "
             "learn, and grow with your team."),
    "ai": ("My background in AI/ML engineering — LLMs, RAG, NLP, and computer vision "
           "with Python and PyTorch, including an IEEE-published project — matches "
           "this role, and I am eager to contribute, learn, and grow with your team."),
    "swe": ("My background in software engineering — Python, TypeScript, React/Next.js, "
            "Django/FastAPI, and PostgreSQL — matches this role, and I am eager to "
            "contribute, learn, and grow with your team."),
    "general": ("My background in software engineering, artificial intelligence, data, "
                "and machine learning matches this role, and I am eager to contribute, "
                "learn, and grow with your team."),
}


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


def render(role: str, company: str, *, family: str | None = None) -> str:
    return TEMPLATE.format(role=role, company=company,
                           middle=MIDDLES[family or family_for(role)])


def render_llm(role: str, company: str, description: str, cfg: dict) -> str:
    """One small call to tailor the middle sentence; falls back to template."""
    try:
        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=cfg["scoring"]["model"],
            max_tokens=150,
            messages=[{"role": "user", "content": (
                "Write ONE sentence (max 40 words) for a cover letter. Candidate: "
                "junior software/AI/data engineer (Python, SQL, PyTorch, RAG, React, "
                "FastAPI; internship at a government ministry). "
                f"Role: {role} at {company}. Job excerpt: {(description or '')[:800]}\n"
                "The sentence must connect the candidate's real background to the role. "
                "English, simple, no invented qualifications."
            )}],
        )
        middle = resp.content[0].text.strip().strip('"')
        return TEMPLATE.format(role=role, company=company, middle=middle)
    except Exception:
        return render(role, company)
