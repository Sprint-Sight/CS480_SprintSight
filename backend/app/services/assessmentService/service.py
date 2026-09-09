from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.repositories.in_memory import assessment_repo, job_repo, metrics_repo, overrides_repo
from app.repositories.interfaces import ManualTextRepository, MetricsRepository, ProjectRepository
from app.schemas.assessment import AssessRequest, AssessmentReport, OverrideRequest, OverrideResponse, StudentScore, TeamScore
from app.services.documentsService.service import collect_document_signals
from app.services.gitlabGithub.service import ingest_github_metrics, resolve_local_repository_path
from app.services.jiraService.service import enrich_jira_metrics
from app.services.manualTextService.service import get_manual_text
from app.services.middleManService.service import build_assessment_payload, send_assessment_to_ai_engine


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


def run_assessment_job(job_id: str, payload: AssessRequest, project, metrics_repository: MetricsRepository, manual_text_repository: ManualTextRepository) -> None:
    """Background worker that collects the same input that the old synchronous endpoint used,
    sends the canonical payload to the AI engine, and then persists a report without
    tying up the API request thread.
    """
    try:
        job_repo.update_job(job_id, status="collecting_data", progress=10, current_stage="collecting_data")
        job_repo.append_event(job_id, "progress", {"status": "collecting_data", "progress": 10, "message": "Collecting sprint data."})

        if not project.local_repo_path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project has no local repository configured.")
        try:
            repository_path = resolve_local_repository_path(project.local_repo_path)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        job_repo.update_job(job_id, status="collecting_data", progress=30, current_stage="collecting_data")
        metrics = ingest_github_metrics(payload, repository_path, metrics_repository)
        _ = enrich_jira_metrics(payload)
        docs = collect_document_signals(payload)
        manual_text = get_manual_text(manual_text_repository, payload.course_id, payload.project_id, payload.sprint_id)

        job_repo.update_job(job_id, status="building_payload", progress=50, current_stage="building_payload")
        job_repo.append_event(job_id, "progress", {"status": "building_payload", "progress": 50, "message": "Building AI payload."})
        middle_man_payload = build_assessment_payload(metrics, docs, manual_text)

        job_repo.update_job(job_id, status="ai_evaluating", progress=70, current_stage="ai_evaluating")
        job_repo.append_event(job_id, "progress", {"status": "ai_evaluating", "progress": 70, "message": "AI is evaluating the sprint."})
        ai_result = send_assessment_to_ai_engine(middle_man_payload, payload.model_name)

        job_repo.update_job(job_id, status="saving_report", progress=90, current_stage="saving_report")
        job_repo.append_event(job_id, "progress", {"status": "saving_report", "progress": 90, "message": "Saving assessment report."})
        report = generate_mock_assessment(payload, metrics_repository)

        job_repo.update_job(job_id, status="completed", progress=100, current_stage="completed", report_id=report.report_id)
        job_repo.append_event(job_id, "completed", {"status": "completed", "progress": 100, "report_id": report.report_id})
    except Exception as exc:
        error_message = str(exc)
        job_repo.update_job(job_id, status="failed", progress=100, current_stage="failed", error_message=error_message)
        job_repo.append_event(job_id, "failed", {"status": "failed", "message": "The assessment failed.", "error_message": error_message})


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
