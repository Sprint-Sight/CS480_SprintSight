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
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
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


# --- Jira contribution outliers (H1) -----------------------------------------------------------


def test_unassigned_instructor_cannot_read_another_courses_jira_outliers(course) -> None:
    outsider, owner = _login("other@sprintsight.edu"), _login("faculty@sprintsight.edu")
    admin = _login("admin@sprintsight.edu")
    base = f"/api/v1/jira/contribution-outliers/courses/{course.id}"

    assert client.get(base, headers=outsider).status_code == 403
    assert client.get(f"{base}/students/u-student-1", headers=outsider).status_code == 403
    # The course has no Jira runs, so an authorised caller gets 404 (no data) rather than 403;
    # the data path itself is covered in test_jira_contribution_outlier.py.
    assert client.get(base, headers=owner).status_code == 404
    assert client.get(base, headers=admin).status_code == 404


# --- Student accounts (H2) ---------------------------------------------------------------------


@pytest.fixture
def students(course):
    """mine-only, theirs-only, shared across both courses, and not enrolled anywhere."""
    from app.dependencies.auth import get_project_repository

    users = app.dependency_overrides[get_user_repository]()
    projects = app.dependency_overrides[get_project_repository]()
    theirs = next(c for c in projects.list_courses() if c.code == "CS999")
    ids = {}
    for key in ("mine", "theirs", "shared", "free"):
        users.create_user(
            UserRecord(
                f"u-{key}",
                f"{key}@sprintsight.edu",
                key.title(),
                Role.STUDENT,
                hash_password("password123"),
            )
        )
        ids[key] = f"u-{key}"
    projects.enroll_student(course.id, ids["mine"])
    projects.enroll_student(theirs.id, ids["theirs"])
    projects.enroll_student(course.id, ids["shared"])
    projects.enroll_student(theirs.id, ids["shared"])
    return ids


def test_instructor_lists_only_students_in_their_courses_or_unenrolled(course, students) -> None:
    response = client.get("/api/v1/users", headers=_login("faculty@sprintsight.edu"))

    listed = {u["id"] for u in response.json()}
    assert response.status_code == 200
    assert {students["mine"], students["shared"], students["free"]} <= listed
    assert students["theirs"] not in listed


def test_instructor_cannot_read_a_student_of_another_course(course, students) -> None:
    headers = _login("faculty@sprintsight.edu")

    assert client.get(f"/api/v1/users/{students['theirs']}", headers=headers).status_code == 403
    for key in ("mine", "shared", "free"):
        assert client.get(f"/api/v1/users/{students[key]}", headers=headers).status_code == 200


def test_instructor_cannot_edit_a_student_of_another_course(course, students) -> None:
    headers = _login("faculty@sprintsight.edu")

    response = client.patch(
        f"/api/v1/users/{students['theirs']}",
        json={"email": "taken-over@example.com"},
        headers=headers,
    )

    assert response.status_code == 403
    users = app.dependency_overrides[get_user_repository]()
    assert users.get_by_id(students["theirs"]).email == "theirs@sprintsight.edu"


def test_enrolling_a_student_into_my_course_does_not_unlock_editing_them(course, students) -> None:
    """Any instructor can enrol any student, so enrolment must not grant edit rights."""
    headers = _login("faculty@sprintsight.edu")
    enrol = client.post(
        f"/api/v1/courses/{course.id}/students/{students['theirs']}", headers=headers
    )
    assert enrol.status_code == 200, enrol.text

    edit = client.patch(
        f"/api/v1/users/{students['theirs']}", json={"email": "x@example.com"}, headers=headers
    )
    shared_edit = client.patch(
        f"/api/v1/users/{students['shared']}", json={"email": "y@example.com"}, headers=headers
    )

    assert edit.status_code == 403
    assert shared_edit.status_code == 403


def test_instructor_can_edit_students_only_in_their_courses_or_unenrolled(course, students) -> None:
    headers = _login("faculty@sprintsight.edu")

    mine = client.patch(
        f"/api/v1/users/{students['mine']}", json={"full_name": "Renamed"}, headers=headers
    )
    free = client.patch(
        f"/api/v1/users/{students['free']}", json={"full_name": "Renamed"}, headers=headers
    )

    assert (mine.status_code, free.status_code) == (200, 200)


def test_admin_can_still_read_and_edit_any_student(course, students) -> None:
    admin = _login("admin@sprintsight.edu")

    listed = {u["id"] for u in client.get("/api/v1/users", headers=admin).json()}
    read = client.get(f"/api/v1/users/{students['theirs']}", headers=admin)
    edit = client.patch(
        f"/api/v1/users/{students['shared']}", json={"full_name": "Admin Edit"}, headers=admin
    )

    assert set(students.values()) <= listed
    assert (read.status_code, edit.status_code) == (200, 200)


def test_changing_a_students_email_signs_out_their_existing_sessions(course, students) -> None:
    student_login = client.post(
        "/api/v1/auth/login", json={"email": "mine@sprintsight.edu", "password": "password123"}
    )
    student = {"Authorization": f"Bearer {student_login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=student).status_code == 200

    patch = client.patch(
        f"/api/v1/users/{students['mine']}",
        json={"email": "mine.new@sprintsight.edu"},
        headers=_login("faculty@sprintsight.edu"),
    )

    assert patch.status_code == 200, patch.text
    assert client.get("/api/v1/auth/me", headers=student).status_code == 401
