import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.dependencies.auth import (
    ensure_course_access,
    get_action_audit_repository,
    get_assessment_repository,
    get_audit_repository,
    get_document_repository,
    get_git_identity_repository,
    get_instructor_model_selection_repository,
    get_jira_ingestion_repository,
    get_manual_text_repository,
    get_metrics_repository,
    get_notification_service,
    get_project_repository,
    get_rubric_weights_repository,
    get_user_repository,
    require_faculty,
    require_instructor,
    require_student_or_faculty,
)
from app.dependencies.insights import get_optional_insights_repository
from app.repositories.in_memory import job_repo
from app.repositories.insights import InsightsRepository
from app.repositories.interfaces import (
    ActionAuditRepository,
    AssessmentRepository,
    AuditRepository,
    DocumentRepository,
    GitIdentityRepository,
    InstructorModelSelectionRepository,
    JiraIngestionRunRepository,
    ManualTextRepository,
    MetricsRepository,
    ProjectRepository,
    RubricWeightsRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.artifacts import ReportEvidenceLinksResponse
from app.schemas.assessment import (
    AssessmentReport,
    AssessRequest,
    ManualAssessmentPatch,
    OverrideRequest,
    RubricWeightsPayload,
    RubricWeightsResponse,
)
from app.schemas.auth import Role
from app.services.artifactViewerService.service import build_report_evidence_links
from app.services.assessmentService.service import (
    get_effective_model_name,
    get_effective_rubric_weights,
    get_latest_assessment,
    list_assessment_reports,
    notify_students_report_overridden,
    override_student_score,
    run_assessment_job,
    set_rubric_weights,
    update_manual_assessment,
)
from app.services.auditLogService.service import append_action_audit, append_override_audit
from app.services.insightsService.blind import stamp_score_exposure
from app.services.insightsService.overrides import record_override
from app.services.notificationService.service import EmailTransport

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assessments", tags=["assessments"])


def build_assessment_executor() -> ThreadPoolExecutor:
    """Runs assessment jobs. Sized to the engine's concurrency: a job waiting for a free worker
    is still "queued" and costs nothing, while a job already sent to a busy engine would sit on
    the engine's lock inside the HTTP read timeout."""
    return ThreadPoolExecutor(
        max_workers=get_settings().ai_engine_max_concurrency,
        thread_name_prefix="assessment-job",
    )


_executor = build_assessment_executor()

def _authorize_report_access(
    current_user: object, course_id: str, project_id: str, projects: ProjectRepository
) -> None:
    if current_user.role != Role.STUDENT:
        ensure_course_access(current_user, course_id, projects)
        return
    project = projects.get_project(project_id)
    if (
        not project
        or project.course_id != course_id
        or current_user.id not in projects.list_member_ids(project_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view assessment reports for your project.",
        )


def _stamp_exposure(
    user: UserRecord, report_ids: list[str], insights: InsightsRepository | None
) -> None:
    """These legacy routes show AI scores. Record that, so an instructor's later blind labels
    are stored as non-blind instead of being counted as an unbiased baseline."""
    if insights is None:
        return
    try:
        stamp_score_exposure(report_ids, user, insights)
    except Exception:
        logger.exception("Could not record score exposure for %s", report_ids)


@router.post("/assess", status_code=status.HTTP_202_ACCEPTED)
def assess_sprint(
    request: Request,
    payload: AssessRequest,
    faculty_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    metrics_repository: Annotated[MetricsRepository, Depends(get_metrics_repository)],
    manual_text_repository: Annotated[ManualTextRepository, Depends(get_manual_text_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    jira_ingestion_repository: Annotated[
        JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)
    ],
    rubric_weights_repository: Annotated[
        RubricWeightsRepository, Depends(get_rubric_weights_repository)
    ],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
    document_repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    notification_service: Annotated[EmailTransport, Depends(get_notification_service)],
    selection_repository: Annotated[
        InstructorModelSelectionRepository, Depends(get_instructor_model_selection_repository)
    ],
    identity_repository: Annotated[GitIdentityRepository, Depends(get_git_identity_repository)],
) -> dict:
    project = projects.get_project(payload.project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if project.course_id != payload.course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Project does not belong to course."
        )
    ensure_course_access(faculty_user, project.course_id, projects)
    if not project.local_repo_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no local repository configured.",
        )

    # Resolve the model before the job is created/persisted so the stored job
    # and the saved report reflect what actually runs. Order: explicit request
    # > the instructor's saved selection > global default. Never empty, so a
    # missing selection can never fail the assessment.
    payload.model_name = get_effective_model_name(
        payload.model_name, faculty_user.id, selection_repository
    )

    # create_job records the "started" event itself.
    job = job_repo.create_job(payload)

    # Start the long-polling worker in a background thread so the endpoint
    # returns immediately with the 202 job contract instead of blocking.
    _executor.submit(
        run_assessment_job,
        job.job_id,
        payload,
        project,
        metrics_repository,
        manual_text_repository,
        assessment_repository,
        jira_ingestion_repository,
        rubric_weights_repository,
        document_repository,
        user_repository=user_repository,
        project_repository=projects,
        notification_service=notification_service,
        identity_repository=identity_repository,
        mlflow_gateway=getattr(request.app.state, "mlflow_gateway", None),
    )
    append_action_audit(
        action_audits,
        actor_id=faculty_user.id,
        actor_role=faculty_user.role.value,
        action="request_assessment",
        target_type="assessment_job",
        target_id=job.job_id,
        details={
            "course_id": payload.course_id,
            "project_id": payload.project_id,
            "sprint_id": payload.sprint_id,
        },
    )

    return {
        "job_id": job.job_id,
        "status": "queued",
        "message": "Assessment has started.",
    }

@router.get("/jobs/{job_id}/events")
def assessment_job_events(
    job_id: str,
    faculty_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
):
    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment job not found."
        )
    ensure_course_access(faculty_user, job.course_id, projects)

    # A job can outlive its stream, but a stream must not outlive its job: stop when the job is
    # gone or well past the longest an assessment may take.
    give_up_at = time.monotonic() + get_settings().ai_engine_timeout_seconds + 600

    def event_stream():
        seen = 0
        while time.monotonic() < give_up_at:
            # Read the status BEFORE the events. The worker writes a job's terminal event before
            # its terminal status, so a status read first that is terminal guarantees the events
            # read next include the final one. Reading in the other order could close the stream
            # between the two writes and the client would never see "failed".
            state = job_repo.get_job(job_id)
            events = job_repo.list_events(job_id)
            if len(events) > seen:
                for item in events[seen:]:
                    yield f"event: {item.event}\n"
                    yield f"data: {json.dumps(item.data)}\n\n"
                seen = len(events)
            if state is None or state.status in {"completed", "failed"}:
                break
            time.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/reports")
def list_reports(
    course_id: str,
    project_id: str,
    sprint_id: str,
    faculty_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    insights_repository: Annotated[
        InsightsRepository | None, Depends(get_optional_insights_repository)
    ],
):
    ensure_course_access(faculty_user, course_id, projects)
    reports = list_assessment_reports(course_id, project_id, sprint_id, assessment_repository)
    _stamp_exposure(faculty_user, [r.report_id for r in reports], insights_repository)
    return reports

@router.get("/latest")
def get_latest(
    course_id: str,
    project_id: str,
    sprint_id: str,
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    insights_repository: Annotated[
        InsightsRepository | None, Depends(get_optional_insights_repository)
    ],
):
    _authorize_report_access(current_user, course_id, project_id, projects)
    report = get_latest_assessment(course_id, project_id, sprint_id, assessment_repository)
    _stamp_exposure(current_user, [report.report_id], insights_repository)
    return report

@router.get("/reports/{report_id}/evidence", response_model=ReportEvidenceLinksResponse)
def get_report_evidence_links(
    report_id: str,
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    jira_ingestion_repository: Annotated[
        JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)
    ],
) -> ReportEvidenceLinksResponse:
    """Every rubric citation in the report, each with an in-app viewer path
    and (when one can be worked out) a GitHub/GitLab/Bitbucket/Jira URL.
    Computed on read rather than stored, so a later repository URL or Jira
    domain change applies."""
    if assessment_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assessment repository unavailable.",
        )
    report = assessment_repository.get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment report not found."
        )
    _authorize_report_access(current_user, report.course_id, report.project_id, projects)
    return build_report_evidence_links(
        report, projects.get_project(report.project_id), jira_ingestion_repository
    )

@router.get("/rubric-weights", response_model=RubricWeightsResponse)
def get_rubric_weights(
    course_id: str,
    faculty_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    rubric_weights_repository: Annotated[
        RubricWeightsRepository, Depends(get_rubric_weights_repository)
    ],
) -> RubricWeightsResponse:
    ensure_course_access(faculty_user, course_id, projects)
    record = rubric_weights_repository.get_weights(course_id)
    if record:
        return RubricWeightsResponse(
            course_id=course_id,
            weights=record.weights,
            is_custom=True,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
        )
    return RubricWeightsResponse(
        course_id=course_id,
        weights=get_effective_rubric_weights(course_id, rubric_weights_repository),
        is_custom=False,
    )

@router.put("/rubric-weights", response_model=RubricWeightsResponse)
def put_rubric_weights(
    course_id: str,
    payload: RubricWeightsPayload,
    faculty_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    rubric_weights_repository: Annotated[
        RubricWeightsRepository, Depends(get_rubric_weights_repository)
    ],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> RubricWeightsResponse:
    ensure_course_access(faculty_user, course_id, projects)
    record = set_rubric_weights(
        course_id, payload.weights, faculty_user.id, rubric_weights_repository
    )
    append_action_audit(
        action_audits,
        actor_id=faculty_user.id,
        actor_role=faculty_user.role.value,
        action="update_rubric_weights",
        target_type="course",
        target_id=course_id,
        details={"weights": record.weights},
    )
    return RubricWeightsResponse(
        course_id=course_id,
        weights=record.weights,
        is_custom=True,
        updated_by=record.updated_by,
        updated_at=record.updated_at,
    )

@router.patch("/reports/{report_id}")
def patch_assessment_report(
    report_id: str,
    payload: ManualAssessmentPatch,
    instructor_user: Annotated[UserRecord, Depends(require_instructor)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    notification_service: Annotated[EmailTransport, Depends(get_notification_service)],
    insights_repository: Annotated[
        InsightsRepository | None, Depends(get_optional_insights_repository)
    ],
) -> AssessmentReport:
    if assessment_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assessment repository unavailable.",
        )
    report = update_manual_assessment(
        report_id,
        payload,
        instructor_user.id,
        assessment_repository,
        projects,
    )
    try:
        record_override(report, instructor_user.id, insights_repository)
    except Exception:  # noqa: BLE001 - AI Insights must never break the override itself
        logger.exception("AI Insights: override of report %s was not recorded", report_id)
    append_action_audit(
        action_audits,
        actor_id=instructor_user.id,
        actor_role=instructor_user.role.value,
        action="update_assessment_report",
        target_type="assessment_report",
        target_id=report_id,
        details={"updated_fields": sorted(payload.model_fields_set)},
    )
    notify_students_report_overridden(
        report,
        user_repository,
        notification_service,
        # Grading is team-level (individual_scores is empty), so notify the team's members.
        list(
            dict.fromkeys(
                [
                    *projects.list_member_ids(report.project_id),
                    *(score.student_id for score in report.individual_scores),
                ]
            )
        ),
        "Your instructor updated the assessment report.",
    )
    return report

@router.post("/override")
def override_score(
    payload: OverrideRequest,
    faculty_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    notification_service: Annotated[EmailTransport, Depends(get_notification_service)],
):
    if assessment_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assessment repository unavailable.",
        )
    existing = assessment_repository.get_report(payload.report_id)
    if existing:
        ensure_course_access(faculty_user, existing.course_id, projects)
    override_record = override_student_score(
        payload,
        instructor_id=faculty_user.id,
        assessment_repository=assessment_repository,
    )
    audit = append_override_audit(override_record, audit_repository)
    report = assessment_repository.get_report(payload.report_id)
    if report:
        notify_students_report_overridden(
            report,
            user_repository,
            notification_service,
            [payload.student_id],
            payload.reason_comment,
        )
    return {
        "override": override_record,
        "audit": audit,
    }