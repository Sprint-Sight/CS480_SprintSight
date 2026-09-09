from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.repositories.interfaces import ProjectRecord
from datetime import datetime, timezone


client = TestClient(app)


def faculty_token() -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "faculty@sprintsight.edu", "password": "password123"},
    )
    return response.json()["access_token"]


def test_assess_and_override_writes_audit(monkeypatch, tmp_path: Path, override_user_repository) -> None:
    audit_file = tmp_path / "audit.log"
    repository_root = tmp_path / "repos"
    repository_path = repository_root / "cs-203-project"
    repository_path.mkdir(parents=True)
    subprocess.run(["git", "init", str(repository_path)], check=True, capture_output=True)
    (repository_path / "README.md").write_text("# CS203 project\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository_path), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repository_path), "-c", "user.name=Test User", "-c", "user.email=test@example.com", "commit", "-m", "Initial commit"],
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("AUDIT_LOG_PATH", str(audit_file))
    monkeypatch.setenv("LOCAL_REPOSITORY_ROOT", str(repository_root))
    get_settings.cache_clear()
    override_user_repository.create_project(
        ProjectRecord(
            id="proj-a",
            project_name="CS203 Project",
            team_name="CS203 Team",
            description=None,
            course_id="cs480",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="cs-203-project",
            created_by="u-faculty-1",
            created_at=datetime.now(timezone.utc),
        ),
        [],
    )

    token = faculty_token()
    headers = {"Authorization": f"Bearer {token}"}

    assess_response = client.post(
        "/api/v1/assessments/assess",
        json={"course_id": "cs480", "project_id": "proj-a", "sprint_id": "sp1"},
        headers=headers,
    )
    assert assess_response.status_code == 200

    report_id = assess_response.json()["report"]["report_id"]

    override_response = client.post(
        "/api/v1/assessments/override",
        json={
            "report_id": report_id,
            "student_id": "stu-001",
            "new_score": 91.0,
            "reason_comment": "Adjusted for strong testing leadership and mentoring.",
        },
        headers=headers,
    )
    assert override_response.status_code == 200
    assert audit_file.exists()
    assert "reason_comment" in audit_file.read_text(encoding="utf-8")

    audit_list_response = client.get("/api/v1/audit/overrides", headers=headers)
    assert audit_list_response.status_code == 200
    assert len(audit_list_response.json()) >= 1


def test_assessment_job_contract_returns_accepted_and_job_id(monkeypatch, tmp_path: Path, override_user_repository) -> None:
    repository_root = tmp_path / "repos"
    repository_path = repository_root / "cs-203-project"
    repository_path.mkdir(parents=True)
    subprocess.run(["git", "init", str(repository_path)], check=True, capture_output=True)
    (repository_path / "README.md").write_text("# CS203 project\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository_path), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repository_path), "-c", "user.name=Test User", "-c", "user.email=test@example.com", "commit", "-m", "Initial commit"],
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("LOCAL_REPOSITORY_ROOT", str(repository_root))
    get_settings.cache_clear()
    override_user_repository.create_project(
        ProjectRecord(
            id="proj-a",
            project_name="CS203 Project",
            team_name="CS203 Team",
            description=None,
            course_id="cs480",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="cs-203-project",
            created_by="u-faculty-1",
            created_at=datetime.now(timezone.utc),
        ),
        [],
    )

    token = faculty_token()
    headers = {"Authorization": f"Bearer {token}"}

    assess_response = client.post(
        "/api/v1/assessments/assess",
        json={"course_id": "cs480", "project_id": "proj-a", "sprint_id": "sp1"},
        headers=headers,
    )
    assert assess_response.status_code == 202
    assert "job_id" in assess_response.json()
    assert assess_response.json()["status"] == "queued"

    job_id = assess_response.json()["job_id"]
    events_response = client.get(f"/api/v1/assessments/jobs/{job_id}/events", headers=headers)
    assert events_response.status_code == 200
    assert "text/event-stream" in events_response.headers.get("content-type", "")
