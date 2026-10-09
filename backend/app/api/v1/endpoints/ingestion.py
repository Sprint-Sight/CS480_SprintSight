from typing import Annotated

import json
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import get_settings
from app.core.storage import storage
from app.dependencies.auth import get_jira_ingestion_repository, get_metrics_repository, get_project_repository, get_user_repository, require_faculty
from app.repositories.interfaces import JiraIngestionRunRecord, JiraIngestionRunRepository, MetricsRepository, ProjectRepository, UserRepository
from app.repositories.interfaces import UserRecord
from app.schemas.assessment import IngestionDataResponse, IngestionRequest, JiraCleanedSnapshot, JiraIngestionRun, JiraRawSyncRequest, PaginationMetadata
from app.services.gitlabGithub.service import ingest_github_metrics, resolve_local_repository_path
from app.services.jiraService.normalizer import JiraNormalizationError, normalize_jira_envelope
from app.services.jiraService.service import enrich_jira_metrics, fetch_and_store_raw_jira_data

router = APIRouter(prefix="/repo-ingestion", tags=["repo-ingestion"])
jira_ingestion_router = APIRouter(prefix="/jira-ingestion", tags=["jira-ingestion"])


@jira_ingestion_router.post("/raw/{project_id}")
def sync_raw_jira_data(
    project_id: str,
    payload: JiraRawSyncRequest,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    runs: Annotated[JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)],
) -> dict[str, object]:
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if not projects.is_instructor_assigned(project.course_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")
    jira_project_key = payload.jira_project_key or project.jira_project_key
    if not jira_project_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Jira project key is required.")
    result = fetch_and_store_raw_jira_data(
        project.course_id,
        project_id,
        payload.sprint_id,
        jira_project_key,
        project,
        payload.jql,
    )
    run = runs.create_run(JiraIngestionRunRecord(
        id=str(uuid4()), course_id=project.course_id, project_id=project_id,
        sprint_id=payload.sprint_id, jira_project_key=str(result["jira_project_key"]),
        jql=str(result["jql"]), raw_bucket=str(result["bucket"]),
        raw_object_key=str(result["object_key"]), issue_count=int(result["issue_count"]),
        captured_at=result["captured_at"],
    ))
    return _run_response(run).model_dump(mode="json")


def _authorized_project(project_id: str, user: UserRecord, projects: ProjectRepository):
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if not projects.is_instructor_assigned(project.course_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")
    return project


def _run_response(run: JiraIngestionRunRecord) -> JiraIngestionRun:
    return JiraIngestionRun(
        run_id=run.id,
        course_id=run.course_id,
        project_id=run.project_id,
        sprint_id=run.sprint_id,
        jira_project_key=run.jira_project_key,
        jql=run.jql,
        raw_bucket=run.raw_bucket,
        raw_object_key=run.raw_object_key,
        issue_count=run.issue_count,
        captured_at=run.captured_at,
        processed_at=run.processed_at,
        processing_status=run.processing_status,
        normalization_version=run.normalization_version,
        processing_error=run.processing_error,
    )


@jira_ingestion_router.get("/runs/{project_id}", response_model=list[JiraIngestionRun])
def list_all_project_jira_runs(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    runs: Annotated[JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)],
) -> list[JiraIngestionRun]:
    project = _authorized_project(project_id, current_user, projects)
    return [_run_response(run) for run in runs.list_project_runs(project.id)]


@jira_ingestion_router.get("/runs/{project_id}/{sprint_id}", response_model=list[JiraIngestionRun])
def list_jira_runs(
    project_id: str,
    sprint_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    runs: Annotated[JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)],
) -> list[JiraIngestionRun]:
    project = _authorized_project(project_id, current_user, projects)
    return [_run_response(run) for run in runs.list_runs(project.id, sprint_id)]


@jira_ingestion_router.post("/runs/{project_id}/{sprint_id}/{run_id}/process", response_model=JiraIngestionRun)
def process_jira_run(
    project_id: str,
    sprint_id: str,
    run_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    runs: Annotated[JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)],
) -> JiraIngestionRun:
    _authorized_project(project_id, current_user, projects)
    run = runs.get_run(project_id, sprint_id, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jira ingestion run not found.")
    try:
        envelope = json.loads(storage.download(run.raw_bucket, run.raw_object_key))
        snapshot = normalize_jira_envelope(envelope, story_points_field=get_settings().jira_story_points_field or None)
    except (json.JSONDecodeError, UnicodeDecodeError, JiraNormalizationError) as exc:
        runs.update_processed_run(project_id, sprint_id, run_id, "failed", datetime.now(timezone.utc), None, str(exc), None)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Jira raw data could not be normalized.") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Jira raw data could not be retrieved from storage.") from exc
    updated = runs.update_processed_run(project_id, sprint_id, run_id, "completed", datetime.now(timezone.utc), snapshot.normalization_version, None, snapshot)
    return _run_response(updated)


@jira_ingestion_router.get("/runs/{project_id}/{sprint_id}/{run_id}/cleaned", response_model=JiraCleanedSnapshot)
def get_cleaned_jira_run(
    project_id: str,
    sprint_id: str,
    run_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    runs: Annotated[JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)],
) -> JiraCleanedSnapshot:
    _authorized_project(project_id, current_user, projects)
    run = runs.get_run(project_id, sprint_id, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jira ingestion run not found.")
    if not run.cleaned_snapshot:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Jira ingestion run has not been processed.")
    return run.cleaned_snapshot


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
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
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

    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date and end_date must be provided together.",
        )
    start_datetime = datetime.combine(start_date, time.min, tzinfo=timezone.utc) if start_date else None
    end_datetime = (
        datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if end_date
        else None
    )
    if start_datetime and end_datetime and start_datetime >= end_datetime:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be before or equal to end_date.",
        )

    if pagination:
        metrics, total = metrics_repository.get_metrics_page(
            course_id, project_id, sprint_id, limit, offset, start_datetime, end_datetime
        )
    else:
        metrics = metrics_repository.get_metrics(
            course_id, project_id, sprint_id, start_datetime, end_datetime
        )
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
    users: Annotated[UserRepository, Depends(get_user_repository)],
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
    github_metrics = ingest_github_metrics(payload, repository_path, metrics_repository, projects, users)
    jira_metrics = enrich_jira_metrics(payload)
    return {
        "github_metrics": github_metrics,
        "jira_metrics": jira_metrics,
    }
