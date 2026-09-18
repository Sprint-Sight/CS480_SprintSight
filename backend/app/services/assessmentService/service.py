from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.repositories.in_memory import assessment_repo, job_repo, metrics_repo, overrides_repo, rubric_weights_repo
from app.repositories.interfaces import AssessmentRepository, JiraIngestionRunRepository, ManualTextRepository, MetricsRepository, ProjectRepository, RubricWeightsRecord, RubricWeightsRepository
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

# Minimum /100 score (inclusive) required for each letter grade, highest first.
GRADE_BOUNDARIES: list[tuple[float, str]] = [
    (86, "A+"),
    (83, "A"),
    (80, "A-"),
    (77, "B+"),
    (74, "B"),
    (70, "B-"),
    (66, "C+"),
    (63, "C"),
    (60, "C-"),
    (53, "D+"),
    (50, "D"),
    (0, "F"),
]


def score_to_grade(score: float) -> str:
    for minimum, grade in GRADE_BOUNDARIES:
        if score >= minimum:
            return grade
    return "F"


def _format_evidence_citations(evidence: object) -> list[str]:
    """The AI engine sends each citation as {"identifier", "reason"}; flatten
    that into a single display string for this endpoint's list[str] contract.
    Still accepts plain strings for older/partial ai_result payloads."""
    if not isinstance(evidence, list):
        return [str(evidence)]
    formatted = []
    for item in evidence:
        if isinstance(item, dict):
            identifier = item.get("identifier", "")
            reason = item.get("reason", "")
            formatted.append(f"{identifier} — {reason}" if reason else str(identifier))
        else:
            formatted.append(str(item))
    return formatted


def convert_ai_result_to_assessment_report(
    payload: AssessRequest | dict,
    ai_result: dict,
    rubric_weights: dict[str, float] | None = None,
) -> AssessmentReport:
    """Shape the AI engine's SprintAssessment JSON into the backend report contract.

    rubric_weights defaults to RUBRIC_WEIGHTS (equal weighting) when the caller
    doesn't pass a course-specific override, e.g. in tests that construct a
    report directly without going through run_assessment_job.
    """
    effective_weights = rubric_weights or RUBRIC_WEIGHTS
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
    strengths = list(ai_result.get("strengths") or [])
    weaknesses = list(ai_result.get("weaknesses") or [])
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
                rubric_scores[dimension_name] = RubricDimensionScoreDetail(
                    score=normalized_score,
                    justification=detail.get("justification") or "AI-generated rubric justification.",
                    evidence_citations=_format_evidence_citations(evidence),
                )

    recommendations = list(ai_result.get("key_recommendations") or [])
    if not recommendations:
        recommendations = list(ai_result.get("recommendations") or [])

    # Weight the actual per-dimension scores by effective_weights so a course's
    # custom weights change the team score, not just the displayed labels.
    # Falls back to the AI engine's own (unweighted) overall_score when
    # per-dimension detail isn't available (e.g. older/partial ai_result).
    if rubric_scores and all(dimension in rubric_scores for dimension in effective_weights):
        weighted_average = sum(
            rubric_scores[dimension].score * weight for dimension, weight in effective_weights.items()
        )
        team_score_value = round(weighted_average * 10, 2)
    elif isinstance(overall_score, (int, float)):
        team_score_value = round(overall_score * 10, 2)
    else:
        team_score_value = 0.0

    def deduplicate(values: list) -> list[str]:
        deduplicated = []
        seen = set()
        for item in values:
            normalized = str(item).strip()
            key = " ".join(normalized.casefold().split())
            if normalized and key not in seen:
                deduplicated.append(normalized)
                seen.add(key)
        return deduplicated

    deduped_recommendations = deduplicate(recommendations)

    return AssessmentReport(
        report_id=f"rpt-{uuid4()}",
        model_name=model_name or get_settings().default_model_name,
        mode=get_settings().assessment_mode,
        course_id=course_id,
        project_id=project_id,
        sprint_id=sprint_id,
        generated_at=datetime.now(timezone.utc),
        rubric_weights=effective_weights,
        team_score=TeamScore(
            score=team_score_value,
            rationale=ai_result.get("executive_summary") or "AI assessment result.",
            overall_grade=score_to_grade(team_score_value),
        ),
        individual_scores=individual_scores,
        recommendations=deduped_recommendations,
        rubric_scores=rubric_scores,
        strengths=deduplicate(strengths),
        weaknesses=deduplicate(weaknesses),
    )


RUBRIC_WEIGHTS = {
    "requirements": 1 / 6,
    "code_quality": 1 / 6,
    "testing": 1 / 6,
    "documentation": 1 / 6,
    "collaboration": 1 / 6,
    "cicd": 1 / 6,
}


def _validate_rubric_weights(weights: dict[str, float]) -> None:
    expected_dimensions = set(RUBRIC_WEIGHTS)
    if set(weights) != expected_dimensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rubric weights must specify exactly these dimensions: {sorted(expected_dimensions)}.",
        )
    total = sum(weights.values())
    if not (0.99 <= total <= 1.01):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rubric weights must sum to 1.0 (got {total:.3f}).",
        )


def get_effective_rubric_weights(
    course_id: str,
    rubric_weights_repository: RubricWeightsRepository | None = None,
) -> dict[str, float]:
    """The course's faculty-set weights, or the hardcoded equal-weight default."""
    repository = rubric_weights_repository or rubric_weights_repo
    record = repository.get_weights(course_id)
    return dict(record.weights) if record else dict(RUBRIC_WEIGHTS)


def set_rubric_weights(
    course_id: str,
    weights: dict[str, float],
    updated_by: str,
    rubric_weights_repository: RubricWeightsRepository | None = None,
) -> RubricWeightsRecord:
    _validate_rubric_weights(weights)
    repository = rubric_weights_repository or rubric_weights_repo
    return repository.set_weights(course_id, weights, updated_by)


def run_assessment_job(
    job_id: str,
    payload: AssessRequest,
    project,
    metrics_repository: MetricsRepository,
    manual_text_repository: ManualTextRepository,
    assessment_repository: AssessmentRepository | None = None,
    jira_ingestion_repository: JiraIngestionRunRepository | None = None,
    rubric_weights_repository: RubricWeightsRepository | None = None,
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
        jira_tickets = []
        if jira_ingestion_repository:
            jira_runs = jira_ingestion_repository.list_runs(payload.project_id, payload.sprint_id)
            processed_runs = [run for run in jira_runs if run.cleaned_snapshot]
            if processed_runs:
                latest_run = max(processed_runs, key=lambda run: run.captured_at)
                jira_tickets = [ticket.model_dump(mode="json") for ticket in latest_run.cleaned_snapshot.tickets]

        job_repo.update_job(job_id, status="building_payload", progress=50, current_stage="building_payload")
        job_repo.append_event(job_id, "progress", {"status": "building_payload", "progress": 50, "message": "Building AI payload."})
        middle_man_payload = build_assessment_payload(metrics, docs, manual_text, jira_tickets)

        job_repo.update_job(job_id, status="ai_evaluating", progress=70, current_stage="ai_evaluating")
        job_repo.append_event(job_id, "progress", {"status": "ai_evaluating", "progress": 70, "message": "AI is evaluating the sprint."})
        ai_result = send_assessment_to_ai_engine(middle_man_payload, payload.model_name)

        effective_weights = get_effective_rubric_weights(payload.course_id, rubric_weights_repository)
        report = convert_ai_result_to_assessment_report(payload, ai_result, rubric_weights=effective_weights)

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
