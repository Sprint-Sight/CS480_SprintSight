import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.storage import storage as default_storage
from app.repositories.in_memory import (
    assessment_repo,
    job_repo,
    metrics_repo,
    overrides_repo,
    rubric_weights_repo,
)
from app.repositories.interfaces import (
    AssessmentRepository,
    DocumentRepository,
    JiraIngestionRunRepository,
    ManualTextRepository,
    MetricsRepository,
    ProjectRepository,
    RubricWeightsRecord,
    RubricWeightsRepository,
    UserRepository,
)
from app.schemas.assessment import (
    AssessmentReport,
    AssessRequest,
    ManualAssessmentPatch,
    OverrideRequest,
    OverrideResponse,
    RubricDimensionScoreDetail,
    StudentScore,
    TeamScore,
)
from app.services.documentsService.service import collect_project_context_documents
from app.services.gitlabGithub.service import ingest_github_metrics, resolve_local_repository_path
from app.services.jiraService.service import enrich_jira_metrics
from app.services.manualTextService.service import get_manual_text
from app.services.middleManService.service import (
    build_assessment_payload,
    send_assessment_to_ai_engine,
)
from app.services.notificationService.service import SMTPNotificationService

logger = logging.getLogger(__name__)

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
    document_repository: DocumentRepository | None = None,
    user_repository: UserRepository | None = None,
    project_repository: ProjectRepository | None = None,
    notification_service: SMTPNotificationService | None = None,
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
        # `artifact_metrics` is reserved for future numeric signals extracted
        # from uploaded artifacts (demo completeness, documentation quality,
        # etc.) and used by the rubric evaluator. Until a real extractor
        # exists, send an empty dict rather than fabricated placeholder
        # scores — uploaded files now flow to the model via
        # `project_context_documents` below instead.
        artifact_signals: dict[str, float] = {}
        manual_text = get_manual_text(manual_text_repository, payload.course_id, payload.project_id, payload.sprint_id)
        jira_tickets = []
        if jira_ingestion_repository:
            jira_runs = jira_ingestion_repository.list_runs(payload.project_id, payload.sprint_id)
            processed_runs = [run for run in jira_runs if run.cleaned_snapshot]
            if processed_runs:
                latest_run = max(processed_runs, key=lambda run: run.captured_at)
                jira_tickets = [ticket.model_dump(mode="json") for ticket in latest_run.cleaned_snapshot.tickets]

        # Collect any faculty/student-uploaded context documents (project
        # briefs, requirements, design notes) so the LLM gets them as
        # background context. This is intentionally separate from
        # `artifact_signals` (reserved for future numeric scores on uploaded
        # artifacts) and from the `documentation` rubric dimension — see
        # build_assessment_payload for the contract.
        project_context_documents: list[dict] = []
        if document_repository is not None:
            try:
                project_context_documents = collect_project_context_documents(
                    payload.project_id, document_repository, default_storage,
                )
            except Exception:
                # A failure to load context documents must not fail the whole
                # assessment — the evaluation flow worked before documents
                # existed, and preserving that fallback is a requirement.
                import logging as _logging
                _logging.getLogger(__name__).exception(
                    "Failed to collect project context documents for project %s; "
                    "continuing assessment without them.",
                    payload.project_id,
                )
        else:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "run_assessment_job: no document_repository passed for project %s; "
                "no uploaded documents will reach the AI engine.",
                payload.project_id,
            )

        job_repo.update_job(job_id, status="building_payload", progress=50, current_stage="building_payload")
        job_repo.append_event(job_id, "progress", {"status": "building_payload", "progress": 50, "message": "Building AI payload."})
        middle_man_payload = build_assessment_payload(
            metrics, artifact_signals, manual_text, jira_tickets, project_context_documents,
        )

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
        if user_repository and project_repository and notification_service:
            _notify_instructors_report_completed(
                report,
                project,
                user_repository,
                project_repository,
                notification_service,
                job_id,
            )
            _notify_students_report_completed(
                report,
                project,
                user_repository,
                notification_service,
                job_id,
                project_repository,
            )
    except Exception as exc:
        error_message = str(exc)
        job_repo.update_job(job_id, status="failed", progress=100, current_stage="failed", error_message=error_message)
        job_repo.append_event(job_id, "failed", {"status": "failed", "message": "The assessment failed.", "error_message": error_message})


def _notify_instructors_report_completed(
    report: AssessmentReport,
    project,
    user_repository: UserRepository,
    project_repository: ProjectRepository,
    notification_service: SMTPNotificationService,
    job_id: str,
) -> None:
    try:
        instructors = [
            user
            for user in user_repository.list_users()
            if user.is_active
            and user.role.value == "instructor"
            and project_repository.is_instructor_assigned(report.course_id, user.id)
        ]
    except Exception:
        logger.exception("Could not identify instructors for completed assessment job %s.", job_id)
        job_repo.append_event(
            job_id,
            "notification_failed",
            {"message": "The report is ready, but instructor email recipients could not be loaded."},
        )
        return

    if not instructors:
        logger.warning("No assigned active instructors found for completed assessment job %s.", job_id)
        return

    subject = f"SprintSight assessment report completed: {project.project_name}"
    body = (
        "The LLM assessment report has been completed.\n\n"
        f"Course: {report.course_id}\n"
        f"Project: {project.project_name}\n"
        f"Sprint: {report.sprint_id}\n"
        f"Report ID: {report.report_id}\n"
        f"Team score: {report.team_score.score}\n"
    )
    for instructor in instructors:
        try:
            notification_service.send_email(instructor.email, subject, body)
        except Exception:
            logger.exception(
                "Could not email instructor %s for completed assessment job %s.",
                instructor.id,
                job_id,
            )
            job_repo.append_event(
                job_id,
                "notification_failed",
                {"message": "The report is ready, but an instructor notification could not be delivered."},
            )
            continue
        job_repo.append_event(
            job_id,
            "notification_sent",
            {"message": "Report completion email sent to an assigned instructor."},
        )


def _notify_students_report_completed(
    report: AssessmentReport,
    project,
    user_repository: UserRepository,
    notification_service: SMTPNotificationService,
    job_id: str,
    project_repository: ProjectRepository | None = None,
) -> None:
    subject = f"Your SprintSight assessment report is ready: {project.project_name}"
    scored_student_ids = [score.student_id for score in report.individual_scores]
    project_student_ids: list[str] = []
    if project_repository:
        try:
            project_student_ids = project_repository.list_member_ids(report.project_id)
        except Exception:
            logger.exception(
                "Could not identify project members for completed assessment job %s.",
                job_id,
            )
            job_repo.append_event(
                job_id,
                "notification_failed",
                {"message": "The report is ready, but student email recipients could not be loaded."},
            )
    student_ids = dict.fromkeys([*project_student_ids, *scored_student_ids])
    for student_id in student_ids:
        try:
            student = user_repository.get_by_id(student_id)
        except Exception:
            logger.exception(
                "Could not load student %s for completed assessment job %s.",
                student_id,
                job_id,
            )
            job_repo.append_event(
                job_id,
                "notification_failed",
                {"message": "The report is ready, but a student email recipient could not be loaded."},
            )
            continue
        if not student or not student.is_active or student.role.value != "student":
            logger.warning(
                "Could not identify an active student %s for completed assessment job %s.",
                student_id,
                job_id,
            )
            continue
        score = next(
            (score for score in report.individual_scores if score.student_id == student_id),
            None,
        )
        body = (
            "Your sprint assessment report has been completed.\n\n"
            f"Course: {report.course_id}\n"
            f"Project: {project.project_name}\n"
            f"Sprint: {report.sprint_id}\n"
            f"Report ID: {report.report_id}\n"
            + (f"Your score: {score.score}\n" if score else "")
        )
        try:
            notification_service.send_email(student.email, subject, body)
        except Exception:
            logger.exception(
                "Could not email student %s for completed assessment job %s.",
                student.id,
                job_id,
            )
            job_repo.append_event(
                job_id,
                "notification_failed",
                {"message": "The report is ready, but a student notification could not be delivered."},
            )
            continue
        job_repo.append_event(
            job_id,
            "notification_sent",
            {"message": "Report completion email sent to a student."},
        )


def notify_students_report_overridden(
    report: AssessmentReport,
    user_repository: UserRepository,
    notification_service: SMTPNotificationService,
    student_ids: list[str],
    reason: str,
) -> None:
    for student_id in dict.fromkeys(student_ids):
        try:
            student = user_repository.get_by_id(student_id)
        except Exception:
            logger.exception(
                "Could not load student %s for report override %s.",
                student_id,
                report.report_id,
            )
            continue
        if not student or not student.is_active or student.role.value != "student":
            logger.warning(
                "Could not identify an active student %s for report override %s.",
                student_id,
                report.report_id,
            )
            continue
        score = next(
            (item for item in report.individual_scores if item.student_id == student_id),
            None,
        )
        body = (
            "Your SprintSight assessment report has been updated by your instructor.\n\n"
            f"Course: {report.course_id}\n"
            f"Project: {report.project_id}\n"
            f"Sprint: {report.sprint_id}\n"
            f"Report ID: {report.report_id}\n"
            + (f"Your updated score: {score.score}\n" if score else "")
            + f"Reason: {reason}\n"
        )
        try:
            notification_service.send_email(
                student.email,
                f"SprintSight assessment report updated: {report.project_id}",
                body,
            )
        except Exception:
            logger.exception(
                "Could not email student %s about overridden report %s.",
                student.id,
                report.report_id,
            )


def list_assessment_reports(course_id: str, project_id: str, sprint_id: str, assessment_repository: AssessmentRepository | None = None) -> list[AssessmentReport]:
    repository = assessment_repository or assessment_repo
    return repository.list_reports(course_id, project_id, sprint_id)


def get_latest_assessment(course_id: str, project_id: str, sprint_id: str, assessment_repository: AssessmentRepository | None = None) -> AssessmentReport:
    repository = assessment_repository or assessment_repo
    report = repository.get_latest_report(course_id, project_id, sprint_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment report not found.")
    return report


def update_manual_assessment(
    report_id: str,
    payload: ManualAssessmentPatch,
    instructor_id: str,
    assessment_repository: AssessmentRepository,
    projects: ProjectRepository,
) -> AssessmentReport:
    report = assessment_repository.get_report(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment report not found.")

    project = projects.get_project(report.project_id)
    if not project or project.course_id != report.course_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment report not found.")
    if not projects.is_instructor_assigned(report.course_id, instructor_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor is not assigned to this course.",
        )

    patch = payload.model_dump(exclude_unset=True)
    rubric_scores = {
        key: detail.model_dump()
        for key, detail in report.rubric_scores.items()
    }
    supplied_rubric_scores = patch.get("rubric_scores") or {}
    rubric_scores.update(supplied_rubric_scores)
    for dimension in ("requirements", "code_quality", "documentation", "collaboration"):
        score_key = f"{dimension}_score"
        justification_key = f"{dimension}_justification"
        if dimension in supplied_rubric_scores:
            continue
        if score_key not in patch and justification_key not in patch:
            continue
        existing = rubric_scores.get(dimension, {})
        rubric_scores[dimension] = {
            **existing,
            "score": patch.get(score_key, existing.get("score", 0)),
            "justification": patch.get(
                justification_key,
                existing.get("justification"),
            ),
        }
    if rubric_scores:
        patch["rubric_scores"] = rubric_scores

    updated = assessment_repository.update_manual_assessment(report_id, patch)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment report not found.")
    return updated


def override_student_score(
    payload: OverrideRequest,
    instructor_id: str,
    assessment_repository: AssessmentRepository | None = None,
) -> OverrideResponse:
    repository = assessment_repository or assessment_repo
    report = repository.get_report(payload.report_id)
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
    repository.save_report(report)
    return override_record
