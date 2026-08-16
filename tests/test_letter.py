"""Cover-letter rendering and saved-answer matching."""
from __future__ import annotations

from src.apply import answer_for
from src.db import add_answer, connect, list_answers
from src.letter import family_for, render

PROFILE = {
    "name": "Jane Candidate",
    "letter": {
        "pitch": "junior engineer",
        "middles": {
            "data": "Data middle.",
            "ai": "AI middle.",
            "swe": "SWE middle.",
            "general": "General middle.",
        },
    },
}


def test_render_uses_profile_name_and_family_middle():
    letter = render("Data Analyst", "PT Contoh", PROFILE)
    assert "Jane Candidate" in letter
    assert "PT Contoh" in letter


def test_render_falls_back_to_general_middle():
    letter = render("Quality Assurance", "PT Contoh", PROFILE)
    assert "General middle." in letter


def test_family_for():
    assert family_for("Junior Data Analyst") == "data"
    assert family_for("Machine Learning Engineer") == "ai"
    assert family_for("Backend Developer") == "swe"
    assert family_for("Account Executive") == "general"


def test_custom_instructions_cover_letter():
    from src.letter import render_llm
    from unittest import mock

    custom_profile = {
        "name": "Alex Designer",
        "skills": [{"name": "figma"}, {"name": "ui/ux"}],
        "experience": [{"role": "Product Designer", "org": "DesignHub", "period": "2022-2024", "summary": "Led design system"}],
        "letter": {
            "pitch": "Product Designer specializing in design systems and SaaS",
            "custom_instructions": "Focus on design systems and Figma expertise.",
        },
    }

    mock_generated = (
        "Dear Hiring Team,\n\n"
        "I am excited to apply for the Lead Product Designer role at PT Studio. "
        "With my background in scalable design systems and Figma at DesignHub, I can help elevate your product's user experience.\n\n"
        "Sincerely,\nAlex Designer"
    )

    with mock.patch("src.letter.complete", return_value=mock_generated) as mock_complete:
        cfg = {"llm": {"model": "gpt-4o-mini"}}
        letter = render_llm(
            "Lead Product Designer",
            "PT Studio",
            "Looking for senior Figma and design systems designer.",
            cfg,
            custom_profile,
        )

        assert "Alex Designer" in letter
        assert "PT Studio" in letter
        assert "scalable design systems" in letter
        # Verify custom instructions were passed in prompt
        called_messages = mock_complete.call_args[1]["messages"]
        system_content = called_messages[0]["content"]
        assert "Focus on design systems and Figma expertise." in system_content


def test_answers_roundtrip_from_db(tmp_path):
    conn = connect(tmp_path / "t.db")
    try:
        add_answer(conn, "expected salary|gaji", "7000000")
        add_answer(conn, "notice period", "Immediately")
        answers = list_answers(conn)
    finally:
        conn.close()
    assert answer_for("Berapa gaji yang Anda harapkan?", answers) == "7000000"
    assert answer_for("Notice period?", answers) == "Immediately"
    assert answer_for("Unrelated question", answers) is None
