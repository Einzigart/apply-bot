"""CV and Resume parsing module using PyPDF and LLM extraction."""
from __future__ import annotations

import io
import json
import re
from typing import Any
import pypdf

from .llm import complete


CV_EXTRACT_SYSTEM_PROMPT = """You are an expert HR assistant and career profile extractor.
Your task is to analyze the provided raw CV/Resume text (which was extracted from a PDF and may contain formatting artifacts, split lines, or messy columns) and extract a structured profile JSON strictly conforming to the JSON schema below.

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
    "pitch": "Brief 1-line professional pitch summarizing background and core stack (e.g. 'full stack engineer specializing in Python, FastAPI, and React')",
    "middles": {
      "data": "My background in data engineering and analytics — [mention candidate data tools] — matches this role, and I am eager to contribute, learn, and grow with your team.",
      "ai": "My background in AI and machine learning — [mention candidate AI tools] — matches this role, and I am eager to contribute, learn, and grow with your team.",
      "swe": "My background in software engineering — [mention candidate SWE stack] — matches this role, and I am eager to contribute, learn, and grow with your team.",
      "general": "My background in software engineering and technology matches this role, and I am eager to contribute, learn, and grow with your team."
    }
  }
}

INSTRUCTIONS & RULES:
1. Return ONLY a valid JSON object. Do not include introductory text, explanations, or wrapping markdown other than ```json if needed.
2. Clean up any OCR/PDF extraction anomalies (e.g. broken words, split lines, column interleaving).
3. Compute `years_experience` realistically based on work history dates (e.g., 0.5 for 6 months, 2.0 for 2 years). If entry level / student, use 0.5.
4. For `skills`, convert all skill `name` fields to lowercase (e.g. "python", "react", "postgresql", "docker"). Provide 1 to 4 useful search aliases for each skill.
5. In `letter.middles`, replace the bracketed placeholders with actual tools/skills found in the CV (e.g. "Python, SQL, and Pandas").
6. If salary is not explicitly mentioned in the CV, supply realistic defaults (e.g. preferred: 7000000, min_acceptable: 6000000, expectation: "6000000-7000000 IDR/month").
7. Ensure all fields in the schema are present. Do not use null for strings or lists; use empty strings "" or empty lists [] if completely unknown.
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


def _clean_json_response(raw_resp: str) -> dict[str, Any]:
    """Clean markdown code fences from LLM response and parse JSON."""
    cleaned = raw_resp.strip()
    # Strip markdown ```json ... ``` code fence
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    else:
        # Fallback to finding outermost { ... }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM did not return valid JSON: {e}\nRaw output:\n{raw_resp[:500]}") from e


def parse_cv_with_llm(cv_text: str, cfg: dict, filename: str = "CV.pdf") -> dict[str, Any]:
    """Parse CV text into structured profile data using configured LLM."""
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
        max_tokens=2500,
        temperature=0.1,
    )

    data = _clean_json_response(resp_text)
    if not isinstance(data, dict):
        raise ValueError("Extracted profile is not a JSON object.")

    # Always set cv_file to the actual uploaded filename
    if filename:
        data["cv_file"] = filename

    return data
