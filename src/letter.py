"""Cover letters generation and rendering.

Template fallback by default (zero tokens); --llm-letter tailors the cover letter
using the candidate profile, target job description, and custom instructions.
"""
from __future__ import annotations

import json
from .db import norm_text
from .llm import complete

DEFAULT_TEMPLATE = """Dear Hiring Team,

I am applying for the {role} position at {company}. {middle}

Thank you for your consideration. I would welcome the opportunity to discuss my application.

Sincerely,
{name}"""


def render(role: str, company: str, profile: dict, *, middle: str | None = None) -> str:
    """Render a deterministic cover letter template as a fallback."""
    name = profile.get("name", "Applicant")
    letter_cfg = profile.get("letter") or {}
    
    if not middle:
        pitch = letter_cfg.get("pitch", "")
        middles = letter_cfg.get("middles") or {}
        if isinstance(middles, dict) and middles.get("general"):
            middle = middles["general"]
        elif pitch:
            middle = f"My background as {pitch} aligns with this role, and I am eager to contribute to your team."
        else:
            middle = "My background and skills match this role, and I am eager to contribute, learn, and grow with your team."

    return DEFAULT_TEMPLATE.format(role=role, company=company, middle=middle, name=name)


def render_llm(role: str, company: str, description: str, cfg: dict,
               profile: dict) -> str:
    """Generate a tailored cover letter using the LLM given profile, job info, and custom instructions."""
    try:
        letter_cfg = profile.get("letter") or {}
        custom_instructions = letter_cfg.get("custom_instructions") or (
            "Write a concise, professional, and humble cover letter (100-150 words max). "
            "Highlight relevant skills and experiences directly aligned with the job requirements. "
            "Do not invent skills or exaggerate qualifications. "
            "Keep the tone direct and natural."
        )

        candidate_summary = {
            "name": profile.get("name", ""),
            "years_experience": profile.get("years_experience", 0),
            "pitch": letter_cfg.get("pitch", ""),
            "skills": profile.get("skills", []),
            "experience": profile.get("experience", []),
            "education": profile.get("education", {}),
            "projects": profile.get("projects", []),
        }

        system_prompt = (
            "You are an expert career advisor and job application writer. "
            "Write an authentic, highly tailored cover letter for a job applicant.\n\n"
            f"User's custom instructions:\n{custom_instructions}\n\n"
            "Formatting requirements:\n"
            "- Return ONLY the cover letter text ready to be sent.\n"
            "- Do not include placeholders like '[Insert Date]' or '[Company Address]'.\n"
            "- Use 'Dear Hiring Team,' or 'Dear Hiring Manager,' as greeting.\n"
            f"- Sign off with: Sincerely,\\n{profile.get('name', 'Applicant')}"
        )

        user_content = (
            f"Candidate Profile:\n{json.dumps(candidate_summary, ensure_ascii=False, indent=2)}\n\n"
            f"Target Position: {role}\n"
            f"Company: {company}\n"
            f"Job Description / Requirements:\n{(description or 'No specific description provided.')[:2500]}"
        )

        resp_text = complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            cfg=cfg,
            max_tokens=500,
            temperature=0.4,
        )

        letter = resp_text.strip().strip('"`')
        if letter:
            return letter
        return render(role, company, profile)
    except Exception:
        return render(role, company, profile)


def family_for(title: str, profile: dict | None = None) -> str:
    """Helper for legacy tests/references."""
    t = norm_text(title)
    if any(k in t for k in ("data analyst", "data scientist", "data engineer", "analyst", "bi ")):
        return "data"
    if any(k in t for k in ("ai ", "artificial intelligence", "machine learning", "ml ", "llm", "nlp")):
        return "ai"
    if any(k in t for k in ("software", "developer", "programmer", "backend", "back-end",
                            "front-end", "frontend", "full stack", "fullstack", "engineer")):
        return "swe"
    return "general"
