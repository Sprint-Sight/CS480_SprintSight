"""
Declares bundle: ArtifactBundle as a param
FastApi sees that type annotation, reads request body, validates it as ArtifactBundle, injects object auto
Gets back SprintAssessment object from evaluator, which FastAPI serializes to JSON and returns to client
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Annotated, Any

import mlflow
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.disconnect import ClientDisconnected, run_unless_disconnected
from evaluation.online.scheduler import get_arbiter, get_judge_queue
from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket
from schemas.modelname import ModelName
from schemas.peer_evaluation import PeerEvaluation
from schemas.repo_snapshot import RepoSnapshot
from schemas.sprint_assessment import SprintAssessment
from services.evaluator import evaluate_sprint

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
    repo_snapshot: RepoSnapshot | None = None
    instructor_expectations: str = "No instructor guidance provided."

def _enqueue_judge(experiment_name: str, trace_id: str, bundle: ArtifactBundle, prompt_versions: dict) -> bool:
    """Queue the judge for this trace. Judging is secondary to the assessment, so a queue
    failure is logged and must never fail the response the backend is waiting on."""
    try:
        return get_judge_queue().enqueue(
            trace_id=trace_id,
            experiment_name=experiment_name,
            team_id=bundle.team_id,
            sprint_id=bundle.sprint_id,
            prompt_versions=prompt_versions,
        )
    except Exception:
        log.exception("Could not queue the judge for trace %s; this trace will not be judged.", trace_id)
        return False

@router.post("/sprint/data", response_model=SprintAssessment, status_code=status.HTTP_200_OK)
async def assess_backend_data_endpoint(
    request: Request,
    payload: BackendAssessmentPayload,
    modelname: Annotated[
        ModelName,
        Query(description="Select the model to use for assessment"),
    ],
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
            repo_snapshot=payload.repo_snapshot,
            instructor_expectations=payload.instructor_expectations,
        )

        if LOG_BUNDLE_DISPLAY:
            print("\nBundle display: ", bundle)
            print()

        mlflow_client = mlflow.MlflowClient()

        trace_ids: list[str] = []

        async def grade():
            # Grading has priority for the single Ollama model slot; a judge job that is running
            # is waited for (bounded), and queued judge jobs wait for grading to go quiet.
            async with get_arbiter().grading():
                return await evaluate_sprint(bundle, modelname, experiment_name, mlflow_client, trace_ids)

        # If the backend hangs up (its timeout), cancel the grading: otherwise Ollama keeps
        # generating for a result nobody will read.
        assessment, prompt_versions_registered = await run_unless_disconnected(request, grade())

        if not trace_ids:
            raise RuntimeError("Sprint evaluation completed without recording an MLflow trace.")

        trace_id = trace_ids[-1]
        # The backend stores this next to the report: it is the join key to the judge verdict,
        # which does not exist yet because the judge runs after this response.
        assessment = assessment.model_copy(update={"trace_id": trace_id})

        # Durable, not BackgroundTasks: the job is a row, so a restart does not lose it.
        _enqueue_judge(experiment_name, trace_id, bundle, prompt_versions_registered)

        return assessment

    except ClientDisconnected:
        # Nobody is listening for the answer. 499 is the conventional "client closed request".
        raise HTTPException(status_code=499, detail="Client disconnected; assessment cancelled.") from None
    except Exception as exc:
        log.exception("AI-engine backend assessment failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
