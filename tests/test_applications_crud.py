import io
import sqlite3
import pytest
from starlette.testclient import TestClient

from src.api.main import create_app
from src import db


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    conn.close()

    app = create_app(data_dir=tmp_path, logs_dir=tmp_path)
    with TestClient(app) as tc:
        yield tc


def test_create_and_delete_application(client):
    # Create application manually
    resp = client.post(
        "/api/applications",
        json={
            "title": "Backend Engineer",
            "company": "Acme Inc",
            "url": "https://example.com/job/123",
            "location": "Remote",
            "salary_entered": "$5,000",
            "status": "Submitted",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # List applications
    resp = client.get("/api/applications")
    assert resp.status_code == 200
    apps = resp.json()["apps"]
    assert len(apps) == 1
    app_id = apps[0]["id"]
    assert apps[0]["title"] == "Backend Engineer"
    assert apps[0]["company"] == "Acme Inc"

    # Edit application
    edit_resp = client.put(
        f"/api/applications/{app_id}",
        json={
            "title": "Senior Backend Engineer",
            "salary_entered": "$6,000",
            "status": "Interview",
        },
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["success"] is True

    # Check updated application
    resp = client.get("/api/applications")
    apps = resp.json()["apps"]
    assert apps[0]["title"] == "Senior Backend Engineer"
    assert apps[0]["salary_entered"] == "$6,000"
    assert apps[0]["status"] == "Interview"

    # Delete application
    del_resp = client.delete(f"/api/applications/{app_id}")
    assert del_resp.status_code == 200

    # List applications again - should be empty
    resp = client.get("/api/applications")
    assert len(resp.json()["apps"]) == 0


def test_import_applications_csv(client):
    csv_content = """Applied Date,Role Title,Company,Location,Status,Salary Entered,Job URL
2026-08-01,Fullstack Developer,Stark Corp,Singapore,Submitted,$7000,https://stark.example.com/job/1
2026-08-02,DevOps Engineer,Wayne Enterprises,Remote,Interview,$8000,https://wayne.example.com/job/2
"""
    files = {
        "file": ("applications.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")
    }
    resp = client.post("/api/applications/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["skipped"] == 0

    # Re-import same CSV to verify dedup skip
    files2 = {
        "file": ("applications.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")
    }
    resp2 = client.post("/api/applications/import", files=files2)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["imported"] == 0
    assert data2["skipped"] == 2


def test_mark_job_applied(client):
    # Insert a mock external job into DB
    db_file = client.app.state.db_path
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    db.upsert_job(
        conn,
        {
            "jobstreet_id": "job_ext_999",
            "title": "Cloud Architect",
            "company": "External Co",
            "url": "https://external.example.com/job/999",
            "is_external": 1,
        },
    )
    conn.close()

    # List jobs: should show is_external = 1, application_id = None
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["is_external"] == 1
    assert jobs[0]["application_id"] is None

    # Mark as applied
    resp = client.post("/api/jobs/job_ext_999/mark-applied")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # List jobs again: application_id should be set
    resp = client.get("/api/jobs")
    jobs = resp.json()["jobs"]
    assert jobs[0]["application_id"] is not None

    # List applications: should now contain Cloud Architect
    resp = client.get("/api/applications")
    apps = resp.json()["apps"]
    assert len(apps) == 1
    assert apps[0]["title"] == "Cloud Architect"
    assert apps[0]["company"] == "External Co"


def test_m3_partial_update_does_not_null_fields(client):
    # Create application with initial values
    resp = client.post(
        "/api/applications",
        json={
            "title": "Data Engineer",
            "company": "Tech Corp",
            "url": "https://example.com/job/456",
            "location": "Jakarta",
            "salary_entered": "IDR 10.000.000",
            "status": "Submitted",
            "applied_at": "2026-08-10",
        },
    )
    assert resp.status_code == 200

    resp = client.get("/api/applications")
    app_id = resp.json()["apps"][0]["id"]

    # Partial update: change only status, send empty applied_at string, omit location and salary_entered
    edit_resp = client.put(
        f"/api/applications/{app_id}",
        json={
            "status": "Interview",
            "applied_at": "",
        },
    )
    assert edit_resp.status_code == 200

    # Verify fields were preserved
    resp_after = client.get("/api/applications")
    app = resp_after.json()["apps"][0]
    assert app["status"] == "Interview"
    assert app["applied_at"] == "2026-08-10"
    assert app["location"] == "Jakarta"
    assert app["salary_entered"] == "IDR 10.000.000"

def test_import_applications_rejects_xls_and_handles_empty_file(client):
    # Reject .xls
    files_xls = {
        "file": ("test.xls", io.BytesIO(b"dummy binary xls data"), "application/vnd.ms-excel")
    }
    resp_xls = client.post("/api/applications/import", files=files_xls)
    assert resp_xls.status_code == 400
    assert "not supported" in resp_xls.json()["detail"]

    # Handle completely empty CSV file
    files_empty = {
        "file": ("empty.csv", io.BytesIO(b""), "text/csv")
    }
    resp_empty = client.post("/api/applications/import", files=files_empty)
    assert resp_empty.status_code == 200
    assert resp_empty.json()["imported"] == 0
