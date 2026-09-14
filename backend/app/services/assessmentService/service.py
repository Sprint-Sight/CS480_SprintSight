from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.repositories.in_memory import assessment_repo, job_repo, metrics_repo, overrides_repo
from app.repositories.interfaces import AssessmentRepository, ManualTextRepository, MetricsRepository, ProjectRepository
from app.schemas.assessment import (
    AssessRequest,
    AssessmentReport,
    OverrideRequest,
    OverrideResponse,
    RubricDimensionScoreDetail,
    StudentScore,
    TeamScore,
)
from app.services.documentsService.service import collect_document_signals
from app.services.gitlabGithub.service import ingest_github_metrics, resolve_local_repository_path
from app.services.jiraService.service import enrich_jira_metrics
from app.services.manualTextService.service import get_manual_text
from app.services.middleManService.service import build_assessment_payload, send_assessment_to_ai_engine


def convert_ai_result_to_assessment_report(payload: AssessRequest | dict, ai_result: dict) -> AssessmentReport:
    """Shape the AI engine's SprintAssessment JSON into the backend report contract."""
    if isinstance(payload, dict):
        course_id = payload.get("course_id", "")
        project_id = payload.get("project_id", "")
        sprint_id = payload.get("sprint_id", "")
        model_name = payload.get("model_name")
    else:
        course_id = payload.course_id
        project_id = payload.project_id
        sprint_id = payload.sprint_id
        model_name = payload.model_name

    overall_score = ai_result.get("overall_score")
    if isinstance(overall_score, int):
        team_score_value = round(overall_score * 10, 2)
    elif isinstance(overall_score, float):
        team_score_value = round(overall_score * 10, 2)
    else:
        team_score_value = 0.0

    individual_scores = []
    for member in ai_result.get("member_contributions", []) or []:
        if isinstance(member, dict):
            student_id = member.get("student_id")
            contribution_score = member.get("contribution_score")
            if not student_id:
                continue
            score = round((contribution_score or 0) * 10, 2)
            rational_text = " | ".join(member.get("primary_contributions") or [])
            if member.get("evidence"):
                rational_text = rational_text + " Evidence: " + " | ".join(member.get("evidence") or [])
            individual_scores.append(
                StudentScore(
                    student_id=str(student_id),
                    score=score,
                    rationale=rational_text or "AI-generated member contribution assessment.",
                )
            )

    rubric_scores = {}
    strengths = []
    weaknesses = []
    raw_scores = ai_result.get("rubric_scores") or {}
    if isinstance(raw_scores, dict):
        for dimension, detail in raw_scores.items():
            if isinstance(detail, dict):
                dimension_name = str(detail.get("dimension") or dimension)
                score = detail.get("score")
                if isinstance(score, int):
                    normalized_score = float(score)
                elif isinstance(score, float):
                    normalized_score = score
                else:
                    normalized_score = 0.0

                evidence = detail.get("evidence_citations") or []
                strength_values = detail.get("strengths") or []
                weakness_values = detail.get("areas_for_improvement") or detail.get("weaknesses") or []

                rubric_scores[dimension_name] = RubricDimensionScoreDetail(
                    score=normalized_score,
                    justification=detail.get("justification") or "AI-generated rubric justification.",
                    evidence_citations=list(evidence) if isinstance(evidence, list) else [str(evidence)],
                )

                if isinstance(strength_values, list):
                    strengths.extend(strength_values)
                elif strength_values:
                    strengths.append(str(strength_values))

                if isinstance(weakness_values, list):
                    weaknesses.extend(weakness_values)
                elif weakness_values:
                    weaknesses.append(str(weakness_values))

    recommendations = list(ai_result.get("key_recommendations") or [])
    if not recommendations:
        raw_scores = ai_result.get("rubric_scores") or {}
        if isinstance(raw_scores, dict):
            for dimension, detail in raw_scores.items():
                if not isinstance(detail, dict):
                    continue
                improvement_values = detail.get("areas_for_improvement") or detail.get("weaknesses") or []
                if isinstance(improvement_values, list):
                    recommendations.extend([str(item).strip() for item in improvement_values if str(item).strip()])
                elif improvement_values:
                    improvement_text = str(improvement_values).strip()
                    if improvement_text:
                        recommendations.append(improvement_text)

    # Remove duplicate recommendations while preserving order.
    deduped_recommendations = []
    seen = set()
    for item in recommendations:
        normalized = str(item).strip()
        if normalized and normalized.lower() not in seen:
            deduped_recommendations.append(normalized)
            seen.add(normalized.lower())

    return AssessmentReport(
        report_id=f"rpt-{uuid4()}",
        model_name=model_name or get_settings().default_model_name,
        mode=get_settings().assessment_mode,
        course_id=course_id,
        project_id=project_id,
        sprint_id=sprint_id,
        generated_at=datetime.now(timezone.utc),
        rubric_weights=RUBRIC_WEIGHTS,
        team_score=TeamScore(
            score=team_score_value,
            rationale=ai_result.get("executive_summary") or "AI assessment result.",
        ),
        individual_scores=individual_scores,
        recommendations=deduped_recommendations,
        rubric_scores=rubric_scores,
        strengths=strengths,
        weaknesses=weaknesses,
    )


RUBRIC_WEIGHTS = {
    "delivery": 0.35,
    "collaboration": 0.30,
    "quality": 0.20,
    "documentation": 0.15,
}


def run_assessment_job(
    job_id: str,
    payload: AssessRequest,
    project,
    metrics_repository: MetricsRepository,
    manual_text_repository: ManualTextRepository,
    assessment_repository: AssessmentRepository | None = None,
) -> None:
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

        report = convert_ai_result_to_assessment_report(payload, ai_result)

        job_repo.update_job(job_id, status="saving_report", progress=90, current_stage="saving_report")
        job_repo.append_event(job_id, "progress", {"status": "saving_report", "progress": 90, "message": "Saving assessment report."})
        if assessment_repository:
            assessment_repository.save_report(report)
        else:
            assessment_repo.save_report(report)

        job_repo.update_job(job_id, status="completed", progress=100, current_stage="completed", report_id=report.report_id)
        job_repo.append_event(job_id, "completed", {"status": "completed", "progress": 100, "report_id": report.report_id})
    except Exception as exc:
        error_message = str(exc)
        job_repo.update_job(job_id, status="failed", progress=100, current_stage="failed", error_message=error_message)
        job_repo.append_event(job_id, "failed", {"status": "failed", "message": "The assessment failed.", "error_message": error_message})


def list_assessment_reports(course_id: str, project_id: str, sprint_id: str, assessment_repository: AssessmentRepository | None = None) -> list[AssessmentReport]:
    repository = assessment_repository or assessment_repo
    return repository.list_reports(course_id, project_id, sprint_id)


def get_latest_assessment(course_id: str, project_id: str, sprint_id: str, assessment_repository: AssessmentRepository | None = None) -> AssessmentReport:
    repository = assessment_repository or assessment_repo
    report = repository.get_latest_report(course_id, project_id, sprint_id)
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
