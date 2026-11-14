"""Shared builders for the AI Insights tests (in-memory repositories, fake MLflow gateway)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.dependencies.auth import get_assessment_repository
from app.dependencies.insights import (
    get_insights_repository,
    get_mlflow_gateway,
    get_optional_insights_repository,
)
from app.main import app
from app.repositories.insights import DIMENSIONS, InMemoryInsightsRepository
from app.repositories.interfaces import ProjectRecord
from app.schemas.assessment import AssessmentReport, RubricDimensionScoreDetail, TeamScore
from app.services.insightsService.fake_gateway import FakeMlflowGateway
from app.services.insightsService.trace_summary import JudgeAssessment, SpanTiming, TraceSummary

client = TestClient(app)
API = "/api/v1/insights"
FACULTY = "faculty@sprintsight.edu"
ADMIN = "admin@sprintsight.edu"
STUDENT = "student@sprintsight.edu"
# The AI's original scores used by most tests; testing is 6 so overrides have a visible gap.
AI_SCORES = {**dict.fromkeys(DIMENSIONS, 7.0), "testing": 6.0}


def headers(email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def six(score: int = 8) -> dict:
    return {"labels": [{"dimension": d, "score": score, "reason": "Looked at commits"} for d in DIMENSIONS]}


def override_patch(requirements: float = 50.0, testing: float = 4.0) -> dict:
    """Body of the Assessment Report editor's PATCH: four typed fields on 0-100, testing in
    rubric_scores on 1-10 (the UI divides it by 10 before sending)."""
    return {
        "requirements_score": requirements,
        "code_quality_score": 70.0,
        "documentation_score": 70.0,
        "collaboration_score": 70.0,
        "requirements_justification": "Reviewed",
        "code_quality_justification": "Reviewed",
        "documentation_justification": "Reviewed",
        "collaboration_justification": "Reviewed",
        "rubric_scores": {"testing": {"score": testing, "justification": "Reviewed"}},
    }


def make_report(report_id, course_id, project_id, *, trace_id=None, scores=None, original=None,
                override=False) -> AssessmentReport:
    scores = scores or dict(AI_SCORES)
    return AssessmentReport(
        report_id=report_id, model_name="sprintsight-qwen", mode="test", course_id=course_id,
        project_id=project_id, sprint_id="sprint-1", generated_at=datetime.now(UTC),
        rubric_weights=dict.fromkeys(DIMENSIONS, 1 / 6), team_score=TeamScore(score=70, rationale="AI"),
        individual_scores=[], recommendations=[], override=override,
        rubric_scores={d: RubricDimensionScoreDetail(score=s, justification="AI justification")
                       for d, s in scores.items()},
        trace_id=trace_id, ai_rubric_scores_original=original,
    )


def judged_summary(trace_id: str) -> TraceSummary:
    return TraceSummary(
        trace_id=trace_id, duration_ms=90_000, llm_call_count=7,
        spans=(SpanTiming("Evaluate_Complete_Sprint", None, 0, 90_000, "OK"),
               SpanTiming("Evaluate_Dimension_testing", "Evaluate_Complete_Sprint", 10, 12_000, "OK")),
        assessments=(
            JudgeAssessment("citation_hallucination_rate", 0.25, "LLM_JUDGE",
                            rationale="C2 [testing] hallucinated/major_misattribution: Commit abc123 is not in the bundle."),
            JudgeAssessment("citation_grounded_rate", 0.75, "LLM_JUDGE"),
            JudgeAssessment("narrative_contradiction_count", 1.0, "LLM_JUDGE"),
            JudgeAssessment("citations_dropped_by_code", 0.0, "CODE"),
        ),
        prompt_versions={"Evaluate_testing": "3"},
        claims={"C1": "a1 | ok", "C2": "abc123 | Added tests"},
    )


def _project(pid, course_id, team) -> ProjectRecord:
    return ProjectRecord(id=pid, project_name=team, team_name=team, description=None, course_id=course_id,
                         course_code="CS480", github_repo_url=None, local_repo_path=None,
                         created_by="u-admin-1", created_at=datetime.now(UTC))


def build_env(projects, monkeypatch, mode: str):
    """Reports: r-in (in the faculty member's course, traced), r-out (another course) and
    r-ovr (already overridden, original AI scores all 5). Returns a namespace; callers must
    call env.cleanup() afterwards."""
    monkeypatch.setattr(get_settings(), "insights_mode", mode)
    assessments = app.dependency_overrides[get_assessment_repository]()
    course_in = projects.create_course("CS480", "Capstone", "G1", 2026, "T1", "u-faculty-1")
    course_out = projects.create_course("CS480", "Capstone", "G2", 2026, "T1", "u-admin-1")
    projects.create_project(_project("p-in", course_in.id, "Team In"), ["u-student-1"])
    projects.create_project(_project("p-out", course_out.id, "Team Out"), [])
    assessments.save_report(make_report("r-in", course_in.id, "p-in", trace_id="tr-1",
                                        original=dict(AI_SCORES)))
    assessments.save_report(make_report("r-out", course_out.id, "p-out", trace_id="tr-2",
                                        original=dict(AI_SCORES)))
    assessments.save_report(make_report("r-ovr", course_in.id, "p-in", scores=dict.fromkeys(DIMENSIONS, 9),
                                        original=dict.fromkeys(DIMENSIONS, 5.0), override=True))
    insights = InMemoryInsightsRepository(assessments, projects)
    gateway = FakeMlflowGateway()
    gateway.traces["tr-1"] = judged_summary("tr-1")
    app.dependency_overrides[get_insights_repository] = lambda: insights
    app.dependency_overrides[get_optional_insights_repository] = lambda: insights
    app.dependency_overrides[get_mlflow_gateway] = lambda: gateway

    def cleanup():
        for dependency in (get_insights_repository, get_optional_insights_repository, get_mlflow_gateway):
            app.dependency_overrides.pop(dependency, None)

    return SimpleNamespace(insights=insights, gateway=gateway, assessments=assessments,
                           course_in=course_in, cleanup=cleanup)
