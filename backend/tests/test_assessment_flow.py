import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.dependencies.auth import get_assessment_repository
from app.main import app
from app.repositories.interfaces import ProjectRecord
from app.schemas.assessment import AssessmentReport, StudentScore, TeamScore
from app.services.assessmentService.service import convert_ai_result_to_assessment_report
from app.services.middleManService.service import send_assessment_to_ai_engine

client = TestClient(app)


def test_convert_ai_result_to_assessment_report_maps_real_ai_payload() -> None:
    payload = {
        "course_id": "cs480",
        "project_id": "proj-a",
        "sprint_id": "sp1",
        "model_name": "sprintsight-llama",
    }
    ai_result = {
        "overall_score": 8,
        "executive_summary": "Strong sprint delivery.",
        "key_recommendations": ["Improve test coverage."],
        "member_contributions": [
            {
                "student_id": "stu-001",
                "contribution_score": 8,
                "primary_contributions": ["Implemented backend API."],
                "evidence": ["git commit evidence"],
            }
        ],
    }

    report = convert_ai_result_to_assessment_report(payload, ai_result)

    assert report.course_id == "cs480"
    assert report.project_id == "proj-a"
    assert report.sprint_id == "sp1"
    assert report.team_score.score == 80.0
    assert report.team_score.rationale == "Strong sprint delivery."
    assert report.individual_scores[0].student_id == "stu-001"
    assert report.individual_scores[0].score == 80.0
    assert report.recommendations == ["Improve test coverage."]


def faculty_token() -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "faculty@sprintsight.edu", "password": "password123"},
    )
    return response.json()["access_token"]


def test_send_assessment_to_ai_engine_uses_single_transport_call_without_fixed_timeout(monkeypatch) -> None:
    called = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "ok"}

    def fake_post(url, json=None, timeout=None):
        called["url"] = url
        called["json"] = json
        called["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("app.services.middleManService.service.httpx.post", fake_post)
    monkeypatch.setattr(
        "app.services.middleManService.service.get_settings",
        lambda: SimpleNamespace(ai_engine_url="http://host.docker.internal:8001/", default_model_name="mock-rubric-v1"),
    )

    result = send_assessment_to_ai_engine({"sprint_context": {"project_id": "demo"}}, "sprintsight-llama")

    assert result == {"status": "ok"}
    assert called["url"] == "http://host.docker.internal:8001/assess/sprint/data?modelname=sprintsight-llama"
    assert called["json"] == {"sprint_context": {"project_id": "demo"}}
    assert called["timeout"] is None


def test_assess_and_override_writes_audit(monkeypatch, tmp_path: Path, override_user_repository) -> None:
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


    monkeypatch.setattr(
        "app.services.assessmentService.service.send_assessment_to_ai_engine",
        lambda *args, **kwargs: {
            "overall_score": 8,
            "executive_summary": "Strong sprint delivery.",
            "key_recommendations": ["Improve test coverage."],
            "member_contributions": [],
        },
    )

    token = faculty_token()
    headers = {"Authorization": f"Bearer {token}"}

    assess_response = client.post(
        "/api/v1/assessments/assess",
        json={"course_id": "cs480", "project_id": "proj-a", "sprint_id": "sp1"},
        headers=headers,
    )
    assert assess_response.status_code == 202

    report_id = "rpt-audit-1"
    app.dependency_overrides[get_assessment_repository]().save_report(
        AssessmentReport(
            report_id=report_id,
            model_name="mock-rubric-v1",
            mode="mock",
            course_id="cs480",
            project_id="proj-a",
            sprint_id="sp1",
            generated_at=datetime.now(timezone.utc),
            rubric_weights={"delivery": 0.35, "collaboration": 0.30, "quality": 0.20, "documentation": 0.15},
            team_score=TeamScore(score=80.0, rationale="Initial team assessment."),
            individual_scores=[StudentScore(student_id="stu-001", score=80.0, rationale="Initial contribution.")],
            recommendations=["Increase unit testing."],
            rubric_scores={},
            strengths=["Delivery"],
            weaknesses=["Testing"],
        )
    )

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
    audit_list_response = client.get("/api/v1/audit/overrides", headers=headers)
    assert audit_list_response.status_code == 200
    assert len(audit_list_response.json()) >= 1


def test_instructor_mutation_actions_are_logged() -> None:
    token = faculty_token()
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/courses",
        json={
            "code": "CS499",
            "name": "Instructor Audit Course",
            "section": "A",
            "year": 2026,
            "term": "Fall",
        },
        headers=headers,
    )
    assert response.status_code == 201

    audit_response = client.get("/api/v1/audit/actions", headers=headers)
    assert audit_response.status_code == 200
    payload = audit_response.json()
    assert any(item.get("action") == "create_course" for item in payload)


def test_admin_reset_password_is_logged() -> None:
    admin_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'admin@sprintsight.edu', 'password': 'password123'}).json()['access_token']}"}
    user_response = client.post(
        "/api/v1/users",
        json={
            "email": "reset.audit.user@sprintsight.edu",
            "full_name": "Reset Audit User",
            "role": "student",
            "password": "temporary123",
        },
        headers=admin_headers,
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    reset_response = client.post(
        f"/api/v1/users/{user_id}/reset-password",
        json={"password": "newPassword456"},
        headers=admin_headers,
    )
    assert reset_response.status_code == 200

    audit_response = client.get("/api/v1/audit/actions", headers=admin_headers)
    assert audit_response.status_code == 200
    payload = audit_response.json()
    assert any(
        item.get("action") == "reset_password"
        and item.get("target_id") == user_id
        and item.get("actor_role") == "admin"
        and "password" not in item.get("details", {})
        for item in payload
    )

    deactivate_response = client.delete(f"/api/v1/users/{user_id}", headers=admin_headers)
    assert deactivate_response.status_code == 200
    activate_response = client.post(f"/api/v1/users/{user_id}/activate", headers=admin_headers)
    assert activate_response.status_code == 200

    updated_audit_response = client.get("/api/v1/audit/actions", headers=admin_headers)
    assert updated_audit_response.status_code == 200
    assert any(
        item.get("action") == "activate_user"
        and item.get("target_id") == user_id
        and item.get("actor_role") == "admin"
        for item in updated_audit_response.json()
    )


def test_audit_actions_are_scoped_to_actor_and_project_changes_are_logged() -> None:
    instructor_headers = {"Authorization": f"Bearer {faculty_token()}"}
    admin_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'admin@sprintsight.edu', 'password': 'password123'}).json()['access_token']}"}

    course = client.post(
        "/api/v1/courses",
        json={
            "code": "CS505",
            "name": "Scoped Audit Course",
            "section": "A",
            "year": 2026,
            "term": "Fall",
        },
        headers=instructor_headers,
    )
    assert course.status_code == 201

    admin_user = client.post(
        "/api/v1/users",
        json={
            "email": "audit.admin.check@sprintsight.edu",
            "full_name": "Audit Admin Check",
            "role": "admin",
            "password": "temporary123",
        },
        headers=admin_headers,
    )
    assert admin_user.status_code == 201

    instructor_audits = client.get("/api/v1/audit/actions", headers=instructor_headers)
    assert instructor_audits.status_code == 200
    instructor_payload = instructor_audits.json()
    instructor_only = [item for item in instructor_payload if item.get("actor_id") == "u-faculty-1"]
    assert instructor_only
    assert all(item["actor_id"] == "u-faculty-1" for item in instructor_payload)

    admin_audits = client.get("/api/v1/audit/actions", headers=admin_headers)
    assert admin_audits.status_code == 200
    admin_payload = admin_audits.json()
    assert any(item["action"] == "create_course" for item in admin_payload)
    assert any(item["action"] == "create_user" for item in admin_payload)

    project = client.post(
        f"/api/v1/courses/{course.json()['id']}/projects",
        json={
            "project_name": "Audit Project",
            "team_name": "Audit Team",
            "description": "Log project updates",
            "course_id": course.json()["id"],
            "member_ids": [],
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "JIRA",
            "jira_api_token": "project-jira-token",
        },
        headers=instructor_headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    update_response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"project_name": "Updated Audit Project"},
        headers=instructor_headers,
    )
    assert update_response.status_code == 200

    delete_response = client.delete(f"/api/v1/projects/{project_id}", headers=instructor_headers)
    assert delete_response.status_code == 200

    final_audits = client.get("/api/v1/audit/actions", headers=instructor_headers)
    assert final_audits.status_code == 200
    actions = [item["action"] for item in final_audits.json()]
    assert "update_project" in actions
    assert "delete_project" in actions


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
