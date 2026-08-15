"""Teaser parsing locked to real card texts captured from id.jobstreet.com
on 2026-08-15 (data-analyst-jobs/in-Jakarta)."""
from src.scrape import _guess_company, _guess_location, _guess_salary, _title_from_teaser

CARD_1 = ("Listed more than nineteen days ago\nData Analyst\ndi\nPT United Dico Citas\n\n"
          "Ini adalah lowongan kerja Full time\n\nJakarta Raya\nBergabunglah sebagai "
          "Data Analyst di PT United Dico Citas.")

CARD_2 = ("Listed more than nine days ago\nJunior Data Analyst\ndi\nPT YHS Indonesia\n\n"
          "Ini adalah lowongan kerja Full time\n\nJakarta Raya\nRp\xa06.500.000 – "
          "Rp\xa07.000.000 per month\nKandidat diharapkan mampu menganalisis data")

CARD_3 = ("Listed more than nine days ago\nData Analyst\ndi\nPT Ayo Indonesia Maju "
          "(ayo.co.id)\nDibutuhkan segera\n\nIni adalah lowongan kerja Full time\n\n"
          "Jakarta Pusat, Jakarta Raya(Hibrid)\nRp\xa012.000.000 – Rp\xa018.000.000 "
          "per month")


def test_title():
    assert _title_from_teaser(CARD_1) == "Data Analyst"
    assert _title_from_teaser(CARD_2) == "Junior Data Analyst"


def test_company():
    assert _guess_company(CARD_1) == "PT United Dico Citas"
    assert _guess_company(CARD_3) == "PT Ayo Indonesia Maju (ayo.co.id)"


def test_location():
    assert _guess_location(CARD_1, {}) == "Jakarta Raya"
    assert _guess_location(CARD_3, {}) == "Jakarta Pusat, Jakarta Raya(Hibrid)"


def test_location_not_confused_by_company_name():
    assert _guess_location(CARD_2, {}) == "Jakarta Raya"  # not "PT YHS Indonesia"


def test_salary():
    assert _guess_salary(CARD_1) is None
    assert "7.000.000" in _guess_salary(CARD_2)
