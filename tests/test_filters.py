import pytest

from src.filters import location_ok, parse_years_required, title_check

CFG = {
    "filters": {
        "title_blacklist": ["intern", "internship", "magang", "senior", "sr.",
                            "lead", "supervisor", "manager", "head of", "principal"],
        "role_keywords": ["data", "analyst", "software", "developer", "programmer",
                          "engineer", "ai engineer"],
        "location_whitelist": ["jakarta", "tangerang", "remote"],
        "max_years_experience": 1,
        "company_cooldown_days": 28,
    }
}


@pytest.mark.parametrize("title", [
    "Senior Data Analyst",
    "Data Analyst Intern",
    "Magang Data Science",
    "Lead Software Engineer",
    "Engineering Manager",
    "Sr. Backend Developer",
    "Principal AI Engineer",
])
def test_blacklisted_titles(title):
    ok, reason = title_check(title, CFG)
    assert not ok, title
    assert "blacklist" in reason


@pytest.mark.parametrize("title", [
    "Data Analyst",
    "Junior Software Engineer",
    "AI Engineer",
    "Full Stack Developer",
    "PROGRAMMER",
    "Fresh Graduate Data Scientist",
])
def test_allowed_titles(title):
    ok, reason = title_check(title, CFG)
    assert ok, f"{title}: {reason}"


def test_internal_audit_not_an_intern_false_positive():
    # word boundaries: "Internal" must not trigger the "intern" rule
    ok, _ = title_check("Internal Audit Data Staff", CFG)
    assert ok


def test_irrelevant_title_rejected():
    ok, reason = title_check("Accounting Staff", CFG)
    assert not ok
    assert "keyword" in reason


@pytest.mark.parametrize("text,expected", [
    ("Minimal 2 tahun pengalaman", 2),
    ("Minimum 3 years of experience", 3),
    ("0-1 years experience", 1),
    ("1-3 tahun pengalaman", 3),
    ("pengalaman kerja 1 tahun", 1),
    ("5+ years experience required", 5),
    ("Fresh graduates are welcome to apply", 0),
    ("Lulusan baru dipersilakan melamar", 0),
    ("Bachelor degree in Computer Science", None),
    # age requirements are not experience (real ad text, 2026-08-15)
    ("Usia 23-30 tahun Minimal pengalaman 1 tahun", 1),
    ("Berusia maksimal 30 tahun", None),
    ("Persyaratan: Usia 25 - 28 tahun, pendidikan min. D3", None),
])
def test_parse_years(text, expected):
    assert parse_years_required(text) == expected


@pytest.mark.parametrize("loc,ok", [
    ("Jakarta Raya", True),
    ("Tangerang, Banten", True),
    ("Tangerang Selatan", True),
    ("Remote", True),
    ("Jakarta Selatan, Jakarta Raya", True),
    ("Surabaya, Jawa Timur", False),
    ("Singapore", False),
    (None, True),  # unknown -> not filtered here
])
def test_location(loc, ok):
    assert location_ok(loc, CFG) == ok
