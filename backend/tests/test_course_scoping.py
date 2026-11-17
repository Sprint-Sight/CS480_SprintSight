"""Staff may use assessment/ingestion routes only for courses they teach (admins: any course)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.dependencies.auth import get_user_repository
from app.main import app
from app.repositories.interfaces import ProjectRecord, UserRecord
from app.schemas.assessment import AssessmentReport, TeamScore
from app.schemas.auth import Role

client = TestClient(app)
PROJECT_ID = "00000000-0000-4000-8000-0000000000c1"


def _login(email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def course(override_user_repository):
    """A course taught by faculty@; other@ is an instructor of a different course."""
    projects = override_user_repository
    users = app.dependency_overrides[get_user_repository]()
    users.create_user(
        UserRecord(
            "u-other-instructor",
            "other@sprintsight.edu",
            "Other Instructor",
            Role.INSTRUCTOR,
            hash_password("password123"),
        )
    )
    mine = projects.create_course("CS480", "Capstone", "001", 2026, "Fall", "u-faculty-1")
    projects.assign_instructor(mine.id, "u-faculty-1")
    theirs = projects.create_course("CS999", "Other", "001", 2026, "Fall", "u-other-instructor")
    projects.assign_instructor(theirs.id, "u-other-instructor")
    projects.create_project(
        ProjectRecord(
            id=PROJECT_ID,
            project_name="P",
            team_name="Team",
            description=None,
            course_id=mine.id,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="some-repo",
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        [],
    )
    return mine


def _assess_body(course) -> dict:
    return {"course_id": course.id, "project_id": PROJECT_ID, "sprint_id": "sprint-1"}


def test_unassigned_instructor_cannot_start_assessment_or_sync(course) -> None:
    outsider = _login("other@sprintsight.edu")

    assess = client.post("/api/v1/assessments/assess", json=_assess_body(course), headers=outsider)
    sync = client.post("/api/v1/repo-ingestion/sync", json=_assess_body(course), headers=outsider)

    assert assess.status_code == 403
    assert sync.status_code == 403


def test_unassigned_instructor_cannot_read_or_change_course_settings(course) -> None:
    outsider = _login("other@sprintsight.edu")
    params = {"course_id": course.id}

    reports = client.get(
        "/api/v1/assessments/reports",
        params={**params, "project_id": PROJECT_ID, "sprint_id": "sprint-1"},
        headers=outsider,
    )
    weights = client.get("/api/v1/assessments/rubric-weights", params=params, headers=outsider)
    put = client.put(
        "/api/v1/assessments/rubric-weights",
        params=params,
        json={"weights": {"requirements": 1.0}},
        headers=outsider,
    )

    assert (reports.status_code, weights.status_code, put.status_code) == (403, 403, 403)


def test_assigned_instructor_and_admin_pass_the_course_check(course) -> None:
    params = {"course_id": course.id}
    for email in ("faculty@sprintsight.edu", "admin@sprintsight.edu"):
        response = client.get(
            "/api/v1/assessments/rubric-weights", params=params, headers=_login(email)
        )
        assert response.status_code == 200, (email, response.text)


def test_unassigned_instructor_cannot_read_a_courses_latest_report_or_job(course) -> None:
    report = AssessmentReport(
        report_id="rpt-scoping",
        model_name="m",
        mode="test",
        course_id=course.id,
        project_id=PROJECT_ID,
        sprint_id="sprint-1",
        generated_at=datetime.now(UTC),
        rubric_weights={},
        team_score=TeamScore(score=80, rationale="ok"),
        individual_scores=[],
        recommendations=[],
    )
    from app.dependencies.auth import get_assessment_repository

    app.dependency_overrides[get_assessment_repository]().save_report(report)
    outsider, owner = _login("other@sprintsight.edu"), _login("faculty@sprintsight.edu")
    params = {"course_id": course.id, "project_id": PROJECT_ID, "sprint_id": "sprint-1"}

    denied = client.get("/api/v1/assessments/latest", params=params, headers=outsider)
    allowed = client.get("/api/v1/assessments/latest", params=params, headers=owner)

    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_legacy_score_routes_mark_the_instructor_as_having_seen_the_ai_score(course) -> None:
    """Otherwise a label saved after peeking at /latest would still count as blind."""
    from app.dependencies.auth import get_assessment_repository, get_project_repository
    from app.dependencies.insights import get_optional_insights_repository
    from app.repositories.insights import InMemoryInsightsRepository

    assessments = app.dependency_overrides[get_assessment_repository]()
    insights = InMemoryInsightsRepository(
        assessments, app.dependency_overrides[get_project_repository]()
    )
    assessments.save_report(
        AssessmentReport(
            report_id="rpt-peek",
            model_name="m",
            mode="test",
            course_id=course.id,
            project_id=PROJECT_ID,
            sprint_id="sprint-1",
            generated_at=datetime.now(UTC),
            rubric_weights={},
            team_score=TeamScore(score=80, rationale="ok"),
            individual_scores=[],
            recommendations=[],
        )
    )
    app.dependency_overrides[get_optional_insights_repository] = lambda: insights
    try:
        response = client.get(
            "/api/v1/assessments/latest",
            params={"course_id": course.id, "project_id": PROJECT_ID, "sprint_id": "sprint-1"},
            headers=_login("faculty@sprintsight.edu"),
        )
    finally:
        app.dependency_overrides.pop(get_optional_insights_repository, None)

    assert response.status_code == 200
    view = insights.get_view("rpt-peek", "u-faculty-1")
    assert view is not None and view.first_score_seen_at is not None
