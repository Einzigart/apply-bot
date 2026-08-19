"""CV and Resume parsing module using PyPDF and LLM extraction."""
from __future__ import annotations

import ast
import io
import json
import re
from typing import Any
import pypdf

from .llm import complete


CV_EXTRACT_SYSTEM_PROMPT = """You are an expert HR assistant, career advisor, and automated job search strategist.
Your task is to analyze the provided raw CV/Resume text (which was extracted from a PDF and may contain formatting artifacts, split lines, or messy columns).
You must extract both the candidate profile AND predict the optimal automated job search & application configuration strictly conforming to the JSON schema below.

JSON SCHEMA:
{
  "name": "Full Name",
  "location": "City, Country (e.g. Jakarta, Indonesia or Remote)",
  "work_rights": "Work authorization status (e.g. 'Citizen, no sponsorship required' or 'Authorized to work in Indonesia')",
  "cv_file": "filename.pdf",
  "years_experience": 2.5,
  "languages": ["English (fluent)", "Indonesian (native)"],
  "locations_ok": ["Jakarta", "Remote"],
  "education": {
    "degree": "Bachelor of Science in Computer Science",
    "university": "Name of Institution",
    "period": "2020-08 to 2024-07",
    "gpa": "3.80/4.00",
    "certifications": ["AWS Certified Developer", "TensorFlow Developer Certificate"]
  },
  "experience": [
    {
      "role": "Job Title",
      "org": "Company Name",
      "period": "2023-01 to Present",
      "summary": "1-2 concise sentences summarizing key accomplishments, systems built, and technologies used."
    }
  ],
  "skills": [
    {
      "name": "python",
      "aliases": ["python3", "py", "cpython"]
    },
    {
      "name": "fastapi",
      "aliases": ["fast-api", "starlette"]
    }
  ],
  "projects": [
    "Project Title — One-line description of what it does and the stack used (Python, React, SQLite)."
  ],
  "salary": {
    "preferred": 10000000,
    "min_acceptable": 8000000
  },
  "salary_expectation": "8000000-10000000 IDR/month",
  "letter": {
    "pitch": "Brief 1-line professional pitch summarizing background and core expertise (e.g. 'full stack engineer specializing in Python, FastAPI, and React' or 'marketing specialist experienced in content strategy and SEO')",
    "custom_instructions": "Keep the letter concise (100-150 words max), humble, and direct. Highlight relevant achievements in Python, FastAPI, and PostgreSQL matching the job requirements."
  },
  "predicted_config": {
    "target_roles": [
      {
        "name": "Software Engineer",
        "slug": "software-engineer"
      },
      {
        "name": "Backend Developer",
        "slug": "backend-developer"
      },
      {
        "name": "Full Stack Developer",
        "slug": "full-stack-developer"
      }
    ],
    "target_locations": [
      {
        "name": "Jakarta",
        "slug": "Jakarta"
      },
      {
        "name": "Tangerang",
        "slug": "Tangerang"
      },
      {
        "name": "Remote (Indonesia)",
        "slug": "Indonesia"
      }
    ],
    "role_keywords": ["software", "engineer", "developer", "backend", "full stack", "python", "fastapi"],
    "location_whitelist": ["jakarta", "tangerang", "remote", "indonesia"],
    "min_years_experience": 0,
    "max_years_experience": 3
  }
}

INSTRUCTIONS & RULES:
1. Return ONLY a valid JSON object. Do not include introductory text, explanations, or wrapping markdown other than ```json if needed.
2. Clean up any OCR/PDF extraction anomalies (e.g. broken words, split lines, column interleaving).
3. Compute `years_experience` realistically based on work history dates (e.g., 0.5 for 6 months, 2.0 for 2 years). If entry level / student, use 0.5.
4. For `skills`, convert all skill `name` fields to lowercase (e.g. "python", "react", "postgresql", "docker", "figma", "copywriting"). Provide 1 to 4 useful search aliases for each skill.
5. In `letter.pitch`, provide a crisp 1-line summary of the candidate's professional identity and core strengths.
6. In `letter.custom_instructions`, craft tailored AI instructions mentioning specific strong tools/strengths from the CV to emphasize during cover letter generation.
7. In `predicted_config`:
   - `target_roles`: Predict 3 to 6 high-relevance Jobstreet search roles tailored specifically to the candidate's skills and trajectory (e.g. `[{"name": "Frontend Developer", "slug": "frontend-developer"}, ...]`). Format slugs with hyphens and lowercase.
   - `target_locations`: Predict relevant locations based on candidate residence and willingness to work remote or in major nearby tech hubs.
   - `role_keywords`: Predict 6 to 12 relevant matching keywords for filtering relevant job titles.
   - `location_whitelist`: Predict lowercase cities or "remote" where the candidate can work.
   - `min_years_experience` and `max_years_experience`: Set realistic filtering bounds based on candidate's experience (e.g. For 1.5 yrs exp, min 0, max 3).
8. If salary is not explicitly mentioned in the CV, supply realistic defaults in IDR (e.g. preferred: 7000000, min_acceptable: 6000000, expectation: "6000000-7000000 IDR/month").
9. Ensure all fields in the schema are present. Do not use null for strings or lists; use empty strings "" or empty lists [] if completely unknown.
"""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract raw text from PDF bytes using PyPDF."""
    if not pdf_bytes:
        raise ValueError("Empty PDF payload.")

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    if len(reader.pages) == 0:
        raise ValueError("PDF contains no pages.")

    pages_text: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text()
            if txt:
                pages_text.append(txt.strip())
        except Exception as e:
            pages_text.append(f"[Error extracting page {i+1}: {e}]")

    combined = "\n\n--- Page Break ---\n\n".join(pages_text)
    if not combined.strip():
        raise ValueError("Could not extract any text from the provided PDF. It may be scanned images without OCR.")

    return combined


def _sanitize_json_text(text: str) -> str:
    """Pre-process text to remove comments, fix trailing commas, and unescape common artifacts."""
    # 1. Remove JavaScript-style single-line and multi-line comments
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # 2. Fix trailing commas before closing braces or brackets (e.g. `{"a": 1,}` or `[1, 2,]`)
    text = re.sub(r",\s*(\})", r"\1", text)
    text = re.sub(r",\s*(\])", r"\1", text)

    return text.strip()


def _attempt_repair_truncated_json(text: str) -> str:
    """Attempt to balance open quotes, brackets, and braces if JSON was truncated."""
    # If unclosed string quote at the end, close it
    # Count unescaped double quotes
    quotes = len(re.findall(r'(?<!\\)"', text))
    if quotes % 2 != 0:
        text += '"'

    # Remove any dangling key or comma before closing, e.g. `, "key": ` or `, `
    text = re.sub(r',\s*("[^"]*"\s*:\s*)?$', '', text)
    text = re.sub(r',\s*$', '', text)

    # Count unmatched opening braces and brackets
    open_curly = 0
    open_square = 0
    in_string = False
    escape = False

    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == '{':
            open_curly += 1
        elif ch == '}':
            open_curly = max(0, open_curly - 1)
        elif ch == '[':
            open_square += 1
        elif ch == ']':
            open_square = max(0, open_square - 1)

    # Close open brackets and braces in reverse order approximation
    text += (']' * open_square) + ('}' * open_curly)
    return text


def _clean_json_response(raw_resp: str) -> dict[str, Any]:
    """Clean markdown code fences and parse JSON with multi-tier error recovery."""
    cleaned = raw_resp.strip()
    if not cleaned:
        raise ValueError("LLM returned empty response.")

    # 1. Extract block from ```json ... ``` code fence if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    else:
        # Fallback to finding outermost { ... }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
        elif start != -1:
            # Model started JSON but never finished closing brace (truncated)
            cleaned = cleaned[start:]

    sanitized = _sanitize_json_text(cleaned)

    # Tier 1: Direct standard JSON decode
    try:
        data = json.loads(sanitized)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Tier 2: Attempt auto-repair on truncated JSON (balance braces/quotes)
    try:
        repaired = _attempt_repair_truncated_json(sanitized)
        repaired = _sanitize_json_text(repaired)
        data = json.loads(repaired)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Tier 3: Python AST evaluation (for single-quoted dicts or python-style dict outputs)
    try:
        # Replace JS bools/null if mixed in python dict syntax
        py_str = sanitized.replace(": true", ": True").replace(": false", ": False").replace(": null", ": None")
        data = ast.literal_eval(py_str)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # If all tiers fail, raise original descriptive error
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM did not return valid JSON: {e}\nRaw output:\n{raw_resp[:500]}") from e


def _normalize_profile_schema(data: dict[str, Any], filename: str = "CV.pdf") -> dict[str, Any]:
    """Ensure all required fields exist and conform to the expected types for lower-tier LLMs."""
    if not isinstance(data, dict):
        data = {}

    # Basic string fields
    data["name"] = str(data.get("name") or "Candidate").strip()
    data["location"] = str(data.get("location") or "Remote").strip()
    data["work_rights"] = str(data.get("work_rights") or "Authorized to work").strip()
    data["cv_file"] = filename or str(data.get("cv_file") or "CV.pdf")

    # Numeric experience
    try:
        data["years_experience"] = float(data.get("years_experience", 1.0))
    except (ValueError, TypeError):
        data["years_experience"] = 1.0

    # Lists
    data["languages"] = [str(x) for x in data.get("languages", []) if x]
    data["locations_ok"] = [str(x) for x in data.get("locations_ok", []) if x]
    data["projects"] = [str(x) for x in data.get("projects", []) if x]

    # Normalize Education
    edu = data.get("education")
    if isinstance(edu, dict):
        certs = edu.get("certifications", [])
        if isinstance(certs, str):
            certs = [certs] if certs.strip() else []
        edu["certifications"] = [str(c) for c in certs if c]
        edu["degree"] = str(edu.get("degree") or "")
        edu["university"] = str(edu.get("university") or "")
        edu["period"] = str(edu.get("period") or "")
        edu["gpa"] = str(edu.get("gpa") or "")
        data["education"] = edu
    elif isinstance(edu, list) and edu and isinstance(edu[0], dict):
        data["education"] = edu[0]
    else:
        data["education"] = {
            "degree": str(edu or ""),
            "university": "",
            "period": "",
            "gpa": "",
            "certifications": [],
        }

    # Normalize Experience
    exp = data.get("experience")
    if isinstance(exp, list):
        norm_exp = []
        for item in exp:
            if isinstance(item, dict):
                norm_exp.append({
                    "role": str(item.get("role") or ""),
                    "org": str(item.get("org") or item.get("company") or ""),
                    "period": str(item.get("period") or ""),
                    "summary": str(item.get("summary") or item.get("description") or ""),
                })
        data["experience"] = norm_exp
    else:
        data["experience"] = []

    # Normalize Skills: [{"name": "python", "aliases": ["python"]}]
    skills = data.get("skills")
    norm_skills = []
    if isinstance(skills, list):
        for item in skills:
            if isinstance(item, dict) and "name" in item:
                name = str(item["name"]).lower().strip()
                aliases = item.get("aliases") or [name]
                if isinstance(aliases, str):
                    aliases = [aliases]
                aliases = [str(a).lower().strip() for a in aliases if a]
                if name not in aliases:
                    aliases.insert(0, name)
                norm_skills.append({"name": name, "aliases": aliases})
            elif isinstance(item, str) and item.strip():
                name = item.lower().strip()
                norm_skills.append({"name": name, "aliases": [name]})
    data["skills"] = norm_skills

    # Normalize Salary
    sal = data.get("salary")
    if isinstance(sal, dict):
        try:
            pref = int(sal.get("preferred") or 7000000)
            min_acc = int(sal.get("min_acceptable") or 6000000)
        except (ValueError, TypeError):
            pref, min_acc = 7000000, 6000000
        data["salary"] = {"preferred": pref, "min_acceptable": min_acc}
    else:
        data["salary"] = {"preferred": 7000000, "min_acceptable": 6000000}

    if not data.get("salary_expectation"):
        data["salary_expectation"] = (
            f"{data['salary']['min_acceptable']}-{data['salary']['preferred']} IDR/month"
        )

    # Normalize Letter Pitch & Instructions
    let = data.get("letter")
    if isinstance(let, dict):
        pitch = str(let.get("pitch") or "")
        custom_inst = str(let.get("custom_instructions") or "")
    else:
        pitch = str(let or "")
        custom_inst = ""
    data["letter"] = {
        "pitch": pitch or f"Professional with {data['years_experience']} years experience",
        "custom_instructions": custom_inst or "Highlight relevant skills and background matching the role.",
    }

    # Normalize Predicted Config
    pred = data.get("predicted_config")
    if not isinstance(pred, dict):
        pred = {}

    target_roles = pred.get("target_roles") or []
    norm_roles = []
    if isinstance(target_roles, list):
        for r in target_roles:
            if isinstance(r, dict) and "name" in r:
                r_name = str(r["name"]).strip()
                slug = str(r.get("slug") or r_name.lower().replace(" ", "-")).strip()
                norm_roles.append({"name": r_name, "slug": slug})
            elif isinstance(r, str) and r.strip():
                norm_roles.append({"name": r.strip(), "slug": r.strip().lower().replace(" ", "-")})

    if not norm_roles:
        # Fallback to roles inferred from candidate skills or experience
        first_role = (data["experience"][0]["role"] if data["experience"] else "") or "Software Engineer"
        norm_roles = [
            {"name": first_role, "slug": first_role.lower().replace(" ", "-")},
            {"name": "Developer", "slug": "developer"},
        ]

    data["predicted_config"] = {
        "target_roles": norm_roles,
        "target_locations": pred.get("target_locations") or [
            {"name": data["location"] or "Jakarta", "slug": data["location"] or "Jakarta"}
        ],
        "role_keywords": [str(k).lower() for k in pred.get("role_keywords") or [r["name"].lower() for r in norm_roles]],
        "location_whitelist": [str(loc).lower() for loc in pred.get("location_whitelist") or ["jakarta", "remote", "indonesia"]],
        "min_years_experience": int(pred.get("min_years_experience", max(0, int(data["years_experience"]) - 1))),
        "max_years_experience": int(pred.get("max_years_experience", int(data["years_experience"]) + 3)),
    }

    return data


def parse_cv_with_llm(cv_text: str, cfg: dict, filename: str = "CV.pdf") -> dict[str, Any]:
    """Parse CV text into structured profile data using configured LLM with automatic repair."""
    messages = [
        {"role": "system", "content": CV_EXTRACT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Uploaded filename: {filename}\n\nRaw extracted CV text:\n\n{cv_text}",
        },
    ]

    resp_text = complete(
        messages=messages,
        cfg=cfg,
        max_tokens=8192,
        temperature=0.1,
    )

    try:
        data = _clean_json_response(resp_text)
    except Exception as e:
        # Secondary fallback: Ask LLM to format raw output as valid JSON (great for local/smaller models)
        repair_messages = [
            {
                "role": "system",
                "content": "You are a JSON repair tool. Convert the following text into valid, well-formed JSON conforming strictly to the requested schema. Return ONLY valid JSON.",
            },
            {
                "role": "user",
                "content": f"Raw unparsed response:\n{resp_text[:3000]}\n\nError:\n{e}",
            },
        ]
        try:
            repaired_text = complete(
                messages=repair_messages,
                cfg=cfg,
                max_tokens=8192,
                temperature=0.0,
            )
            data = _clean_json_response(repaired_text)
        except Exception:
            raise e

    if not isinstance(data, dict):
        raise ValueError("Extracted profile is not a JSON object.")

    # Normalize structure and fill any missing keys defensively
    return _normalize_profile_schema(data, filename=filename)
