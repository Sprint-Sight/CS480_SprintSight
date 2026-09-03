from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.dependencies.auth import get_metrics_repository, get_project_repository, require_faculty
from app.repositories.interfaces import MetricsRepository, ProjectRepository
from app.schemas.assessment import AssessRequest, OverrideRequest
from app.services.assessmentService.service import (
    generate_ai_assessment,
    generate_mock_assessment,
    get_latest_assessment,
    override_student_score,
)
from app.services.auditLogService.service import append_override_audit
from app.services.documentsService.service import collect_document_signals
from app.services.gitlabGithub.service import ingest_github_metrics, resolve_local_repository_path
from app.services.jiraService.service import enrich_jira_metrics
from app.services.manualTextService.service import get_manual_text
from app.services.middleManService.service import build_assessment_payload

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("/assess")
async def assess_sprint(
    payload: AssessRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    metrics_repository: Annotated[MetricsRepository, Depends(get_metrics_repository)],
) -> dict:
    _ = faculty_user
    try:
        UUID(payload.project_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id must be a valid project UUID.",
        ) from exc
    project = projects.get_project(payload.project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if project.course_id != payload.course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project does not belong to course.")
    if not project.local_repo_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project has no local repository configured.")
    try:
        repository_path = resolve_local_repository_path(project.local_repo_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    metrics = ingest_github_metrics(payload, repository_path, metrics_repository)
    _ = enrich_jira_metrics(payload)
    docs = collect_document_signals(payload)
    manual_text = get_manual_text(payload.course_id, payload.project_id, payload.sprint_id)
    middle_man_payload = build_assessment_payload(metrics, docs, manual_text)

    if get_settings().assessment_mode.lower() == "ai":
        report = await generate_ai_assessment(payload, middle_man_payload)
    else:
        report = generate_mock_assessment(payload, metrics_repository)
    return {
        "input_payload": middle_man_payload,
        "report": report,
    }


@router.get("/latest")
def get_latest(
    course_id: str,
    project_id: str,
    sprint_id: str,
    faculty_user: Annotated[object, Depends(require_faculty)],
):
    _ = faculty_user
    return get_latest_assessment(course_id, project_id, sprint_id)


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
