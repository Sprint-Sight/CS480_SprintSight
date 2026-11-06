from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import (
    get_jira_ingestion_repository,
    get_project_repository,
    require_student_or_faculty,
)
from app.repositories.interfaces import (  # noqa: E501
    JiraIngestionRunRepository,
    ProjectRecord,
    ProjectRepository,
    UserRecord,
)
from app.schemas.artifacts import ArtifactCommitView, ArtifactFileView, ArtifactTicketView
from app.schemas.auth import Role
from app.services.artifactViewerService.service import (
    read_commit_view,
    read_file_view,
    read_ticket_view,
)
from app.services.gitlabGithub.service import ArtifactNotFoundError, resolve_local_repository_path

# Read-only views of the project artifacts that AI evidence citations point
# at. The per-citation links come from GET /assessments/reports/{id}/evidence.
router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _get_authorized_project(
    project_id: str, current_user: object, projects: ProjectRepository
) -> ProjectRecord:
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if current_user.role == Role.STUDENT and current_user.id not in projects.list_member_ids(
        project_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view artifacts for your project.",
        )
    return project


def _repository_path(project: ProjectRecord) -> Path:
    if not project.local_repo_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project has no local repository configured.",
        )
    try:
        return resolve_local_repository_path(project.local_repo_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/projects/{project_id}/file", response_model=ArtifactFileView)
def get_artifact_file(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    path: Annotated[str, Query(min_length=1, max_length=1024)],
    ref: Annotated[
        str | None, Query(max_length=40, description="Commit SHA; defaults to the repository HEAD.")
    ] = None,
    start: Annotated[int | None, Query(ge=1, description="First line to highlight.")] = None,
    end: Annotated[int | None, Query(ge=1, description="Last line to highlight.")] = None,
) -> ArtifactFileView:
    project = _get_authorized_project(project_id, current_user, projects)
    try:
        return read_file_view(project, _repository_path(project), path, ref, start, end)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/projects/{project_id}/commits/{commit_sha}", response_model=ArtifactCommitView)
def get_artifact_commit(
    project_id: str,
    commit_sha: str,
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ArtifactCommitView:
    project = _get_authorized_project(project_id, current_user, projects)
    try:
        return read_commit_view(project, _repository_path(project), commit_sha)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/projects/{project_id}/tickets/{ticket_id}", response_model=ArtifactTicketView)
def get_artifact_ticket(
    project_id: str,
    ticket_id: str,
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    jira_ingestion_repository: Annotated[
        JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)
    ],
) -> ArtifactTicketView:
    project = _get_authorized_project(project_id, current_user, projects)
    try:
        return read_ticket_view(project, ticket_id, jira_ingestion_repository)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
