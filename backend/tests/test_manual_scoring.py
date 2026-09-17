from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.dependencies.auth import get_assessment_repository
from app.main import app
from app.repositories.in_memory import InMemoryAssessmentRepository
from app.schemas.assessment import AssessmentReport, StudentScore, TeamScore

client = TestClient(app)


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(email)}"}


def setup_project(repository) -> None:
    from app.repositories.interfaces import ProjectRecord

    repository.create_project(
        ProjectRecord(
            id="manual-project",
            project_name="Manual Project",
            team_name="Manual Team",
            description=None,
            course_id="manual-course",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        ["u-student-1"],
    )
    repository.assign_instructor("manual-course", "u-faculty-1")


def report() -> AssessmentReport:
    return AssessmentReport(
        report_id="rpt-manual-1",
        model_name="test-model",
        mode="test",
        course_id="manual-course",
        project_id="manual-project",
        sprint_id="sprint-1",
        generated_at=datetime.now(UTC),
        rubric_weights={"quality": 1.0},
        team_score=TeamScore(score=80, rationale="AI rationale"),
        individual_scores=[
            StudentScore(student_id="u-student-1", score=80, rationale="AI rationale")
        ],
        recommendations=["Keep testing"],
    )


def payload(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "requirements_score": 80,
        "code_quality_score": 90,
        "documentation_score": 100,
        "collaboration_score": 60,
        "requirements_justification": "Requirements were met.",
        "code_quality_justification": "Code is maintainable.",
        "documentation_justification": "Documentation is complete.",
        "collaboration_justification": "The team collaborated effectively.",
    }
    result.update(overrides)
    return result


def test_instructor_can_patch_assessment_report(override_user_repository) -> None:
    setup_project(override_user_repository)
    assessment_repository = InMemoryAssessmentRepository()
    assessment_repository.save_report(report())
    app.dependency_overrides[get_assessment_repository] = lambda: assessment_repository

    response = client.patch(
        "/api/v1/assessments/reports/rpt-manual-1",
        json=payload(),
        headers=headers("faculty@sprintsight.edu"),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["report_id"] == "rpt-manual-1"
    assert result["override"] is True
    assert result["requirements_score"] == 80
    assert result["team_score"]["rationale"] == "AI rationale"


def test_unassigned_instructor_cannot_patch_assessment_report(override_user_repository) -> None:
    setup_project(override_user_repository)
    assessment_repository = InMemoryAssessmentRepository()
    assessment_repository.save_report(report())
    app.dependency_overrides[get_assessment_repository] = lambda: assessment_repository

    response = client.patch(
        "/api/v1/assessments/reports/rpt-manual-1",
        json=payload(),
        headers=headers("admin@sprintsight.edu"),
    )

    assert response.status_code == 403


def test_patch_requires_valid_scores_and_justifications(override_user_repository) -> None:
    setup_project(override_user_repository)
    assessment_repository = InMemoryAssessmentRepository()
    assessment_repository.save_report(report())
    app.dependency_overrides[get_assessment_repository] = lambda: assessment_repository

    response = client.patch(
        "/api/v1/assessments/reports/rpt-manual-1",
        json=payload(requirements_score=101, documentation_justification=""),
        headers=headers("faculty@sprintsight.edu"),
    )

    assert response.status_code == 422


def test_missing_assessment_report_returns_not_found(override_user_repository) -> None:
    setup_project(override_user_repository)
    assessment_repository = InMemoryAssessmentRepository()
    app.dependency_overrides[get_assessment_repository] = lambda: assessment_repository

    response = client.patch(
        "/api/v1/assessments/reports/rpt-missing",
        json=payload(),
        headers=headers("faculty@sprintsight.edu"),
    )

    assert response.status_code == 404
