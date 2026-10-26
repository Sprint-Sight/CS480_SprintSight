"""Tests for the report export feature (PDF/CSV download for instructors)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.dependencies.auth import (
    get_assessment_repository,
    get_export_log_repository,
    get_project_repository,
    get_user_repository,
)
from app.main import app
from app.repositories.in_memory import (
    InMemoryAssessmentRepository,
    InMemoryExportLogRepository,
    InMemoryProjectRepository,
    InMemoryUserRepository,
)
from app.repositories.interfaces import (
    ProjectRecord,
    Role,
    UserRecord,
)
from app.schemas.assessment import (
    AssessmentReport,
    RubricDimensionScoreDetail,
    StudentScore,
    TeamScore,
)
from app.services.exportService.service import _EXPORT_STORE

client = TestClient(app)


def _token_for(email: str, password: str = "password123") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]

def _make_report(course_id: str, project_id: str, sprint_id: str) -> AssessmentReport:
    return AssessmentReport(
        report_id="rpt-export-1",
        model_name="test-model",
        mode="test",
        course_id=course_id,
        project_id=project_id,
        sprint_id=sprint_id,
        generated_at=datetime.now(UTC),
        rubric_weights={},
        team_score=TeamScore(score=85.0, rationale="Strong sprint delivery.", overall_grade="A"),
        individual_scores=[
            StudentScore(
                student_id="u-student-1",
                score=90.0,
                rationale="Great individual contribution.",
            )
        ],
        rubric_scores={
            "requirements": RubricDimensionScoreDetail(
                score=9.0, justification="Met all requirements.", evidence_citations=[]
            ),
            "code_quality": RubricDimensionScoreDetail(
                score=8.0, justification="Clean code.", evidence_citations=[]
            ),
        },
        strengths=["Delivery"],
        weaknesses=["Testing"],
        recommendations=["Add unit tests."],
    )


@pytest.fixture(autouse=True)
def _clear_export_store():
    _EXPORT_STORE.clear()
    yield
    _EXPORT_STORE.clear()


# ---------------------------------------------------------------------------
# Helpers to build a course + project owned by faculty@sprintsight.edu (u-faculty-1)
# ---------------------------------------------------------------------------

def _setup_course_and_project():
    """Create a course and project owned by the seeded faculty user."""
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    project_repository.create_project(
        ProjectRecord(
            id="proj-export",
            project_name="Export Project",
            team_name="Export Team",
            description=None,
            course_id=course.id,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        [],
    )
    return project_repository, course


def _override_repos(
    project_repository,
    assessment_repository,
    user_repository=None,
    export_log_repository=None,
):
    app.dependency_overrides[get_project_repository] = lambda: project_repository
    app.dependency_overrides[get_assessment_repository] = lambda: assessment_repository
    if user_repository is not None:
        app.dependency_overrides[get_user_repository] = lambda: user_repository
    if export_log_repository is not None:
        app.dependency_overrides[get_export_log_repository] = lambda: export_log_repository


def _clear_overrides():
    for dep in (
        get_project_repository,
        get_assessment_repository,
        get_user_repository,
        get_export_log_repository,
    ):
        app.dependency_overrides.pop(dep, None)


# ---------------------------------------------------------------------------
# GET /export/preview
# ---------------------------------------------------------------------------


def test_export_preview_returns_basic_assessment_data(override_user_repository) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(project_repository, assessment_repository)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/export/preview?course_id={course.id}&project_id=proj-export&sprint_id=sp1",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["report_id"] == "rpt-export-1"
        assert data["course_id"] == course.id
        assert data["project_id"] == "proj-export"
        assert data["sprint_id"] == "sp1"
        assert data["team_score"] == 85.0
        assert data["team_grade"] == "A"
        assert data["student_count"] == 1
        assert data["recommendation_count"] == 1
    finally:
        _clear_overrides()


def test_export_preview_404_when_no_report(override_user_repository) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()

    _override_repos(project_repository, assessment_repository)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/export/preview?course_id={course.id}&project_id=proj-export&sprint_id=sp1",
            headers=headers,
        )
        assert response.status_code == 404, response.text
    finally:
        _clear_overrides()


def test_export_preview_403_when_not_assigned_to_course(override_user_repository) -> None:
    """An instructor who is not assigned to the course gets 403."""
    project_repository = InMemoryProjectRepository()
    assessment_repository = InMemoryAssessmentRepository()

    # A different instructor (u-other-instr) owns the course; faculty@sprintsight.edu
    # (u-faculty-1) is not assigned to it.
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-other-instr",
    )
    project_repository.create_project(
        ProjectRecord(
            id="proj-export",
            project_name="Export Project",
            team_name="Export Team",
            description=None,
            course_id=course.id,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by="u-other-instr",
            created_at=datetime.now(UTC),
        ),
        [],
    )
    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(project_repository, assessment_repository)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/export/preview?course_id={course.id}&project_id=proj-export&sprint_id=sp1",
            headers=headers,
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# POST /export/pdf and POST /export/csv
# ---------------------------------------------------------------------------


def test_export_pdf_generates_download_url_and_logs_export(
    override_user_repository,
) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()
    user_repository = InMemoryUserRepository()

    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(
        project_repository,
        assessment_repository,
        user_repository=user_repository,
        export_log_repository=export_log_repository,
    )

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/export/pdf",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "pdf",
                "include_student_emails": False,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["format"] == "pdf"
        assert data["report_id"] == "rpt-export-1"
        assert data["include_student_emails"] is False
        assert data["download_url"].startswith("/api/v1/export/download/")
        assert data["file_size_bytes"] > 0

        # Verify the download link expires after 1 hour.
        expires_at = datetime.fromisoformat(data["expires_at"])
        expected_expiry = datetime.now(UTC) + timedelta(hours=1)
        assert abs((expires_at - expected_expiry).total_seconds()) < 10

        # Verify export was logged.
        logs = export_log_repository.list_logs("u-faculty-1")
        assert len(logs) == 1
        assert logs[0].user_id == "u-faculty-1"
        assert logs[0].report_type == "pdf"
        assert logs[0].course_id == course.id
        assert logs[0].project_id == "proj-export"
        assert logs[0].sprint_id == "sp1"
        assert logs[0].include_student_emails is False

        # Verify the file is in the store and is valid PDF.
        download_token = data["download_url"].split("/")[-1]
        assert download_token in _EXPORT_STORE
        file_bytes, _, fmt = _EXPORT_STORE[download_token]
        assert fmt.value == "pdf"
        assert file_bytes.startswith(b"%PDF")
    finally:
        _clear_overrides()


def test_export_csv_generates_download_url(override_user_repository) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()
    user_repository = InMemoryUserRepository()

    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(
        project_repository,
        assessment_repository,
        user_repository=user_repository,
        export_log_repository=export_log_repository,
    )

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/export/csv",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "csv",
                "include_student_emails": True,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["format"] == "csv"
        assert data["include_student_emails"] is True

        download_token = data["download_url"].split("/")[-1]
        file_bytes, _, fmt = _EXPORT_STORE[download_token]
        assert fmt.value == "csv"
        content = file_bytes.decode("utf-8")
        assert "rpt-export-1" in content
        assert "85.0" in content
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Rate limiting: 5 exports per minute
# ---------------------------------------------------------------------------


def test_export_rate_limit_caps_at_five_per_minute(override_user_repository) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()

    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(
        project_repository,
        assessment_repository,
        export_log_repository=export_log_repository,
    )

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        # First 5 exports should succeed.
        for i in range(5):
            response = client.post(
                "/api/v1/export/pdf",
                json={
                    "course_id": course.id,
                    "project_id": "proj-export",
                    "sprint_id": "sp1",
                    "format": "pdf",
                    "include_student_emails": False,
                },
                headers=headers,
            )
            assert response.status_code == 200, f"Export {i+1} failed: {response.text}"

        # 6th export should be rate-limited.
        response = client.post(
            "/api/v1/export/pdf",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "pdf",
                "include_student_emails": False,
            },
            headers=headers,
        )
        assert response.status_code == 429, response.text
        assert "rate limit" in response.text.lower()
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Download link: expiry and access control
# ---------------------------------------------------------------------------


def test_export_download_returns_file_with_correct_headers(
    override_user_repository,
) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()
    user_repository = InMemoryUserRepository()

    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(
        project_repository,
        assessment_repository,
        user_repository=user_repository,
        export_log_repository=export_log_repository,
    )

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/v1/export/pdf",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "pdf",
                "include_student_emails": False,
            },
            headers=headers,
        )
        assert response.status_code == 200
        download_url = response.json()["download_url"]

        # Download the file.
        download_response = client.get(download_url, headers=headers)
        assert download_response.status_code == 200, download_response.text
        assert download_response.headers["content-type"] == "application/pdf"
        assert "attachment;" in download_response.headers.get("content-disposition", "")
        assert download_response.content.startswith(b"%PDF")
        assert "X-Export-Expires-At" in download_response.headers
    finally:
        _clear_overrides()


def test_export_download_403_for_non_creator(override_user_repository) -> None:
    """A different instructor cannot download another's export.

    Creates a second instructor user, exports as faculty, then verifies
    that the export log records the correct creator user_id.
    """
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()
    user_repository = InMemoryUserRepository()

    # Second instructor user with a known password.
    other_instructor = UserRecord(
        id="u-other-instr-2",
        email="other2.instr@sprintsight.edu",
        full_name="Other Instructor 2",
        role=Role.INSTRUCTOR,
        hashed_password=hash_password("password123"),
    )
    user_repository.create_user(other_instructor)
    project_repository.assign_instructor(course.id, "u-other-instr-2")

    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(
        project_repository,
        assessment_repository,
        user_repository=user_repository,
        export_log_repository=export_log_repository,
    )

    try:
        creator_token = _token_for("faculty@sprintsight.edu")
        creator_headers = {"Authorization": f"Bearer {creator_token}"}

        response = client.post(
            "/api/v1/export/pdf",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "pdf",
                "include_student_emails": False,
            },
            headers=creator_headers,
        )
        assert response.status_code == 200, response.text
        download_url = response.json()["download_url"]

        # Verify the export was logged with the creator's user_id.
        logs = export_log_repository.list_logs("u-faculty-1")
        assert len(logs) == 1
        assert logs[0].user_id == "u-faculty-1"
        assert logs[0].report_type == "pdf"

        # The other instructor cannot download this export.
        other_token = _token_for("other2.instr@sprintsight.edu")
        other_headers = {"Authorization": f"Bearer {other_token}"}
        download_response = client.get(download_url, headers=other_headers)
        assert download_response.status_code == 403, download_response.text

        # Admin can download.
        admin_token = _token_for("admin@sprintsight.edu")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        download_response = client.get(download_url, headers=admin_headers)
        assert download_response.status_code == 200, download_response.text
    finally:
        _clear_overrides()


def test_export_download_410_when_expired(override_user_repository) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()
    user_repository = InMemoryUserRepository()

    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(
        project_repository,
        assessment_repository,
        user_repository=user_repository,
        export_log_repository=export_log_repository,
    )

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/v1/export/pdf",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "pdf",
                "include_student_emails": False,
            },
            headers=headers,
        )
        download_url = response.json()["download_url"]

        # Manually expire the log entry.
        download_token = download_url.split("/")[-1]
        log = export_log_repository.get_log(download_token)
        assert log is not None
        log.expires_at = datetime.now(UTC) - timedelta(hours=1)

        download_response = client.get(download_url, headers=headers)
        assert download_response.status_code == 410, download_response.text
    finally:
        _clear_overrides()


def test_export_pdf_generates_valid_pdf(override_user_repository) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()
    user_repository = InMemoryUserRepository()

    report = _make_report(course.id, "proj-export", "sp1")
    assessment_repository.save_report(report)

    _override_repos(
        project_repository,
        assessment_repository,
        user_repository=user_repository,
        export_log_repository=export_log_repository,
    )

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/v1/export/pdf",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "pdf",
                "include_student_emails": False,
            },
            headers=headers,
        )
        download_url = response.json()["download_url"]
        download_token = download_url.split("/")[-1]
        file_bytes, _, _ = _EXPORT_STORE[download_token]
        assert file_bytes.startswith(b"%PDF")
        assert len(file_bytes) > 100  # non-trivial PDF with content
    finally:
        _clear_overrides()


def test_export_404_when_no_report_found(override_user_repository) -> None:
    project_repository, course = _setup_course_and_project()
    assessment_repository = InMemoryAssessmentRepository()
    export_log_repository = InMemoryExportLogRepository()
    user_repository = InMemoryUserRepository()

    _override_repos(
        project_repository,
        assessment_repository,
        user_repository=user_repository,
        export_log_repository=export_log_repository,
    )

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/export/pdf",
            json={
                "course_id": course.id,
                "project_id": "proj-export",
                "sprint_id": "sp1",
                "format": "pdf",
                "include_student_emails": False,
            },
            headers=headers,
        )
        assert response.status_code == 404, response.text
    finally:
        _clear_overrides()
