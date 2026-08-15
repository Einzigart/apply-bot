"""One-time import of application-log.md (129 rows) into SQLite.

Joins the 'Applications submitted' table with the 'Job links' section to
recover jobstreet IDs where possible (matched on normalized company name;
ties broken by title similarity — see the Vertika duplicate rows 15-16).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .db import insert_application, norm_company

TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
LINK = re.compile(
    r"-\s*\[(?P<label>.+?)\]\((?P<url>https://id\.jobstreet\.com/id/job/(?P<jsid>\d+))[^)]*\)")
# "- AI Engineer — Infomedia Nusantara (93961785): external ATS ..."
SKIPPED = re.compile(r"^-\s+(?P<label>.+?)\s+\((?P<jsid>\d+)\):\s+(?P<reason>.+)$", re.M)
LAST_UPDATED = re.compile(r"Last updated:\s*(\d{4}-\d{2}-\d{2})")


@dataclass
class MigrateStats:
    rows: int = 0
    imported: int = 0
    linked: int = 0
    unlinked: int = 0
    skipped_status: int = 0
    duplicate_ads: int = 0      # applications reusing an existing job row
    skipped_jobs: int = 0       # entries imported from "Skipped jobs (notable)"
    errors: list[str] = field(default_factory=list)


def parse_table(md: str) -> list[dict]:
    rows = []
    for line in md.splitlines():
        m = TABLE_ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not cells or not cells[0].isdigit():
            continue  # header / separator rows
        if len(cells) < 9:
            continue
        rows.append({
            "no": int(cells[0]),
            "date": cells[1],
            "company": cells[2],
            "role": cells[3],
            "location": cells[4],
            "salary": cells[5],
            "cv": cells[6].strip("`"),
            "app_status": cells[7],
            "response_status": cells[8],
        })
    return rows


def parse_links(md: str) -> dict[str, list[dict]]:
    """norm_company -> [{title, url, jobstreet_id}]"""
    links: dict[str, list[dict]] = {}
    for m in LINK.finditer(md):
        label = m.group("label")
        if " — " not in label:
            continue
        title, company = label.rsplit(" — ", 1)
        links.setdefault(norm_company(company), []).append({
            "title": title.strip(),
            "url": m.group("url"),
            "jobstreet_id": m.group("jsid"),
        })
    return links


def parse_skipped(md: str) -> list[dict]:
    """The '## Skipped jobs (notable)' bullet list:
    '- <Title> — <Company> (<jobstreet_id>): <reason>'"""
    out = []
    for m in SKIPPED.finditer(md):
        label = m.group("label")
        if " — " not in label:
            continue
        title, company = label.rsplit(" — ", 1)
        out.append({
            "title": title.strip(),
            "company": company.strip(),
            "jobstreet_id": m.group("jsid"),
            "reason": m.group("reason").strip(),
        })
    return out


def _match_link(row: dict, links: dict[str, list[dict]]) -> dict | None:
    candidates = links.get(norm_company(row["company"]), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    import difflib

    best = difflib.get_close_matches(
        row["role"], [c["title"] for c in candidates], n=1, cutoff=0.3)
    if best:
        return next(c for c in candidates if c["title"] == best[0])
    return None


def migrate(conn, md: str) -> MigrateStats:
    stats = MigrateStats()
    links = parse_links(md)
    for row in parse_table(md):
        stats.rows += 1
        if row["app_status"].lower() != "submitted":
            stats.skipped_status += 1
            continue
        link = _match_link(row, links)
        if link:
            stats.linked += 1
        else:
            stats.unlinked += 1
        try:
            job_id = None
            if link:
                existing = conn.execute(
                    "SELECT id FROM jobs WHERE jobstreet_id = ?",
                    (link["jobstreet_id"],),
                ).fetchone()
                if existing:
                    job_id = existing["id"]  # duplicate application to same ad
                    stats.duplicate_ads += 1
            if job_id is None:
                cur = conn.execute(
                    """INSERT INTO jobs
                       (jobstreet_id, url, title, company, company_norm, location,
                        salary_text, description, teaser, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        link["jobstreet_id"] if link else None,
                        link["url"] if link else None,
                        row["role"], row["company"], norm_company(row["company"]),
                        row["location"], None, None, None, row["date"], row["date"],
                    ),
                )
                job_id = cur.lastrowid
            insert_application(conn, job_id, {
                "applied_at": row["date"],
                "salary_entered": None if row["salary"] == "Not asked" else row["salary"],
                "confirmation": "legacy import (see application-log.md)",
                "status": row["app_status"],
            })
            stats.imported += 1
        except Exception as e:
            stats.errors.append(f"row {row['no']}: {e}")

    # "Skipped jobs (notable)" -> jobs + skip evaluations, so the bot never
    # re-considers known dead ends (external ATS, excessive experience, ...)
    from .db import insert_evaluation

    m = LAST_UPDATED.search(md)
    seen = m.group(1) if m else date.today().isoformat()
    for s in parse_skipped(md):
        try:
            row = conn.execute(
                "SELECT id FROM jobs WHERE jobstreet_id = ?", (s["jobstreet_id"],)
            ).fetchone()
            if row:
                job_id = row["id"]
            else:
                cur = conn.execute(
                    """INSERT INTO jobs
                       (jobstreet_id, url, title, company, company_norm, location,
                        salary_text, description, teaser, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        s["jobstreet_id"],
                        f"https://id.jobstreet.com/id/job/{s['jobstreet_id']}",
                        s["title"], s["company"], norm_company(s["company"]),
                        None, None, None, None, seen, seen,
                    ),
                )
                job_id = cur.lastrowid
            insert_evaluation(conn, job_id, {
                "model": "legacy-skip",
                "decision": "skip",
                "reason": s["reason"],
            })
            stats.skipped_jobs += 1
        except Exception as e:
            stats.errors.append(f"skipped {s['jobstreet_id']}: {e}")
    conn.commit()
    return stats
