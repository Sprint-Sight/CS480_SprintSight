"""Small fixes from the repository audit (the low-severity batch)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.endpoints import assessment as assessment_endpoints
from app.main import app
from app.repositories.in_memory import InMemoryAssessmentJobRepository, job_repo
from app.repositories.interfaces import ProjectRecord
from app.schemas.assessment import AssessRequest
from app.services.assessmentService import service as assessment_service
from app.services.assessmentService.service import (
    convert_ai_result_to_assessment_report,
    run_assessment_job,
    safe_job_error_message,
)
from app.services.middleManService.service import AIEngineError

client = TestClient(app)
PAYLOAD = {"course_id": "c", "project_id": "p", "sprint_id": "sprint-1", "model_name": "m"}


def login(email: str, password: str = "password123") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def course_with_project(override_user_repository):
    override_user_repository.assign_instructor("cs480", "u-faculty-1")
    override_user_repository.create_project(
        ProjectRecord(
            id="proj-a",
            project_name="P",
            team_name="T",
            description=None,
            course_id="cs480",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="some-repo",
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        [],
    )
    return override_user_repository


# --- item 7: a temporary password must be changed before these routes work ---------------------


def test_a_user_who_must_change_their_password_cannot_use_notifications_or_courses(
    override_user_repository,
) -> None:
    admin = login("admin@sprintsight.edu")
    created = client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": "temp.student@example.com",
            "full_name": "Temp Student",
            "role": "student",
            "password": "TempPass123!",
            "student_number": 424242,
        },
    )
    assert created.status_code == 201, created.text
    temp = login("temp.student@example.com", "TempPass123!")

    for path in ("/api/v1/notifications", "/api/v1/courses", "/api/v1/students/projects"):
        response = client.get(path, headers=temp)
        assert response.status_code == 403, (path, response.status_code)
        assert response.json()["error"]["message"] == "Password change required."


def test_the_same_routes_work_once_the_password_is_not_temporary(override_user_repository) -> None:
    student = login("student@sprintsight.edu")

    assert client.get("/api/v1/notifications", headers=student).status_code == 200
    assert client.get("/api/v1/courses", headers=student).status_code == 200


# --- item 8: admins may use the Jira routes of any course --------------------------------------


def test_an_admin_can_read_a_projects_jira_runs_but_an_unassigned_instructor_cannot(
    course_with_project,
) -> None:
    from app.core.security import hash_password
    from app.dependencies.auth import get_user_repository
    from app.repositories.interfaces import UserRecord
    from app.schemas.auth import Role

    app.dependency_overrides[get_user_repository]().create_user(
        UserRecord(
            "u-outsider",
            "outsider@sprintsight.edu",
            "Outsider",
            Role.INSTRUCTOR,
            hash_password("password123"),
        )
    )
    path = "/api/v1/jira-ingestion/runs/proj-a/sprint-1"

    admin = client.get(path, headers=login("admin@sprintsight.edu"))
    owner = client.get(path, headers=login("faculty@sprintsight.edu"))
    outsider = client.get(path, headers=login("outsider@sprintsight.edu"))

    assert (admin.status_code, owner.status_code, outsider.status_code) == (200, 200, 403)


# --- item 4: a score that is not a number is a failed dimension, not a 0 -----------------------


def engine_result(**scores: object) -> dict:
    dimensions = {
        name: {"dimension": name, "score": score, "justification": f"on {name}"}
        for name, score in scores.items()
    }
    return {"overall_score": 7, "rubric_scores": dimensions}


@pytest.mark.parametrize("bad_score", ["high", None, True, [7]])
def test_a_non_numeric_dimension_score_is_flagged_instead_of_counted_as_zero(bad_score) -> None:
    result = engine_result(
        requirements=8, code_quality=7, testing=bad_score, documentation=9, collaboration=5, cicd=4
    )

    report = convert_ai_result_to_assessment_report(PAYLOAD, result)

    assert report.failed_dimensions == ["testing"]
    assert report.evaluation_failed is True
    detail = report.rubric_scores["testing"]
    assert detail.evaluation_failed is True and detail.failure_class == "schema_validation"
    # the other five are averaged as before, testing left out: (8+7+9+5+4)/5 = 6.6
    assert report.team_score.score == pytest.approx(66.0)
    assert "testing" not in (report.ai_rubric_scores_original or {})


def test_numeric_scores_are_unchanged() -> None:
    result = engine_result(
        requirements=8, code_quality=7.5, testing=6, documentation=9, collaboration=5, cicd=4
    )

    report = convert_ai_result_to_assessment_report(PAYLOAD, result)

    assert report.failed_dimensions == []
    assert report.rubric_scores["code_quality"].score == 7.5


# --- item 5: what a failed job shows is never raw exception text -------------------------------


def test_the_job_error_is_a_fixed_sentence_unless_it_is_our_own_wording() -> None:
    secret = "connect to http://10.0.0.5:8001/assess failed; body={'student':'Jane Doe'}"

    assert "10.0.0.5" not in safe_job_error_message(RuntimeError(secret))
    assert "Jane" not in safe_job_error_message(
        AIEngineError(secret, kind="engine_error", transient=False)
    )
    assert (
        safe_job_error_message(AIEngineError(secret, kind="timeout", transient=True))
        == "The AI engine did not answer in time."
    )
    assert (
        safe_job_error_message(HTTPException(status_code=400, detail="Project has no repository."))
        == "Project has no repository."
    )


def test_a_failed_job_keeps_the_traceback_in_the_log_and_shows_a_safe_sentence(
    monkeypatch, caplog
) -> None:
    repository = InMemoryAssessmentJobRepository()
    monkeypatch.setattr(job_repo, "_target", repository)
    request = AssessRequest(course_id="c", project_id="p", sprint_id="s")
    job = repository.create_job(request)

    def explode(*args, **kwargs):
        raise RuntimeError("secret http://internal:8001 password=hunter2")

    monkeypatch.setattr(assessment_service, "resolve_local_repository_path", explode)
    project = SimpleNamespace(local_repo_path="some-repo")

    with caplog.at_level("ERROR"):
        run_assessment_job(job.job_id, request, project, None, None)

    state = repository.get_job(job.job_id)
    assert state is not None and state.status == "failed"
    shown = [state.error_message, repository.list_events(job.job_id)[-1].data["error_message"]]
    assert all("hunter2" not in text and "internal" not in text for text in shown)
    assert any("hunter2" in record.getMessage() or record.exc_info for record in caplog.records)


# --- item 6: a model the client names must be one the engine can serve -------------------------


def test_assess_rejects_an_unknown_model_and_still_accepts_none_or_a_catalogued_one(
    course_with_project, monkeypatch
) -> None:
    monkeypatch.setattr(assessment_endpoints._executor, "submit", lambda *a, **k: None)
    headers = login("faculty@sprintsight.edu")
    body = {"course_id": "cs480", "project_id": "proj-a", "sprint_id": "sp1"}

    unknown = client.post(
        "/api/v1/assessments/assess", json={**body, "model_name": "gpt-nonsense"}, headers=headers
    )
    default = client.post("/api/v1/assessments/assess", json=body, headers=headers)
    known = client.post(
        "/api/v1/assessments/assess",
        json={**body, "model_name": "sprintsight-qwen"},
        headers=headers,
    )

    assert unknown.status_code == 400 and "gpt-nonsense" in unknown.json()["error"]["message"]
    assert default.status_code == 202, default.text
    assert known.status_code == 202, known.text
