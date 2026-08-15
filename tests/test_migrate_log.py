import sqlite3

from src.db import SCHEMA, company_in_cooldown, norm_company
from src.migrate_log import migrate, parse_links, parse_table

FIXTURE = """# Jobstreet Application Log

## Applications submitted

| No. | Date | Company | Role | Location | Salary entered | CV | Application status | Response status |
|---:|---|---|---|---|---:|---|---|---|
| 1 | 2026-08-02 | PT Indostar Security | AI Application Engineer | Kelapa Gading, Jakarta Raya | IDR 7,000,000/month | `CV.pdf` | Submitted | Pending response |
| 15 | 2026-08-02 | PT Vertika Technologies Nusantara | Software Engineer Backend Intern | Jakarta Raya (Hybrid) | IDR 7,000,000/month | `CV.pdf` | Submitted | Pending response |
| 16 | 2026-08-02 | PT Vertika Technologies Nusantara | Software Engineer Web/Frontend Intern | Jakarta Raya (Hybrid) | IDR 7,000,000/month | `CV.pdf` | Submitted | Pending response |
| 17 | 2026-08-03 | Mystery Co | Data Analyst | Jakarta | IDR 6,000,000/month | `CV.pdf` | Submitted | Pending response |
| 76 | 2026-08-08 | Firstwish Bakery | IT - Junior Back-End Developer | Jakarta Utara | IDR 7,000,000/month | `CV.pdf` | Submitted | Pending response |
| 77 | 2026-08-09 | Firstwish Bakery | IT - Junior Back-End Developer | Jakarta Utara | IDR 7,000,000/month | `CV.pdf` | Submitted | Pending response |

## Job links

- [AI Application Engineer — PT Indostar Security](https://id.jobstreet.com/id/job/93690903)
- [Software Engineer Backend Intern — PT Vertika Technologies Nusantara](https://id.jobstreet.com/id/job/93513186)
- [Software Engineer Web/Frontend Intern — PT Vertika Technologies Nusantara](https://id.jobstreet.com/id/job/93513381)
- [IT - Junior Back-End Developer — Firstwish Bakery](https://id.jobstreet.com/id/job/93491888)

## Skipped jobs (notable)

- AI Engineer — Infomedia Nusantara (93961785): external ATS (recruit.infomedia.co.id) requires separate account.
- Data Analyst — Erajaya Group (93970820): external ATS (career.erajaya.com).
"""


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def test_parse_table():
    rows = parse_table(FIXTURE)
    assert len(rows) == 6
    assert rows[0]["company"] == "PT Indostar Security"
    assert rows[0]["date"] == "2026-08-02"


def test_parse_links():
    links = parse_links(FIXTURE)
    assert norm_company("PT Indostar Security") in links
    assert len(links[norm_company("PT Vertika Technologies Nusantara")]) == 2


def test_migrate_links_and_duplicates():
    conn = _conn()
    stats = migrate(conn, FIXTURE)
    assert stats.rows == 6
    assert stats.imported == 6
    assert stats.linked == 5          # Vertika x2 + Indostar + Firstwish x2
    assert stats.unlinked == 1        # Mystery Co has no link
    assert stats.duplicate_ads == 1   # Firstwish rows 76/77 share one job ad

    apps = conn.execute(
        "SELECT COUNT(*) c FROM applications").fetchone()["c"]
    assert apps == 6  # duplicates are preserved as history

    linked = conn.execute(
        "SELECT COUNT(*) c FROM jobs WHERE jobstreet_id IS NOT NULL").fetchone()["c"]
    assert linked == 4 + 2  # 4 distinct applied ads + 2 skipped-job ads


def test_skipped_jobs_imported_as_skip_evaluations():
    from src.migrate_log import parse_skipped

    entries = parse_skipped(FIXTURE)
    assert len(entries) == 2
    assert entries[0]["company"] == "Infomedia Nusantara"
    assert entries[0]["jobstreet_id"] == "93961785"

    conn = _conn()
    stats = migrate(conn, FIXTURE)
    assert stats.skipped_jobs == 2
    row = conn.execute(
        """SELECT e.decision, e.reason FROM jobs j
           JOIN evaluations e ON e.job_id = j.id
           WHERE j.jobstreet_id = '93961785'""").fetchone()
    assert row["decision"] == "skip"
    assert "external ATS" in row["reason"]


def test_cooldown_uses_imported_history():
    conn = _conn()
    migrate(conn, FIXTURE)
    assert company_in_cooldown(conn, norm_company("PT. Indostar Security"),
                               days=365)  # long window: seen
    assert not company_in_cooldown(conn, norm_company("PT. Indostar Security"),
                                   days=1)  # short window: not recent
    assert not company_in_cooldown(conn, norm_company("Never Applied Ltd"),
                                   days=365)


def test_norm_company():
    assert norm_company("PT. Wide Technologies Indonesia") == "wide technologies indonesia"
    assert norm_company("PT Bina Usaha Raya (UMKMall)") == "bina usaha raya"
    assert norm_company("") == ""
