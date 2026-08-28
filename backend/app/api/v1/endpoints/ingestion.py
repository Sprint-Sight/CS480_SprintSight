from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import get_metrics_repository, get_project_repository, require_faculty
from app.repositories.interfaces import MetricsRepository, ProjectRepository
from app.repositories.interfaces import UserRecord
from app.schemas.assessment import IngestionDataResponse, IngestionRequest, PaginationMetadata
from app.services.documentsService.service import collect_document_signals
from app.services.gitlabGithub.service import ingest_github_metrics, resolve_local_repository_path
from app.services.jiraService.service import enrich_jira_metrics

router = APIRouter(prefix="/repo-ingestion", tags=["repo-ingestion"])


@router.get("/runs/{project_id}/{sprint_id}", response_model=IngestionDataResponse)
def get_repo_ingestion_data(
    project_id: str,
    sprint_id: str,
    course_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    metrics_repository: Annotated[MetricsRepository, Depends(get_metrics_repository)],
    pagination: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int | None = Query(default=None, ge=0),
) -> IngestionDataResponse:
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if project.course_id != course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project does not belong to course.")
    if not projects.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")

    if pagination and (limit is None or offset is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit and offset are required when pagination is enabled.",
        )
    if not pagination and (limit is not None or offset is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit and offset must be omitted when pagination is disabled.",
        )

    if pagination:
        metrics, total = metrics_repository.get_metrics_page(
            course_id, project_id, sprint_id, limit, offset
        )
    else:
        metrics = metrics_repository.get_metrics(course_id, project_id, sprint_id)
        total = len(metrics.commits) if metrics else 0
    if not metrics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion data not found.")
    return IngestionDataResponse(
        course_id=metrics.course_id,
        project_id=metrics.project_id,
        sprint_id=metrics.sprint_id,
        head_sha=metrics.head_sha,
        captured_at=metrics.captured_at,
        commit_frequency=metrics.commit_frequency,
        code_churn=metrics.code_churn,
        pr_turnaround_hours=metrics.pr_turnaround_hours,
        assigned_story_points=metrics.assigned_story_points,
        completion_percent=metrics.completion_percent,
        commits=metrics.commits,
        pagination=PaginationMetadata(
            limit=limit if pagination else None,
            offset=offset if pagination else None,
            total=total,
            has_more=bool(pagination and offset is not None and offset + len(metrics.commits) < total),
        ),
    )


@router.post("/sync")
def sync_repository_ingestion(
    payload: IngestionRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    metrics_repository: Annotated[MetricsRepository, Depends(get_metrics_repository)],
) -> dict:
    _ = faculty_user
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
    github_metrics = ingest_github_metrics(payload, repository_path, metrics_repository)
    jira_metrics = enrich_jira_metrics(payload)
    document_signals = collect_document_signals(payload)
    return {
        "github_metrics": github_metrics,
        "jira_metrics": jira_metrics,
        "document_signals": document_signals,
    }
