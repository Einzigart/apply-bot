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
