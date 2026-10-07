from typing import Annotated
import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies.auth import get_action_audit_repository, get_assessment_repository, get_audit_repository, get_jira_ingestion_repository, get_manual_text_repository, get_metrics_repository, get_project_repository, get_rubric_weights_repository, require_faculty, require_instructor, require_student_or_faculty
from app.repositories.in_memory import job_repo
from app.repositories.interfaces import ActionAuditRepository, AssessmentRepository, AuditRepository, JiraIngestionRunRepository, ManualTextRepository, MetricsRepository, ProjectRepository, RubricWeightsRepository
from app.schemas.assessment import AssessRequest, AssessmentReport, ManualAssessmentPatch, OverrideRequest, RubricWeightsPayload, RubricWeightsResponse
from app.schemas.auth import Role
from app.services.assessmentService.service import (
    get_effective_rubric_weights,
    get_latest_assessment,
    list_assessment_reports,
    override_student_score,
    run_assessment_job,
    set_rubric_weights,
    update_manual_assessment,
)
from app.services.auditLogService.service import append_action_audit, append_override_audit

router = APIRouter(prefix="/assessments", tags=["assessments"])
_executor = ThreadPoolExecutor(max_workers=4)


def _authorize_report_access(current_user: object, course_id: str, project_id: str, projects: ProjectRepository) -> None:
    if current_user.role != Role.STUDENT:
        return
    project = projects.get_project(project_id)
    if not project or project.course_id != course_id or current_user.id not in projects.list_member_ids(project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view assessment reports for your project.")


@router.post("/assess", status_code=status.HTTP_202_ACCEPTED)
def assess_sprint(
    payload: AssessRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    metrics_repository: Annotated[MetricsRepository, Depends(get_metrics_repository)],
    manual_text_repository: Annotated[ManualTextRepository, Depends(get_manual_text_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    jira_ingestion_repository: Annotated[JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)],
    rubric_weights_repository: Annotated[RubricWeightsRepository, Depends(get_rubric_weights_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
    document_repository: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> dict:
    project = projects.get_project(payload.project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if project.course_id != payload.course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project does not belong to course.")
    if not project.local_repo_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project has no local repository configured.")

    job = job_repo.create_job(payload)
    job_repo.append_event(job.job_id, "started", {"status": "started", "message": "Assessment has started."})

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
    )
    append_action_audit(
        action_audits,
        actor_id=faculty_user.id,
        actor_role=faculty_user.role.value,
        action="request_assessment",
        target_type="assessment_job",
        target_id=job.job_id,
        details={"course_id": payload.course_id, "project_id": payload.project_id, "sprint_id": payload.sprint_id},
    )

    return {
        "job_id": job.job_id,
        "status": "queued",
        "message": "Assessment has started.",
    }


@router.get("/jobs/{job_id}/events")
def assessment_job_events(
    job_id: str,
    faculty_user: Annotated[object, Depends(require_faculty)],
):
    _ = faculty_user
    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment job not found.")

    def event_stream():
        seen = 0
        while True:
            events = job_repo.list_events(job_id)
            if len(events) > seen:
                for item in events[seen:]:
                    yield f"event: {item.event}\n"
                    yield f"data: {json.dumps(item.data)}\n\n"
                seen = len(events)
            state = job_repo.get_job(job_id)
            if state and state.status in {"completed", "failed"}:
                break
            time.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/reports")
def list_reports(
    course_id: str,
    project_id: str,
    sprint_id: str,
    faculty_user: Annotated[object, Depends(require_faculty)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
):
    _ = faculty_user
    return list_assessment_reports(course_id, project_id, sprint_id, assessment_repository)


@router.get("/latest")
def get_latest(
    course_id: str,
    project_id: str,
    sprint_id: str,
    current_user: Annotated[object, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
):
    _authorize_report_access(current_user, course_id, project_id, projects)
    return get_latest_assessment(course_id, project_id, sprint_id, assessment_repository)


@router.get("/rubric-weights", response_model=RubricWeightsResponse)
def get_rubric_weights(
    course_id: str,
    faculty_user: Annotated[object, Depends(require_faculty)],
    rubric_weights_repository: Annotated[RubricWeightsRepository, Depends(get_rubric_weights_repository)],
) -> RubricWeightsResponse:
    _ = faculty_user
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
    faculty_user: Annotated[object, Depends(require_faculty)],
    rubric_weights_repository: Annotated[RubricWeightsRepository, Depends(get_rubric_weights_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> RubricWeightsResponse:
    record = set_rubric_weights(course_id, payload.weights, faculty_user.id, rubric_weights_repository)
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
    instructor_user: Annotated[object, Depends(require_instructor)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> AssessmentReport:
    if assessment_repository is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Assessment repository unavailable.")
    report = update_manual_assessment(
        report_id,
        payload,
        instructor_user.id,
        assessment_repository,
        projects,
    )
    append_action_audit(
        action_audits,
        actor_id=instructor_user.id,
        actor_role=instructor_user.role.value,
        action="update_assessment_report",
        target_type="assessment_report",
        target_id=report_id,
        details={"updated_fields": sorted(payload.model_fields_set)},
    )
    return report


@router.post("/override")
def override_score(
    payload: OverrideRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
):
    override_record = override_student_score(payload, instructor_id=faculty_user.id)
    audit = append_override_audit(override_record, audit_repository)
    return {
        "override": override_record,
        "audit": audit,
    }
