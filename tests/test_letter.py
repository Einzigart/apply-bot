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
    assert "Data middle." in letter
    assert "Data Analyst" in letter and "PT Contoh" in letter


def test_render_falls_back_to_general_middle():
    letter = render("Quality Assurance", "PT Contoh", PROFILE)
    assert "General middle." in letter


def test_family_for():
    assert family_for("Junior Data Analyst") == "data"
    assert family_for("Machine Learning Engineer") == "ai"
    assert family_for("Backend Developer") == "swe"
    assert family_for("Account Executive") == "general"


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
