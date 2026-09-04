from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.repositories.in_memory import assessment_repo, metrics_repo, overrides_repo
from app.repositories.interfaces import MetricsRepository
from app.schemas.assessment import AssessRequest, AssessmentReport, OverrideRequest, OverrideResponse, StudentScore, TeamScore
from app.services.middleManService.service import request_ai_assessment


RUBRIC_WEIGHTS = {
    "delivery": 0.35,
    "collaboration": 0.30,
    "quality": 0.20,
    "documentation": 0.15,
}


def generate_mock_assessment(payload: AssessRequest, metrics_repository: MetricsRepository | None = None) -> AssessmentReport:
    metrics = (metrics_repository or metrics_repo).get_metrics(payload.course_id, payload.project_id, payload.sprint_id)
    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ingestion metrics found. Trigger ingestion first.",
        )

    base_score = min(
        100.0,
        ((metrics.completion_percent or 0.0) * 0.45)
        + (metrics.commit_frequency * 1.2)
        + ((100.0 - (metrics.pr_turnaround_hours or 0.0)) * 0.25),
    )

    team_score_value = round(base_score, 2)
    report = AssessmentReport(
        report_id=f"rpt-{uuid4().hex[:12]}",
        model_name=get_settings().default_model_name,
        mode=get_settings().assessment_mode,
        course_id=payload.course_id,
        project_id=payload.project_id,
        sprint_id=payload.sprint_id,
        generated_at=datetime.now(timezone.utc),
        rubric_weights=RUBRIC_WEIGHTS,
        team_score=TeamScore(
            score=team_score_value,
            rationale="Mock score generated from sprint throughput and collaboration metrics.",
        ),
        individual_scores=[
            StudentScore(
                student_id="stu-001",
                score=round(max(0.0, team_score_value - 2.5), 2),
                rationale="Consistent contribution across commit and review signals.",
            ),
            StudentScore(
                student_id="stu-002",
                score=round(min(100.0, team_score_value + 1.5), 2),
                rationale="High task completion with strong collaborative responsiveness.",
            ),
        ],
        recommendations=[
            "Increase peer review turnaround predictability.",
            "Improve documentation coverage for sprint demo artifacts.",
        ],
    )
    assessment_repo.save_report(report)
    return report


async def generate_ai_assessment(
    payload: AssessRequest,
    ai_payload: dict,
) -> AssessmentReport:
    settings = get_settings()
    ai_result = await request_ai_assessment(ai_payload, payload.model_name)

    report = AssessmentReport(
        report_id=f"rpt-{uuid4().hex[:12]}",
        model_name=payload.model_name or settings.default_model_name,
        mode="ai",
        course_id=payload.course_id,
        project_id=payload.project_id,
        sprint_id=payload.sprint_id,
        generated_at=datetime.now(timezone.utc),
        rubric_weights=RUBRIC_WEIGHTS,
        team_score=TeamScore(
            score=round(float(ai_result["overall_score"]) * 10, 2),
            rationale=ai_result["executive_summary"],
        ),
        individual_scores=[],
        recommendations=ai_result.get("key_recommendations", []),
    )
    assessment_repo.save_report(report)
    return report


def get_latest_assessment(course_id: str, project_id: str, sprint_id: str) -> AssessmentReport:
    report = assessment_repo.get_latest_report(course_id, project_id, sprint_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment report not found.")
    return report


def override_student_score(payload: OverrideRequest, instructor_id: str) -> OverrideResponse:
    report = assessment_repo.get_report(payload.report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    original_entry = next((x for x in report.individual_scores if x.student_id == payload.student_id), None)
    if not original_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student score not found in report.")

    override_record = OverrideResponse(
        override_id=f"ovr-{uuid4().hex[:12]}",
        report_id=payload.report_id,
        student_id=payload.student_id,
        original_score=original_entry.score,
        new_score=payload.new_score,
        reason_comment=payload.reason_comment,
        instructor_id=instructor_id,
        created_at=datetime.now(timezone.utc),
    )
    original_entry.score = payload.new_score
    overrides_repo.save_override(override_record)
    assessment_repo.save_report(report)
    return override_record
