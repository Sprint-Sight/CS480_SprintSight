from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.dependencies.auth import (
    get_assessment_repository,
    get_project_repository,
    require_password_changed,
)
from app.repositories.insights import InsightsRepository, RunRow, canonical_report_id
from app.repositories.interfaces import AssessmentRepository, ProjectRepository, UserRecord
from app.schemas.assessment import AssessmentReport
from app.schemas.auth import Role
from app.services.insightsService.mlflow_gateway import MlflowGateway

'''
Dependencies for the Insights API.
Dependencies are functions that FastAPI calls to provide arguments to route handlers.
They can also be used as decorators on route handlers to enforce authentication,
authorization, and other preconditions.
This file contains dependencies that are specific to the Insights API, such as
getting the Insights repository,
'''

def get_insights_repository(request: Request) -> InsightsRepository:
    repository = getattr(request.app.state, "insights_repository", None)
    if repository is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Insights storage is not configured."
        )
    return repository

def get_optional_insights_repository(request: Request) -> InsightsRepository | None:
    """Like get_insights_repository but never raises, so legacy routes work without Insights."""
    return getattr(request.app.state, "insights_repository", None)

def get_mlflow_gateway(request: Request) -> MlflowGateway:
    gateway = getattr(request.app.state, "mlflow_gateway", None)
    if gateway is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "MLflow gateway is not configured."
        )
    return gateway

def require_insights_user(current_user=Depends(require_password_changed)) -> UserRecord:
    """Applied to the whole /insights router: students (and anything else) get 403."""
    if current_user.role not in (Role.INSTRUCTOR, Role.ADMIN):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "AI insights are for instructors and admins only."
        )
    return current_user

@dataclass(frozen=True)
class ScopedReport:
    report: AssessmentReport
    run: RunRow
    user: UserRecord

    @property
    def is_admin(self) -> bool:
        return self.user.role == Role.ADMIN

def load_report(repository: AssessmentRepository, report_id: str) -> AssessmentReport | None:
    """Accepts 'rpt-<uuid>' or '<uuid>'; Postgres raises ValueError for non-UUID ids."""
    for candidate in dict.fromkeys((report_id, canonical_report_id(report_id))):
        try:
            report = repository.get_report(candidate)
        except ValueError:
            continue
        if report is not None:
            return report
    return None

def get_scoped_report(
    report_id: str,
    user: Annotated[UserRecord, Depends(require_insights_user)],
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    insights: Annotated[InsightsRepository, Depends(get_insights_repository)],
) -> ScopedReport:
    not_found = HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    if assessments is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Assessment repository unavailable."
        )
    report = load_report(assessments, report_id)
    if report is None:
        raise not_found
    # Out of scope is indistinguishable from unknown, so report IDs can't be probed.
    if user.role != Role.ADMIN and not projects.is_instructor_assigned(report.course_id, user.id):
        raise not_found
    run = insights.get_run(report.report_id)
    if run is None:
        raise not_found
    return ScopedReport(report=report, run=run, user=user)

def scoped_course_ids(user: UserRecord, projects: ProjectRepository) -> list[str] | None:
    """None means 'all courses' (admin)."""
    return None if user.role == Role.ADMIN else projects.list_instructor_course_ids(user.id)