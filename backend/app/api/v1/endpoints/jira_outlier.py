"""Instructor-only Jira contribution outlier endpoints.

These GET endpoints expose the evidence (Jira tickets) behind each student's
contribution score so instructors can review outliers and the AI engine can
consume the same structured data.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import (
    get_jira_ingestion_repository,
    get_project_repository,
    get_user_repository,
    require_faculty,
)
from app.repositories.interfaces import (
    JiraIngestionRunRepository,
    ProjectRepository,
    UserRepository,
)
from app.schemas.jira_outlier import (
    JiraContributionOutlierReport,
    JiraContributionOutlierResponse,
)
from app.services.jiraService.service import (
    get_jira_contribution_outlier,
    get_jira_contribution_outliers,
)

router = APIRouter(
    prefix="/jira/contribution-outliers",
    tags=["jira-contribution-outliers"],
    dependencies=[Depends(require_faculty)],
)


@router.get(
    "/courses/{course_id}",
    response_model=JiraContributionOutlierReport,
    summary="List Jira-contribution outliers for an entire course",
)
def list_jira_contribution_outliers(
    course_id: str,
    jira_repo: Annotated[
        JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)
    ],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    only_outliers: bool = Query(
        default=False,
        description="When true, return only students flagged as outliers.",
    ),
) -> JiraContributionOutlierReport:
    """Return contribution totals, course statistics, and ticket evidence.

    Every enrolled student is included (zero points when they have no Jira
    tickets). Use ``only_outliers=true`` for a short list of flagged students.
    """
    return get_jira_contribution_outliers(
        course_id=course_id,
        jira_repo=jira_repo,
        user_repo=user_repo,
        project_repo=project_repo,
        only_outliers=only_outliers,
    )


@router.get(
    "/courses/{course_id}/students/{student_id}",
    response_model=JiraContributionOutlierResponse,
    summary="Get Jira-contribution outlier info for a single student",
)
def jira_contribution_outlier(
    course_id: str,
    student_id: str,
    jira_repo: Annotated[
        JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)
    ],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> JiraContributionOutlierResponse:
    """Instructor-only endpoint that shows how outlier-ish a student's Jira
    contribution is, together with the tickets that make up the total.

    This is different from the peer-evaluation outlier
    (``is_total_outlier``) because it is based on story-point volume rather
    than peer ratings.
    """
    return get_jira_contribution_outlier(
        course_id=course_id,
        student_id=student_id,
        jira_repo=jira_repo,
        user_repo=user_repo,
        project_repo=project_repo,
    )
