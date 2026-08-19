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
  is_external   INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS answers (
  id         INTEGER PRIMARY KEY,
  match      TEXT NOT NULL,   -- case-insensitive regex vs the question label
  answer     TEXT NOT NULL,
  created_at TEXT NOT NULL
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
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Run lightweight schema migrations for existing databases."""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
    if cols and "is_external" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN is_external INTEGER NOT NULL DEFAULT 0")
        conn.commit()


# --- jobs -----------------------------------------------------------------

def upsert_job(conn: sqlite3.Connection, job: dict) -> int:
    today = date.today().isoformat()
    job = dict(job)

    # Coerce any structured fields to string/None so sqlite3 never fails on dict/list
    for k in ("title", "company", "location", "salary_text", "description", "teaser", "url"):
        val = job.get(k)
        if isinstance(val, dict):
            job[k] = val.get("label") or val.get("text") or str(val)
        elif isinstance(val, list):
            job[k] = ", ".join(str(x.get("label") if isinstance(x, dict) else x) for x in val)
        elif val is not None:
            job[k] = str(val)

    job.setdefault("company_norm", norm_company(job.get("company")))
    is_ext = 1 if job.get("is_external") else 0
    js_id = str(job.get("jobstreet_id")) if job.get("jobstreet_id") is not None else None
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
                   url         = COALESCE(?, url),
                   is_external = COALESCE(?, is_external)
                 WHERE id = ?""",
                (
                    today,
                    job.get("title"), job.get("company"), job.get("company_norm"),
                    job.get("location"), job.get("salary_text"),
                    job.get("description"), job.get("teaser"), job.get("url"),
                    is_ext,
                    row["id"],
                ),
            )
            conn.commit()
            return row["id"]
    cur = conn.execute(
        """INSERT INTO jobs
           (jobstreet_id, url, title, company, company_norm, location,
            salary_text, description, teaser, is_external, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            js_id, job.get("url"), job.get("title"), job.get("company"),
            job.get("company_norm"), job.get("location"), job.get("salary_text"),
            job.get("description"), job.get("teaser"), is_ext, today, today,
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


def job_has_evaluation(conn: sqlite3.Connection, job_id: int) -> bool:
    """True if at least one evaluation exists for this job."""
    row = conn.execute(
        "SELECT 1 FROM evaluations WHERE job_id = ? LIMIT 1",
        (job_id,),
    ).fetchone()
    return row is not None


def record_decision(conn: sqlite3.Connection, jobstreet_id: str | int,
                    decision: str, reason: str | None = None) -> bool:
    """Record a human review verdict as the job's latest evaluation.

    Evaluations are append-only, so the newest row wins in
    latest_evaluations()/approved_unapplied(). Returns False if the job
    is unknown. Supports both jobstreet_id string and internal numeric id.
    """
    job = find_job(conn, str(jobstreet_id))
    if not job and str(jobstreet_id).isdigit():
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (int(jobstreet_id),)).fetchone()
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
    """True if this company already has an application within `days`.
    If days <= 0, cooldown is disabled (returns False)."""
    if not company_norm or days <= 0:
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
    """Jobs whose latest evaluation says 'apply' and that have no application, excluding external apply jobs."""
    return conn.execute(
        """SELECT j.*, e.match_pct, e.reason FROM jobs j
           JOIN evaluations e ON e.job_id = j.id
           WHERE e.id = (SELECT MAX(id) FROM evaluations WHERE job_id = j.id)
             AND e.decision = 'apply'
             AND j.is_external = 0
             AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id)
           ORDER BY e.match_pct DESC"""
    ).fetchall()


# --- saved answers ----------------------------------------------------------
# Employer-question answers live here (not in a tracked file): they hold
# personal data, and the applier appends new ones at apply time.

def list_answers(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT id, match, answer FROM answers ORDER BY id"
    ).fetchall()


def add_answer(conn: sqlite3.Connection, match: str, answer: str) -> int:
    cur = conn.execute(
        "INSERT INTO answers (match, answer, created_at) VALUES (?,?,?)",
        (match, str(answer), datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return cur.lastrowid


# --- runs -------------------------------------------------------------------

def start_run(conn: sqlite3.Connection, command: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (started_at, command) VALUES (?,?)",
        (datetime.now().isoformat(timespec="seconds"), command),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, notes: str | None = None) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, notes = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), notes, run_id),
    )
    conn.commit()


def finish_run_if_open(conn: sqlite3.Connection, run_id: int, notes: str) -> bool:
    """Stamp a run closed only if it is still open.

    Safe against the race where the CLI subprocess finishes (and stamps
    its own row) between a caller's read and this write."""
    cur = conn.execute(
        """UPDATE runs SET finished_at = ?, notes = ?
           WHERE id = ? AND finished_at IS NULL""",
        (datetime.now().isoformat(timespec="seconds"), notes, run_id),
    )
    conn.commit()
    return cur.rowcount == 1


def mark_interrupted_runs(conn: sqlite3.Connection) -> int:
    """Runs still open when a (web) process starts were killed with the last
    process — stamp them so they don't look alive forever."""
    cur = conn.execute(
        """UPDATE runs SET finished_at = ?, notes = 'interrupted (process exit)'
           WHERE finished_at IS NULL""",
        (datetime.now().isoformat(timespec="seconds"),),
    )
    conn.commit()
    return cur.rowcount


def list_runs(
    conn: sqlite3.Connection,
    limit: int = 100,
    sort: str | None = None,
    order: str | None = None,
):
    sort_cols = {
        "id": "id",
        "command": "command",
        "started_at": "started_at",
        "finished_at": "finished_at",
        "notes": "notes",
    }
    col = sort_cols.get(sort or "")
    direction = "ASC" if (order or "").lower() == "asc" else "DESC"

    if col:
        if col == "finished_at":
            sql = f"SELECT * FROM runs ORDER BY {col} IS NULL, {col} {direction}, id DESC LIMIT ?"
        else:
            sql = f"SELECT * FROM runs ORDER BY {col} {direction}, id DESC LIMIT ?"
    else:
        sql = "SELECT * FROM runs ORDER BY id DESC LIMIT ?"

    return conn.execute(sql, (limit,)).fetchall()


def get_run(conn: sqlite3.Connection, run_id: int):
    return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


# --- API / Query helpers ------------------------------------------------------

def jobs_with_latest_eval(conn: sqlite3.Connection, decision: str | None = None,
                          q: str | None = None, is_external: bool | int | None = None,
                          sort: str | None = None, order: str | None = None,
                          limit: int = 50, offset: int = 0):
    sql = """SELECT j.*, e.decision, e.match_pct, e.model, e.reason, e.scored_at,
                    (SELECT id FROM applications WHERE job_id = j.id LIMIT 1) AS application_id
             FROM jobs j
             LEFT JOIN evaluations e ON e.job_id = j.id
               AND e.id = (SELECT MAX(id) FROM evaluations WHERE job_id = j.id)
             WHERE 1=1"""
    params: list = []
    if decision == "unevaluated":
        sql += " AND e.decision IS NULL"
    elif decision:
        sql += " AND e.decision = ?"
        params.append(decision)
    if q:
        sql += " AND (j.title LIKE ? OR j.company LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if is_external is not None:
        sql += " AND j.is_external = ?"
        params.append(1 if is_external else 0)

    sort_cols = {
        "title": "j.title",
        "company": "j.company",
        "location": "j.location",
        "decision": "e.decision",
        "match": "e.match_pct",
        "model": "e.model",
        "last_seen": "j.last_seen",
    }
    col = sort_cols.get(sort or "")
    direction = "ASC" if (order or "").lower() == "asc" else "DESC"

    if col:
        if col == "e.match_pct":
            # For match percentage, sort nulls last
            sql += f" ORDER BY {col} IS NULL, {col} {direction}, j.id DESC LIMIT ? OFFSET ?"
        else:
            sql += f" ORDER BY {col} {direction}, j.id DESC LIMIT ? OFFSET ?"
    else:
        sql += " ORDER BY j.last_seen DESC, j.id DESC LIMIT ? OFFSET ?"

    params += [limit, offset]
    return conn.execute(sql, params).fetchall()


def count_jobs_filtered(conn: sqlite3.Connection, decision: str | None = None,
                        q: str | None = None, is_external: bool | int | None = None) -> int:
    sql = """SELECT COUNT(*) c
             FROM jobs j
             LEFT JOIN evaluations e ON e.job_id = j.id
               AND e.id = (SELECT MAX(id) FROM evaluations WHERE job_id = j.id)
             WHERE 1=1"""
    params: list = []
    if decision == "unevaluated":
        sql += " AND e.decision IS NULL"
    elif decision:
        sql += " AND e.decision = ?"
        params.append(decision)
    if q:
        sql += " AND (j.title LIKE ? OR j.company LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if is_external is not None:
        sql += " AND j.is_external = ?"
        params.append(1 if is_external else 0)
    return conn.execute(sql, params).fetchone()["c"]


def count_jobs(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]


def decision_counts(conn: sqlite3.Connection):
    """Latest decision per job, grouped — the dashboard headline numbers."""
    return conn.execute(
        """SELECT e.decision, COUNT(*) c FROM evaluations e
           WHERE e.id = (SELECT MAX(id) FROM evaluations WHERE job_id = e.job_id)
           GROUP BY e.decision"""
    ).fetchall()


def list_applications(
    conn: sqlite3.Connection,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
):
    where = []
    params: list = []

    if status:
        where.append("LOWER(a.status) = LOWER(?)")
        params.append(status)

    if q:
        where.append("(j.title LIKE ? OR j.company LIKE ? OR j.location LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sort_cols = {
        "applied_at": "a.applied_at",
        "title": "j.title",
        "company": "j.company",
        "location": "j.location",
        "salary_entered": "a.salary_entered",
        "status": "a.status",
    }
    col = sort_cols.get(sort or "")
    direction = "ASC" if (order or "").lower() == "asc" else "DESC"

    if col:
        order_sql = f"ORDER BY {col} {direction}, a.id DESC"
    else:
        order_sql = "ORDER BY a.applied_at DESC, a.id DESC"

    sql = f"""SELECT a.*, j.title, j.company, j.location, j.url
              FROM applications a JOIN jobs j ON j.id = a.job_id
              {where_sql}
              {order_sql} LIMIT ? OFFSET ?"""

    params.extend([limit, offset])
    return conn.execute(sql, params).fetchall()


def count_applications(
    conn: sqlite3.Connection,
    status: str | None = None,
    q: str | None = None,
) -> int:
    where = []
    params: list = []

    if status:
        where.append("LOWER(a.status) = LOWER(?)")
        params.append(status)

    if q:
        where.append("(j.title LIKE ? OR j.company LIKE ? OR j.location LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""SELECT COUNT(*) c FROM applications a JOIN jobs j ON j.id = a.job_id {where_sql}"""
    return conn.execute(sql, params).fetchone()["c"]


def update_application_status(conn: sqlite3.Connection, app_id: int, status: str) -> bool:
    cur = conn.execute(
        "UPDATE applications SET status = ? WHERE id = ?",
        (status, app_id),
    )
    conn.commit()
    return cur.rowcount > 0


def mark_job_applied(
    conn: sqlite3.Connection,
    job_identifier: str | int,
    applied_at: str | None = None,
    status: str = "Submitted",
    salary_entered: str | None = None,
) -> int | None:
    """Mark a job as applied by creating an application entry.

    `job_identifier` can be either jobstreet_id or numeric internal id.
    """
    job = find_job(conn, str(job_identifier))
    if not job and str(job_identifier).isdigit():
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (int(job_identifier),)).fetchone()

    if not job:
        return None

    job_id = job["id"]
    today = date.today().isoformat()
    app_date = applied_at or today

    existing = conn.execute(
        "SELECT id FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()

    if existing:
        return existing["id"]

    cur = conn.execute(
        """INSERT INTO applications (job_id, applied_at, status, salary_entered)
           VALUES (?, ?, ?, ?)""",
        (job_id, app_date, status, salary_entered),
    )
    app_id = cur.lastrowid

    # Also ensure a positive human evaluation is recorded
    insert_evaluation(
        conn,
        job_id,
        {
            "model": "human",
            "decision": "apply",
            "reason": "marked applied via UI",
        },
    )
    conn.commit()
    return app_id


def delete_application(conn: sqlite3.Connection, app_id: int) -> bool:
    """Delete an application by ID."""
    cur = conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    return cur.rowcount > 0


def get_application(conn: sqlite3.Connection, app_id: int):
    """Fetch a single application with joined job details."""
    sql = """SELECT a.*, j.title, j.company, j.location, j.url
             FROM applications a JOIN jobs j ON j.id = a.job_id
             WHERE a.id = ?"""
    return conn.execute(sql, (app_id,)).fetchone()


def find_application_by_job_details(
    conn: sqlite3.Connection, title: str, company: str, url: str
):
    """Find an existing application matching role, company, and url (case-insensitive)."""
    sql = """SELECT a.id FROM applications a
             JOIN jobs j ON j.id = a.job_id
             WHERE LOWER(TRIM(COALESCE(j.title, ''))) = LOWER(TRIM(?))
               AND LOWER(TRIM(COALESCE(j.company, ''))) = LOWER(TRIM(?))
               AND LOWER(TRIM(COALESCE(j.url, ''))) = LOWER(TRIM(?))
             LIMIT 1"""
    return conn.execute(sql, (title or "", company or "", url or "")).fetchone()


def update_application(
    conn: sqlite3.Connection,
    app_id: int,
    data: dict,
) -> bool:
    """Update application and its associated job record."""
    row = conn.execute(
        "SELECT job_id FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not row:
        return False

    job_id = row["job_id"]
    now = datetime.now().isoformat(timespec="seconds")
    applied_at_val = data.get("applied_at") or None

    conn.execute(
        """UPDATE applications
           SET applied_at = COALESCE(?, applied_at),
               salary_entered = COALESCE(?, salary_entered),
               status = COALESCE(?, status)
           WHERE id = ?""",
        (
            applied_at_val,
            data.get("salary_entered"),
            data.get("status"),
            app_id,
        ),
    )

    conn.execute(
        """UPDATE jobs
           SET title = COALESCE(?, title),
               company = COALESCE(?, company),
               company_norm = COALESCE(?, company_norm),
               location = COALESCE(?, location),
               url = COALESCE(?, url),
               last_seen = ?
           WHERE id = ?""",
        (
            data.get("title"),
            data.get("company"),
            norm_company(data.get("company")) if data.get("company") else None,
            data.get("location"),
            data.get("url"),
            now,
            job_id,
        ),
    )
    conn.commit()
    return True


def create_manual_application(
    conn: sqlite3.Connection,
    data: dict,
) -> int:
    """Create a new job and an associated application record."""
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    applied_at = data.get("applied_at") or today
    company = data.get("company") or ""
    company_norm = norm_company(company)

    # Insert into jobs
    cur = conn.execute(
        """INSERT INTO jobs (title, company, company_norm, location, url, is_external, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            data.get("title") or "",
            company,
            company_norm,
            data.get("location"),
            data.get("url") or "",
            applied_at,
            now,
        ),
    )
    job_id = cur.lastrowid

    # Insert into applications
    cur = conn.execute(
        """INSERT INTO applications (job_id, applied_at, salary_entered, cover_letter, confirmation, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            job_id,
            applied_at,
            data.get("salary_entered"),
            data.get("cover_letter"),
            data.get("confirmation"),
            data.get("status") or "Submitted",
        ),
    )
    app_id = cur.lastrowid
    conn.commit()
    return app_id


def reset_database(db_path: Path) -> None:
    """Clear all data from database tables and re-initialize the schema."""
    db_path = Path(db_path)
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript("""
            DROP TABLE IF EXISTS applications;
            DROP TABLE IF EXISTS evaluations;
            DROP TABLE IF EXISTS jobs;
            DROP TABLE IF EXISTS runs;
            DROP TABLE IF EXISTS answers;
        """)
        conn.executescript(SCHEMA)
        _migrate(conn)
    finally:
        conn.close()


def export_database_records(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Export all records from SQLite tables into dictionary lists."""
    tables = ["jobs", "evaluations", "applications", "runs", "answers"]
    result: dict[str, list[dict]] = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        result[table] = [dict(r) for r in rows]
    return result


def import_database_records(conn: sqlite3.Connection, data: dict[str, list[dict]]) -> dict[str, int]:
    """Import records into SQLite database tables, preserving relationships.

    Resets tables to a clean state and inserts rows in dependency order.
    Returns counts of inserted rows per table.
    """
    counts: dict[str, int] = {}
    
    # 1. Reset tables with schema
    conn.executescript("""
        DROP TABLE IF EXISTS applications;
        DROP TABLE IF EXISTS evaluations;
        DROP TABLE IF EXISTS jobs;
        DROP TABLE IF EXISTS runs;
        DROP TABLE IF EXISTS answers;
    """)
    conn.executescript(SCHEMA)
    _migrate(conn)

    # 2. Insert jobs
    jobs = data.get("jobs") or []
    for j in jobs:
        conn.execute(
            """INSERT INTO jobs (id, jobstreet_id, url, title, company, company_norm, location,
                               salary_text, description, teaser, is_external, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                j.get("id"),
                j.get("jobstreet_id"),
                j.get("url"),
                j.get("title"),
                j.get("company"),
                j.get("company_norm") or norm_company(j.get("company")),
                j.get("location"),
                j.get("salary_text"),
                j.get("description"),
                j.get("teaser"),
                j.get("is_external", 0),
                j.get("first_seen") or date.today().isoformat(),
                j.get("last_seen") or date.today().isoformat(),
            ),
        )
    counts["jobs"] = len(jobs)

    # 3. Insert evaluations
    evals = data.get("evaluations") or []
    for e in evals:
        conn.execute(
            """INSERT INTO evaluations (id, job_id, scored_at, model, match_pct, years_required, seniority,
                                       met, unmet, decision, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.get("id"),
                e.get("job_id"),
                e.get("scored_at") or datetime.now().isoformat(timespec="seconds"),
                e.get("model", "unknown"),
                e.get("match_pct"),
                e.get("years_required"),
                e.get("seniority"),
                e.get("met"),
                e.get("unmet"),
                e.get("decision", "skip"),
                e.get("reason"),
            ),
        )
    counts["evaluations"] = len(evals)

    # 4. Insert applications
    apps = data.get("applications") or []
    for a in apps:
        conn.execute(
            """INSERT INTO applications (id, job_id, applied_at, salary_entered, cover_letter, confirmation, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                a.get("id"),
                a.get("job_id"),
                a.get("applied_at") or date.today().isoformat(),
                a.get("salary_entered"),
                a.get("cover_letter"),
                a.get("confirmation"),
                a.get("status", "Submitted"),
            ),
        )
    counts["applications"] = len(apps)

    # 5. Insert runs
    runs = data.get("runs") or []
    for r in runs:
        conn.execute(
            """INSERT INTO runs (id, started_at, finished_at, command, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (
                r.get("id"),
                r.get("started_at") or datetime.now().isoformat(timespec="seconds"),
                r.get("finished_at"),
                r.get("command"),
                r.get("notes"),
            ),
        )
    counts["runs"] = len(runs)

    # 6. Insert answers
    answers = data.get("answers") or []
    for ans in answers:
        conn.execute(
            """INSERT INTO answers (id, match, answer, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                ans.get("id"),
                ans.get("match", ""),
                str(ans.get("answer", "")),
                ans.get("created_at") or datetime.now().isoformat(timespec="seconds"),
            ),
        )
    counts["answers"] = len(answers)

    conn.commit()
    return counts
