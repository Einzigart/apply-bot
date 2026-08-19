"""Tests for CV PDF extraction and LLM parser."""
from __future__ import annotations

import io
import json
import pytest
import pypdf

from src.cv_parser import (
    _clean_json_response,
    extract_text_from_pdf,
    parse_cv_with_llm,
)


def _create_dummy_pdf(text: str = "Jane Doe\nSoftware Engineer\nPython, FastAPI, SQL") -> bytes:
    writer = pypdf.PdfWriter()
    # Create a blank page and add annotation/text or create page with text
    page = writer.add_blank_page(width=612, height=792)
    # pypdf Writer can create a minimal valid PDF stream
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_clean_json_response():
    # Markdown code fence json
    raw = """```json
    {
      "name": "Jane Doe",
      "years_experience": 2
    }
    ```"""
    data = _clean_json_response(raw)
    assert data["name"] == "Jane Doe"
    assert data["years_experience"] == 2

    # Plain text json with preamble
    raw2 = """Here is the extracted json:
    {"name": "John Smith", "location": "Jakarta"}
    Hope this helps!"""
    data2 = _clean_json_response(raw2)
    assert data2["name"] == "John Smith"
    assert data2["location"] == "Jakarta"

    # JSON with trailing commas and comments
    raw3 = """```json
    {
      // Candidate info
      "name": "Alice",
      "skills": ["python", "docker",],
    }
    ```"""
    data3 = _clean_json_response(raw3)
    assert data3["name"] == "Alice"
    assert data3["skills"] == ["python", "docker"]

    # Truncated JSON auto-repair
    raw4 = '{"name": "Bob", "skills": ["python", "fastapi"], "education": {"degree": "B.Sc.'
    data4 = _clean_json_response(raw4)
    assert data4["name"] == "Bob"
    assert data4["skills"] == ["python", "fastapi"]


def test_clean_json_response_invalid():
    with pytest.raises(ValueError, match="LLM did not return valid JSON|empty response"):
        _clean_json_response("This is not json at all with nothing salvageable.")


def test_extract_text_empty():
    with pytest.raises(ValueError, match="Empty PDF payload"):
        extract_text_from_pdf(b"")

    # Empty pages PDF
    writer = pypdf.PdfWriter()
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(ValueError, match="PDF contains no pages"):
        extract_text_from_pdf(buf.getvalue())

    # PDF with pages but unextractable/empty text
    blank_pdf = _create_dummy_pdf()
    with pytest.raises(ValueError, match="Could not extract any text"):
        extract_text_from_pdf(blank_pdf)


def test_clean_json_response_not_dict(monkeypatch):
    monkeypatch.setattr("src.cv_parser.complete", lambda messages, cfg, **kw: "[\"item1\", \"item2\"]")
    with pytest.raises(ValueError, match="Extracted profile is not a JSON object"):
        parse_cv_with_llm("CV text", cfg={}, filename="test.pdf")


def test_parse_cv_with_llm_mock(monkeypatch):
    mock_resp = json.dumps({
        "name": "M Farid Hakim",
        "location": "Jakarta, Indonesia",
        "work_rights": "Citizen",
        "cv_file": "my_cv.pdf",
        "years_experience": 2.5,
        "languages": ["Indonesian", "English"],
        "locations_ok": ["Jakarta", "Remote"],
        "education": {
            "degree": "B.Sc. Computer Science",
            "university": "University of Indonesia",
            "period": "2020-2024",
            "gpa": "3.80/4.00",
            "certifications": ["AWS Certified Cloud Practitioner"],
        },
        "experience": [
            {
                "role": "Full Stack Engineer",
                "org": "Tech Startup",
                "period": "2023-Present",
                "summary": "Built FastAPI backend and React frontend.",
            }
        ],
        "skills": [
            {"name": "python", "aliases": ["python3", "py"]},
            {"name": "fastapi", "aliases": ["fast-api"]},
        ],
        "projects": [
            "Apply Bot — Job automation tool (Python, FastAPI, Playwright)"
        ],
        "salary": {"preferred": 12000000, "min_acceptable": 10000000},
        "salary_expectation": "10000000-12000000 IDR/month",
        "letter": {
            "pitch": "full stack engineer with Python and React",
            "middles": {
                "data": "My data background in Python and SQL matches this role.",
                "ai": "My AI background in Python matches this role.",
                "swe": "My SWE background in Python and FastAPI matches this role.",
                "general": "My background matches this role.",
            },
        },
    })

    monkeypatch.setattr("src.cv_parser.complete", lambda messages, cfg, **kw: mock_resp)

    cfg = {"llm": {"provider": "openai", "api_key": "test-key"}}
    result = parse_cv_with_llm("CV text content", cfg=cfg, filename="Farid_CV.pdf")

    assert result["name"] == "M Farid Hakim"
    assert result["years_experience"] == 2.5
    assert len(result["skills"]) == 2
    assert result["cv_file"] == "Farid_CV.pdf"


def test_parse_cv_with_llm_low_tier_model_normalization(monkeypatch):
    # Mock messy/flat response from small/local LLM
    mock_resp = """Here is the result:
    {
        "name": "Akhdan Khairu Nabiha",
        "location": "Jakarta, Indonesia",
        "work_rights": "Authorized in Indonesia",
        "years_experience": "1.5",
        "languages": ["Indonesian", "English"],
        "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
        "education": "Sarjana Terapan (D4) Teknik Informatika",
        "experience": [
            {"role": "Backend Engineer", "company": "Tech Corp", "period": "2023-present"}
        ],
        "salary": {"preferred": "8000000"}
    }
    """
    monkeypatch.setattr("src.cv_parser.complete", lambda messages, cfg, **kw: mock_resp)

    cfg = {"llm": {"provider": "openai", "api_key": "test-key"}}
    result = parse_cv_with_llm("CV raw text", cfg=cfg, filename="CV_Akhdan.pdf")

    assert result["name"] == "Akhdan Khairu Nabiha"
    assert result["years_experience"] == 1.5
    assert result["cv_file"] == "CV_Akhdan.pdf"
    # Skills normalized to object format
    assert result["skills"][0]["name"] == "python"
    assert result["skills"][0]["aliases"] == ["python"]
    # Education normalized
    assert result["education"]["degree"] == "Sarjana Terapan (D4) Teknik Informatika"
    # Predicted config auto-generated
    assert "predicted_config" in result
    assert result["predicted_config"]["target_roles"][0]["name"] == "Backend Engineer"
