"""
Declares bundle: ArtifactBundle as a param
FastApi sees that type annotation, reads request body, validates it as ArtifactBundle, injects object auto
Gets back SprintAssessment object from evaluator, which FastAPI serializes to JSON and returns to client
"""

from __future__ import annotations

import logging, os, mlflow
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket
from schemas.modelname import ModelName
from schemas.peer_evaluation import PeerEvaluation
from schemas.sprint_assessment import SprintAssessment
from services.evaluator import evaluate_sprint

from judges.promote import judge_and_promote_trace

log = logging.getLogger("sprintsight.router.assessment")

# Bundle contents can be large and may include student data, so printing is opt-in.
LOG_BUNDLE_DISPLAY = os.getenv("LOG_BUNDLE_DISPLAY", "false").strip().lower() in ("1", "true", "yes")

router = APIRouter( # Create router (defines path group)
    prefix="/assess",
    tags=["Sprint Assessment"]
)

class BackendSprintContext(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    captured_at: datetime | str

class BackendCollaborationMetrics(BaseModel):
    commit_frequency: float | None = None
    code_churn: int | None = None
    pr_turnaround_hours: float | None = None
    assigned_story_points: int | None = None
    completion_percent: float | None = None

class BackendAssessmentPayload(BaseModel):
    sprint_context: BackendSprintContext
    collaboration_metrics: BackendCollaborationMetrics = Field(default_factory=BackendCollaborationMetrics)
    commits: list[CommitInfo] = Field(default_factory=list)
    jira_tickets: list[JiraTicket] = Field(default_factory=list)
    peer_evaluations: list[PeerEvaluation] = Field(default_factory=list)
    artifact_metrics: dict[str, Any] = Field(default_factory=dict)
    project_context_documents: list[dict[str, Any]] = Field(default_factory=list)
    instructor_expectations: str = "No instructor guidance provided."

@router.post("/sprint/data", response_model=SprintAssessment, status_code=status.HTTP_200_OK)
async def assess_backend_data_endpoint(
    payload: BackendAssessmentPayload,
    modelname: Annotated[
        ModelName,
        Query(description="Select the model to use for assessment"),
    ],
    background_tasks: BackgroundTasks,
    experiment_name: str = "SprintSight Evaluations",
):
    """Accept the backend middleman payload and evaluate it with the configured model."""
    try:
        bundle = ArtifactBundle(
            team_id=payload.sprint_context.project_id,
            sprint_id=payload.sprint_context.sprint_id,
            commits=payload.commits,
            jira_tickets=payload.jira_tickets,
            peer_evaluations=payload.peer_evaluations,
            collaboration_metrics=payload.collaboration_metrics.model_dump(),
            artifact_metrics=payload.artifact_metrics,
            project_context_documents=payload.project_context_documents,
            instructor_expectations=payload.instructor_expectations,
        )

        if LOG_BUNDLE_DISPLAY:
            print("\nBundle display: ", bundle)
            print()

        mlflow_client = mlflow.MlflowClient()

        assessment, prompt_versions_registered = await evaluate_sprint(bundle, modelname, experiment_name, mlflow_client)
        trace_id = mlflow.get_last_active_trace_id() # trace evaluate_sprint just created

        # Add a background task to promote the trace to production after evaluation, or handle it in the evaluator itself.
        background_tasks.add_task(judge_and_promote_trace, experiment_name, trace_id, bundle.team_id, prompt_versions_registered, mlflow_client, bundle.sprint_id)

        if mlflow.active_run(): # Play safe and close any active run from previous call (if any)
            mlflow.end_run()
            print("Closed active MLflow run.")
        return assessment
    
    except Exception as exc:
        log.exception("AI-engine backend assessment failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc