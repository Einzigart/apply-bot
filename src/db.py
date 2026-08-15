"""SQLite storage. jobs.db is the source of truth for dedup and history."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id            INTEGER PRIMARY KEY,
  jobstreet_id  TEXT UNIQUE,              -- NULL only for legacy imports
  url           TEXT,
  title         TEXT,
  company       TEXT,
  company_norm  TEXT,
  location      TEXT,
  salary_text   TEXT,
  description   TEXT,
  teaser        TEXT,
  first_seen    TEXT NOT NULL,
  last_seen     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
  id              INTEGER PRIMARY KEY,
  job_id          INTEGER NOT NULL REFERENCES jobs(id),
  scored_at       TEXT NOT NULL,
  model           TEXT NOT NULL,          -- 'rules-v1' for deterministic gates
  match_pct       INTEGER,
  years_required  INTEGER,
  seniority       TEXT,
  met             TEXT,                   -- JSON array
  unmet           TEXT,                   -- JSON array
  decision        TEXT NOT NULL,          -- apply | review | skip
  reason          TEXT
);
CREATE INDEX IF NOT EXISTS idx_eval_job ON evaluations(job_id);

CREATE TABLE IF NOT EXISTS applications (
  id            INTEGER PRIMARY KEY,
  job_id        INTEGER NOT NULL REFERENCES jobs(id),
  -- NOTE: no UNIQUE(job_id) — the legacy log contains genuine duplicate
  -- applications and history must import faithfully. Runtime dedup is
  -- enforced by job_already_applied()/company_in_cooldown() queries.
  applied_at    TEXT NOT NULL,
  salary_entered TEXT,
  cover_letter  TEXT,
  confirmation  TEXT,
  status        TEXT NOT NULL DEFAULT 'Submitted'
);

CREATE TABLE IF NOT EXISTS runs (
  id          INTEGER PRIMARY KEY,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  command     TEXT,
  notes       TEXT
);
"""

_COMPANY_NOISE = re.compile(r"\b(pt|tbk|co|ltd|inc|llc|cv|ud|tbk)\b", re.I)


def norm_company(name: str | None) -> str:
    """Normalize a company name for dedup, e.g.
    'PT. Wide Technologies Indonesia' -> 'wide technologies indonesia'."""
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r"\(.*?\)", " ", n)          # drop parentheticals like (UMKMall)
    n = re.sub(r"[.,/\-&]", " ", n)
    n = _COMPANY_NOISE.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def norm_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# --- jobs -----------------------------------------------------------------

def upsert_job(conn: sqlite3.Connection, job: dict) -> int:
    today = date.today().isoformat()
    job = dict(job)
    job.setdefault("company_norm", norm_company(job.get("company")))
    js_id = job.get("jobstreet_id")
    if js_id:
        row = conn.execute(
            "SELECT id FROM jobs WHERE jobstreet_id = ?", (js_id,)
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE jobs SET last_seen = ?,
                   title       = COALESCE(?, title),
                   company     = COALESCE(?, company),
                   company_norm= COALESCE(?, company_norm),
                   location    = COALESCE(?, location),
                   salary_text = COALESCE(?, salary_text),
                   description = COALESCE(?, description),
                   teaser      = COALESCE(?, teaser),
                   url         = COALESCE(?, url)
                 WHERE id = ?""",
                (
                    today,
                    job.get("title"), job.get("company"), job.get("company_norm"),
                    job.get("location"), job.get("salary_text"),
                    job.get("description"), job.get("teaser"), job.get("url"),
                    row["id"],
                ),
            )
            conn.commit()
            return row["id"]
    cur = conn.execute(
        """INSERT INTO jobs
           (jobstreet_id, url, title, company, company_norm, location,
            salary_text, description, teaser, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            js_id, job.get("url"), job.get("title"), job.get("company"),
            job.get("company_norm"), job.get("location"), job.get("salary_text"),
            job.get("description"), job.get("teaser"), today, today,
        ),
    )
    conn.commit()
    return cur.lastrowid


def find_job(conn: sqlite3.Connection, jobstreet_id: str):
    return conn.execute(
        "SELECT * FROM jobs WHERE jobstreet_id = ?", (jobstreet_id,)
    ).fetchone()


def jobs_without_details(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT * FROM jobs WHERE description IS NULL AND jobstreet_id IS NOT NULL"
    ).fetchall()


def jobs_without_evaluation(conn: sqlite3.Connection):
    return conn.execute(
        """SELECT j.* FROM jobs j
           WHERE NOT EXISTS (SELECT 1 FROM evaluations e WHERE e.job_id = j.id)
             AND j.title IS NOT NULL"""
    ).fetchall()


# --- evaluations ------------------------------------------------------------

def insert_evaluation(conn: sqlite3.Connection, job_id: int, ev: dict) -> None:
    conn.execute(
        """INSERT INTO evaluations
           (job_id, scored_at, model, match_pct, years_required, seniority,
            met, unmet, decision, reason)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            job_id,
            datetime.now().isoformat(timespec="seconds"),
            ev.get("model", "unknown"),
            ev.get("match_pct"),
            ev.get("years_required"),
            ev.get("seniority"),
            ev.get("met"),      # JSON strings
            ev.get("unmet"),
            ev["decision"],
            ev.get("reason"),
        ),
    )
    conn.commit()


def latest_evaluations(conn: sqlite3.Connection, decision: str | None = None):
    q = """SELECT j.title, j.company, j.location, j.url, e.*
           FROM evaluations e
           JOIN jobs j ON j.id = e.job_id
           WHERE e.id = (SELECT MAX(id) FROM evaluations WHERE job_id = e.job_id)"""
    if decision:
        q += " AND e.decision = ?"
        return conn.execute(q + " ORDER BY e.match_pct DESC", (decision,)).fetchall()
    return conn.execute(q + " ORDER BY e.scored_at DESC").fetchall()


def record_decision(conn: sqlite3.Connection, jobstreet_id: str,
                    decision: str, reason: str | None = None) -> bool:
    """Record a human review verdict as the job's latest evaluation.

    Evaluations are append-only, so the newest row wins in
    latest_evaluations()/approved_unapplied(). Returns False if the job
    is unknown.
    """
    job = find_job(conn, jobstreet_id)
    if job is None:
        return False
    insert_evaluation(conn, job["id"], {
        "model": "human",
        "decision": decision,
        "reason": reason or "manual review",
    })
    return True


# --- applications -----------------------------------------------------------

def company_in_cooldown(
    conn: sqlite3.Connection, company_norm: str, days: int, today: date | None = None
) -> bool:
    """True if this company already has an application within `days`."""
    if not company_norm:
        return False
    today = today or date.today()
    cutoff = (today - timedelta(days=days)).isoformat()
    row = conn.execute(
        """SELECT 1 FROM applications a
           JOIN jobs j ON j.id = a.job_id
           WHERE j.company_norm = ? AND a.applied_at >= ?
           LIMIT 1""",
        (company_norm, cutoff),
    ).fetchone()
    return row is not None


def job_already_applied(conn: sqlite3.Connection, jobstreet_id: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM applications a
           JOIN jobs j ON j.id = a.job_id
           WHERE j.jobstreet_id = ? LIMIT 1""",
        (jobstreet_id,),
    ).fetchone()
    return row is not None


def insert_application(conn: sqlite3.Connection, job_id: int, app: dict) -> None:
    conn.execute(
        """INSERT INTO applications
           (job_id, applied_at, salary_entered, cover_letter, confirmation, status)
           VALUES (?,?,?,?,?,?)""",
        (
            job_id,
            app["applied_at"],
            app.get("salary_entered"),
            app.get("cover_letter"),
            app.get("confirmation"),
            app.get("status", "Submitted"),
        ),
    )
    conn.commit()


def approved_unapplied(conn: sqlite3.Connection):
    """Jobs whose latest evaluation says 'apply' and that have no application."""
    return conn.execute(
        """SELECT j.*, e.match_pct, e.reason FROM jobs j
           JOIN evaluations e ON e.job_id = j.id
           WHERE e.id = (SELECT MAX(id) FROM evaluations WHERE job_id = j.id)
             AND e.decision = 'apply'
             AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id)
           ORDER BY e.match_pct DESC"""
    ).fetchall()
