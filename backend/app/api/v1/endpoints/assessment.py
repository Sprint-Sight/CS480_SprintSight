from typing import Annotated
import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies.auth import get_assessment_repository, get_jira_ingestion_repository, get_manual_text_repository, get_metrics_repository, get_project_repository, require_faculty
from app.repositories.in_memory import job_repo
from app.repositories.interfaces import AssessmentRepository, JiraIngestionRunRepository, ManualTextRepository, MetricsRepository, ProjectRepository
from app.schemas.assessment import AssessRequest, OverrideRequest
from app.schemas.auth import Role
from app.services.assessmentService.service import (
    get_latest_assessment,
    list_assessment_reports,
    override_student_score,
    run_assessment_job,
)
from app.services.auditLogService.service import append_override_audit

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
) -> dict:
    _ = faculty_user
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


@router.post("/override")
def override_score(
    payload: OverrideRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
):
    override_record = override_student_score(payload, instructor_id=faculty_user.id)
    audit = append_override_audit(override_record)
    return {
        "override": override_record,
        "audit": audit,
    }
