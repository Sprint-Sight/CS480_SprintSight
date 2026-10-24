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
    assert result["rubric_scores"]["requirements"]["score"] == 80
    assert result["rubric_scores"]["requirements"]["justification"] == "Requirements were met."


def test_patch_persists_all_report_content_edits(override_user_repository) -> None:
    setup_project(override_user_repository)
    assessment_repository = InMemoryAssessmentRepository()
    assessment_repository.save_report(report())
    app.dependency_overrides[get_assessment_repository] = lambda: assessment_repository

    edits = {
        **payload(),
        "rubric_weights": {"requirements": 0.5, "quality": 0.5},
        "team_score": {"score": 91, "rationale": "Updated overall rationale", "overall_grade": "A"},
        "individual_scores": [
            {"student_id": "u-student-1", "score": 92, "rationale": "Updated contribution"}
        ],
        "rubric_scores": {
            "requirements": {
                "score": 95,
                "justification": "Updated criterion feedback",
                "evidence_citations": ["commit:abc123"],
            },
            "testing": {
                "score": 88,
                "justification": "Regression coverage is strong.",
                "evidence_citations": ["tests/test_api.py"],
            },
            "cicd": {
                "score": 76,
                "justification": "Pipeline is configured but lacks deployment checks.",
                "evidence_citations": [".github/workflows/ci.yml"],
            },
        },
        "strengths": ["Strong delivery"],
        "weaknesses": ["Needs more tests"],
        "recommendations": ["Add regression tests"],
    }

    response = client.patch(
        "/api/v1/assessments/reports/rpt-manual-1",
        json=edits,
        headers=headers("faculty@sprintsight.edu"),
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["rubric_weights"] == edits["rubric_weights"]
    assert result["team_score"]["rationale"] == "Updated overall rationale"
    assert result["individual_scores"][0]["rationale"] == "Updated contribution"
    assert result["rubric_scores"]["requirements"]["evidence_citations"] == ["commit:abc123"]
    assert result["strengths"] == ["Strong delivery"]
    assert result["weaknesses"] == ["Needs more tests"]
    assert result["recommendations"] == ["Add regression tests"]
    assert result["requirements_score"] == 80
    assert result["rubric_scores"]["requirements"]["score"] == 95
    assert result["rubric_scores"]["requirements"]["justification"] == "Updated criterion feedback"
    assert result["rubric_scores"]["testing"]["score"] == 88
    assert result["rubric_scores"]["testing"]["justification"] == "Regression coverage is strong."
    assert result["rubric_scores"]["cicd"]["score"] == 76
    assert result["rubric_scores"]["cicd"]["justification"] == "Pipeline is configured but lacks deployment checks."

    reloaded = client.get(
        "/api/v1/assessments/latest?course_id=manual-course&project_id=manual-project&sprint_id=sprint-1",
        headers=headers("faculty@sprintsight.edu"),
    )
    assert reloaded.status_code == 200, reloaded.text
    reloaded_report = reloaded.json()
    assert reloaded_report["team_score"]["rationale"] == "Updated overall rationale"
    assert reloaded_report["rubric_scores"]["testing"]["justification"] == "Regression coverage is strong."
    assert reloaded_report["rubric_scores"]["cicd"]["score"] == 76
    assert reloaded_report["strengths"] == ["Strong delivery"]
    assert reloaded_report["weaknesses"] == ["Needs more tests"]
    assert reloaded_report["recommendations"] == ["Add regression tests"]


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
