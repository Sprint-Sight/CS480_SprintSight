from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import get_settings
from app.dependencies.auth import (
    get_assessment_repository,
    get_document_repository,
    get_jira_ingestion_repository,
    get_metrics_repository,
    get_peer_evaluation_repository,
    get_project_repository,
    require_admin,
)
from app.dependencies.insights import (
    ScopedReport,
    get_insights_repository,
    get_mlflow_gateway,
    get_scoped_report,
    require_insights_user,
    scoped_course_ids,
)
from app.repositories.insights import InsightsRepository, LabelInput
from app.repositories.interfaces import (
    AssessmentRepository,
    DocumentRepository,
    JiraIngestionRunRepository,
    MetricsRepository,
    PeerEvaluationRepository,
    ProjectRepository,
    UserRecord,
)
from app.services.insightsService import service
from app.services.insightsService.blind import is_override_mode
from app.services.insightsService.label_sync import sync_labels_for_report
from app.services.insightsService.mlflow_gateway import MlflowGateway
from app.services.insightsService.override_stats import override_stats

'''
Mlflow insights endpoints. All endpoints are prefixed with /insights 
and require the user to have the insights role.
'''

# Router-level dependency: every /insights route rejects students with 403.
router = APIRouter(
    prefix="/insights", tags=["insights"], dependencies=[Depends(require_insights_user)]
)

Dimension = Literal[
    "requirements", "code_quality", "testing", "documentation", "collaboration", "cicd"
]
CurrentUser = Annotated[UserRecord, Depends(require_insights_user)]
Insights = Annotated[InsightsRepository, Depends(get_insights_repository)]
Gateway = Annotated[MlflowGateway, Depends(get_mlflow_gateway)]
Scoped = Annotated[ScopedReport, Depends(get_scoped_report)]
Projects = Annotated[ProjectRepository, Depends(get_project_repository)]

class LabelIn(BaseModel): # Label input of the form {dimension, score, reason}
    dimension: Dimension
    score: int = Field(ge=1, le=10)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

class LabelsIn(BaseModel):
    labels: list[LabelIn] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _unique_dimensions(self): # Ensure that each dimension appears only once in the labels list.
        dims = [label.dimension for label in self.labels]
        if len(dims) != len(set(dims)):
            raise ValueError("Each dimension may appear only once.")
        return self

@router.get("/my-courses") # list of course that use has access to
def my_courses(user: CurrentUser, insights: Insights, projects: Projects):
    return service.my_courses(user, insights, projects)

@router.get("/runs")
def list_runs(
    user: CurrentUser,
    insights: Insights,
    projects: Projects,
    course_id: str | None = None,
    sprint_id: str | None = None,
    model: str | None = None,
    label_status: Literal["all", "labelled", "unlabelled"] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    return service.list_runs(
        user,
        insights,
        projects,
        course_id=course_id,
        sprint_id=sprint_id,
        model=model,
        label_status=label_status,
        page=page,
        page_size=page_size,
    )

@router.get("/reports/{report_id}/evidence")
def report_evidence(
    scoped: Scoped,
    insights: Insights,
    metrics: Annotated[MetricsRepository, Depends(get_metrics_repository)],
    jira: Annotated[JiraIngestionRunRepository, Depends(get_jira_ingestion_repository)],
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
    peers: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
):
    return service.evidence(scoped, insights, metrics, jira, documents, peers)

@router.put("/reports/{report_id}/labels")
def put_labels(
    body: LabelsIn,
    scoped: Scoped,
    insights: Insights,
    gateway: Gateway,
    background_tasks: BackgroundTasks,
):
    items = [LabelInput(label.dimension, label.score, label.reason) for label in body.labels]
    result = service.save_labels(scoped, items, insights)
    background_tasks.add_task(
        sync_labels_for_report, insights, gateway, scoped.report.report_id, scoped.user.id
    )
    return result

@router.get("/reports/{report_id}/reveal")
def reveal(scoped: Scoped, insights: Insights, gateway: Gateway):
    return service.reveal(
        scoped, insights, gateway, stale_minutes=get_settings().insights_judge_stale_minutes
    )

@router.get("/reports/{report_id}/trace")
def trace(scoped: Scoped, insights: Insights, gateway: Gateway):
    return service.trace_view(scoped, insights, gateway)

@router.get("/reports/{report_id}/judge-status")
def judge_status(scoped: Scoped, insights: Insights, gateway: Gateway):
    return service.judge_status_view(
        scoped, insights, gateway, stale_minutes=get_settings().insights_judge_stale_minutes
    )

@router.get("/health", dependencies=[Depends(require_admin)])
def insights_health(insights: Insights, gateway: Gateway):
    return service.health(gateway, insights)

@router.get("/config")
def insights_config():
    return {"mode": "override_gate" if is_override_mode() else "blind_label"}

@router.get("/override-stats")
def override_statistics(
    user: CurrentUser,
    insights: Insights,
    projects: Projects,
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
):
    """How often and how far overrides changed AI scores. Not an accuracy measure."""
    runs = insights.list_runs(scoped_course_ids(user, projects))
    reports = [r for r in (assessments.get_report(run.report_id) for run in runs) if r is not None]
    return override_stats(reports)