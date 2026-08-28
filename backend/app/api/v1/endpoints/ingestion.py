from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_metrics_repository, get_project_repository, require_faculty
from app.repositories.interfaces import MetricsRepository, ProjectRepository
from app.schemas.assessment import IngestionRequest
from app.services.documentsService.service import collect_document_signals
from app.services.gitlabGithub.service import ingest_github_metrics, resolve_local_repository_path
from app.services.jiraService.service import enrich_jira_metrics

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/sync")
def sync_ingestion(
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
