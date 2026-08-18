"""Human review verdicts: record_decision overrides the latest evaluation."""
import sqlite3

from src.db import (approved_unapplied, connect, insert_evaluation,
                    latest_evaluations, record_decision, upsert_job)


def make_conn() -> sqlite3.Connection:
    return connect(":memory:")


def add_job(conn, js_id="12345"):
    return upsert_job(conn, {
        "jobstreet_id": js_id, "title": "Data Analyst",
        "company": "PT Test", "location": "Jakarta",
    })


def test_record_decision_overrides_review():
    conn = make_conn()
    job_id = add_job(conn)
    insert_evaluation(conn, job_id, {
        "model": "offline-v1", "match_pct": 50,
        "decision": "review", "reason": "borderline",
    })
    assert record_decision(conn, "12345", "apply", "looks good")
    latest = latest_evaluations(conn)[0]
    assert latest["decision"] == "apply"
    assert latest["model"] == "human"
    assert latest["reason"] == "looks good"


def test_approved_job_reaches_apply_queue():
    conn = make_conn()
    job_id = add_job(conn)
    insert_evaluation(conn, job_id, {"model": "offline-v1",
                                     "decision": "review"})
    assert approved_unapplied(conn) == []
    record_decision(conn, "12345", "apply")
    assert len(approved_unapplied(conn)) == 1


def test_rejected_job_stays_out_of_apply_queue():
    conn = make_conn()
    add_job(conn)
    record_decision(conn, "12345", "skip")
    assert approved_unapplied(conn) == []


def test_unknown_job_returns_false():
    conn = make_conn()
    assert not record_decision(conn, "99999", "apply")

def test_m7_record_decision_numeric_id_fallback():
    conn = make_conn()
    # Job has a non-numeric jobstreet_id (e.g. slug or uuid)
    job_id = upsert_job(conn, {
        "jobstreet_id": "non-numeric-slug-xyz",
        "title": "Software Engineer",
        "company": "PT Tech",
        "location": "Jakarta",
    })
    # Calling record_decision with internal database numeric ID
    assert record_decision(conn, job_id, "apply", "approved by numeric ID")
    latest = latest_evaluations(conn)[0]
    assert latest["job_id"] == job_id
    assert latest["decision"] == "apply"
    assert latest["model"] == "human"
