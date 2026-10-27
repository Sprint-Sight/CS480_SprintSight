# backend/tests/test_jira_contribution_outlier.py
"""
Tests for the Jira contribution outlier endpoints:
    GET /api/v1/jira/contribution-outliers/courses/{course_id}
    GET /api/v1/jira/contribution-outliers/courses/{course_id}/students/{student_id}
"""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.dependencies.auth import (
    get_jira_ingestion_repository,
    get_project_repository,
    get_user_repository,
)
from app.main import app
from app.repositories.in_memory import (
    InMemoryJiraIngestionRunRepository,
    InMemoryProjectRepository,
    InMemoryUserRepository,
)
from app.repositories.interfaces import (
    JiraIngestionRunRecord,
    ProjectRecord,
    Role,
    UserRecord,
)
from app.schemas.assessment import JiraCleanedSnapshot, JiraTicket
from app.schemas.jira_outlier import (
    JiraContributionOutlierReport,
    JiraContributionOutlierResponse,
)

client = TestClient(app)


def _token_for(email: str, password: str = "password123") -> str:
    """Login and return a JWT access‑token."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _setup_course_with_project():
    """
    Create a course, two students, a project and enrol the students.
    Returns: (project_repo, course, user_repo, student_a, student_b)
    """
    project_repo = InMemoryProjectRepository()
    course = project_repo.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1"
    )

    student_a = UserRecord(
        id="u-student-a",
        email="student.a@sprintsight.edu",
        full_name="Student A",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=101,
    )
    student_b = UserRecord(
        id="u-student-b",
        email="student.b@sprintsight.edu",
        full_name="Student B",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=102,
    )
    user_repo = InMemoryUserRepository()
    user_repo.create_user(student_a)
    user_repo.create_user(student_b)

    # ── create a ProjectRecord and register the project ──────────────────
    project = ProjectRecord(
        id="proj-jira-1",
        project_name="Jira Test Project",
        team_name="Team Alpha",
        description="Test project for Jira contribution outlier tests",
        course_id=course.id,
        course_code="CS480",
        github_repo_url="https://github.com/example/sprintsight",
        local_repo_path="/tmp/sprintsight",
        created_by="u-faculty-1",
        created_at=datetime.now(UTC),
    )
    project_repo.create_project(project, ["u-student-a", "u-student-b"])

    # enrol students in the course
    project_repo.enroll_student(course.id, "u-student-a")
    project_repo.enroll_student(course.id, "u-student-b")

    return project_repo, course, user_repo, student_a, student_b


def _override_repos(
    project_repository,
    user_repository,
    jira_ingestion_repository,
    peer_eval_repo=None,
):
    """Push the in‑memory repos into the FastAPI dependency overrides."""
    app.dependency_overrides[get_project_repository] = lambda: project_repository
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_jira_ingestion_repository] = lambda: jira_ingestion_repository
    if peer_eval_repo is not None:
        # keep the override list consistent (no‑op)
        pass


def _clear_overrides():
    for dependency in (
        get_project_repository,
        get_user_repository,
        get_jira_ingestion_repository,
    ):
        app.dependency_overrides.pop(dependency, None)


# ----------------------------------------------------------------------
# TESTS
# ----------------------------------------------------------------------


def test_instructor_can_get_contribution_outlier():
    """
    Faculty member can call the endpoint and receives a valid
    JiraContributionOutlierResponse.
    """
    project_repo, course, user_repo, sa, sb = _setup_course_with_project()

    jira_repo = InMemoryJiraIngestionRunRepository()

    cleaned = {
        "issues": [
            {
                "key": "PROJ-1",
                "fields": {
                    "assignee": {"id": "u-student-a", "displayName": "Student A"},
                    "customfield_10009": 5,
                    "summary": "Implement login",
                },
            },
            {
                "key": "PROJ-2",
                "fields": {
                    "assignee": {"id": "u-student-a", "displayName": "Student A"},
                    "customfield_10009": 3,
                    "summary": "Write docs",
                },
            },
            {
                "key": "PROJ-3",
                "fields": {
                    "assignee": {"id": "u-student-b", "displayName": "Student B"},
                    "customfield_10009": 2,
                    "summary": "Fix typo",
                },
            },
        ]
    }

    run = JiraIngestionRunRecord(
        id="run-1",
        course_id=course.id,
        project_id="proj-jira-1",
        sprint_id=None,
        jira_project_key="PROJ",
        jql="project = PROJ",
        raw_bucket="raw/bucket",
        raw_object_key="objectKey",
        issue_count=3,
        captured_at=datetime.now(UTC),
        cleaned_snapshot=cleaned,
    )
    jira_repo.create_run(run)

    _override_repos(project_repo, user_repo, jira_repo)

    try:
        faculty_token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {faculty_token}"}

        resp = client.get(
            f"/api/v1/jira/contribution-outliers/courses/{course.id}/students/{sa.id}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        outlier = JiraContributionOutlierResponse(**data)

        # Student A has 2 tickets, 5+3 = 8 points
        assert outlier.student_id == sa.id
        assert outlier.student_full_name == "Student A"
        assert outlier.total_tickets == 2
        assert outlier.total_story_points == 8
        assert outlier.average_points_per_ticket == 4.0

        # Course baseline (only student A & B have data → mean = (8+2)/2 = 5)
        assert outlier.course_average_total_points == 5.0
        # The course cohort is the full population: pstdev([8, 2]) = 3.0
        assert outlier.course_total_score_std_dev == 3.0

        # z‑score = (8‑5)/3 = 1.0 → at the threshold → flagged high
        assert outlier.contribution_z_score == 1.0
        assert outlier.is_contribution_outlier is True
        assert outlier.outlier_direction == "high"

        # Below‑average count: student B has 2 points < 5, so 1
        assert outlier.students_below_course_average == 1
        assert outlier.enrolled_student_count == 2
        assert outlier.students_with_jira_data == 2
        # Evidence: both tickets assigned to student A are returned.
        assert [ticket.ticket_id for ticket in outlier.tickets] == ["PROJ-1", "PROJ-2"]

    finally:
        _clear_overrides()


def test_instructor_403_when_not_faculty():
    """A non‑faculty user (student) receives 403."""
    project_repo, course, user_repo, sa, sb = _setup_course_with_project()
    jira_repo = InMemoryJiraIngestionRunRepository()
    _override_repos(project_repo, user_repo, jira_repo)

    student_token = _token_for("student.a@sprintsight.edu")
    headers = {"Authorization": f"Bearer {student_token}"}

    resp = client.get(
        f"/api/v1/jira/contribution-outliers/courses/{course.id}/students/{sa.id}",
        headers=headers,
    )
    assert resp.status_code == 403, resp.text


def test_student_403_when_not_faculty():
    """Re‑use the previous test logic; just a second assertion."""
    assert test_instructor_403_when_not_faculty() is None  # noqa


def test_missing_jira_data_returns_404():
    """
    When there is no Jira ingestion run for the course the endpoint
    returns 404 (service raises HTTPException).
    """
    project_repo, course, user_repo, sa, sb = _setup_course_with_project()
    jira_repo = InMemoryJiraIngestionRunRepository()
    _override_repos(project_repo, user_repo, jira_repo)

    resp = client.get(
        f"/api/v1/jira/contribution-outliers/courses/{course.id}/students/{sa.id}",
        headers={"Authorization": f"Bearer {_token_for('faculty@sprintsight.edu')}"},
    )
    assert resp.status_code == 404, resp.text


def test_outlier_flag_and_direction_when_low():
    """
    When a student’s total story‑points is clearly below the course mean,
    the response should have `is_contribution_outlier=True`,
    `outlier_direction="low"` and a numeric `contribution_z_score`.
    """
    project_repo, course, user_repo, sa, sb = _setup_course_with_project()

    # A third student makes a true low outlier possible: with only two
    # students every z-score is exactly ±1.
    student_c = UserRecord(
        id="u-student-c",
        email="student.c@sprintsight.edu",
        full_name="Student C",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=103,
    )
    user_repo.create_user(student_c)
    project_repo.set_members("proj-jira-1", [sa.id, sb.id, student_c.id])
    project_repo.enroll_student(course.id, student_c.id)

    jira_repo = InMemoryJiraIngestionRunRepository()

    # Student A is far below B and C.
    cleaned = {
        "issues": [
            {
                "key": "P1",
                "fields": {
                    "assignee": {"id": sa.id},
                    "customfield_10009": 1,
                    "summary": "A1",
                },
            },
            {
                "key": "P2",
                "fields": {
                    "assignee": {"id": sb.id},
                    "customfield_10009": 10,
                    "summary": "B1",
                },
            },
            {
                "key": "P3",
                "fields": {
                    "assignee": {"id": student_c.id},
                    "customfield_10009": 10,
                    "summary": "C1",
                },
            },
        ]
    }

    run = JiraIngestionRunRecord(
        id="run-2",
        course_id=course.id,
        project_id="proj-jira-1",
        sprint_id=None,
        jira_project_key="PROJ",
        jql="project = PROJ",
        raw_bucket="raw/b",
        raw_object_key="obj",
        issue_count=3,
        captured_at=datetime.now(UTC),
        cleaned_snapshot=cleaned,
    )
    jira_repo.create_run(run)

    _override_repos(project_repo, user_repo, jira_repo)

    try:
        faculty_token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {faculty_token}"}

        resp = client.get(
            f"/api/v1/jira/contribution-outliers/courses/{course.id}/students/{sa.id}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        outlier = JiraContributionOutlierResponse(**data)

        # Student A: 1 ticket, 1 point total.
        # Course totals: [1, 10, 10] → mean = 7, pstdev = sqrt(18) ≈ 4.24
        assert outlier.total_tickets == 1
        assert outlier.total_story_points == 1
        assert outlier.course_average_total_points == 7.0
        assert outlier.course_total_score_std_dev == 4.24
        # z = (1-7)/4.24 ≈ -1.41 → outlier, below the mean
        assert outlier.contribution_z_score == -1.41
        assert outlier.is_contribution_outlier is True
        assert outlier.outlier_direction == "low"

        assert outlier.students_below_course_average == 1
        assert outlier.enrolled_student_count == 3
        assert [ticket.ticket_id for ticket in outlier.tickets] == ["P1"]

    finally:
        _clear_overrides()


def test_outlier_flag_and_direction_when_high():
    """
    Symmetric test: student above the course mean should have
    `outlier_direction="high"`.
    """
    project_repo, course, user_repo, sa, sb = _setup_course_with_project()

    jira_repo = InMemoryJiraIngestionRunRepository()

    # Student A gets many points, student B few
    cleaned = {
        "issues": [
            {
                "key": "P1",
                "fields": {
                    "assignee": {"id": sa.id},
                    "customfield_10009": 10,
                    "summary": "A1",
                },
            },
            {
                "key": "P2",
                "fields": {
                    "assignee": {"id": sb.id},
                    "customfield_10009": 1,
                    "summary": "B1",
                },
            },
        ]
    }

    run = JiraIngestionRunRecord(
        id="run-3",
        course_id=course.id,
        project_id="proj-jira-1",
        sprint_id=None,
        jira_project_key="PROJ",
        jql="project = PROJ",
        raw_bucket="raw/b",
        raw_object_key="obj",
        issue_count=2,
        captured_at=datetime.now(UTC),
        cleaned_snapshot=cleaned,
    )
    jira_repo.create_run(run)

    _override_repos(project_repo, user_repo, jira_repo)

    try:
        faculty_token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {faculty_token}"}

        resp = client.get(
            f"/api/v1/jira/contribution-outliers/courses/{course.id}/students/{sa.id}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        outlier = JiraContributionOutlierResponse(**data)

        # A: 1 ticket, 10 points. B: 1 ticket, 1 point. Mean = 5.5, pstdev = 4.5
        assert outlier.total_story_points == 10
        assert outlier.course_average_total_points == 5.5
        assert outlier.course_total_score_std_dev == 4.5
        # z = (10‑5.5)/4.5 ≈ 1.0 → outlier = True, direction high
        assert outlier.contribution_z_score == 1.0
        assert outlier.is_contribution_outlier is True
        assert outlier.outlier_direction == "high"

    finally:
        _clear_overrides()


def _add_third_student(project_repo, user_repo, course):
    student_c = UserRecord(
        id="u-student-c",
        email="student.c@sprintsight.edu",
        full_name="Student C",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=103,
    )
    user_repo.create_user(student_c)
    project_repo.set_members(
        "proj-jira-1", ["u-student-a", "u-student-b", student_c.id]
    )
    project_repo.enroll_student(course.id, student_c.id)
    return student_c


def test_course_report_lists_students_and_filters_outliers():
    """The course endpoint returns every student, evidence, and a filtered view."""
    project_repo, course, user_repo, sa, sb = _setup_course_with_project()
    student_c = _add_third_student(project_repo, user_repo, course)

    jira_repo = InMemoryJiraIngestionRunRepository()
    cleaned = {
        "issues": [
            {
                "key": "P1",
                "fields": {
                    "assignee": {"id": sa.id},
                    "customfield_10009": 1,
                    "summary": "A1",
                },
            },
            {
                "key": "P2",
                "fields": {
                    "assignee": {"id": sb.id},
                    "customfield_10009": 10,
                    "summary": "B1",
                },
            },
            {
                "key": "P3",
                "fields": {
                    "assignee": {"id": student_c.id},
                    "customfield_10009": 10,
                    "summary": "C1",
                },
            },
        ]
    }
    jira_repo.create_run(
        JiraIngestionRunRecord(
            id="run-course",
            course_id=course.id,
            project_id="proj-jira-1",
            sprint_id=None,
            jira_project_key="PROJ",
            jql="project = PROJ",
            raw_bucket="raw/b",
            raw_object_key="obj",
            issue_count=3,
            captured_at=datetime.now(UTC),
            cleaned_snapshot=cleaned,
        )
    )
    _override_repos(project_repo, user_repo, jira_repo)

    try:
        headers = {"Authorization": f"Bearer {_token_for('faculty@sprintsight.edu')}"}
        resp = client.get(
            f"/api/v1/jira/contribution-outliers/courses/{course.id}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        report = JiraContributionOutlierReport(**resp.json())

        assert report.enrolled_student_count == 3
        assert report.students_with_jira_data == 3
        assert report.outlier_count == 1
        assert [student.student_id for student in report.students] == [
            sb.id,
            student_c.id,
            sa.id,
        ]
        low_outlier = report.students[-1]
        assert low_outlier.outlier_direction == "low"
        assert [ticket.ticket_id for ticket in low_outlier.tickets] == ["P1"]

        filtered = client.get(
            f"/api/v1/jira/contribution-outliers/courses/{course.id}",
            params={"only_outliers": True},
            headers=headers,
        )
        assert filtered.status_code == 200, filtered.text
        filtered_report = JiraContributionOutlierReport(**filtered.json())
        assert [student.student_id for student in filtered_report.students] == [sa.id]
        assert filtered_report.outlier_count == 1
    finally:
        _clear_overrides()


def test_normalized_snapshot_matches_assignee_display_name():
    """Normalized snapshots store display names, which must map to student ids."""
    project_repo, course, user_repo, sa, sb = _setup_course_with_project()

    snapshot = JiraCleanedSnapshot(
        normalization_version="jira-ticket-v1",
        jira_project_key="PROJ",
        course_id=course.id,
        project_id="proj-jira-1",
        sprint_id="Sprint 1",
        captured_at=datetime.now(UTC),
        tickets=[
            JiraTicket(
                ticket_id="PROJ-1",
                summary="Implement login",
                assignee="Student A",
                story_points=5,
            ),
            JiraTicket(
                ticket_id="PROJ-2",
                summary="Fix typo",
                assignee="Student B",
                story_points=2,
            ),
        ],
    )
    jira_repo = InMemoryJiraIngestionRunRepository()
    jira_repo.create_run(
        JiraIngestionRunRecord(
            id="run-normalized",
            course_id=course.id,
            project_id="proj-jira-1",
            sprint_id="Sprint 1",
            jira_project_key="PROJ",
            jql="project = PROJ",
            raw_bucket="raw/b",
            raw_object_key="obj",
            issue_count=2,
            captured_at=datetime.now(UTC),
            cleaned_snapshot=snapshot,
        )
    )
    _override_repos(project_repo, user_repo, jira_repo)

    try:
        headers = {"Authorization": f"Bearer {_token_for('faculty@sprintsight.edu')}"}
        resp = client.get(
            f"/api/v1/jira/contribution-outliers/courses/{course.id}/students/{sa.id}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        outlier = JiraContributionOutlierResponse(**resp.json())
        assert outlier.total_story_points == 5
        assert outlier.total_tickets == 1
        assert outlier.tickets[0].ticket_id == "PROJ-1"
    finally:
        _clear_overrides()
