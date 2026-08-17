import pytest
from datetime import date, timedelta
from src.db import (
    connect,
    upsert_job,
    find_job,
    jobs_without_details,
    jobs_without_evaluation,
    insert_evaluation,
    latest_evaluations,
    record_decision,
    company_in_cooldown,
    job_already_applied,
    insert_application,
    approved_unapplied,
    list_answers,
    add_answer,
    start_run,
    finish_run,
    finish_run_if_open,
    mark_interrupted_runs,
    list_runs,
    get_run,
    jobs_with_latest_eval,
    count_jobs_filtered,
    count_jobs,
    decision_counts,
    list_applications,
    count_applications,
    update_application_status,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_db_extra.db"
    conn = connect(db_file)
    yield conn
    conn.close()


def test_db_upsert_job_structure_types_and_update(test_db):
    # Upsert with dict and list structured values
    job_dict = {
        "jobstreet_id": "js-101",
        "url": "https://example.com/job/101",
        "title": {"label": "Software Engineer"},
        "company": {"text": "Acme Corp"},
        "location": ["Jakarta", {"label": "Remote"}],
        "salary_text": 15000000,
        "description": "Build python apps",
        "teaser": "Great python role",
    }
    job_id = upsert_job(test_db, job_dict)
    assert job_id > 0

    found = find_job(test_db, "js-101")
    assert found["title"] == "Software Engineer"
    assert found["company"] == "Acme Corp"
    assert "Jakarta" in found["location"]
    assert "Remote" in found["location"]
    assert found["salary_text"] == "15000000"

    # Upsert again with new details to trigger UPDATE branch
    updated_dict = {
        "jobstreet_id": "js-101",
        "title": "Senior Software Engineer",
        "description": "Updated description",
    }
    same_id = upsert_job(test_db, updated_dict)
    assert same_id == job_id

    refreshed = find_job(test_db, "js-101")
    assert refreshed["title"] == "Senior Software Engineer"
    assert refreshed["description"] == "Updated description"
    assert refreshed["company"] == "Acme Corp"  # preserved through COALESCE


def test_db_queries_jobs_without_details_and_evaluations(test_db):
    job1_id = upsert_job(test_db, {
        "jobstreet_id": "js-201",
        "title": "Frontend Engineer",
        "company": "Beta Inc",
        "description": None,
    })
    job2_id = upsert_job(test_db, {
        "jobstreet_id": "js-202",
        "title": "Backend Engineer",
        "company": "Gamma Inc",
        "description": "Has description",
    })

    no_details = jobs_without_details(test_db)
    ids_no_details = [j["id"] for j in no_details]
    assert job1_id in ids_no_details
    assert job2_id not in ids_no_details

    no_eval = jobs_without_evaluation(test_db)
    ids_no_eval = [j["id"] for j in no_eval]
    assert job1_id in ids_no_eval
    assert job2_id in ids_no_eval

    # Evaluate job2
    insert_evaluation(test_db, job2_id, {
        "model": "gpt-4o",
        "match_pct": 85,
        "years_required": 2,
        "seniority": "mid",
        "decision": "apply",
        "reason": "Good match",
    })

    no_eval_after = jobs_without_evaluation(test_db)
    ids_no_eval_after = [j["id"] for j in no_eval_after]
    assert job1_id in ids_no_eval_after
    assert job2_id not in ids_no_eval_after


def test_db_runs_lifecycle(test_db):
    run_id = start_run(test_db, "python -m src.run pipeline")
    assert run_id > 0

    run = get_run(test_db, run_id)
    assert run["command"] == "python -m src.run pipeline"
    assert run["finished_at"] is None

    # Finish run if open
    closed = finish_run_if_open(test_db, run_id, "Completed normally")
    assert closed is True
    assert finish_run_if_open(test_db, run_id, "Already closed") is False

    # Start another run and finish unconditionally
    run2_id = start_run(test_db, "python -m src.run scrape")
    finish_run(test_db, run2_id, "Done")
    run2 = get_run(test_db, run2_id)
    assert run2["finished_at"] is not None

    # Mark interrupted runs
    run3_id = start_run(test_db, "python -m src.run apply")
    interrupted_count = mark_interrupted_runs(test_db)
    assert interrupted_count == 1
    run3 = get_run(test_db, run3_id)
    assert "interrupted" in run3["notes"]

    # List runs with sorting
    runs_asc = list_runs(test_db, sort="id", order="asc")
    assert runs_asc[0]["id"] == run_id

    runs_by_finished = list_runs(test_db, sort="finished_at", order="desc")
    assert len(runs_by_finished) >= 3


def test_db_jobs_and_evaluations_queries(test_db):
    j1 = upsert_job(test_db, {"jobstreet_id": "q1", "title": "React Dev", "company": "Alpha Corp", "location": "Jakarta"})
    j2 = upsert_job(test_db, {"jobstreet_id": "q2", "title": "Python Dev", "company": "Zeta Tech", "location": "Bandung"})
    j3 = upsert_job(test_db, {"jobstreet_id": "q3", "title": "DevOps", "company": "Delta Cloud", "location": "Jakarta"})

    insert_evaluation(test_db, j1, {"decision": "apply", "match_pct": 90, "reason": "strong"})
    insert_evaluation(test_db, j2, {"decision": "skip", "match_pct": 40, "reason": "mismatch"})

    # Latest evaluations without filter & with filter
    all_evals = latest_evaluations(test_db)
    assert len(all_evals) == 2

    apply_evals = latest_evaluations(test_db, decision="apply")
    assert len(apply_evals) == 1
    assert apply_evals[0]["title"] == "React Dev"

    # Query unevaluated
    uneval_jobs = jobs_with_latest_eval(test_db, decision="unevaluated")
    assert any(j["id"] == j3 for j in uneval_jobs)
    assert count_jobs_filtered(test_db, decision="unevaluated") == 1

    # Search with q
    search_res = jobs_with_latest_eval(test_db, q="Alpha")
    assert len(search_res) == 1
    assert search_res[0]["company"] == "Alpha Corp"

    # Sort by match_pct
    sorted_res = jobs_with_latest_eval(test_db, sort="match", order="desc")
    assert sorted_res[0]["id"] == j1

    # Total counts and decision counts
    assert count_jobs(test_db) == 3
    dec_counts = {row["decision"]: row["c"] for row in decision_counts(test_db)}
    assert dec_counts.get("apply") == 1
    assert dec_counts.get("skip") == 1


def test_db_applications_and_answers(test_db):
    job_id = upsert_job(test_db, {"jobstreet_id": "app1", "title": "Golang Dev", "company": "Go Inc", "location": "Jakarta"})
    insert_application(test_db, job_id, {
        "applied_at": "2026-08-15T10:00:00",
        "salary_entered": "12000000",
        "cover_letter": "I love Go",
        "confirmation": "OK-123",
        "status": "Submitted",
    })

    assert job_already_applied(test_db, "app1") is True
    assert job_already_applied(test_db, "unapplied") is False

    apps = list_applications(test_db, status="Submitted", q="Golang", sort="salary_entered", order="desc")
    assert len(apps) == 1
    assert apps[0]["salary_entered"] == "12000000"

    assert count_applications(test_db, status="Submitted", q="Golang") == 1
    assert count_applications(test_db, status="Rejected") == 0

    # Update status
    app_id = apps[0]["id"]
    updated = update_application_status(test_db, app_id, "Interviewing")
    assert updated is True

    # Answers
    ans_id = add_answer(test_db, "notice_period", "Immediate")
    assert ans_id > 0
    all_ans = list_answers(test_db)
    assert any(a["match"] == "notice_period" and a["answer"] == "Immediate" for a in all_ans)
